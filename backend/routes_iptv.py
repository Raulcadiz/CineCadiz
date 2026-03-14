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

_SESSION_TTL_MINUTES = 2   # sesión caduca si no hay heartbeat en 2 min


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


def _purge_old_sessions(iptv_user_id: int) -> None:
    """Elimina sesiones con heartbeat más antiguo que TTL."""
    cutoff = datetime.utcnow() - timedelta(minutes=_SESSION_TTL_MINUTES)
    IptvSession.query.filter(
        IptvSession.iptv_user_id == iptv_user_id,
        IptvSession.last_heartbeat < cutoff,
    ).delete(synchronize_session=False)
    db.session.commit()


def _active_sessions_count(iptv_user_id: int) -> int:
    cutoff = datetime.utcnow() - timedelta(minutes=_SESSION_TTL_MINUTES)
    return IptvSession.query.filter(
        IptvSession.iptv_user_id == iptv_user_id,
        IptvSession.last_heartbeat >= cutoff,
    ).count()


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
    """Genera una playlist M3U con todos los canales live activos."""
    u = _auth(username, password)
    if not u:
        abort(401)

    canales = (
        Contenido.query
        .filter_by(tipo='live', activo=True)
        .order_by(Contenido.group_title, Contenido.titulo)
        .all()
    )

    base = request.host_url.rstrip('/')
    lines = ['#EXTM3U']
    for c in canales:
        img = c.imagen or ''
        grp = c.group_title or 'General'
        stream_url = f'{base}/iptv/{username}/{password}/stream/{c.id}'
        lines.append(
            f'#EXTINF:-1 tvg-logo="{img}" group-title="{grp}",{c.titulo}'
        )
        lines.append(stream_url)

    content = '\n'.join(lines) + '\n'
    return Response(
        content,
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

    # Buscar sesión existente de esta IP para este usuario
    cutoff = datetime.utcnow() - timedelta(minutes=_SESSION_TTL_MINUTES)
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
