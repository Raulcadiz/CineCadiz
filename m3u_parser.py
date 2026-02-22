"""
Parser de listas M3U/M3U8.
Extrae metadatos y aplica filtros:
  1. is_vod_content()          — solo VOD (películas/series), excluye canales en vivo
  2. is_explicitly_non_spanish()— excluye solo lo que tiene tvg-language NO español (siempre activo)
  3. is_spanish()              — filtro estricto por idioma/país (solo si el admin lo activa)
"""
import re
import hashlib
import time
from urllib.parse import urlparse

import requests


# ──────────────────────────────────────────────────────────────
# Utilidades
# ──────────────────────────────────────────────────────────────

def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode('utf-8')).hexdigest()


def _attr(line: str, name: str) -> str:
    """Extrae el valor de un atributo name="value" de una línea #EXTINF."""
    m = re.search(rf'{re.escape(name)}="([^"]*)"', line, re.IGNORECASE)
    return m.group(1).strip() if m else ''


def _normalize(text: str) -> str:
    """Minúsculas y reemplaza vocales acentuadas para comparaciones tolerantes."""
    return (text.lower()
            .replace('á','a').replace('é','e').replace('í','i')
            .replace('ó','o').replace('ú','u').replace('ü','u')
            .replace('ñ','n'))


# ──────────────────────────────────────────────────────────────
# Parser principal
# ──────────────────────────────────────────────────────────────

# Palabras en group-title que CONFIRMAN el tipo serie
_SERIE_GROUPS = [
    'serie', 'series', 'show', 'shows', 'novela', 'telenovela',
    'temporada', 'temporadas', 'dorama', 'anime', 'animacion',
    'animação', 'cartoon', 'docuseries',
]

# Palabras en group-title que CONFIRMAN el tipo pelicula
_PELICULA_GROUPS = [
    'pelicula', 'peliculas', 'peli ', 'pelis',
    'movie', 'movies', 'film', 'films', 'cine', 'cinema',
    'documental', 'documentales', 'documentary',
]


def parse_extinf(line: str) -> dict:
    """Parsea una línea #EXTINF y devuelve un dict con metadatos."""
    info = {
        'titulo': '',
        'tipo': 'pelicula',   # default
        'imagen': '',
        'idioma': '',
        'pais': '',
        'group_title': '',
        'temporada': None,
        'episodio': None,
        'año': None,
        'genero': '',
    }

    # Título: todo lo que hay después de la última coma
    comma_idx = line.rfind(',')
    if comma_idx != -1:
        info['titulo'] = line[comma_idx + 1:].strip()

    # Atributos estándar IPTV
    tvg_name = _attr(line, 'tvg-name')
    if tvg_name:
        info['titulo'] = tvg_name

    info['imagen']      = _attr(line, 'tvg-logo')
    info['idioma']      = _attr(line, 'tvg-language')
    info['pais']        = _attr(line, 'tvg-country')
    info['group_title'] = _attr(line, 'group-title')
    info['genero']      = _attr(line, 'tvg-genre')

    year_str = _attr(line, 'tvg-year')
    if year_str.isdigit():
        info['año'] = int(year_str)

    season_str = _attr(line, 'tvg-season') or _attr(line, 'season')
    ep_str     = _attr(line, 'tvg-episode') or _attr(line, 'episode')
    if season_str.isdigit():
        info['temporada'] = int(season_str)
        info['tipo'] = 'serie'
    if ep_str.isdigit():
        info['episodio'] = int(ep_str)

    # ── Extraer año del título si no viene en atributo ────────
    if not info['año']:
        m = re.search(r'\((\d{4})\)', info['titulo'])
        if m:
            info['año'] = int(m.group(1))
            info['titulo'] = re.sub(r'\s*\(\d{4}\)\s*', ' ', info['titulo']).strip()

    # ── Detectar serie por patrón S01E01 en el título ─────────
    se = re.search(r'[Ss](\d{1,2})[Ee](\d{1,3})', info['titulo'])
    if se:
        info['tipo'] = 'serie'
        if not info['temporada']:
            info['temporada'] = int(se.group(1))
        if not info['episodio']:
            info['episodio'] = int(se.group(2))

    # ── Detectar tipo por group-title ─────────────────────────
    if info['group_title']:
        gl = _normalize(info['group_title'])

        # Series tienen prioridad
        if any(kw in gl for kw in _SERIE_GROUPS):
            info['tipo'] = 'serie'
        # Películas (solo si aún no detectamos serie)
        elif any(kw in gl for kw in _PELICULA_GROUPS):
            info['tipo'] = 'pelicula'

    return info


def parse_m3u_content(content: str) -> list[dict]:
    """Parsea el texto de una lista M3U y devuelve una lista de items."""
    items   = []
    lines   = content.splitlines()
    current = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.lstrip('\ufeff') == '#EXTM3U':
            continue

        if line.upper().startswith('#EXTINF'):
            current = parse_extinf(line)

        elif current is not None and re.match(r'[a-zA-Z][a-zA-Z0-9+\-.]*://', line):
            # Acepta http://, https://, rtmp://, rtsp://, etc.
            current['url_stream'] = line
            current['url_hash']   = url_hash(line)
            try:
                current['servidor'] = urlparse(line).netloc
            except Exception:
                current['servidor'] = ''
            items.append(current)
            current = None

    return items


# ──────────────────────────────────────────────────────────────
# Filtro de idioma español
# ──────────────────────────────────────────────────────────────

_DEFAULT_LANGUAGES = ['spanish', 'español', 'castellano', 'espanol', 'castella', 'spa']
_DEFAULT_COUNTRIES = ['es', 'esp', 'spain', 'españa', 'espana']

# Indicadores claros de español en group-title.
# NO incluimos 'series', 'peliculas' etc. porque son genéricos.
_DEFAULT_GROUPS = [
    'spain', 'españa', 'español', 'castellano', 'espana', 'espanol',
    'esp',
    '|es|', '|esp|', '|spa|', '[es]', '[esp]',
    'es -', '- es', '- esp', 'esp -',
    'es|', '|es', 'esp|', '|esp',
    'peliculas es', 'películas es', 'pelicula es',
    'series es', 'series esp', 'series spain',
    'movies es', 'movies esp', 'movies spain',
    'films es', 'vod es', 'vod esp',
    'spain vod', 'es vod', 'esp vod',
    'castellano', 'en español',
]

# Palabras en group-title que CONFIRMAN VOD (para is_vod_content)
_DEFAULT_VOD_CONFIRMED = [
    'pelicula', 'película', 'peliculas', 'películas',
    'movie', 'movies', 'film', 'films', 'cine', 'cinema',
    'serie', 'series', 'show', 'shows', 'temporada',
    'documental', 'documentales', 'documentary',
    'animacion', 'animación', 'anime', 'dorama',
    'vod',
]

# Palabras en group-title que indican CANAL EN VIVO → excluir
_DEFAULT_LIVE_GROUPS = [
    'live', 'directo', 'direct', '24h', '24/7',
    'news', 'noticias',
    'sport', 'sports', 'deportes', 'deporte', 'futbol', 'fútbol',
    'radio',
    'music', 'musica', 'música',
    'adult', 'xxx', 'erotic', 'porno',
    'kids', 'infantil', 'children',
    'shopping', 'teleshopping',
    'religious', 'religion',
    'canal', 'canales', 'channel', 'channels',
    'tdt',          # Televisión Digital Terrestre (España/LatAm)
]

# Rutas en la URL que confirman live stream → excluir
_LIVE_URL_PATHS = ['/live/', '//live/']

# Rutas en la URL que confirman VOD → incluir
_VOD_URL_PATHS  = ['/movie/', '/movies/', '/vod/', '/film/', '/films/',
                   '/series/', '/serie/', '/shows/', '/show/']


def _cfg(config, key: str, default: list) -> list:
    """Lee un valor de config; funciona tanto con clase Config como dict app.config."""
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def _word_in(text: str, word: str) -> bool:
    """True si `word` existe como palabra completa en `text` (case-sensitive ya vendrá en lower)."""
    return bool(re.search(rf'(?<![a-z]){re.escape(word)}(?![a-z])', text))


def is_explicitly_non_spanish(item: dict, config) -> bool:
    """
    Filtro PASIVO — True solo si el item tiene un tag tvg-language explícito
    que no es español. Items sin tag de idioma NO se excluyen (pasan).

    Esto permite importar listas españolas que no etiquetan el idioma,
    mientras excluye items claramente marcados como English, French, etc.
    """
    lang = (item.get('idioma') or '').lower().strip()
    if not lang:
        return False   # sin etiqueta → no excluir
    for kw in _cfg(config, 'SPANISH_LANGUAGES', _DEFAULT_LANGUAGES):
        if kw in lang:
            return False   # es español → no excluir
    return True   # tiene idioma explícito y no es español → excluir


def is_spanish(item: dict, config) -> bool:
    """
    Filtro ESTRICTO — True si el item es claramente en español.
    Primero busca tag de idioma/país explícito, luego el group-title.
    """
    lang    = _normalize(item.get('idioma')      or '')
    country = _normalize(item.get('pais')        or '')
    group   = _normalize(item.get('group_title') or '')

    # 1. Tag tvg-language explícito
    for kw in _cfg(config, 'SPANISH_LANGUAGES', _DEFAULT_LANGUAGES):
        if kw in lang:
            return True

    # 2. Tag tvg-country explícito
    for kw in _cfg(config, 'SPANISH_COUNTRIES', _DEFAULT_COUNTRIES):
        if kw == country or country.startswith(kw) or country.endswith(kw):
            return True

    # 3. group-title con indicadores específicos de español
    for kw in _cfg(config, 'SPANISH_GROUPS', _DEFAULT_GROUPS):
        kw_n = _normalize(kw)
        if len(kw_n) <= 3:
            if _word_in(group, kw_n):   # word-boundary para códigos cortos
                return True
        else:
            if kw_n in group:
                return True

    return False


# ──────────────────────────────────────────────────────────────
# Filtro de canales en vivo
# ──────────────────────────────────────────────────────────────

def is_vod_content(item: dict, config) -> bool:
    """
    True si el item parece VOD (película/serie), no un canal en directo.

    Lógica (por orden de prioridad):
      1. URL contiene /live/ → False (live stream definitivo)
      2. group-title contiene palabras de live TV → False
      3. URL contiene /movie/, /series/, /vod/ → True (VOD definitivo)
      4. group-title contiene palabras VOD confirmadas → True
      5. Título con año (2024) o patrón S01E01 → True
      6. Sin group-title → True (listas simples, no descartar)
      7. group-title existe pero no encaja → False (canal sin clasificar)
    """
    if not _cfg(config, 'FILTER_LIVE_CHANNELS', True):
        return True

    group  = _normalize(item.get('group_title') or '')
    titulo = item.get('titulo') or ''
    url    = (item.get('url_stream') or '').lower()

    # ── 1. URL confirma live stream → excluir ─────────────────
    live_url_paths = _cfg(config, 'LIVE_URL_PATHS', _LIVE_URL_PATHS)
    if any(p in url for p in live_url_paths):
        return False

    # ── 2. Exclusión: live TV por group-title ──────────────────
    live_kws = _cfg(config, 'LIVE_CHANNEL_GROUPS', _DEFAULT_LIVE_GROUPS)
    for kw in live_kws:
        if _normalize(kw) in group:   # normalizar kw igual que group
            return False

    # ── 3. URL confirma VOD → incluir ─────────────────────────
    vod_url_paths = _cfg(config, 'VOD_URL_PATHS', _VOD_URL_PATHS)
    if any(p in url for p in vod_url_paths):
        return True

    # ── 4. Inclusión: VOD confirmado por group-title ───────────
    vod_kws = _cfg(config, 'VOD_CONFIRMED_GROUPS', _DEFAULT_VOD_CONFIRMED)
    for kw in vod_kws:
        if _normalize(kw) in group:
            return True

    # ── 5. Inclusión: título con año o patrón S/E ──────────────
    if re.search(r'\(\d{4}\)', titulo):
        return True
    if re.search(r'[Ss]\d{1,2}[Ee]\d{1,3}', titulo):
        return True
    if item.get('temporada') or item.get('episodio'):
        return True

    # ── 6. Sin group-title → incluir (listas simples) ─────────
    if not group:
        return True

    # ── 7. group-title existe pero no encaja → excluir ─────────
    return False


# ──────────────────────────────────────────────────────────────
# Descarga y parseo completo
# ──────────────────────────────────────────────────────────────

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}


def fetch_and_parse(url: str, config, filter_spanish: bool = False) -> tuple[list, str | None]:
    """
    Descarga una lista M3U con TIMEOUT TOTAL, la parsea y aplica filtros:

      1. Siempre: excluye canales en vivo (FILTER_LIVE_CHANNELS)
      2. Siempre: excluye ítems con tvg-language explícito NO español
      3. Si filter_spanish=True: aplica filtro estricto de español

    Timeout total configurable (DOWNLOAD_TIMEOUT segundos, default 90).
    Usa streaming para detectar si el servidor es muy lento y abortar.

    Devuelve (items, error_msg). Si error_msg es None, fue exitoso.
    """
    max_secs = _cfg(config, 'DOWNLOAD_TIMEOUT', 90)

    try:
        start = time.monotonic()
        resp = requests.get(
            url,
            timeout=(10, 30),   # (connect_timeout, read_per_chunk_timeout)
            headers=HEADERS,
            stream=True,
        )
        resp.raise_for_status()

        # Leer en chunks con límite de tiempo total
        chunks: list[bytes] = []
        for chunk in resp.iter_content(chunk_size=131_072):  # 128 KB por chunk
            if chunk:
                chunks.append(chunk)
            elapsed = time.monotonic() - start
            if elapsed > max_secs:
                resp.close()
                return [], (
                    f'Timeout total: la lista tardó más de {max_secs}s en descargarse. '
                    f'El servidor es demasiado lento o el archivo es demasiado grande.'
                )
        raw_bytes = b''.join(chunks)

    except requests.exceptions.Timeout:
        return [], 'Timeout de conexión: el servidor no respondió en 10s'
    except requests.exceptions.ConnectionError as e:
        return [], f'Error de conexión: {e}'
    except requests.exceptions.HTTPError as e:
        return [], f'Error HTTP {e.response.status_code}'
    except Exception as e:
        return [], str(e)

    # Decodificar con fallback de encoding (utf-8-sig primero para BOM)
    content = None
    for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'iso-8859-1', 'windows-1252'):
        try:
            content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        content = raw_bytes.decode('utf-8', errors='replace')

    all_items = parse_m3u_content(content)
    total = len(all_items)

    # Filtro 1: excluir canales en vivo
    items = [it for it in all_items if is_vod_content(it, config)]

    # Filtro 2: excluir ítems EXPLICITAMENTE marcados como no español
    #           (nunca bloquea ítems sin etiqueta de idioma)
    items = [it for it in items if not is_explicitly_non_spanish(it, config)]

    # Filtro 3: solo español estricto (si el admin lo activó)
    if filter_spanish:
        items = [it for it in items if is_spanish(it, config)]

    return items, None
