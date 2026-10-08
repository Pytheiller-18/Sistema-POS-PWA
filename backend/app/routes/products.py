import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from app.extensions import db
from app.models.product import Product, Category
from app.middlewares.auth import tenant_required

products_bp = Blueprint('products', __name__, url_prefix='/api/v1/products')

# ============================================================================
# DOBLE VERIFICACIÓN DE SEGURIDAD - PRODUCTOS:
# 1. Toda consulta (SELECT, UPDATE, DELETE) filtra obligatoriamente por
#    `tenant_id == g.tenant_id`. Jamás se usa ID directo sin validar pertenencia.
# 2. Las eliminaciones son 'soft deletes' (is_active=False) para no corromper
#    integridad referencial en ventas pasadas.
# 3. Soporte delta `?since=...` para permitir sincronización eficiente del catálogo.
# ============================================================================

@products_bp.route('', methods=['GET'])
@tenant_required()
def list_products():
    """Lista productos del catálogo del tenant con soporte de búsqueda y delta."""
    search = request.args.get('search', '').strip()
    category_id = request.args.get('category_id')
    since = request.args.get('since') # Para delta sync offline

    query = Product.query.filter_by(tenant_id=g.tenant_id)

    # Si no es sincronización delta completa, sólo productos activos
    if not since:
        query = query.filter_by(is_active=True)
    else:
        try:
            since_dt = datetime.fromisoformat(since)
            query = query.filter(Product.updated_at >= since_dt)
        except Exception:
            pass # Si el formato es inválido, continúa con consulta estándar

    if category_id:
        query = query.filter_by(category_id=category_id)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (Product.name.ilike(search_filter)) | 
            (Product.barcode.ilike(search_filter))
        )

    products = query.order_by(Product.name.asc()).all()

    return jsonify({
        'success': True,
        'count': len(products),
        'products': [p.to_dict() for p in products]
    }), 200

@products_bp.route('/<product_id>', methods=['GET'])
@tenant_required()
def get_product(product_id):
    """Obtiene un producto específico perteneciente al tenant autenticado."""
    product = Product.query.filter_by(id=product_id, tenant_id=g.tenant_id).first_or_404(
        description="Producto no encontrado o no pertenece a su tienda"
    )
    return jsonify({
        'success': True,
        'product': product.to_dict()
    }), 200

@products_bp.route('', methods=['POST'])
@tenant_required(allowed_roles=['ADMIN', 'MANAGER'])
def create_product():
    """Crea un nuevo producto en el catálogo del tenant."""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'El nombre del producto es obligatorio'}), 400

    barcode = data.get('barcode', '').strip() or None
    if barcode:
        # Verificar que el código de barras no esté duplicado en el mismo tenant
        existing = Product.query.filter_by(tenant_id=g.tenant_id, barcode=barcode, is_active=True).first()
        if existing:
            return jsonify({'success': False, 'error': f'Ya existe un producto con el código de barras {barcode}'}), 409

    category_id = data.get('category_id')
    if category_id:
        category = Category.query.filter_by(id=category_id, tenant_id=g.tenant_id).first()
        if not category:
            return jsonify({'success': False, 'error': 'La categoría seleccionada no existe'}), 404

    product = Product(
        id=str(uuid.uuid4()),
        tenant_id=g.tenant_id,
        category_id=category_id,
        barcode=barcode,
        name=name,
        cost_price=float(data.get('cost_price', 0.0)),
        sale_price=float(data.get('sale_price', 0.0)),
        stock=int(data.get('stock', 0)),
        min_stock=int(data.get('min_stock', 5)),
        is_active=True
    )
    db.session.add(product)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Producto creado exitosamente',
        'product': product.to_dict()
    }), 201

@products_bp.route('/<product_id>', methods=['PUT'])
@tenant_required(allowed_roles=['ADMIN', 'MANAGER'])
def update_product(product_id):
    """Actualiza datos de un producto dentro del tenant."""
    product = Product.query.filter_by(id=product_id, tenant_id=g.tenant_id).first_or_404()
    data = request.get_json() or {}

    if 'name' in data:
        name = data['name'].strip()
        if not name:
            return jsonify({'success': False, 'error': 'El nombre no puede ser vacío'}), 400
        product.name = name

    if 'barcode' in data:
        barcode = data['barcode'].strip() or None
        if barcode and barcode != product.barcode:
            existing = Product.query.filter_by(tenant_id=g.tenant_id, barcode=barcode, is_active=True).first()
            if existing and existing.id != product.id:
                return jsonify({'success': False, 'error': 'Código de barras ya asignado a otro producto'}), 409
        product.barcode = barcode

    if 'category_id' in data:
        cat_id = data['category_id']
        if cat_id:
            category = Category.query.filter_by(id=cat_id, tenant_id=g.tenant_id).first()
            if not category:
                return jsonify({'success': False, 'error': 'Categoría inválida'}), 404
        product.category_id = cat_id

    if 'cost_price' in data:
        product.cost_price = float(data['cost_price'])
    if 'sale_price' in data:
        product.sale_price = float(data['sale_price'])
    if 'stock' in data:
        product.stock = int(data['stock'])
    if 'min_stock' in data:
        product.min_stock = int(data['min_stock'])
    if 'is_active' in data:
        product.is_active = bool(data['is_active'])

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Producto actualizado exitosamente',
        'product': product.to_dict()
    }), 200

@products_bp.route('/<product_id>', methods=['DELETE'])
@tenant_required(allowed_roles=['ADMIN'])
def delete_product(product_id):
    """Desactivación lógica (soft delete) del producto."""
    product = Product.query.filter_by(id=product_id, tenant_id=g.tenant_id).first_or_404()
    product.is_active = False
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Producto desactivado exitosamente del catálogo'
    }), 200

@products_bp.route('/categories', methods=['GET'])
@tenant_required()
def list_categories():
    """Lista categorías creadas para la tienda."""
    categories = Category.query.filter_by(tenant_id=g.tenant_id, is_active=True).order_by(Category.name.asc()).all()
    return jsonify({
        'success': True,
        'categories': [c.to_dict() for c in categories]
    }), 200

@products_bp.route('/categories', methods=['POST'])
@tenant_required(allowed_roles=['ADMIN', 'MANAGER'])
def create_category():
    """Crea una nueva categoría para la tienda."""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'El nombre de categoría es obligatorio'}), 400

    category = Category(
        id=str(uuid.uuid4()),
        tenant_id=g.tenant_id,
        name=name,
        description=data.get('description'),
        is_active=True
    )
    db.session.add(category)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Categoría creada',
        'category': category.to_dict()
    }), 201
