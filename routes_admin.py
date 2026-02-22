"""
Panel de administración — /admin/
"""
import threading
from datetime import datetime
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash, jsonify, current_app,
)

from models import db, Lista, FuenteRSS, Contenido
from m3u_parser import fetch_and_parse
from link_checker import scan_dead_links
from rss_importer import import_rss_source, DEFAULT_RSS_SOURCES

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ── Estado del scan en memoria ─────────────────────────────────
_scan_state: dict = {'running': False, 'last_result': None}


# ── Auth ───────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated


@admin_bp.get('/login')
def login():
    return render_template('admin/login.html')


@admin_bp.post('/login')
def login_post():
    user = request.form.get('usuario', '').strip()
    pwd = request.form.get('password', '')
    if (user == current_app.config['ADMIN_USER']
            and pwd == current_app.config['ADMIN_PASSWORD']):
        session['admin_logged_in'] = True
        session.permanent = True
        return redirect(url_for('admin.dashboard'))
    flash('Usuario o contraseña incorrectos', 'danger')
    return redirect(url_for('admin.login'))


@admin_bp.get('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for('admin.login'))


# ── Dashboard ──────────────────────────────────────────────────

@admin_bp.get('/')
@login_required
def dashboard():
    stats = {
        'peliculas':   Contenido.query.filter_by(tipo='pelicula', activo=True).count(),
        'series':      Contenido.query.filter_by(tipo='serie', activo=True).count(),
        'inactivos':   Contenido.query.filter_by(activo=False).count(),
        'listas_m3u':  Lista.query.count(),
        'fuentes_rss': FuenteRSS.query.count(),
        'total_m3u':   Contenido.query.filter_by(fuente='m3u', activo=True).count(),
        'total_rss':   Contenido.query.filter_by(fuente='rss', activo=True).count(),
    }
    listas = Lista.query.order_by(Lista.fecha_creacion.desc()).all()
    fuentes = FuenteRSS.query.order_by(FuenteRSS.fecha_creacion.desc()).all()
    return render_template('admin/dashboard.html',
                           stats=stats, listas=listas,
                           fuentes=fuentes, scan_state=_scan_state)


# ── Gestión de listas M3U ──────────────────────────────────────

@admin_bp.get('/listas')
@login_required
def listas():
    all_listas = Lista.query.order_by(Lista.fecha_creacion.desc()).all()
    return render_template('admin/lists.html', listas=all_listas)


@admin_bp.post('/listas/agregar')
@login_required
def agregar_lista():
    nombre = request.form.get('nombre', '').strip()
    url = request.form.get('url', '').strip()
    # checkbox desmarcado no envía nada → in request.form es la forma correcta
    filtrar = 'filtrar_español' in request.form

    if not nombre or not url:
        flash('Nombre y URL son obligatorios', 'danger')
        return redirect(url_for('admin.listas'))
    if not url.startswith('http'):
        flash('La URL debe comenzar con http:// o https://', 'danger')
        return redirect(url_for('admin.listas'))

    lista = Lista(nombre=nombre, url=url, filtrar_español=filtrar)
    db.session.add(lista)
    db.session.commit()
    _import_lista_async(current_app._get_current_object(), lista.id)
    flash(f'Lista "{nombre}" agregada. Importando en segundo plano...', 'success')
    return redirect(url_for('admin.listas'))


@admin_bp.post('/listas/<int:lista_id>/refresh')
@login_required
def refresh_lista(lista_id):
    lista = Lista.query.get_or_404(lista_id)
    _import_lista_async(current_app._get_current_object(), lista.id)
    flash(f'Re-importando "{lista.nombre}" en segundo plano...', 'info')
    return redirect(url_for('admin.listas'))


@admin_bp.post('/listas/<int:lista_id>/eliminar')
@login_required
def eliminar_lista(lista_id):
    lista = Lista.query.get_or_404(lista_id)
    nombre = lista.nombre
    db.session.delete(lista)
    db.session.commit()
    flash(f'Lista "{nombre}" y todo su contenido eliminados.', 'success')
    return redirect(url_for('admin.listas'))


@admin_bp.post('/listas/<int:lista_id>/toggle')
@login_required
def toggle_lista(lista_id):
    lista = Lista.query.get_or_404(lista_id)
    lista.activa = not lista.activa
    db.session.commit()
    flash(f'Lista "{lista.nombre}" {"activada" if lista.activa else "desactivada"}.', 'info')
    return redirect(url_for('admin.listas'))


# ── Gestión de fuentes RSS ──────────────────────────────────────

@admin_bp.get('/rss')
@login_required
def rss():
    fuentes = FuenteRSS.query.order_by(FuenteRSS.fecha_creacion.desc()).all()
    return render_template('admin/rss.html', fuentes=fuentes)


@admin_bp.post('/rss/agregar')
@login_required
def agregar_rss():
    nombre = request.form.get('nombre', '').strip()
    url = request.form.get('url', '').strip()
    if not nombre or not url:
        flash('Nombre y URL son obligatorios', 'danger')
        return redirect(url_for('admin.rss'))
    fuente = FuenteRSS(nombre=nombre, url=url)
    db.session.add(fuente)
    db.session.commit()
    import_rss_source(current_app._get_current_object(), fuente.id)
    flash(f'Fuente RSS "{nombre}" agregada. Importando...', 'success')
    return redirect(url_for('admin.rss'))


@admin_bp.post('/rss/<int:fuente_id>/refresh')
@login_required
def refresh_rss(fuente_id):
    fuente = FuenteRSS.query.get_or_404(fuente_id)
    import_rss_source(current_app._get_current_object(), fuente.id)
    flash(f'Re-importando "{fuente.nombre}"...', 'info')
    return redirect(url_for('admin.rss'))


@admin_bp.post('/rss/<int:fuente_id>/eliminar')
@login_required
def eliminar_rss(fuente_id):
    fuente = FuenteRSS.query.get_or_404(fuente_id)
    nombre = fuente.nombre
    db.session.delete(fuente)
    db.session.commit()
    flash(f'Fuente RSS "{nombre}" eliminada.', 'success')
    return redirect(url_for('admin.rss'))


@admin_bp.post('/rss/importar-defaults')
@login_required
def importar_defaults_rss():
    """Importa las fuentes RSS por defecto de cinemacity.cc si no existen."""
    app = current_app._get_current_object()
    agregadas = 0
    for src in DEFAULT_RSS_SOURCES:
        existe = FuenteRSS.query.filter_by(url=src['url']).first()
        if not existe:
            f = FuenteRSS(nombre=src['nombre'], url=src['url'])
            db.session.add(f)
            db.session.commit()
            import_rss_source(app, f.id)
            agregadas += 1
    if agregadas:
        flash(f'{agregadas} fuentes RSS de cinemacity.cc agregadas e importando...', 'success')
    else:
        flash('Las fuentes de cinemacity.cc ya estaban agregadas.', 'info')
    return redirect(url_for('admin.rss'))


# ── Escaneo de links M3U ───────────────────────────────────────

@admin_bp.post('/scan')
@login_required
def manual_scan():
    """Escaneo multi-hilo de links caídos. Solo actúa sobre fuente='m3u'."""
    if _scan_state['running']:
        flash('Ya hay un escaneo en curso. Espera a que termine.', 'warning')
        return redirect(url_for('admin.dashboard'))

    app = current_app._get_current_object()
    batch = request.form.get('batch', app.config.get('SCAN_BATCH_SIZE', 500), type=int)
    workers = request.form.get('workers', 40, type=int)
    workers = max(5, min(workers, 80))   # entre 5 y 80

    def run():
        _scan_state['running'] = True
        try:
            result = scan_dead_links(app, batch_size=batch, max_workers=workers)
            _scan_state['last_result'] = result
        except Exception as e:
            _scan_state['last_result'] = {'error': str(e)}
        finally:
            _scan_state['running'] = False

    t = threading.Thread(target=run, daemon=True)
    t.start()
    flash(
        f'Escaneo iniciado: {batch} links con {workers} hilos en paralelo. '
        f'Refresca en unos minutos para ver resultados.',
        'info'
    )
    return redirect(url_for('admin.dashboard'))


@admin_bp.get('/api/scan-status')
@login_required
def scan_status():
    return jsonify({
        'running': _scan_state['running'],
        'last_result': _scan_state['last_result'],
    })


# ── Gestión de contenido ───────────────────────────────────────

@admin_bp.get('/contenido')
@login_required
def contenido():
    page = max(1, request.args.get('page', 1, type=int))
    tipo = request.args.get('tipo', '')
    fuente = request.args.get('fuente', '')
    q = request.args.get('q', '').strip()

    query = Contenido.query
    if tipo in ('pelicula', 'serie'):
        query = query.filter_by(tipo=tipo)
    if fuente in ('m3u', 'rss'):
        query = query.filter_by(fuente=fuente)
    if q:
        query = query.filter(Contenido.titulo.ilike(f'%{q}%'))

    pagination = query.order_by(Contenido.fecha_agregado.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    return render_template('admin/content.html',
                           pagination=pagination, tipo=tipo, fuente=fuente, q=q)


@admin_bp.post('/contenido/<int:item_id>/toggle')
@login_required
def toggle_contenido(item_id):
    item = Contenido.query.get_or_404(item_id)
    item.activo = not item.activo
    db.session.commit()
    return jsonify({'activo': item.activo})


# ── API AJAX ───────────────────────────────────────────────────

@admin_bp.get('/api/listas/<int:lista_id>/status')
@login_required
def lista_status(lista_id):
    return jsonify(Lista.query.get_or_404(lista_id).to_dict())


@admin_bp.get('/api/rss/<int:fuente_id>/status')
@login_required
def rss_status(fuente_id):
    return jsonify(FuenteRSS.query.get_or_404(fuente_id).to_dict())


# ── Importador M3U (interno) ───────────────────────────────────

def _import_lista_async(app, lista_id: int):
    t = threading.Thread(target=_import_lista, args=(app, lista_id), daemon=True)
    t.start()


def _import_lista(app, lista_id: int):
    with app.app_context():
        try:
            lista = Lista.query.get(lista_id)
            if not lista:
                return

            app.logger.info(f'[Import M3U] Iniciando: {lista.nombre}')
            items, error = fetch_and_parse(
                lista.url,
                app.config,
                filter_spanish=lista.filtrar_español,
            )

            if error:
                lista.error = error
                lista.ultima_actualizacion = datetime.utcnow()
                db.session.commit()
                app.logger.error(f'[Import M3U] Error descargando {lista.nombre}: {error}')
                return

            app.logger.info(
                f'[Import M3U] {lista.nombre}: {len(items)} items tras filtros '
                f'(filtrar_español={lista.filtrar_español})'
            )

            # ── Deduplicación en 1 sola query (no N queries) ───────
            # Para listas de 3000-7000 items, esto es crítico para el rendimiento.
            candidate_hashes = {it['url_hash'] for it in items}
            # SQLite tiene límite de ~999 variables en IN; procesamos en chunks
            existing_hashes: set[str] = set()
            chunk_list = list(candidate_hashes)
            for i in range(0, len(chunk_list), 900):
                chunk = chunk_list[i:i + 900]
                rows = db.session.query(Contenido.url_hash)\
                    .filter(Contenido.url_hash.in_(chunk)).all()
                existing_hashes.update(r[0] for r in rows)

            nuevos = 0
            for it in items:
                if it['url_hash'] in existing_hashes:
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
                    group_title=it.get('group_title', ''),
                    idioma=it.get('idioma', ''),
                    pais=it.get('pais', ''),
                    temporada=it.get('temporada'),
                    episodio=it.get('episodio'),
                    fuente='m3u',
                    lista_id=lista_id,
                )
                db.session.add(c)
                nuevos += 1
                if nuevos % 500 == 0:
                    db.session.commit()

            db.session.commit()
            lista.error = None
            lista.total_items = Contenido.query.filter_by(lista_id=lista_id).count()
            lista.items_activos = Contenido.query.filter_by(lista_id=lista_id, activo=True).count()
            lista.ultima_actualizacion = datetime.utcnow()
            db.session.commit()

            app.logger.info(
                f'[Import M3U] {lista.nombre}: {nuevos} nuevos / {lista.total_items} total'
            )

        except Exception as exc:
            app.logger.exception(f'[Import M3U] Excepción inesperada en lista {lista_id}: {exc}')
            try:
                lista = Lista.query.get(lista_id)
                if lista:
                    lista.error = f'Error interno: {exc}'
                    lista.ultima_actualizacion = datetime.utcnow()
                    db.session.commit()
            except Exception:
                pass
