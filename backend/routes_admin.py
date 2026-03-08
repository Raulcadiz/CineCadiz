"""
Panel de administración — /admin/
"""
import json
import re as _re
import threading
import uuid
from datetime import datetime
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash, jsonify, current_app,
)

import random
import requests as _requests   # alias para no colisionar con el parámetro 'request' de Flask

from models import db, Lista, FuenteRSS, Contenido, Proxy, User, InviteToken, Ticket, UserSession
from m3u_parser import (
    fetch_and_parse, parse_and_filter,
    fetch_groups_preview, get_groups_preview, decode_m3u_bytes,
)
from link_checker import scan_dead_links
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
    """Requiere rol superadmin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        u = _get_panel_user()
        if not u or not u.is_superadmin:
            flash('Acceso restringido al superadmin.', 'danger')
            return redirect(url_for('admin.dashboard'))
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

    return render_template(
        'admin/dashboard.html',
        stats=stats, listas=listas, fuentes=fuentes,
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
    db.session.delete(lista)
    db.session.commit()
    flash(f'Lista "{nombre}" y todo su contenido eliminados.', 'success')
    return redirect(url_for('admin.listas'))


@admin_bp.post('/listas/<int:lista_id>/toggle')
@login_required
def toggle_lista(lista_id):
    lista = Lista.query.get_or_404(lista_id)
    lista.activa = not lista.activa
    db.session.commit()
    flash(f'Lista "{lista.nombre}" {"activada" if lista.activa else "desactivada"}.', 'info')
    return redirect(url_for('admin.listas'))


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
    batch = request.form.get('batch', app.config.get('SCAN_BATCH_SIZE', 500), type=int)
    workers = request.form.get('workers', 40, type=int)
    workers = max(5, min(workers, 80))   # entre 5 y 80

    def run():
        _scan_state['running'] = True
        try:
            result = scan_dead_links(app, batch_size=batch, max_workers=workers)
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
    db.session.flush()

    app = current_app._get_current_object()
    t = threading.Thread(
        target=_import_from_bytes, args=(app, lista.id, raw_bytes),
        daemon=True,
    )
    t.start()

    db.session.commit()
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

    # Borrar contenido antiguo de esta lista antes de re-importar
    Contenido.query.filter_by(lista_id=lista_id).delete()
    lista.ultima_actualizacion = None
    lista.error = None
    db.session.commit()

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


def _do_bulk_insert(items: list, existing_hashes: set, lista_id: int) -> tuple[int, int]:
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
    for i in range(0, len(rows), _BULK_CHUNK):
        db.session.execute(Contenido.__table__.insert(), rows[i:i + _BULK_CHUNK])
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

            # Parsear grupos_seleccionados si existe
            grupos_set = None
            if lista.grupos_seleccionados:
                try:
                    grupos_set = set(json.loads(lista.grupos_seleccionados))
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

        except Exception as exc:
            app.logger.exception(f'[Import M3U] Excepción inesperada en lista {lista_id}: {exc}')
            try:
                lista = Lista.query.get(lista_id)
                if lista:
                    lista.error = f'Error interno: {exc}'
                    lista.ultima_actualizacion = datetime.utcnow()
                    db.session.commit()
            except Exception:
                pass


def _import_from_bytes(app, lista_id: int, raw_bytes: bytes):
    """Importa contenido M3U desde bytes ya cargados (archivo subido por el admin)."""
    with app.app_context():
        try:
            lista = Lista.query.get(lista_id)
            if not lista:
                return

            app.logger.info(f'[Import M3U] Procesando archivo: {lista.nombre} ({len(raw_bytes)//1024} KB)')

            content = decode_m3u_bytes(raw_bytes)

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

            items = parse_and_filter(
                content, app.config,
                filter_spanish=lista.filtrar_español,
                include_live=lista.incluir_live,
                grupos=grupos_set,
                tipos_override=tipos_override,
            )

            app.logger.info(f'[Import M3U] {lista.nombre}: {len(items)} items tras filtros')

            # ── Deduplicación en 1 query (chunked para SQLite) ──────────
            candidate_hashes = {it['url_hash'] for it in items}
            existing_hashes: set[str] = set()
            chunk_list = list(candidate_hashes)
            for i in range(0, len(chunk_list), 900):
                chunk = chunk_list[i:i + 900]
                rows = db.session.query(Contenido.url_hash)\
                    .filter(Contenido.url_hash.in_(chunk)).all()
                existing_hashes.update(r[0] for r in rows)

            nuevos, dupl_m3u = _do_bulk_insert(items, existing_hashes, lista_id)

            lista.error = None
            lista.total_items   = Contenido.query.filter_by(lista_id=lista_id).count()
            lista.items_activos = Contenido.query.filter_by(lista_id=lista_id, activo=True).count()
            lista.ultima_actualizacion = datetime.utcnow()
            db.session.commit()

            app.logger.info(
                f'[Import M3U] {lista.nombre}: {nuevos} nuevos '
                f'({dupl_m3u} dupl. en M3U) / {lista.total_items} total'
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
