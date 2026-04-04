"""
CinemaCity — Flask Application Factory
"""
import json
import os
from datetime import timedelta
from flask import Flask, render_template, send_from_directory, session, g, request

from config import Config
from models import db
from routes_api import api_bp
from routes_admin import admin_bp
from routes_iptv import iptv_bp, xtream_bp
from scheduler import init_scheduler


def create_app(config_class=Config):
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
    )
    app.config.from_object(config_class)

    # Duración de la sesión permanente
    app.permanent_session_lifetime = timedelta(
        days=app.config.get('SESSION_LIFETIME_DAYS', 30)
    )

    # ── Extensiones ────────────────────────────────────────────
    db.init_app(app)

    # ── Blueprints ─────────────────────────────────────────────
    from routes_auth import auth_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(iptv_bp)
    app.register_blueprint(xtream_bp)

    # ── Filtros Jinja2 personalizados ──────────────────────────
    @app.template_filter('fromjson')
    def fromjson_filter(value):
        try:
            return json.loads(value) if value else []
        except (ValueError, TypeError):
            return []

    # ── Context processor: inyectar current_user en todas las plantillas ──
    @app.context_processor
    def inject_current_user():
        from models import User
        user_id = session.get('user_id')
        if user_id:
            user = User.query.get(user_id)
            return {'current_user': user}
        return {'current_user': None}

    # ── BD: crear tablas + migraciones seguras ─────────────────
    with app.app_context():
        os.makedirs(
            os.path.join(app.root_path, 'instance'),
            exist_ok=True,
        )
        db.create_all()
        _migrate_db()
        _fix_sqlite_pragmas()
        _ensure_superadmin(app)

    # ── Scheduler (solo si no estamos en testing y AUTO_SCAN=1) ─
    if not app.testing and app.config.get('AUTO_SCAN', 0):
        init_scheduler(app)

    # ── Rutas frontend ─────────────────────────────────────────
    @app.route('/')
    def index():
        from flask import session as _session, redirect as _redirect, url_for as _url_for
        if not _session.get('user_id'):
            return _redirect(_url_for('auth.login'))
        return render_template('index.html')

    @app.route('/player')
    def player():
        url       = request.args.get('url',       '').strip()
        title     = request.args.get('title',     '').strip()
        raw_urls  = request.args.get('live_urls', '').strip()
        drm_type  = request.args.get('drm_type',  '').strip()
        drm_key_id = request.args.get('drm_key_id', '').strip()
        drm_key   = request.args.get('drm_key',   '').strip()
        try:
            live_urls = json.loads(raw_urls) if raw_urls else []
            if not isinstance(live_urls, list):
                live_urls = []
            live_urls = [u for u in live_urls if isinstance(u, str) and u.startswith(('http://', 'https://', 'rtmp://', 'rtsp://'))]
        except (ValueError, TypeError):
            live_urls = []
        drm_config = None
        if drm_type == 'clearkey' and drm_key_id and drm_key:
            drm_config = {'type': 'clearkey', 'keyId': drm_key_id, 'key': drm_key}
        return render_template('player.html', url=url, title=title, live_urls=live_urls, drm_config=drm_config)

    @app.route('/manifest.json')
    def manifest():
        return send_from_directory(app.static_folder, 'manifest.json')

    @app.route('/service-worker.js')
    def service_worker():
        return send_from_directory(
            app.static_folder, 'js/service-worker.js',
            mimetype='application/javascript',
        )

    # ── Descarga APK ───────────────────────────────────────────
    @app.route('/app/<path:filename>')
    def serve_apk(filename):
        apk_dir = os.path.join(app.static_folder, 'app')
        return send_from_directory(apk_dir, filename, as_attachment=True)

    @app.route('/lists/<path:filename>')
    def serve_lists(filename):
        lists_dir = os.path.join(os.path.dirname(app.root_path), 'lists')
        return send_from_directory(lists_dir, filename, as_attachment=True)

    @app.route('/instalar')
    def instalar():
        return render_template('instalar.html')

    # ── Errores ────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return {'error': 'No encontrado'}, 404

    @app.errorhandler(500)
    def server_error(e):
        return {'error': 'Error interno del servidor'}, 500

    return app


def _fix_sqlite_pragmas():
    """
    WAL (Write-Ahead Logging) permite lecturas concurrentes mientras se escribe,
    ideal para imports largos en background + peticiones HTTP simultáneas.
    synchronous=NORMAL es seguro con WAL y mucho más rápido que FULL.
    cache_size=-65536 → 64 MB de caché en memoria para queries frecuentes.
    """
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            conn.execute(text('PRAGMA journal_mode=WAL'))
            conn.execute(text('PRAGMA synchronous=NORMAL'))
            conn.execute(text('PRAGMA cache_size=-65536'))
            conn.execute(text('PRAGMA temp_store=MEMORY'))
            conn.commit()
    except Exception:
        pass


def _migrate_db():
    """Agrega columnas nuevas a tablas existentes sin perder datos (SQLite safe)."""
    from sqlalchemy import text
    stmts = [
        # Columnas pre-existentes
        'ALTER TABLE listas ADD COLUMN incluir_live         BOOLEAN NOT NULL DEFAULT 0',
        'ALTER TABLE listas ADD COLUMN usar_proxy           BOOLEAN NOT NULL DEFAULT 0',
        'ALTER TABLE listas ADD COLUMN grupos_seleccionados TEXT',
        'ALTER TABLE listas ADD COLUMN grupos_tipos         TEXT',
        # Multi-usuario
        'ALTER TABLE listas ADD COLUMN owner_id    INTEGER REFERENCES users(id)',
        'ALTER TABLE listas ADD COLUMN visibilidad TEXT NOT NULL DEFAULT \'global\'',
        'ALTER TABLE fuentes_rss ADD COLUMN owner_id    INTEGER REFERENCES users(id)',
        'ALTER TABLE fuentes_rss ADD COLUMN visibilidad TEXT NOT NULL DEFAULT \'global\'',
        # Reportes y IPTV — creadas por db.create_all() en BD nueva;
        # en BD existente se crean aquí solo las columnas que falten
        # (las tablas completas las crea db.create_all si no existen)
        'ALTER TABLE iptv_users ADD COLUMN owner_id INTEGER REFERENCES users(id)',
        'ALTER TABLE iptv_users ADD COLUMN grupos_permitidos TEXT',
        'ALTER TABLE users ADD COLUMN iptv_user_limit INTEGER NOT NULL DEFAULT 10',
        'ALTER TABLE iptv_users ADD COLUMN password_plain TEXT',
        # Live channel failover
        'ALTER TABLE contenidos ADD COLUMN live_urls_json TEXT',
        'ALTER TABLE contenidos ADD COLUMN live_active_idx INTEGER NOT NULL DEFAULT 0',
        # Lista predeterminada
        'ALTER TABLE listas ADD COLUMN es_defecto BOOLEAN NOT NULL DEFAULT 0',
        # Telegram bot config (las tablas nuevas las crea db.create_all; estas son por si acaso)
        'ALTER TABLE telegram_config ADD COLUMN daily_digest BOOLEAN NOT NULL DEFAULT 1',
        'ALTER TABLE telegram_config ADD COLUMN digest_hour  INTEGER NOT NULL DEFAULT 8',
        'ALTER TABLE telegram_config ADD COLUMN alert_threshold INTEGER NOT NULL DEFAULT 80',
        # Guardar M3U local + Telegram + live a curado
        'ALTER TABLE listas ADD COLUMN guardar_local    BOOLEAN NOT NULL DEFAULT 1',
        'ALTER TABLE listas ADD COLUMN enviar_telegram  BOOLEAN NOT NULL DEFAULT 1',
        'ALTER TABLE listas ADD COLUMN live_a_curado    BOOLEAN NOT NULL DEFAULT 1',
        # CanalCurado: origen de la lista
        'ALTER TABLE canales_curados ADD COLUMN fuente     TEXT',
        'ALTER TABLE canales_curados ADD COLUMN lista_id   INTEGER REFERENCES listas(id)',
    ]
    with db.engine.connect() as conn:
        for stmt in stmts:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass   # columna ya existe → ignorar


def _ensure_superadmin(app):
    """
    Si no existe ningún usuario en la BD, crea el superadmin con las
    credenciales definidas en ADMIN_USER / ADMIN_PASSWORD.
    """
    from models import User
    if User.query.count() == 0:
        admin = User(
            username=app.config.get('ADMIN_USER', 'admin'),
            role='superadmin',
            invite_limit=9999,
        )
        admin.set_password(app.config.get('ADMIN_PASSWORD', 'admin1234'))
        db.session.add(admin)
        db.session.commit()


# ── Punto de entrada para desarrollo local ─────────────────────
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=80)
