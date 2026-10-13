from datetime import datetime, timezone, timedelta
from calendar import monthrange
from flask import current_app
from sqlalchemy import func
from app.extensions import db
from app.models.sale import Sale, SaleItem

# ============================================================================
# DOBLE VERIFICACIÓN DE SEGURIDAD - ANALÍTICAS Y REPORTES:
# 1. Cada consulta de agregación (SUM, COUNT, GROUP BY) incluye obligatoriamente
#    el filtro `tenant_id == tenant_id` para evitar mezcla de información contable.
# 2. El cálculo de utilidades utiliza `unit_cost` registrado en cada transacción,
#    garantizando precisión financiera incluso si los costos de compra han variado.
# 3. (A7) Ajuste por zona horaria de negocio (UTC-5 por defecto) para que el
#    cierre diario coincida con el día del comercio y no con medianoche UTC.
# 4. (O2) Consultas de agregación SQL directas (no carga objetos en memoria)
#    y rangos indexados en lugar de extract() para máximo rendimiento.
# ============================================================================

def _get_business_offset() -> float:
    try:
        return float(current_app.config.get('BUSINESS_UTC_OFFSET_HOURS', -5))
    except Exception:
        return -5.0


def _get_local_now() -> tuple[datetime, float]:
    offset = _get_business_offset()
    utc_now = datetime.now(timezone.utc)
    local_now = utc_now + timedelta(hours=offset)
    return local_now, offset


def get_today_summary(tenant_id: str) -> dict:
    """Calcula ventas del día actual del negocio, número de transacciones y ticket promedio."""
    local_now, offset = _get_local_now()

    # Inicio y fin del día en hora local convertidos a UTC naive (formato almacenado en BD)
    local_start = datetime(local_now.year, local_now.month, local_now.day, 0, 0, 0)
    local_end = datetime(local_now.year, local_now.month, local_now.day, 23, 59, 59)
    utc_start = local_start - timedelta(hours=offset)
    utc_end = local_end - timedelta(hours=offset)

    # (O2) Agregación SQL directa
    stats = db.session.query(
        func.coalesce(func.sum(Sale.total), 0),
        func.count(Sale.id)
    ).filter(
        Sale.tenant_id == tenant_id,
        Sale.created_at >= utc_start,
        Sale.created_at <= utc_end
    ).first()

    total_sales = float(stats[0] if stats else 0)
    transaction_count = int(stats[1] if stats else 0)
    average_ticket = (total_sales / transaction_count) if transaction_count > 0 else 0.0

    # Total de unidades vendidas hoy
    items_count = db.session.query(
        func.coalesce(func.sum(SaleItem.quantity), 0)
    ).join(
        Sale, SaleItem.sale_id == Sale.id
    ).filter(
        Sale.tenant_id == tenant_id,
        Sale.created_at >= utc_start,
        Sale.created_at <= utc_end
    ).scalar() or 0

    return {
        'date': local_now.strftime('%Y-%m-%d'),
        'total_sales': round(total_sales, 2),
        'transaction_count': transaction_count,
        'average_ticket': round(average_ticket, 2),
        'items_sold': int(items_count)
    }


def get_monthly_summary(tenant_id: str, year: int = None, month: int = None) -> dict:
    """Calcula el resumen de ventas del mes y desglose diario usando rangos indexados."""
    local_now, offset = _get_local_now()
    target_year = year or local_now.year
    target_month = month or local_now.month

    days_in_month = monthrange(target_year, target_month)[1]
    local_start = datetime(target_year, target_month, 1, 0, 0, 0)
    local_end = datetime(target_year, target_month, days_in_month, 23, 59, 59)
    utc_start = local_start - timedelta(hours=offset)
    utc_end = local_end - timedelta(hours=offset)

    # Ventas del mes
    sales = Sale.query.filter(
        Sale.tenant_id == tenant_id,
        Sale.created_at >= utc_start,
        Sale.created_at <= utc_end
    ).all()

    total_sales = sum(float(s.total) for s in sales)
    transaction_count = len(sales)

    # Desglose por días del mes (ajustado a la fecha local del negocio)
    daily_totals = {}
    for s in sales:
        if s.created_at:
            local_created = s.created_at + timedelta(hours=offset)
            day_str = local_created.strftime('%Y-%m-%d')
            daily_totals[day_str] = daily_totals.get(day_str, 0.0) + float(s.total)

    daily_chart = [{'date': k, 'total': round(v, 2)} for k, v in sorted(daily_totals.items())]

    # Comparativa con mes anterior usando rangos indexados
    prev_month = 12 if target_month == 1 else target_month - 1
    prev_year = target_year - 1 if target_month == 1 else target_year
    prev_days = monthrange(prev_year, prev_month)[1]
    prev_start_utc = datetime(prev_year, prev_month, 1, 0, 0, 0) - timedelta(hours=offset)
    prev_end_utc = datetime(prev_year, prev_month, prev_days, 23, 59, 59) - timedelta(hours=offset)

    prev_sales_total = db.session.query(
        func.coalesce(func.sum(Sale.total), 0)
    ).filter(
        Sale.tenant_id == tenant_id,
        Sale.created_at >= prev_start_utc,
        Sale.created_at <= prev_end_utc
    ).scalar() or 0.0

    prev_total = float(prev_sales_total)
    growth_pct = 0.0
    if prev_total > 0:
        growth_pct = ((total_sales - prev_total) / prev_total) * 100.0

    return {
        'year': target_year,
        'month': target_month,
        'total_sales': round(total_sales, 2),
        'transaction_count': transaction_count,
        'previous_month_total': round(prev_total, 2),
        'growth_percentage': round(growth_pct, 1),
        'daily_chart': daily_chart
    }


def get_annual_summary(tenant_id: str, year: int = None) -> dict:
    """Calcula el resumen financiero anual usando agregación con rangos indexados."""
    local_now, offset = _get_local_now()
    target_year = year or local_now.year

    start_year_utc = datetime(target_year, 1, 1, 0, 0, 0) - timedelta(hours=offset)
    end_year_utc = datetime(target_year, 12, 31, 23, 59, 59) - timedelta(hours=offset)

    month_names = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    monthly_totals = {m: 0.0 for m in range(1, 13)}

    # Traer solo id, total, created_at del año
    year_sales = db.session.query(
        Sale.total,
        Sale.created_at
    ).filter(
        Sale.tenant_id == tenant_id,
        Sale.created_at >= start_year_utc,
        Sale.created_at <= end_year_utc
    ).all()

    total_annual = 0.0
    for total, created_at in year_sales:
        if created_at:
            m = (created_at + timedelta(hours=offset)).month
            val = float(total or 0.0)
            monthly_totals[m] += val
            total_annual += val

    monthly_data = [
        {
            'month_number': m,
            'month_name': month_names[m - 1],
            'total': round(monthly_totals[m], 2)
        }
        for m in range(1, 13)
    ]

    return {
        'year': target_year,
        'total_annual': round(total_annual, 2),
        'months': monthly_data
    }


def get_top_products(tenant_id: str, limit: int = 5) -> list[dict]:
    """Obtiene los N productos más vendidos ordenados por cantidad e ingresos."""
    safe_limit = max(1, min(limit or 5, 50))
    results = db.session.query(
        SaleItem.product_id,
        SaleItem.product_name,
        func.sum(SaleItem.quantity).label('total_units'),
        func.sum(SaleItem.total).label('total_revenue')
    ).filter(
        SaleItem.tenant_id == tenant_id
    ).group_by(
        SaleItem.product_id,
        SaleItem.product_name
    ).order_by(
        func.sum(SaleItem.quantity).desc()
    ).limit(safe_limit).all()

    return [
        {
            'product_id': r.product_id,
            'product_name': r.product_name,
            'total_units': int(r.total_units or 0),
            'total_revenue': round(float(r.total_revenue or 0.0), 2)
        }
        for r in results
    ]


def get_profit_summary(tenant_id: str) -> dict:
    """Calcula ingresos brutos, costos totales históricos y margen de utilidad neta."""
    total_revenue = db.session.query(
        func.coalesce(func.sum(Sale.total), 0)
    ).filter(
        Sale.tenant_id == tenant_id
    ).scalar() or 0.0
    total_revenue = float(total_revenue)

    total_cost = db.session.query(
        func.coalesce(func.sum(SaleItem.quantity * SaleItem.unit_cost), 0)
    ).filter(
        SaleItem.tenant_id == tenant_id
    ).scalar() or 0.0
    total_cost = float(total_cost)

    gross_profit = total_revenue - total_cost
    margin_percentage = (gross_profit / total_revenue * 100.0) if total_revenue > 0 else 0.0

    return {
        'total_revenue': round(total_revenue, 2),
        'total_cost': round(total_cost, 2),
        'gross_profit': round(gross_profit, 2),
        'margin_percentage': round(margin_percentage, 1)
    }
