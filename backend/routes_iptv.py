"""
Servicio IPTV externo — /iptv/
Los usuarios IPTV acceden con su usuario+contraseña para obtener su playlist
personalizada y reproducir canales (con control de conexiones simultáneas).

Endpoints públicos (sin sesión web):
  GET  /iptv/<user>/<pass>/playlist.m3u         → playlist M3U personalizada
  GET  /iptv/<user>/<pass>/stream/<int:id>       → redirige al stream (controla conexiones)
  POST /iptv/<user>/<pass>/heartbeat/<token>     → mantiene sesión activa
  GET  /iptv/<user>/<pass>/info                  → JSON con datos del plan

Limpieza de sesiones caducadas: automática al crear sesión nueva.
"""
import secrets
from datetime import datetime, timedelta

import requests as _requests
from flask import Blueprint, Response, abort, jsonify, redirect, request

from models import db, Contenido, IptvUser, IptvSession

iptv_bp = Blueprint('iptv', __name__, url_prefix='/iptv')

# Blueprint para compatibilidad Xtream Codes API (/get.php)
xtream_bp = Blueprint('xtream', __name__)

_SESSION_TTL_MINUTES = 5   # sesión caduca si no hay heartbeat en 5 min
# Para live: las apps IPTV hacen peticiones frecuentes → caduca rápido
# Para pelicula/serie: el cliente hace una sola petición → la sesión dura más
_SESSION_TTL_STREAM_MINUTES = 240  # 4h para VOD (película/serie)


# ── Helpers ─────────────────────────────────────────────────────

def _auth(username: str, password: str) -> IptvUser | None:
    """Autentica un usuario IPTV. Devuelve el objeto o None."""
    u = IptvUser.query.filter_by(username=username, activo=True).first()
    if not u:
        return None
    if not u.check_password(password):
        return None
    if u.is_expired:
        return None
    return u


def _session_cutoff(tipo: str | None = None) -> datetime:
    """Devuelve el datetime límite según el tipo de contenido."""
    if tipo in ('pelicula', 'serie'):
        return datetime.utcnow() - timedelta(minutes=_SESSION_TTL_STREAM_MINUTES)
    return datetime.utcnow() - timedelta(minutes=_SESSION_TTL_MINUTES)


def _purge_old_sessions(iptv_user_id: int) -> None:
    """Elimina sesiones caducadas (live > 5 min, VOD > 4h sin actividad)."""
    from sqlalchemy import or_ as _or, and_ as _and
    from models import Contenido as _C
    cutoff_live = datetime.utcnow() - timedelta(minutes=_SESSION_TTL_MINUTES)
    cutoff_vod  = datetime.utcnow() - timedelta(minutes=_SESSION_TTL_STREAM_MINUTES)

    # Sesiones cuyo contenido es live (o NULL) y han caducado por TTL corto
    dead_live = (
        IptvSession.query
        .outerjoin(_C, IptvSession.contenido_id == _C.id)
        .filter(
            IptvSession.iptv_user_id == iptv_user_id,
            _or(_C.tipo == 'live', _C.tipo.is_(None), IptvSession.contenido_id.is_(None)),
            IptvSession.last_heartbeat < cutoff_live,
        )
    )
    # Sesiones VOD caducadas por TTL largo
    dead_vod = (
        IptvSession.query
        .join(_C, IptvSession.contenido_id == _C.id)
        .filter(
            IptvSession.iptv_user_id == iptv_user_id,
            _C.tipo.in_(('pelicula', 'serie')),
            IptvSession.last_heartbeat < cutoff_vod,
        )
    )
    for s in dead_live.all() + dead_vod.all():
        db.session.delete(s)
    db.session.commit()


def _active_sessions_count(iptv_user_id: int) -> int:
    """Cuenta sesiones vivas (respeta TTL diferenciado por tipo)."""
    from sqlalchemy import or_ as _or
    from models import Contenido as _C
    cutoff_live = datetime.utcnow() - timedelta(minutes=_SESSION_TTL_MINUTES)
    cutoff_vod  = datetime.utcnow() - timedelta(minutes=_SESSION_TTL_STREAM_MINUTES)
    live_count = (
        IptvSession.query
        .outerjoin(_C, IptvSession.contenido_id == _C.id)
        .filter(
            IptvSession.iptv_user_id == iptv_user_id,
            _or(_C.tipo == 'live', _C.tipo.is_(None), IptvSession.contenido_id.is_(None)),
            IptvSession.last_heartbeat >= cutoff_live,
        ).count()
    )
    vod_count = (
        IptvSession.query
        .join(_C, IptvSession.contenido_id == _C.id)
        .filter(
            IptvSession.iptv_user_id == iptv_user_id,
            _C.tipo.in_(('pelicula', 'serie')),
            IptvSession.last_heartbeat >= cutoff_vod,
        ).count()
    )
    return live_count + vod_count


# ── Endpoints ───────────────────────────────────────────────────

@iptv_bp.get('/<username>/<password>/info')
def info(username: str, password: str):
    u = _auth(username, password)
    if not u:
        return jsonify({'error': 'Credenciales incorrectas o suscripción caducada'}), 401
    _purge_old_sessions(u.id)
    return jsonify({
        'username':        u.username,
        'plan':            u.plan_label,
        'expires_at':      u.expires_at.strftime('%d/%m/%Y') if u.expires_at else '—',
        'max_connections': u.max_connections,
        'active_sessions': _active_sessions_count(u.id),
    })


@iptv_bp.get('/<username>/<password>/playlist.m3u')
def playlist(username: str, password: str):
    """
    Genera una playlist M3U con todo el contenido activo, ordenado:
      1. Directo (live)  → grupo real del canal
      2. Películas       → grupo real o 'Películas'
      3. Series          → grupo real o 'Series'
    Usa streaming de respuesta para no cargar los 20k+ items en RAM.
    """
    u = _auth(username, password)
    if not u:
        abort(401)

    base = request.host_url.rstrip('/')

    import json as _json
    from sqlalchemy import case as _case
    tipo_orden = _case(
        {'live': 0, 'pelicula': 1, 'serie': 2},
        value=Contenido.tipo,
        else_=3,
    )

    _tipo_grp = {'live': 'Directo', 'pelicula': 'Películas', 'serie': 'Series'}

    # Obtener solo los campos necesarios como tuplas ligeras (no instancias ORM completas)
    # para poder cerrar la sesión de BD antes de hacer el streaming de respuesta.
    q = (
        db.session.query(
            Contenido.id,
            Contenido.titulo,
            Contenido.tipo,
            Contenido.imagen,
            Contenido.group_title,
        )
        .filter(Contenido.activo == True)
    )

    # Filtrar por grupos asignados al usuario IPTV (si tiene restricción)
    if u.grupos_permitidos:
        try:
            grupos_set = set(_json.loads(u.grupos_permitidos))
            if grupos_set:
                q = q.filter(Contenido.group_title.in_(list(grupos_set)))
        except (ValueError, TypeError):
            pass

    filas = q.order_by(tipo_orden, Contenido.group_title, Contenido.titulo).all()

    lines = ['#EXTM3U x-tvg-url=""']
    for cid, titulo, tipo, imagen, group_title in filas:
        img = (imagen or '').replace('"', '')
        # Para canales live: usar el group_title original del canal
        # Para VOD (pelicula/serie): usar nombre de categoría reconocible por apps IPTV
        if tipo == 'live':
            grp = (group_title or 'Directo').replace('"', '')
        else:
            grp = _tipo_grp.get(tipo, group_title or 'General').replace('"', '')
        tit   = (titulo or '').replace(',', ' ').replace('"', '')
        tvgid = f'CC{cid}'
        # Live → .ts (formato nativo IPTV), pelicula → .mp4, serie → .mkv
        ext   = '.ts' if tipo == 'live' else '.mp4' if tipo == 'pelicula' else '.mkv'
        stream_url = f'{base}/iptv/{username}/{password}/stream/{cid}{ext}'
        lines.append(
            f'#EXTINF:-1 tvg-id="{tvgid}" tvg-name="{tit}" '
            f'tvg-logo="{img}" group-title="{grp}",{tit}'
        )
        lines.append(stream_url)

    content = '\n'.join(lines) + '\n'
    return Response(
        content,
        mimetype='audio/x-mpegurl',
        headers={'Content-Disposition': f'attachment; filename="{username}.m3u"'},
    )


@iptv_bp.get('/<username>/<password>/stream/<path:cid_str>')
def stream(username: str, password: str, cid_str: str):
    """
    Controla conexiones simultáneas y redirige al stream real.
    Crea una sesión nueva (o reutiliza la del mismo token en cookie).
    """
    u = _auth(username, password)
    if not u:
        abort(401)

    # Extraer ID numérico ignorando extensión (.mp4, .mkv, etc.)
    try:
        contenido_id = int(cid_str.split('.')[0])
    except (ValueError, AttributeError):
        abort(404)

    c = Contenido.query.get_or_404(contenido_id)

    _purge_old_sessions(u.id)

    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()

    # Buscar sesión existente de esta IP para este usuario (TTL según tipo)
    cutoff = _session_cutoff(c.tipo)
    sesion = IptvSession.query.filter(
        IptvSession.iptv_user_id == u.id,
        IptvSession.ip_address == ip,
        IptvSession.last_heartbeat >= cutoff,
    ).first()

    if sesion:
        # Reutilizar sesión existente (mismo dispositivo cambia de canal)
        sesion.contenido_id   = contenido_id
        sesion.last_heartbeat = datetime.utcnow()
        db.session.commit()
    else:
        # Nueva sesión — comprobar límite
        n_activas = _active_sessions_count(u.id)
        if n_activas >= u.max_connections:
            return Response(
                '#EXTM3U\n#EXTINF:-1,Límite de conexiones alcanzado\n'
                'http://invalid/limite_conexiones\n',
                mimetype='audio/x-mpegurl',
                status=403,
            )
        sesion = IptvSession(
            iptv_user_id=u.id,
            contenido_id=contenido_id,
            ip_address=ip,
        )
        db.session.add(sesion)
        db.session.commit()

    return redirect(c.url_stream, code=302)


@iptv_bp.post('/<username>/<password>/heartbeat/<token>')
def heartbeat(username: str, password: str, token: str):
    """Las apps IPTV pueden llamar aquí cada ~60s para mantener la sesión activa."""
    u = _auth(username, password)
    if not u:
        return jsonify({'ok': False}), 401

    sesion = IptvSession.query.filter_by(
        iptv_user_id=u.id, session_token=token
    ).first()
    if sesion:
        sesion.last_heartbeat = datetime.utcnow()
        db.session.commit()
    return jsonify({'ok': True})


# ── Compatibilidad Xtream Codes API ─────────────────────────────

@xtream_bp.get('/get.php')
def get_php():
    """
    Endpoint de compatibilidad con formato Xtream Codes.
    Soporta: /get.php?username=USER&password=PASS&type=m3u_plus&output=ts
    Redirige internamente a la playlist M3U del usuario.
    """
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

    import json as _json
    from sqlalchemy import case as _case
    tipo_orden = _case(
        {'live': 0, 'pelicula': 1, 'serie': 2},
        value=Contenido.tipo,
        else_=3,
    )
    _tipo_grp = {'live': 'Directo', 'pelicula': 'Películas', 'serie': 'Series'}

    q = (
        db.session.query(
            Contenido.id,
            Contenido.titulo,
            Contenido.tipo,
            Contenido.imagen,
            Contenido.group_title,
        )
        .filter(Contenido.activo == True)
    )

    if u.grupos_permitidos:
        try:
            grupos_set = set(_json.loads(u.grupos_permitidos))
            if grupos_set:
                q = q.filter(Contenido.group_title.in_(list(grupos_set)))
        except (ValueError, TypeError):
            pass

    filas = q.order_by(tipo_orden, Contenido.group_title, Contenido.titulo).all()

    lines = ['#EXTM3U x-tvg-url=""']
    for cid, titulo, tipo, imagen, group_title in filas:
        img = (imagen or '').replace('"', '')
        # Para canales live: usar el group_title original del canal
        # Para VOD (pelicula/serie): usar nombre de categoría reconocible por apps IPTV
        if tipo == 'live':
            grp = (group_title or 'Directo').replace('"', '')
        else:
            grp = _tipo_grp.get(tipo, group_title or 'General').replace('"', '')
        tit   = (titulo or '').replace(',', ' ').replace('"', '')
        tvgid = f'CC{cid}'
        # Live → .ts (formato nativo IPTV), pelicula → .mp4, serie → .mkv
        ext   = '.ts' if tipo == 'live' else '.mp4' if tipo == 'pelicula' else '.mkv'
        stream_url = f'{base}/iptv/{username}/{password}/stream/{cid}{ext}'
        lines.append(
            f'#EXTINF:-1 tvg-id="{tvgid}" tvg-name="{tit}" '
            f'tvg-logo="{img}" group-title="{grp}",{tit}'
        )
        lines.append(stream_url)

    content = '\n'.join(lines) + '\n'
    return Response(
        content,
        mimetype='audio/x-mpegurl',
        headers={'Content-Disposition': f'attachment; filename="{username}.m3u"'},
    )
