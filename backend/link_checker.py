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

# User-Agent de VLC — los servidores IPTV reconocen y sirven a VLC;
# bloquean o rechazan peticiones de navegadores convencionales.
_VLC_UA = 'VLC/3.0.20 LibVLC/3.0.20'

_HEADERS_VLC = {
    'User-Agent': _VLC_UA,
    'Range': 'bytes=0-1023',
    'Icy-MetaData': '0',
}

# User-Agent de navegador como fallback (algunos servidores web normales
# solo sirven a navegadores y rechazan VLC)
_HEADERS_BROWSER = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Range': 'bytes=0-1023',
}


def check_url(url: str, timeout: int = 5) -> bool:
    """
    True si la URL responde con código HTTP < 400.

    Estrategia para streams IPTV:
      1. GET parcial (Range) con UA de VLC — lo que usa el reproductor real.
         HEAD se omite porque muchos servidores IPTV devuelven 405 a HEAD y
         gastaríamos tiempo antes del fallback.
      2. Si falla (timeout o error de red), intento rápido con UA de navegador
         por si el servidor bloquea VLC pero admite navegadores.

    El timeout se aplica a la conexión+primera respuesta (connect + read),
    no a la descarga completa — el Range header limita a 1 KB.
    """
    # Aumentamos el read-timeout ligeramente respecto al connect-timeout
    # porque los servidores IPTV tardan más en empezar a emitir que en conectar.
    connect_t = min(timeout, 8)
    read_t    = max(timeout, 12)   # mínimo 12s de read aunque el scan_timeout sea 5

    for headers in (_HEADERS_VLC, _HEADERS_BROWSER):
        try:
            r = requests.get(
                url,
                headers=headers,
                stream=True,
                allow_redirects=True,
                timeout=(connect_t, read_t),
            )
            r.close()
            if r.status_code < 400:
                return True
            # 405 = HEAD/método no permitido, 401/403 = auth requerida →
            # el stream existe pero requiere credenciales → lo consideramos vivo.
            if r.status_code in (401, 403, 405):
                return True
        except requests.exceptions.Timeout:
            # Timeout de red ≠ stream caído; puede ser servidor IPTV lento.
            # Solo marcamos como caído si AMBOS intentos fallan por timeout.
            continue
        except Exception:
            continue

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


def purge_dead_links(app, days: int = 7) -> dict:
    """
    Elimina permanentemente de la BD el contenido M3U que lleva más de `days` días
    marcado como inactivo (activo=False) y ya fue verificado al menos una vez.

    Solo elimina fuente='m3u' para no borrar items RSS que no pasan por el scanner.
    """
    from models import db, Contenido
    from sqlalchemy import and_

    cutoff = datetime.utcnow() - __import__('datetime').timedelta(days=days)

    with app.app_context():
        to_delete = (
            Contenido.query
            .filter(
                and_(
                    Contenido.activo == False,
                    Contenido.fuente == 'm3u',
                    Contenido.ultima_verificacion.isnot(None),
                    Contenido.ultima_verificacion < cutoff,
                )
            )
            .all()
        )
        count = len(to_delete)
        for item in to_delete:
            db.session.delete(item)
        db.session.commit()

    result = {
        'deleted': count,
        'days': days,
        'timestamp': datetime.utcnow().isoformat(),
    }
    logger.info(f'[Purge] Eliminados {count} items inactivos (>{days}d): {result}')
    return result


def server_health(app) -> list:
    """
    Devuelve estadísticas de salud por servidor (dominio base de url_stream).
    Útil para detectar qué proveedores tienen la mayoría de streams caídos.
    """
    from models import db, Contenido
    from sqlalchemy import func, case
    import urllib.parse

    with app.app_context():
        rows = (
            db.session.query(Contenido.servidor, Contenido.activo,
                             func.count(Contenido.id).label('cnt'))
            .filter(Contenido.fuente == 'm3u', Contenido.servidor.isnot(None))
            .group_by(Contenido.servidor, Contenido.activo)
            .all()
        )

    # Agrupar por servidor
    servers: dict = {}
    for servidor, activo, cnt in rows:
        key = servidor or 'desconocido'
        if key not in servers:
            servers[key] = {'servidor': key, 'alive': 0, 'dead': 0}
        if activo:
            servers[key]['alive'] += cnt
        else:
            servers[key]['dead'] += cnt

    result = []
    for s in servers.values():
        total = s['alive'] + s['dead']
        s['total'] = total
        s['dead_pct'] = round(s['dead'] / total * 100, 1) if total else 0
        result.append(s)

    result.sort(key=lambda x: x['dead_pct'], reverse=True)
    return result
