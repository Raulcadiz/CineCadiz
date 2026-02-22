from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Lista(db.Model):
    """Lista M3U importada por el admin."""
    __tablename__ = 'listas'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    url = db.Column(db.Text, nullable=False)
    filtrar_español = db.Column(db.Boolean, default=False)
    activa = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    ultima_actualizacion = db.Column(db.DateTime)
    total_items = db.Column(db.Integer, default=0)
    items_activos = db.Column(db.Integer, default=0)
    error = db.Column(db.Text)

    contenidos = db.relationship(
        'Contenido', backref='lista',
        foreign_keys='Contenido.lista_id',
        lazy=True, cascade='all, delete-orphan',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'url': self.url,
            'filtrar_español': self.filtrar_español,
            'activa': self.activa,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'ultima_actualizacion': (
                self.ultima_actualizacion.isoformat() if self.ultima_actualizacion else None
            ),
            'total_items': self.total_items,
            'items_activos': self.items_activos,
            'error': self.error,
        }


class FuenteRSS(db.Model):
    """Fuente RSS (cinemacity.cc u otras webs con RSS)."""
    __tablename__ = 'fuentes_rss'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    url = db.Column(db.Text, nullable=False)
    activa = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    ultima_actualizacion = db.Column(db.DateTime)
    total_items = db.Column(db.Integer, default=0)
    error = db.Column(db.Text)

    contenidos = db.relationship(
        'Contenido', backref='fuente_rss_obj',
        foreign_keys='Contenido.fuente_rss_id',
        lazy=True, cascade='all, delete-orphan',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'url': self.url,
            'activa': self.activa,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'ultima_actualizacion': (
                self.ultima_actualizacion.isoformat() if self.ultima_actualizacion else None
            ),
            'total_items': self.total_items,
            'error': self.error,
        }


class Contenido(db.Model):
    """Película o serie — puede venir de RSS o M3U."""
    __tablename__ = 'contenidos'

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(500), nullable=False)
    tipo = db.Column(db.String(20), default='pelicula')     # 'pelicula' | 'serie'

    # URL única del stream / página (SHA-256 para deduplicar globalmente)
    url_stream = db.Column(db.Text, nullable=False)
    url_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)

    # Origen: 'm3u' usa video player; 'rss' abre en nueva pestaña
    fuente = db.Column(db.String(10), default='m3u', index=True)

    servidor = db.Column(db.String(300))
    imagen = db.Column(db.Text)
    descripcion = db.Column(db.Text)
    año = db.Column(db.Integer)
    genero = db.Column(db.String(300))
    group_title = db.Column(db.String(300))
    idioma = db.Column(db.String(100))
    pais = db.Column(db.String(50))
    temporada = db.Column(db.Integer)
    episodio = db.Column(db.Integer)

    activo = db.Column(db.Boolean, default=True, index=True)
    fecha_agregado = db.Column(db.DateTime, default=datetime.utcnow)
    ultima_verificacion = db.Column(db.DateTime)

    # FK a lista M3U (solo para fuente='m3u')
    lista_id = db.Column(db.Integer, db.ForeignKey('listas.id'), nullable=True)
    # FK a fuente RSS (solo para fuente='rss')
    fuente_rss_id = db.Column(db.Integer, db.ForeignKey('fuentes_rss.id'), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.titulo,
            'type': 'movie' if self.tipo == 'pelicula' else 'series',
            'streamUrl': self.url_stream,
            'source': self.fuente,          # 'm3u' | 'rss' → frontend decide cómo reproducir
            'server': self.servidor,
            'image': self.imagen or '',
            'description': self.descripcion or '',
            'year': self.año,
            'genres': [g.strip() for g in self.genero.split(',')] if self.genero else [],
            'groupTitle': self.group_title,
            'season': self.temporada,
            'episode': self.episodio,
            'active': self.activo,
            'addedAt': self.fecha_agregado.isoformat() if self.fecha_agregado else None,
            'lastCheck': (
                self.ultima_verificacion.isoformat() if self.ultima_verificacion else None
            ),
        }
