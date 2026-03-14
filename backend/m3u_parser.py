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
    'animados',   # "CLÁSICOS ANIMADOS", "ANIMADOS HD", etc.
    'clasicos',   # "CLÁSICOS" con episodios numerados
]

# Palabras en group-title que CONFIRMAN el tipo pelicula
_PELICULA_GROUPS = [
    'pelicula', 'peliculas', 'peli ', 'pelis',
    'movie', 'movies', 'film', 'films', 'cine', 'cinema',
    'documental', 'documentales', 'documentary',
    'estrenos', 'estreno',   # "ESTRENOS 2021", "ESTRENO", etc.
    'novedades', 'novedad',  # "NOVEDADES 2025"
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
    # Acepta: S01E01, S01.E01, S01-E01, S01 E01 (punto/guion/espacio como separador)
    se = re.search(r'[Ss](\d{1,2})\s*[._-]?\s*[Ee](\d{1,3})', info['titulo'])
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


def parse_m3u_content(content: str, grupos_set: set | None = None) -> list[dict]:
    """
    Parsea el texto de una lista M3U y devuelve una lista de items.

    grupos_set: si se indica, se aplica un pre-filtro rápido por group-title
    ANTES de ejecutar parse_extinf (que es costoso). Esto evita parsear entradas
    que luego se descartarían, reduciendo drásticamente el tiempo en archivos grandes.
    """
    items   = []
    lines   = content.splitlines()
    current = None

    # Regex compilada una vez para el pre-filtro de group-title
    _gt_re = re.compile(r'group-title="([^"]*)"', re.IGNORECASE)

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.lstrip('\ufeff') == '#EXTM3U':
            continue

        if line.upper().startswith('#EXTINF'):
            # Pre-filtro rápido: si hay grupos seleccionados, verificar group-title
            # antes de llamar a parse_extinf (ahorra 8+ regex + SHA256 por entrada)
            if grupos_set is not None:
                m = _gt_re.search(line)
                grp = m.group(1).strip() if m else ''
                if grp not in grupos_set:
                    current = None
                    continue
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

# "es" es el código ISO 639-1 oficial pero requiere match exacto/subtag
# porque "es" aparece como subcadena en "portuguese", "chinese", etc.
_DEFAULT_LANGUAGES = ['es', 'spa', 'spanish', 'español', 'castellano', 'espanol', 'castella']
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
    'animados',              # "CLÁSICOS ANIMADOS"
    'clasicos',              # "CLÁSICOS" (colecciones antiguas con episodios)
    'estrenos', 'estreno',   # "ESTRENOS 2021"
    'novedades', 'novedad',  # "NOVEDADES 2025"
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


def _lang_is_spanish(lang: str, config) -> bool:
    """
    True si el tag tvg-language (ya en minúsculas) corresponde a español.

    Para códigos cortos (≤ 3 chars, ej. "es", "spa") usa match exacto o subtag
    ("es-es", "es-mx", "es_419") para evitar falsos positivos en "portuguese",
    "chinese", etc. que contienen "es" como subcadena.
    Para códigos largos ("spanish", "español"...) usa substring normal.
    """
    for kw in _cfg(config, 'SPANISH_LANGUAGES', _DEFAULT_LANGUAGES):
        kw = kw.lower()
        if len(kw) <= 3:
            if lang == kw or lang.startswith(kw + '-') or lang.startswith(kw + '_'):
                return True
        else:
            if kw in lang:
                return True
    return False


def _word_in(text: str, word: str) -> bool:
    """True si `word` existe como palabra completa en `text` (case-sensitive ya vendrá en lower)."""
    return bool(re.search(rf'(?<![a-z]){re.escape(word)}(?![a-z])', text))


def is_explicitly_non_spanish(item: dict, config) -> bool:
    """
    Filtro PASIVO — True solo si el item tiene un tag tvg-language explícito
    que no es español. Items sin tag de idioma NO se excluyen (pasan).

    Esto permite importar listas españolas que no etiquetan el idioma,
    mientras excluye items claramente marcados como English, French, etc.
    Usa _lang_is_spanish() para evitar falsos positivos con "es" en "portuguese".
    """
    lang = (item.get('idioma') or '').lower().strip()
    if not lang:
        return False   # sin etiqueta → no excluir
    if _lang_is_spanish(lang, config):
        return False   # es español → no excluir
    return True   # tiene idioma explícito y no es español → excluir


def is_spanish(item: dict, config) -> bool:
    """
    Filtro ESTRICTO — True si el item es claramente en español.
    Primero busca tag de idioma/país explícito, luego el group-title.
    """
    lang_raw = (item.get('idioma') or '').lower().strip()
    lang     = _normalize(lang_raw)
    country  = _normalize(item.get('pais')        or '')
    group    = _normalize(item.get('group_title') or '')

    # 1. Tag tvg-language explícito (usa helper con match exacto para códigos cortos)
    if lang_raw and _lang_is_spanish(lang_raw, config):
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

    # 4. Sin etiqueta de idioma ni país → asumir español.
    #    Muchas listas IPTV en español no incluyen tvg-language ni tvg-country;
    #    sería incorrecto descartarlas con el filtro "Solo español".
    if not lang and not country:
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
    # Acepta: S01E01, S01.E01, S01-E01, S01 E01
    if re.search(r'[Ss]\d{1,2}\s*[._-]?\s*[Ee]\d{1,3}', titulo):
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

def parse_and_filter(
    content: str,
    config,
    filter_spanish: bool = False,
    include_live: bool = False,
    grupos: set | None = None,
    tipos_override: dict | None = None,   # {group_title: 'pelicula'|'serie'|'live'}
) -> list:
    """
    Parsea un string M3U ya decodificado y aplica los filtros de idioma/live.
    Útil cuando el contenido ya está disponible localmente (archivo subido por el admin).

    grupos: si se indica, solo se incluyen items cuyo group_title esté en ese conjunto.
            Los items de grupos live se incluyen automáticamente si su grupo fue seleccionado.
            Si es None, se usa el comportamiento clásico (include_live flag).
    tipos_override: mapa {group_title: tipo} con la clasificación manual del admin.
            Cuando está definido, su clasificación tiene prioridad sobre is_vod_content().
    """
    # Pasar grupos al parser para el pre-filtro rápido por group-title
    all_items = parse_m3u_content(content, grupos_set=grupos)

    vod_items, live_items = [], []
    for it in all_items:
        g = it.get('group_title') or '(sin grupo)'

        # Filtro por grupos seleccionados
        if grupos is not None:
            if g not in grupos:
                continue

        # Usar tipos_override si el admin asignó un tipo manualmente a este grupo
        if tipos_override and g in tipos_override:
            it['tipo'] = tipos_override[g]
            if it['tipo'] == 'live':
                live_items.append(it)
            else:
                vod_items.append(it)
        elif is_vod_content(it, config):
            vod_items.append(it)
        else:
            it['tipo'] = 'live'
            live_items.append(it)

    # Con grupos seleccionados: incluir todo lo que pasó el filtro de grupo
    # Sin grupos: usar la flag include_live clásica
    if grupos is not None:
        items = vod_items + live_items
    else:
        items = vod_items + (live_items if include_live else [])

    items = [it for it in items if not is_explicitly_non_spanish(it, config)]
    if filter_spanish:
        items = [it for it in items if is_spanish(it, config)]
    return items


# ──────────────────────────────────────────────────────────────
# Previsualización de grupos
# ──────────────────────────────────────────────────────────────

def get_groups_preview(content: str) -> list[dict]:
    """
    Parsea el contenido M3U y devuelve los grupos únicos con tipo detectado y conteo.
    No aplica ningún filtro de idioma ni de live/VOD — muestra TODO para que el usuario elija.
    """
    all_items = parse_m3u_content(content)
    groups: dict[str, dict] = {}

    for item in all_items:
        g = item.get('group_title') or '(sin grupo)'
        gl = _normalize(g)

        # Clasificar el grupo por su nombre: live tiene prioridad
        if any(kw in gl for kw in _DEFAULT_LIVE_GROUPS):
            tipo = 'live'
        elif any(kw in gl for kw in _SERIE_GROUPS):
            tipo = 'serie'
        elif any(kw in gl for kw in _PELICULA_GROUPS):
            tipo = 'pelicula'
        else:
            tipo = item.get('tipo', 'pelicula')   # fallback a lo que detectó parse_extinf

        if g not in groups:
            groups[g] = {'name': g, 'tipo': tipo, 'count': 0}
        groups[g]['count'] += 1

    return sorted(groups.values(), key=lambda x: (-x['count'], x['name']))


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


def _download_m3u(
    url: str,
    config,
    proxy: str | None = None,
) -> tuple[bytes | None, str | None]:
    """Descarga una lista M3U con timeout total. Devuelve (raw_bytes, error_msg)."""
    max_secs = _cfg(config, 'DOWNLOAD_TIMEOUT', 300)
    req_proxies = {
        'http':  f'http://{proxy}',
        'https': f'http://{proxy}',
    } if proxy else {}

    try:
        start = time.monotonic()
        resp = requests.get(
            url,
            timeout=(10, 30),
            headers=HEADERS,
            stream=True,
            proxies=req_proxies,
        )
        resp.raise_for_status()

        chunks: list[bytes] = []
        for chunk in resp.iter_content(chunk_size=131_072):
            if chunk:
                chunks.append(chunk)
            if time.monotonic() - start > max_secs:
                resp.close()
                return None, (
                    f'Timeout total: la lista tardó más de {max_secs}s en descargarse. '
                    f'El servidor es demasiado lento o el archivo es demasiado grande.'
                )
        return b''.join(chunks), None

    except requests.exceptions.Timeout:
        return None, 'Timeout de conexión: el servidor no respondió en 10s'
    except requests.exceptions.ConnectionError as e:
        return None, f'Error de conexión: {e}'
    except requests.exceptions.HTTPError as e:
        return None, f'Error HTTP {e.response.status_code}'
    except Exception as e:
        return None, str(e)


def decode_m3u_bytes(raw_bytes: bytes) -> str:
    """Decodifica bytes M3U con fallback de encoding (utf-8-sig primero para BOM)."""
    for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'iso-8859-1', 'windows-1252'):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode('utf-8', errors='replace')


def fetch_and_parse(
    url: str,
    config,
    filter_spanish: bool = False,
    include_live: bool = False,
    proxy: str | None = None,
    grupos: set | None = None,
    tipos_override: dict | None = None,   # {group_title: 'pelicula'|'serie'|'live'}
) -> tuple[list, str | None]:
    """
    Descarga una lista M3U con TIMEOUT TOTAL, la parsea y aplica filtros:

      1. Siempre: clasifica canales en vivo (tipo='live')
         - Si grupos es None e include_live=False → excluye canales en vivo
         - Si grupos es None e include_live=True  → los incluye con tipo='live'
         - Si grupos está definido → incluye todo lo que tenga grupo seleccionado
      2. Siempre: excluye ítems con tvg-language explícito NO español
      3. Si filter_spanish=True: aplica filtro estricto de español

    proxy: "host:port" (sin esquema) del proxy HTTP a usar, o None para directo.
    grupos: conjunto de nombres de group-title a incluir, o None para no filtrar por grupo.
    tipos_override: mapa {group_title: tipo} con la clasificación manual del admin.
    Devuelve (items, error_msg). Si error_msg es None, fue exitoso.
    """
    raw_bytes, error = _download_m3u(url, config, proxy)
    if error:
        return [], error

    content = decode_m3u_bytes(raw_bytes)
    return parse_and_filter(content, config, filter_spanish, include_live, grupos, tipos_override), None


def fetch_groups_preview(
    url: str,
    config,
    proxy: str | None = None,
) -> tuple[list, str | None]:
    """
    Descarga la M3U en streaming y devuelve los grupos únicos para previsualización.
    No necesita bufferar el archivo completo: extrae solo los group-title de líneas
    #EXTINF y para cuando lleva GRACE_ITEMS ítems consecutivos sin grupos nuevos
    (early-stop) o alcanza MAX_ITEMS.
    Devuelve (groups, error_msg).
    """
    MAX_ITEMS   = 150_000  # hard cap — soporta M3U de hasta ~150k entradas
    GRACE_ITEMS = 30_000   # ítems consecutivos sin grupo NUEVO antes de parar
    max_secs    = _cfg(config, 'DOWNLOAD_TIMEOUT', 300)
    req_proxies = {
        'http':  f'http://{proxy}',
        'https': f'http://{proxy}',
    } if proxy else {}

    try:
        start = time.monotonic()
        resp  = requests.get(
            url, timeout=(10, 30), headers=HEADERS,
            stream=True, proxies=req_proxies,
        )
        resp.raise_for_status()

        groups: dict[str, dict] = {}
        buf        = b''
        items_seen = 0
        since_new  = 0
        stop       = False

        for chunk in resp.iter_content(chunk_size=65_536):
            if not chunk:
                continue
            if time.monotonic() - start > max_secs:
                break
            buf += chunk
            while b'\n' in buf:
                raw_line, buf = buf.split(b'\n', 1)
                line = raw_line.decode('utf-8', errors='replace').strip()
                if not line or line.lstrip('\ufeff') == '#EXTM3U':
                    continue
                if not line.upper().startswith('#EXTINF'):
                    continue

                g_name = _attr(line, 'group-title') or '(sin grupo)'
                gl     = _normalize(g_name)
                if any(kw in gl for kw in _DEFAULT_LIVE_GROUPS):
                    tipo = 'live'
                elif any(kw in gl for kw in _SERIE_GROUPS):
                    tipo = 'serie'
                elif any(kw in gl for kw in _PELICULA_GROUPS):
                    tipo = 'pelicula'
                else:
                    tipo = 'otro'

                is_new = g_name not in groups
                if is_new:
                    groups[g_name] = {'name': g_name, 'tipo': tipo, 'count': 0}
                    since_new = 0
                else:
                    since_new += 1
                groups[g_name]['count'] += 1
                items_seen += 1

                if items_seen >= MAX_ITEMS or (since_new >= GRACE_ITEMS and groups):
                    stop = True
                    break
            if stop:
                break

        try:
            resp.close()
        except Exception:
            pass

        return sorted(groups.values(), key=lambda x: (-x['count'], x['name'])), None

    except requests.exceptions.Timeout:
        return [], 'Timeout de conexión: el servidor no respondió en 10s'
    except requests.exceptions.ConnectionError as e:
        return [], f'Error de conexión: {e}'
    except requests.exceptions.HTTPError as e:
        return [], f'Error HTTP {e.response.status_code}'
    except Exception as e:
        return [], str(e)
