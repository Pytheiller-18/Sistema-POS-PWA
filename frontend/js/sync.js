/**
 * SISTEMA POS PWA - Orquestador de Sincronización Offline-First
 * Gestiona el paso transparente entre modo local (IndexedDB) y la nube (API REST).
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
      if (this.effectiveOnlineStatus() && !this.isSyncing && window.apiClient.isAuthenticated()) {
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
   */
  async syncCatalogToLocal() {
    if (!this.effectiveOnlineStatus() || !window.apiClient.isAuthenticated()) {
      return false;
    }

    try {
      const prodRes = await window.apiClient.getProducts();
      if (prodRes.success && prodRes.products) {
        await window.posDB.saveProducts(prodRes.products);
      }

      const catRes = await window.apiClient.getCategories();
      if (catRes.success && catRes.categories) {
        await window.posDB.saveCategories(catRes.categories);
      }

      await window.posDB.setConfig('last_catalog_sync', new Date().toISOString());
      console.log('✅ Catálogo sincronizado en IndexedDB local.');
      return true;
    } catch (err) {
      console.warn('No fue posible sincronizar catálogo desde nube:', err.message);
      return false;
    }
  }

  /**
   * Sube todas las ventas guardadas localmente hacia la nube por lotes.
   */
  async triggerSync() {
    if (this.isSyncing || !this.effectiveOnlineStatus() || !window.apiClient.isAuthenticated()) {
      return { success: false, reason: 'No disponible para sincronizar' };
    }

    this.isSyncing = true;
    window.dispatchEvent(new CustomEvent('sync-start'));

    try {
      const pendingSales = await window.posDB.getPendingSales();
      if (!pendingSales || pendingSales.length === 0) {
        this.isSyncing = false;
        window.dispatchEvent(new CustomEvent('sync-complete', { detail: { synced: 0, pending: 0 } }));
        return { success: true, count: 0 };
      }

      console.log(`📤 Sincronizando lote de ${pendingSales.length} ventas offline...`);

      // Enviar lote al backend con idempotencia
      const response = await window.apiClient.syncBatch(pendingSales);

      if (response.success && response.summary) {
        const { synced_ids, already_synced_ids } = response.summary;
        const allProcessed = [...(synced_ids || []), ...(already_synced_ids || [])];

        for (const syncId of allProcessed) {
          await window.posDB.markSaleAsSynced(syncId);
        }

        // Refrescar catálogo local para asegurar stock actualizado
        await this.syncCatalogToLocal();

        const remaining = await window.posDB.getPendingSales();
        window.dispatchEvent(new CustomEvent('sync-complete', {
          detail: {
            synced: allProcessed.length,
            pending: remaining.length,
            summary: response.summary
          }
        }));

        this.isSyncing = false;
        return { success: true, count: allProcessed.length };
      }
    } catch (error) {
      console.error('Error durante sincronización en segundo plano:', error);
      window.dispatchEvent(new CustomEvent('sync-error', { detail: { error: error.message } }));
    } finally {
      this.isSyncing = false;
    }
  }
}

window.syncManager = new SyncManager();
