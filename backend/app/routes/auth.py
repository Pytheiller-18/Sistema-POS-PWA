from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.tenant import Tenant
from app.models.user import User
from app.middlewares.auth import hash_password, verify_password, generate_jwt_token, tenant_required
from app.utils.validators import clean_str, ValidationError, login_limiter
from app.utils.uuid7 import uuid7_str

auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')

# ============================================================================
# DOBLE VERIFICACIÓN DE SEGURIDAD - RUTAS DE AUTENTICACIÓN:
# 1. En register-tenant, la creación de Tenant y User Admin es estrictamente
#    atómica (misma transacción). Si uno falla, no queda empresa huérfana.
# 2. Las contraseñas jamás se devuelven en JSON ni se almacenan en texto plano.
# 3. La consulta de login filtra al usuario y verifica su estado 'is_active'.
# 4. (C5) El email es ÚNICO GLOBALMENTE: el login se resuelve por email, por lo que
#    dos usuarios con el mismo correo en tiendas distintas harían ambiguo el acceso.
# 5. (O8) Limitador de intentos fallidos por IP+email contra fuerza bruta.
# ============================================================================

MIN_PASSWORD_LENGTH = 6
# Hash ficticio para igualar tiempos de respuesta cuando el email no existe
_DUMMY_HASH = hash_password('timing-attack-mitigation')


def _validate_email(raw) -> str:
    email = (clean_str(raw, 'email', 120, required=True) or '').lower()
    if '@' not in email or '.' not in email.split('@')[-1]:
        raise ValidationError('El correo electrónico no es válido')
    return email


def _validate_password(raw) -> str:
    if not isinstance(raw, str) or len(raw) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f'La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres')
    if len(raw) > 128:
        raise ValidationError('La contraseña es demasiado larga')
    return raw


def _email_taken(email: str) -> bool:
    return db.session.query(User.id).filter(User.email == email).first() is not None


@auth_bp.route('/register-tenant', methods=['POST'])
def register_tenant():
    """Registra una nueva tienda/empresa con su usuario Administrador inicial."""
    data = request.get_json(silent=True) or {}

    business_name = clean_str(data.get('business_name'), 'business_name', 150, required=True)
    full_name = clean_str(data.get('full_name'), 'full_name', 120, required=True)
    email = _validate_email(data.get('email'))
    password = _validate_password(data.get('password'))

    # Verificar si el email ya existe en algún tenant (para login único)
    if _email_taken(email):
        return jsonify({
            'success': False,
            'error': 'El correo electrónico ya se encuentra registrado'
        }), 409

    try:
        tenant_id = uuid7_str()
        tenant = Tenant(
            id=tenant_id,
            business_name=business_name,
            tax_id=clean_str(data.get('tax_id'), 'tax_id', 50),
            phone=clean_str(data.get('phone'), 'phone', 30),
            email=email,
            address=clean_str(data.get('address'), 'address', 255),
            currency_symbol=clean_str(data.get('currency_symbol'), 'currency_symbol', 5) or '$'
        )
        db.session.add(tenant)

        user = User(
            id=uuid7_str(),
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

    except IntegrityError:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'El correo electrónico ya se encuentra registrado'}), 409
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Error al registrar empresa')
        return jsonify({
            'success': False,
            'error': 'Error interno al registrar la empresa'
        }), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """Inicio de sesión. Valida credenciales y entrega token JWT multi-tenant."""
    data = request.get_json(silent=True) or {}
    email = str(data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password or not isinstance(password, str):
        return jsonify({
            'success': False,
            'error': 'Debe proporcionar email y contraseña'
        }), 400

    # (O8) Protección contra fuerza bruta
    limiter_key = f"{request.remote_addr}|{email}"
    max_attempts = current_app.config.get('LOGIN_MAX_ATTEMPTS', 8)
    window = current_app.config.get('LOGIN_WINDOW_SECONDS', 300)
    wait = login_limiter.is_blocked(limiter_key, max_attempts, window)
    if wait:
        return jsonify({
            'success': False,
            'error': f'Demasiados intentos fallidos. Intente de nuevo en {wait} segundos.'
        }), 429

    user = User.query.filter_by(email=email).first()
    password_ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if not user or not password_ok:
        login_limiter.register_failure(limiter_key, window)
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
    if not tenant or tenant.status not in ('ACTIVE', 'TRIAL'):
        return jsonify({
            'success': False,
            'error': 'La tienda asociada se encuentra suspendida o inactiva.'
        }), 403

    login_limiter.reset(limiter_key)
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
    data = request.get_json(silent=True) or {}
    email = _validate_email(data.get('email'))
    full_name = clean_str(data.get('full_name'), 'full_name', 120, required=True)
    password = _validate_password(data.get('password'))
    role = str(data.get('role') or 'CASHIER').upper()

    if role not in ['ADMIN', 'MANAGER', 'CASHIER']:
        return jsonify({'success': False, 'error': 'Rol inválido'}), 400

    # (C5) Unicidad GLOBAL del email (el login no conoce el tenant de antemano)
    if _email_taken(email):
        return jsonify({'success': False, 'error': 'El correo electrónico ya está registrado'}), 409

    user = User(
        id=uuid7_str(),
        tenant_id=g.tenant_id,
        full_name=full_name,
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=True
    )
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'El correo electrónico ya está registrado'}), 409

    return jsonify({
        'success': True,
        'message': 'Usuario creado exitosamente',
        'user': user.to_dict()
    }), 201
