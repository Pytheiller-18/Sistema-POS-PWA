import os
from flask import Flask, jsonify, send_from_directory, abort
from app.config import Config
from app.extensions import db, cors
from app.utils.validators import ValidationError

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'frontend'))


def create_app(config_class=Config):
    """Fábrica de aplicaciones Flask para Positiva-POS."""
    app = Flask(__name__, static_folder=None)
    app.config.from_object(config_class)

    # Inicializar extensiones
    db.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})

    # Registrar Blueprints
    from app.routes.auth import auth_bp
    from app.routes.products import products_bp
    from app.routes.sales import sales_bp
    from app.routes.sync import sync_bp
    from app.routes.reports import reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(sync_bp)
    app.register_blueprint(reports_bp)

    # Endpoint de estado del servidor
    @app.route('/api/health', methods=['GET'])
    def health_check():
        return jsonify({
            'status': 'healthy',
            'system': 'Positiva-POS API',
            'version': '1.1.0',
            'multi_tenant': True,
            'offline_first_ready': True
        }), 200

    # ------------------------------------------------------------------
    # (A8) Servir el frontend PWA desde el mismo origen que la API.
    # Un solo puerto => funciona en celulares por Wi-Fi o túnel sin
    # depender de "localhost:5000" (que en el teléfono apunta a sí mismo).
    # ------------------------------------------------------------------
    @app.route('/', methods=['GET'])
    def frontend_index():
        return send_from_directory(FRONTEND_DIR, 'index.html')

    @app.route('/<path:filename>', methods=['GET'])
    def frontend_assets(filename):
        if filename.startswith('api/'):
            abort(404)
        response = send_from_directory(FRONTEND_DIR, filename)
        if filename == 'sw.js':
            # El Service Worker nunca debe quedar cacheado por el navegador
            response.headers['Cache-Control'] = 'no-cache'
            response.headers['Service-Worker-Allowed'] = '/'
        return response

    # Cabeceras de seguridad básicas
    @app.after_request
    def security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        return response

    # Manejadores de errores globales
    @app.errorhandler(ValidationError)
    def validation_error(error):
        db.session.rollback()
        return jsonify({'success': False, 'error': str(error)}), 400

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({
            'success': False,
            'error': str(error.description) if hasattr(error, 'description') else 'Solicitud inválida'
        }), 400

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'success': False,
            'error': str(error.description) if hasattr(error, 'description') else 'Recurso no encontrado'
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({'success': False, 'error': 'Método HTTP no permitido'}), 405

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor'
        }), 500

    return app
