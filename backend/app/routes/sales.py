from datetime import datetime
from flask import Blueprint, request, jsonify, g
from app.models.sale import Sale
from app.services.sale_service import process_sale
from app.middlewares.auth import tenant_required

sales_bp = Blueprint('sales', __name__, url_prefix='/api/v1/sales')

# ============================================================================
# DOBLE VERIFICACIÓN DE SEGURIDAD - VENTAS:
# 1. process_sale() encapsula toda la transacción asegurando que el cajero
#    solo pueda registrar ventas para el tenant al que pertenece.
# 2. Las consultas históricas no pueden acceder a transacciones de otros tenants.
# ============================================================================

@sales_bp.route('', methods=['POST'])
@tenant_required()
def create_sale():
    """Registra una venta en el punto de venta de forma directa/online."""
    data = request.get_json() or {}
    result, status_code = process_sale(
        tenant_id=g.tenant_id,
        user_id=g.user_id,
        data=data,
        sync_status='ONLINE'
    )
    return jsonify(result), status_code

@sales_bp.route('', methods=['GET'])
@tenant_required()
def list_sales():
    """Lista las ventas del tenant con soporte de paginación y filtros de fecha."""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = Sale.query.filter_by(tenant_id=g.tenant_id)

    if start_date:
        try:
            st = datetime.fromisoformat(start_date)
            query = query.filter(Sale.created_at >= st)
        except Exception:
            pass

    if end_date:
        try:
            et = datetime.fromisoformat(end_date)
            query = query.filter(Sale.created_at <= et)
        except Exception:
            pass

    paginated = query.order_by(Sale.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'success': True,
        'page': page,
        'per_page': per_page,
        'total_records': paginated.total,
        'total_pages': paginated.pages,
        'sales': [s.to_dict(include_items=False) for s in paginated.items]
    }), 200

@sales_bp.route('/<sale_id>', methods=['GET'])
@tenant_required()
def get_sale(sale_id):
    """Obtiene el detalle completo de una venta e ítems para impresión de ticket."""
    sale = Sale.query.filter_by(id=sale_id, tenant_id=g.tenant_id).first_or_404(
        description="Venta no encontrada en su tienda"
    )
    return jsonify({
        'success': True,
        'sale': sale.to_dict(include_items=True)
    }), 200
