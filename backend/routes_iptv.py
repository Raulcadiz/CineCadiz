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
    # Orden: live primero, luego pelicula, luego serie; dentro de cada tipo
    # ordenar por group_title y título.
    from sqlalchemy import case as _case
    tipo_orden = _case(
        {'live': 0, 'pelicula': 1, 'serie': 2},
        value=Contenido.tipo,
        else_=3,
    )
    q = (
        Contenido.query
        .filter_by(activo=True)
        .order_by(tipo_orden, Contenido.group_title, Contenido.titulo)
        .yield_per(500)   # procesa 500 filas a la vez sin cargar todo
    )

    _tipo_grp = {'live': 'Directo', 'pelicula': 'Películas', 'serie': 'Series'}

    def _generate():
        yield '#EXTM3U\n'
        for c in q:
            img = (c.imagen or '').replace('"', '')
            grp = (c.group_title or _tipo_grp.get(c.tipo, 'General')).replace('"', '')
            titulo = c.titulo.replace(',', ' ')
            stream_url = f'{base}/iptv/{username}/{password}/stream/{c.id}'
            yield f'#EXTINF:-1 tvg-logo="{img}" group-title="{grp}",{titulo}\n'
            yield f'{stream_url}\n'

    return Response(
        _generate(),
        mimetype='audio/x-mpegurl',
        headers={'Content-Disposition': f'attachment; filename="{username}.m3u"'},
    )


@iptv_bp.get('/<username>/<password>/stream/<int:contenido_id>')
def stream(username: str, password: str, contenido_id: int):
    """
    Controla conexiones simultáneas y redirige al stream real.
    Crea una sesión nueva (o reutiliza la del mismo token en cookie).
    """
    u = _auth(username, password)
    if not u:
        abort(401)

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
