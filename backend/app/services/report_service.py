from datetime import datetime, timezone, timedelta
from sqlalchemy import func, extract
from app.extensions import db
from app.models.sale import Sale, SaleItem

# ============================================================================
# DOBLE VERIFICACIÓN DE SEGURIDAD - ANALÍTICAS Y REPORTES:
# 1. Cada consulta de agregación (SUM, COUNT, GROUP BY) incluye obligatoriamente
#    el filtro `tenant_id == tenant_id` para evitar mezcla de información contable.
# 2. El cálculo de utilidades utiliza `unit_cost` registrado en cada transacción,
#    garantizando precisión financiera incluso si los costos de compra han variado.
# ============================================================================

def get_today_summary(tenant_id: str) -> dict:
    """Calcula ventas del día actual, número de transacciones y ticket promedio."""
    now = datetime.now(timezone.utc)
    start_of_day = datetime(now.year, now.month, now.day, 0, 0, 0)
    end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59)

    sales = Sale.query.filter(
        Sale.tenant_id == tenant_id,
        Sale.created_at >= start_of_day,
        Sale.created_at <= end_of_day
    ).all()

    total_sales = sum(float(s.total) for s in sales)
    transaction_count = len(sales)
    average_ticket = (total_sales / transaction_count) if transaction_count > 0 else 0.0

    # Total de productos vendidos hoy
    items_count = db.session.query(func.sum(SaleItem.quantity))\
        .join(Sale, SaleItem.sale_id == Sale.id)\
        .filter(
            Sale.tenant_id == tenant_id,
            Sale.created_at >= start_of_day,
            Sale.created_at <= end_of_day
        ).scalar() or 0

    return {
        'date': now.strftime('%Y-%m-%d'),
        'total_sales': round(total_sales, 2),
        'transaction_count': transaction_count,
        'average_ticket': round(average_ticket, 2),
        'items_sold': int(items_count)
    }

def get_monthly_summary(tenant_id: str, year: int = None, month: int = None) -> dict:
    """Calcula el resumen de ventas del mes en curso y desglose diario."""
    now = datetime.now(timezone.utc)
    target_year = year or now.year
    target_month = month or now.month

    sales = Sale.query.filter(
        Sale.tenant_id == tenant_id,
        extract('year', Sale.created_at) == target_year,
        extract('month', Sale.created_at) == target_month
    ).all()

    total_sales = sum(float(s.total) for s in sales)
    transaction_count = len(sales)

    # Desglose por días del mes
    daily_totals = {}
    for s in sales:
        day_str = s.created_at.strftime('%Y-%m-%d')
        daily_totals[day_str] = daily_totals.get(day_str, 0.0) + float(s.total)

    daily_chart = [{'date': k, 'total': round(v, 2)} for k, v in sorted(daily_totals.items())]

    # Comparativa con mes anterior
    prev_month = 12 if target_month == 1 else target_month - 1
    prev_year = target_year - 1 if target_month == 1 else target_year
    prev_sales_total = db.session.query(func.sum(Sale.total)).filter(
        Sale.tenant_id == tenant_id,
        extract('year', Sale.created_at) == prev_year,
        extract('month', Sale.created_at) == prev_month
    ).scalar() or 0.0

    growth_pct = 0.0
    if prev_sales_total > 0:
        growth_pct = ((total_sales - float(prev_sales_total)) / float(prev_sales_total)) * 100.0

    return {
        'year': target_year,
        'month': target_month,
        'total_sales': round(total_sales, 2),
        'transaction_count': transaction_count,
        'previous_month_total': round(float(prev_sales_total), 2),
        'growth_percentage': round(growth_pct, 1),
        'daily_chart': daily_chart
    }

def get_annual_summary(tenant_id: str, year: int = None) -> dict:
    """Calcula el resumen financiero anual mes por mes."""
    now = datetime.now(timezone.utc)
    target_year = year or now.year

    month_names = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    monthly_data = []
    total_annual = 0.0

    for m in range(1, 13):
        m_total = db.session.query(func.sum(Sale.total)).filter(
            Sale.tenant_id == tenant_id,
            extract('year', Sale.created_at) == target_year,
            extract('month', Sale.created_at) == m
        ).scalar() or 0.0
        
        m_val = round(float(m_total), 2)
        total_annual += m_val
        monthly_data.append({
            'month_number': m,
            'month_name': month_names[m - 1],
            'total': m_val
        })

    return {
        'year': target_year,
        'total_annual': round(total_annual, 2),
        'months': monthly_data
    }

def get_top_products(tenant_id: str, limit: int = 5) -> list[dict]:
    """Obtiene los N productos más vendidos ordenados por cantidad e ingresos."""
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
    ).limit(limit).all()

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
    # Ingresos totales
    total_revenue = db.session.query(func.sum(Sale.total)).filter(
        Sale.tenant_id == tenant_id
    ).scalar() or 0.0
    total_revenue = float(total_revenue)

    # Costos totales basados en cantidad * unit_cost de cada venta
    total_cost = db.session.query(
        func.sum(SaleItem.quantity * SaleItem.unit_cost)
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
