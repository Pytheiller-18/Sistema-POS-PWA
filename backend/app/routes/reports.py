from flask import Blueprint, request, jsonify, g
from app.middlewares.auth import tenant_required
from app.utils.validators import to_int
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
    year_param = request.args.get('year')
    month_param = request.args.get('month')
    year = to_int(year_param, 'year', min_value=2000, max_value=2100) if year_param else None
    month = to_int(month_param, 'month', min_value=1, max_value=12) if month_param else None
    data = get_monthly_summary(g.tenant_id, year=year, month=month)
    return jsonify({'success': True, 'data': data}), 200

@reports_bp.route('/annual', methods=['GET'])
@tenant_required(allowed_roles=['ADMIN', 'MANAGER'])
def report_annual():
    """Resumen acumulado del año desglosado mes a mes."""
    year_param = request.args.get('year')
    year = to_int(year_param, 'year', min_value=2000, max_value=2100) if year_param else None
    data = get_annual_summary(g.tenant_id, year=year)
    return jsonify({'success': True, 'data': data}), 200

@reports_bp.route('/top-products', methods=['GET'])
@tenant_required(allowed_roles=['ADMIN', 'MANAGER'])
def report_top_products():
    """Top productos con mayor volumen de ventas e ingresos."""
    limit_param = request.args.get('limit')
    limit = to_int(limit_param, 'limit', default=5, min_value=1, max_value=50) if limit_param else 5
    data = get_top_products(g.tenant_id, limit=limit)
    return jsonify({'success': True, 'data': data}), 200

@reports_bp.route('/profit', methods=['GET'])
@tenant_required(allowed_roles=['ADMIN'])
def report_profit():
    """Utilidad neta, costos totales y margen de ganancia."""
    data = get_profit_summary(g.tenant_id)
    return jsonify({'success': True, 'data': data}), 200
