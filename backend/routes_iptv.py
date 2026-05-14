"""
Servicio IPTV externo — /iptv/ + Xtream Codes API

Endpoints M3U clásico (/iptv/):
  GET  /iptv/<user>/<pass>/playlist.m3u
  GET  /iptv/<user>/<pass>/stream/<id>
  POST /iptv/<user>/<pass>/heartbeat/<token>
  GET  /iptv/<user>/<pass>/info

Xtream Codes API (apps tipo XCIPTV, IPTV Smarters, TiviMate):
  GET  /player_api.php?username=X&password=Y[&action=...]
  GET  /<user>/<pass>/<stream_id>            <- live
  GET  /<user>/<pass>/<stream_id>.ts/.m3u8   <- live con extension
  GET  /movie/<user>/<pass>/<id>.mp4         <- VOD
  GET  /series/<user>/<pass>/<id>.mkv        <- series
  GET  /get.php?username=X&password=Y&type=m3u_plus  <- playlist M3U (legacy)
  GET  /xmltv.php?username=X&password=Y      <- EPG stub

El modo de stream (proxy VPS / directo al proveedor) se controla desde el
panel admin -> IPTV -> Configuracion Xtream (XtreamConfig en BD).
"""
import json as _json
import re as _re
import secrets
from datetime import datetime, timedelta
from urllib.parse import quote as _quote

import requests as _requests
from flask import Blueprint, Response, abort, jsonify, redirect, request, stream_with_context

from models import db, Contenido, IptvUser, IptvSession, Lista, XtreamConfig

iptv_bp = Blueprint('iptv', __name__, url_prefix='/iptv')
xtream_bp = Blueprint('xtream', __name__)

_SESSION_TTL_MINUTES        = 5
_SESSION_TTL_STREAM_MINUTES = 240   # 4h para VOD


# ════════════════════════════════════════════════════════════════
# HELPERS COMUNES
# ════════════════════════════════════════════════════════════════

def _auth(username: str, password: str) -> IptvUser | None:
    u = IptvUser.query.filter_by(username=username, activo=True).first()
    if not u or not u.check_password(password) or u.is_expired:
        return None
    return u


def _session_cutoff(tipo: str | None = None) -> datetime:
    if tipo in ('pelicula', 'serie'):
        return datetime.utcnow() - timedelta(minutes=_SESSION_TTL_STREAM_MINUTES)
    return datetime.utcnow() - timedelta(minutes=_SESSION_TTL_MINUTES)


def _purge_old_sessions(iptv_user_id: int) -> None:
    from sqlalchemy import or_ as _or
    cutoff_live = datetime.utcnow() - timedelta(minutes=_SESSION_TTL_MINUTES)
    cutoff_vod  = datetime.utcnow() - timedelta(minutes=_SESSION_TTL_STREAM_MINUTES)
    dead_live = (
        IptvSession.query
        .outerjoin(Contenido, IptvSession.contenido_id == Contenido.id)
        .filter(
            IptvSession.iptv_user_id == iptv_user_id,
            _or(Contenido.tipo == 'live', Contenido.tipo.is_(None),
                IptvSession.contenido_id.is_(None)),
            IptvSession.last_heartbeat < cutoff_live,
        )
    )
    dead_vod = (
        IptvSession.query
        .join(Contenido, IptvSession.contenido_id == Contenido.id)
        .filter(
            IptvSession.iptv_user_id == iptv_user_id,
            Contenido.tipo.in_(('pelicula', 'serie')),
            IptvSession.last_heartbeat < cutoff_vod,
        )
    )
    for s in dead_live.all() + dead_vod.all():
        db.session.delete(s)
    db.session.commit()


def _active_sessions_count(iptv_user_id: int) -> int:
    from sqlalchemy import or_ as _or
    cutoff_live = datetime.utcnow() - timedelta(minutes=_SESSION_TTL_MINUTES)
    cutoff_vod  = datetime.utcnow() - timedelta(minutes=_SESSION_TTL_STREAM_MINUTES)
    live_count = (
        IptvSession.query
        .outerjoin(Contenido, IptvSession.contenido_id == Contenido.id)
        .filter(
            IptvSession.iptv_user_id == iptv_user_id,
            _or(Contenido.tipo == 'live', Contenido.tipo.is_(None),
                IptvSession.contenido_id.is_(None)),
            IptvSession.last_heartbeat >= cutoff_live,
        ).count()
    )
    vod_count = (
        IptvSession.query
        .join(Contenido, IptvSession.contenido_id == Contenido.id)
        .filter(
            IptvSession.iptv_user_id == iptv_user_id,
            Contenido.tipo.in_(('pelicula', 'serie')),
            IptvSession.last_heartbeat >= cutoff_vod,
        ).count()
    )
    return live_count + vod_count


# ════════════════════════════════════════════════════════════════
# /iptv/ — M3U clasico
# ════════════════════════════════════════════════════════════════

@iptv_bp.get('/<username>/<password>/info')
def info(username: str, password: str):
    u = _auth(username, password)
    if not u:
        return jsonify({'error': 'Credenciales incorrectas o suscripcion caducada'}), 401
    _purge_old_sessions(u.id)
    return jsonify({
        'username':        u.username,
        'plan':            u.plan_label,
        'expires_at':      u.expires_at.strftime('%d/%m/%Y') if u.expires_at else '-',
        'max_connections': u.max_connections,
        'active_sessions': _active_sessions_count(u.id),
    })


@iptv_bp.get('/<username>/<password>/playlist.m3u')
def playlist(username: str, password: str):
    u = _auth(username, password)
    if not u:
        abort(401)
    base = request.host_url.rstrip('/')
    from sqlalchemy import case as _case
    tipo_orden = _case(
        (Contenido.tipo == 'live', 0),
        (Contenido.tipo == 'pelicula', 1),
        (Contenido.tipo == 'serie', 2),
        else_=3,
    )
    _tipo_grp = {'live': 'Directo', 'pelicula': 'Peliculas', 'serie': 'Series'}
    lista_def = Lista.query.filter_by(es_defecto=True).first()
    q = db.session.query(
        Contenido.id, Contenido.titulo, Contenido.tipo,
        Contenido.imagen, Contenido.group_title,
    ).filter(Contenido.activo == True)
    if lista_def:
        from sqlalchemy import or_ as _or
        q = q.filter(_or(
            Contenido.tipo != 'live',
            Contenido.lista_id == lista_def.id,
        ))
    if u.grupos_permitidos:
        try:
            gs = set(_json.loads(u.grupos_permitidos))
            if gs:
                q = q.filter(Contenido.group_title.in_(list(gs)))
        except (ValueError, TypeError):
            pass
    filas = q.order_by(tipo_orden, Contenido.group_title, Contenido.titulo).all()
    lines = ['#EXTM3U x-tvg-url=""']
    for cid, titulo, tipo, imagen, group_title in filas:
        img = (imagen or '').replace('"', '')
        grp = (group_title or _tipo_grp.get(tipo, 'General')).replace('"', '')
        tit = (titulo or '').replace(',', ' ').replace('"', '')
        ext = '.ts' if tipo == 'live' else '.mp4' if tipo == 'pelicula' else '.mkv'
        stream_url = f'{base}/iptv/{username}/{password}/stream/{cid}{ext}'
        lines.append(
            f'#EXTINF:-1 tvg-id="CC{cid}" tvg-name="{tit}" '
            f'tvg-logo="{img}" group-title="{grp}",{tit}'
        )
        lines.append(stream_url)
    return Response(
        '\n'.join(lines) + '\n',
        mimetype='audio/x-mpegurl',
        headers={'Content-Disposition': f'attachment; filename="{username}.m3u"'},
    )


@iptv_bp.get('/<username>/<password>/stream/<path:cid_str>')
def stream(username: str, password: str, cid_str: str):
    u = _auth(username, password)
    if not u:
        abort(401)
    try:
        contenido_id = int(cid_str.split('.')[0])
    except (ValueError, AttributeError):
        abort(404)
    c = Contenido.query.get_or_404(contenido_id)
    _purge_old_sessions(u.id)
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    cutoff = _session_cutoff(c.tipo)
    sesion = IptvSession.query.filter(
        IptvSession.iptv_user_id == u.id,
        IptvSession.ip_address == ip,
        IptvSession.last_heartbeat >= cutoff,
    ).first()
    if sesion:
        sesion.contenido_id   = contenido_id
        sesion.last_heartbeat = datetime.utcnow()
        db.session.commit()
    else:
        if _active_sessions_count(u.id) >= u.max_connections:
            return Response(
                '#EXTM3U\n#EXTINF:-1,Limite de conexiones alcanzado\n'
                'http://invalid/limite_conexiones\n',
                mimetype='audio/x-mpegurl', status=403,
            )
        db.session.add(IptvSession(
            iptv_user_id=u.id, contenido_id=contenido_id, ip_address=ip,
        ))
        db.session.commit()
    cfg = _xtream_cfg()
    return _do_stream(c, cfg)


@iptv_bp.post('/<username>/<password>/heartbeat/<token>')
def heartbeat(username: str, password: str, token: str):
    u = _auth(username, password)
    if not u:
        return jsonify({'ok': False}), 401
    sesion = IptvSession.query.filter_by(
        iptv_user_id=u.id, session_token=token,
    ).first()
    if sesion:
        sesion.last_heartbeat = datetime.utcnow()
        db.session.commit()
    return jsonify({'ok': True})


# ════════════════════════════════════════════════════════════════
# XTREAM CODES — helpers internos
# ════════════════════════════════════════════════════════════════

def _xtream_cfg() -> XtreamConfig:
    """Config singleton (id=1). La crea con defaults si no existe."""
    cfg = XtreamConfig.query.get(1)
    if cfg is None:
        cfg = XtreamConfig(id=1)
        db.session.add(cfg)
        db.session.commit()
    return cfg


def _do_stream(c: Contenido, cfg: XtreamConfig):
    """302 redirect directo al proveedor, o al stream-proxy del VPS."""
    if cfg.stream_mode == 'proxy':
        return redirect(f'/api/stream-proxy?url={_quote(c.url_stream, safe="")}', code=302)
    return redirect(c.url_stream, code=302)


def _build_account_info(u: IptvUser, base: str) -> dict:
    exp  = int(u.expires_at.timestamp()) if u.expires_at else 9999999999
    now  = datetime.utcnow()
    host = base.split('://')[-1].split('/')[0].split(':')[0]
    return {
        'user_info': {
            'username':               u.username,
            'password':               u.password_plain or '',
            'message':                'Welcome to CineCadiz IPTV',
            'auth':                   1,
            'status':                 'Active' if not u.is_expired else 'Expired',
            'exp_date':               str(exp),
            'is_trial':               '0',
            'active_cons':            str(_active_sessions_count(u.id)),
            'created_at':             str(int(u.fecha_creacion.timestamp())),
            'max_connections':        str(u.max_connections),
            'allowed_output_formats': ['m3u8', 'ts', 'rtmp'],
        },
        'server_info': {
            'url':             host,
            'port':            '80',
            'https_port':      '443',
            'server_protocol': 'https' if base.startswith('https') else 'http',
            'rtmp_port':       '1935',
            'timezone':        'Europe/Madrid',
            'timestamp_now':   int(now.timestamp()),
            'time_now':        now.strftime('%Y-%m-%d %H:%M:%S'),
        },
    }


def _user_q(u: IptvUser, tipo: str):
    q = db.session.query(Contenido).filter(
        Contenido.activo == True, Contenido.tipo == tipo,
    )
    if tipo == 'live':
        lista_def = Lista.query.filter_by(es_defecto=True).first()
        if lista_def:
            q = q.filter(Contenido.lista_id == lista_def.id)
    if u.grupos_permitidos:
        try:
            gs = set(_json.loads(u.grupos_permitidos))
            if gs:
                q = q.filter(Contenido.group_title.in_(list(gs)))
        except (ValueError, TypeError):
            pass
    return q


def _cat_map(tipo: str) -> dict:
    rows = (
        db.session.query(Contenido.group_title)
        .filter(Contenido.activo == True, Contenido.tipo == tipo,
                Contenido.group_title != None, Contenido.group_title != '')
        .distinct().order_by(Contenido.group_title).all()
    )
    return {r[0]: str(i + 1) for i, r in enumerate(rows)}


def _file_ext(url_stream: str, fallback: str = 'mp4') -> str:
    path = (url_stream or '').split('?')[0]
    if '.' in path:
        ext = path.rsplit('.', 1)[-1].lower()
        if ext in ('mp4', 'mkv', 'avi', 'mov', 'webm', 'm4v', 'ts'):
            return ext
    return fallback


_EP_PAT = _re.compile(r'\s*[Ss]\d{1,2}[Ee]\d{1,3}.*$')


def _xtream_dispatch(username: str, password: str, cid_str: str,
                     allowed_tipo: str | None = None):
    """Auth + control de conexiones + stream (directo o proxy)."""
    u = _auth(username, password)
    if not u:
        abort(401)
    try:
        cid = int(cid_str.split('.')[0])
    except (ValueError, AttributeError):
        abort(404)
    c = Contenido.query.get_or_404(cid)
    if not c.activo or (allowed_tipo and c.tipo != allowed_tipo):
        abort(404)
    _purge_old_sessions(u.id)
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    cutoff = _session_cutoff(c.tipo)
    sesion = IptvSession.query.filter(
        IptvSession.iptv_user_id == u.id,
        IptvSession.ip_address == ip,
        IptvSession.last_heartbeat >= cutoff,
    ).first()
    if sesion:
        sesion.contenido_id   = cid
        sesion.last_heartbeat = datetime.utcnow()
        db.session.commit()
    else:
        if _active_sessions_count(u.id) >= u.max_connections:
            abort(403)
        db.session.add(IptvSession(iptv_user_id=u.id, contenido_id=cid, ip_address=ip))
        db.session.commit()
    return _do_stream(c, _xtream_cfg())


# ════════════════════════════════════════════════════════════════
# XTREAM CODES — endpoints publicos
# ════════════════════════════════════════════════════════════════

# ── get.php (legacy M3U) ──────────────────────────────────────────

@xtream_bp.get('/get.php')
def get_php():
    username = request.args.get('username', '').strip()
    password = request.args.get('password', '').strip()
    type_    = request.args.get('type', 'm3u_plus')
    if not username or not password:
        abort(400)
    u = _auth(username, password)
    if not u:
        abort(401)
    if type_ not in ('m3u_plus', 'm3u'):
        abort(400)
    base = request.host_url.rstrip('/')
    from sqlalchemy import case as _case
    tipo_orden = _case(
        (Contenido.tipo == 'live', 0),
        (Contenido.tipo == 'pelicula', 1),
        (Contenido.tipo == 'serie', 2),
        else_=3,
    )
    _tipo_grp = {'live': 'Directo', 'pelicula': 'Peliculas', 'serie': 'Series'}
    lista_def = Lista.query.filter_by(es_defecto=True).first()
    q = db.session.query(
        Contenido.id, Contenido.titulo, Contenido.tipo,
        Contenido.imagen, Contenido.group_title,
    ).filter(Contenido.activo == True)
    if lista_def:
        from sqlalchemy import or_ as _or
        q = q.filter(_or(
            Contenido.tipo != 'live',
            Contenido.lista_id == lista_def.id,
        ))
    if u.grupos_permitidos:
        try:
            gs = set(_json.loads(u.grupos_permitidos))
            if gs:
                q = q.filter(Contenido.group_title.in_(list(gs)))
        except (ValueError, TypeError):
            pass
    filas = q.order_by(tipo_orden, Contenido.group_title, Contenido.titulo).all()
    lines = ['#EXTM3U x-tvg-url=""']
    for cid, titulo, tipo, imagen, group_title in filas:
        img = (imagen or '').replace('"', '')
        grp = (group_title or _tipo_grp.get(tipo, 'General')).replace('"', '')
        tit = (titulo or '').replace(',', ' ').replace('"', '')
        ext = '.ts' if tipo == 'live' else '.mp4' if tipo == 'pelicula' else '.mkv'
        stream_url = f'{base}/iptv/{username}/{password}/stream/{cid}{ext}'
        lines.append(
            f'#EXTINF:-1 tvg-id="CC{cid}" tvg-name="{tit}" '
            f'tvg-logo="{img}" group-title="{grp}",{tit}'
        )
        lines.append(stream_url)
    return Response(
        '\n'.join(lines) + '\n',
        mimetype='audio/x-mpegurl',
        headers={'Content-Disposition': f'attachment; filename="{username}.m3u"'},
    )


# ── player_api.php (Xtream JSON API) ─────────────────────────────

@xtream_bp.get('/player_api.php')
@xtream_bp.post('/player_api.php')
def player_api():
    username = request.values.get('username', '').strip()
    password = request.values.get('password', '').strip()
    action   = request.values.get('action',   '').strip()

    u = _auth(username, password)
    if not u:
        return jsonify({'user_info': {'auth': 0}}), 401

    cfg  = _xtream_cfg()
    base = request.host_url.rstrip('/')

    # Sin action → info de cuenta/servidor
    if not action:
        return jsonify(_build_account_info(u, base))

    # ── Categorias live ───────────────────────────────────────
    if action == 'get_live_categories':
        if not cfg.live_enabled:
            return jsonify([])
        cm = _cat_map('live')
        return jsonify([
            {'category_id': cid, 'category_name': grp, 'parent_id': 0}
            for grp, cid in cm.items()
        ])

    # ── Streams live ──────────────────────────────────────────
    if action == 'get_live_streams':
        if not cfg.live_enabled:
            return jsonify([])
        cm    = _cat_map('live')
        items = _user_q(u, 'live').order_by(Contenido.group_title, Contenido.titulo).all()
        return jsonify([{
            'num':                 idx + 1,
            'name':                c.titulo,
            'stream_type':         'live',
            'stream_id':           c.id,
            'stream_icon':         c.imagen or '',
            'epg_channel_id':      '',
            'added':               str(int(c.fecha_agregado.timestamp())) if c.fecha_agregado else '0',
            'category_id':         cm.get(c.group_title or '', '1'),
            'custom_sid':          '',
            'tv_archive':          0,
            'direct_source':       '',
            'tv_archive_duration': 0,
        } for idx, c in enumerate(items)])

    # ── Categorias VOD ────────────────────────────────────────
    if action == 'get_vod_categories':
        if not cfg.vod_enabled:
            return jsonify([])
        cm = _cat_map('pelicula')
        return jsonify([
            {'category_id': cid, 'category_name': grp, 'parent_id': 0}
            for grp, cid in cm.items()
        ])

    # ── Streams VOD ───────────────────────────────────────────
    if action == 'get_vod_streams':
        if not cfg.vod_enabled:
            return jsonify([])
        cm    = _cat_map('pelicula')
        items = _user_q(u, 'pelicula').order_by(Contenido.titulo).all()
        result = []
        for idx, c in enumerate(items):
            ext = _file_ext(c.url_stream, 'mp4')
            result.append({
                'num':                 idx + 1,
                'name':                c.titulo,
                'stream_type':         'movie',
                'stream_id':           c.id,
                'stream_icon':         c.imagen or '',
                'rating':              '',
                'rating_5based':       0,
                'added':               str(int(c.fecha_agregado.timestamp())) if c.fecha_agregado else '0',
                'category_id':         cm.get(c.group_title or '', '1'),
                'container_extension': ext,
                'custom_sid':          '',
                'direct_source':       '',
            })
        return jsonify(result)

    # ── Categorias series ─────────────────────────────────────
    if action == 'get_series_categories':
        if not cfg.series_enabled:
            return jsonify([])
        cm = _cat_map('serie')
        return jsonify([
            {'category_id': cid, 'category_name': grp, 'parent_id': 0}
            for grp, cid in cm.items()
        ])

    # ── Series (agrupadas por titulo base) ────────────────────
    if action == 'get_series':
        if not cfg.series_enabled:
            return jsonify([])
        cm    = _cat_map('serie')
        items = _user_q(u, 'serie').order_by(Contenido.titulo).all()
        seen: dict[str, dict] = {}
        for c in items:
            base_title = _EP_PAT.sub('', c.titulo).strip() or c.titulo
            if base_title not in seen:
                seen[base_title] = {
                    'series_id':       c.id,
                    'name':            base_title,
                    'cover':           c.imagen or '',
                    'plot':            c.descripcion or '',
                    'cast':            '',
                    'director':        '',
                    'genre':           c.genero or '',
                    'release_date':    str(c.año) if c.año else '',
                    'last_modified':   str(int(c.fecha_agregado.timestamp())) if c.fecha_agregado else '0',
                    'rating':          '',
                    'rating_5based':   0,
                    'backdrop_path':   [],
                    'youtube_trailer': '',
                    'episode_run_time': '',
                    'category_id':     cm.get(c.group_title or '', '1'),
                }
        return jsonify(list(seen.values()))

    # ── Info de serie (episodios por temporada) ───────────────
    if action == 'get_series_info':
        if not cfg.series_enabled:
            return jsonify({})
        try:
            sid = int(request.values.get('series_id', 0))
        except (ValueError, TypeError):
            return jsonify({})
        root = Contenido.query.get(sid)
        if not root or root.tipo != 'serie':
            return jsonify({})
        base_title = _EP_PAT.sub('', root.titulo).strip() or root.titulo
        eps = (
            Contenido.query
            .filter(Contenido.activo == True, Contenido.tipo == 'serie',
                    Contenido.titulo.like(f'{base_title}%'))
            .order_by(Contenido.temporada, Contenido.episodio, Contenido.titulo)
            .all()
        )
        seasons: dict[str, list] = {}
        for c in eps:
            s   = str(c.temporada or 1)
            ext = _file_ext(c.url_stream, 'mkv')
            seasons.setdefault(s, []).append({
                'id':                  c.id,
                'episode_num':         c.episodio or 1,
                'title':               c.titulo,
                'container_extension': ext,
                'info': {
                    'plot':        c.descripcion or '',
                    'releasedate': str(c.año) if c.año else '',
                    'rating':      '',
                    'duration_secs': 0,
                    'duration':    '00:00:00',
                    'movie_image': c.imagen or '',
                },
                'added':         str(int(c.fecha_agregado.timestamp())) if c.fecha_agregado else '0',
                'season':        c.temporada or 1,
                'direct_source': '',
            })
        return jsonify({
            'info': {
                'name':          base_title,
                'cover':         root.imagen or '',
                'plot':          root.descripcion or '',
                'cast':          '',
                'director':      '',
                'genre':         root.genero or '',
                'release_date':  str(root.año) if root.año else '',
                'last_modified': '',
                'rating':        '',
                'category_id':   '1',
                'backdrop_path': [],
            },
            'episodes': seasons,
        })

    # Accion desconocida -> lista vacia (no rompe la app)
    return jsonify([])


# ── xmltv.php — EPG stub ──────────────────────────────────────────

@xtream_bp.get('/xmltv.php')
def xmltv():
    if not _auth(
        request.args.get('username', '').strip(),
        request.args.get('password', '').strip(),
    ):
        abort(401)
    return Response(
        '<?xml version="1.0" encoding="utf-8"?>\n<tv generator-info-name="CineCadiz"></tv>\n',
        mimetype='application/xml',
    )


# ── Stream endpoints Xtream ───────────────────────────────────────

@xtream_bp.get('/<username>/<password>/<path:stream_id_str>')
def xtream_live(username: str, password: str, stream_id_str: str):
    """Live: /<user>/<pass>/<id>  o  /<user>/<pass>/<id>.ts/.m3u8"""
    return _xtream_dispatch(username, password, stream_id_str, 'live')


@xtream_bp.get('/movie/<username>/<password>/<path:stream_id_str>')
def xtream_movie(username: str, password: str, stream_id_str: str):
    """VOD: /movie/<user>/<pass>/<id>.mp4"""
    return _xtream_dispatch(username, password, stream_id_str, 'pelicula')


@xtream_bp.get('/series/<username>/<password>/<path:stream_id_str>')
def xtream_series_ep(username: str, password: str, stream_id_str: str):
    """Episodio: /series/<user>/<pass>/<id>.mkv"""
    return _xtream_dispatch(username, password, stream_id_str, 'serie')
