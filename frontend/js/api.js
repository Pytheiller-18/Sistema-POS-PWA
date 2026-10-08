/**
 * SISTEMA POS PWA - Cliente de API HTTP REST
 * Gestiona peticiones autenticadas, manejo de tokens JWT e intercepción de errores.
 */

class PosApiClient {
  constructor() {
    this.baseUrl = window.API_BASE_URL || 'http://localhost:5000/api/v1';
    this.token = localStorage.getItem('pos_pwa_token') || null;
    this.tenant = JSON.parse(localStorage.getItem('pos_pwa_tenant') || 'null');
    this.user = JSON.parse(localStorage.getItem('pos_pwa_user') || 'null');
  }

  setSession(token, user, tenant) {
    this.token = token;
    this.user = user;
    this.tenant = tenant;
    localStorage.setItem('pos_pwa_token', token);
    localStorage.setItem('pos_pwa_user', JSON.stringify(user));
    localStorage.setItem('pos_pwa_tenant', JSON.stringify(tenant));
  }

  clearSession() {
    this.token = null;
    this.user = null;
    this.tenant = null;
    localStorage.removeItem('pos_pwa_token');
    localStorage.removeItem('pos_pwa_user');
    localStorage.removeItem('pos_pwa_tenant');
  }

  isAuthenticated() {
    return !!this.token;
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers
      });

      if (response.status === 401) {
        console.warn('Sesión no autorizada o expirada');
        // Si no estamos intentando iniciar sesión, limpiar
        if (!endpoint.includes('/auth/login')) {
          this.clearSession();
          window.dispatchEvent(new CustomEvent('auth-expired'));
        }
      }

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.error || `Error HTTP ${response.status}`);
      }

      return data;
    } catch (err) {
      // Si la red falla completamente (Failed to fetch)
      if (err.name === 'TypeError' && err.message.includes('fetch')) {
        err.isNetworkError = true;
      }
      throw err;
    }
  }

  // --- Auth ---
  async login(email, password) {
    const data = await this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
    if (data.success) {
      this.setSession(data.token, data.user, data.tenant);
    }
    return data;
  }

  async registerTenant(payload) {
    const data = await this.request('/auth/register-tenant', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    if (data.success) {
      this.setSession(data.token, data.user, data.tenant);
    }
    return data;
  }

  async getMe() {
    return this.request('/auth/me');
  }

  // --- Productos & Categorías ---
  async getProducts(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/products${query ? '?' + query : ''}`);
  }

  async createProduct(productData) {
    return this.request('/products', {
      method: 'POST',
      body: JSON.stringify(productData)
    });
  }

  async updateProduct(id, productData) {
    return this.request(`/products/${id}`, {
      method: 'PUT',
      body: JSON.stringify(productData)
    });
  }

  async deleteProduct(id) {
    return this.request(`/products/${id}`, {
      method: 'DELETE'
    });
  }

  async getCategories() {
    return this.request('/products/categories');
  }

  async createCategory(categoryData) {
    return this.request('/products/categories', {
      method: 'POST',
      body: JSON.stringify(categoryData)
    });
  }

  // --- Ventas ---
  async postSale(saleData) {
    return this.request('/sales', {
      method: 'POST',
      body: JSON.stringify(saleData)
    });
  }

  async getSales(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/sales${query ? '?' + query : ''}`);
  }

  async getSaleById(id) {
    return this.request(`/sales/${id}`);
  }

  // --- Sincronización Lote Offline ---
  async syncBatch(salesBatch, deviceId = 'POS-CLIENT-PWA') {
    return this.request('/sync/sales-batch', {
      method: 'POST',
      body: JSON.stringify({
        device_id: deviceId,
        sales: salesBatch
      })
    });
  }

  async getSyncStatus() {
    return this.request('/sync/status');
  }

  // --- Analíticas & Reportes ---
  async getReportsToday() {
    return this.request('/reports/today');
  }

  async getReportsMonthly(year, month) {
    const query = new URLSearchParams();
    if (year) query.append('year', year);
    if (month) query.append('month', month);
    return this.request(`/reports/monthly?${query.toString()}`);
  }

  async getReportsAnnual(year) {
    const query = year ? `?year=${year}` : '';
    return this.request(`/reports/annual${query}`);
  }

  async getReportsTopProducts(limit = 5) {
    return this.request(`/reports/top-products?limit=${limit}`);
  }

  async getReportsProfit() {
    return this.request('/reports/profit');
  }
}

window.apiClient = new PosApiClient();
