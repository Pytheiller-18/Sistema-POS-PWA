from flask import Blueprint, request, jsonify, g
from app.middlewares.auth import tenant_required
from app.services.report_service import (
    get_today_summary,
    get_monthly_summary,
    get_annual_summary,
    get_top_products,
    get_profit_summary
)

reports_bp = Blueprint('reports', __name__, url_prefix='/api/v1/reports')

# ============================================================================
# DOBLE VERIFICACIÓN DE SEGURIDAD - ANALÍTICAS FINANCIERAS:
# 1. El acceso a reportes está restringido a roles gerenciales (ADMIN, MANAGER).
# 2. Toda función de servicio recibe explícitamente `g.tenant_id`. No es posible
#    consultar las métricas de otra empresa cambiando parámetros en la URL.
# ============================================================================

@reports_bp.route('/today', methods=['GET'])
@tenant_required(allowed_roles=['ADMIN', 'MANAGER'])
def report_today():
    """Resumen de ventas del día en curso."""
    data = get_today_summary(g.tenant_id)
    return jsonify({'success': True, 'data': data}), 200

@reports_bp.route('/monthly', methods=['GET'])
@tenant_required(allowed_roles=['ADMIN', 'MANAGER'])
def report_monthly():
    """Resumen del mes actual y comparativa con el mes previo."""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    data = get_monthly_summary(g.tenant_id, year=year, month=month)
    return jsonify({'success': True, 'data': data}), 200

@reports_bp.route('/annual', methods=['GET'])
@tenant_required(allowed_roles=['ADMIN', 'MANAGER'])
def report_annual():
    """Resumen acumulado del año desglosado mes a mes."""
    year = request.args.get('year', type=int)
    data = get_annual_summary(g.tenant_id, year=year)
    return jsonify({'success': True, 'data': data}), 200

@reports_bp.route('/top-products', methods=['GET'])
@tenant_required(allowed_roles=['ADMIN', 'MANAGER'])
def report_top_products():
    """Top productos con mayor volumen de ventas e ingresos."""
    limit = request.args.get('limit', default=5, type=int)
    data = get_top_products(g.tenant_id, limit=limit)
    return jsonify({'success': True, 'data': data}), 200

@reports_bp.route('/profit', methods=['GET'])
@tenant_required(allowed_roles=['ADMIN'])
def report_profit():
    """Utilidad neta, costos totales y margen de ganancia."""
    data = get_profit_summary(g.tenant_id)
    return jsonify({'success': True, 'data': data}), 200
