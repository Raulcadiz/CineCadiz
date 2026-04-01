"""
Panel de administración — /admin/
"""
import json
import re as _re
import threading
import time as _time
import uuid
from datetime import datetime
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash, jsonify, current_app,
)

import random
import requests as _requests   # alias para no colisionar con el parámetro 'request' de Flask

from models import db, Lista, FuenteRSS, Contenido, Proxy, User, InviteToken, Ticket, UserSession, ChannelReport, IptvUser, IptvSession, WatchHistory, TelegramConfig, CanalCurado
from m3u_parser import (
    fetch_and_parse, parse_and_filter,
    fetch_groups_preview, get_groups_preview, decode_m3u_bytes,
)
from link_checker import scan_dead_links, purge_dead_links, server_health
from rss_importer import import_rss_source, DEFAULT_RSS_SOURCES

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ── Estado del scan en memoria ─────────────────────────────────
_scan_state: dict = {'running': False, 'last_result': None}

# ── Almacén temporal para uploads en el flujo de previsualización ──
# Clave: temp_id (UUID), valor: raw_bytes del archivo M3U
_temp_uploads: dict[str, bytes] = {}


# ── Auth ───────────────────────────────────────────────────────

def _get_panel_user():
    """Devuelve el User activo de la sesión actual (premium o superadmin), o None."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    u = User.query.get(user_id)
    return u if (u and u.activo and u.is_premium) else None


def login_required(f):
    """Requiere que el usuario sea premium o superadmin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _get_panel_user():
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated


def superadmin_required(f):
    """Requiere rol superadmin (para páginas HTML — devuelve redirect)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        u = _get_panel_user()
        if not u or not u.is_superadmin:
            flash('Acceso restringido al superadmin.', 'danger')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated


def superadmin_api_required(f):
    """Requiere rol superadmin (para rutas /api/ — devuelve JSON en lugar de redirect)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        u = _get_panel_user()
        if not u or not u.is_superadmin:
            from flask import jsonify as _jsonify
            return _jsonify({'ok': False, 'msg': 'Acceso restringido al superadmin.'}), 403
        return f(*args, **kwargs)
    return decorated


@admin_bp.get('/login')
def login():
    if _get_panel_user():
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/login.html')


@admin_bp.post('/login')
def login_post():
    username = request.form.get('usuario', '').strip()
    pwd      = request.form.get('password', '')
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(pwd) or not user.activo:
        flash('Usuario o contraseña incorrectos', 'danger')
        return redirect(url_for('admin.login'))
    if not user.is_premium:
        flash('No tienes acceso al panel de administración.', 'danger')
        return redirect(url_for('admin.login'))

    from routes_auth import _refresh_user_session
    session.clear()
    session['user_id']   = user.id
    session['user_role'] = user.role
    session['username']  = user.username
    session.permanent = True
    _refresh_user_session(user)
    return redirect(url_for('admin.dashboard'))


@admin_bp.get('/logout')
@login_required
def logout():
    from routes_auth import _refresh_user_session
    sk = session.get('session_key')
    if sk:
        us = UserSession.query.filter_by(session_key=sk).first()
        if us:
            db.session.delete(us)
            db.session.commit()
    session.clear()
    return redirect(url_for('admin.login'))


# ── Dashboard ──────────────────────────────────────────────────

@admin_bp.get('/')
@login_required
def dashboard():
    panel_user = _get_panel_user()

    if panel_user.is_superadmin:
        stats = {
            'peliculas':   Contenido.query.filter_by(tipo='pelicula', activo=True).count(),
            'series':      Contenido.query.filter_by(tipo='serie', activo=True).count(),
            'live':        Contenido.query.filter_by(tipo='live', activo=True).count(),
            'inactivos':   Contenido.query.filter_by(activo=False).count(),
            'listas_m3u':  Lista.query.count(),
            'fuentes_rss': FuenteRSS.query.count(),
            'total_m3u':   Contenido.query.filter_by(fuente='m3u', activo=True).count(),
            'total_rss':   Contenido.query.filter_by(fuente='rss', activo=True).count(),
            'usuarios':    User.query.count(),
            'usuarios_normales': User.query.filter_by(role='user').count(),
            'usuarios_premium':  User.query.filter_by(role='premium').count(),
            'tickets_pendientes': Ticket.query.filter_by(estado='pendiente').count(),
        }
        listas  = Lista.query.order_by(Lista.fecha_creacion.desc()).limit(6).all()
        fuentes = FuenteRSS.query.order_by(FuenteRSS.fecha_creacion.desc()).limit(6).all()
    else:
        # Usuario premium: solo sus listas privadas
        mis_ids = [l.id for l in panel_user.listas]
        q_cont  = Contenido.query.filter(
            Contenido.lista_id.in_(mis_ids), Contenido.activo == True
        ) if mis_ids else Contenido.query.filter(False)
        stats = {
            'peliculas':   q_cont.filter_by(tipo='pelicula').count(),
            'series':      q_cont.filter_by(tipo='serie').count(),
            'live':        q_cont.filter_by(tipo='live').count(),
            'inactivos':   0,
            'listas_m3u':  panel_user.listas.count(),
            'fuentes_rss': panel_user.fuentes_rss.count(),
            'total_m3u':   q_cont.count(),
            'total_rss':   0,
        }
        listas  = panel_user.listas.order_by(Lista.fecha_creacion.desc()).limit(6).all()
        fuentes = panel_user.fuentes_rss.order_by(FuenteRSS.fecha_creacion.desc()).limit(6).all()

    # Usuarios en línea (activos en los últimos N minutos)
    from datetime import timedelta
    timeout = current_app.config.get('ONLINE_TIMEOUT_MINUTES', 5)
    cutoff  = datetime.utcnow() - timedelta(minutes=timeout)
    online_count = UserSession.query.filter(UserSession.last_seen >= cutoff).count()

    # Todas las listas M3U (para el selector del escaneo)
    all_listas = Lista.query.order_by(Lista.nombre).all() if panel_user.is_superadmin else []

    return render_template(
        'admin/dashboard.html',
        stats=stats, listas=listas, fuentes=fuentes,
        all_listas=all_listas,
        scan_state=_scan_state, online_count=online_count,
        panel_user=panel_user,
    )


# ── Reclasificación de contenido ──────────────────────────────

@admin_bp.post('/reclassify')
@login_required
def reclassify_content():
    """
    Re-clasifica el contenido M3U existente usando las reglas del parser actualizado.
    Corrige items mal clasificados (ej: series guardadas como 'live').
    """
    import re as _re_adm
    from m3u_parser import _normalize, _SERIE_GROUPS, _PELICULA_GROUPS, _DEFAULT_VOD_CONFIRMED

    items = Contenido.query.filter_by(fuente='m3u', activo=True).all()
    updated = 0

    for item in items:
        titulo = item.titulo or ''
        group  = _normalize(item.group_title or '')
        nuevo_tipo = None

        # 1. S01E01 en el título → serie (regex ampliado con punto/guion)
        if _re_adm.search(r'[Ss]\d{1,2}\s*[._-]?\s*[Ee]\d{1,3}', titulo):
            nuevo_tipo = 'serie'

        # 2. Temporada o episodio ya detectado en la BD
        elif item.temporada or item.episodio:
            nuevo_tipo = 'serie'

        # 3. Group-title → serie
        elif any(kw in group for kw in _SERIE_GROUPS):
            nuevo_tipo = 'serie'

        # 4. Group-title → pelicula
        elif any(kw in group for kw in _PELICULA_GROUPS):
            nuevo_tipo = 'pelicula'

        # 5. Group-title VOD confirmado
        elif any(_normalize(kw) in group for kw in _DEFAULT_VOD_CONFIRMED):
            if item.tipo == 'live':
                nuevo_tipo = 'pelicula'

        if nuevo_tipo and nuevo_tipo != item.tipo:
            item.tipo = nuevo_tipo
            updated += 1

    if updated:
        db.session.commit()

    return jsonify({
        'ok': True,
        'updated': updated,
        'total': len(items),
        'msg': f'{updated} de {len(items)} items reclasificados correctamente.',
    })


# ── Gestión de listas M3U ──────────────────────────────────────

@admin_bp.get('/listas')
@login_required
def listas():
    panel_user = _get_panel_user()
    if panel_user.is_superadmin:
        all_listas = Lista.query.order_by(Lista.fecha_creacion.desc()).all()
    else:
        all_listas = panel_user.listas.order_by(Lista.fecha_creacion.desc()).all()
    return render_template('admin/lists.html', listas=all_listas, panel_user=panel_user)


@admin_bp.post('/listas/agregar')
@login_required
def agregar_lista():
    nombre = request.form.get('nombre', '').strip()
    url = request.form.get('url', '').strip()
    filtrar    = 'filtrar_español' in request.form
    usar_proxy = 'usar_proxy'      in request.form

    if not nombre or not url:
        flash('Nombre y URL son obligatorios', 'danger')
        return redirect(url_for('admin.listas'))
    if not url.startswith('http'):
        flash('La URL debe comenzar con http:// o https://', 'danger')
        return redirect(url_for('admin.listas'))

    # grupos_seleccionados: JSON list de group-titles enviado por el paso de preview
    grupos_json = request.form.get('grupos_seleccionados', '').strip() or None
    if grupos_json:
        try:
            parsed = json.loads(grupos_json)
            grupos_json = json.dumps(parsed) if isinstance(parsed, list) and parsed else None
        except (ValueError, TypeError):
            grupos_json = None

    # grupos_tipos: JSON dict {group_title: tipo} con la clasificación manual del admin
    grupos_tipos_json = request.form.get('grupos_tipos', '').strip() or None
    if grupos_tipos_json:
        try:
            parsed_t = json.loads(grupos_tipos_json)
            grupos_tipos_json = json.dumps(parsed_t) if isinstance(parsed_t, dict) and parsed_t else None
        except (ValueError, TypeError):
            grupos_tipos_json = None

    panel_user = _get_panel_user()
    lista = Lista(
        nombre=nombre,
        url=url,
        filtrar_español=filtrar,
        incluir_live=True,
        usar_proxy=usar_proxy,
        grupos_seleccionados=grupos_json,
        grupos_tipos=grupos_tipos_json,
        owner_id=None if panel_user.is_superadmin else panel_user.id,
        visibilidad='global' if panel_user.is_superadmin else 'private',
    )
    db.session.add(lista)
    db.session.commit()
    _import_lista_async(current_app._get_current_object(), lista.id)
    flash(f'Lista "{nombre}" agregada. Importando en segundo plano...', 'success')
    return redirect(url_for('admin.listas'))


@admin_bp.post('/listas/<int:lista_id>/refresh')
@login_required
def refresh_lista(lista_id):
    lista = Lista.query.get_or_404(lista_id)
    _import_lista_async(current_app._get_current_object(), lista.id)
    flash(f'Re-importando "{lista.nombre}" en segundo plano...', 'info')
    return redirect(url_for('admin.listas'))


@admin_bp.post('/listas/<int:lista_id>/eliminar')
@login_required
def eliminar_lista(lista_id):
    lista = Lista.query.get_or_404(lista_id)
    panel_user = _get_panel_user()
    # Los premium solo pueden borrar sus propias listas
    if not panel_user.is_superadmin and lista.owner_id != panel_user.id:
        flash('No tienes permiso para eliminar esta lista.', 'danger')
        return redirect(url_for('admin.listas'))
    nombre = lista.nombre
    contenido_ids = [c.id for c in lista.contenidos]
    if contenido_ids:
        for i in range(0, len(contenido_ids), 900):
            chunk = contenido_ids[i:i + 900]
            # Limpiar todas las tablas con FK NOT NULL a contenidos antes de borrar
            WatchHistory.query.filter(WatchHistory.contenido_id.in_(chunk)).delete(synchronize_session=False)
            ChannelReport.query.filter(ChannelReport.contenido_id.in_(chunk)).delete(synchronize_session=False)
    db.session.expire_all()
    db.session.delete(lista)
    db.session.commit()
    flash(f'Lista "{nombre}" y todo su contenido eliminados.', 'success')
    return redirect(url_for('admin.listas'))


@admin_bp.post('/listas/<int:lista_id>/editar-url')
@login_required
def editar_url_lista(lista_id):
    """Cambia la URL de una lista existente y la re-importa."""
    lista = Lista.query.get_or_404(lista_id)
    panel_user = _get_panel_user()
    if not panel_user.is_superadmin and lista.owner_id != panel_user.id:
        return jsonify({'error': 'Sin permiso'}), 403

    nueva_url = (request.form.get('url') or request.get_json(silent=True, force=True) or {}).get('url', '') if request.is_json else request.form.get('url', '')
    if isinstance(nueva_url, dict):
        nueva_url = nueva_url.get('url', '')
    nueva_url = str(nueva_url).strip()

    if not nueva_url or not nueva_url.lower().startswith('http'):
        flash('URL inválida.', 'danger')
        return redirect(url_for('admin.listas'))

    lista.url   = nueva_url
    lista.error = None
    lista.ultima_actualizacion = None   # fuerza estado "Pendiente"
    db.session.commit()

    _import_lista_async(current_app._get_current_object(), lista.id)
    flash(f'URL de "{lista.nombre}" actualizada. Re-importando en segundo plano…', 'success')
    return redirect(url_for('admin.listas'))


@admin_bp.post('/listas/<int:lista_id>/toggle')
@login_required
def toggle_lista(lista_id):
    lista = Lista.query.get_or_404(lista_id)
    lista.activa = not lista.activa
    db.session.commit()
    flash(f'Lista "{lista.nombre}" {"activada" if lista.activa else "desactivada"}.', 'info')
    return redirect(url_for('admin.listas'))


@admin_bp.post('/listas/<int:lista_id>/set-default')
@login_required
def set_default_lista(lista_id):
    """
    Marca una lista como predeterminada (solo puede haber una).
    Si se llama sobre la lista ya marcada, la desmarca (toggle).
    La lista predeterminada se pre-selecciona en la web, APK y IPTV.
    """
    lista = Lista.query.get_or_404(lista_id)
    if lista.es_defecto:
        # Toggle off: quitar el default
        lista.es_defecto = False
        db.session.commit()
        return jsonify({'ok': True, 'es_defecto': False, 'nombre': lista.nombre})
    # Quitar default de cualquier lista anterior
    Lista.query.filter(Lista.es_defecto == True).update({'es_defecto': False})
    lista.es_defecto = True
    db.session.commit()
    return jsonify({'ok': True, 'es_defecto': True, 'nombre': lista.nombre})


# ── Gestión de fuentes RSS ──────────────────────────────────────

@admin_bp.get('/rss')
@login_required
def rss():
    panel_user = _get_panel_user()
    if panel_user.is_superadmin:
        fuentes = FuenteRSS.query.order_by(FuenteRSS.fecha_creacion.desc()).all()
    else:
        fuentes = panel_user.fuentes_rss.order_by(FuenteRSS.fecha_creacion.desc()).all()
    return render_template('admin/rss.html', fuentes=fuentes, panel_user=panel_user)


@admin_bp.post('/rss/agregar')
@login_required
def agregar_rss():
    nombre = request.form.get('nombre', '').strip()
    url = request.form.get('url', '').strip()
    if not nombre or not url:
        flash('Nombre y URL son obligatorios', 'danger')
        return redirect(url_for('admin.rss'))
    fuente = FuenteRSS(nombre=nombre, url=url)
    db.session.add(fuente)
    db.session.commit()
    import_rss_source(current_app._get_current_object(), fuente.id)
    flash(f'Fuente RSS "{nombre}" agregada. Importando...', 'success')
    return redirect(url_for('admin.rss'))


@admin_bp.post('/rss/<int:fuente_id>/refresh')
@login_required
def refresh_rss(fuente_id):
    fuente = FuenteRSS.query.get_or_404(fuente_id)
    import_rss_source(current_app._get_current_object(), fuente.id)
    flash(f'Re-importando "{fuente.nombre}"...', 'info')
    return redirect(url_for('admin.rss'))


@admin_bp.post('/rss/<int:fuente_id>/eliminar')
@login_required
def eliminar_rss(fuente_id):
    fuente = FuenteRSS.query.get_or_404(fuente_id)
    nombre = fuente.nombre
    db.session.delete(fuente)
    db.session.commit()
    flash(f'Fuente RSS "{nombre}" eliminada.', 'success')
    return redirect(url_for('admin.rss'))


@admin_bp.post('/rss/importar-defaults')
@login_required
def importar_defaults_rss():
    """Importa las fuentes RSS por defecto de cinemacity.cc si no existen."""
    app = current_app._get_current_object()
    agregadas = 0
    for src in DEFAULT_RSS_SOURCES:
        existe = FuenteRSS.query.filter_by(url=src['url']).first()
        if not existe:
            f = FuenteRSS(nombre=src['nombre'], url=src['url'])
            db.session.add(f)
            db.session.commit()
            import_rss_source(app, f.id)
            agregadas += 1
    if agregadas:
        flash(f'{agregadas} fuentes RSS de cinemacity.cc agregadas e importando...', 'success')
    else:
        flash('Las fuentes de cinemacity.cc ya estaban agregadas.', 'info')
    return redirect(url_for('admin.rss'))


# ── Escaneo de links M3U ───────────────────────────────────────

@admin_bp.post('/scan')
@login_required
def manual_scan():
    """Escaneo multi-hilo de links caídos. Solo actúa sobre fuente='m3u'."""
    if _scan_state['running']:
        flash('Ya hay un escaneo en curso. Espera a que termine.', 'warning')
        return redirect(url_for('admin.dashboard'))

    app = current_app._get_current_object()
    batch   = request.form.get('batch', app.config.get('SCAN_BATCH_SIZE', 500), type=int)
    workers = request.form.get('workers', 40, type=int)
    workers = max(5, min(workers, 80))   # entre 5 y 80
    lista_id = request.form.get('lista_id', 0, type=int) or None

    lista_nombre = None
    if lista_id:
        l = Lista.query.get(lista_id)
        lista_nombre = l.nombre if l else None

    def run():
        _scan_state['running'] = True
        try:
            result = scan_dead_links(app, batch_size=batch, max_workers=workers,
                                     lista_id=lista_id)
            if lista_nombre:
                result['lista_nombre'] = lista_nombre
            _scan_state['last_result'] = result
        except Exception as e:
            _scan_state['last_result'] = {'error': str(e)}
        finally:
            _scan_state['running'] = False

    t = threading.Thread(target=run, daemon=True)
    t.start()
    flash(
        f'Escaneo iniciado: {batch} links con {workers} hilos en paralelo. '
        f'Refresca en unos minutos para ver resultados.',
        'info'
    )
    return redirect(url_for('admin.dashboard'))


@admin_bp.get('/api/scan-status')
@login_required
def scan_status():
    return jsonify({
        'running': _scan_state['running'],
        'last_result': _scan_state['last_result'],
    })


@admin_bp.post('/purge-dead')
@login_required
def admin_purge_dead():
    """Elimina permanentemente el contenido M3U inactivo más de N días."""
    days = request.form.get('days', 7, type=int)
    days = max(1, min(days, 365))
    app = current_app._get_current_object()
    result = purge_dead_links(app, days=days)
    flash(
        f'Purge completado: {result["deleted"]} items eliminados '
        f'(inactivos >{days} días).',
        'success' if result['deleted'] > 0 else 'info',
    )
    return redirect(url_for('admin.dashboard'))


@admin_bp.get('/api/server-health')
@login_required
def admin_server_health():
    """JSON con estadísticas de salud por servidor (% streams caídos)."""
    app = current_app._get_current_object()
    data = server_health(app)
    return jsonify(data)


@admin_bp.post('/purge-server')
@login_required
def admin_purge_server():
    """
    Elimina PERMANENTEMENTE todo el contenido caído de un servidor concreto.
    Útil para limpiar servidores con 100% de streams muertos.
    Body JSON o form: { "servidor": "8tb.btv.mx" }
    """
    from models import db, Contenido
    servidor = (request.form.get('servidor') or
                (request.get_json(silent=True) or {}).get('servidor', '')).strip()
    if not servidor:
        return jsonify({'error': 'servidor requerido'}), 400

    with current_app.app_context():
        deleted = (
            Contenido.query
            .filter(
                Contenido.servidor == servidor,
                Contenido.activo == False,
                Contenido.fuente == 'm3u',
            )
            .delete(synchronize_session=False)
        )
        db.session.commit()

    flash(f'Eliminados {deleted} streams caídos del servidor "{servidor}".', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.get('/api/telegram-config')
@login_required
def get_telegram_config():
    """Devuelve la configuración actual del bot Telegram."""
    from models import TelegramConfig
    cfg = TelegramConfig.query.first()
    return jsonify(cfg.to_dict() if cfg else {
        'enabled': False, 'token': '', 'chat_ids': [],
        'alert_threshold': 80, 'daily_digest': True, 'digest_hour': 8,
    })


@admin_bp.post('/api/telegram-config')
@login_required
def save_telegram_config():
    """Guarda la configuración del bot Telegram."""
    import json as _json
    from models import db, TelegramConfig

    data = request.get_json(silent=True) or {}
    cfg = TelegramConfig.query.first()
    if cfg is None:
        cfg = TelegramConfig()
        db.session.add(cfg)

    cfg.enabled         = bool(data.get('enabled', True))
    cfg.token           = data.get('token', '').strip() or None
    cfg.alert_threshold = max(1, min(100, int(data.get('alert_threshold', 80))))
    cfg.daily_digest    = bool(data.get('daily_digest', True))
    cfg.digest_hour     = max(0, min(23, int(data.get('digest_hour', 8))))

    ids = data.get('chat_ids', [])
    if isinstance(ids, str):
        ids = [i.strip() for i in ids.replace(',', '\n').splitlines() if i.strip()]
    cfg.chat_ids_json = _json.dumps([str(i) for i in ids]) if ids else None
    cfg.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True, 'config': cfg.to_dict()})


@admin_bp.post('/api/telegram-test')
@login_required
def test_telegram():
    """Envía un mensaje de prueba al chat_id indicado."""
    from telegram_bot import send_test
    data     = request.get_json(silent=True) or {}
    token    = data.get('token', '').strip()
    chat_id  = str(data.get('chat_id', '')).strip()
    if not token or not chat_id:
        return jsonify({'ok': False, 'msg': 'token y chat_id son obligatorios'}), 400
    ok, msg = send_test(token, chat_id)
    return jsonify({'ok': ok, 'msg': msg})


@admin_bp.post('/rescan-server')
@login_required
def admin_rescan_server():
    """
    Fuerza re-escaneo inmediato de todos los streams de un servidor concreto,
    tanto activos como inactivos (les resetea ultima_verificacion para que
    el siguiente scan automático los re-compruebe primero).
    Body form: { "servidor": "8tb.btv.mx" }
    """
    from models import db, Contenido
    servidor = request.form.get('servidor', '').strip()
    if not servidor:
        flash('Servidor no especificado.', 'danger')
        return redirect(url_for('admin.dashboard'))

    with current_app.app_context():
        updated = (
            Contenido.query
            .filter(Contenido.servidor == servidor)
            .update({'ultima_verificacion': None}, synchronize_session=False)
        )
        db.session.commit()

    flash(
        f'{updated} streams del servidor "{servidor}" marcados para re-escaneo. '
        'El scanner automático los revisará en la próxima ronda.',
        'info',
    )
    return redirect(url_for('admin.dashboard'))


# ── Gestión de contenido ───────────────────────────────────────

@admin_bp.get('/contenido')
@login_required
def contenido():
    page = max(1, request.args.get('page', 1, type=int))
    tipo = request.args.get('tipo', '')
    fuente = request.args.get('fuente', '')
    q = request.args.get('q', '').strip()

    query = Contenido.query
    if tipo in ('pelicula', 'serie'):
        query = query.filter_by(tipo=tipo)
    if fuente in ('m3u', 'rss'):
        query = query.filter_by(fuente=fuente)
    if q:
        query = query.filter(Contenido.titulo.ilike(f'%{q}%'))

    pagination = query.order_by(Contenido.fecha_agregado.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    return render_template('admin/content.html',
                           pagination=pagination, tipo=tipo, fuente=fuente, q=q)


@admin_bp.post('/contenido/<int:item_id>/toggle')
@login_required
def toggle_contenido(item_id):
    item = Contenido.query.get_or_404(item_id)
    item.activo = not item.activo
    db.session.commit()
    return jsonify({'activo': item.activo})


@admin_bp.get('/contenido/<int:item_id>/backup-urls')
@login_required
def get_backup_urls(item_id):
    """Devuelve las URLs de respaldo de un canal live."""
    import json as _j
    item = Contenido.query.get_or_404(item_id)
    try:
        urls = _j.loads(item.live_urls_json) if item.live_urls_json else []
    except (ValueError, TypeError):
        urls = []
    return jsonify({
        'id':        item.id,
        'titulo':    item.titulo,
        'url_stream': item.url_stream,
        'live_urls': urls,
    })


@admin_bp.post('/contenido/<int:item_id>/backup-urls')
@login_required
def set_backup_urls(item_id):
    """
    Guarda la lista de URLs de respaldo para un canal live.
    Body JSON: {"urls": ["http://...", "http://..."]}
    La primera URL de la lista se convierte también en url_stream (URL principal).
    """
    import json as _j
    item = Contenido.query.get_or_404(item_id)
    data = request.get_json(silent=True) or {}
    raw = data.get('urls', [])
    if not isinstance(raw, list):
        return jsonify({'error': 'urls debe ser una lista'}), 400

    # Limpiar y deduplicar manteniendo el orden
    cleaned = []
    seen = set()
    for u in raw:
        u = (u or '').strip()
        if u and u not in seen:
            cleaned.append(u)
            seen.add(u)

    if not cleaned:
        return jsonify({'error': 'Se requiere al menos una URL'}), 400

    item.live_urls_json  = _j.dumps(cleaned)
    item.live_active_idx = 0
    item.url_stream      = cleaned[0]   # la primera es siempre la principal
    db.session.commit()
    return jsonify({'ok': True, 'urls_guardadas': len(cleaned)})


@admin_bp.post('/contenido/cambiar-servidor-live')
@superadmin_required
def cambiar_servidor_live():
    """
    Reemplaza el servidor (host) en todas las URLs de canales live.
    Útil para cambiar de proveedor IPTV sin reimportar toda la lista.
    Body JSON: {"servidor_old": "dplatino.net", "servidor_new": "nuevoserver.com"}
    """
    import json as _j
    data = request.get_json(silent=True) or {}
    old = (data.get('servidor_old') or '').strip()
    new = (data.get('servidor_new') or '').strip()

    if not old or not new:
        return jsonify({'error': 'servidor_old y servidor_new son obligatorios'}), 400
    if old == new:
        return jsonify({'error': 'Los servidores son iguales'}), 400

    # Solo actualizar canales live activos cuya URL contiene el servidor antiguo
    from sqlalchemy import func as _func
    items = (Contenido.query
             .filter(Contenido.tipo == 'live',
                     Contenido.url_stream.ilike(f'%{old}%'))
             .all())

    actualizados = 0
    for item in items:
        if item.url_stream and old in item.url_stream:
            item.url_stream = item.url_stream.replace(old, new)
            actualizados += 1

    db.session.commit()
    return jsonify({'ok': True, 'actualizados': actualizados, 'servidor_old': old, 'servidor_new': new})


# ── API AJAX ───────────────────────────────────────────────────

@admin_bp.get('/api/listas/<int:lista_id>/status')
@login_required
def lista_status(lista_id):
    return jsonify(Lista.query.get_or_404(lista_id).to_dict())


@admin_bp.get('/api/rss/<int:fuente_id>/status')
@login_required
def rss_status(fuente_id):
    return jsonify(FuenteRSS.query.get_or_404(fuente_id).to_dict())


@admin_bp.get('/api/online')
@login_required
def online_users():
    """Devuelve la lista de usuarios activos en los últimos N minutos."""
    from datetime import timedelta
    timeout = current_app.config.get('ONLINE_TIMEOUT_MINUTES', 5)
    cutoff  = datetime.utcnow() - timedelta(minutes=timeout)
    sessions = (
        UserSession.query
        .filter(UserSession.last_seen >= cutoff)
        .order_by(UserSession.last_seen.desc())
        .all()
    )
    result = []
    for s in sessions:
        u = User.query.get(s.user_id)
        result.append({
            'user_id':    s.user_id,
            'username':   u.username if u else '?',
            'role':       u.role if u else '?',
            'ip':         s.ip_address,
            'last_seen':  s.last_seen.isoformat(),
        })
    return jsonify({'online': len(result), 'sessions': result})


# ── Gestión de proxies HTTP ────────────────────────────────

@admin_bp.get('/proxies')
@login_required
def proxies():
    all_proxies = Proxy.query.order_by(Proxy.fecha_creacion.desc()).all()
    return render_template('admin/proxies.html', proxies=all_proxies)


@admin_bp.post('/proxies/agregar')
@login_required
def agregar_proxy():
    # Acepta textarea con múltiples proxies (uno por línea) o campo 'url' simple
    raw = request.form.get('urls', '') or request.form.get('url', '')
    lineas = [l.strip() for l in raw.splitlines() if l.strip()]
    if not lineas:
        flash('Introduce al menos una dirección de proxy.', 'danger')
        return redirect(url_for('admin.proxies'))

    agregados, duplicados, invalidos = 0, 0, 0
    for linea in lineas:
        # Quitar esquema si el usuario lo puso
        url = linea.replace('http://', '').replace('https://', '').rstrip('/')
        # Validar formato host:puerto básico
        if not url or ':' not in url:
            invalidos += 1
            continue
        if Proxy.query.filter_by(url=url).first():
            duplicados += 1
            continue
        db.session.add(Proxy(url=url))
        agregados += 1

    db.session.commit()
    msgs = []
    if agregados:   msgs.append(f'{agregados} proxy(s) agregado(s)')
    if duplicados:  msgs.append(f'{duplicados} ya existían')
    if invalidos:   msgs.append(f'{invalidos} inválidos (formato esperado host:puerto)')
    flash('. '.join(msgs) + '.', 'success' if agregados else 'warning')
    return redirect(url_for('admin.proxies'))


@admin_bp.get('/proxies/<int:proxy_id>/test')
@login_required
def test_proxy(proxy_id):
    """Comprueba si el proxy está vivo. Devuelve JSON {ok, ip?, error?}."""
    proxy = Proxy.query.get_or_404(proxy_id)
    req_proxies = {
        'http':  f'http://{proxy.url}',
        'https': f'http://{proxy.url}',
    }
    # Usar varios endpoints de fallback para obtener la IP saliente
    _TEST_URLS = [
        ('http://api.ipify.org?format=json', lambda r: r.json().get('ip', '?')),
        ('http://api64.ipify.org?format=json', lambda r: r.json().get('ip', '?')),
        ('http://checkip.amazonaws.com',      lambda r: r.text.strip()),
    ]
    last_err = 'Sin respuesta'
    for test_url, extract_ip in _TEST_URLS:
        try:
            resp = _requests.get(
                test_url,
                proxies=req_proxies,
                timeout=8,
                headers={'User-Agent': 'Mozilla/5.0'},
            )
            ip = extract_ip(resp)
            return jsonify({'ok': True, 'ip': ip})
        except Exception as e:
            msg = str(e)
            if 'Connection refused' in msg:
                last_err = 'Conexión rechazada — proxy caído'
            elif 'timed out' in msg.lower() or 'timeout' in msg.lower():
                last_err = 'Timeout — proxy no responde'
            elif 'Failed to establish' in msg or 'Max retries' in msg:
                last_err = 'No se pudo conectar al proxy'
            elif '407' in msg:
                last_err = 'Proxy requiere autenticación (407)'
            else:
                last_err = msg[:100]
    return jsonify({'ok': False, 'error': last_err})


@admin_bp.post('/proxies/<int:proxy_id>/toggle')
@login_required
def toggle_proxy(proxy_id):
    proxy = Proxy.query.get_or_404(proxy_id)
    proxy.activo = not proxy.activo
    db.session.commit()
    flash(f'Proxy {proxy.url} {"activado" if proxy.activo else "desactivado"}.', 'info')
    return redirect(url_for('admin.proxies'))


@admin_bp.post('/proxies/<int:proxy_id>/eliminar')
@login_required
def eliminar_proxy(proxy_id):
    proxy = Proxy.query.get_or_404(proxy_id)
    url = proxy.url
    db.session.delete(proxy)
    db.session.commit()
    flash(f'Proxy {url} eliminado.', 'success')
    return redirect(url_for('admin.proxies'))


# ── Subida directa de archivo M3U ──────────────────────────────

@admin_bp.post('/listas/subir')
@login_required
def subir_lista():
    """Importa un archivo .m3u subido por el admin (bypass de bloqueo IP)."""
    nombre   = request.form.get('nombre', '').strip()
    filtrar  = 'filtrar_español' in request.form
    temp_id  = request.form.get('temp_id', '').strip()

    if not nombre:
        flash('El nombre es obligatorio.', 'danger')
        return redirect(url_for('admin.listas'))

    # Obtener bytes: primero desde el almacén temporal (flujo 2-pasos), luego desde el archivo
    raw_bytes = None
    if temp_id and temp_id in _temp_uploads:
        raw_bytes = _temp_uploads.pop(temp_id)
    else:
        archivo = request.files.get('archivo')
        if not archivo or not archivo.filename:
            flash('Selecciona un archivo .m3u o .m3u8.', 'danger')
            return redirect(url_for('admin.listas'))
        try:
            raw_bytes = archivo.read()
        except Exception as e:
            flash(f'Error al leer el archivo: {e}', 'danger')
            return redirect(url_for('admin.listas'))

    if not raw_bytes:
        flash('El archivo está vacío.', 'danger')
        return redirect(url_for('admin.listas'))

    grupos_json = request.form.get('grupos_seleccionados', '').strip() or None
    if grupos_json:
        try:
            parsed = json.loads(grupos_json)
            grupos_json = json.dumps(parsed) if isinstance(parsed, list) and parsed else None
        except (ValueError, TypeError):
            grupos_json = None

    grupos_tipos_json = request.form.get('grupos_tipos', '').strip() or None
    if grupos_tipos_json:
        try:
            parsed_t = json.loads(grupos_tipos_json)
            grupos_tipos_json = json.dumps(parsed_t) if isinstance(parsed_t, dict) and parsed_t else None
        except (ValueError, TypeError):
            grupos_tipos_json = None

    lista = Lista(
        nombre=nombre,
        url='[archivo subido]',
        filtrar_español=filtrar,
        incluir_live=True,
        usar_proxy=False,
        grupos_seleccionados=grupos_json,
        grupos_tipos=grupos_tipos_json,
    )
    db.session.add(lista)
    db.session.commit()   # commit ANTES de lanzar el hilo para que el hilo vea la fila

    app = current_app._get_current_object()
    t = threading.Thread(
        target=_import_from_bytes, args=(app, lista.id, raw_bytes),
        daemon=True,
    )
    t.start()
    flash(
        f'Lista "{nombre}" creada. Procesando archivo ({len(raw_bytes)//1024} KB)…',
        'info',
    )
    return redirect(url_for('admin.listas'))


@admin_bp.post('/listas/<int:lista_id>/resubir')
@login_required
def resubir_lista(lista_id):
    """Actualiza el contenido de una lista subida con un nuevo archivo."""
    lista   = Lista.query.get_or_404(lista_id)
    archivo = request.files.get('archivo')

    if not archivo or not archivo.filename:
        flash('Selecciona un archivo .m3u o .m3u8.', 'danger')
        return redirect(url_for('admin.listas'))

    try:
        raw_bytes = archivo.read()
    except Exception as e:
        flash(f'Error al leer el archivo: {e}', 'danger')
        return redirect(url_for('admin.listas'))

    if not raw_bytes:
        flash('El archivo está vacío.', 'danger')
        return redirect(url_for('admin.listas'))

    # Borrar watch_history de los contenidos de esta lista antes de la eliminación en bloque
    old_ids = [r[0] for r in db.session.query(Contenido.id).filter_by(lista_id=lista_id).all()]
    if old_ids:
        for i in range(0, len(old_ids), 900):
            chunk = old_ids[i:i + 900]
            WatchHistory.query.filter(WatchHistory.contenido_id.in_(chunk)).delete(synchronize_session=False)
    # Borrar contenido antiguo de esta lista antes de re-importar
    Contenido.query.filter_by(lista_id=lista_id).delete()
    lista.ultima_actualizacion = None
    lista.error = None
    db.session.commit()   # commit ANTES de lanzar el hilo

    app = current_app._get_current_object()
    t = threading.Thread(
        target=_import_from_bytes, args=(app, lista_id, raw_bytes),
        daemon=True,
    )
    t.start()

    flash(f'Re-importando "{lista.nombre}" desde nuevo archivo…', 'info')
    return redirect(url_for('admin.listas'))


# ── Previsualización de grupos M3U ─────────────────────────────

@admin_bp.post('/listas/preview-url')
@login_required
def preview_url_grupos():
    """Descarga la M3U y devuelve los grupos únicos para que el admin seleccione."""
    url = request.form.get('url', '').strip()
    usar_proxy = 'usar_proxy' in request.form

    if not url or not url.startswith('http'):
        return jsonify({'ok': False, 'error': 'URL inválida'}), 400

    proxy_url = None
    if usar_proxy:
        active_proxies = Proxy.query.filter_by(activo=True).all()
        if active_proxies:
            proxy_url = random.choice(active_proxies).url

    groups, error = fetch_groups_preview(url, current_app.config, proxy=proxy_url)
    if error:
        return jsonify({'ok': False, 'error': error}), 400

    return jsonify({'ok': True, 'groups': groups})


@admin_bp.post('/listas/preview-file')
@login_required
def preview_file_grupos():
    """Lee el archivo M3U subido y devuelve los grupos únicos + un temp_id para el import."""
    archivo = request.files.get('archivo')
    if not archivo or not archivo.filename:
        return jsonify({'ok': False, 'error': 'No se recibió archivo'}), 400

    try:
        raw_bytes = archivo.read()
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

    if not raw_bytes:
        return jsonify({'ok': False, 'error': 'El archivo está vacío'}), 400

    content = decode_m3u_bytes(raw_bytes)
    groups = get_groups_preview(content)

    temp_id = str(uuid.uuid4())
    _temp_uploads[temp_id] = raw_bytes

    return jsonify({
        'ok': True,
        'groups': groups,
        'temp_id': temp_id,
        'size_kb': len(raw_bytes) // 1024,
    })


# ── Edición de grupos de una lista existente ───────────────────

@admin_bp.get('/listas/<int:lista_id>/grupos')
@login_required
def lista_grupos_preview(lista_id):
    """Devuelve los grupos de una lista ya importada con su selección actual marcada."""
    lista = Lista.query.get_or_404(lista_id)
    panel_user = _get_panel_user()
    if not panel_user.is_superadmin and lista.owner_id != panel_user.id:
        return jsonify({'ok': False, 'error': 'Sin permiso'}), 403

    # Grupos actuales de la BD
    rows = db.session.query(
        Contenido.group_title
    ).filter(
        Contenido.lista_id == lista_id,
        Contenido.group_title != None,
        Contenido.group_title != '',
    ).distinct().all()
    all_groups = sorted(set(r[0] for r in rows if r[0]))

    seleccionados = set()
    if lista.grupos_seleccionados:
        try:
            seleccionados = set(json.loads(lista.grupos_seleccionados))
        except (ValueError, TypeError):
            pass

    tipos_map = {}
    if lista.grupos_tipos:
        try:
            tipos_map = json.loads(lista.grupos_tipos)
        except (ValueError, TypeError):
            pass

    # Contar items por grupo
    count_rows = db.session.query(
        Contenido.group_title, db.func.count(Contenido.id)
    ).filter(
        Contenido.lista_id == lista_id,
        Contenido.group_title != None,
        Contenido.group_title != '',
    ).group_by(Contenido.group_title).all()
    counts = {r[0]: r[1] for r in count_rows}

    groups = []
    for g in all_groups:
        # Si hay selección guardada, marcar solo los seleccionados; si no, marcar todos
        checked = g in seleccionados if seleccionados else True
        tipo = tipos_map.get(g, 'otro')
        groups.append({'name': g, 'count': counts.get(g, 0), 'tipo': tipo, 'checked': checked})

    return jsonify({'ok': True, 'groups': groups, 'lista_id': lista_id, 'nombre': lista.nombre})


@admin_bp.post('/listas/<int:lista_id>/edit-grupos')
@login_required
def lista_edit_grupos(lista_id):
    """Guarda la nueva selección de grupos y re-importa la lista."""
    lista = Lista.query.get_or_404(lista_id)
    panel_user = _get_panel_user()
    if not panel_user.is_superadmin and lista.owner_id != panel_user.id:
        flash('No tienes permiso para editar esta lista.', 'danger')
        return redirect(url_for('admin.listas'))

    grupos_json = request.form.get('grupos_seleccionados', '').strip() or None
    if grupos_json:
        try:
            parsed = json.loads(grupos_json)
            grupos_json = json.dumps(parsed) if isinstance(parsed, list) and parsed else None
        except (ValueError, TypeError):
            grupos_json = None

    grupos_tipos_json = request.form.get('grupos_tipos', '').strip() or None
    if grupos_tipos_json:
        try:
            parsed_t = json.loads(grupos_tipos_json)
            grupos_tipos_json = json.dumps(parsed_t) if isinstance(parsed_t, dict) and parsed_t else None
        except (ValueError, TypeError):
            grupos_tipos_json = None

    lista.grupos_seleccionados = grupos_json
    lista.grupos_tipos = grupos_tipos_json
    lista.ultima_actualizacion = None
    lista.error = None

    # Limpiar contenido actual y re-importar con la nueva selección
    old_ids = [r[0] for r in db.session.query(Contenido.id).filter_by(lista_id=lista_id).all()]
    if old_ids:
        for i in range(0, len(old_ids), 900):
            chunk = old_ids[i:i + 900]
            WatchHistory.query.filter(WatchHistory.contenido_id.in_(chunk)).delete(synchronize_session=False)
    Contenido.query.filter_by(lista_id=lista_id).delete()
    db.session.commit()

    _import_lista_async(current_app._get_current_object(), lista.id)
    flash(f'Selección de grupos actualizada para "{lista.nombre}". Re-importando...', 'success')
    return redirect(url_for('admin.listas'))


# ── Importador M3U (interno) ───────────────────────────────────

_BULK_CHUNK = 2000   # filas por INSERT masivo

# Marcadores de calidad/idioma/formato que se eliminan al normalizar el título
# para deduplicar variantes del mismo film ("Bambi 4K", "Bambi VOSE", "Bambi Castellano")
_TITLE_NOISE_RE = _re.compile(
    r'\b(?:vose?i?|vos|vo\b|subs?|sub[-.]?titulad[ao]s?|'
    r'doblad[ao]|cast(?:ellano)?|español|espanol|english|latino|'
    r'fran[cç]ais|french|arabic|arabic|german|deutsch|'
    r'4k|uhd|2160p|fhd|1080p|hd|720p|sd|480p|'
    r'cam(?:rip)?|\bts\b|web[-.]?dl|blu[-.]?ray|bdrip|dvdrip|hdtv|'
    r'hevc|x\.?264|x\.?265|h\.?264|h\.?265|avc|xvid|'
    r'remux|repack|proper)\b',
    _re.IGNORECASE,
)


def _title_key(titulo: str) -> str:
    """
    Genera una clave normalizada para deduplicar películas.
    Elimina marcadores de calidad/idioma/formato, acentos y puntuación.
    "Bambi VOSE", "Bambi 4K", "Bambi Castellano" → todos dan "bambi".
    Solo se usa para tipo='pelicula'; series y live NO se deducan por título.
    """
    if not titulo:
        return ''
    t = titulo.lower()
    t = _TITLE_NOISE_RE.sub(' ', t)                       # quitar ruido
    t = _re.sub(r'[\(\[\{]\s*\d{4}\s*[\)\]\}]', ' ', t)  # (2024), [2024]
    t = _re.sub(r'\s*\d{4}\s*$', '', t)                   # año al final sin paréntesis
    for src, dst in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ü','u'),('ñ','n')]:
        t = t.replace(src, dst)
    t = _re.sub(r'[^a-z0-9\s]', '', t)
    return ' '.join(t.split())


def _do_bulk_insert(items: list, existing_hashes: set, lista_id: int, conflict_ignore: bool = False) -> tuple[int, int]:
    """
    Construye dicts planos y los inserta en bulk usando SQL Core.
    Mucho más rápido que ORM add() para listas grandes (12k+ items pasan
    de ~5 min a <15 s en SQLite/Windows).

    Para películas deduplica además por título normalizado: si el M3U tiene
    "Bambi 4K", "Bambi VOSE" y "Bambi Castellano" solo inserta la mejor
    (preferencia: tiene imagen > tiene año > primera encontrada).
    Series y canales live NO se deducan por título.

    Devuelve (nuevos_insertados, duplicados_descartados_del_m3u).
    """
    now = datetime.utcnow()

    # ── Fase 1: elegir la mejor variante por título (películas) ────────
    best_pelicula: dict[str, dict] = {}   # title_key → mejor item
    other_items:   list[dict]      = []   # series + live
    url_seen:      set[str]        = set()

    for it in items:
        h = it['url_hash']
        if h in existing_hashes:
            continue
        tipo = it.get('tipo', 'pelicula')
        if tipo == 'pelicula':
            tk = _title_key(it.get('titulo') or '')
            if not tk:
                if h not in url_seen:
                    url_seen.add(h)
                    other_items.append(it)
                continue
            if tk not in best_pelicula:
                best_pelicula[tk] = it
            else:
                cur = best_pelicula[tk]
                # Prefiere: tiene imagen > tiene año > primera encontrada
                if it.get('imagen') and not cur.get('imagen'):
                    best_pelicula[tk] = it
                elif it.get('año') and not cur.get('año'):
                    best_pelicula[tk] = it
        else:
            if h not in url_seen:
                url_seen.add(h)
                other_items.append(it)

    # ── Fase 2: construir filas a insertar ──────────────────────────────
    candidates = list(best_pelicula.values()) + other_items
    n_existing  = sum(1 for it in items if it['url_hash'] in existing_hashes)
    dupl_m3u    = max(0, len(items) - n_existing - len(candidates))

    inserted: set[str] = set()
    rows: list[dict] = []
    for it in candidates:
        h = it['url_hash']
        if h in inserted:
            continue
        inserted.add(h)
        rows.append({
            'titulo':              it.get('titulo') or 'Sin título',
            'tipo':                it.get('tipo', 'pelicula'),
            'url_stream':          it['url_stream'],
            'url_hash':            h,
            'fuente':              'm3u',
            'servidor':            it.get('servidor') or '',
            'imagen':              it.get('imagen') or '',
            'descripcion':         None,
            'año':                 it.get('año'),
            'genero':              it.get('genero') or '',
            'group_title':         it.get('group_title') or '',
            'idioma':              it.get('idioma') or '',
            'pais':                it.get('pais') or '',
            'temporada':           it.get('temporada'),
            'episodio':            it.get('episodio'),
            'activo':              True,
            'fecha_agregado':      now,
            'ultima_verificacion': None,
            'lista_id':            lista_id,
            'fuente_rss_id':       None,
        })

    # ── Fase 3: Bulk INSERT en chunks ───────────────────────────────────
    if conflict_ignore:
        # INSERT OR IGNORE via engine.connect() (evita insertmanyvalues de SQLAlchemy 2.x
        # que añade RETURNING y es lento con on_conflict_do_nothing).
        # Un único COMMIT al final → 1 fsync total.
        _stmt = Contenido.__table__.insert().prefix_with('OR IGNORE')
        with db.engine.connect() as _conn:
            for i in range(0, len(rows), _BULK_CHUNK):
                _conn.execute(_stmt, rows[i:i + _BULK_CHUNK])
            _conn.commit()
    else:
        _stmt = Contenido.__table__.insert()
        for i in range(0, len(rows), _BULK_CHUNK):
            db.session.execute(_stmt, rows[i:i + _BULK_CHUNK])
            db.session.commit()

    return len(rows), dupl_m3u


def _import_lista_async(app, lista_id: int):
    t = threading.Thread(target=_import_lista, args=(app, lista_id), daemon=True)
    t.start()


def _import_lista(app, lista_id: int):
    with app.app_context():
        try:
            lista = Lista.query.get(lista_id)
            if not lista:
                return

            # Seleccionar proxy si la lista lo requiere
            proxy_url = None
            if lista.usar_proxy:
                active_proxies = Proxy.query.filter_by(activo=True).all()
                if active_proxies:
                    proxy_url = random.choice(active_proxies).url

            # Parsear grupos_seleccionados si existe.
            # Se normalizan los nombres (strip) para que coincidan exactamente con
            # los que produce parse_and_filter(), evitando que diferencias de
            # espacios entre la previsualización y el import descarten contenido.
            grupos_set = None
            if lista.grupos_seleccionados:
                try:
                    raw = json.loads(lista.grupos_seleccionados)
                    if isinstance(raw, list) and raw:
                        grupos_set = {g.strip() for g in raw if isinstance(g, str)}
                except (ValueError, TypeError):
                    pass

            # Parsear grupos_tipos (clasificación manual del admin)
            tipos_override = None
            if lista.grupos_tipos:
                try:
                    tipos_override = json.loads(lista.grupos_tipos)
                except (ValueError, TypeError):
                    pass

            app.logger.info(
                f'[Import M3U] Iniciando: {lista.nombre}'
                + (f' (proxy: {proxy_url})' if proxy_url else '')
                + (f' ({len(grupos_set)} grupos seleccionados)' if grupos_set else '')
                + (f' ({len(tipos_override)} tipos override)' if tipos_override else '')
            )
            items, error = fetch_and_parse(
                lista.url,
                app.config,
                filter_spanish=lista.filtrar_español,
                include_live=lista.incluir_live,
                proxy=proxy_url,
                grupos=grupos_set,
                tipos_override=tipos_override,
            )

            if error:
                lista.error = error
                lista.ultima_actualizacion = datetime.utcnow()
                db.session.commit()
                app.logger.error(f'[Import M3U] Error descargando {lista.nombre}: {error}')
                return

            app.logger.info(
                f'[Import M3U] {lista.nombre}: {len(items)} items tras filtros '
                f'(filtrar_español={lista.filtrar_español})'
            )

            # ── Deduplicación en 1 sola query (no N queries) ───────
            # Para listas de 3000-7000 items, esto es crítico para el rendimiento.
            candidate_hashes = {it['url_hash'] for it in items}
            # SQLite tiene límite de ~999 variables en IN; procesamos en chunks
            existing_hashes: set[str] = set()
            chunk_list = list(candidate_hashes)
            for i in range(0, len(chunk_list), 900):
                chunk = chunk_list[i:i + 900]
                rows = db.session.query(Contenido.url_hash)\
                    .filter(Contenido.url_hash.in_(chunk)).all()
                existing_hashes.update(r[0] for r in rows)

            nuevos, dupl_m3u = _do_bulk_insert(items, existing_hashes, lista_id)

            lista.error = None
            lista.total_items = Contenido.query.filter_by(lista_id=lista_id).count()
            lista.items_activos = Contenido.query.filter_by(lista_id=lista_id, activo=True).count()
            lista.ultima_actualizacion = datetime.utcnow()
            db.session.commit()

            app.logger.info(
                f'[Import M3U] {lista.nombre}: {nuevos} nuevos '
                f'({dupl_m3u} dupl. en M3U) / {lista.total_items} total'
            )

            # Notificar a Telegram si se importó contenido nuevo
            if nuevos > 0:
                try:
                    from telegram_bot import notify_new_content
                    movies_new = sum(1 for it in items[:nuevos] if it.get('tipo') == 'pelicula')
                    series_new = sum(1 for it in items[:nuevos] if it.get('tipo') == 'serie')
                    live_new   = sum(1 for it in items[:nuevos] if it.get('tipo') == 'live')
                    notify_new_content(app, movies_new, series_new, live_new, lista.nombre)
                except Exception:
                    pass

        except Exception as exc:
            app.logger.exception(f'[Import M3U] Excepción inesperada en lista {lista_id}: {exc}')
            try:
                lista = Lista.query.get(lista_id)
                if lista:
                    lista.error = f'Error interno: {exc}'
                    lista.ultima_actualizacion = datetime.utcnow()
                    db.session.commit()
                    try:
                        from telegram_bot import notify_import_error
                        notify_import_error(app, lista.nombre, str(exc))
                    except Exception:
                        pass
            except Exception:
                pass


def _import_from_bytes(app, lista_id: int, raw_bytes: bytes):
    """Importa contenido M3U desde bytes ya cargados (archivo subido por el admin)."""
    with app.app_context():
        try:
            lista = Lista.query.get(lista_id)
            if not lista:
                return

            t0 = _time.monotonic()
            app.logger.info(f'[Import archivo] {lista.nombre}: iniciando ({len(raw_bytes)//1024} KB)')

            content = decode_m3u_bytes(raw_bytes)
            app.logger.info(f'[Import archivo] decodificado en {_time.monotonic()-t0:.1f}s')

            grupos_set = None
            if lista.grupos_seleccionados:
                try:
                    grupos_set = set(json.loads(lista.grupos_seleccionados))
                except (ValueError, TypeError):
                    pass

            tipos_override = None
            if lista.grupos_tipos:
                try:
                    tipos_override = json.loads(lista.grupos_tipos)
                except (ValueError, TypeError):
                    pass

            t1 = _time.monotonic()
            items = parse_and_filter(
                content, app.config,
                filter_spanish=lista.filtrar_español,
                include_live=lista.incluir_live,
                grupos=grupos_set,
                tipos_override=tipos_override,
            )
            app.logger.info(
                f'[Import archivo] parse_and_filter: {len(items)} items '
                f'en {_time.monotonic()-t1:.1f}s'
            )

            # Para archivos subidos: INSERT OR IGNORE via engine.connect() —
            # sin pre-query de hashes, sin insertmanyvalues overhead.
            t2 = _time.monotonic()
            nuevos, dupl_m3u = _do_bulk_insert(items, set(), lista_id, conflict_ignore=True)
            app.logger.info(
                f'[Import archivo] bulk_insert: {nuevos} nuevos '
                f'en {_time.monotonic()-t2:.1f}s'
            )

            lista.error = None
            lista.total_items   = Contenido.query.filter_by(lista_id=lista_id).count()
            lista.items_activos = Contenido.query.filter_by(lista_id=lista_id, activo=True).count()
            lista.ultima_actualizacion = datetime.utcnow()
            db.session.commit()

            app.logger.info(
                f'[Import archivo] {lista.nombre}: COMPLETADO — {nuevos} nuevos '
                f'({dupl_m3u} dupl. en M3U) / {lista.total_items} total '
                f'| total {_time.monotonic()-t0:.1f}s'
            )

        except Exception as exc:
            app.logger.exception(f'[Import M3U] Excepción en archivo lista {lista_id}: {exc}')
            try:
                lista = Lista.query.get(lista_id)
                if lista:
                    lista.error = f'Error interno: {exc}'
                    lista.ultima_actualizacion = datetime.utcnow()
                    db.session.commit()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════
# LIMPIEZA DE DUPLICADOS
# ═══════════════════════════════════════════════════════════

@admin_bp.post('/api/dedup-peliculas')
@login_required
def dedup_peliculas():
    """
    Elimina películas duplicadas de la BD (mismo título normalizado).
    Conserva la que tiene mejor metadata (imagen > año > id más bajo).
    Solo afecta a tipo='pelicula'.
    """
    peliculas = Contenido.query.filter_by(tipo='pelicula', activo=True).all()

    best: dict[str, Contenido] = {}   # title_key → mejor objeto
    to_delete: list[int] = []

    for p in peliculas:
        tk = _title_key(p.titulo)
        if not tk:
            continue
        if tk not in best:
            best[tk] = p
        else:
            cur = best[tk]
            # Prefiere: tiene imagen > tiene año > id más pequeño (primero insertado)
            if p.imagen and not cur.imagen:
                to_delete.append(cur.id)
                best[tk] = p
            elif p.año and not cur.año and not (p.imagen and not cur.imagen):
                to_delete.append(cur.id)
                best[tk] = p
            else:
                to_delete.append(p.id)

    if to_delete:
        # Primero borrar watch_history para evitar violación NOT NULL en FK
        for i in range(0, len(to_delete), 900):
            chunk = to_delete[i:i + 900]
            WatchHistory.query.filter(WatchHistory.contenido_id.in_(chunk)).delete(synchronize_session=False)
        # Eliminar en chunks de 900 (límite SQLite IN)
        for i in range(0, len(to_delete), 900):
            chunk = to_delete[i:i + 900]
            Contenido.query.filter(Contenido.id.in_(chunk)).delete(synchronize_session=False)
        db.session.commit()

    return jsonify({'ok': True, 'eliminados': len(to_delete)})


# ═══════════════════════════════════════════════════════════
# GESTIÓN DE USUARIOS  (solo superadmin)
# ═══════════════════════════════════════════════════════════

@admin_bp.get('/users')
@superadmin_required
def users():
    all_users = User.query.order_by(User.fecha_creacion.desc()).all()
    return render_template('admin/users.html', users=all_users)


@admin_bp.post('/users/<int:user_id>/toggle')
@superadmin_required
def toggle_user(user_id):
    u = User.query.get_or_404(user_id)
    if u.is_superadmin:
        flash('No puedes desactivar al superadmin.', 'danger')
    else:
        u.activo = not u.activo
        db.session.commit()
        flash(f'Usuario {u.username} {"activado" if u.activo else "desactivado"}.', 'info')
    return redirect(url_for('admin.users'))


@admin_bp.post('/users/<int:user_id>/set-role')
@superadmin_required
def set_user_role(user_id):
    u = User.query.get_or_404(user_id)
    if u.is_superadmin:
        flash('No puedes cambiar el rol del superadmin.', 'danger')
        return redirect(url_for('admin.users'))
    nuevo_rol = request.form.get('role', 'user')
    if nuevo_rol not in ('user', 'premium'):
        nuevo_rol = 'user'
    u.role = nuevo_rol
    db.session.commit()
    flash(f'Rol de {u.username} cambiado a {nuevo_rol}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.post('/users/<int:user_id>/set-invite-limit')
@superadmin_required
def set_invite_limit(user_id):
    u = User.query.get_or_404(user_id)
    limit = request.form.get('limit', 10, type=int)
    limit = max(0, min(limit, 9999))
    u.invite_limit = limit
    db.session.commit()
    flash(f'Límite de invitaciones de {u.username} actualizado a {limit}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.post('/users/<int:user_id>/set-iptv-limit')
@superadmin_required
def set_iptv_limit(user_id):
    u = User.query.get_or_404(user_id)
    limit = request.form.get('limit', 10, type=int)
    limit = max(0, min(limit, 9999))
    u.iptv_user_limit = limit
    db.session.commit()
    flash(f'Límite de usuarios IPTV de {u.username} actualizado a {limit}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.post('/users/<int:user_id>/eliminar')
@superadmin_required
def eliminar_user(user_id):
    u = User.query.get_or_404(user_id)
    if u.is_superadmin:
        flash('No puedes eliminar al superadmin.', 'danger')
        return redirect(url_for('admin.users'))
    # Reasignar sus listas a global antes de borrar
    Lista.query.filter_by(owner_id=u.id).update({
        'owner_id': None, 'visibilidad': 'global'
    })
    FuenteRSS.query.filter_by(owner_id=u.id).update({
        'owner_id': None, 'visibilidad': 'global'
    })
    db.session.delete(u)
    db.session.commit()
    flash(f'Usuario {u.username} eliminado.', 'success')
    return redirect(url_for('admin.users'))


# ═══════════════════════════════════════════════════════════
# GESTIÓN DE TICKETS  (solo superadmin)
# ═══════════════════════════════════════════════════════════

@admin_bp.get('/tickets')
@superadmin_required
def tickets():
    estado_filter = request.args.get('estado', 'pendiente')
    query = Ticket.query
    if estado_filter in ('pendiente', 'aprobado', 'rechazado'):
        query = query.filter_by(estado=estado_filter)
    all_tickets = query.order_by(Ticket.fecha_creacion.desc()).all()
    pendientes = Ticket.query.filter_by(estado='pendiente').count()
    return render_template(
        'admin/tickets.html',
        tickets=all_tickets,
        estado_filter=estado_filter,
        pendientes=pendientes,
    )


@admin_bp.post('/tickets/<int:ticket_id>/responder')
@superadmin_required
def responder_ticket(ticket_id):
    ticket    = Ticket.query.get_or_404(ticket_id)
    accion    = request.form.get('accion', 'rechazado')
    respuesta = request.form.get('respuesta', '').strip()

    if accion not in ('aprobado', 'rechazado'):
        accion = 'rechazado'

    ticket.estado          = accion
    ticket.respuesta       = respuesta
    ticket.fecha_respuesta = datetime.utcnow()

    # Si es aprobado y el tipo es 'mas_invitaciones', aumentar el límite
    if accion == 'aprobado' and ticket.tipo == 'mas_invitaciones':
        incremento = request.form.get('incremento', 10, type=int)
        incremento = max(1, min(incremento, 100))
        u = User.query.get(ticket.user_id)
        if u:
            u.invite_limit += incremento
            flash(
                f'Ticket aprobado. Se han añadido {incremento} invitaciones a {u.username}.',
                'success'
            )
    else:
        flash(f'Ticket marcado como {accion}.', 'info')

    db.session.commit()
    return redirect(url_for('admin.tickets'))


# ═══════════════════════════════════════════════════════════
# REPORTES DE CANALES
# ═══════════════════════════════════════════════════════════

@admin_bp.get('/reportes')
@superadmin_required
def reportes():
    estado = request.args.get('estado', 'pendiente')
    q = (
        ChannelReport.query
        .join(Contenido, ChannelReport.contenido_id == Contenido.id)
        .filter(ChannelReport.estado == estado)
        .order_by(ChannelReport.fecha_creacion.desc())
    )
    items = q.all()
    return render_template(
        'admin/reportes.html',
        reportes=items,
        estado_filtro=estado,
    )


@admin_bp.post('/reportes/<int:report_id>/resolver')
@superadmin_required
def resolver_reporte(report_id):
    r     = ChannelReport.query.get_or_404(report_id)
    accion = request.form.get('accion', 'revisado')  # revisado|resuelto|eliminar_canal

    if accion == 'eliminar_canal':
        c = Contenido.query.get(r.contenido_id)
        if c:
            c.activo = False
        r.estado         = 'resuelto'
        r.nota_admin     = 'Canal desactivado'
        r.fecha_revision = datetime.utcnow()
        db.session.commit()
        flash('Canal desactivado y reporte cerrado.', 'success')
    elif accion == 'resuelto':
        r.estado         = 'resuelto'
        r.nota_admin     = request.form.get('nota', '').strip()
        r.fecha_revision = datetime.utcnow()
        db.session.commit()
        flash('Reporte marcado como resuelto.', 'success')
    else:
        r.estado         = 'revisado'
        r.nota_admin     = request.form.get('nota', '').strip()
        r.fecha_revision = datetime.utcnow()
        db.session.commit()
        flash('Reporte marcado como revisado.', 'info')

    return redirect(url_for('admin.reportes', estado=request.form.get('volver', 'pendiente')))


@admin_bp.post('/reportes/<int:report_id>/eliminar')
@superadmin_required
def eliminar_reporte(report_id):
    r = ChannelReport.query.get_or_404(report_id)
    db.session.delete(r)
    db.session.commit()
    flash('Reporte eliminado.', 'success')
    return redirect(url_for('admin.reportes'))


@admin_bp.get('/reportes/<int:report_id>/verificar')
@superadmin_required
def verificar_canal(report_id):
    """Comprueba si el stream del canal reportado responde (HEAD request)."""
    r = ChannelReport.query.get_or_404(report_id)
    c = Contenido.query.get(r.contenido_id)
    if not c:
        return jsonify({'ok': False, 'error': 'Canal no encontrado'})
    try:
        resp = _requests.head(c.url_stream, timeout=8, allow_redirects=True,
                              headers={'User-Agent': 'VLC/3.0'})
        return jsonify({'ok': resp.status_code < 400, 'status': resp.status_code,
                        'url': c.url_stream, 'titulo': c.titulo})
    except Exception as ex:
        return jsonify({'ok': False, 'error': str(ex), 'url': c.url_stream, 'titulo': c.titulo})


# ═══════════════════════════════════════════════════════════
# PANEL IPTV — GESTIÓN DE USUARIOS IPTV
# ═══════════════════════════════════════════════════════════

@admin_bp.get('/iptv')
@login_required
def iptv_panel():
    panel_user = _get_panel_user()
    if panel_user.is_superadmin:
        usuarios = IptvUser.query.order_by(IptvUser.fecha_creacion.desc()).all()
    else:
        usuarios = IptvUser.query.filter_by(owner_id=panel_user.id).order_by(IptvUser.fecha_creacion.desc()).all()
    # Contar sesiones activas por usuario (heartbeat < 2 min)
    from datetime import timedelta
    _limite = datetime.utcnow() - timedelta(minutes=2)
    activas = {}
    for u in usuarios:
        activas[u.id] = IptvSession.query.filter(
            IptvSession.iptv_user_id == u.id,
            IptvSession.last_heartbeat >= _limite,
        ).count()
    # Grupos disponibles organizados por tipo (pelicula/serie/live)
    from sqlalchemy import func as _func
    _rows = (
        db.session.query(Contenido.group_title, Contenido.tipo, _func.count().label('cnt'))
        .filter(Contenido.activo == True, Contenido.group_title != None, Contenido.group_title != '')
        .group_by(Contenido.group_title, Contenido.tipo)
        .order_by(Contenido.group_title)
        .all()
    )
    # Para cada group_title tomar el tipo dominante (más contenidos)
    _seen: dict = {}
    for row in sorted(_rows, key=lambda x: -x.cnt):
        if row.group_title not in _seen:
            _seen[row.group_title] = row.tipo or 'otro'
    groups_by_type = {'pelicula': [], 'serie': [], 'live': [], 'otro': []}
    for grp, tipo in sorted(_seen.items()):
        groups_by_type[tipo if tipo in groups_by_type else 'otro'].append(grp)
    all_groups = sorted(_seen.keys())
    # Límite IPTV del usuario actual y cuántos ha creado ya
    iptv_creados = 0 if panel_user.is_superadmin else len(usuarios)
    from models import XtreamConfig
    xtream_cfg = XtreamConfig.query.get(1)
    if xtream_cfg is None:
        xtream_cfg = XtreamConfig(id=1)
        db.session.add(xtream_cfg)
        db.session.commit()
    return render_template(
        'admin/iptv.html',
        usuarios=usuarios, activas=activas, panel_user=panel_user,
        all_groups=all_groups, groups_by_type=groups_by_type,
        iptv_creados=iptv_creados, xtream_cfg=xtream_cfg,
    )


@admin_bp.post('/iptv/xtream-config')
@login_required
def iptv_xtream_config():
    """Guarda la configuración del servidor Xtream (modo stream + tipos habilitados)."""
    from models import XtreamConfig
    if not _get_panel_user().is_superadmin:
        abort(403)
    cfg = XtreamConfig.query.get(1)
    if cfg is None:
        cfg = XtreamConfig(id=1)
        db.session.add(cfg)
    cfg.stream_mode    = 'proxy' if request.form.get('stream_mode') == 'proxy' else 'direct'
    cfg.live_enabled   = bool(request.form.get('live_enabled'))
    cfg.vod_enabled    = bool(request.form.get('vod_enabled'))
    cfg.series_enabled = bool(request.form.get('series_enabled'))
    db.session.commit()
    from flask import flash
    flash('Configuración Xtream guardada.', 'success')
    return redirect(url_for('admin.iptv_panel'))


@admin_bp.post('/iptv/crear')
@login_required
def iptv_crear():
    from datetime import timedelta
    panel_user = _get_panel_user()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    plan     = request.form.get('plan', '1m')
    max_con  = int(request.form.get('max_connections', 1))
    nota     = request.form.get('nota', '').strip()

    if not username or not password:
        flash('Usuario y contraseña son obligatorios.', 'danger')
        return redirect(url_for('admin.iptv_panel'))
    if IptvUser.query.filter_by(username=username).first():
        flash('Ya existe un usuario con ese nombre.', 'danger')
        return redirect(url_for('admin.iptv_panel'))

    # Verificar límite de usuarios IPTV para premium
    if not panel_user.is_superadmin:
        current_count = IptvUser.query.filter_by(owner_id=panel_user.id).count()
        limite = panel_user.iptv_user_limit
        if current_count >= limite:
            flash(f'Has alcanzado el límite de {limite} usuarios IPTV. Solicita un aumento al superadmin.', 'danger')
            return redirect(url_for('admin.iptv_panel'))

    duraciones = {'1m': 30, '3m': 90, '6m': 180, '1y': 365}
    dias = duraciones.get(plan, 30)
    expires_at = datetime.utcnow() + timedelta(days=dias)

    # Grupos permitidos (JSON list de group_titles seleccionados)
    grupos_sel = request.form.getlist('grupos_permitidos')
    grupos_json = json.dumps(grupos_sel) if grupos_sel else None

    u = IptvUser(username=username, plan=plan,
                 max_connections=max(1, min(max_con, 5)),
                 expires_at=expires_at, nota=nota or None,
                 grupos_permitidos=grupos_json,
                 owner_id=None if panel_user.is_superadmin else panel_user.id)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    flash(f'Usuario IPTV "{username}" creado con plan {u.plan_label}.', 'success')
    return redirect(url_for('admin.iptv_panel'))


@admin_bp.post('/iptv/<int:uid>/editar')
@login_required
def iptv_editar(uid):
    from datetime import timedelta
    panel_user = _get_panel_user()
    u = IptvUser.query.get_or_404(uid)
    if not panel_user.is_superadmin and u.owner_id != panel_user.id:
        flash('No tienes permiso para editar este usuario.', 'danger')
        return redirect(url_for('admin.iptv_panel'))
    plan    = request.form.get('plan', u.plan)
    max_con = int(request.form.get('max_connections', u.max_connections))
    activo  = request.form.get('activo') == '1'
    nota    = request.form.get('nota', '').strip()
    renovar = request.form.get('renovar') == '1'
    nueva_pass = request.form.get('password', '').strip()

    # Grupos permitidos actualizados
    grupos_sel = request.form.getlist('grupos_permitidos')
    u.grupos_permitidos = json.dumps(grupos_sel) if grupos_sel else None

    u.plan            = plan
    u.max_connections = max(1, min(max_con, 5))
    u.activo          = activo
    u.nota            = nota or None
    if nueva_pass:
        u.set_password(nueva_pass)
    if renovar:
        duraciones = {'1m': 30, '3m': 90, '6m': 180, '1y': 365}
        dias = duraciones.get(plan, 30)
        base = max(datetime.utcnow(), u.expires_at or datetime.utcnow())
        u.expires_at = base + timedelta(days=dias)
        flash(f'Suscripción renovada hasta {u.expires_at.strftime("%d/%m/%Y")}.', 'success')
    db.session.commit()
    flash(f'Usuario "{u.username}" actualizado.', 'success')
    return redirect(url_for('admin.iptv_panel'))


@admin_bp.post('/iptv/<int:uid>/eliminar')
@login_required
def iptv_eliminar(uid):
    panel_user = _get_panel_user()
    u = IptvUser.query.get_or_404(uid)
    if not panel_user.is_superadmin and u.owner_id != panel_user.id:
        flash('No tienes permiso para eliminar este usuario.', 'danger')
        return redirect(url_for('admin.iptv_panel'))
    nombre = u.username
    db.session.delete(u)
    db.session.commit()
    flash(f'Usuario IPTV "{nombre}" eliminado.', 'success')
    return redirect(url_for('admin.iptv_panel'))


@admin_bp.get('/iptv/api/online')
@login_required
def iptv_online():
    """Devuelve JSON con sesiones IPTV activas (heartbeat < 2 min)."""
    from datetime import timedelta
    limite = datetime.utcnow() - timedelta(minutes=2)
    sesiones = (
        IptvSession.query
        .filter(IptvSession.last_heartbeat >= limite)
        .join(IptvUser, IptvSession.iptv_user_id == IptvUser.id)
        .all()
    )
    return jsonify([{
        'usuario':      s.iptv_user.username,
        'ip':           s.ip_address,
        'contenido_id': s.contenido_id,
        'last_hb':      s.last_heartbeat.isoformat(),
    } for s in sesiones])


# ══════════════════════════════════════════════════════════════
# TELEGRAM BOT — configuración y test
# ══════════════════════════════════════════════════════════════

@admin_bp.get('/telegram')
@superadmin_required
def telegram():
    cfg = TelegramConfig.query.first()
    return render_template('admin/telegram.html', cfg=cfg)


@admin_bp.get('/api/telegram-config')
@superadmin_required
def telegram_config_get():
    cfg = TelegramConfig.query.first()
    if not cfg:
        return jsonify({'enabled': False, 'token': '', 'chat_ids': [],
                        'alert_threshold': 80, 'daily_digest': True, 'digest_hour': 8})
    import json as _json
    try:
        ids = _json.loads(cfg.chat_ids_json) if cfg.chat_ids_json else []
    except Exception:
        ids = []
    return jsonify({
        'enabled':         cfg.enabled,
        'token':           cfg.token or '',
        'chat_ids':        ids,
        'alert_threshold': cfg.alert_threshold,
        'daily_digest':    cfg.daily_digest,
        'digest_hour':     cfg.digest_hour,
    })


@admin_bp.post('/api/telegram-config')
@superadmin_required
def telegram_config_save():
    data = request.get_json(silent=True) or {}
    cfg = TelegramConfig.query.first()
    if not cfg:
        cfg = TelegramConfig()
        db.session.add(cfg)

    raw_ids = data.get('chat_ids', [])
    if isinstance(raw_ids, str):
        raw_ids = [x.strip() for x in raw_ids.replace('\n', ',').split(',') if x.strip()]

    cfg.enabled          = bool(data.get('enabled', True))
    cfg.token            = (data.get('token') or '').strip()
    cfg.chat_ids_json    = json.dumps(raw_ids)
    cfg.alert_threshold  = int(data.get('alert_threshold', 80))
    cfg.daily_digest     = bool(data.get('daily_digest', True))
    cfg.digest_hour      = int(data.get('digest_hour', 8))
    cfg.updated_at       = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True})


@admin_bp.post('/api/telegram-test')
@superadmin_required
def telegram_test():
    data    = request.get_json(silent=True) or {}
    token   = (data.get('token') or '').strip()
    chat_id = (data.get('chat_id') or '').strip()
    if not token or not chat_id:
        return jsonify({'ok': False, 'msg': 'Falta token o chat_id.'})
    from telegram_bot import send_test
    ok, msg = send_test(token, chat_id)
    return jsonify({'ok': ok, 'msg': msg})


# ══════════════════════════════════════════════════════════════
# SERVIDORES — purgar caídos / re-escanear
# ══════════════════════════════════════════════════════════════

@admin_bp.post('/api/purge-server')
@superadmin_required
def purge_server():
    """Elimina todos los contenidos inactivos (activo=False) de un servidor."""
    servidor = (request.get_json(silent=True) or {}).get('servidor', '').strip()
    if not servidor:
        return jsonify({'ok': False, 'msg': 'Falta servidor.'})
    deleted = Contenido.query.filter_by(servidor=servidor, activo=False).delete()
    db.session.commit()
    return jsonify({'ok': True, 'deleted': deleted})


@admin_bp.post('/api/rescan-server')
@superadmin_required
def rescan_server():
    """Marca todos los contenidos de un servidor para que sean re-verificados."""
    servidor = (request.get_json(silent=True) or {}).get('servidor', '').strip()
    if not servidor:
        return jsonify({'ok': False, 'msg': 'Falta servidor.'})
    updated = (
        Contenido.query
        .filter_by(servidor=servidor)
        .update({'ultima_verificacion': None}, synchronize_session=False)
    )
    db.session.commit()
    return jsonify({'ok': True, 'updated': updated})


# ── Acciones manuales Telegram ─────────────────────────────────

@admin_bp.post('/api/telegram-send-digest')
@superadmin_required
def telegram_send_digest():
    """Envía el resumen diario de estadísticas ahora mismo."""
    try:
        from telegram_bot import notify_daily_digest
        notify_daily_digest(current_app._get_current_object())
        return jsonify({'ok': True, 'msg': 'Resumen enviado correctamente.'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})


@admin_bp.post('/api/telegram-send-servers')
@superadmin_required
def telegram_send_servers():
    """Envía el estado de salud de todos los servidores."""
    try:
        from link_checker import server_health
        rows = server_health(current_app._get_current_object())
        if not rows:
            return jsonify({'ok': False, 'msg': 'No hay datos de servidores.'})

        from telegram_bot import notify_all
        from datetime import datetime
        lines = ['🖥️ <b>Estado de servidores</b>', f'📅 {datetime.now().strftime("%d/%m/%Y %H:%M")}', '']
        for r in rows:
            pct_ok = 100 - r['dead_pct']
            icon = '🟢' if pct_ok >= 80 else ('🟡' if pct_ok >= 50 else '🔴')
            lines.append(
                f'{icon} <code>{r["servidor"]}</code>\n'
                f'   ✅ {r["alive"]:,} activos / 🔴 {r["dead"]:,} caídos ({r["dead_pct"]:.1f}%)'
            )
        notify_all(current_app._get_current_object(), '\n'.join(lines))
        return jsonify({'ok': True, 'msg': f'Estado de {len(rows)} servidores enviado.'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})


@admin_bp.post('/api/telegram-send-down')
@superadmin_required
def telegram_send_down():
    """Envía solo los servidores críticos (>= umbral de alerta)."""
    try:
        from link_checker import server_health
        from telegram_bot import notify_all, _get_config
        from models import TelegramConfig
        from datetime import datetime

        cfg = TelegramConfig.query.first()
        threshold = cfg.alert_threshold if cfg else 80
        rows = server_health(current_app._get_current_object())
        criticos = [r for r in rows if r['dead_pct'] >= threshold]

        if not criticos:
            notify_all(current_app._get_current_object(),
                       f'✅ <b>Sin servidores críticos</b>\n\nTodos los servidores están por debajo del umbral de alerta ({threshold}%).\n📅 {datetime.now().strftime("%d/%m/%Y %H:%M")}')
            return jsonify({'ok': True, 'msg': 'Ningún servidor crítico. Mensaje enviado.'})

        lines = [f'🚨 <b>Servidores críticos ({len(criticos)})</b>', f'⚠️ Umbral: {threshold}%', '']
        for r in criticos:
            lines.append(
                f'🔴 <code>{r["servidor"]}</code>\n'
                f'   📉 {r["dead_pct"]:.1f}% caídos ({r["dead"]:,}/{r["total"]:,})'
            )
        notify_all(current_app._get_current_object(), '\n'.join(lines))
        return jsonify({'ok': True, 'msg': f'{len(criticos)} servidor(es) crítico(s) enviados.'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})


@admin_bp.post('/api/backup-create')
@superadmin_api_required
def backup_create():
    """Crea un backup manual de la BD."""
    try:
        from backup import create_backup
        path = create_backup(current_app._get_current_object())
        return jsonify({'ok': True, 'msg': f'Backup creado: {path.name} ({path.stat().st_size // 1024} KB)'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})


@admin_bp.post('/api/backup-send')
@superadmin_api_required
def backup_send():
    """Crea un backup y lo envía por Telegram."""
    try:
        from backup import create_backup, send_backup_telegram
        app = current_app._get_current_object()
        path = create_backup(app)
        ok, msg = send_backup_telegram(app, path)
        return jsonify({'ok': ok, 'msg': msg})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})


@admin_bp.get('/api/backup-list')
@superadmin_api_required
def backup_list():
    """Lista los backups disponibles."""
    from backup import list_backups
    return jsonify({'ok': True, 'backups': list_backups()})


@admin_bp.get('/api/backup-download/<filename>')
@superadmin_api_required
def backup_download(filename: str):
    """Descarga un fichero de backup."""
    import re
    from backup import BACKUP_DIR
    from flask import send_file, abort
    # Validar nombre para evitar path traversal
    if not re.match(r'^cinemacity_\d{8}_\d{6}\.db$', filename):
        abort(400)
    path = BACKUP_DIR / filename
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=filename)


@admin_bp.post('/api/telegram-send-content')
@superadmin_required
def telegram_send_content():
    """Envía el reporte de contenido de la BD."""
    try:
        from telegram_bot import notify_all
        from datetime import datetime

        total     = Contenido.query.filter_by(fuente='m3u').count()
        activos   = Contenido.query.filter_by(fuente='m3u', activo=True).count()
        caidos    = total - activos
        peliculas = Contenido.query.filter_by(fuente='m3u', tipo='pelicula', activo=True).count()
        series    = Contenido.query.filter_by(fuente='m3u', tipo='serie',    activo=True).count()
        live      = Contenido.query.filter_by(fuente='m3u', tipo='live',     activo=True).count()
        pct_ok    = round(activos / total * 100, 1) if total else 0

        text = (
            f'📦 <b>Reporte de contenido</b>\n'
            f'📅 {datetime.now().strftime("%d/%m/%Y %H:%M")}\n\n'
            f'🎬 Películas: <b>{peliculas:,}</b>\n'
            f'📺 Series: <b>{series:,}</b>\n'
            f'📡 Directo: <b>{live:,}</b>\n\n'
            f'✅ Activos: <b>{activos:,}</b> ({pct_ok}%)\n'
            f'🔴 Caídos: <b>{caidos:,}</b>\n'
            f'📊 Total: <b>{total:,}</b>'
        )
        notify_all(current_app._get_current_object(), text)
        return jsonify({'ok': True, 'msg': 'Reporte de contenido enviado.'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})


# ─────────────────────────────────────────────────────────────
# Telegram — Webhook (recibe updates de Telegram, sin auth)
# ─────────────────────────────────────────────────────────────

@admin_bp.post('/api/telegram-webhook/<path:token_path>')
def telegram_webhook(token_path):
    """
    Endpoint que Telegram llama con cada update.
    La URL incluye el token del bot como capa de seguridad.
    No requiere sesión de administrador.
    """
    from telegram_bot import handle_webhook_update

    cfg = TelegramConfig.query.first()
    if not cfg or not cfg.token or cfg.token != token_path:
        return '', 403

    update = request.get_json(silent=True) or {}
    import threading
    app = current_app._get_current_object()
    threading.Thread(
        target=handle_webhook_update,
        args=(app, update),
        daemon=True,
    ).start()
    return '', 200


# ─────────────────────────────────────────────────────────────
# Telegram — Gestión del webhook desde el panel admin
# ─────────────────────────────────────────────────────────────

@admin_bp.post('/api/telegram-webhook-set')
@superadmin_required
def telegram_webhook_set():
    """Registra el webhook de Telegram apuntando a este servidor."""
    from telegram_bot import set_webhook

    cfg = TelegramConfig.query.first()
    if not cfg or not cfg.token:
        return jsonify({'ok': False, 'msg': 'Bot no configurado. Guarda el token primero.'})

    base_url = request.json.get('base_url', '').rstrip('/')
    if not base_url:
        return jsonify({'ok': False, 'msg': 'Falta la URL base del servidor.'})

    webhook_url = f"{base_url}/admin/api/telegram-webhook/{cfg.token}"
    ok, msg = set_webhook(cfg.token, webhook_url)
    return jsonify({'ok': ok, 'msg': msg, 'webhook_url': webhook_url if ok else ''})


@admin_bp.post('/api/telegram-webhook-del')
@superadmin_required
def telegram_webhook_del():
    """Elimina el webhook de Telegram."""
    from telegram_bot import delete_webhook

    cfg = TelegramConfig.query.first()
    if not cfg or not cfg.token:
        return jsonify({'ok': False, 'msg': 'Bot no configurado.'})

    ok, msg = delete_webhook(cfg.token)
    return jsonify({'ok': ok, 'msg': msg})


@admin_bp.get('/api/telegram-webhook-info')
@superadmin_required
def telegram_webhook_info():
    """Devuelve el estado actual del webhook registrado en Telegram."""
    from telegram_bot import get_webhook_info

    cfg = TelegramConfig.query.first()
    if not cfg or not cfg.token:
        return jsonify({'ok': False, 'info': {}})

    info = get_webhook_info(cfg.token)
    return jsonify({'ok': True, 'info': info})


# ══════════════════════════════════════════════════════════════
# CANALES CURADOS — Lista manual de live con múltiples fuentes
# ══════════════════════════════════════════════════════════════

@admin_bp.get('/curado')
@superadmin_required
def curado():
    """Gestión de la lista de canales en directo curados manualmente."""
    canales = CanalCurado.query.order_by(CanalCurado.orden, CanalCurado.nombre).all()
    panel_user = _get_panel_user()
    return render_template('admin/curado.html', canales=canales, panel_user=panel_user)


@admin_bp.get('/curado/api/buscar')
@superadmin_required
def curado_buscar():
    """Busca canales live en la BD para añadir a la lista curada (AJAX)."""
    q = request.args.get('q', '').strip()
    lista_id = request.args.get('lista_id', 0, type=int) or None

    base_q = Contenido.query.filter(
        Contenido.tipo == 'live',
        Contenido.activo == True,
    )
    if q:
        base_q = base_q.filter(Contenido.titulo.ilike(f'%{q}%'))
    if lista_id:
        base_q = base_q.filter(Contenido.lista_id == lista_id)

    resultados = base_q.order_by(Contenido.titulo).limit(60).all()
    listas = Lista.query.order_by(Lista.nombre).all()

    return jsonify({
        'canales': [{
            'id':      c.id,
            'titulo':  c.titulo,
            'logo':    c.imagen or '',
            'grupo':   c.group_title or '',
            'url':     c.url_stream,
            'servidor': c.servidor or '',
            'lista_id': c.lista_id,
        } for c in resultados],
        'listas': [{'id': l.id, 'nombre': l.nombre} for l in listas],
    })


@admin_bp.post('/curado/crear')
@superadmin_required
def curado_crear():
    """Crea un nuevo canal curado."""
    import json as _j
    nombre = request.form.get('nombre', '').strip()
    if not nombre:
        flash('El nombre es obligatorio.', 'danger')
        return redirect(url_for('admin.curado'))

    logo  = request.form.get('logo', '').strip() or None
    grupo = request.form.get('grupo', '').strip() or None
    try:
        urls = _j.loads(request.form.get('urls', '[]'))
    except Exception:
        urls = []

    max_orden = db.session.query(db.func.max(CanalCurado.orden)).scalar() or 0
    canal = CanalCurado(
        nombre=nombre, logo=logo, grupo=grupo,
        urls_json=_j.dumps(urls),
        orden=max_orden + 1,
    )
    db.session.add(canal)
    db.session.commit()
    flash(f'Canal "{nombre}" añadido a la lista curada.', 'success')
    return redirect(url_for('admin.curado'))


@admin_bp.post('/curado/<int:cid>/editar')
@superadmin_required
def curado_editar(cid):
    """Edita un canal curado (llamada AJAX, devuelve JSON)."""
    import json as _j
    canal = CanalCurado.query.get_or_404(cid)
    canal.nombre = request.form.get('nombre', canal.nombre).strip()
    canal.logo   = request.form.get('logo', '').strip() or None
    canal.grupo  = request.form.get('grupo', '').strip() or None
    canal.activo = request.form.get('activo', 'true') == 'true'
    try:
        canal.urls_json = _j.dumps(_j.loads(request.form.get('urls', '[]')))
    except Exception:
        pass
    db.session.commit()
    return jsonify({'ok': True})


@admin_bp.post('/curado/<int:cid>/eliminar')
@superadmin_required
def curado_eliminar(cid):
    """Elimina un canal curado."""
    canal = CanalCurado.query.get_or_404(cid)
    nombre = canal.nombre
    db.session.delete(canal)
    db.session.commit()
    flash(f'Canal "{nombre}" eliminado.', 'info')
    return redirect(url_for('admin.curado'))


@admin_bp.post('/curado/reordenar')
@superadmin_required
def curado_reordenar():
    """Actualiza el orden de los canales. Body JSON: {"ids": [3, 1, 5, ...]}"""
    import json as _j
    data = request.get_json(silent=True) or {}
    for idx, cid in enumerate(data.get('ids', [])):
        CanalCurado.query.filter_by(id=int(cid)).update({'orden': idx})
    db.session.commit()
    return jsonify({'ok': True})


@admin_bp.post('/curado/importar-m3u')
@superadmin_required
def curado_importar_m3u():
    """Importa canales curados en bloque desde un archivo .m3u subido."""
    import json as _jj
    from m3u_parser import decode_m3u_bytes, parse_extinf, is_vod_content

    archivo = request.files.get('archivo')
    if not archivo or not archivo.filename:
        flash('Selecciona un archivo .m3u', 'danger')
        return redirect(url_for('admin.curado'))

    try:
        raw = archivo.read()
    except Exception as exc:
        flash(f'Error leyendo archivo: {exc}', 'danger')
        return redirect(url_for('admin.curado'))

    content = decode_m3u_bytes(raw)

    # Parseo ligero del M3U para extraer solo canales en directo
    canales = {}   # clave normalizada → {nombre, logo, grupo, urls:[]}
    lines   = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.upper().startswith('#EXTINF:'):
            # Buscar la URL (siguiente línea no vacía y no comentario)
            url = ''
            j   = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if nxt and not nxt.startswith('#'):
                    url = nxt
                    break
                j += 1

            info = parse_extinf(line)
            info['url_stream'] = url   # necesario para is_vod_content (ruta /live/)

            # Solo canales en directo (excluir películas y series)
            if url and not is_vod_content(info, current_app.config):
                nombre = (info.get('titulo') or '').strip() or 'Canal'
                logo   = info.get('imagen')      or ''
                grupo  = info.get('group_title') or ''
                key    = nombre.lower().strip()

                if key not in canales:
                    canales[key] = {'nombre': nombre, 'logo': logo, 'grupo': grupo, 'urls': []}
                canales[key]['urls'].append({
                    'nombre': 'URL ' + str(len(canales[key]['urls']) + 1),
                    'url':    url,
                })
            i = j + 1
        else:
            i += 1

    if not canales:
        flash('No se encontraron canales en directo en el archivo.', 'warning')
        return redirect(url_for('admin.curado'))

    # Opción: borrar todos los existentes antes de importar
    if request.form.get('reemplazar'):
        CanalCurado.query.delete()
        db.session.flush()

    max_orden = db.session.query(db.func.max(CanalCurado.orden)).scalar() or 0
    creados   = 0
    for ch in canales.values():
        canal = CanalCurado(
            nombre   = ch['nombre'],
            logo     = ch['logo'] or None,
            grupo    = ch['grupo'] or None,
            urls_json= _jj.dumps(ch['urls']),
            orden    = max_orden + creados + 1,
            activo   = True,
        )
        db.session.add(canal)
        creados += 1

    db.session.commit()
    flash(f'✓ {creados} canales curados importados correctamente.', 'success')
    return redirect(url_for('admin.curado'))
