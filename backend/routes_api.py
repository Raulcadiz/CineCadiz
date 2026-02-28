"""
API REST pública — /api/
Consumida por el frontend JavaScript.
"""
import re as _re
import socket as _socket
from urllib.parse import urlparse as _urlparse, urljoin as _urljoin, quote as _quote
from flask import Blueprint, jsonify, request, current_app, Response
from models import db, Contenido, Lista
from sqlalchemy import or_, nulls_last
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
        query = query.filter(Contenido.genero.ilike(f'%{genero}%'))

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
    """Novedades: primero los de año más reciente (2026 > 2025 …), luego los más añadidos."""
    limit = min(request.args.get('limit', 20, type=int), 50)
    items = (
        Contenido.query
        .filter_by(activo=True)
        .order_by(Contenido.año.desc(), Contenido.fecha_agregado.desc())
        .limit(limit)
        .all()
    )
    return jsonify([i.to_dict() for i in items])


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

    return jsonify(sorted(generos))


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
