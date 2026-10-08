/**
 * SISTEMA POS PWA - Capa de Persistencia Local (IndexedDB)
 * Proporciona almacenamiento transaccional offline-first en el navegador.
 */

const DB_NAME = 'SistemaPosDB';
const DB_VERSION = 1;

class PosDatabase {
  constructor() {
    this.db = null;
  }

  async init() {
    if (this.db) return this.db;

    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onupgradeneeded = (event) => {
        const db = event.target.result;

        // 1. Catálogo local de Productos
        if (!db.objectStoreNames.contains('products')) {
          const productStore = db.createObjectStore('products', { keyPath: 'id' });
          productStore.createIndex('barcode', 'barcode', { unique: false });
          productStore.createIndex('category_id', 'category_id', { unique: false });
          productStore.createIndex('name', 'name', { unique: false });
        }

        // 2. Categorías
        if (!db.objectStoreNames.contains('categories')) {
          db.createObjectStore('categories', { keyPath: 'id' });
        }

        // 3. Cola de Ventas Pendientes de Sincronización
        if (!db.objectStoreNames.contains('pending_sales')) {
          const pendingStore = db.createObjectStore('pending_sales', { keyPath: 'client_sync_id' });
          pendingStore.createIndex('status', 'status', { unique: false });
          pendingStore.createIndex('created_at', 'created_at', { unique: false });
        }

        // 4. Histórico Local de Ventas
        if (!db.objectStoreNames.contains('sales_history')) {
          const historyStore = db.createObjectStore('sales_history', { keyPath: 'client_sync_id' });
          historyStore.createIndex('invoice_number', 'invoice_number', { unique: false });
          historyStore.createIndex('created_at', 'created_at', { unique: false });
        }

        // 5. Ajustes y Configuración Local
        if (!db.objectStoreNames.contains('config')) {
          db.createObjectStore('config', { keyPath: 'key' });
        }
      };

      request.onsuccess = (event) => {
        this.db = event.target.result;
        resolve(this.db);
      };

      request.onerror = (event) => {
        console.error('Error al abrir IndexedDB:', event.target.error);
        reject(event.target.error);
      };
    });
  }

  // --- Manejo de Productos ---
  async saveProducts(products) {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('products', 'readwrite');
      const store = tx.objectStore('products');
      products.forEach((p) => store.put(p));
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => reject(tx.error);
    });
  }

  async getAllProducts() {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('products', 'readonly');
      const store = tx.objectStore('products');
      const request = store.getAll();
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    });
  }

  async updateProductStockLocal(productId, quantitySold) {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('products', 'readwrite');
      const store = tx.objectStore('products');
      const req = store.get(productId);
      req.onsuccess = () => {
        const product = req.result;
        if (product) {
          product.stock = (product.stock || 0) - quantitySold;
          store.put(product);
        }
        resolve(product);
      };
      req.onerror = () => reject(req.error);
    });
  }

  // --- Categorías ---
  async saveCategories(categories) {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('categories', 'readwrite');
      const store = tx.objectStore('categories');
      categories.forEach((c) => store.put(c));
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => reject(tx.error);
    });
  }

  async getAllCategories() {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('categories', 'readonly');
      const store = tx.objectStore('categories');
      const req = store.getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  }

  // --- Cola de Ventas Offline (Pending Sales) ---
  async queuePendingSale(sale) {
    await this.init();
    sale.status = 'PENDING';
    sale.queued_at = new Date().toISOString();

    return new Promise((resolve, reject) => {
      const tx = this.db.transaction(['pending_sales', 'sales_history'], 'readwrite');
      tx.objectStore('pending_sales').put(sale);
      tx.objectStore('sales_history').put(sale);
      tx.oncomplete = () => resolve(sale);
      tx.onerror = () => reject(tx.error);
    });
  }

  async getPendingSales() {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('pending_sales', 'readonly');
      const store = tx.objectStore('pending_sales');
      const req = store.getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  }

  async markSaleAsSynced(clientSyncId) {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction(['pending_sales', 'sales_history'], 'readwrite');
      // Borrar de pendientes
      tx.objectStore('pending_sales').delete(clientSyncId);

      // Actualizar en histórico
      const historyStore = tx.objectStore('sales_history');
      const getReq = historyStore.get(clientSyncId);
      getReq.onsuccess = () => {
        const item = getReq.result;
        if (item) {
          item.status = 'SYNCED';
          item.synced_at = new Date().toISOString();
          historyStore.put(item);
        }
      };

      tx.oncomplete = () => resolve(true);
      tx.onerror = () => reject(tx.error);
    });
  }

  async getAllSalesHistory() {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('sales_history', 'readonly');
      const store = tx.objectStore('sales_history');
      const req = store.getAll();
      req.onsuccess = () => {
        const results = req.result || [];
        // Ordenar por fecha descendente
        results.sort((a, b) => new Date(b.created_at || b.queued_at) - new Date(a.created_at || a.queued_at));
        resolve(results);
      };
      req.onerror = () => reject(req.error);
    });
  }

  // --- Configuración y Metadatos ---
  async setConfig(key, value) {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('config', 'readwrite');
      tx.objectStore('config').put({ key, value });
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => reject(tx.error);
    });
  }

  async getConfig(key) {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('config', 'readonly');
      const req = tx.objectStore('config').get(key);
      req.onsuccess = () => resolve(req.result ? req.result.value : null);
      req.onerror = () => reject(req.error);
    });
  }
}

// Instancia global
window.posDB = new PosDatabase();
