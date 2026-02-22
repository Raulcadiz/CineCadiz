"""
API REST pública — /api/
Consumida por el frontend JavaScript.
"""
from flask import Blueprint, jsonify, request, current_app, Response
from models import db, Contenido, Lista
from sqlalchemy import or_
import requests

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
    Query params: tipo, genero, año, q (búsqueda), page, limit
    """
    tipo = request.args.get('tipo')           # 'pelicula' | 'serie'
    genero = request.args.get('genero', '')
    año = request.args.get('año', '')
    q = request.args.get('q', '').strip()
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

    query = query.order_by(Contenido.fecha_agregado.desc())
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
    """Contenido más reciente (últimas 24h o los N más nuevos)."""
    limit = min(request.args.get('limit', 20, type=int), 50)
    items = (
        Contenido.query
        .filter_by(activo=True)
        .order_by(Contenido.fecha_agregado.desc())
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
