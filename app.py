"""
CinemaCity — Flask Application Factory
"""
import os
from flask import Flask, render_template, send_from_directory

from config import Config
from models import db
from routes_api import api_bp
from routes_admin import admin_bp
from scheduler import init_scheduler


def create_app(config_class=Config):
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
    )
    app.config.from_object(config_class)

    # ── Extensiones ────────────────────────────────────────────
    db.init_app(app)

    # ── Blueprints ─────────────────────────────────────────────
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)

    # ── BD: crear tablas si no existen ─────────────────────────
    with app.app_context():
        os.makedirs(
            os.path.join(app.root_path, 'instance'),
            exist_ok=True,
        )
        db.create_all()
        _migrate_db()


def _migrate_db():
    """Agrega columnas nuevas a tablas existentes sin perder datos (SQLite safe)."""
    from sqlalchemy import text
    with db.engine.connect() as conn:
        for stmt in (
            'ALTER TABLE listas ADD COLUMN incluir_live BOOLEAN NOT NULL DEFAULT 0',
            'ALTER TABLE listas ADD COLUMN usar_proxy   BOOLEAN NOT NULL DEFAULT 0',
        ):
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass   # columna ya existe → ignorar

    # ── Scheduler (solo si no estamos en testing y AUTO_SCAN=1) ─
    # Poner AUTO_SCAN=0 en .env para deshabilitar el escaneo automático.
    if not app.testing and app.config.get('AUTO_SCAN', 1):
        init_scheduler(app)

    # ── Rutas frontend ─────────────────────────────────────────
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/manifest.json')
    def manifest():
        return send_from_directory(app.static_folder, 'manifest.json')

    @app.route('/service-worker.js')
    def service_worker():
        return send_from_directory(
            app.static_folder, 'js/service-worker.js',
            mimetype='application/javascript',
        )

    # ── Errores ────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return {'error': 'No encontrado'}, 404

    @app.errorhandler(500)
    def server_error(e):
        return {'error': 'Error interno del servidor'}, 500

    return app


# ── Punto de entrada para desarrollo local ─────────────────────
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=8000)
