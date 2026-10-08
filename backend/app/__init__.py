from flask import Flask, jsonify
from app.config import Config
from app.extensions import db, cors

def create_app(config_class=Config):
    """Fábrica de aplicaciones Flask para el SISTEMA POS PWA."""
    app = Flask(__name__)
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
            'system': 'SISTEMA POS PWA API',
            'version': '1.0.0',
            'multi_tenant': True,
            'offline_first_ready': True
        }), 200

    # Manejadores de errores globales
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

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor'
        }), 500

    return app
