import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # ── Seguridad ──────────────────────────────────────────────
    SECRET_KEY = os.environ.get('SECRET_KEY', 'cinemacity-cambia-esta-clave-en-produccion')

    # ── Base de datos ──────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        f'sqlite:///{os.path.join(BASE_DIR, "instance", "cinemacity.db")}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Admin ──────────────────────────────────────────────────
    ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin1234')

    # ── Descarga de listas M3U ─────────────────────────────────
    # Tiempo máximo TOTAL para descargar el archivo M3U (segundos).
    # Evita que servidores lentos bloqueen el import indefinidamente.
    DOWNLOAD_TIMEOUT = int(os.environ.get('DOWNLOAD_TIMEOUT', 300))

    # ── Scheduler ──────────────────────────────────────────────
    SCAN_INTERVAL_HOURS = int(os.environ.get('SCAN_INTERVAL_HOURS', 24))
    SCAN_TIMEOUT = int(os.environ.get('SCAN_TIMEOUT', 8))       # segundos por link
    SCAN_BATCH_SIZE = int(os.environ.get('SCAN_BATCH_SIZE', 100))
    # AUTO_SCAN=0 → no comprobar links automáticamente (recomendado para listas grandes)
    # AUTO_SCAN=1 → habilitar escaneo automático cada SCAN_INTERVAL_HOURS horas
    AUTO_SCAN = int(os.environ.get('AUTO_SCAN', 0))

    # ── Subida de archivos ────────────────────────────────────
    # Límite máximo de tamaño para archivos M3U subidos (50 MB)
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024

    # ── Paginación API ─────────────────────────────────────────
    ITEMS_PER_PAGE = 24

    # ── Filtros español ────────────────────────────────────────
    # Idioma explícito en tag tvg-language
    SPANISH_LANGUAGES = ['spanish', 'español', 'castellano', 'espanol', 'castella', 'spa']

    # País explícito en tag tvg-country
    SPANISH_COUNTRIES = ['es', 'esp', 'spain', 'españa', 'espana']

    # Indicadores españoles en group-title
    # ⚠️ Sin keywords genéricos como 'series', 'peliculas' que aparecen en CUALQUIER idioma
    SPANISH_GROUPS = [
        # Nombres de país/idioma explícitos
        'spain', 'españa', 'español', 'castellano', 'espana', 'espanol',
        # Códigos IPTV cortos (se aplica word-boundary en el código)
        'esp',
        # Patrones IPTV con separadores: |ES|, [ESP], ES -, etc.
        '|es|', '|esp|', '|spa|', '[es]', '[esp]',
        'es -', '- es', '- esp', 'esp -',
        'es|', '|es', 'esp|', '|esp',
        # Combinaciones explícitas con tipo de contenido
        'peliculas es', 'películas es', 'pelicula es',
        'series es', 'series esp', 'series spain',
        'movies es', 'movies esp', 'movies spain',
        'films es', 'vod es', 'vod esp',
        # Marcadores extra comunes en listas IPTV españolas
        'spain vod', 'es vod', 'esp vod',
        'en español', 'en castellano',
    ]

    # ── Filtro canales en vivo ──────────────────────────────────
    # Si group-title contiene alguna de estas palabras → se descarta como canal live
    FILTER_LIVE_CHANNELS = True
    LIVE_CHANNEL_GROUPS = [
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
        'tdt',      # Televisión Digital Terrestre
    ]

    # Rutas en la URL del stream que confirman live → excluir
    LIVE_URL_PATHS = ['/live/', '//live/']

    # Rutas en la URL del stream que confirman VOD → incluir
    VOD_URL_PATHS = [
        '/movie/', '/movies/', '/vod/', '/film/', '/films/',
        '/series/', '/serie/', '/shows/', '/show/',
    ]

    # Palabras que CONFIRMAN que es VOD (película/serie) y no live TV
    VOD_CONFIRMED_GROUPS = [
        'pelicula', 'película', 'peliculas', 'películas',
        'movie', 'movies', 'film', 'films', 'cine', 'cinema',
        'serie', 'series', 'show', 'shows', 'temporada', 'temporadas',
        'documental', 'documentales', 'documentary',
        'animacion', 'animación', 'anime', 'dorama', 'vod',
    ]
