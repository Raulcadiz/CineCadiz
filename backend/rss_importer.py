"""
Importador de fuentes RSS (cinemacity.cc y similares).
Los items RSS se guardan con fuente='rss' y url_stream = enlace a la página web.
El frontend abre esos links en una nueva pestaña en lugar de usar el player.
"""
import re
import hashlib
import logging
from xml.etree import ElementTree as ET
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}

# Fuentes por defecto de cinemacity.cc
DEFAULT_RSS_SOURCES = [
    {'nombre': 'CinemaCity — Películas',  'url': 'https://cinemacity.cc/movies/rss.xml'},
    {'nombre': 'CinemaCity — Series',     'url': 'https://cinemacity.cc/tv-series/rss.xml'},
    {'nombre': 'CinemaCity — General',    'url': 'https://cinemacity.cc/rss.xml'},
]


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode('utf-8')).hexdigest()


def _text(element, tag: str, default: str = '') -> str:
    node = element.find(tag)
    return (node.text or default).strip() if node is not None else default


# Namespaces comunes en feeds RSS de WordPress/CinemaCity
_NS = {
    'media':   'http://search.yahoo.com/mrss/',
    'content': 'http://purl.org/rss/1.0/modules/content/',
    'dc':      'http://purl.org/dc/elements/1.1/',
}


def _extract_image(node, desc: str) -> str:
    """
    Extrae la URL de imagen de un <item> RSS por orden de prioridad:
      1. <media:content url="..." medium="image">
      2. <media:thumbnail url="...">
      3. <enclosure type="image/...">
      4. Primera <img src="..."> en la description
      5. Primera <img src="..."> en content:encoded
    """
    # 1. media:content con medium="image" o extensión de imagen
    for mc in node.findall('media:content', _NS):
        url = mc.get('url', '')
        medium = mc.get('medium', '')
        if url and (medium == 'image' or
                    url.lower().split('?')[0].endswith(
                        ('.jpg', '.jpeg', '.png', '.webp', '.gif'))):
            return url

    # 2. media:thumbnail
    mt = node.find('media:thumbnail', _NS)
    if mt is not None and mt.get('url'):
        return mt.get('url')

    # 3. enclosure de tipo imagen
    enc = node.find('enclosure')
    if enc is not None and 'image' in (enc.get('type') or ''):
        url = enc.get('url') or ''
        if url:
            return url

    # 4. <img src="..."> o data-src / data-lazy-src en la descripción HTML
    _IMG_RE = re.compile(
        r'<img[^>]+(?:src|data-src|data-lazy-src)=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    m = _IMG_RE.search(desc)
    if m:
        return m.group(1)

    # 5. content:encoded (WordPress pone el contenido completo del post aquí)
    ce = node.find('content:encoded', _NS)
    if ce is not None and ce.text:
        # Primero buscar img con src normal; luego data-src para lazy-load
        m2 = re.search(
            r'<img[^>]+(?:src|data-src|data-lazy-src)=["\']([^"\']+)["\']',
            ce.text, re.IGNORECASE,
        )
        if m2:
            return m2.group(1)

    # 6. og:image en el HTML de la descripción (algunos feeds lo incluyen)
    m3 = re.search(
        r'<meta[^>]+(?:property=["\']og:image["\'][^>]+content|content=[^>]+property=["\']og:image["\'])[^>]*=["\']([^"\']+)["\']',
        desc, re.IGNORECASE,
    )
    if m3:
        return m3.group(1)

    return ''


def parse_rss_feed(content: bytes) -> list[dict]:
    """Parsea XML de un RSS feed y devuelve lista de items."""
    for prefix, uri in _NS.items():
        ET.register_namespace(prefix, uri)

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        logger.error(f'[RSS] Error XML: {e}')
        return []

    channel = root.find('channel')
    if channel is None:
        return []

    items = []
    for node in channel.findall('item'):
        title = _text(node, 'title')
        link  = _text(node, 'link')
        desc  = _text(node, 'description')

        if not title or not link:
            continue

        # Imagen — varios formatos de feed soportados
        image = _extract_image(node, desc)

        # Año desde el título "(2024)"
        year = None
        ym = re.search(r'\((\d{4})\)', title)
        if ym:
            year = int(ym.group(1))
            title = re.sub(r'\s*\(\d{4}\)\s*', ' ', title).strip()

        # Tipo según URL
        tipo = 'serie' if ('/tv-series/' in link or '/series/' in link) else 'pelicula'

        # Géneros desde <category>
        cats = [c.text.strip() for c in node.findall('category') if c.text]
        genero = ', '.join(cats)

        # Descripción limpia (sin HTML)
        clean_desc = re.sub(r'<[^>]+>', '', desc).strip()

        # Rating si aparece "X/10" en la descripción
        rating = None
        rm = re.search(r'(\d+(?:\.\d+)?)\s*/\s*10', clean_desc)
        if rm:
            try:
                rating = float(rm.group(1))
            except ValueError:
                pass

        items.append({
            'titulo':      title,
            'tipo':        tipo,
            'url_stream':  link,
            'url_hash':    url_hash(link),
            'imagen':      image,
            'año':         year,
            'genero':      genero,
            'descripcion': clean_desc[:600],
            'fuente':      'rss',
            'servidor':    'cinemacity.cc',
            'group_title': '',
            'idioma':      'es',
            'pais':        'es',
            'temporada':   None,
            'episodio':    None,
            'rating':      rating,
        })

    return items


def fetch_rss(url: str) -> tuple[list, str | None]:
    """Descarga y parsea un RSS. Devuelve (items, error)."""
    try:
        # proxies={} ignora HTTPS_PROXY del sistema (PythonAnywhere lo inyecta y bloquea sitios)
        resp = requests.get(url, timeout=20, headers=_HEADERS, proxies={})
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        return [], 'Timeout al descargar RSS'
    except requests.exceptions.ConnectionError as e:
        return [], f'Error de conexión: {e}'
    except requests.exceptions.HTTPError as e:
        return [], f'Error HTTP {e.response.status_code}'
    except Exception as e:
        return [], str(e)

    return parse_rss_feed(resp.content), None


def import_rss_source(app, fuente_rss_id: int):
    """
    Importa una FuenteRSS a la BD.
    Solo guarda items nuevos (deduplicación por url_hash).
    """
    import threading
    t = threading.Thread(
        target=_do_import,
        args=(app, fuente_rss_id),
        daemon=True,
    )
    t.start()


def _do_import(app, fuente_rss_id: int):
    from models import db, Contenido, FuenteRSS

    with app.app_context():
        fuente = FuenteRSS.query.get(fuente_rss_id)
        if not fuente:
            return

        logger.info(f'[RSS Import] Iniciando: {fuente.nombre}')
        items, error = fetch_rss(fuente.url)

        if error:
            fuente.error = error
            fuente.ultima_actualizacion = datetime.utcnow()
            db.session.commit()
            logger.error(f'[RSS Import] Error: {error}')
            return

        nuevos = 0
        for it in items:
            if Contenido.query.filter_by(url_hash=it['url_hash']).first():
                continue

            c = Contenido(
                titulo=it['titulo'] or 'Sin título',
                tipo=it['tipo'],
                url_stream=it['url_stream'],
                url_hash=it['url_hash'],
                servidor=it.get('servidor', ''),
                imagen=it.get('imagen', ''),
                año=it.get('año'),
                genero=it.get('genero', ''),
                descripcion=it.get('descripcion', ''),
                group_title=it.get('group_title', ''),
                idioma=it.get('idioma', 'es'),
                pais=it.get('pais', 'es'),
                temporada=it.get('temporada'),
                episodio=it.get('episodio'),
                fuente='rss',
                fuente_rss_id=fuente_rss_id,
                lista_id=None,
            )
            db.session.add(c)
            nuevos += 1
            if nuevos % 200 == 0:
                db.session.commit()

        db.session.commit()

        fuente.error = None
        fuente.total_items = Contenido.query.filter_by(fuente_rss_id=fuente_rss_id).count()
        fuente.ultima_actualizacion = datetime.utcnow()
        db.session.commit()

        logger.info(f'[RSS Import] {fuente.nombre}: {nuevos} nuevos / {fuente.total_items} total')
