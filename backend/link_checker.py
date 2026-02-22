"""
Verificador de links de stream — multi-hilo con ThreadPoolExecutor.

Estrategia:
  1. Cargar IDs + URLs de la BD (hilo principal)
  2. Verificar en paralelo con N workers (sin acceso a BD)
  3. Actualizar BD con resultados (hilo principal)

Solo se verifican items fuente='m3u' (los RSS son páginas web, no streams).
Con 40 workers y timeout=5s → ~500 links por minuto.
"""
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger(__name__)

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Range': 'bytes=0-1023',
}


def check_url(url: str, timeout: int = 5) -> bool:
    """
    True si la URL responde. Intenta HEAD; si falla, prueba GET parcial.
    Timeout corto para no bloquear el pool.
    """
    try:
        r = requests.head(url, timeout=timeout, headers=_HEADERS, allow_redirects=True)
        if r.status_code < 400:
            return True
        r2 = requests.get(url, timeout=timeout, headers=_HEADERS, stream=True)
        r2.close()
        return r2.status_code < 400
    except Exception:
        return False


def scan_dead_links(app, batch_size: int = 500, max_workers: int = 40) -> dict:
    """
    Escanea hasta `batch_size` links M3U en paralelo.

    Rendimiento estimado (40 workers, timeout 5s):
      - Batch de 500  → ~60-90 segundos
      - 7000 links completos → varias ejecuciones o batch_size=7000 (15-20 min)
    """
    from models import db, Contenido, Lista

    # ── 1. Leer datos de BD en hilo principal ──────────────────
    with app.app_context():
        timeout = app.config.get('SCAN_TIMEOUT', 5)
        rows = (
            Contenido.query
            .filter_by(activo=True, fuente='m3u')
            .order_by(Contenido.ultima_verificacion.asc().nullsfirst())
            .limit(batch_size)
            .with_entities(Contenido.id, Contenido.url_stream)
            .all()
        )

    if not rows:
        return {'checked': 0, 'alive': 0, 'dead': 0,
                'timestamp': datetime.utcnow().isoformat()}

    to_check = list(rows)
    logger.info(f'[Scan] Verificando {len(to_check)} links con {max_workers} workers...')

    # ── 2. Verificar en paralelo (sin BD) ──────────────────────
    results: dict[int, bool] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(check_url, url, timeout): cid
            for cid, url in to_check
        }
        for future in as_completed(future_map):
            cid = future_map[future]
            try:
                results[cid] = future.result()
            except Exception:
                results[cid] = False

    # ── 3. Actualizar BD en hilo principal ──────────────────────
    dead = alive = 0
    with app.app_context():
        now = datetime.utcnow()
        items = Contenido.query.filter(Contenido.id.in_(list(results.keys()))).all()
        affected_listas: set[int] = set()

        for item in items:
            is_alive = results.get(item.id, False)
            item.ultima_verificacion = now
            if not is_alive:
                item.activo = False
                dead += 1
            else:
                alive += 1
            if item.lista_id:
                affected_listas.add(item.lista_id)

        db.session.commit()

        for lid in affected_listas:
            lista = Lista.query.get(lid)
            if lista:
                lista.items_activos = (
                    Contenido.query.filter_by(lista_id=lid, activo=True).count()
                )
        db.session.commit()

    result = {
        'checked': len(results),
        'alive': alive,
        'dead': dead,
        'timestamp': datetime.utcnow().isoformat(),
    }
    logger.info(f'[Scan] Completado: {result}')
    return result
