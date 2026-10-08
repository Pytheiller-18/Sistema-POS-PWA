import uuid
from flask import Blueprint, request, jsonify, g
from app.extensions import db
from app.models.tenant import Tenant
from app.models.user import User
from app.middlewares.auth import hash_password, verify_password, generate_jwt_token, tenant_required

auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')

# ============================================================================
# DOBLE VERIFICACIÓN DE SEGURIDAD - RUTAS DE AUTENTICACIÓN:
# 1. En register-tenant, la creación de Tenant y User Admin es estrictamente
#    atómica (misma transacción). Si uno falla, no queda empresa huérfana.
# 2. Las contraseñas jamás se devuelven en JSON ni se almacenan en texto plano.
# 3. La consulta de login filtra al usuario y verifica su estado 'is_active'.
# ============================================================================

@auth_bp.route('/register-tenant', methods=['POST'])
def register_tenant():
    """Registra una nueva tienda/empresa con su usuario Administrador inicial."""
    data = request.get_json() or {}
    
    business_name = data.get('business_name', '').strip()
    full_name = data.get('full_name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not business_name or not full_name or not email or not password:
        return jsonify({
            'success': False,
            'error': 'Todos los campos son obligatorios (business_name, full_name, email, password)'
        }), 400

    # Verificar si el email ya existe en algún tenant (para login único)
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({
            'success': False,
            'error': 'El correo electrónico ya se encuentra registrado'
        }), 409

    try:
        tenant_id = str(uuid.uuid4())
        tenant = Tenant(
            id=tenant_id,
            business_name=business_name,
            tax_id=data.get('tax_id'),
            phone=data.get('phone'),
            email=email,
            address=data.get('address'),
            currency_symbol=data.get('currency_symbol', '$')
        )
        db.session.add(tenant)

        user = User(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            role='ADMIN',
            is_active=True
        )
        db.session.add(user)

        db.session.commit()

        token = generate_jwt_token(user.id, tenant.id, user.role, tenant.business_name)

        return jsonify({
            'success': True,
            'message': 'Tienda y usuario administrador registrados exitosamente',
            'token': token,
            'user': user.to_dict(),
            'tenant': tenant.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Error al registrar empresa: {str(e)}'
        }), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    """Inicio de sesión. Valida credenciales y entrega token JWT multi-tenant."""
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({
            'success': False,
            'error': 'Debe proporcionar email y contraseña'
        }), 400

    user = User.query.filter_by(email=email).first()
    if not user or not verify_password(password, user.password_hash):
        return jsonify({
            'success': False,
            'error': 'Credenciales inválidas (correo o contraseña incorrectos)'
        }), 401

    if not user.is_active:
        return jsonify({
            'success': False,
            'error': 'Este usuario se encuentra inactivo. Contacte al administrador.'
        }), 403

    tenant = Tenant.query.filter_by(id=user.tenant_id).first()
    if not tenant or tenant.status != 'ACTIVE':
        return jsonify({
            'success': False,
            'error': 'La tienda asociada se encuentra suspendida o inactiva.'
        }), 403

    token = generate_jwt_token(user.id, tenant.id, user.role, tenant.business_name)

    return jsonify({
        'success': True,
        'message': 'Autenticación exitosa',
        'token': token,
        'user': user.to_dict(),
        'tenant': tenant.to_dict()
    }), 200

@auth_bp.route('/me', methods=['GET'])
@tenant_required()
def get_me():
    """Retorna información del usuario y empresa autenticados."""
    user = User.query.filter_by(id=g.user_id, tenant_id=g.tenant_id).first_or_404()
    tenant = Tenant.query.filter_by(id=g.tenant_id).first_or_404()

    return jsonify({
        'success': True,
        'user': user.to_dict(),
        'tenant': tenant.to_dict()
    }), 200

@auth_bp.route('/users', methods=['GET'])
@tenant_required(allowed_roles=['ADMIN', 'MANAGER'])
def list_users():
    """Lista usuarios pertenecientes al tenant del usuario autenticado."""
    users = User.query.filter_by(tenant_id=g.tenant_id).all()
    return jsonify({
        'success': True,
        'users': [u.to_dict() for u in users]
    }), 200

@auth_bp.route('/users', methods=['POST'])
@tenant_required(allowed_roles=['ADMIN'])
def create_user():
    """Crea un usuario (cajero o manager) dentro del tenant del admin."""
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    full_name = data.get('full_name', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'CASHIER').upper()

    if not email or not full_name or not password:
        return jsonify({'success': False, 'error': 'Datos incompletos'}), 400

    if role not in ['ADMIN', 'MANAGER', 'CASHIER']:
        return jsonify({'success': False, 'error': 'Rol inválido'}), 400

    existing = User.query.filter_by(tenant_id=g.tenant_id, email=email).first()
    if existing:
        return jsonify({'success': False, 'error': 'El email ya existe en su tienda'}), 409

    user = User(
        id=str(uuid.uuid4()),
        tenant_id=g.tenant_id,
        full_name=full_name,
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=True
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Usuario creado exitosamente',
        'user': user.to_dict()
    }), 201
