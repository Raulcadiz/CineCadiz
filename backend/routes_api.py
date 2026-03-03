"""
API REST pública — /api/
Consumida por el frontend JavaScript.
"""
import re as _re
import socket as _socket
from urllib.parse import urlparse as _urlparse, urljoin as _urljoin, quote as _quote
from flask import Blueprint, jsonify, request, current_app, Response
from models import db, Contenido, Lista
from sqlalchemy import or_, and_, nulls_last
import requests

# ── Helpers de seguridad para proxies ───────────────────────────

def _is_private(url: str) -> bool:
    """Bloquea URLs que apunten a IPs privadas/locales (prevención de SSRF)."""
    try:
        h = _urlparse(url).hostname or ''
        if h in ('localhost', '127.0.0.1', '::1', '0.0.0.0', ''):
            return True
        ip = _socket.gethostbyname(h)
        p = list(map(int, ip.split('.')))
        return (p[0] == 127 or p[0] == 10
                or (p[0] == 172 and 16 <= p[1] <= 31)
                or (p[0] == 192 and p[1] == 168)
                or (p[0] == 169 and p[1] == 254))
    except Exception:
        return True   # fail-safe: si no se puede resolver, bloquear

_PROXY_UA = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
}

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

    query = Contenido.query.filter_by(activo=True)

    if tipo in ('pelicula', 'serie', 'live'):
        query = query.filter_by(tipo=tipo)

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
    per_page = current_app.config['ITEMS_PER_PAGE']
    query = (
        Contenido.query
        .filter_by(activo=True, tipo=tipo)
        .order_by(Contenido.fecha_agregado.desc())
    )
    return jsonify(paginate_query(query, page, per_page))


@api_bp.get('/trending')
def get_trending():
    """Novedades: año más reciente primero, luego fecha de adición.
    Las series se deduplicán: una sola tarjeta por serie (el episodio más reciente)
    para evitar que la misma serie ocupe 20 tarjetas en la sección Tendencias."""
    limit = min(request.args.get('limit', 20, type=int), 50)

    # Obtener más candidatos de los necesarios para poder deduplicar sin quedarnos cortos
    candidates = (
        Contenido.query
        .filter(Contenido.activo == True, Contenido.tipo != 'live')
        .order_by(Contenido.año.desc(), Contenido.fecha_agregado.desc())
        .limit(limit * 8)
        .all()
    )

    seen_series: set = set()
    result: list = []
    for item in candidates:
        # Deduplicar series: una tarjeta por título base (sin S01E01)
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
    if request.headers.get('Range'):          # soporte parcial de contenido (seeking)
        hdrs['Range'] = request.headers['Range']

    try:
        up = requests.get(url, stream=True, headers=hdrs, timeout=20,
                          proxies={}, allow_redirects=True)
        ct = up.headers.get('Content-Type', 'video/mp2t')
        # Para streams MPEG-TS, forzar content-type correcto aunque el CDN
        # devuelva 'application/octet-stream' (el navegador no lo reproduciría)
        url_path_lower = url.lower().split('?')[0]
        if url_path_lower.endswith('.ts') or ct in (
            'application/octet-stream', 'binary/octet-stream', 'application/download', ''
        ):
            ct = 'video/mp2t'

        out_hdrs = {
            'Access-Control-Allow-Origin':  '*',
            'Access-Control-Allow-Headers': 'Range',
            'Access-Control-Expose-Headers': 'Content-Length, Content-Range, Accept-Ranges',
            'Cache-Control': 'no-cache',
        }
        for h in ('Content-Length', 'Content-Range', 'Accept-Ranges'):
            if h in up.headers:
                out_hdrs[h] = up.headers[h]

        def _gen():
            try:
                for chunk in up.iter_content(chunk_size=65536):
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
        resp = requests.get(url, headers=_PROXY_UA, timeout=5,
                            proxies={}, allow_redirects=True)
        resp.raise_for_status()

        parsed   = _urlparse(url)
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
            headers={'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-cache'},
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
