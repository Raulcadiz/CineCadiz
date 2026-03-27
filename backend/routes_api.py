"""
API REST pública — /api/
Consumida por el frontend JavaScript.
"""
import re as _re
import socket as _socket
from urllib.parse import urlparse as _urlparse, urljoin as _urljoin, quote as _quote
from flask import Blueprint, jsonify, request, current_app, Response
from flask import session as _session
from models import db, Contenido, Lista, FuenteRSS, ChannelReport, WatchHistory, LiveScanConfig, LiveScanReport
from sqlalchemy import or_, and_, nulls_last
import requests

# ── Helpers de seguridad para proxies ───────────────────────────

def _is_private(url: str) -> bool:
    """Bloquea URLs que apunten a IPs privadas/locales (prevención de SSRF)."""
    import re as _re2
    try:
        h = _urlparse(url).hostname or ''
        if h in ('localhost', '127.0.0.1', '::1', '0.0.0.0', ''):
            return True
        # Si el hostname ya es una IP literal, comprobamos directamente sin DNS
        if _re2.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', h):
            p = list(map(int, h.split('.')))
            return (p[0] == 127 or p[0] == 10
                    or (p[0] == 172 and 16 <= p[1] <= 31)
                    or (p[0] == 192 and p[1] == 168)
                    or (p[0] == 169 and p[1] == 254))
        # Para nombres de host: intentar DNS con timeout corto
        # Si falla (sin red, DNS lento) → permitir; requests.get fallará de forma segura
        old_timeout = _socket.getdefaulttimeout()
        try:
            _socket.setdefaulttimeout(3)
            ip = _socket.gethostbyname(h)
            p = list(map(int, ip.split('.')))
            return (p[0] == 127 or p[0] == 10
                    or (p[0] == 172 and 16 <= p[1] <= 31)
                    or (p[0] == 192 and p[1] == 168)
                    or (p[0] == 169 and p[1] == 254))
        except Exception:
            return False  # DNS falló → dejar pasar; requests manejará el error
        finally:
            _socket.setdefaulttimeout(old_timeout)
    except Exception:
        return True  # URL malformada → bloquear

_PROXY_UA = {
    # VLC como User-Agent principal — los servidores IPTV reconocen y sirven a VLC;
    # bloquean peticiones de navegadores convencionales (Chrome, Firefox).
    'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20',
    'Icy-MetaData': '0',
}

# Tabla de Content-Type por extensión de URL para el proxy de streams
_EXT_CONTENT_TYPE: dict[str, str] = {
    '.mp4':  'video/mp4',
    '.m4v':  'video/mp4',
    '.mkv':  'video/x-matroska',
    '.webm': 'video/webm',
    '.avi':  'video/x-msvideo',
    '.mov':  'video/quicktime',
    '.ts':   'video/mp2t',
    '.m2ts': 'video/mp2t',
    '.flv':  'video/x-flv',
    '.wmv':  'video/x-ms-wmv',
    '.mpg':  'video/mpeg',
    '.mpeg': 'video/mpeg',
}


def _content_type_for_url(url: str, server_ct: str) -> str:
    """
    Devuelve el Content-Type correcto para el stream-proxy.
    Si el servidor manda un tipo de vídeo válido, lo usa.
    Si manda 'application/octet-stream' u otro tipo genérico,
    lo infiere por la extensión de la URL en lugar de asumir MPEG-TS.
    """
    url_path = url.lower().split('?')[0]
    # Content-Type útil que viene del servidor → respetarlo
    if server_ct and server_ct.startswith('video/') and server_ct != 'video/mp2t':
        # Conservar video/* explícito (excepto mp2t que a veces es incorrecto)
        return server_ct
    if server_ct and server_ct.startswith('video/mp2t'):
        # mp2t solo es correcto para .ts/.m2ts
        if url_path.endswith('.ts') or url_path.endswith('.m2ts'):
            return server_ct
    # Inferir por extensión
    for ext, ct in _EXT_CONTENT_TYPE.items():
        if url_path.endswith(ext):
            return ct
    # Sin extensión conocida (streams IPTV sin extensión) → mp2t es lo habitual
    return server_ct or 'video/mp2t'

api_bp = Blueprint('api', __name__, url_prefix='/api')


# ── Helpers ────────────────────────────────────────────────────

def paginate_query(query, page, per_page):
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        'items': [item.to_dict() for item in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'pages': pagination.pages,
        'per_page': per_page,
    }


def _build_visible_query():
    """
    Construye una query base de Contenido que respeta la visibilidad:
    - Contenido global (lista.visibilidad='global' o sin lista) → visible para todos
    - Contenido privado → solo visible para el propietario de la lista
    El JOIN con Lista es LEFT OUTER para incluir contenido RSS (lista_id=NULL).
    """
    user_id = _session.get('user_id')
    q = (
        Contenido.query
        .filter_by(activo=True)
        .outerjoin(Lista, Contenido.lista_id == Lista.id)
    )
    if user_id:
        q = q.filter(
            or_(
                Contenido.lista_id.is_(None),            # contenido RSS
                Lista.visibilidad == 'global',           # lista global
                and_(
                    Lista.owner_id == user_id,
                    Lista.visibilidad == 'private',      # lista privada del usuario
                ),
            )
        )
    else:
        q = q.filter(
            or_(
                Contenido.lista_id.is_(None),
                Lista.visibilidad == 'global',
            )
        )
    return q


# ── Endpoints ──────────────────────────────────────────────────

@api_bp.get('/contenido')
def get_contenido():
    """
    Lista contenido con filtros opcionales.
    Query params: tipo, genero, año, q (búsqueda), sort, page, limit
    sort: recent (default) | year_desc | year_asc | title_asc
    """
    tipo = request.args.get('tipo')           # 'pelicula' | 'serie'
    genero = request.args.get('genero', '')
    año = request.args.get('año', '')
    q = request.args.get('q', '').strip()
    sort = request.args.get('sort', 'recent')
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(
        request.args.get('limit', current_app.config['ITEMS_PER_PAGE'], type=int),
        100
    )

    query = _build_visible_query()

    if tipo in ('pelicula', 'serie', 'live'):
        query = query.filter(Contenido.tipo == tipo)

    if genero:
        # ilike en ambos campos: SQLAlchemy genera lower(col) LIKE lower(pattern),
        # lo que funciona con caracteres acentuados en SQLite porque lower() los deja
        # igual en ambos lados (SQLite lower() solo convierte ASCII).
        query = query.filter(
            or_(
                Contenido.genero.ilike(f'%{genero}%'),
                Contenido.group_title.ilike(f'%{genero}%'),
            )
        )

    if año and año.isdigit():
        query = query.filter_by(año=int(año))

    if q:
        query = query.filter(
            or_(
                Contenido.titulo.ilike(f'%{q}%'),
                Contenido.genero.ilike(f'%{q}%'),
                Contenido.group_title.ilike(f'%{q}%'),
            )
        )

    _sort_map = {
        'year_desc':  [nulls_last(Contenido.año.desc()),   Contenido.fecha_agregado.desc()],
        'year_asc':   [nulls_last(Contenido.año.asc()),    Contenido.fecha_agregado.desc()],
        'title_asc':  [Contenido.titulo.asc()],
        'recent':     [Contenido.fecha_agregado.desc()],
    }
    for col in _sort_map.get(sort, _sort_map['recent']):
        query = query.order_by(col)

    return jsonify(paginate_query(query, page, per_page))


@api_bp.get('/contenido/<int:item_id>')
def get_item(item_id):
    item = Contenido.query.filter_by(id=item_id, activo=True).first_or_404()
    return jsonify(item.to_dict())


@api_bp.get('/peliculas')
def get_peliculas():
    """Shortcut: solo películas."""
    return get_contenido_by_type('pelicula')


@api_bp.get('/series')
def get_series():
    """Shortcut: solo series."""
    return get_contenido_by_type('serie')


@api_bp.get('/live')
def get_live():
    """Shortcut: solo canales en directo."""
    return get_contenido_by_type('live')


def get_contenido_by_type(tipo):
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(
        request.args.get('limit', current_app.config['ITEMS_PER_PAGE'], type=int),
        200,
    )
    query = (
        _build_visible_query()
        .filter(Contenido.tipo == tipo)
        .order_by(Contenido.fecha_agregado.desc())
    )
    return jsonify(paginate_query(query, page, per_page))


@api_bp.get('/trending')
def get_trending():
    """
    Tendencias: contenido del último año (o los 2 más recientes si hay pocos),
    selección aleatoria para que cambie en cada carga.
    Series deduplicadas: una tarjeta por título base.
    """
    import random as _random
    limit = min(request.args.get('limit', 20, type=int), 50)

    # Determinar el año de corte (último año con contenido)
    from sqlalchemy import func as _func
    max_year = (
        db.session.query(_func.max(Contenido.año))
        .filter(Contenido.activo == True, Contenido.tipo != 'live', Contenido.año.isnot(None))
        .scalar()
    ) or 0
    # Incluir también el año anterior para tener suficiente variedad
    min_year = max(max_year - 1, max_year)

    candidates = (
        Contenido.query
        .filter(
            Contenido.activo == True,
            Contenido.tipo != 'live',
            Contenido.año >= min_year,
            Contenido.imagen.isnot(None),
            Contenido.imagen != '',
        )
        .order_by(Contenido.año.desc(), Contenido.fecha_agregado.desc())
        .limit(limit * 20)   # pool amplio para poder mezclar y deduplicar
        .all()
    )

    # Si no hay suficientes con imagen en el último año, relajar el filtro
    if len(candidates) < limit * 3:
        candidates = (
            Contenido.query
            .filter(Contenido.activo == True, Contenido.tipo != 'live')
            .order_by(Contenido.año.desc(), Contenido.fecha_agregado.desc())
            .limit(limit * 20)
            .all()
        )

    # Mezclar para que cada visita muestre un orden diferente
    _random.shuffle(candidates)

    seen_series: set = set()
    result: list = []
    for item in candidates:
        if item.tipo == 'serie' or item.temporada is not None:
            base = _get_base_title(item.titulo)
            if base in seen_series:
                continue
            seen_series.add(base)
        result.append(item)
        if len(result) >= limit:
            break

    return jsonify([i.to_dict() for i in result])


def _clean_genre_text(text: str) -> str:
    """
    Limpia emojis y caracteres decorativos de textos de group-title.
    Elimina: emojis, flechas (⏩⏪), llaves decorativas, asteriscos, etc.
    Elimina también años de 4 dígitos (ej: "ESTRENOS 2021" → "ESTRENOS").
    Conserva: letras (incluidas las acentuadas), dígitos no-año, espacios, guiones.
    Devuelve el texto en mayúsculas para que el LIKE en SQLite lo encuentre
    directamente en el group_title original (que también suele ser mayúsculas).
    """
    # Conservar solo letras unicode, dígitos, espacios, guiones y paréntesis
    cleaned = _re.sub(r'[^\w\s\-\(\)]', ' ', text)
    # Eliminar números de 4 dígitos que parecen años (2000-2029)
    cleaned = _re.sub(r'\b20[0-2]\d\b', '', cleaned)
    cleaned = _re.sub(r'\b19\d{2}\b', '', cleaned)
    # Normalizar espacios y convertir a mayúsculas (para coincidir con group_title)
    return ' '.join(cleaned.split()).upper()


@api_bp.get('/generos')
def get_generos():
    """Lista de géneros únicos disponibles."""
    rows = db.session.query(Contenido.genero).filter(
        Contenido.activo == True,
        Contenido.genero != None,
        Contenido.genero != '',
    ).distinct().all()

    generos = set()
    for (g,) in rows:
        for part in g.split(','):
            cleaned = part.strip()
            if cleaned:
                generos.add(cleaned)

    # Si hay muy pocos géneros, usar group_title como fallback
    # Solo de contenido NO-live (excluye grupos de canales de TV)
    # Lista de valores a omitir como "géneros" (son categorías genéricas, no géneros reales)
    # Se compara en mayúsculas con la versión limpia del group_title
    _SKIP = {
        'VOD', 'VOD SPAIN', 'SERIES', 'PELICULAS', 'MOVIES', 'LIVE TV', 'LIVE',
        'ADULT', 'XXX', 'SPORTS', 'NEWS', 'KIDS', 'ENTERTAINMENT', 'GENERAL',
        'UNDEFINED', 'UK', 'US', 'ES', 'LATINO', 'ESPANOL', 'ENGLISH',
        'TV', 'TDT', 'RADIO', 'CANAL', 'CANALES', 'CHANNEL', 'CHANNELS',
        'MUSIC', 'MUSICA', 'DEPORTES', 'NOTICIAS',
    }
    if len(generos) < 5:
        rows2 = db.session.query(Contenido.group_title).filter(
            Contenido.activo == True,
            Contenido.tipo != 'live',   # excluir grupos de canales en directo
            Contenido.group_title != None,
            Contenido.group_title != '',
        ).distinct().all()
        for (g,) in rows2:
            # Usar el valor original (no _clean_genre_text) para que el filtro por
            # group_title coincida exactamente con lo almacenado en la BD
            cleaned_check = _clean_genre_text(g)   # solo para la comprobación _SKIP
            if (cleaned_check and cleaned_check not in _SKIP
                    and 2 < len(g.strip()) <= 60):
                generos.add(g.strip())

    return jsonify(sorted(generos))


# ── Helper para extraer título base de serie ───────────────

def _get_base_title(title: str) -> str:
    """
    Elimina info de temporada/episodio del título para agrupar series.
    Maneja el formato IPTV habitual: "{título} S01 {título} - S01E52"
    """
    _EP_PATTERNS = [
        r'\s+[Ss]\d{1,3}\s*[Ee]\d{1,3}.*$',           # S01E01, S01.E01, S01-E01
        r'\s+\d{1,2}[xX]\d{1,3}.*$',                   # 1x01, 2x10
        r'\s+[-–]\s*[Ss]eason\s*\d+.*$',                # - Season 1
        r'\s+[-–]\s*[Tt]emporada\s*\d+.*$',             # - Temporada 1
        r'\s+[Tt]\d+\s*[Ee]\d+.*$',                     # T1E01
        r'\s+[-–:]\s*[Cc]ap[íi]tulo\s*\d+.*$',         # - Capitulo 1
        r'\s+[-–:]\s*[Ee]p(?:isodio|isode)?\.?\s*\d+.*$',   # Episodio / Episode 1
        # Limpieza del marcador de temporada suelto (formato IPTV: "Título S01 Título")
        # Se aplica DESPUÉS de quitar el patrón SnnEmm para eliminar " S01 resto"
        r'\s+[Ss]\d{1,2}\b.*$',                         # S01 ... al final
        r'\s+[-–:]\s*\d+$',                              # número suelto al final
    ]
    result = title.strip()
    for p in _EP_PATTERNS:
        new = _re.sub(p, '', result, flags=_re.IGNORECASE).strip(' -–:')
        if new:
            result = new
    return result or title.strip()


@api_bp.get('/series-agrupadas')
def get_series_agrupadas():
    """
    Series agrupadas por título base (un ítem por serie).
    Devuelve: título, imagen, año, géneros, nº temporadas, nº episodios.
    """
    page     = max(1, request.args.get('page', 1, type=int))
    per_page = min(request.args.get('limit', 24, type=int), 100)
    q        = request.args.get('q', '').strip()
    genero   = request.args.get('genero', '').strip()
    sort     = request.args.get('sort', 'title_asc')

    # Incluir tipo='serie', items 'live' con temporada (series mal clasificadas por el
    # parser antiguo) Y tipo='pelicula' con temporada (importados antes del tipos_override)
    base_q = Contenido.query.filter(
        Contenido.activo == True,
        or_(
            Contenido.tipo == 'serie',
            and_(
                Contenido.tipo == 'live',
                Contenido.temporada != None,   # tiene S01E01 → es serie, no canal
            ),
            and_(
                Contenido.tipo == 'pelicula',
                Contenido.temporada != None,   # importado antes del tipos_override
            ),
        ),
    )
    if q:
        base_q = base_q.filter(Contenido.titulo.ilike(f'%{q}%'))
    if genero:
        base_q = base_q.filter(
            or_(Contenido.genero.ilike(f'%{genero}%'),
                Contenido.group_title.ilike(f'%{genero}%'))
        )

    all_eps = base_q.all()

    groups: dict = {}
    for ep in all_eps:
        base = _get_base_title(ep.titulo)
        if base not in groups:
            groups[base] = {
                'first_id':   ep.id,
                'image':      ep.imagen or '',
                'year':       ep.año,
                'genres':     [],
                'seasons':    set(),
                'ep_count':   0,
                'group_title': ep.group_title or '',
                'added_at':   ep.fecha_agregado,
                'source':     ep.fuente,
            }
        g = groups[base]
        g['ep_count'] += 1
        if ep.temporada:
            g['seasons'].add(ep.temporada)
        if ep.imagen and not g['image']:
            g['image'] = ep.imagen
        if ep.año and not g['year']:
            g['year'] = ep.año
        if ep.genero and not g['genres']:
            g['genres'] = [x.strip() for x in ep.genero.split(',') if x.strip()]
        if ep.fecha_agregado and (
            not g['added_at'] or ep.fecha_agregado > g['added_at']
        ):
            g['added_at'] = ep.fecha_agregado

    series_list = []
    for base_title, data in groups.items():
        series_list.append({
            'id':           data['first_id'],
            'title':        base_title,
            'type':         'series',
            'source':       data['source'],
            'streamUrl':    '',
            'image':        data['image'],
            'year':         data['year'],
            'genres':       data['genres'],
            'seasonCount':  len(data['seasons']) or 1,
            'episodeCount': data['ep_count'],
            'groupTitle':   data['group_title'],
            'addedAt':      data['added_at'].isoformat() if data['added_at'] else None,
        })

    if sort == 'recent':
        series_list.sort(key=lambda x: x.get('addedAt') or '', reverse=True)
    elif sort == 'year_desc':
        series_list.sort(key=lambda x: (x.get('year') or 0), reverse=True)
    elif sort == 'year_asc':
        series_list.sort(key=lambda x: (x.get('year') or 9999))
    else:
        series_list.sort(key=lambda x: x['title'].lower())

    total = len(series_list)
    start = (page - 1) * per_page
    items = series_list[start:start + per_page]

    return jsonify({
        'items':    items,
        'total':    total,
        'page':     page,
        'pages':    max(1, (total + per_page - 1) // per_page),
        'per_page': per_page,
    })


def _normalize_live_base(title: str) -> str:
    """
    Strip quality/variant suffixes so duplicate live channels can be grouped.
    Examples:
      "DAZN FHD 1"  → "DAZN"      "DAZN HD 2"   → "DAZN"
      "ESPN 2 HD"   → "ESPN 2"     "La 1 HD"     → "La 1"
      "Telecinco HD"→ "Telecinco"
    """
    quality = r'(?:FULL\s?HD|FHD|UHD|4K|2K|1080[pP]?|720[pP]?|480[pP]?|360[pP]?|HD\+?|SD|HQ|LQ)'
    t = title.strip()
    for _ in range(3):
        prev = t
        # "[base] [quality] [optional 1-2 digit number]"  →  "[base]"
        t = _re.sub(rf'\s+{quality}(?:\s+\d{{1,2}})?\s*$', '', t, flags=_re.IGNORECASE).strip()
        # "[base] [1-2 digit number] [quality]"  →  "[base]"
        t = _re.sub(rf'\s+\d{{1,2}}\s+{quality}\s*$', '', t, flags=_re.IGNORECASE).strip()
        if t == prev or not t:
            break
    return t or title.strip()


@api_bp.get('/live-agrupados')
def get_live_agrupados():
    """
    Canales en directo agrupados por nombre base (elimina sufijos de calidad/variante).
    Devuelve cada grupo con sus canales internos para mostrar un selector de calidad.
    """
    q         = request.args.get('q', '').strip()
    categoria = request.args.get('categoria', '').strip()

    base_q = _build_visible_query().filter(
        Contenido.tipo == 'live',
        Contenido.temporada == None,   # excluir live con S01E01 (son series)
    )
    if q:
        base_q = base_q.filter(Contenido.titulo.ilike(f'%{q}%'))
    if categoria:
        base_q = base_q.filter(Contenido.group_title.ilike(f'%{categoria}%'))

    channels = base_q.order_by(Contenido.titulo.asc()).all()

    groups: dict = {}
    for ch in channels:
        base = _normalize_live_base(ch.titulo)
        if base not in groups:
            groups[base] = {
                'first_id':    ch.id,
                'image':       ch.imagen or '',
                'genres':      [],
                'group_title': ch.group_title or '',
                'channels':    [],
                'source':      ch.fuente,
            }
        g = groups[base]
        g['channels'].append(ch.to_dict())
        if ch.imagen and not g['image']:
            g['image'] = ch.imagen
        if ch.genero and not g['genres']:
            g['genres'] = [x.strip() for x in ch.genero.split(',') if x.strip()]

    result = []
    for base_title, data in sorted(groups.items(), key=lambda x: x[0].lower()):
        best_ch = data['channels'][0]
        result.append({
            'id':           data['first_id'],
            'title':        base_title,
            'type':         'live',
            'source':       data['source'],
            'streamUrl':    best_ch['streamUrl'],
            'image':        data['image'],
            'year':         None,
            'genres':       data['genres'],
            'groupTitle':   data['group_title'],
            'channelCount': len(data['channels']),
            'channels':     data['channels'],
        })

    return jsonify(result)


@api_bp.get('/live-categorias')
def get_live_categorias():
    """
    Categorías de canales en directo.
    Usa group_title si está disponible, si no usa genero como fallback.
    """
    rows = db.session.query(Contenido.group_title).filter(
        Contenido.activo == True,
        Contenido.tipo == 'live',
        Contenido.group_title != None,
        Contenido.group_title != '',
    ).distinct().all()
    cats = sorted({row[0].strip() for row in rows if row[0].strip()}, key=str.lower)

    return jsonify(cats)


@api_bp.get('/serie-episodios')
def get_serie_episodios():
    """Devuelve todos los episodios de una serie dado su título base."""
    titulo = request.args.get('titulo', '').strip()
    if not titulo:
        return jsonify([])

    # Igual que series-agrupadas: incluir 'serie', 'live' con temporada y 'pelicula' con temporada
    all_eps = Contenido.query.filter(
        Contenido.activo == True,
        or_(
            Contenido.tipo == 'serie',
            and_(
                Contenido.tipo == 'live',
                Contenido.temporada != None,
            ),
            and_(
                Contenido.tipo == 'pelicula',
                Contenido.temporada != None,
            ),
        ),
    ).all()
    episodes = [ep.to_dict() for ep in all_eps if _get_base_title(ep.titulo) == titulo]
    episodes.sort(key=lambda x: (x.get('season') or 99, x.get('episode') or 99))
    return jsonify(episodes)


@api_bp.get('/anos')
def get_años():
    """Lista de años disponibles (para filtros)."""
    rows = db.session.query(Contenido.año).filter(
        Contenido.activo == True,
        Contenido.año != None,
    ).distinct().order_by(Contenido.año.desc()).all()
    return jsonify([r[0] for r in rows])


@api_bp.get('/proxy-image')
def proxy_image():
    """Proxy para imágenes externas — bypass hotlinking/VPN de cinemacity.cc."""
    url = request.args.get('url', '').strip()
    if not url or not url.lower().startswith('http'):
        return '', 400
    try:
        resp = requests.get(url, timeout=8, headers={
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Referer': 'https://cinemacity.cc/',
        })
        content_type = resp.headers.get('content-type', 'image/jpeg')
        return Response(
            resp.content,
            mimetype=content_type,
            headers={'Cache-Control': 'public, max-age=86400'},
        )
    except Exception:
        return '', 404


@api_bp.get('/stream-proxy')
def stream_proxy():
    """
    Relay de stream con CORS.
    El VPS descarga el stream y lo retransmite al navegador con
    Access-Control-Allow-Origin: * para que HLS.js / <video> puedan cargarlo.
    También sirve para esquivar bloqueos de IP a nivel de navegador.
    """
    url = request.args.get('url', '').strip()
    if not url or not url.lower().startswith('http'):
        return '', 400
    if _is_private(url):
        return '', 403

    hdrs = {**_PROXY_UA}
    # Referer = origen del servidor IPTV; valida sesión de segmentos HLS (/hlsr/)
    _p = _urlparse(url)
    hdrs['Referer'] = f'{_p.scheme}://{_p.netloc}/'
    if request.headers.get('Range'):          # soporte parcial de contenido (seeking)
        hdrs['Range'] = request.headers['Range']

    try:
        up = requests.get(url, stream=True, headers=hdrs, timeout=(8, 20),
                          proxies={}, allow_redirects=True)
        ct = _content_type_for_url(url, up.headers.get('Content-Type', ''))

        out_hdrs = {
            'Access-Control-Allow-Origin':  '*',
            'Access-Control-Allow-Headers': 'Range',
            'Access-Control-Expose-Headers': 'Content-Length, Content-Range, Accept-Ranges',
            'Cache-Control': 'no-cache',
            # Desactiva el buffering de nginx para que los chunks lleguen al cliente
            # en tiempo real (crítico para streams live y progresivos de video)
            'X-Accel-Buffering': 'no',
        }
        for h in ('Content-Length', 'Content-Range', 'Accept-Ranges'):
            if h in up.headers:
                out_hdrs[h] = up.headers[h]

        def _gen():
            try:
                for chunk in up.iter_content(chunk_size=32768):
                    if chunk:
                        yield chunk
            except Exception:
                pass

        return Response(_gen(), status=up.status_code,
                        content_type=ct, headers=out_hdrs)
    except requests.exceptions.Timeout:
        return '', 504
    except Exception:
        return '', 502


@api_bp.get('/hls-proxy')
def hls_proxy():
    """
    Proxy de manifests HLS (.m3u8).
    Descarga el manifest y reescribe todas las URIs (segmentos, claves,
    sub-playlists) para que también pasen por /api/stream-proxy.
    Permite que HLS.js cargue cualquier stream sin restricciones de CORS.
    """
    url = request.args.get('url', '').strip()
    if not url or not url.lower().startswith('http'):
        return '', 400
    if _is_private(url):
        return '', 403

    try:
        parsed   = _urlparse(url)
        mfst_hdrs = {
            **_PROXY_UA,
            'Referer': f'{parsed.scheme}://{parsed.netloc}/',
        }
        resp = requests.get(url, headers=mfst_hdrs, timeout=15,
                            proxies={}, allow_redirects=True)
        resp.raise_for_status()

        base_url = f'{parsed.scheme}://{parsed.netloc}{parsed.path.rsplit("/", 1)[0]}/'
        ps = request.host_url.rstrip('/') + '/api/stream-proxy'
        ph = request.host_url.rstrip('/') + '/api/hls-proxy'

        lines = []
        for line in resp.text.splitlines():
            s = line.strip()
            if not s:
                lines.append('')
                continue
            if s.startswith('#'):
                # Reescribir URI="..." en directivas (ej: EXT-X-KEY)
                if 'URI="' in s:
                    def _make_rep(_ps):
                        def _rep(m):
                            u = m.group(1)
                            if not u.startswith('http'):
                                u = _urljoin(base_url, u)
                            return f'URI="{_ps}?url={_quote(u, safe="")}"'
                        return _rep
                    s = _re.sub(r'URI="([^"]+)"', _make_rep(ps), s)
                lines.append(s)
            else:
                # Líneas de URI (segmentos .ts, sub-playlists .m3u8, etc.)
                full = s if s.startswith('http') else _urljoin(base_url, s)
                enc  = _quote(full, safe='')
                target = ph if '.m3u8' in s.lower() else ps
                lines.append(f'{target}?url={enc}')

        return Response(
            '\n'.join(lines),
            content_type='application/vnd.apple.mpegurl',
            headers={
                'Access-Control-Allow-Origin': '*',
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            },
        )
    except Exception:
        return '', 502


@api_bp.get('/playlist/<int:item_id>.m3u')
def item_playlist(item_id):
    """
    Descarga un .m3u de un ítem concreto.
    El sistema operativo lo abre en el reproductor registrado (VLC, Kodi, MPV…)
    que puede reproducir cualquier formato: MKV, TS, IPTV, etc.
    """
    item = Contenido.query.filter_by(id=item_id, activo=True).first_or_404()
    m3u = (
        '#EXTM3U\n'
        f'#EXTINF:-1 tvg-logo="{item.imagen or ""}",{item.titulo}\n'
        f'{item.url_stream}\n'
    )
    return Response(
        m3u,
        content_type='audio/x-mpegurl',
        headers={
            'Content-Disposition': f'attachment; filename="stream_{item_id}.m3u"',
            'Cache-Control': 'no-store',
        },
    )


@api_bp.get('/og-image')
def og_image():
    """
    Extrae og:image de una página web y la sirve como proxy.
    Útil para ítems RSS que no tienen imagen en el feed pero sí en la página.
    """
    url = request.args.get('url', '').strip()
    if not url or not url.lower().startswith('http'):
        return '', 400
    _HEADERS = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
    }
    try:
        resp = requests.get(url, timeout=10, headers=_HEADERS, stream=False)
        html = resp.text[:50000]  # solo los primeros 50 KB para no descargar todo

        # Buscar og:image (dos órdenes de atributos posibles)
        m = _re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            html, _re.IGNORECASE,
        )
        if not m:
            m = _re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                html, _re.IGNORECASE,
            )
        if not m:
            # Fallback: primera imagen grande del HTML
            m = _re.search(
                r'<img[^>]+src=["\']([^"\']*(?:poster|cover|thumb|banner|image)[^"\']*)["\']',
                html, _re.IGNORECASE,
            )

        if m:
            img_url = m.group(1).strip()
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            elif img_url.startswith('/'):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                img_url = f'{parsed.scheme}://{parsed.netloc}{img_url}'

            img_resp = requests.get(img_url, timeout=8, headers={**_HEADERS, 'Referer': url})
            ct = img_resp.headers.get('content-type', 'image/jpeg')
            return Response(
                img_resp.content,
                mimetype=ct,
                headers={'Cache-Control': 'public, max-age=86400'},
            )
    except Exception:
        pass
    return '', 404


@api_bp.get('/stats')
def get_stats():
    """Estadísticas básicas (usadas en el frontend y admin)."""
    total_peliculas = Contenido.query.filter_by(tipo='pelicula', activo=True).count()
    total_series = Contenido.query.filter_by(tipo='serie', activo=True).count()
    total_live = Contenido.query.filter_by(tipo='live', activo=True).count()
    total_inactivos = Contenido.query.filter_by(activo=False).count()
    total_listas = Lista.query.filter_by(activa=True).count()

    return jsonify({
        'peliculas': total_peliculas,
        'series': total_series,
        'live': total_live,
        'inactivos': total_inactivos,
        'listas': total_listas,
        'total': total_peliculas + total_series + total_live,
    })


# ── Watch history y recomendaciones ────────────────────────

@api_bp.post('/watch')
def record_watch():
    """
    Registra una reproducción para alimentar el motor de recomendaciones.
    Acepta:
      session_key  — ID de sesión anónima (generado en el cliente)
      contenido_id — ID del ítem reproducido
    """
    data = request.get_json(silent=True) or {}
    session_key  = (data.get('session_key') or '').strip()[:64]
    contenido_id = data.get('contenido_id')

    if not session_key or not contenido_id:
        return jsonify({'ok': False}), 400

    item = Contenido.query.filter_by(id=contenido_id, activo=True).first()
    if not item:
        return jsonify({'ok': False}), 404

    user_id = _session.get('user_id')

    # Deduplica: no registrar el mismo item dos veces en 30 minutos
    from datetime import timedelta
    from sqlalchemy import and_ as _and_
    cutoff = __import__('datetime').datetime.utcnow() - timedelta(minutes=30)
    exists = WatchHistory.query.filter(
        _and_(
            WatchHistory.session_key == session_key,
            WatchHistory.contenido_id == contenido_id,
            WatchHistory.played_at >= cutoff,
        )
    ).first()

    if not exists:
        genres_snap = item.genero or ''
        w = WatchHistory(
            session_key=session_key,
            user_id=user_id,
            contenido_id=contenido_id,
            genres_snapshot=genres_snap,
        )
        db.session.add(w)
        db.session.commit()

    return jsonify({'ok': True})


@api_bp.get('/recomendaciones')
def get_recomendaciones():
    """
    Recomendaciones personalizadas basadas en historial de reproducción.

    Parámetros:
      session_key  — ID de sesión anónima del cliente
      limit        — número de resultados (default 20, max 60)
      context_id   — ID de un ítem concreto para "porque viste X"
                     (si se indica, devuelve items del mismo género/tipo)

    Algoritmo:
      1. Recuperar los últimos 30 items vistos por esta sesión
      2. Construir perfil de géneros ponderado (más reciente = más peso)
      3. Puntuar todos los items activos por overlap de géneros
      4. Excluir los ya vistos recientemente
      5. Devolver top N mezclado con algo de aleatoriedad (no siempre el mismo orden)
    """
    import random as _rand
    session_key = request.args.get('session_key', '').strip()[:64]
    limit       = min(request.args.get('limit', 20, type=int), 60)
    context_id  = request.args.get('context_id', type=int)

    # ── 1. Perfil del usuario ───────────────────────────────
    # Si hay context_id, usar ese item como contexto (para "porque viste X")
    context_item = None
    if context_id:
        context_item = Contenido.query.filter_by(id=context_id, activo=True).first()

    genre_weights: dict[str, float] = {}
    watched_ids: set[int] = set()

    if session_key:
        recent = (
            WatchHistory.query
            .filter_by(session_key=session_key)
            .order_by(WatchHistory.played_at.desc())
            .limit(50)
            .all()
        )
        for i, w in enumerate(recent):
            watched_ids.add(w.contenido_id)
            decay = 1.0 / (i + 1)   # más reciente = más peso
            genres = [g.strip() for g in (w.genres_snapshot or '').split(',') if g.strip()]
            for g in genres:
                genre_weights[g] = genre_weights.get(g, 0) + decay

    # Si hay item de contexto, sus géneros dominan
    if context_item:
        ctx_genres = [g.strip() for g in (context_item.genero or '').split(',') if g.strip()]
        for g in ctx_genres:
            genre_weights[g] = genre_weights.get(g, 0) + 5.0   # boost fuerte

    # Sin perfil ni contexto → devolver trending normal
    if not genre_weights:
        import random as _r
        candidates = (
            Contenido.query
            .filter(
                Contenido.activo == True,
                Contenido.tipo != 'live',
                Contenido.imagen.isnot(None),
                Contenido.imagen != '',
            )
            .order_by(Contenido.fecha_agregado.desc())
            .limit(limit * 5)
            .all()
        )
        _r.shuffle(candidates)
        return jsonify([c.to_dict() for c in candidates[:limit]])

    # ── 2. Candidatos: todo el contenido activo no visto ───
    base_q = _build_visible_query().filter(
        Contenido.tipo != 'live',
    )
    if watched_ids:
        base_q = base_q.filter(Contenido.id.notin_(list(watched_ids)[:500]))
    if context_item:
        base_q = base_q.filter(Contenido.tipo == context_item.tipo)

    pool = base_q.limit(2000).all()

    # ── 3. Puntuar candidatos ──────────────────────────────
    top_genres = sorted(genre_weights, key=genre_weights.get, reverse=True)[:5]

    def _score(item: Contenido) -> float:
        if not item.genero:
            return 0.0
        item_genres = {g.strip() for g in item.genero.split(',') if g.strip()}
        score = sum(genre_weights.get(g, 0) for g in item_genres)
        # Pequeño boost por imagen disponible (mejor experiencia visual)
        if item.imagen:
            score += 0.3
        # Jitter aleatorio ±0.1 para evitar que el mismo orden se repita siempre
        score += _rand.uniform(-0.1, 0.1)
        return score

    ranked = sorted(pool, key=_score, reverse=True)

    # ── 4. Diversificar: no más de 3 items del mismo género ─
    genre_quota: dict[str, int] = {}
    result: list[Contenido] = []
    for item in ranked:
        if len(result) >= limit:
            break
        main_genre = (item.genero or '').split(',')[0].strip()
        if genre_quota.get(main_genre, 0) >= 4:
            continue
        genre_quota[main_genre] = genre_quota.get(main_genre, 0) + 1
        result.append(item)

    # Rellenar si quedan huecos
    if len(result) < limit:
        seen_ids = {i.id for i in result}
        for item in ranked:
            if len(result) >= limit:
                break
            if item.id not in seen_ids:
                result.append(item)

    return jsonify({
        'items':       [i.to_dict() for i in result],
        'top_genres':  top_genres[:3],
        'context':     context_item.to_dict() if context_item else None,
    })


# ── Reportes de canales ────────────────────────────────────

@api_bp.post('/reportar/<int:contenido_id>')
def reportar_canal(contenido_id):
    """El usuario reporta que un canal no funciona."""
    c = Contenido.query.get_or_404(contenido_id)
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()

    # Evitar duplicados recientes (misma IP + mismo canal en los últimos 10 min)
    from datetime import timedelta
    from sqlalchemy import and_ as _and_
    hace_10 = __import__('datetime').datetime.utcnow() - timedelta(minutes=10)
    existe = ChannelReport.query.filter(
        _and_(
            ChannelReport.contenido_id == contenido_id,
            ChannelReport.ip_address == ip,
            ChannelReport.fecha_creacion >= hace_10,
        )
    ).first()
    if existe:
        return jsonify({'ok': True, 'duplicate': True})

    report = ChannelReport(contenido_id=contenido_id, ip_address=ip)
    db.session.add(report)
    db.session.commit()
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════════════════
# LIVE — GESTIÓN DE CANALES EN DIRECTO (failover, scan config)
# ═══════════════════════════════════════════════════════════════

def _get_or_create_scan_config():
    """Devuelve LiveScanConfig, creándola con valores por defecto si no existe."""
    config = LiveScanConfig.query.first()
    if config is None:
        config = LiveScanConfig(auto_scan_enabled=True, interval_hours=24)
        db.session.add(config)
        db.session.commit()
    return config


@api_bp.get('/live/scan-config')
def get_live_scan_config():
    """Devuelve la configuración del escaneo automático de canales en directo."""
    return jsonify(_get_or_create_scan_config().to_dict())


@api_bp.post('/live/scan-config')
def update_live_scan_config():
    """
    Actualiza la configuración del escaneo automático.
    Body JSON: { "auto_scan_enabled": bool, "interval_hours": int (24|48|72) }
    """
    data = request.get_json(silent=True) or {}
    config = _get_or_create_scan_config()

    if 'auto_scan_enabled' in data:
        config.auto_scan_enabled = bool(data['auto_scan_enabled'])

    if 'interval_hours' in data:
        hours = int(data['interval_hours'])
        if hours not in (24, 48, 72):
            return jsonify({'error': 'interval_hours debe ser 24, 48 o 72'}), 400
        config.interval_hours = hours

    db.session.commit()
    return jsonify(config.to_dict())


@api_bp.post('/live/<int:channel_id>/report-down')
def report_live_down(channel_id):
    """
    El cliente informa que una URL de canal en directo no responde.
    Si coincide con la URL activa → el backend hace failover a la siguiente.
    Responde con: { next_url, channel_still_alive }
    """
    import json as _json
    data = request.get_json(silent=True) or {}
    reported_url = data.get('url', '').strip()

    channel = Contenido.query.filter_by(id=channel_id, tipo='live', activo=True).first()
    if channel is None:
        return jsonify({'next_url': None, 'channel_still_alive': False})

    # Obtener lista completa de URLs
    try:
        urls = _json.loads(channel.live_urls_json) if channel.live_urls_json else []
    except (ValueError, TypeError):
        urls = []
    if not urls:
        urls = [channel.url_stream]

    current_idx = channel.live_active_idx or 0

    # Comprobar si la URL reportada es la activa
    try:
        reported_idx = urls.index(reported_url)
    except ValueError:
        reported_idx = current_idx   # URL desconocida → asumir que es la activa

    if reported_idx != current_idx:
        # El cliente reporta una URL que ya no es la activa → dar la activa actual
        active_url = urls[current_idx] if current_idx < len(urls) else None
        return jsonify({'next_url': active_url, 'channel_still_alive': True})

    # Buscar la siguiente URL disponible
    next_idx = None
    for i in range(current_idx + 1, len(urls)):
        next_idx = i
        break

    if next_idx is not None:
        channel.live_active_idx = next_idx
        db.session.commit()
        return jsonify({'next_url': urls[next_idx], 'channel_still_alive': True})
    else:
        # Sin más URLs de respaldo → informar al cliente, pero NO desactivar el canal.
        # El escáner periódico es quien debe decidir si un canal está realmente muerto.
        # Desactivarlo aquí causaría que un simple error de red de un usuario
        # mate el canal permanentemente para todos.
        return jsonify({'next_url': None, 'channel_still_alive': False})


@api_bp.post('/live/<int:channel_id>/add-url')
def add_live_url(channel_id):
    """
    Añade una URL de respaldo al canal. La nueva URL se añade al FINAL
    de la lista (no desplaza a la URL activa actual).
    Body JSON: { "url": "rtsp://..." }
    """
    import json as _json
    data = request.get_json(silent=True) or {}
    new_url = data.get('url', '').strip()
    if not new_url:
        return jsonify({'error': 'url requerida'}), 400

    channel = Contenido.query.filter_by(id=channel_id, tipo='live').first_or_404()

    try:
        urls = _json.loads(channel.live_urls_json) if channel.live_urls_json else []
    except (ValueError, TypeError):
        urls = []
    if not urls:
        urls = [channel.url_stream]

    if new_url in urls:
        return jsonify({'ok': True, 'duplicate': True, 'urls': urls})

    urls.append(new_url)
    channel.live_urls_json = _json.dumps(urls)
    db.session.commit()
    return jsonify({'ok': True, 'urls': urls})


@api_bp.get('/live/scan-reports')
def get_live_scan_reports():
    """
    Devuelve los reportes de las últimas verificaciones.
    Por defecto solo las URLs caídas; ?all=1 para todos.
    """
    show_all = request.args.get('all', '0') == '1'
    limit = min(request.args.get('limit', 100, type=int), 500)

    q = LiveScanReport.query.order_by(LiveScanReport.timestamp.desc())
    if not show_all:
        q = q.filter_by(resultado=False)
    reports = q.limit(limit).all()
    return jsonify([r.to_dict() for r in reports])


@api_bp.post('/live/scan/run')
def run_live_scan_now():
    """Lanza el escaneo de canales en directo de forma inmediata (manual)."""
    import threading

    def _run():
        from link_checker import scan_live_channels
        scan_live_channels(current_app._get_current_object())

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({'ok': True, 'message': 'Escaneo iniciado en background'})


@api_bp.post('/live/<int:channel_id>/set-server')
def set_live_server(channel_id):
    """
    Selección manual de servidor para un canal en directo.
    Body JSON: { "index": N }  — índice en la lista liveUrls del canal.
    Responde con: { ok, active_url, active_index }
    """
    import json as _json
    data = request.get_json(silent=True) or {}
    idx  = data.get('index')

    if idx is None:
        return jsonify({'error': 'index requerido'}), 400

    channel = Contenido.query.filter_by(id=channel_id, tipo='live').first_or_404()

    try:
        urls = _json.loads(channel.live_urls_json) if channel.live_urls_json else []
    except (ValueError, TypeError):
        urls = []
    if not urls:
        urls = [channel.url_stream]

    idx = int(idx)
    if idx < 0 or idx >= len(urls):
        return jsonify({'error': f'index fuera de rango (0-{len(urls)-1})'}), 400

    channel.live_active_idx = idx
    channel.activo = True
    db.session.commit()

    return jsonify({
        'ok':           True,
        'active_url':   urls[idx],
        'active_index': idx,
    })


@api_bp.get('/live/<int:channel_id>/servers')
def get_live_servers(channel_id):
    """
    Devuelve todos los servidores disponibles para un canal, con estado de
    la última verificación conocida.
    """
    import json as _json
    channel = Contenido.query.filter_by(id=channel_id, tipo='live').first_or_404()

    try:
        urls = _json.loads(channel.live_urls_json) if channel.live_urls_json else []
    except (ValueError, TypeError):
        urls = []
    if not urls:
        urls = [channel.url_stream]

    active_idx = channel.live_active_idx or 0

    # Obtener último resultado de scan para cada URL
    from models import LiveScanReport
    from sqlalchemy import func
    last_reports = {}
    for url in urls:
        rep = (
            LiveScanReport.query
            .filter_by(contenido_id=channel_id, url_probada=url)
            .order_by(LiveScanReport.timestamp.desc())
            .first()
        )
        if rep:
            last_reports[url] = {
                'alive':      rep.resultado,
                'latency_ms': rep.latencia_ms,
                'checked_at': rep.timestamp.isoformat(),
            }

    servers = []
    for i, url in enumerate(urls):
        entry = {
            'index':    i,
            'url':      url,
            'active':   (i == active_idx),
            'label':    f'Servidor {i + 1}',
        }
        if url in last_reports:
            entry.update(last_reports[url])
        servers.append(entry)

    return jsonify({'servers': servers, 'active_index': active_idx})


# ── Versión de la app (para notificación de actualización) ──────

# Bump este número cuando publiques una nueva APK
APP_VERSION = "2.1"
APK_URL     = "https://cinecadiz.servegame.com/download/cinecadiz.apk"

@api_bp.get('/version')
def app_version():
    return jsonify({
        'version': APP_VERSION,
        'apk_url': APK_URL,
    })


# ── Canales curados ────────────────────────────────────────────

@api_bp.get('/canales-curados')
def canales_curados():
    """
    Lista de canales TV en directo curados manualmente por el admin.
    Devuelve los activos ordenados por orden/nombre.
    Mismo formato que Contenido.to_dict() → el APK puede usarlos con failover.
    """
    from models import CanalCurado
    canales = (
        CanalCurado.query
        .filter_by(activo=True)
        .order_by(CanalCurado.orden, CanalCurado.nombre)
        .all()
    )
    return jsonify([c.to_dict() for c in canales])

