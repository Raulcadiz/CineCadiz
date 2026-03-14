import secrets
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# ═══════════════════════════════════════════════════════════
# USUARIOS Y AUTENTICACIÓN
# ═══════════════════════════════════════════════════════════

class User(db.Model):
    """
    Usuario del sistema.
    Roles:
      superadmin – control total, límite de invitaciones ilimitado
      premium    – gestiona sus propias listas privadas + puede invitar usuarios
      user       – solo lectura (ve el contenido compartido)
    """
    __tablename__ = 'users'

    id             = db.Column(db.Integer, primary_key=True)
    username       = db.Column(db.String(50), unique=True, nullable=False)
    password_hash  = db.Column(db.String(255), nullable=False)
    role           = db.Column(db.String(20), nullable=False, default='user')
    invite_limit   = db.Column(db.Integer, nullable=False, default=10)
    invites_used   = db.Column(db.Integer, nullable=False, default=0)
    activo         = db.Column(db.Boolean, nullable=False, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen      = db.Column(db.DateTime, nullable=True)
    invited_by_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # ── Relaciones ────────────────────────────────────────
    invited_by = db.relationship(
        'User', remote_side=[id], foreign_keys=[invited_by_id],
    )
    listas = db.relationship(
        'Lista', foreign_keys='Lista.owner_id',
        backref='owner', lazy='dynamic',
    )
    fuentes_rss = db.relationship(
        'FuenteRSS', foreign_keys='FuenteRSS.owner_id',
        backref='owner', lazy='dynamic',
    )
    invite_tokens = db.relationship(
        'InviteToken', foreign_keys='InviteToken.created_by_id',
        backref='creator', lazy='dynamic',
    )
    sessions = db.relationship(
        'UserSession', backref='user', lazy='dynamic',
        cascade='all, delete-orphan',
    )
    tickets = db.relationship(
        'Ticket', foreign_keys='Ticket.user_id',
        backref='user', lazy='dynamic',
    )

    # ── Gestión de contraseña ─────────────────────────────
    def set_password(self, password: str) -> None:
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

    # ── Propiedades de rol ────────────────────────────────
    @property
    def is_superadmin(self) -> bool:
        return self.role == 'superadmin'

    @property
    def is_premium(self) -> bool:
        """Superadmin y premium tienen acceso al panel de administración."""
        return self.role in ('superadmin', 'premium')

    @property
    def can_invite(self) -> bool:
        if self.role == 'superadmin':
            return True
        return self.role == 'premium' and self.invites_used < self.invite_limit

    @property
    def invites_remaining(self) -> int:
        if self.role == 'superadmin':
            return 9999   # ilimitado
        return max(0, self.invite_limit - self.invites_used)

    def to_dict(self) -> dict:
        return {
            'id':                self.id,
            'username':          self.username,
            'role':              self.role,
            'invite_limit':      self.invite_limit,
            'invites_used':      self.invites_used,
            'invites_remaining': self.invites_remaining,
            'activo':            self.activo,
            'fecha_creacion':    self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'last_seen':         self.last_seen.isoformat() if self.last_seen else None,
        }


class InviteToken(db.Model):
    """Token de invitación de un solo uso para registrar nuevos usuarios."""
    __tablename__ = 'invite_tokens'

    id             = db.Column(db.Integer, primary_key=True)
    token          = db.Column(
        db.String(64), unique=True, nullable=False,
        default=lambda: secrets.token_urlsafe(32),
    )
    created_by_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    used_by_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    role_asignado  = db.Column(db.String(20), nullable=False, default='user')
    usado          = db.Column(db.Boolean, nullable=False, default=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_uso      = db.Column(db.DateTime, nullable=True)

    used_by = db.relationship('User', foreign_keys=[used_by_id])


class Ticket(db.Model):
    """Solicitud de soporte (p. ej. pedir más invitaciones)."""
    __tablename__ = 'tickets'

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tipo            = db.Column(db.String(50), nullable=False, default='mas_invitaciones')
    mensaje         = db.Column(db.Text, nullable=False)
    estado          = db.Column(db.String(20), nullable=False, default='pendiente')  # pendiente|aprobado|rechazado
    respuesta       = db.Column(db.Text, nullable=True)
    fecha_creacion  = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_respuesta = db.Column(db.DateTime, nullable=True)


class UserSession(db.Model):
    """Sesión activa de usuario para tracking de conexiones simultáneas."""
    __tablename__ = 'user_sessions'

    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_key    = db.Column(db.String(64), unique=True, nullable=False)
    last_seen      = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address     = db.Column(db.String(45), nullable=True)
    user_agent     = db.Column(db.String(255), nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)


# ═══════════════════════════════════════════════════════════
# PROXIES
# ═══════════════════════════════════════════════════════════

class Proxy(db.Model):
    """Proxy HTTP opcional para descargar listas M3U cuyo proveedor bloquea IPs."""
    __tablename__ = 'proxies'

    id             = db.Column(db.Integer, primary_key=True)
    url            = db.Column(db.String(200), nullable=False, unique=True)  # host:port
    activo         = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':     self.id,
            'url':    self.url,
            'activo': self.activo,
        }


# ═══════════════════════════════════════════════════════════
# LISTAS M3U
# ═══════════════════════════════════════════════════════════

class Lista(db.Model):
    """
    Lista M3U importada.
    Si owner_id es NULL → lista global (visible a todos).
    Si owner_id tiene valor → lista privada del usuario premium.
    """
    __tablename__ = 'listas'

    id                   = db.Column(db.Integer, primary_key=True)
    nombre               = db.Column(db.String(200), nullable=False)
    url                  = db.Column(db.Text, nullable=False)
    filtrar_español      = db.Column(db.Boolean, default=False)
    incluir_live         = db.Column(db.Boolean, default=False)
    usar_proxy           = db.Column(db.Boolean, default=False)
    grupos_seleccionados = db.Column(db.Text, nullable=True)   # JSON list
    grupos_tipos         = db.Column(db.Text, nullable=True)   # JSON dict
    activa               = db.Column(db.Boolean, default=True)
    fecha_creacion       = db.Column(db.DateTime, default=datetime.utcnow)
    ultima_actualizacion = db.Column(db.DateTime)
    total_items          = db.Column(db.Integer, default=0)
    items_activos        = db.Column(db.Integer, default=0)
    error                = db.Column(db.Text)

    # Multi-usuario: NULL → global; FK → privada del propietario
    owner_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    visibilidad = db.Column(db.String(20), nullable=False, default='global')  # 'global' | 'private'

    contenidos = db.relationship(
        'Contenido', backref='lista',
        foreign_keys='Contenido.lista_id',
        lazy=True, cascade='all, delete-orphan',
    )

    def to_dict(self):
        return {
            'id':                   self.id,
            'nombre':               self.nombre,
            'url':                  self.url,
            'filtrar_español':      self.filtrar_español,
            'incluir_live':         self.incluir_live,
            'usar_proxy':           self.usar_proxy,
            'grupos_seleccionados': self.grupos_seleccionados,
            'grupos_tipos':         self.grupos_tipos,
            'activa':               self.activa,
            'visibilidad':          self.visibilidad,
            'owner_id':             self.owner_id,
            'fecha_creacion': (
                self.fecha_creacion.isoformat() if self.fecha_creacion else None
            ),
            'ultima_actualizacion': (
                self.ultima_actualizacion.isoformat() if self.ultima_actualizacion else None
            ),
            'total_items':   self.total_items,
            'items_activos': self.items_activos,
            'error':         self.error,
        }


# ═══════════════════════════════════════════════════════════
# FUENTES RSS
# ═══════════════════════════════════════════════════════════

class FuenteRSS(db.Model):
    """Fuente RSS (cinemacity.cc u otras webs con RSS)."""
    __tablename__ = 'fuentes_rss'

    id                   = db.Column(db.Integer, primary_key=True)
    nombre               = db.Column(db.String(200), nullable=False)
    url                  = db.Column(db.Text, nullable=False)
    activa               = db.Column(db.Boolean, default=True)
    fecha_creacion       = db.Column(db.DateTime, default=datetime.utcnow)
    ultima_actualizacion = db.Column(db.DateTime)
    total_items          = db.Column(db.Integer, default=0)
    error                = db.Column(db.Text)

    # Multi-usuario
    owner_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    visibilidad = db.Column(db.String(20), nullable=False, default='global')

    contenidos = db.relationship(
        'Contenido', backref='fuente_rss_obj',
        foreign_keys='Contenido.fuente_rss_id',
        lazy=True, cascade='all, delete-orphan',
    )

    def to_dict(self):
        return {
            'id':           self.id,
            'nombre':       self.nombre,
            'url':          self.url,
            'activa':       self.activa,
            'visibilidad':  self.visibilidad,
            'owner_id':     self.owner_id,
            'fecha_creacion': (
                self.fecha_creacion.isoformat() if self.fecha_creacion else None
            ),
            'ultima_actualizacion': (
                self.ultima_actualizacion.isoformat() if self.ultima_actualizacion else None
            ),
            'total_items': self.total_items,
            'error':       self.error,
        }


# ═══════════════════════════════════════════════════════════
# CONTENIDO
# ═══════════════════════════════════════════════════════════

class Contenido(db.Model):
    """Película o serie — puede venir de RSS o M3U."""
    __tablename__ = 'contenidos'

    id            = db.Column(db.Integer, primary_key=True)
    titulo        = db.Column(db.String(500), nullable=False)
    tipo          = db.Column(db.String(20), default='pelicula')     # 'pelicula' | 'serie' | 'live'

    url_stream    = db.Column(db.Text, nullable=False)
    url_hash      = db.Column(db.String(64), unique=True, nullable=False, index=True)

    fuente        = db.Column(db.String(10), default='m3u', index=True)

    servidor      = db.Column(db.String(300))
    imagen        = db.Column(db.Text)
    descripcion   = db.Column(db.Text)
    año           = db.Column(db.Integer)
    genero        = db.Column(db.String(300))
    group_title   = db.Column(db.String(300))
    idioma        = db.Column(db.String(100))
    pais          = db.Column(db.String(50))
    temporada     = db.Column(db.Integer)
    episodio      = db.Column(db.Integer)

    activo              = db.Column(db.Boolean, default=True, index=True)
    fecha_agregado      = db.Column(db.DateTime, default=datetime.utcnow)
    ultima_verificacion = db.Column(db.DateTime)

    lista_id      = db.Column(db.Integer, db.ForeignKey('listas.id'),      nullable=True)
    fuente_rss_id = db.Column(db.Integer, db.ForeignKey('fuentes_rss.id'), nullable=True)

    reports = db.relationship(
        'ChannelReport', backref='contenido',
        lazy='dynamic', cascade='all, delete-orphan',
    )

    def to_dict(self):
        _type_map = {'pelicula': 'movie', 'serie': 'series', 'live': 'live'}
        return {
            'id':          self.id,
            'title':       self.titulo,
            'type':        _type_map.get(self.tipo, self.tipo),
            'streamUrl':   self.url_stream,
            'source':      self.fuente,
            'server':      self.servidor,
            'image':       self.imagen or '',
            'description': self.descripcion or '',
            'year':        self.año,
            'genres':      [g.strip() for g in self.genero.split(',')] if self.genero else [],
            'groupTitle':  self.group_title,
            'season':      self.temporada,
            'episode':     self.episodio,
            'active':      self.activo,
            'addedAt':     self.fecha_agregado.isoformat() if self.fecha_agregado else None,
            'lastCheck':   (
                self.ultima_verificacion.isoformat() if self.ultima_verificacion else None
            ),
        }


# ═══════════════════════════════════════════════════════════
# REPORTES DE CANALES
# ═══════════════════════════════════════════════════════════

class ChannelReport(db.Model):
    """Reporte enviado por el usuario cuando un canal no funciona."""
    __tablename__ = 'channel_reports'

    id             = db.Column(db.Integer, primary_key=True)
    contenido_id   = db.Column(db.Integer, db.ForeignKey('contenidos.id'), nullable=False)
    ip_address     = db.Column(db.String(45), nullable=True)
    estado         = db.Column(db.String(20), nullable=False, default='pendiente')  # pendiente|revisado|resuelto
    nota_admin     = db.Column(db.Text, nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_revision = db.Column(db.DateTime, nullable=True)


# ═══════════════════════════════════════════════════════════
# IPTV — USUARIOS Y SESIONES
# ═══════════════════════════════════════════════════════════

class IptvUser(db.Model):
    """
    Usuario del servicio IPTV externo.
    Recibe una URL personalizada con su usuario/contraseña para acceder
    al contenido con su plan y límite de conexiones simultáneas.
    """
    __tablename__ = 'iptv_users'

    id              = db.Column(db.Integer, primary_key=True)
    username        = db.Column(db.String(80), unique=True, nullable=False)
    password_hash   = db.Column(db.String(255), nullable=False)
    plan            = db.Column(db.String(10), nullable=False, default='1m')  # 1m|3m|6m|1y
    max_connections = db.Column(db.Integer, nullable=False, default=1)        # 1|2|3|5
    activo          = db.Column(db.Boolean, nullable=False, default=True)
    expires_at      = db.Column(db.DateTime, nullable=True)
    fecha_creacion  = db.Column(db.DateTime, default=datetime.utcnow)
    nota            = db.Column(db.String(255), nullable=True)

    sessions = db.relationship(
        'IptvSession', backref='iptv_user', lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def set_password(self, password: str) -> None:
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def plan_label(self) -> str:
        return {'1m': '1 mes', '3m': '3 meses', '6m': '6 meses', '1y': '1 año'}.get(self.plan, self.plan)

    def to_dict(self) -> dict:
        return {
            'id':              self.id,
            'username':        self.username,
            'plan':            self.plan,
            'plan_label':      self.plan_label,
            'max_connections': self.max_connections,
            'activo':          self.activo,
            'expires_at':      self.expires_at.isoformat() if self.expires_at else None,
            'fecha_creacion':  self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'nota':            self.nota,
        }


class IptvSession(db.Model):
    """Sesión IPTV activa — usada para controlar conexiones simultáneas."""
    __tablename__ = 'iptv_sessions'

    id             = db.Column(db.Integer, primary_key=True)
    iptv_user_id   = db.Column(db.Integer, db.ForeignKey('iptv_users.id'), nullable=False)
    session_token  = db.Column(db.String(64), unique=True, nullable=False,
                               default=lambda: secrets.token_hex(32))
    contenido_id   = db.Column(db.Integer, db.ForeignKey('contenidos.id'), nullable=True)
    ip_address     = db.Column(db.String(45), nullable=True)
    last_heartbeat = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
