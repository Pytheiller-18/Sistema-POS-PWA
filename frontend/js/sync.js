/**
 * Positiva-POS - Orquestador de Sincronización Offline-First
 * Gestiona el paso transparente entre modo local (IndexedDB) y la nube (API REST).
 * Soporta sincronización delta por ?since= y lotes fragmentados (O3, O4, C3).
 */

class SyncManager {
  constructor() {
    this.isOnline = navigator.onLine;
    this.isSimulatedOffline = false; // Permite probar offline directamente
    this.isSyncing = false;
    this.syncInterval = null;

    this.initListeners();
  }

  initListeners() {
    window.addEventListener('online', () => {
      this.updateOnlineStatus();
      if (!this.isSimulatedOffline) {
        this.triggerSync();
      }
    });

    window.addEventListener('offline', () => {
      this.updateOnlineStatus();
    });

    // Monitoreo periódico cada 30 segundos
    this.syncInterval = setInterval(() => {
      if (this.effectiveOnlineStatus() && !this.isSyncing && window.apiClient && window.apiClient.isAuthenticated()) {
        this.triggerSync();
      }
    }, 30000);
  }

  setSimulatedOffline(value) {
    this.isSimulatedOffline = value;
    this.updateOnlineStatus();
    if (!value && navigator.onLine) {
      this.triggerSync();
    }
  }

  effectiveOnlineStatus() {
    if (this.isSimulatedOffline) return false;
    return navigator.onLine;
  }

  updateOnlineStatus() {
    this.isOnline = this.effectiveOnlineStatus();
    window.dispatchEvent(new CustomEvent('network-status-changed', {
      detail: { online: this.isOnline, simulated: this.isSimulatedOffline }
    }));
  }

  /**
   * Sincroniza el catálogo de productos de la nube a IndexedDB local.
   * (O3) Utiliza ?since= con la marca de tiempo provista por el servidor para descargar solo cambios.
   */
  async syncCatalogToLocal(forceFull = false) {
    if (!this.effectiveOnlineStatus() || !window.apiClient || !window.apiClient.isAuthenticated()) {
      return false;
    }

    try {
      const params = {};
      if (!forceFull) {
        const lastServerTime = await window.posDB.getConfig('last_catalog_server_time');
        if (lastServerTime) {
          params.since = lastServerTime;
        }
      }

      const prodRes = await window.apiClient.getProducts(params);
      if (prodRes && prodRes.success && Array.isArray(prodRes.products)) {
        await window.posDB.saveProducts(prodRes.products);
        if (prodRes.server_time) {
          await window.posDB.setConfig('last_catalog_server_time', prodRes.server_time);
        }
      }

      const catRes = await window.apiClient.getCategories();
      if (catRes && catRes.success && Array.isArray(catRes.categories)) {
        await window.posDB.saveCategories(catRes.categories);
      }

      await window.posDB.setConfig('last_catalog_sync', new Date().toISOString());
      return true;
    } catch (err) {
      console.warn('No fue posible sincronizar catálogo desde nube:', err.message);
      return false;
    }
  }

  /**
   * Sube todas las ventas guardadas localmente hacia la nube por lotes (O4).
   * Aísla las ventas por el tenant actualmente autenticado (C3).
   */
  async triggerSync() {
    if (this.isSyncing || !this.effectiveOnlineStatus() || !window.apiClient || !window.apiClient.isAuthenticated()) {
      return { success: false, reason: 'No disponible para sincronizar' };
    }

    const currentTenant = window.apiClient.tenant;
    const currentTenantId = currentTenant ? currentTenant.id : null;

    this.isSyncing = true;
    window.dispatchEvent(new CustomEvent('sync-start'));

    try {
      const allPending = await window.posDB.getPendingSales();
      if (!allPending || allPending.length === 0) {
        this.isSyncing = false;
        window.dispatchEvent(new CustomEvent('sync-complete', { detail: { synced: 0, pending: 0 } }));
        return { success: true, count: 0 };
      }

      // (C3) Filtrar exclusivamente las ventas del tenant autenticado
      const tenantSales = allPending.filter((s) => !s.tenant_id || s.tenant_id === currentTenantId);

      if (tenantSales.length === 0) {
        this.isSyncing = false;
        window.dispatchEvent(new CustomEvent('sync-complete', { detail: { synced: 0, pending: allPending.length } }));
        return { success: true, count: 0 };
      }

      console.log(`📤 Sincronizando ${tenantSales.length} ventas offline del tenant actual...`);

      // (O4) Enviar en fragmentos máximos de 50 para evitar sobrecarga
      const CHUNK_SIZE = 50;
      let totalSyncedCount = 0;
      const combinedProcessed = [];

      for (let i = 0; i < tenantSales.length; i += CHUNK_SIZE) {
        const chunk = tenantSales.slice(i, i + CHUNK_SIZE);
        const response = await window.apiClient.syncBatch(chunk);

        if (response && response.success && response.summary) {
          const { synced_ids, already_synced_ids } = response.summary;
          const chunkProcessed = [...(synced_ids || []), ...(already_synced_ids || [])];

          for (const syncId of chunkProcessed) {
            await window.posDB.markSaleAsSynced(syncId);
            combinedProcessed.push(syncId);
          }
          totalSyncedCount += chunkProcessed.length;
        }
      }

      // Refrescar catálogo local para asegurar stock actualizado del servidor
      await this.syncCatalogToLocal();

      const remaining = await window.posDB.getPendingSales();
      window.dispatchEvent(new CustomEvent('sync-complete', {
        detail: {
          synced: totalSyncedCount,
          pending: remaining.length,
          processed_ids: combinedProcessed
        }
      }));

      this.isSyncing = false;
      return { success: true, count: totalSyncedCount };
    } catch (error) {
      console.error('Error durante sincronización en segundo plano:', error);
      window.dispatchEvent(new CustomEvent('sync-error', { detail: { error: error.message } }));
      return { success: false, error: error.message };
    } finally {
      this.isSyncing = false;
    }
  }
}

window.syncManager = new SyncManager();
