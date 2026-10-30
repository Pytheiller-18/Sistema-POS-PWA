import os
import secrets
from datetime import timedelta

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_SECRETS_FILE = os.path.join(_BACKEND_DIR, '.secrets')


def _load_or_create_secret(env_name: str) -> str:
    """
    SEGURIDAD (C6): Nunca usar secretos hardcodeados en un repositorio público.
    1. Si existe la variable de entorno, se usa.
    2. Si no, se lee/genera un secreto aleatorio persistente en `backend/.secrets`
       (excluido de Git), de modo que los tokens sobreviven a reinicios del servidor.
    """
    value = os.environ.get(env_name)
    if value:
        return value

    stored = {}
    if os.path.exists(_SECRETS_FILE):
        with open(_SECRETS_FILE, 'r', encoding='utf-8') as fh:
            for line in fh:
                if '=' in line:
                    k, v = line.strip().split('=', 1)
                    stored[k] = v

    if env_name not in stored:
        stored[env_name] = secrets.token_urlsafe(48)
        with open(_SECRETS_FILE, 'w', encoding='utf-8') as fh:
            for k, v in stored.items():
                fh.write(f'{k}={v}\n')

    return stored[env_name]


class Config:
    SECRET_KEY = _load_or_create_secret('SECRET_KEY')
    JWT_SECRET_KEY = _load_or_create_secret('JWT_SECRET_KEY')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.environ.get('JWT_EXPIRES_HOURS', 12)))

    # Zona horaria del negocio para reportes (Colombia = UTC-5, sin horario de verano)
    BUSINESS_UTC_OFFSET_HOURS = float(os.environ.get('BUSINESS_UTC_OFFSET_HOURS', -5))

    # Límites de protección
    MAX_SYNC_BATCH_SIZE = int(os.environ.get('MAX_SYNC_BATCH_SIZE', 200))
    LOGIN_MAX_ATTEMPTS = int(os.environ.get('LOGIN_MAX_ATTEMPTS', 8))
    LOGIN_WINDOW_SECONDS = int(os.environ.get('LOGIN_WINDOW_SECONDS', 300))
    
    # Soporte para MySQL y fallback a SQLite local si no hay servidor MySQL corriendo
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_PORT = os.environ.get('MYSQL_PORT', '3306')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'positiva_pos')

    # Detectar URL explícita o construir URL de MySQL / SQLite
    legacy_sqlite_path = os.path.join(_BACKEND_DIR, 'sistema_pos_pwa.db')
    default_sqlite_path = os.path.join(_BACKEND_DIR, 'positiva_pos.db')
    if not os.path.exists(default_sqlite_path) and os.path.exists(legacy_sqlite_path):
        default_sqlite_path = legacy_sqlite_path
    DATABASE_URL = os.environ.get('DATABASE_URL')
    
    if not DATABASE_URL:
        # Si se especifica USE_MYSQL=1 o variables de MySQL
        if os.environ.get('USE_MYSQL', '0') == '1':
            SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
        else:
            SQLALCHEMY_DATABASE_URI = f"sqlite:///{default_sqlite_path}"
    else:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_recycle': 280,
        'pool_pre_ping': True
    }
    
    # Configuración de CORS
    CORS_HEADERS = 'Content-Type'
