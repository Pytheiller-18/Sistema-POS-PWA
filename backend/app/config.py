import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'sistema-pos-pwa-super-secret-jwt-key-2026')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'jwt-pos-pwa-secure-token-secret-2026')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.environ.get('JWT_EXPIRES_HOURS', 12)))
    
    # Soporte para MySQL y fallback a SQLite local si no hay servidor MySQL corriendo
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_PORT = os.environ.get('MYSQL_PORT', '3306')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'sistema_pos_pwa')

    # Detectar URL explícita o construir URL de MySQL / SQLite
    default_sqlite_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'sistema_pos_pwa.db'))
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
