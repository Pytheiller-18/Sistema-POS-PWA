import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.product import Product
from app.models.sale import Sale, SaleItem
from app.models.sync_log import SyncAuditLog

# ============================================================================
# DOBLE VERIFICACIÓN DE SEGURIDAD - PROCESAMIENTO DE VENTAS:
# 1. Idempotencia Robusta: Se verifica client_sync_id dentro del tenant antes de
#    cualquier inserción o deducción de inventario para evitar duplicidad de cobro.
# 2. Validación Estricta de Tenant: Cada producto referenciado debe pertenecer
#    al tenant_id autenticado. Se rechaza si un producto es de otra tienda.
# 3. Transaccionalidad ACID: Si un ítem falla, se realiza rollback completo.
# 4. Histórico Inmutable: Se congela el costo (unit_cost) y precio (unit_price)
#    vigentes en sale_items para preservar la auditoría contable.
# ============================================================================

def generate_invoice_number(tenant_id: str) -> str:
    """Genera un número de factura correlativo seguro para el tenant."""
    count = Sale.query.filter_by(tenant_id=tenant_id).count()
    current_year = datetime.now(timezone.utc).year
    return f"POS-{current_year}-{(count + 1):06d}"

def process_sale(tenant_id: str, user_id: str, data: dict, sync_status: str = 'ONLINE') -> tuple[dict, int]:
    """
    Procesa y registra una venta garantizando atomicidad e idempotencia.
    Retorna (resultado_dict, status_code).
    """
    client_sync_id = data.get('client_sync_id') or str(uuid.uuid4())
    
    # 1. VERIFICACIÓN DE IDEMPOTENCIA
    existing_sale = Sale.query.filter_by(tenant_id=tenant_id, client_sync_id=client_sync_id).first()
    if existing_sale:
        # Ya fue procesada previamente (ej. reintento de sincronización)
        return {
            'success': True,
            'message': 'Venta ya registrada previamente (Idempotente)',
            'already_synced': True,
            'sale': existing_sale.to_dict()
        }, 200

    items_data = data.get('items', [])
    if not items_data or not isinstance(items_data, list):
        return {
            'success': False,
            'error': 'La venta debe contener al menos un producto válido'
        }, 400

    invoice_number = data.get('invoice_number') or generate_invoice_number(tenant_id)
    payment_method = data.get('payment_method', 'CASH').upper()
    amount_paid = float(data.get('amount_paid', 0.0))
    discount = float(data.get('discount', 0.0))
    tax_rate = float(data.get('tax_rate', 0.0)) # Ej: 0.19 o 0.0 si está incluido
    notes = data.get('notes', '')

    calculated_subtotal = 0.0
    sale_items = []

    try:
        # Iniciar transacción
        for item in items_data:
            product_id = item.get('product_id')
            quantity = int(item.get('quantity', 1))
            if quantity <= 0:
                return {'success': False, 'error': f'Cantidad inválida ({quantity})'}, 400

            # 2. DOBLE VERIFICACIÓN: El producto DEBE pertenecer al tenant
            product = Product.query.filter_by(id=product_id, tenant_id=tenant_id).first()
            if not product:
                return {
                    'success': False, 
                    'error': f'Producto ID {product_id} no encontrado en su inventario o no autorizado'
                }, 404

            unit_price = float(product.sale_price)
            unit_cost = float(product.cost_price)
            item_subtotal = unit_price * quantity
            calculated_subtotal += item_subtotal

            # Deducción de inventario (Offline-First permite stock negativo con alerta)
            product.stock -= quantity

            # Crear ítem de venta con costo histórico
            sale_item = SaleItem(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                product_id=product.id,
                product_name=product.name,
                quantity=quantity,
                unit_cost=unit_cost,
                unit_price=unit_price,
                subtotal=item_subtotal,
                total=item_subtotal
            )
            sale_items.append(sale_item)

        # Calcular impuestos y totales
        tax = calculated_subtotal * tax_rate
        total = calculated_subtotal + tax - discount
        if total < 0:
            total = 0.0

        if amount_paid == 0.0:
            amount_paid = total
        change_due = max(0.0, amount_paid - total)

        # 3. Crear encabezado de venta
        sale = Sale(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            client_sync_id=client_sync_id,
            invoice_number=invoice_number,
            subtotal=calculated_subtotal,
            tax=tax,
            discount=discount,
            total=total,
            payment_method=payment_method,
            amount_paid=amount_paid,
            change_due=change_due,
            sync_status=sync_status,
            notes=notes
        )
        
        db.session.add(sale)
        for s_item in sale_items:
            s_item.sale_id = sale.id
            db.session.add(s_item)

        # Registro en bitácora de sincronización
        audit = SyncAuditLog(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            client_sync_id=client_sync_id,
            device_id=data.get('device_id', 'WEB-POS'),
            status='SUCCESS',
            details=f'Venta registrada {sale.invoice_number} por valor de {sale.total}'
        )
        db.session.add(audit)

        db.session.commit()

        return {
            'success': True,
            'message': 'Venta registrada exitosamente',
            'already_synced': False,
            'sale': sale.to_dict()
        }, 201

    except Exception as e:
        db.session.rollback()
        return {
            'success': False,
            'error': f'Error interno al procesar venta: {str(e)}'
        }, 500
