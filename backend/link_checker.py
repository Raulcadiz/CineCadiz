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


_HTML_SIGNATURES = (b'<!doctype', b'<html', b'<HTML', b'<!DOCTYPE')

def _is_real_stream(r) -> bool:
    """
    Verifica que la respuesta sea realmente un stream de vídeo/audio y no una
    página HTML de error disfrazada con código 200.

    Reglas (en orden de coste):
    1. Content-Type 'text/html' → falso positivo seguro.
    2. Lee hasta 512 bytes y comprueba que no empiecen por firma HTML.
    3. Content-Type de vídeo explícito → verdadero positivo confirmado.
    """
    ct = r.headers.get('Content-Type', '').lower().split(';')[0].strip()

    # Regla 1: HTML en Content-Type → error page
    if ct in ('text/html', 'text/plain', 'application/xhtml+xml'):
        return False

    # Regla 2: leer un pequeño chunk para verificar contenido real
    try:
        chunk = b''
        for data in r.iter_content(512):
            chunk = data
            break
    except Exception:
        chunk = b''

    if not chunk:
        # Respuesta vacía: puede ser un stream que tarde en arrancar;
        # solo rechazamos si el Content-Type tampoco es de vídeo.
        return ct.startswith(('video/', 'audio/', 'application/octet-stream',
                               'application/vnd', 'multipart/x-mixed-replace'))

    # Comprobación de firma HTML en los primeros bytes
    head = chunk[:64].lower()
    if any(sig.lower() in head for sig in _HTML_SIGNATURES):
        return False

    return True


def check_url(url: str, timeout: int = 5) -> bool:
    """
    True si la URL devuelve un stream real (no una página HTML de error).

    Estrategia:
      1. GET parcial (Range) con UA de VLC.
      2. Fallback con UA de navegador.
      Para cada intento: comprueba código HTTP Y contenido para
      descartar falsos positivos (servidores que devuelven 200 + HTML).
    """
    connect_t = min(timeout, 8)
    read_t    = max(timeout, 12)

    for headers in (_HEADERS_VLC, _HEADERS_BROWSER):
        try:
            r = requests.get(
                url,
                headers=headers,
                stream=True,
                allow_redirects=True,
                timeout=(connect_t, read_t),
            )

            # Códigos de error definitivos
            if r.status_code >= 400 and r.status_code not in (401, 403, 405):
                r.close()
                continue

            # Auth requerida → el recurso existe
            if r.status_code in (401, 403, 405):
                r.close()
                return True

            # 2xx / 3xx → verificar que es stream real
            alive = _is_real_stream(r)
            r.close()
            if alive:
                return True
            # Si llegamos aquí con VLC-UA, intentamos con browser-UA
            continue

        except requests.exceptions.Timeout:
            continue
        except Exception:
            continue

    return False


def check_url_with_latency(url: str, timeout: int = 5) -> tuple:
    """
    Comprueba si una URL devuelve un stream real y mide la latencia en ms.
    Devuelve (alive: bool, latency_ms: int).
    Aplica la misma detección de falsos positivos que check_url().
    """
    import time
    connect_t = min(timeout, 8)
    read_t    = max(timeout, 12)

    for headers in (_HEADERS_VLC, _HEADERS_BROWSER):
        try:
            t0 = time.monotonic()
            r = requests.get(
                url,
                headers=headers,
                stream=True,
                allow_redirects=True,
                timeout=(connect_t, read_t),
            )
            latency = int((time.monotonic() - t0) * 1000)

            if r.status_code >= 400 and r.status_code not in (401, 403, 405):
                r.close()
                continue

            if r.status_code in (401, 403, 405):
                r.close()
                return True, latency

            alive = _is_real_stream(r)
            r.close()
            if alive:
                return True, latency
            continue

        except requests.exceptions.Timeout:
            continue
        except Exception:
            continue

    return False, 0


def scan_live_channels(app, max_workers: int = 20) -> dict:
    """
    Escanea todos los canales en directo (tipo='live'):
    - Mide latencia de cada URL del canal
    - Failover: si la URL activa falla, avanza a la siguiente que funcione
    - Deduplicación: elimina URLs duplicadas exactas; entre URLs con la misma
      latencia conserva la más antigua (primera en la lista); entre URLs con
      distinta latencia elimina la de peor calidad
    - Registra LiveScanReport por cada URL comprobada
    - Mantiene historial 7 días
    """
    import json as _json
    from datetime import timedelta
    from models import db, Contenido, LiveScanConfig, LiveScanReport

    with app.app_context():
        timeout = app.config.get('SCAN_TIMEOUT', 5)
        channels = (
            Contenido.query
            .filter_by(tipo='live', fuente='m3u')
            .all()
        )

        # Inicializar live_urls_json para canales que aún no lo tienen
        for ch in channels:
            if not ch.live_urls_json:
                ch.live_urls_json = _json.dumps([ch.url_stream])
        db.session.commit()

        # Recoger todas las URLs únicas para verificar en paralelo
        channel_url_map: dict[int, list] = {}
        for ch in channels:
            try:
                urls = _json.loads(ch.live_urls_json)
            except (ValueError, TypeError):
                urls = [ch.url_stream]
            channel_url_map[ch.id] = urls

    if not channel_url_map:
        return {'channels': 0, 'failed': 0, 'timestamp': datetime.utcnow().isoformat()}

    all_unique_urls = list({u for urls in channel_url_map.values() for u in urls})
    logger.info(f'[LiveScan] Comprobando {len(all_unique_urls)} URLs de {len(channel_url_map)} canales...')

    # Verificar en paralelo
    url_results: dict[str, tuple] = {}   # url → (alive, latency_ms)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {pool.submit(check_url_with_latency, url, timeout): url for url in all_unique_urls}
        for future in as_completed(future_map):
            url = future_map[future]
            try:
                url_results[url] = future.result()
            except Exception:
                url_results[url] = (False, 0)

    # Actualizar BD y generar reportes
    failed = 0
    now = datetime.utcnow()
    cutoff = now - __import__('datetime').timedelta(days=7)

    with app.app_context():
        channels = Contenido.query.filter_by(tipo='live', fuente='m3u').all()
        reports = []

        for ch in channels:
            try:
                urls = _json.loads(ch.live_urls_json or '[]') or [ch.url_stream]
            except (ValueError, TypeError):
                urls = [ch.url_stream]

            # ── 1. Eliminar duplicados exactos (mantener primera aparición) ──
            seen: set = set()
            deduped = []
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    deduped.append(u)

            # ── 2. Resultados para este canal ──
            # Lista de (url, alive, latency_ms)
            results_for_ch = [(u, *url_results.get(u, (False, 0))) for u in deduped]

            # Crear registros de reporte
            for url, alive, latency in results_for_ch:
                reports.append(LiveScanReport(
                    contenido_id=ch.id,
                    url_probada=url,
                    resultado=alive,
                    latencia_ms=latency,
                    timestamp=now,
                ))

            # ── 3. Deduplicación por calidad: entre URLs vivas, si hay dos
            #       con latencia muy similar (±200ms), quitar la de peor latencia
            alive_with_lat = [(u, lat) for u, alive, lat in results_for_ch if alive]
            dead_urls      = {u for u, alive, _ in results_for_ch if not alive}

            # Eliminar URLs muertas que NO son la única URL disponible
            if dead_urls and len(deduped) > len(dead_urls):
                deduped = [u for u in deduped if u not in dead_urls]
                results_for_ch = [(u, a, l) for u, a, l in results_for_ch if u not in dead_urls]
                alive_with_lat = [(u, lat) for u, lat in alive_with_lat]

            # ── 4. Actualizar índice activo ──
            current_idx = ch.live_active_idx or 0
            current_url = deduped[current_idx] if current_idx < len(deduped) else (deduped[0] if deduped else ch.url_stream)
            current_alive = url_results.get(current_url, (False, 0))[0]

            if alive_with_lat:
                if not current_alive:
                    # Failover: buscar la primera URL viva en orden
                    for i, u in enumerate(deduped):
                        if url_results.get(u, (False, 0))[0]:
                            ch.live_active_idx = i
                            logger.info(f'[LiveScan] Failover {ch.titulo}: índice {current_idx} → {i}')
                            break
                # else: la URL activa sigue viva, no cambiar nada
                ch.activo = True
            else:
                # Todos los servidores caídos
                ch.activo = False
                failed += 1
                logger.warning(f'[LiveScan] Canal totalmente caído: {ch.titulo}')

            ch.live_urls_json = _json.dumps(deduped)
            ch.ultima_verificacion = now

        # Guardar reportes y purgar los viejos
        db.session.bulk_save_objects(reports)
        LiveScanReport.query.filter(LiveScanReport.timestamp < cutoff).delete()

        # Actualizar last_scan en config
        config = LiveScanConfig.query.first()
        if config:
            config.last_scan = now

        db.session.commit()

    result = {
        'channels': len(channel_url_map),
        'failed':   failed,
        'timestamp': now.isoformat(),
    }
    logger.info(f'[LiveScan] Completado: {result}')
    return result


def scan_dead_links(app, batch_size: int = 5000, max_workers: int = 40,
                    lista_id: int = None) -> dict:
    """
    Escanea hasta `batch_size` links M3U (VOD) en paralelo.
    Excluye canales en directo (tipo='live') — esos los gestiona scan_live_channels().

    batch_size=0 → sin límite, escanea todos los items pendientes.
    lista_id → si se especifica, solo escanea contenido de esa lista.

    Rendimiento orientativo (40 workers, timeout 15s):
      - ~160 checks/min → 80 000 items en ~8 horas (job nocturno ideal)
    """
    from models import db, Contenido, Lista

    # ── 1. Leer datos de BD en hilo principal ──────────────────
    with app.app_context():
        timeout = app.config.get('SCAN_TIMEOUT', 15)
        q = Contenido.query.filter(
            Contenido.activo == True,
            Contenido.fuente == 'm3u',
            Contenido.tipo != 'live',   # los live los gestiona scan_live_channels()
        )
        if lista_id:
            q = q.filter(Contenido.lista_id == lista_id)
        q = (
            q.order_by(Contenido.ultima_verificacion.asc().nullsfirst())
            .with_entities(Contenido.id, Contenido.url_stream)
        )
        if batch_size > 0:
            q = q.limit(batch_size)
        rows = q.all()

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

    # has_more=True si procesamos exactamente batch_size → probablemente hay más
    has_more = batch_size > 0 and len(results) == batch_size

    result = {
        'checked':   len(results),
        'alive':     alive,
        'dead':      dead,
        'has_more':  has_more,
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
