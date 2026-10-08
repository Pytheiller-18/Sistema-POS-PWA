from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g
from app.models.sale import Sale
from app.models.sync_log import SyncAuditLog
from app.services.sale_service import process_sale
from app.middlewares.auth import tenant_required

sync_bp = Blueprint('sync', __name__, url_prefix='/api/v1/sync')

# ============================================================================
# DOBLE VERIFICACIÓN DE SEGURIDAD - SINCRONIZACIÓN OFFLINE-FIRST:
# 1. Procesa lotes manteniendo la integridad por cada registro individual.
# 2. Si un registro ya existía (mismo client_sync_id y tenant_id), se marca
#    como 'already_synced' sin duplicar deducciones de inventario ni contabilidad.
# 3. Todo fallo individual se aísla sin cancelar las ventas válidas del lote.
# ============================================================================

@sync_bp.route('/sales-batch', methods=['POST'])
@tenant_required()
def sync_sales_batch():
    """
    Recibe un lote de ventas registradas offline en IndexedDB y las sincroniza en la nube.
    Garantiza idempotencia absoluta por `client_sync_id`.
    """
    data = request.get_json() or {}
    sales_batch = data.get('sales', [])
    device_id = data.get('device_id', 'PWA-CLIENT')

    if not sales_batch or not isinstance(sales_batch, list):
        return jsonify({
            'success': False,
            'error': 'El lote debe contener un arreglo de ventas no vacío'
        }), 400

    results = {
        'synced_count': 0,
        'already_synced_count': 0,
        'failed_count': 0,
        'synced_ids': [],
        'already_synced_ids': [],
        'failed': []
    }

    for item in sales_batch:
        client_sync_id = item.get('client_sync_id')
        if not client_sync_id:
            results['failed_count'] += 1
            results['failed'].append({
                'client_sync_id': None,
                'error': 'Falta identificador único client_sync_id'
            })
            continue

        item['device_id'] = device_id
        res, status_code = process_sale(
            tenant_id=g.tenant_id,
            user_id=g.user_id,
            data=item,
            sync_status='SYNCED_OFFLINE'
        )

        if status_code in [200, 201]:
            if res.get('already_synced'):
                results['already_synced_count'] += 1
                results['already_synced_ids'].append(client_sync_id)
            else:
                results['synced_count'] += 1
                results['synced_ids'].append(client_sync_id)
        else:
            results['failed_count'] += 1
            results['failed'].append({
                'client_sync_id': client_sync_id,
                'error': res.get('error', 'Error desconocido al sincronizar')
            })

    return jsonify({
        'success': True,
        'message': f'Lote procesado: {results["synced_count"]} nuevas, {results["already_synced_count"]} ya existían, {results["failed_count"]} fallaron.',
        'summary': results
    }), 200

@sync_bp.route('/status', methods=['GET'])
@tenant_required()
def get_sync_status():
    """Retorna estado y estadísticas de sincronización para la terminal cliente."""
    total_sales = Sale.query.filter_by(tenant_id=g.tenant_id).count()
    last_audit = SyncAuditLog.query.filter_by(tenant_id=g.tenant_id).order_by(SyncAuditLog.synced_at.desc()).first()

    return jsonify({
        'success': True,
        'server_time': datetime.now(timezone.utc).isoformat(),
        'tenant_id': g.tenant_id,
        'total_sales_recorded': total_sales,
        'last_sync_log': last_audit.to_dict() if last_audit else None
    }), 200
