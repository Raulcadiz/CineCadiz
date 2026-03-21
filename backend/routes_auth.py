"""
Autenticación pública — /login, /logout, /registro/<token>, /mi-cuenta
Accesible tanto para usuarios normales como para premium/superadmin.
"""
import secrets
from datetime import datetime
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash, current_app, jsonify,
)

from models import db, User, InviteToken, Ticket, UserSession

auth_bp = Blueprint('auth', __name__)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def get_current_user() -> User | None:
    """Devuelve el User de la sesión activa, o None."""
    user_id = session.get('user_id')
    return User.query.get(user_id) if user_id else None


def login_required_any(f):
    """Decorator: requiere cualquier usuario autenticado (cualquier rol)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def _refresh_user_session(user: User) -> None:
    """Crea/actualiza UserSession y almacena session_key en la sesión Flask."""
    sk = session.get('session_key') or secrets.token_urlsafe(32)
    us = UserSession.query.filter_by(session_key=sk).first()
    if not us:
        us = UserSession(
            user_id=user.id,
            session_key=sk,
            ip_address=request.remote_addr,
            user_agent=(request.user_agent.string or '')[:255],
        )
        db.session.add(us)
    else:
        us.last_seen  = datetime.utcnow()
        us.ip_address = request.remote_addr
    user.last_seen = datetime.utcnow()
    db.session.commit()
    session['session_key'] = sk


# ═══════════════════════════════════════════════════════════
# LOGIN / LOGOUT
# ═══════════════════════════════════════════════════════════

@auth_bp.get('/login')
def login():
    if session.get('user_id'):
        user = get_current_user()
        if user and user.is_premium:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('index'))
    return render_template('auth/login.html')


@auth_bp.post('/login')
def login_post():
    username = request.form.get('usuario', '').strip()
    password = request.form.get('password', '')

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password) or not user.activo:
        flash('Usuario o contraseña incorrectos.', 'danger')
        return redirect(url_for('auth.login'))

    session.clear()
    session['user_id']   = user.id
    session['user_role'] = user.role
    session['username']  = user.username
    session.permanent = True

    _refresh_user_session(user)

    if user.is_premium:
        return redirect(url_for('admin.dashboard'))
    return redirect(url_for('index'))


@auth_bp.get('/logout')
def logout():
    sk = session.get('session_key')
    if sk:
        us = UserSession.query.filter_by(session_key=sk).first()
        if us:
            db.session.delete(us)
            db.session.commit()
    session.clear()
    return redirect(url_for('auth.login'))


# ═══════════════════════════════════════════════════════════
# REGISTRO CON TOKEN DE INVITACIÓN
# ═══════════════════════════════════════════════════════════

@auth_bp.get('/registro/<token>')
def registro(token):
    invite = InviteToken.query.filter_by(token=token, usado=False).first()
    if not invite:
        flash('Invitación inválida o ya utilizada.', 'danger')
        return redirect(url_for('auth.login'))
    creator = User.query.get(invite.created_by_id)
    return render_template(
        'auth/registro.html',
        token=token,
        role=invite.role_asignado,
        creator=creator,
    )


@auth_bp.post('/registro/<token>')
def registro_post(token):
    invite = InviteToken.query.filter_by(token=token, usado=False).first()
    if not invite:
        flash('Invitación inválida o ya utilizada.', 'danger')
        return redirect(url_for('auth.login'))

    username  = request.form.get('usuario', '').strip()
    password  = request.form.get('password', '')
    password2 = request.form.get('password2', '')

    if not username or len(username) < 3:
        flash('El nombre de usuario debe tener al menos 3 caracteres.', 'danger')
        return redirect(url_for('auth.registro', token=token))
    if User.query.filter_by(username=username).first():
        flash('Ese nombre de usuario ya está en uso.', 'danger')
        return redirect(url_for('auth.registro', token=token))
    if not password or len(password) < 6:
        flash('La contraseña debe tener al menos 6 caracteres.', 'danger')
        return redirect(url_for('auth.registro', token=token))
    if password != password2:
        flash('Las contraseñas no coinciden.', 'danger')
        return redirect(url_for('auth.registro', token=token))

    invite_limit = current_app.config.get('DEFAULT_INVITE_LIMIT', 10)
    user = User(
        username=username,
        role=invite.role_asignado,
        invite_limit=invite_limit,
        invited_by_id=invite.created_by_id,
    )
    user.set_password(password)
    db.session.add(user)

    invite.usado     = True
    invite.fecha_uso = datetime.utcnow()
    db.session.flush()      # obtener user.id antes del commit
    invite.used_by_id = user.id

    creator = User.query.get(invite.created_by_id)
    if creator:
        creator.invites_used += 1

    db.session.commit()
    flash(f'¡Cuenta creada! Bienvenido, {username}. Ya puedes iniciar sesión.', 'success')
    return redirect(url_for('auth.login'))


# ═══════════════════════════════════════════════════════════
# MI CUENTA
# ═══════════════════════════════════════════════════════════

@auth_bp.get('/mi-cuenta')
@login_required_any
def mi_cuenta():
    user = get_current_user()
    tokens = (
        InviteToken.query
        .filter_by(created_by_id=user.id, usado=False)
        .order_by(InviteToken.fecha_creacion.desc())
        .all()
    )
    used_tokens = (
        InviteToken.query
        .filter_by(created_by_id=user.id, usado=True)
        .order_by(InviteToken.fecha_uso.desc())
        .limit(10).all()
    )
    tickets = (
        Ticket.query
        .filter_by(user_id=user.id)
        .order_by(Ticket.fecha_creacion.desc())
        .limit(20).all()
    )
    return render_template(
        'auth/mi_cuenta.html',
        user=user,
        tokens=tokens,
        used_tokens=used_tokens,
        tickets=tickets,
    )


@auth_bp.post('/mi-cuenta/cambiar-password')
@login_required_any
def cambiar_password():
    user    = get_current_user()
    actual  = request.form.get('password_actual', '')
    nueva   = request.form.get('password_nueva', '')
    nueva2  = request.form.get('password_nueva2', '')

    if not user.check_password(actual):
        flash('La contraseña actual es incorrecta.', 'danger')
    elif len(nueva) < 6:
        flash('La nueva contraseña debe tener al menos 6 caracteres.', 'danger')
    elif nueva != nueva2:
        flash('Las contraseñas nuevas no coinciden.', 'danger')
    else:
        user.set_password(nueva)
        db.session.commit()
        flash('Contraseña actualizada correctamente.', 'success')

    return redirect(url_for('auth.mi_cuenta'))


@auth_bp.post('/mi-cuenta/crear-invitacion')
@login_required_any
def crear_invitacion():
    user = get_current_user()
    if not user or not user.can_invite:
        flash('No tienes invitaciones disponibles. Solicita más al administrador.', 'warning')
        return redirect(url_for('auth.mi_cuenta'))

    role_para = request.form.get('role', 'user')
    if role_para not in ('user', 'premium'):
        role_para = 'user'
    # Superadmin puede crear tokens para cualquier rol.
    # Premium puede invitar a 1 premium (solo si no tiene ya uno creado o usado).
    if role_para == 'premium' and not user.is_superadmin:
        if not user.is_premium:
            role_para = 'user'
        else:
            ya_premium = InviteToken.query.filter_by(
                created_by_id=user.id, role_asignado='premium'
            ).count()
            if ya_premium >= 1:
                flash('Solo puedes crear 1 invitación premium. Ya tienes una.', 'warning')
                return redirect(url_for('auth.mi_cuenta'))

    token = InviteToken(created_by_id=user.id, role_asignado=role_para)
    db.session.add(token)
    db.session.commit()

    flash('Invitación creada. Comparte el enlace con tu amigo.', 'success')
    return redirect(url_for('auth.mi_cuenta'))


@auth_bp.post('/mi-cuenta/eliminar-invitacion/<int:token_id>')
@login_required_any
def eliminar_invitacion(token_id):
    user  = get_current_user()
    token = InviteToken.query.filter_by(id=token_id, created_by_id=user.id, usado=False).first()
    if token:
        db.session.delete(token)
        db.session.commit()
        flash('Invitación eliminada.', 'success')
    return redirect(url_for('auth.mi_cuenta'))


@auth_bp.post('/mi-cuenta/enviar-ticket')
@login_required_any
def enviar_ticket():
    user    = get_current_user()
    tipo    = request.form.get('tipo', 'mas_invitaciones')
    mensaje = request.form.get('mensaje', '').strip()

    if not mensaje:
        flash('El mensaje no puede estar vacío.', 'danger')
        return redirect(url_for('auth.mi_cuenta'))

    ticket = Ticket(user_id=user.id, tipo=tipo, mensaje=mensaje)
    db.session.add(ticket)
    db.session.commit()
    flash('Ticket enviado. El administrador lo revisará pronto.', 'success')
    return redirect(url_for('auth.mi_cuenta'))


# ═══════════════════════════════════════════════════════════
# HEARTBEAT — tracking de usuarios online
# ═══════════════════════════════════════════════════════════

@auth_bp.post('/api/heartbeat')
def heartbeat():
    """
    El frontend llama a este endpoint cada ~30 s para mantener la sesión
    marcada como 'en línea'.  No requiere estar autenticado (usuarios anónimos
    también cuentan como visitas, aunque no se identifican por nombre).
    """
    user_id = session.get('user_id')
    sk      = session.get('session_key')

    if user_id and sk:
        us = UserSession.query.filter_by(session_key=sk).first()
        if us:
            us.last_seen = datetime.utcnow()
            user = User.query.get(user_id)
            if user:
                user.last_seen = datetime.utcnow()
            db.session.commit()

    return jsonify({'ok': True})
