import jwt
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import request, jsonify, g, current_app
from werkzeug.security import generate_password_hash, check_password_hash

# ============================================================================
# DOBLE VERIFICACIÓN DE SEGURIDAD - AUTENTICACIÓN Y MULTI-TENANCY:
# 1. El token JWT almacena tenant_id, user_id y role firmados criptográficamente.
# 2. El cliente NUNCA puede suplantar o inyectar un tenant_id en payloads o query params;
#    el tenant se obtiene EXCLUSIVAMENTE de g.tenant_id validado por el decorador.
# 3. Se verifica expiración y firma en cada petición antes de acceder a la capa de datos.
# ============================================================================

def hash_password(password: str) -> str:
    """Genera un hash seguro usando PBKDF2 con sal criptográfica."""
    return generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)

def verify_password(password: str, password_hash: str) -> bool:
    """Verifica si la contraseña en texto plano coincide con el hash almacenado."""
    return check_password_hash(password_hash, password)

def generate_jwt_token(user_id: str, tenant_id: str, role: str, business_name: str = "") -> str:
    """Genera un token JWT firmado con expiración configurada."""
    now = datetime.now(timezone.utc)
    expires = now + current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES', timedelta(hours=12))
    payload = {
        'sub': user_id,
        'tenant_id': tenant_id,
        'role': role,
        'business_name': business_name,
        'iat': int(now.timestamp()),
        'exp': int(expires.timestamp())
    }
    return jwt.encode(payload, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')

def decode_jwt_token(token: str) -> dict:
    """Decodifica y valida la firma y vigencia del token JWT."""
    return jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'])

def tenant_required(allowed_roles=None):
    """
    Decorador para proteger endpoints. Valida el JWT y asegura aislamiento multi-tenant.
    Inyecta en flask.g:
      - g.user_id
      - g.tenant_id
      - g.user_role
      - g.business_name
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get('Authorization', None)
            if not auth_header:
                return jsonify({
                    'success': False,
                    'error': 'Falta cabecera Authorization (Bearer Token)'
                }), 401
            
            parts = auth_header.split()
            if len(parts) != 2 or parts[0].lower() != 'bearer':
                return jsonify({
                    'success': False,
                    'error': 'Formato de autorización inválido. Use: Bearer <token>'
                }), 401
            
            token = parts[1]
            try:
                payload = decode_jwt_token(token)
            except jwt.ExpiredSignatureError:
                return jsonify({
                    'success': False,
                    'error': 'La sesión ha expirado. Por favor inicie sesión nuevamente.'
                }), 401
            except jwt.InvalidTokenError:
                return jsonify({
                    'success': False,
                    'error': 'Token de autenticación inválido o alterado.'
                }), 401

            # Inyección obligatoria de contexto del Tenant en flask.g
            g.user_id = payload.get('sub')
            g.tenant_id = payload.get('tenant_id')
            g.user_role = payload.get('role')
            g.business_name = payload.get('business_name', '')

            if not g.tenant_id or not g.user_id:
                return jsonify({
                    'success': False,
                    'error': 'Token incompleto: falta información de tienda o usuario.'
                }), 403

            # Doble verificación de roles autorizados si se especificaron
            if allowed_roles:
                if isinstance(allowed_roles, str):
                    roles = [allowed_roles]
                else:
                    roles = allowed_roles
                if g.user_role not in roles:
                    return jsonify({
                        'success': False,
                        'error': f'Acceso denegado: Se requiere rol {", ".join(roles)}'
                    }), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator
