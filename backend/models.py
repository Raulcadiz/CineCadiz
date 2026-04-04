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
    invite_limit      = db.Column(db.Integer, nullable=False, default=10)
    invites_used      = db.Column(db.Integer, nullable=False, default=0)
    iptv_user_limit   = db.Column(db.Integer, nullable=False, default=10)
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
    # Lista predeterminada: su contenido live se pre-selecciona en la web, APK e IPTV
    es_defecto           = db.Column(db.Boolean, nullable=False, default=False)

    # Multi-usuario: NULL → global; FK → privada del propietario
    owner_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    visibilidad = db.Column(db.String(20), nullable=False, default='global')  # 'global' | 'private'

    # Guardar M3U localmente y enviar por Telegram al importar
    guardar_local = db.Column(db.Boolean, default=True)
    enviar_telegram = db.Column(db.Boolean, default=True)
    # Guardar canales live también en CanalCurado agrupados por nombre de lista
    live_a_curado  = db.Column(db.Boolean, default=True)

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
            'es_defecto':    self.es_defecto,
            'guardar_local':   self.guardar_local,
            'enviar_telegram': self.enviar_telegram,
            'live_a_curado':  self.live_a_curado,
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

    # ── Campos exclusivos para canales en directo (tipo='live') ──
    # JSON array con todas las URLs de backup ordenadas por prioridad
    live_urls_json  = db.Column(db.Text, nullable=True)
    # Índice de la URL activa en live_urls_json (0 = primera/original)
    live_active_idx = db.Column(db.Integer, nullable=False, default=0)

    # ── Propiedades DRM / Avanzadas ───────────────────────────
    # Para streams con Widevine/PlayReady/ClearKey
    drm_license_type = db.Column(db.String(100), nullable=True)
    drm_license_key  = db.Column(db.Text, nullable=True)
    drm_key_id       = db.Column(db.String(64), nullable=True)
    drm_key          = db.Column(db.String(64), nullable=True)
    manifest_type    = db.Column(db.String(50), nullable=True)
    # Catchup / Timeshift (reproducción desde inicio)
    catchup_type    = db.Column(db.String(50), nullable=True)
    catchup_source  = db.Column(db.Text, nullable=True)
    catchup_days    = db.Column(db.Integer, nullable=True)
    # Headers personalizados
    user_agent      = db.Column(db.String(500), nullable=True)
    http_referrer   = db.Column(db.String(500), nullable=True)

    lista_id      = db.Column(db.Integer, db.ForeignKey('listas.id'),      nullable=True)
    fuente_rss_id = db.Column(db.Integer, db.ForeignKey('fuentes_rss.id'), nullable=True)

    reports = db.relationship(
        'ChannelReport', backref='contenido',
        lazy='dynamic', cascade='all, delete-orphan',
    )

    def to_dict(self):
        import json as _json
        _type_map = {'pelicula': 'movie', 'serie': 'series', 'live': 'live'}

        # Para canales live: calcular URL activa y lista completa
        if self.tipo == 'live' and self.live_urls_json:
            try:
                all_urls = _json.loads(self.live_urls_json)
                active_idx = self.live_active_idx or 0
                active_url = all_urls[active_idx] if all_urls and active_idx < len(all_urls) else self.url_stream
            except (ValueError, IndexError, TypeError):
                all_urls = [self.url_stream]
                active_idx = 0
                active_url = self.url_stream
        else:
            all_urls = None
            active_idx = 0
            active_url = self.url_stream

        d = {
            'id':          self.id,
            'title':       self.titulo,
            'type':        _type_map.get(self.tipo, self.tipo),
            'streamUrl':   active_url,
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
        if self.tipo == 'live':
            d['liveUrls'] = all_urls or [self.url_stream]
            d['activeUrlIndex'] = active_idx
        # Propiedades DRM / Avanzadas
        if self.drm_license_type:
            d['drmLicenseType'] = self.drm_license_type
        if self.drm_license_key:
            d['drmLicenseKey'] = self.drm_license_key
        if self.drm_key_id:
            d['drmKeyId'] = self.drm_key_id
        if self.drm_key:
            d['drmKey'] = self.drm_key
        if self.manifest_type:
            d['manifestType'] = self.manifest_type
        if self.catchup_type:
            d['catchupType'] = self.catchup_type
        if self.catchup_source:
            d['catchupSource'] = self.catchup_source
        if self.catchup_days:
            d['catchupDays'] = self.catchup_days
        if self.user_agent:
            d['userAgent'] = self.user_agent
        if self.http_referrer:
            d['httpReferrer'] = self.http_referrer
        return d


# ═══════════════════════════════════════════════════════════
# HISTORIAL DE REPRODUCCIÓN
# ═══════════════════════════════════════════════════════════

class WatchHistory(db.Model):
    """
    Evento de reproducción — anónimo (session_key) o vinculado a usuario.
    Permite calcular recomendaciones personalizadas sin requerir login.
    Un mismo contenido puede aparecer varias veces (repeticiones); el frontend
    deduplica por contenido_id cuando construye el perfil de afinidad.
    """
    __tablename__ = 'watch_history'

    id             = db.Column(db.Integer, primary_key=True)
    # Sesión anónima — generada en el cliente, persiste en localStorage
    session_key    = db.Column(db.String(64), nullable=False, index=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    contenido_id   = db.Column(db.Integer, db.ForeignKey('contenidos.id'), nullable=False)
    played_at      = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    # Géneros del item en el momento de la reproducción (snapshot para no requerir join)
    genres_snapshot = db.Column(db.String(300), nullable=True)

    contenido = db.relationship('Contenido', backref=db.backref('watches', lazy='dynamic', cascade='all, delete-orphan'))


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
    password_plain  = db.Column(db.String(255), nullable=True)   # para mostrar URL al admin
    # Grupos permitidos: JSON list de group_title. NULL = acceso a todo el contenido.
    grupos_permitidos = db.Column(db.Text, nullable=True)
    # Multi-admin: NULL → creado por superadmin (visible a todos los premium); FK → privado del admin
    owner_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    sessions = db.relationship(
        'IptvSession', backref='iptv_user', lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def set_password(self, password: str) -> None:
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)
        self.password_plain = password

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


# ═══════════════════════════════════════════════════════════
# LIVE SCAN — CONFIGURACIÓN Y REPORTES
# ═══════════════════════════════════════════════════════════

class LiveScanConfig(db.Model):
    """Configuración global del escaneo automático de canales en directo."""
    __tablename__ = 'live_scan_config'

    id                  = db.Column(db.Integer, primary_key=True)
    auto_scan_enabled   = db.Column(db.Boolean, nullable=False, default=True)
    interval_hours      = db.Column(db.Integer, nullable=False, default=24)  # 24 | 48 | 72
    last_scan           = db.Column(db.DateTime, nullable=True)
    show_in_frontend    = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            'auto_scan_enabled': self.auto_scan_enabled,
            'interval_hours':    self.interval_hours,
            'last_scan':         self.last_scan.isoformat() if self.last_scan else None,
            'show_in_frontend':  self.show_in_frontend,
        }


class LiveScanReport(db.Model):
    """Registro de cada verificación de URL de canal en directo."""
    __tablename__ = 'live_scan_reports'

    id           = db.Column(db.Integer, primary_key=True)
    contenido_id = db.Column(db.Integer, db.ForeignKey('contenidos.id'), nullable=False)
    url_probada  = db.Column(db.Text, nullable=False)
    resultado    = db.Column(db.Boolean, nullable=False)   # True=viva, False=caída
    latencia_ms  = db.Column(db.Integer, nullable=True)
    timestamp    = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    contenido = db.relationship('Contenido', backref=db.backref('scan_reports', lazy='dynamic'))

    def to_dict(self):
        return {
            'id':           self.id,
            'contenido_id': self.contenido_id,
            'channel_title': self.contenido.titulo if self.contenido else '',
            'url_probada':  self.url_probada,
            'resultado':    self.resultado,
            'latencia_ms':  self.latencia_ms,
            'timestamp':    self.timestamp.isoformat() if self.timestamp else None,
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


# ═══════════════════════════════════════════════════════════
# TELEGRAM — CONFIGURACIÓN Y SNAPSHOTS DE SALUD
# ═══════════════════════════════════════════════════════════

class TelegramConfig(db.Model):
    """Configuración del bot de Telegram para notificaciones."""
    __tablename__ = 'telegram_config'

    id               = db.Column(db.Integer, primary_key=True)
    enabled          = db.Column(db.Boolean, nullable=False, default=True)
    token            = db.Column(db.String(200), nullable=True)
    # JSON list de chat/group IDs, p.ej. ["-1001234567890", "987654321"]
    chat_ids_json    = db.Column(db.Text, nullable=True)
    # Umbral % de streams caídos que dispara la alerta (defecto 80%)
    alert_threshold  = db.Column(db.Integer, nullable=False, default=80)
    # Enviar resumen diario automático
    daily_digest     = db.Column(db.Boolean, nullable=False, default=True)
    # Hora UTC para el digest (0-23)
    digest_hour      = db.Column(db.Integer, nullable=False, default=8)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        import json as _json
        ids = []
        try:
            ids = _json.loads(self.chat_ids_json) if self.chat_ids_json else []
        except Exception:
            pass
        return {
            'enabled':         self.enabled,
            'token':           self.token or '',
            'chat_ids':        ids,
            'alert_threshold': self.alert_threshold,
            'daily_digest':    self.daily_digest,
            'digest_hour':     self.digest_hour,
        }


# ═══════════════════════════════════════════════════════════
# CANALES CURADOS — Lista manual de live con múltiples fuentes
# ═══════════════════════════════════════════════════════════

class CanalCurado(db.Model):
    """
    Canal TV en directo curado manualmente por el admin.
    Tiene múltiples URLs de backup (de distintos servidores IPTV);
    el APK y la web prueban cada URL en orden hasta que una funcione.
    """
    __tablename__ = 'canales_curados'

    id         = db.Column(db.Integer, primary_key=True)
    nombre     = db.Column(db.String(200), nullable=False)
    logo       = db.Column(db.Text, nullable=True)
    grupo      = db.Column(db.String(200), nullable=True)
    orden      = db.Column(db.Integer, nullable=False, default=0)
    activo     = db.Column(db.Boolean, nullable=False, default=True)
    urls_json  = db.Column(db.Text, nullable=False, default='[]')
    fuente     = db.Column(db.String(200), nullable=True)
    lista_id   = db.Column(db.Integer, db.ForeignKey('listas.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def urls(self):
        import json as _j
        try:
            return _j.loads(self.urls_json or '[]')
        except Exception:
            return []

    def to_dict(self):
        """
        Devuelve el canal en el mismo formato que Contenido.to_dict()
        para que el APK pueda usarlo sin cambios (incluye liveUrls para failover).
        """
        all_urls = [e['url'] for e in self.urls if e.get('url')]
        stream_url = all_urls[0] if all_urls else ''
        return {
            'id':             self.id,
            'title':          self.nombre,
            'type':           'live',
            'streamUrl':      stream_url,
            'source':         'curado',
            'server':         None,
            'image':          self.logo or '',
            'description':    '',
            'year':           None,
            'genres':         [],
            'groupTitle':     self.grupo or 'Curados',
            'season':         None,
            'episode':        None,
            'active':         self.activo,
            'addedAt':        self.created_at.isoformat() if self.created_at else None,
            'liveUrls':       all_urls,
            'activeUrlIndex': 0,
        }


# ═══════════════════════════════════════════════════════════
# XTREAM CODES — CONFIGURACIÓN DEL SERVIDOR
# ═══════════════════════════════════════════════════════════

class XtreamConfig(db.Model):
    """
    Configuración global del servidor Xtream Codes integrado.
    Solo existe una fila (singleton, id=1).
    """
    __tablename__ = 'xtream_config'

    id             = db.Column(db.Integer, primary_key=True)
    # 'direct' → 302 redirect al proveedor original (sin pasar por VPS)
    # 'proxy'  → el VPS retransmite el stream (oculta credenciales del proveedor)
    stream_mode    = db.Column(db.String(10), nullable=False, default='direct')
    live_enabled   = db.Column(db.Boolean,   nullable=False, default=True)
    vod_enabled    = db.Column(db.Boolean,   nullable=False, default=True)
    series_enabled = db.Column(db.Boolean,   nullable=False, default=True)

    def to_dict(self):
        return {
            'stream_mode':    self.stream_mode,
            'live_enabled':   self.live_enabled,
            'vod_enabled':    self.vod_enabled,
            'series_enabled': self.series_enabled,
        }


# ═══════════════════════════════════════════════════════════
# SERVER HEALTH SNAPSHOTS
# ═══════════════════════════════════════════════════════════

class ServerHealthSnapshot(db.Model):
    """
    Último estado conocido de cada servidor.
    Permite detectar cambios (servidor se cae / se recupera) entre escaneos.
    """
    __tablename__ = 'server_health_snapshots'

    id         = db.Column(db.Integer, primary_key=True)
    servidor   = db.Column(db.String(300), unique=True, nullable=False, index=True)
    dead_pct   = db.Column(db.Float, nullable=False, default=0.0)
    # True si ya se envió alerta de caída para este servidor (evita duplicados)
    alerted    = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
