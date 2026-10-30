from datetime import datetime, timezone
from decimal import Decimal
from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.product import Product
from app.models.sale import Sale, SaleItem
from app.models.sync_log import SyncAuditLog
from app.utils.validators import ValidationError, to_decimal, to_int, clean_str, TWO_PLACES
from app.utils.uuid7 import uuid7_str

# ============================================================================
# DOBLE VERIFICACIÓN DE SEGURIDAD - PROCESAMIENTO DE VENTAS:
# 1. Idempotencia Robusta: Se verifica client_sync_id dentro del tenant antes de
#    cualquier inserción o deducción de inventario para evitar duplicidad de cobro.
#    Si dos peticiones idénticas compiten, la restricción UNIQUE resuelve la carrera
#    y la perdedora responde 'already_synced' (nunca 500 ni doble descuento).
# 2. Validación Estricta de Tenant: Cada producto referenciado debe pertenecer
#    al tenant_id autenticado. Se rechaza si un producto es de otra tienda.
# 3. Transaccionalidad ACID (C2): TODO se valida ANTES de modificar inventario.
#    Cualquier fallo hace rollback completo; jamás queda stock descontado a medias.
# 4. Histórico Inmutable: Se congela el costo (unit_cost) y precio (unit_price)
#    vigentes en sale_items para preservar la auditoría contable.
# 5. (A1) El servidor es la fuente de verdad: precios, descuento, impuesto,
#    método de pago y número de factura se validan/generan en backend.
# 6. (O5) Aritmética monetaria con Decimal (sin errores de redondeo de float).
# ============================================================================

VALID_PAYMENT_METHODS = {'CASH', 'CARD', 'TRANSFER', 'OTHER'}
MAX_ITEMS_PER_SALE = 500
MAX_QTY_PER_ITEM = 100_000
MAX_INVOICE_RETRIES = 3
ZERO = Decimal('0.00')


class SaleError(Exception):
    """Error de negocio con código HTTP asociado."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def generate_invoice_number(tenant_id: str) -> str:
    """
    (A2) Genera el siguiente número correlativo POS-AAAA-NNNNNN del tenant.
    Se basa en el MAYOR número existente del año (no en COUNT, que repite números
    si se eliminan ventas) y la restricción UNIQUE(tenant_id, invoice_number)
    + reintentos garantizan unicidad incluso con peticiones concurrentes.
    """
    year = datetime.now(timezone.utc).year
    prefix = f"POS-{year}-"
    last = db.session.query(func.max(Sale.invoice_number)).filter(
        Sale.tenant_id == tenant_id,
        Sale.invoice_number.like(f"{prefix}%")
    ).scalar()
    next_seq = 1
    if last:
        try:
            next_seq = int(last[len(prefix):]) + 1
        except ValueError:
            next_seq = 1
    return f"{prefix}{next_seq:06d}"


def _idempotent_response(sale: Sale) -> tuple[dict, int]:
    return {
        'success': True,
        'message': 'Venta ya registrada previamente (Idempotente)',
        'already_synced': True,
        'sale': sale.to_dict()
    }, 200


def _parse_sale_input(data: dict) -> dict:
    """Valida y normaliza el payload de venta. Lanza ValidationError/SaleError."""
    items_data = data.get('items')
    if not items_data or not isinstance(items_data, list):
        raise SaleError('La venta debe contener al menos un producto válido', 400)
    if len(items_data) > MAX_ITEMS_PER_SALE:
        raise SaleError(f'La venta excede el máximo de {MAX_ITEMS_PER_SALE} ítems', 400)

    # Agrupar líneas repetidas del mismo producto
    quantities: dict[str, int] = {}
    for item in items_data:
        if not isinstance(item, dict) or not item.get('product_id'):
            raise SaleError('Cada ítem debe incluir product_id', 400)
        pid = str(item['product_id'])
        qty = to_int(item.get('quantity'), 'quantity', default=1, min_value=1, max_value=MAX_QTY_PER_ITEM)
        quantities[pid] = quantities.get(pid, 0) + qty

    payment_method = str(data.get('payment_method') or 'CASH').upper()
    if payment_method not in VALID_PAYMENT_METHODS:
        raise SaleError(f'Método de pago inválido: {payment_method}', 400)

    return {
        'quantities': quantities,
        'payment_method': payment_method,
        'amount_paid': to_decimal(data.get('amount_paid'), 'amount_paid', default=0, min_value=0, max_value=10**10),
        'discount': to_decimal(data.get('discount'), 'discount', default=0, min_value=0, max_value=10**10),
        # Tasa de impuesto (0.19 = 19%). Rango cerrado para impedir manipulación.
        'tax_rate': to_decimal(data.get('tax_rate'), 'tax_rate', default=0, min_value=0, max_value=1),
        'notes': clean_str(data.get('notes'), 'notes', 255),
        'device_id': clean_str(str(data.get('device_id') or 'WEB-POS'), 'device_id', 100),
    }


def _persist_sale(tenant_id: str, user_id: str, client_sync_id: str, parsed: dict, sync_status: str) -> Sale:
    """Construye y confirma la venta en una única transacción. Lanza SaleError/IntegrityError."""
    quantities = parsed['quantities']

    # 1. Cargar TODOS los productos en una sola consulta, filtrando por tenant
    products = Product.query.filter(
        Product.tenant_id == tenant_id,
        Product.id.in_(list(quantities.keys()))
    ).all()
    product_map = {p.id: p for p in products}

    # 2. Validar ANTES de mutar inventario (C2)
    missing = [pid for pid in quantities if pid not in product_map]
    if missing:
        raise SaleError(f'Producto ID {missing[0]} no encontrado en su inventario o no autorizado', 404)

    # 3. Construir ítems con precios del servidor
    subtotal = ZERO
    sale_items = []
    for pid, qty in quantities.items():
        product = product_map[pid]
        unit_price = Decimal(product.sale_price or 0).quantize(TWO_PLACES)
        unit_cost = Decimal(product.cost_price or 0).quantize(TWO_PLACES)
        line_total = (unit_price * qty).quantize(TWO_PLACES)
        subtotal += line_total
        sale_items.append(SaleItem(
            id=uuid7_str(),
            tenant_id=tenant_id,
            product_id=product.id,
            product_name=product.name,
            quantity=qty,
            unit_cost=unit_cost,
            unit_price=unit_price,
            subtotal=line_total,
            total=line_total
        ))

    # 4. Totales
    discount = min(parsed['discount'], subtotal)  # El descuento nunca supera el subtotal
    tax = ((subtotal - discount) * parsed['tax_rate']).quantize(TWO_PLACES)
    total = max(ZERO, subtotal - discount + tax)
    amount_paid = parsed['amount_paid'] if parsed['amount_paid'] > ZERO else total
    change_due = max(ZERO, amount_paid - total)

    # 5. Deducción ATÓMICA de inventario (UPDATE stock = stock - n en SQL, evita
    #    pérdidas por condiciones de carrera entre terminales). Offline-First permite
    #    stock negativo, que se refleja como alerta en el inventario.
    for pid, qty in quantities.items():
        product_map[pid].stock = Product.stock - qty

    sale = Sale(
        id=uuid7_str(),
        tenant_id=tenant_id,
        user_id=user_id,
        client_sync_id=client_sync_id,
        invoice_number=generate_invoice_number(tenant_id),
        subtotal=subtotal,
        tax=tax,
        discount=discount,
        total=total,
        payment_method=parsed['payment_method'],
        amount_paid=amount_paid,
        change_due=change_due,
        sync_status=sync_status,
        notes=parsed['notes']
    )
    db.session.add(sale)
    for s_item in sale_items:
        s_item.sale_id = sale.id
        db.session.add(s_item)

    db.session.add(SyncAuditLog(
        id=uuid7_str(),
        tenant_id=tenant_id,
        client_sync_id=client_sync_id,
        device_id=parsed['device_id'],
        status='SUCCESS',
        details=f'Venta registrada {sale.invoice_number} por valor de {total}'
    ))

    db.session.commit()
    return sale


def process_sale(tenant_id: str, user_id: str, data: dict, sync_status: str = 'ONLINE') -> tuple[dict, int]:
    """
    Procesa y registra una venta garantizando atomicidad e idempotencia.
    Retorna (resultado_dict, status_code). Nunca lanza excepciones al llamador.
    """
    if not isinstance(data, dict):
        return {'success': False, 'error': 'Formato de venta inválido'}, 400

    client_sync_id = str(data.get('client_sync_id') or uuid7_str())
    if len(client_sync_id) > 64:
        return {'success': False, 'error': 'client_sync_id excede 64 caracteres'}, 400

    # 1. VERIFICACIÓN DE IDEMPOTENCIA
    existing_sale = Sale.query.filter_by(tenant_id=tenant_id, client_sync_id=client_sync_id).first()
    if existing_sale:
        return _idempotent_response(existing_sale)

    try:
        parsed = _parse_sale_input(data)
    except (ValidationError, SaleError) as e:
        return {'success': False, 'error': str(e)}, getattr(e, 'status', 400)

    for attempt in range(MAX_INVOICE_RETRIES):
        try:
            sale = _persist_sale(tenant_id, user_id, client_sync_id, parsed, sync_status)
            return {
                'success': True,
                'message': 'Venta registrada exitosamente',
                'already_synced': False,
                'sale': sale.to_dict()
            }, 201
        except SaleError as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}, e.status
        except IntegrityError:
            db.session.rollback()
            # ¿Otra petición idéntica ganó la carrera? => idempotente
            winner = Sale.query.filter_by(tenant_id=tenant_id, client_sync_id=client_sync_id).first()
            if winner:
                return _idempotent_response(winner)
            # Si no, colisión de número de factura: reintentar con el siguiente
            continue
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error interno al procesar venta')
            return {'success': False, 'error': 'Error interno al procesar la venta'}, 500

    return {'success': False, 'error': 'No fue posible asignar número de factura, reintente'}, 409
