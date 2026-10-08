/**
 * SISTEMA POS PWA - Coordinador Principal de Interfaz de Usuario y Lógica de Negocio
 */

class PosApp {
  constructor() {
    this.cart = [];
    this.products = [];
    this.categories = [];
    this.selectedCategory = 'ALL';
    this.searchQuery = '';
    this.activeDiscount = 0;
    this.currentSaleCompleted = null;

    this.init();
  }

  async init() {
    this.registerServiceWorker();
    this.bindEvents();
    this.checkSession();
    await this.loadLocalCatalog();
    this.updateNetworkBadge();
    this.refreshPendingSyncCount();

    // Si ya hay sesión activa, sincronizar datos con backend
    if (window.apiClient.isAuthenticated()) {
      window.syncManager.syncCatalogToLocal().then(() => this.loadLocalCatalog());
    }
  }

  // --- Service Worker ---
  registerServiceWorker() {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('./sw.js')
        .then((reg) => console.log('✅ Service Worker registrado con éxito:', reg.scope))
        .catch((err) => console.warn('Fallo registro de SW:', err));
    }
  }

  // --- Sesión & Autenticación ---
  checkSession() {
    if (window.apiClient.isAuthenticated()) {
      const user = window.apiClient.user;
      const tenant = window.apiClient.tenant;
      document.getElementById('header-user-name').textContent = user ? user.full_name : 'Usuario';
      document.getElementById('header-tenant-name').textContent = tenant ? tenant.business_name : 'Mi Tienda POS';
      document.getElementById('auth-modal').classList.remove('active');
    } else {
      document.getElementById('auth-modal').classList.add('active');
    }
  }

  // --- Carga Local-First del Catálogo ---
  async loadLocalCatalog() {
    try {
      this.products = await window.posDB.getAllProducts();
      this.categories = await window.posDB.getAllCategories();

      this.renderCategoriesBar();
      this.renderProductsGrid();
      this.renderProductsTable();
    } catch (err) {
      console.error('Error al cargar catálogo de IndexedDB:', err);
    }
  }

  // --- Renderizado de Catálogo en Caja (POS) ---
  renderCategoriesBar() {
    const container = document.getElementById('categories-bar');
    if (!container) return;

    let html = `<button class="category-chip ${this.selectedCategory === 'ALL' ? 'active' : ''}" data-cat="ALL">Todos</button>`;
    this.categories.forEach((c) => {
      const isActive = this.selectedCategory === c.id ? 'active' : '';
      html += `<button class="category-chip ${isActive}" data-cat="${c.id}">${c.name}</button>`;
    });

    container.innerHTML = html;

    container.querySelectorAll('.category-chip').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        this.selectedCategory = e.currentTarget.dataset.cat;
        this.renderCategoriesBar();
        this.renderProductsGrid();
      });
    });
  }

  renderProductsGrid() {
    const container = document.getElementById('products-grid');
    if (!container) return;

    const filtered = this.products.filter((p) => {
      if (!p.is_active) return false;
      const matchesCat = this.selectedCategory === 'ALL' || p.category_id === this.selectedCategory;
      const q = this.searchQuery.toLowerCase();
      const matchesSearch = !q || p.name.toLowerCase().includes(q) || (p.barcode && p.barcode.toLowerCase().includes(q));
      return matchesCat && matchesSearch;
    });

    if (filtered.length === 0) {
      container.innerHTML = `
        <div style="grid-column: 1/-1; text-align: center; padding: 3rem 1rem; color: var(--text-secondary);">
          <p style="font-size: 1.1rem; margin-bottom: 0.5rem;">🔍 No se encontraron productos</p>
          <p style="font-size: 0.85rem;">Prueba con otro término de búsqueda o agrega productos desde el inventario.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = filtered.map((p) => {
      let stockClass = 'stock-ok';
      let stockLabel = `${p.stock} en stock`;
      if (p.stock <= 0) {
        stockClass = 'stock-empty';
        stockLabel = 'Sin stock';
      } else if (p.stock <= (p.min_stock || 5)) {
        stockClass = 'stock-low';
        stockLabel = `Bajo: ${p.stock}`;
      }

      return `
        <div class="product-card" data-id="${p.id}">
          <div class="product-header">
            <span class="product-category-tag">${p.category_name || 'General'}</span>
            <span class="product-stock-tag ${stockClass}">${stockLabel}</span>
          </div>
          <div class="product-name" title="${p.name}">${p.name}</div>
          <div class="product-barcode">${p.barcode || 'SIN-CÓDIGO'}</div>
          <div class="product-price-row">
            <span class="product-price">$${Number(p.sale_price).toLocaleString()}</span>
            <button class="product-add-btn" title="Agregar a la orden">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
            </button>
          </div>
        </div>
      `;
    }).join('');

    container.querySelectorAll('.product-card').forEach((card) => {
      card.addEventListener('click', () => {
        const pId = card.dataset.id;
        const prod = this.products.find((p) => p.id === pId);
        if (prod) this.addToCart(prod);
      });
    });
  }

  // --- Manejo del Carrito de Compras ---
  addToCart(product) {
    const existing = this.cart.find((item) => item.product_id === product.id);
    if (existing) {
      existing.quantity += 1;
    } else {
      this.cart.push({
        product_id: product.id,
        name: product.name,
        price: Number(product.sale_price),
        cost: Number(product.cost_price || 0),
        quantity: 1
      });
    }
    this.renderCart();
  }

  changeCartItemQty(productId, delta) {
    const item = this.cart.find((i) => i.product_id === productId);
    if (!item) return;

    item.quantity += delta;
    if (item.quantity <= 0) {
      this.cart = this.cart.filter((i) => i.product_id !== productId);
    }
    this.renderCart();
  }

  removeFromCart(productId) {
    this.cart = this.cart.filter((i) => i.product_id !== productId);
    this.renderCart();
  }

  clearCart() {
    this.cart = [];
    this.activeDiscount = 0;
    this.renderCart();
  }

  calculateCartTotals() {
    const subtotal = this.cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
    const tax = 0; // Configurable
    const total = Math.max(0, subtotal + tax - this.activeDiscount);
    const totalItems = this.cart.reduce((sum, item) => sum + item.quantity, 0);
    return { subtotal, tax, discount: this.activeDiscount, total, totalItems };
  }

  renderCart() {
    const itemsList = document.getElementById('cart-items-list');
    const { subtotal, tax, discount, total, totalItems } = this.calculateCartTotals();

    // Actualizar badges
    const badgeElements = document.querySelectorAll('.cart-count-badge');
    badgeElements.forEach((b) => (b.textContent = totalItems));

    document.getElementById('cart-subtotal').textContent = `$${subtotal.toLocaleString()}`;
    document.getElementById('cart-total').textContent = `$${total.toLocaleString()}`;
    document.getElementById('mobile-cart-total-badge').textContent = `$${total.toLocaleString()}`;

    if (this.cart.length === 0) {
      itemsList.innerHTML = `
        <div style="text-align: center; color: var(--text-muted); margin: auto; padding: 2rem 0;">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 0.5rem; opacity: 0.5;">
            <circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle>
            <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path>
          </svg>
          <p>El carrito está vacío</p>
          <p style="font-size: 0.75rem;">Haz clic en un producto o escanea su código</p>
        </div>
      `;
      document.getElementById('btn-checkout').disabled = true;
      return;
    }

    document.getElementById('btn-checkout').disabled = false;

    itemsList.innerHTML = this.cart.map((item) => `
      <div class="cart-item">
        <div class="cart-item-info">
          <div class="cart-item-title">${item.name}</div>
          <div class="cart-item-price">$${item.price.toLocaleString()} c/u</div>
        </div>
        <div class="cart-qty-control">
          <button class="cart-qty-btn" onclick="window.posApp.changeCartItemQty('${item.product_id}', -1)">-</button>
          <span class="cart-qty-val">${item.quantity}</span>
          <button class="cart-qty-btn" onclick="window.posApp.changeCartItemQty('${item.product_id}', 1)">+</button>
        </div>
        <div class="cart-item-total">$${(item.price * item.quantity).toLocaleString()}</div>
        <button class="cart-item-remove" onclick="window.posApp.removeFromCart('${item.product_id}')">✕</button>
      </div>
    `).join('');
  }

  // --- Proceso de Cobro (Checkout Modal) ---
  openCheckoutModal() {
    if (this.cart.length === 0) return;

    const { total } = this.calculateCartTotals();
    document.getElementById('checkout-total-display').textContent = `$${total.toLocaleString()}`;
    const paidInput = document.getElementById('checkout-paid-amount');
    paidInput.value = total;
    this.calculateChange();

    document.getElementById('checkout-modal').classList.add('active');
  }

  calculateChange() {
    const { total } = this.calculateCartTotals();
    const paid = Number(document.getElementById('checkout-paid-amount').value) || 0;
    const change = Math.max(0, paid - total);
    document.getElementById('checkout-change-display').textContent = `$${change.toLocaleString()}`;
  }

  setQuickCash(amount) {
    const { total } = this.calculateCartTotals();
    const input = document.getElementById('checkout-paid-amount');
    input.value = amount === 'EXACT' ? total : amount;
    this.calculateChange();
  }

  async finalizeSale() {
    const { subtotal, tax, discount, total } = this.calculateCartTotals();
    const paid = Number(document.getElementById('checkout-paid-amount').value) || total;
    const change = Math.max(0, paid - total);
    const paymentMethod = document.getElementById('checkout-payment-method').value;

    const clientSyncId = 'pos-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    const invoiceNumber = 'POS-' + new Date().getFullYear() + '-' + Math.floor(100000 + Math.random() * 900000);

    const salePayload = {
      client_sync_id: clientSyncId,
      invoice_number: invoiceNumber,
      subtotal,
      tax,
      discount,
      total,
      payment_method: paymentMethod,
      amount_paid: paid,
      change_due: change,
      created_at: new Date().toISOString(),
      items: this.cart.map((item) => ({
        product_id: item.product_id,
        product_name: item.name,
        quantity: item.quantity,
        unit_price: item.price,
        unit_cost: item.cost,
        subtotal: item.price * item.quantity,
        total: item.price * item.quantity
      }))
    };

    // 1. Descontar stock localmente en IndexedDB de inmediato
    for (const item of this.cart) {
      await window.posDB.updateProductStockLocal(item.product_id, item.quantity);
    }

    // 2. Guardar en cola IndexedDB (Offline-First garantizado)
    await window.posDB.queuePendingSale(salePayload);

    // 3. Si hay conexión efectiva, sincronizar inmediatamente
    let isSyncedNow = false;
    if (window.syncManager.effectiveOnlineStatus() && window.apiClient.isAuthenticated()) {
      try {
        const res = await window.apiClient.postSale(salePayload);
        if (res.success) {
          await window.posDB.markSaleAsSynced(clientSyncId);
          isSyncedNow = true;
        }
      } catch (err) {
        console.warn('Venta guardada localmente, sincronización pendiente:', err.message);
      }
    }

    // Preparar ticket impreso
    this.currentSaleCompleted = {
      ...salePayload,
      isSynced: isSyncedNow,
      tenant: window.apiClient.tenant || { business_name: 'Mi Tienda POS', tax_id: 'NIT Demo' },
      user: window.apiClient.user || { full_name: 'Cajero' }
    };

    // Cerrar modal de cobro y abrir ticket
    document.getElementById('checkout-modal').classList.remove('active');
    this.showReceiptModal();

    // Limpiar carrito y refrescar UI
    this.clearCart();
    await this.loadLocalCatalog();
    this.refreshPendingSyncCount();

    if (window.innerWidth < 1024) {
      document.getElementById('cart-pane').classList.remove('mobile-open');
    }
  }

  showReceiptModal() {
    const sale = this.currentSaleCompleted;
    if (!sale) return;

    const receiptContent = document.getElementById('receipt-ticket-content');
    receiptContent.innerHTML = `
      <div class="ticket-header">
        <div class="ticket-store-name">${sale.tenant.business_name}</div>
        <div>${sale.tenant.tax_id || ''}</div>
        <div>Tel: ${sale.tenant.phone || ''}</div>
        <div style="margin-top: 6px;">Factura: <strong>${sale.invoice_number}</strong></div>
        <div>Fecha: ${new Date(sale.created_at).toLocaleString()}</div>
        <div>Atendido por: ${sale.user.full_name}</div>
        <div style="margin-top: 4px; font-weight: 700; color: ${sale.isSynced ? '#059669' : '#d97706'};">
          ${sale.isSynced ? '● SINCRONIZADO EN NUBE' : '▲ GUARDADO LOCAL (OFFLINE)'}
        </div>
      </div>

      <div class="ticket-divider"></div>

      <div style="margin-bottom: 6px;">
        ${sale.items.map((i) => `
          <div class="ticket-row">
            <span>${i.quantity}x ${i.product_name}</span>
            <span>$${i.total.toLocaleString()}</span>
          </div>
        `).join('')}
      </div>

      <div class="ticket-divider"></div>

      <div class="ticket-row">
        <span>Subtotal:</span>
        <span>$${sale.subtotal.toLocaleString()}</span>
      </div>
      ${sale.discount > 0 ? `
      <div class="ticket-row">
        <span>Descuento:</span>
        <span>-$${sale.discount.toLocaleString()}</span>
      </div>` : ''}
      <div class="ticket-row ticket-total">
        <span>TOTAL:</span>
        <span>$${sale.total.toLocaleString()}</span>
      </div>
      <div class="ticket-row">
        <span>Método:</span>
        <span>${sale.payment_method}</span>
      </div>
      <div class="ticket-row">
        <span>Pagó con:</span>
        <span>$${sale.amount_paid.toLocaleString()}</span>
      </div>
      <div class="ticket-row">
        <span>Cambio / Vueltas:</span>
        <span>$${sale.change_due.toLocaleString()}</span>
      </div>

      <div class="ticket-divider"></div>
      <div style="text-align: center; margin-top: 8px;">
        <p>¡Gracias por su compra!</p>
        <p style="font-size: 10px; color: #888;">ID: ${sale.client_sync_id}</p>
      </div>
    `;

    document.getElementById('receipt-modal').classList.add('active');
  }

  // --- Actualización de Badges y Red ---
  updateNetworkBadge() {
    const badge = document.getElementById('network-status-badge');
    const isOnline = window.syncManager.effectiveOnlineStatus();

    if (isOnline) {
      badge.className = 'status-pill online';
      badge.innerHTML = '<span class="pulse-dot"></span> Online';
    } else {
      badge.className = 'status-pill offline';
      badge.innerHTML = '<span class="pulse-dot"></span> Offline';
    }
  }

  async refreshPendingSyncCount() {
    const pending = await window.posDB.getPendingSales();
    const count = pending.length;
    const badge = document.getElementById('pending-sync-count');
    if (badge) {
      badge.textContent = `${count} pendientes`;
      badge.style.display = count > 0 ? 'inline-block' : 'none';
    }
  }

  // --- Cambio de Vistas ---
  switchView(viewName) {
    this.activeView = viewName;
    document.querySelectorAll('.view-section').forEach((s) => s.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach((t) => t.classList.remove('active'));

    const targetSection = document.getElementById(`view-${viewName}`);
    const targetTab = document.querySelector(`.nav-tab[data-view="${viewName}"]`);

    if (targetSection) targetSection.classList.add('active');
    if (targetTab) targetTab.classList.add('active');

    if (viewName === 'reports') this.loadReportsView();
    if (viewName === 'sync') this.loadSyncView();
    if (viewName === 'products') this.renderProductsTable();
  }

  // --- Vista de Inventario & Productos ---
  renderProductsTable() {
    const tbody = document.getElementById('products-table-body');
    if (!tbody) return;

    if (this.products.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 2rem;">No hay productos en inventario.</td></tr>';
      return;
    }

    tbody.innerHTML = this.products.map((p) => `
      <tr>
        <td style="font-family: var(--font-mono); font-size: 0.8rem;">${p.barcode || '-'}</td>
        <td style="font-weight: 700;">${p.name}</td>
        <td>${p.category_name || 'General'}</td>
        <td>$${Number(p.cost_price).toLocaleString()}</td>
        <td style="font-weight: 700; color: var(--success);">$${Number(p.sale_price).toLocaleString()}</td>
        <td style="font-weight: 800; color: ${p.stock <= p.min_stock ? 'var(--warning)' : 'var(--text-main)'};">${p.stock}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="window.posApp.openEditProductModal('${p.id}')">Editar</button>
        </td>
      </tr>
    `).join('');
  }

  openNewProductModal() {
    document.getElementById('product-form-id').value = '';
    document.getElementById('product-form-name').value = '';
    document.getElementById('product-form-barcode').value = '';
    document.getElementById('product-form-cost').value = '';
    document.getElementById('product-form-price').value = '';
    document.getElementById('product-form-stock').value = '';
    document.getElementById('product-form-min-stock').value = '5';
    document.getElementById('product-modal-title').textContent = 'Nuevo Producto';

    // Rellenar categorías
    const catSelect = document.getElementById('product-form-category');
    catSelect.innerHTML = '<option value="">Sin Categoría</option>' + 
      this.categories.map((c) => `<option value="${c.id}">${c.name}</option>`).join('');

    document.getElementById('product-modal').classList.add('active');
  }

  openEditProductModal(id) {
    const prod = this.products.find((p) => p.id === id);
    if (!prod) return;

    document.getElementById('product-form-id').value = prod.id;
    document.getElementById('product-form-name').value = prod.name;
    document.getElementById('product-form-barcode').value = prod.barcode || '';
    document.getElementById('product-form-cost').value = prod.cost_price;
    document.getElementById('product-form-price').value = prod.sale_price;
    document.getElementById('product-form-stock').value = prod.stock;
    document.getElementById('product-form-min-stock').value = prod.min_stock;
    document.getElementById('product-modal-title').textContent = 'Editar Producto';

    const catSelect = document.getElementById('product-form-category');
    catSelect.innerHTML = '<option value="">Sin Categoría</option>' + 
      this.categories.map((c) => `<option value="${c.id}" ${c.id === prod.category_id ? 'selected' : ''}>${c.name}</option>`).join('');

    document.getElementById('product-modal').classList.add('active');
  }

  async saveProductFromModal() {
    const id = document.getElementById('product-form-id').value;
    const payload = {
      name: document.getElementById('product-form-name').value.trim(),
      barcode: document.getElementById('product-form-barcode').value.trim() || null,
      category_id: document.getElementById('product-form-category').value || null,
      cost_price: Number(document.getElementById('product-form-cost').value) || 0,
      sale_price: Number(document.getElementById('product-form-price').value) || 0,
      stock: Number(document.getElementById('product-form-stock').value) || 0,
      min_stock: Number(document.getElementById('product-form-min-stock').value) || 5
    };

    if (!payload.name) {
      alert('El nombre del producto es obligatorio');
      return;
    }

    try {
      if (id) {
        // Actualizar
        if (window.syncManager.effectiveOnlineStatus()) {
          await window.apiClient.updateProduct(id, payload);
        }
        // Actualizar local
        const existing = this.products.find((p) => p.id === id);
        if (existing) Object.assign(existing, payload);
        await window.posDB.saveProducts([existing]);
      } else {
        // Crear
        if (window.syncManager.effectiveOnlineStatus()) {
          const res = await window.apiClient.createProduct(payload);
          if (res.product) await window.posDB.saveProducts([res.product]);
        } else {
          payload.id = 'local-prod-' + Date.now();
          payload.is_active = true;
          await window.posDB.saveProducts([payload]);
        }
      }

      document.getElementById('product-modal').classList.remove('active');
      await this.loadLocalCatalog();
    } catch (err) {
      alert('Error al guardar producto: ' + err.message);
    }
  }

  // --- Vista de Analíticas y Reportes ---
  async loadReportsView() {
    if (!window.syncManager.effectiveOnlineStatus() || !window.apiClient.isAuthenticated()) {
      document.getElementById('reports-offline-warning').style.display = 'block';
    } else {
      document.getElementById('reports-offline-warning').style.display = 'none';
      try {
        const [todayRes, monthRes, profitRes, topRes] = await Promise.all([
          window.apiClient.getReportsToday(),
          window.apiClient.getReportsMonthly(),
          window.apiClient.getReportsProfit(),
          window.apiClient.getReportsTopProducts(5)
        ]);

        if (todayRes.success) {
          document.getElementById('kpi-today-sales').textContent = `$${Number(todayRes.data.total_sales).toLocaleString()}`;
          document.getElementById('kpi-today-tickets').textContent = `${todayRes.data.transaction_count} tickets`;
        }

        if (monthRes.success) {
          document.getElementById('kpi-month-sales').textContent = `$${Number(monthRes.data.total_sales).toLocaleString()}`;
          document.getElementById('kpi-month-growth').textContent = `${monthRes.data.growth_percentage >= 0 ? '+' : ''}${monthRes.data.growth_percentage}% vs mes anterior`;
        }

        if (profitRes.success) {
          document.getElementById('kpi-total-profit').textContent = `$${Number(profitRes.data.gross_profit).toLocaleString()}`;
          document.getElementById('kpi-profit-margin').textContent = `Margen: ${profitRes.data.margin_percentage}%`;
        }

        if (topRes.success && topRes.data) {
          const topContainer = document.getElementById('top-products-container');
          topContainer.innerHTML = topRes.data.map((tp, idx) => `
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.65rem 0; border-bottom: 1px solid var(--border-color);">
              <div>
                <span style="font-weight: 800; color: var(--primary); margin-right: 0.5rem;">#${idx + 1}</span>
                <span style="font-weight: 600;">${tp.product_name}</span>
              </div>
              <div style="text-align: right;">
                <div style="font-weight: 800; color: var(--success);">$${Number(tp.total_revenue).toLocaleString()}</div>
                <div style="font-size: 0.75rem; color: var(--text-muted);">${tp.total_units} unidades</div>
              </div>
            </div>
          `).join('');
        }
      } catch (err) {
        console.warn('Error al cargar analíticas:', err);
      }
    }
  }

  // --- Vista de Sincronización ---
  async loadSyncView() {
    const pending = await window.posDB.getPendingSales();
    const history = await window.posDB.getAllSalesHistory();
    const listEl = document.getElementById('sync-pending-list');

    document.getElementById('sync-pending-count-large').textContent = pending.length;
    document.getElementById('sync-history-count-large').textContent = history.length;

    if (pending.length === 0) {
      listEl.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 1.5rem;">No hay ventas pendientes por sincronizar. ¡Todo al día!</p>';
    } else {
      listEl.innerHTML = pending.map((s) => `
        <div style="background: var(--bg-surface); padding: 0.75rem 1rem; border-radius: var(--radius-sm); border: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
          <div>
            <strong>${s.invoice_number}</strong>
            <div style="font-size: 0.75rem; color: var(--text-muted);">${new Date(s.created_at).toLocaleString()} | ${s.items.length} ítems</div>
          </div>
          <div style="text-align: right;">
            <div style="font-weight: 800; color: var(--warning);">$${s.total.toLocaleString()}</div>
            <span style="font-size: 0.7rem; background: var(--warning-light); color: var(--warning); padding: 2px 6px; border-radius: 4px;">Pendiente</span>
          </div>
        </div>
      `).join('');
    }
  }

  // --- Event Listeners Globales ---
  bindEvents() {
    // Tabs
    document.querySelectorAll('.nav-tab').forEach((tab) => {
      tab.addEventListener('click', () => this.switchView(tab.dataset.view));
    });

    // Búsqueda en caja
    const searchInput = document.getElementById('pos-search-input');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.searchQuery = e.target.value;
        this.renderProductsGrid();
      });
    }

    // Botones de Carrito
    document.getElementById('btn-clear-cart').addEventListener('click', () => this.clearCart());
    document.getElementById('btn-checkout').addEventListener('click', () => this.openCheckoutModal());
    document.getElementById('mobile-cart-toggle-btn').addEventListener('click', () => {
      document.getElementById('cart-pane').classList.toggle('mobile-open');
    });

    // Checkout Modal
    document.getElementById('checkout-paid-amount').addEventListener('input', () => this.calculateChange());
    document.getElementById('btn-confirm-sale').addEventListener('click', () => this.finalizeSale());
    document.getElementById('checkout-modal-close').addEventListener('click', () => {
      document.getElementById('checkout-modal').classList.remove('active');
    });

    // Receipt Modal
    document.getElementById('receipt-modal-close').addEventListener('click', () => {
      document.getElementById('receipt-modal').classList.remove('active');
    });
    document.getElementById('btn-print-receipt').addEventListener('click', () => window.print());

    // Toggle Simulación Offline
    const offlineToggle = document.getElementById('simulated-offline-toggle');
    if (offlineToggle) {
      offlineToggle.addEventListener('change', (e) => {
        window.syncManager.setSimulatedOffline(e.target.checked);
      });
    }

    // Botón Sincronizar Ahora
    const triggerSyncBtn = document.getElementById('btn-trigger-sync');
    if (triggerSyncBtn) {
      triggerSyncBtn.addEventListener('click', async () => {
        triggerSyncBtn.disabled = true;
        triggerSyncBtn.textContent = 'Sincronizando...';
        await window.syncManager.triggerSync();
        triggerSyncBtn.disabled = false;
        triggerSyncBtn.textContent = 'Sincronizar Lote Ahora';
        this.loadSyncView();
      });
    }

    // Eventos de red
    window.addEventListener('network-status-changed', () => this.updateNetworkBadge());
    window.addEventListener('sync-complete', () => {
      this.refreshPendingSyncCount();
      if (this.activeView === 'sync') this.loadSyncView();
    });

    // Modal Producto
    document.getElementById('btn-new-product').addEventListener('click', () => this.openNewProductModal());
    document.getElementById('product-modal-close').addEventListener('click', () => {
      document.getElementById('product-modal').classList.remove('active');
    });
    document.getElementById('btn-save-product').addEventListener('click', () => this.saveProductFromModal());

    // Login y Logout
    document.getElementById('auth-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('login-email').value;
      const pass = document.getElementById('login-password').value;
      try {
        const res = await window.apiClient.login(email, pass);
        if (res.success) {
          this.checkSession();
          await window.syncManager.syncCatalogToLocal();
          await this.loadLocalCatalog();
        }
      } catch (err) {
        alert('Error de inicio de sesión: ' + err.message);
      }
    });

    document.getElementById('btn-logout').addEventListener('click', () => {
      window.apiClient.clearSession();
      this.checkSession();
    });
  }
}

// Inicialización cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
  window.posApp = new PosApp();
});
