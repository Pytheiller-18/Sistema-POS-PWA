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
    this.isSubmittingSale = false;

    // Escáner de código de barras
    this.html5QrCode = null;
    this.scannerContext = 'POS'; // 'POS' o 'PRODUCT'
    this.availableCameras = [];
    this.currentCameraIndex = 0;
    this.isScanning = false;
    this.isTorchOn = false;
    this.lastScannedCode = null;
    this.lastScannedTime = 0;

    // Sintetizador de audio para escaneo (Web Audio API)
    this.audioCtx = null;

    this.init();
  }

  // --- Utilidades de Seguridad y Formato (C4, O6) ---
  escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  formatMoney(amount) {
    return '$' + Number(amount || 0).toLocaleString('es-CO', { maximumFractionDigits: 0 });
  }

  async init() {
    this.initTheme();
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
      document.getElementById('header-user-name').textContent = 'Sin Sesión';
      document.getElementById('header-tenant-name').textContent = 'POS Offline';
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
      html += `<button class="category-chip ${isActive}" data-cat="${this.escapeHtml(c.id)}">${this.escapeHtml(c.name)}</button>`;
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

      const escapedId = this.escapeHtml(p.id);
      const escapedName = this.escapeHtml(p.name);
      const escapedCategory = this.escapeHtml(p.category_name || 'General');
      const escapedBarcode = this.escapeHtml(p.barcode || 'SIN-CÓDIGO');
      const formattedPrice = this.formatMoney(p.sale_price);

      return `
        <div class="product-card" data-id="${escapedId}">
          <div class="product-header">
            <span class="product-category-tag">${escapedCategory}</span>
            <span class="product-stock-tag ${stockClass}">${stockLabel}</span>
          </div>
          <div class="product-name" title="${escapedName}">${escapedName}</div>
          <div class="product-barcode">${escapedBarcode}</div>
          <div class="product-price-row">
            <span class="product-price">${formattedPrice}</span>
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

    document.getElementById('cart-subtotal').textContent = this.formatMoney(subtotal);
    document.getElementById('cart-total').textContent = this.formatMoney(total);
    document.getElementById('mobile-cart-total-badge').textContent = this.formatMoney(total);

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
          <div class="cart-item-title">${this.escapeHtml(item.name)}</div>
          <div class="cart-item-price">${this.formatMoney(item.price)} c/u</div>
        </div>
        <div class="cart-qty-control">
          <button class="cart-qty-btn" onclick="window.posApp.changeCartItemQty('${this.escapeHtml(item.product_id)}', -1)">-</button>
          <span class="cart-qty-val">${item.quantity}</span>
          <button class="cart-qty-btn" onclick="window.posApp.changeCartItemQty('${this.escapeHtml(item.product_id)}', 1)">+</button>
        </div>
        <div class="cart-item-total">${this.formatMoney(item.price * item.quantity)}</div>
        <button class="cart-item-remove" onclick="window.posApp.removeFromCart('${this.escapeHtml(item.product_id)}')">✕</button>
      </div>
    `).join('');
  }

  // --- Notificaciones & Audio Sintetizado (Offline) ---
  playBeep(type = 'success') {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      if (!this.audioCtx) this.audioCtx = new AudioCtx();
      if (this.audioCtx.state === 'suspended') {
        this.audioCtx.resume();
      }

      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();
      osc.connect(gain);
      gain.connect(this.audioCtx.destination);

      if (type === 'success') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(880, this.audioCtx.currentTime); // Nota La5 (Beep de POS clásico)
        gain.gain.setValueAtTime(0.18, this.audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + 0.12);
        osc.start();
        osc.stop(this.audioCtx.currentTime + 0.12);
      } else {
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(320, this.audioCtx.currentTime);
        gain.gain.setValueAtTime(0.2, this.audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + 0.22);
        osc.start();
        osc.stop(this.audioCtx.currentTime + 0.22);
      }
    } catch (e) {
      console.warn('Audio no disponible:', e);
    }
  }

  showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast-message ${type}`;
    const icon = type === 'success' ? '✓' : (type === 'warning' ? '⚠️' : 'ℹ️');
    toast.innerHTML = `<span style="font-weight:900;">${icon}</span> <span>${this.escapeHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 2500);
  }

  // --- Gestión de Tema Claro / Oscuro ---
  initTheme() {
    const savedTheme = localStorage.getItem('pos_pwa_theme') || 'dark';
    this.applyTheme(savedTheme);
  }

  toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    this.applyTheme(newTheme);
  }

  applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('pos_pwa_theme', theme);

    const sunIcon = document.getElementById('icon-theme-sun');
    const moonIcon = document.getElementById('icon-theme-moon');
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');

    if (theme === 'light') {
      if (sunIcon) sunIcon.style.display = 'none';
      if (moonIcon) moonIcon.style.display = 'block';
      if (metaThemeColor) metaThemeColor.setAttribute('content', '#f1f5f9');
    } else {
      if (sunIcon) sunIcon.style.display = 'block';
      if (moonIcon) moonIcon.style.display = 'none';
      if (metaThemeColor) metaThemeColor.setAttribute('content', '#0b0f19');
    }
  }

  // --- Escáner de Códigos de Barras con Cámara (PWA / Html5Qrcode) ---
  async openBarcodeScanner(context = 'POS') {
    this.scannerContext = context;
    const modalTitle = document.getElementById('scanner-modal-title');
    const lastDetected = document.getElementById('scanner-last-detected');

    if (modalTitle) {
      modalTitle.textContent = context === 'POS' ? '📷 Escanear Producto (Caja)' : '📷 Escanear Código (Inventario)';
    }
    if (lastDetected) {
      lastDetected.textContent = 'Apunta la cámara al código de barras del producto...';
    }

    document.getElementById('scanner-modal').classList.add('active');

    try {
      if (!window.Html5Qrcode) {
        alert('Librería de escaneo no disponible.');
        return;
      }

      if (!this.html5QrCode) {
        this.html5QrCode = new Html5Qrcode("scanner-viewport");
      }

      try {
        this.availableCameras = await Html5Qrcode.getCameras();
      } catch (err) {
        this.availableCameras = [];
      }

      const config = {
        fps: 15,
        qrbox: { width: 260, height: 160 },
        aspectRatio: 1.0,
        experimentalFeatures: {
          useBarCodeDetectorIfSupported: true
        }
      };

      let cameraConfig = { facingMode: "environment" }; // Preferir cámara trasera en celulares
      if (this.availableCameras && this.availableCameras.length > 0) {
        const backCam = this.availableCameras.find((c) =>
          c.label.toLowerCase().includes('back') || c.label.toLowerCase().includes('trasera') || c.label.toLowerCase().includes('posterior')
        );
        if (backCam) {
          cameraConfig = backCam.id;
        } else {
          cameraConfig = this.availableCameras[this.currentCameraIndex % this.availableCameras.length].id;
        }
      }

      await this.html5QrCode.start(
        cameraConfig,
        config,
        (decodedText) => this.onBarcodeDetected(decodedText),
        () => {} // Ignorar frames sin código
      );
      this.isScanning = true;
    } catch (err) {
      console.warn('Error al iniciar cámara para escáner:', err);
      if (lastDetected) {
        lastDetected.innerHTML = `<span style="color: var(--danger);">⚠️ No se pudo acceder a la cámara: ${this.escapeHtml(err.message || 'Permiso denegado')}</span>`;
      }
    }
  }

  async stopBarcodeScanner() {
    if (this.html5QrCode && this.isScanning) {
      try {
        await this.html5QrCode.stop();
      } catch (e) {
        console.warn('Error al detener escáner:', e);
      }
      this.isScanning = false;
    }
    this.isTorchOn = false;
    const modal = document.getElementById('scanner-modal');
    if (modal) modal.classList.remove('active');
  }

  async toggleTorch() {
    if (!this.html5QrCode || !this.isScanning) return;
    try {
      this.isTorchOn = !this.isTorchOn;
      await this.html5QrCode.applyVideoConstraints({
        advanced: [{ torch: this.isTorchOn }]
      });
      const torchBtn = document.getElementById('btn-scanner-toggle-torch');
      if (torchBtn) {
        torchBtn.textContent = this.isTorchOn ? '🔦 Apagar Linterna' : '🔦 Linterna';
      }
    } catch (e) {
      console.warn('Linterna no soportada en este dispositivo:', e);
      this.showToast('Linterna no compatible en este sensor', 'warning');
    }
  }

  async flipCamera() {
    if (!this.availableCameras || this.availableCameras.length < 2) {
      this.showToast('Solo hay 1 cámara disponible en este dispositivo', 'warning');
      return;
    }
    await this.stopBarcodeScanner();
    this.currentCameraIndex = (this.currentCameraIndex + 1) % this.availableCameras.length;
    await this.openBarcodeScanner(this.scannerContext);
  }

  onBarcodeDetected(code) {
    const cleanCode = String(code).trim();
    if (!cleanCode) return;

    const now = Date.now();
    // Debounce: evitar lecturas duplicadas en menos de 1.4 segundos para el mismo código
    if (this.lastScannedCode === cleanCode && (now - this.lastScannedTime) < 1400) {
      return;
    }
    this.lastScannedCode = cleanCode;
    this.lastScannedTime = now;

    const continuousCheckbox = document.getElementById('scanner-continuous-mode');
    const isContinuous = continuousCheckbox ? continuousCheckbox.checked : false;

    if (this.scannerContext === 'POS') {
      const codeLower = cleanCode.toLowerCase();
      const product = this.products.find((p) => p.is_active && (
        (p.barcode && String(p.barcode).trim().toLowerCase() === codeLower) ||
        p.id.toLowerCase() === codeLower
      ));

      if (product) {
        this.playBeep('success');
        this.addToCart(product);
        this.showToast(`Agregado: ${product.name}`, 'success');
        const lastDetected = document.getElementById('scanner-last-detected');
        if (lastDetected) {
          lastDetected.innerHTML = `<strong style="color: var(--success);">✓ ${this.escapeHtml(product.name)}</strong> (${this.formatMoney(product.sale_price)})`;
        }
        if (!isContinuous) {
          setTimeout(() => this.stopBarcodeScanner(), 600);
        }
      } else {
        this.playBeep('warning');
        this.showToast(`Código [${cleanCode}] no registrado`, 'warning');
        const lastDetected = document.getElementById('scanner-last-detected');
        if (lastDetected) {
          lastDetected.innerHTML = `<span style="color: var(--warning);">⚠️ Código [${this.escapeHtml(cleanCode)}] no encontrado en catálogo</span>`;
        }
      }
    } else if (this.scannerContext === 'PRODUCT') {
      this.playBeep('success');
      const barcodeInput = document.getElementById('product-form-barcode');
      if (barcodeInput) {
        barcodeInput.value = cleanCode;
      }
      this.showToast(`Código asignado: ${cleanCode}`, 'success');
      setTimeout(() => this.stopBarcodeScanner(), 500);
    }
  }

  // --- Proceso de Cobro y Cálculo Dinámico de Cambio (Checkout) ---
  openCheckoutModal() {
    if (this.cart.length === 0) return;

    const { total } = this.calculateCartTotals();
    document.getElementById('checkout-total-display').textContent = this.formatMoney(total);
    const paidInput = document.getElementById('checkout-paid-amount');
    paidInput.value = total;

    document.getElementById('checkout-payment-method').value = 'CASH';
    this.renderSmartDenominations(total);
    this.calculateChange();

    document.getElementById('checkout-modal').classList.add('active');
  }

  renderSmartDenominations(total) {
    const container = document.getElementById('checkout-smart-denominations');
    if (!container) return;

    if (total <= 0) {
      container.innerHTML = '<button type="button" class="cash-pill-btn active" onclick="window.posApp.setQuickCash(\'EXACT\')">Exacto ($0)</button>';
      return;
    }

    const suggestions = new Set();
    suggestions.add(total); // Pago exacto

    [1000, 2000, 5000, 10000, 20000, 50000, 100000].forEach((denom) => {
      if (denom > total) {
        suggestions.add(denom);
      } else {
        const nextMultiple = Math.ceil(total / denom) * denom;
        if (nextMultiple > total) suggestions.add(nextMultiple);
      }
    });

    [10000, 20000, 50000, 100000].forEach((b) => {
      if (b >= total) suggestions.add(b);
    });

    const sorted = Array.from(suggestions).sort((a, b) => a - b).slice(0, 5);

    let html = `<button type="button" class="cash-pill-btn active" onclick="window.posApp.setQuickCash('EXACT')">Exacto (${this.formatMoney(total)})</button>`;
    sorted.forEach((val) => {
      if (val !== total) {
        html += `<button type="button" class="cash-pill-btn" onclick="window.posApp.setQuickCash(${val})">${this.formatMoney(val)}</button>`;
      }
    });

    container.innerHTML = html;
  }

  calculateChange() {
    const { total } = this.calculateCartTotals();
    const method = document.getElementById('checkout-payment-method').value;
    const paidInput = document.getElementById('checkout-paid-amount');
    const cardEl = document.getElementById('checkout-change-card');
    const titleEl = document.getElementById('checkout-change-title');
    const subtitleEl = document.getElementById('checkout-change-subtitle');
    const amountEl = document.getElementById('checkout-change-display');
    const confirmBtn = document.getElementById('btn-confirm-sale');
    const cashSection = document.getElementById('cash-payment-section');

    if (method !== 'CASH') {
      if (cashSection) cashSection.style.display = 'none';
      if (cardEl) {
        cardEl.className = 'checkout-change-card change-exact';
        if (titleEl) titleEl.textContent = 'Pago Electrónico:';
        if (subtitleEl) subtitleEl.textContent = 'Sin devuelta en efectivo';
        if (amountEl) amountEl.textContent = this.formatMoney(total);
      }
      confirmBtn.disabled = false;
      return;
    }

    if (cashSection) cashSection.style.display = 'block';

    const paid = Number(paidInput.value) || 0;
    const difference = paid - total;

    // Resaltar botón activo en las denominaciones si coincide
    document.querySelectorAll('#checkout-smart-denominations .cash-pill-btn').forEach((btn) => {
      if (paid === total && btn.textContent.includes('Exacto')) {
        btn.classList.add('active');
      } else if (btn.textContent.includes(this.formatMoney(paid)) && !btn.textContent.includes('Exacto')) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    if (difference > 0) {
      if (cardEl) cardEl.className = 'checkout-change-card change-positive';
      if (titleEl) titleEl.textContent = 'Cambio / Devuelta a Entregar:';
      if (subtitleEl) subtitleEl.textContent = 'Entregar al cliente';
      if (amountEl) amountEl.textContent = this.formatMoney(difference);
      confirmBtn.disabled = false;
    } else if (difference === 0) {
      if (cardEl) cardEl.className = 'checkout-change-card change-exact';
      if (titleEl) titleEl.textContent = 'Pago Exacto:';
      if (subtitleEl) subtitleEl.textContent = 'Sin devuelta en efectivo';
      if (amountEl) amountEl.textContent = '$0';
      confirmBtn.disabled = false;
    } else {
      if (cardEl) cardEl.className = 'checkout-change-card change-negative';
      if (titleEl) titleEl.textContent = 'Monto Insuficiente (Faltante):';
      if (subtitleEl) subtitleEl.textContent = 'Falta dinero para cubrir la venta';
      if (amountEl) amountEl.textContent = `-${this.formatMoney(Math.abs(difference))}`;
      confirmBtn.disabled = true; // Prohibir confirmación hasta cubrir la orden
    }
  }

  setQuickCash(amount) {
    const { total } = this.calculateCartTotals();
    const input = document.getElementById('checkout-paid-amount');
    const value = amount === 'EXACT' ? total : Number(amount);
    input.value = value;
    this.calculateChange();
  }

  addCashIncrement(amount) {
    const input = document.getElementById('checkout-paid-amount');
    const current = Number(input.value) || 0;
    input.value = current + Number(amount);
    this.calculateChange();
  }

  async finalizeSale() {
    if (this.isSubmittingSale) return;
    const confirmBtn = document.getElementById('btn-confirm-sale');

    const { subtotal, tax, discount, total } = this.calculateCartTotals();
    const paymentMethod = document.getElementById('checkout-payment-method').value;
    let paid = Number(document.getElementById('checkout-paid-amount').value) || total;

    if (paymentMethod !== 'CASH') {
      paid = total;
    } else if (paid < total) {
      this.showToast('El monto pagado en efectivo es insuficiente para completar la venta.', 'warning');
      return;
    }

    const change = Math.max(0, paid - total);

    // (A4) Bloqueo de concurrencia y protección contra doble clic
    this.isSubmittingSale = true;
    if (confirmBtn) {
      confirmBtn.disabled = true;
      confirmBtn.textContent = 'Procesando venta...';
    }

    const clientSyncId = 'pos-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    const invoiceNumber = 'POS-' + new Date().getFullYear() + '-' + Math.floor(100000 + Math.random() * 900000);
    const currentTenant = window.apiClient.tenant;

    const salePayload = {
      tenant_id: currentTenant ? currentTenant.id : null,
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

    try {
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
          if (res && res.success) {
            await window.posDB.markSaleAsSynced(clientSyncId);
            isSyncedNow = true;
            if (res.sale && res.sale.invoice_number) {
              salePayload.invoice_number = res.sale.invoice_number;
            }
          }
        } catch (err) {
          console.warn('Venta guardada localmente, sincronización pendiente:', err.message);
        }
      }

      // Preparar ticket impreso
      this.currentSaleCompleted = {
        ...salePayload,
        isSynced: isSyncedNow,
        tenant: currentTenant || { business_name: 'Mi Tienda POS', tax_id: 'NIT Demo' },
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
    } catch (e) {
      console.error('Error al procesar la venta:', e);
      this.showToast('Error al registrar la venta: ' + e.message, 'warning');
    } finally {
      this.isSubmittingSale = false;
      if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Confirmar Venta (Enter)';
      }
    }
  }

  showReceiptModal() {
    const sale = this.currentSaleCompleted;
    if (!sale) return;

    const receiptContent = document.getElementById('receipt-ticket-content');
    receiptContent.innerHTML = `
      <div class="ticket-header">
        <div class="ticket-store-name">${this.escapeHtml(sale.tenant.business_name)}</div>
        <div>${this.escapeHtml(sale.tenant.tax_id || '')}</div>
        <div>Tel: ${this.escapeHtml(sale.tenant.phone || '')}</div>
        <div style="margin-top: 6px;">Factura: <strong>${this.escapeHtml(sale.invoice_number)}</strong></div>
        <div>Fecha: ${new Date(sale.created_at).toLocaleString()}</div>
        <div>Atendido por: ${this.escapeHtml(sale.user.full_name)}</div>
        <div style="margin-top: 4px; font-weight: 700; color: ${sale.isSynced ? '#059669' : '#d97706'};">
          ${sale.isSynced ? '● SINCRONIZADO EN NUBE' : '▲ GUARDADO LOCAL (OFFLINE)'}
        </div>
      </div>

      <div class="ticket-divider"></div>

      <div style="margin-bottom: 6px;">
        ${sale.items.map((i) => `
          <div class="ticket-row">
            <span>${i.quantity}x ${this.escapeHtml(i.product_name)}</span>
            <span>${this.formatMoney(i.total)}</span>
          </div>
        `).join('')}
      </div>

      <div class="ticket-divider"></div>

      <div class="ticket-row">
        <span>Subtotal:</span>
        <span>${this.formatMoney(sale.subtotal)}</span>
      </div>
      ${sale.discount > 0 ? `
      <div class="ticket-row">
        <span>Descuento:</span>
        <span>-${this.formatMoney(sale.discount)}</span>
      </div>` : ''}
      <div class="ticket-row ticket-total">
        <span>TOTAL:</span>
        <span>${this.formatMoney(sale.total)}</span>
      </div>
      <div class="ticket-row">
        <span>Método:</span>
        <span>${this.escapeHtml(sale.payment_method)}</span>
      </div>
      <div class="ticket-row">
        <span>Pagó con:</span>
        <span>${this.formatMoney(sale.amount_paid)}</span>
      </div>
      <div class="ticket-row">
        <span>Cambio / Vueltas:</span>
        <span>${this.formatMoney(sale.change_due)}</span>
      </div>

      <div class="ticket-divider"></div>
      <div style="text-align: center; margin-top: 8px;">
        <p>¡Gracias por su compra!</p>
        <p style="font-size: 10px; color: #888;">ID: ${this.escapeHtml(sale.client_sync_id)}</p>
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
        <td style="font-family: var(--font-mono); font-size: 0.8rem;">${this.escapeHtml(p.barcode || '-')}</td>
        <td style="font-weight: 700;">${this.escapeHtml(p.name)}</td>
        <td>${this.escapeHtml(p.category_name || 'General')}</td>
        <td>${this.formatMoney(p.cost_price)}</td>
        <td style="font-weight: 700; color: var(--success);">${this.formatMoney(p.sale_price)}</td>
        <td style="font-weight: 800; color: ${p.stock <= p.min_stock ? 'var(--warning)' : 'var(--text-main)'};">${p.stock}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="window.posApp.openEditProductModal('${this.escapeHtml(p.id)}')">Editar</button>
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
      this.categories.map((c) => `<option value="${this.escapeHtml(c.id)}">${this.escapeHtml(c.name)}</option>`).join('');

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
      this.categories.map((c) => `<option value="${this.escapeHtml(c.id)}" ${c.id === prod.category_id ? 'selected' : ''}>${this.escapeHtml(c.name)}</option>`).join('');

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
      this.showToast('El nombre del producto es obligatorio', 'warning');
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
        this.showToast('Producto actualizado con éxito', 'success');
      } else {
        // (A3) Crear nuevo producto: requiere conexión activa para asignar UUID oficial
        if (!window.syncManager.effectiveOnlineStatus()) {
          this.showToast('Para evitar inconsistencias en ventas, la creación de nuevos productos requiere conexión activa.', 'warning');
          return;
        }
        const res = await window.apiClient.createProduct(payload);
        if (res.product) {
          await window.posDB.saveProducts([res.product]);
        }
        this.showToast('Producto creado exitosamente', 'success');
      }

      document.getElementById('product-modal').classList.remove('active');
      await this.loadLocalCatalog();
    } catch (err) {
      this.showToast('Error al guardar producto: ' + err.message, 'warning');
    }
  }

  // --- Vista de Analíticas y Reportes (A5) ---
  async loadReportsView() {
    if (!window.syncManager.effectiveOnlineStatus() || !window.apiClient.isAuthenticated()) {
      document.getElementById('reports-offline-warning').style.display = 'block';
      return;
    }

    document.getElementById('reports-offline-warning').style.display = 'none';
    const user = window.apiClient.user;
    const isAdmin = user && user.role === 'ADMIN';

    try {
      // Manejo seguro por rol: no rompe la vista si el usuario no es ADMIN
      const requests = [
        window.apiClient.getReportsToday().catch((e) => ({ success: false, error: e })),
        window.apiClient.getReportsMonthly().catch((e) => ({ success: false, error: e })),
        window.apiClient.getReportsTopProducts(5).catch((e) => ({ success: false, error: e }))
      ];

      if (isAdmin) {
        requests.push(window.apiClient.getReportsProfit().catch((e) => ({ success: false, error: e })));
      }

      const results = await Promise.all(requests);
      const todayRes = results[0];
      const monthRes = results[1];
      const topRes = results[2];
      const profitRes = isAdmin ? results[3] : null;

      if (todayRes && todayRes.success && todayRes.data) {
        document.getElementById('kpi-today-sales').textContent = this.formatMoney(todayRes.data.total_sales);
        document.getElementById('kpi-today-tickets').textContent = `${todayRes.data.transaction_count} tickets`;
      }

      if (monthRes && monthRes.success && monthRes.data) {
        document.getElementById('kpi-month-sales').textContent = this.formatMoney(monthRes.data.total_sales);
        document.getElementById('kpi-month-growth').textContent = `${monthRes.data.growth_percentage >= 0 ? '+' : ''}${monthRes.data.growth_percentage}% vs mes anterior`;
      }

      if (profitRes && profitRes.success && profitRes.data) {
        document.getElementById('kpi-total-profit').textContent = this.formatMoney(profitRes.data.gross_profit);
        document.getElementById('kpi-profit-margin').textContent = `Margen: ${profitRes.data.margin_percentage}%`;
      } else if (!isAdmin) {
        document.getElementById('kpi-total-profit').textContent = 'Solo Admin';
        document.getElementById('kpi-profit-margin').textContent = 'Acceso restringido';
      }

      if (topRes && topRes.success && Array.isArray(topRes.data)) {
        const topContainer = document.getElementById('top-products-container');
        topContainer.innerHTML = topRes.data.map((tp, idx) => `
          <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.65rem 0; border-bottom: 1px solid var(--border-color);">
            <div>
              <span style="font-weight: 800; color: var(--primary); margin-right: 0.5rem;">#${idx + 1}</span>
              <span style="font-weight: 600;">${this.escapeHtml(tp.product_name)}</span>
            </div>
            <div style="text-align: right;">
              <div style="font-weight: 800; color: var(--success);">${this.formatMoney(tp.total_revenue)}</div>
              <div style="font-size: 0.75rem; color: var(--text-muted);">${tp.total_units} unidades</div>
            </div>
          </div>
        `).join('');
      }
    } catch (err) {
      console.warn('Error al cargar analíticas:', err);
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
            <strong>${this.escapeHtml(s.invoice_number)}</strong>
            <div style="font-size: 0.75rem; color: var(--text-muted);">${new Date(s.created_at).toLocaleString()} | ${s.items.length} ítems</div>
          </div>
          <div style="text-align: right;">
            <div style="font-weight: 800; color: var(--warning);">${this.formatMoney(s.total)}</div>
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

    // Selector de Tema (Claro / Oscuro)
    const btnToggleTheme = document.getElementById('btn-toggle-theme');
    if (btnToggleTheme) {
      btnToggleTheme.addEventListener('click', () => this.toggleTheme());
    }

    // Escáner de Códigos de Barras (Cámara)
    const btnScanPos = document.getElementById('btn-open-scanner-pos');
    if (btnScanPos) {
      btnScanPos.addEventListener('click', () => this.openBarcodeScanner('POS'));
    }

    const btnScanProd = document.getElementById('btn-open-scanner-prod');
    if (btnScanProd) {
      btnScanProd.addEventListener('click', () => this.openBarcodeScanner('PRODUCT'));
    }

    const btnScanClose = document.getElementById('scanner-modal-close');
    if (btnScanClose) {
      btnScanClose.addEventListener('click', () => this.stopBarcodeScanner());
    }

    const btnTorch = document.getElementById('btn-scanner-toggle-torch');
    if (btnTorch) {
      btnTorch.addEventListener('click', () => this.toggleTorch());
    }

    const btnFlip = document.getElementById('btn-scanner-flip-camera');
    if (btnFlip) {
      btnFlip.addEventListener('click', () => this.flipCamera());
    }

    // Búsqueda en caja (Input y soporte para lector de código de barras físico USB/Bluetooth)
    const searchInput = document.getElementById('pos-search-input');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.searchQuery = e.target.value;
        this.renderProductsGrid();
      });

      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          const val = searchInput.value.trim().toLowerCase();
          if (val) {
            const exactProduct = this.products.find((p) => p.is_active && p.barcode && String(p.barcode).trim().toLowerCase() === val);
            if (exactProduct) {
              this.addToCart(exactProduct);
              this.playBeep('success');
              this.showToast(`Agregado: ${exactProduct.name}`, 'success');
              searchInput.value = '';
              this.searchQuery = '';
              this.renderProductsGrid();
            }
          }
        }
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
    const paymentSelect = document.getElementById('checkout-payment-method');
    if (paymentSelect) {
      paymentSelect.addEventListener('change', () => this.calculateChange());
    }
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

    // (A6) Interceptación de sesión expirada
    window.addEventListener('auth-expired', () => {
      this.clearCart();
      this.checkSession();
      this.showToast('Tu sesión ha expirado. Por favor inicia sesión nuevamente.', 'warning');
    });

    // Modal Producto
    document.getElementById('btn-new-product').addEventListener('click', () => this.openNewProductModal());
    document.getElementById('product-modal-close').addEventListener('click', () => {
      document.getElementById('product-modal').classList.remove('active');
    });
    document.getElementById('btn-save-product').addEventListener('click', () => this.saveProductFromModal());

    // Login y Logout (C3)
    document.getElementById('auth-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('login-email').value;
      const pass = document.getElementById('login-password').value;
      try {
        const res = await window.apiClient.login(email, pass);
        if (res.success) {
          // (C3) Si se cambió de tienda en el mismo dispositivo, limpiar catálogo anterior
          const prevTenantId = await window.posDB.getConfig('current_tenant_id');
          if (prevTenantId && res.tenant && prevTenantId !== res.tenant.id) {
            await window.posDB.clearCatalogData();
          }
          if (res.tenant) {
            await window.posDB.setConfig('current_tenant_id', res.tenant.id);
          }
          this.checkSession();
          await window.syncManager.syncCatalogToLocal(true);
          await this.loadLocalCatalog();
          this.showToast('Bienvenido, ' + (res.user ? res.user.full_name : ''), 'success');
        }
      } catch (err) {
        this.showToast('Error de inicio de sesión: ' + err.message, 'warning');
      }
    });

    document.getElementById('btn-logout').addEventListener('click', () => {
      this.clearCart();
      window.apiClient.clearSession();
      this.checkSession();
      this.showToast('Sesión cerrada correctamente', 'info');
    });

    // Alternar visibilidad de contraseña (ojo abierto / cerrado)
    const btnTogglePass = document.getElementById('btn-toggle-password');
    const passInput = document.getElementById('login-password');
    const iconEyeClosed = document.getElementById('icon-eye-closed');
    const iconEyeOpen = document.getElementById('icon-eye-open');

    if (btnTogglePass && passInput) {
      btnTogglePass.addEventListener('click', () => {
        const isPassword = passInput.type === 'password';
        passInput.type = isPassword ? 'text' : 'password';

        if (isPassword) {
          iconEyeClosed.style.display = 'none';
          iconEyeOpen.style.display = 'block';
          btnTogglePass.title = 'Ocultar contraseña';
        } else {
          iconEyeClosed.style.display = 'block';
          iconEyeOpen.style.display = 'none';
          btnTogglePass.title = 'Mostrar contraseña';
        }
      });
    }
  }
}

// Inicialización cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
  window.posApp = new PosApp();
});
