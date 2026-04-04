// ╔══════════════════════════════════════════════════════════╗
// ║  CineCadiz — Frontend JS                                ║
// ║  Consume la API Flask en /api/                          ║
// ╚══════════════════════════════════════════════════════════╝

// Placeholder SVG inline — nunca genera 404
const PLACEHOLDER = '/static/images/placeholder.svg';

// ── Sesión anónima para recomendaciones ────────────────────
function _getSessionKey() {
    let key = localStorage.getItem('cc_session_key');
    if (!key) {
        key = 'cc_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 9);
        localStorage.setItem('cc_session_key', key);
    }
    return key;
}
const SESSION_KEY = _getSessionKey();

// ── Estado global ──────────────────────────────────────────
const state = {
    currentPage: 1,
    currentType: '',
    currentYear: '',
    currentGenre: '',
    currentSort: 'year_desc',
    currentListaId: '',     // lista activa en la vista En Directo
    favorites: JSON.parse(localStorage.getItem('cc_favorites') || '[]'),
    allItems: [],           // caché local para búsqueda rápida
    liveGroups: [],         // caché de grupos de canales en directo
};

// ── Elementos DOM ──────────────────────────────────────────
const el = {
    preloader:         document.getElementById('preloader'),
    heroSlider:        document.getElementById('heroSlider'),
    novedades:         document.getElementById('novedades'),
    peliculasCarousel: document.getElementById('peliculasCarousel'),
    seriesCarousel:    document.getElementById('seriesCarousel'),
    liveCarousel:      document.getElementById('liveCarousel'),
    moviesGrid:        document.getElementById('moviesGrid'),
    loadMore:          document.getElementById('loadMore'),
    searchInput:       document.getElementById('searchInput'),
    searchBtn:         document.getElementById('searchBtn'),
    searchResults:     document.getElementById('searchResults'),
    typeFilter:        document.getElementById('typeFilter'),
    yearFilter:        document.getElementById('yearFilter'),
    genreFilter:       document.getElementById('genreFilter'),
    gridTitle:         document.getElementById('gridTitle'),
    detailsModal:      document.getElementById('detailsModal'),
    modalBody:         document.getElementById('modalBody'),
    player:            document.getElementById('player'),
    videoPlayer:       document.getElementById('videoPlayer'),
};

// ── API Service ────────────────────────────────────────────
const api = {
    async get(endpoint, params = {}) {
        const query = new URLSearchParams(
            Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v != null))
        ).toString();
        const url = `/api/${endpoint}${query ? '?' + query : ''}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },

    trending: () => api.get('trending', { limit: 20 }),
    peliculas: (page = 1) => api.get('contenido', { tipo: 'pelicula', page, limit: 20 }),
    series:    (page = 1) => api.get('series-agrupadas', { page, limit: 20 }),
    live:      (page = 1) => api.get('contenido', { tipo: 'live',     page, limit: 20 }),
    generos:   ()         => api.get('generos'),
    años:      ()         => api.get('anos'),   // endpoint sin tilde
    stats:     ()         => api.get('stats'),

    search: (q) => api.get('contenido', { q, limit: 8 }),

    contenido: (params) => api.get('contenido', params),
    seriesAgrupadas: (params) => api.get('series-agrupadas', params),
    serieEpisodios: (titulo) => api.get('serie-episodios', { titulo }),

    item: (id) => api.get(`contenido/${id}`),

    liveAgrupados: (params = {}) => api.get('live-agrupados', params),
    liveCategorias: (params = {}) => api.get('live-categorias', params),
    liveListas: ()                => api.get('live-listas'),

    watch: (contenidoId) => fetch('/api/watch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_key: SESSION_KEY, contenido_id: contenidoId }),
    }).catch(() => {}),   // never block playback on network errors

    recomendaciones: (contextId = null) => {
        const params = { session_key: SESSION_KEY, limit: 20 };
        if (contextId) params.context_id = contextId;
        return api.get('recomendaciones', params);
    },
};

// ── Proxy de imágenes RSS (bypass hotlinking/VPN) ──────────
/**
 * Devuelve la URL de imagen correcta:
 *  - RSS con imagen: usa /api/proxy-image para evitar bloqueos de cinemacity.cc
 *  - RSS sin imagen: usa /api/og-image para extraer og:image de la página
 *  - M3U: usa la URL directa (CDN externo sin restricciones)
 */
function getImageUrl(item) {
    if (item.source === 'rss') {
        if (item.image) {
            return `/api/proxy-image?url=${encodeURIComponent(item.image)}`;
        }
        // Sin imagen en el feed → intentar og:image de la página
        if (item.streamUrl) {
            return `/api/og-image?url=${encodeURIComponent(item.streamUrl)}`;
        }
    }
    return item.image || PLACEHOLDER;
}

// ── Render helpers ─────────────────────────────────────────
function isFav(id) {
    return state.favorites.includes(String(id));
}

function renderCard(item) {
    // Series agrupadas → tarjeta especial con selector de episodios
    if (item.episodeCount !== undefined) {
        return renderSeriesCard(item);
    }

    const fav = isFav(item.id);
    const typeIcon = item.type === 'movie' ? '🎬' : item.type === 'live' ? '📡' : '📺';
    const epBadge = item.season
        ? `<span class="badge-ep">S${String(item.season).padStart(2,'0')}E${String(item.episode||0).padStart(2,'0')}</span>`
        : '';

    const isRss  = item.source === 'rss';
    const isLive = item.type  === 'live';
    const playLabel = isRss
        ? '<i class="bi bi-box-arrow-up-right"></i> Abrir'
        : '<i class="bi bi-play-fill"></i> Ver';

    const imgSrc = getImageUrl(item);

    // Data attribute para failover en canales live con múltiples URLs
    const liveUrlsAttr = (isLive && item.liveUrls && item.liveUrls.length > 1)
        ? ` data-live-urls="${encodeURIComponent(JSON.stringify(item.liveUrls))}"`
        : '';
    const drmKeyIdAttr = item.drmKeyId || '';
    const drmKeyAttr = item.drmKey || '';
    const drmTypeAttr = item.drmLicenseType || '';

    return `
    <div class="movie-card" data-id="${item.id}" data-type="${item.type || 'movie'}">
        <div class="card-img-wrap">
            <img src="${imgSrc}"
                 alt="${item.title}"
                 loading="lazy"
                 onerror="this.src='${PLACEHOLDER}'">
            ${isLive ? '<span class="live-badge">🔴 LIVE</span>' : ''}
            ${isRss  ? '<span class="rss-badge">WEB</span>'      : ''}
            ${drmTypeAttr === 'clearkey' ? '<span class="drm-badge">🔐 DRM</span>' : ''}
        </div>
        <div class="movie-info">
            <h3 class="movie-title">${item.title}</h3>
            <div class="movie-meta">
                <span>${item.year || ''}</span>
                <span>${typeIcon} ${epBadge}</span>
            </div>
        </div>
        <div class="movie-overlay">
            <button class="btn-watch"
                    data-stream="${encodeURIComponent(item.streamUrl)}"
                    data-source="${item.source || 'm3u'}"
                    data-title="${item.title}"
                    data-id="${item.id}"
                    data-image="${encodeURIComponent(imgSrc)}"${liveUrlsAttr}
                    data-drm-key-id="${drmKeyIdAttr}"
                    data-drm-key="${drmKeyAttr}"
                    data-drm-type="${drmTypeAttr}">
                ${playLabel}
            </button>
            <button class="btn-favorite ${fav ? 'active' : ''}" data-fav="${item.id}">
                <i class="bi ${fav ? 'bi-heart-fill' : 'bi-heart'}"></i>
            </button>
            <p class="movie-genres">${(item.genres || []).slice(0,2).join(', ') || 'Sin género'}</p>
        </div>
    </div>`;
}

/** Tarjeta para series agrupadas (muestra temporadas + episodios). */
function renderSeriesCard(series) {
    const fav = isFav(series.id);
    const imgSrc = series.image || PLACEHOLDER;
    const seasons = series.seasonCount || 1;
    const eps     = series.episodeCount || 0;
    const badge   = seasons > 1
        ? `${seasons} Temp. · ${eps} Ep.`
        : `${eps} Episodio${eps !== 1 ? 's' : ''}`;

    const encodedTitle = encodeURIComponent(series.title);

    return `
    <div class="movie-card series-card"
         data-id="${series.id}"
         data-series-title="${encodedTitle}">
        <div class="card-img-wrap">
            <img src="${imgSrc}"
                 alt="${series.title}"
                 loading="lazy"
                 onerror="this.src='${PLACEHOLDER}'">
            <span class="series-ep-badge">📺 ${badge}</span>
        </div>
        <div class="movie-info">
            <h3 class="movie-title">${series.title}</h3>
            <div class="movie-meta">
                <span>${series.year || ''}</span>
                <span>📺 Serie</span>
            </div>
        </div>
        <div class="movie-overlay">
            <button class="btn-watch btn-series-open"
                    data-series-title="${encodedTitle}">
                <i class="bi bi-collection-play"></i> Ver episodios
            </button>
            <button class="btn-favorite ${fav ? 'active' : ''}" data-fav="${series.id}">
                <i class="bi ${fav ? 'bi-heart-fill' : 'bi-heart'}"></i>
            </button>
            <p class="movie-genres">${(series.genres || []).slice(0,2).join(', ') || 'Serie'}</p>
        </div>
    </div>`;
}

/** Tarjeta para un grupo de canales en directo (DAZN HD + DAZN FHD → una tarjeta). */
function renderLiveGroupCard(group, idx) {
    const img   = group.image || PLACEHOLDER;
    const count = group.channelCount || 1;
    const encTitle = encodeURIComponent(group.title || '');
    return `
    <div class="movie-card live-group-card" data-type="live" data-group-idx="${idx}" data-group-title="${encTitle}">
        <div class="card-img-wrap">
            <img src="${img}" alt="${group.title}" loading="lazy"
                 onerror="this.src='${PLACEHOLDER}'">
            <span class="live-badge">🔴 LIVE</span>
            ${count > 1 ? `<span class="live-variants-badge">📡 ${count}</span>` : ''}
        </div>
        <div class="movie-info">
            <h3 class="movie-title">${group.title}</h3>
            <div class="movie-meta">
                <span>📡 Directo</span>
            </div>
        </div>
        <div class="movie-overlay">
            <button class="btn-watch btn-live-group-open" data-group-idx="${idx}" data-group-title="${encTitle}">
                <i class="bi bi-${count > 1 ? 'collection-play' : 'play-fill'}"></i>
                ${count > 1 ? 'Ver canales' : 'Ver'}
            </button>
        </div>
    </div>`;
}

/** Abre el modal de grupo de canales (variantes de calidad de un canal). */
function showLiveGroupDetail(group) {
    const modal = document.getElementById('liveGroupModal');
    const body  = document.getElementById('liveGroupModalBody');
    if (!modal || !body) return;

    const channels = group.channels || [];
    if (!channels.length) return;

    modal.style.display = 'flex';
    const heroImg  = group.image || PLACEHOLDER;
    const baseTitle = group.title || '';

    // Etiqueta de calidad: eliminar el nombre base del título del canal
    function qualityLabel(ch) {
        const chTitle = ch.title || ch.titulo || '';
        if (!chTitle) return '—';
        if (!baseTitle) return chTitle;
        const suffix = chTitle.replace(
            new RegExp('^' + baseTitle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'), ''
        ).trim();
        return suffix || chTitle;
    }

    try {
        body.innerHTML = `
        <div class="series-hero" style="background-image:url('${heroImg}')">
            <div class="series-hero-content">
                <img class="series-hero-poster" src="${heroImg}" alt="${baseTitle}"
                     onerror="this.style.display='none'">
                <div class="series-hero-info">
                    <h2>${baseTitle}</h2>
                    <div class="series-stats">
                        <span class="stat-pill">📡 En Directo</span>
                        ${channels.length > 1 ? `<span class="stat-pill">${channels.length} calidades</span>` : ''}
                    </div>
                </div>
            </div>
        </div>
        <div class="live-channels-list">
            ${channels.map(ch => {
                const streamUrl  = ch.streamUrl || ch.url_stream || '';
                const encStream  = encodeURIComponent(streamUrl);
                const encImg     = encodeURIComponent(ch.image || group.image || PLACEHOLDER);
                const qlabel     = qualityLabel(ch);
                const chTitle    = ch.title || ch.titulo || baseTitle;
                // data-live-urls para failover automático si el canal tiene backups
                const chLiveUrls = ch.liveUrls && ch.liveUrls.length > 1
                    ? ` data-live-urls="${encodeURIComponent(JSON.stringify(ch.liveUrls))}"`
                    : '';
                const chDrmKeyId = ch.drmKeyId || '';
                const chDrmKey = ch.drmKey || '';
                const chDrmType = ch.drmLicenseType || '';
                return `
                <div class="live-channel-row"
                     data-stream="${encStream}"
                     data-source="${ch.source || ch.fuente || 'm3u'}"
                     data-title="${chTitle}"
                     data-id="${ch.id || ''}"
                     data-image="${encImg}"${chLiveUrls}
                     data-drm-key-id="${chDrmKeyId}"
                     data-drm-key="${chDrmKey}"
                     data-drm-type="${chDrmType}">
                    <i class="bi bi-play-circle-fill live-row-icon"></i>
                    <span class="live-row-label">${qlabel}</span>
                    <span class="live-row-play">▶ Reproducir</span>
                </div>`;
            }).join('')}
        </div>`;
    } catch (err) {
        console.error('showLiveGroupDetail error:', err);
        body.innerHTML = '<p class="no-content">Error al cargar los canales</p>';
    }

    body.querySelectorAll('.live-channel-row').forEach(row => {
        row.addEventListener('click', e => {
            e.stopPropagation();
            modal.style.display = 'none';
            let rowLiveUrls = null;
            if (row.dataset.liveUrls) {
                try { rowLiveUrls = JSON.parse(decodeURIComponent(row.dataset.liveUrls)); } catch (_) {}
            }
            const drmKeyId = row.dataset.drmKeyId || '';
            const drmKey = row.dataset.drmKey || '';
            const drmType = row.dataset.drmType || '';
            playStream(row.dataset.stream, row.dataset.title,
                       row.dataset.source || 'm3u', row.dataset.id, row.dataset.image, rowLiveUrls,
                       drmKeyId, drmKey, drmType);
        });
    });
}

/** Tarjeta de episodio dentro del modal de serie. */
function renderEpisodeCard(ep) {
    const imgSrc   = getImageUrl(ep);
    const epLabel  = (ep.season && ep.episode)
        ? `S${String(ep.season).padStart(2,'0')}E${String(ep.episode).padStart(2,'0')}`
        : '';
    const encStream = encodeURIComponent(ep.streamUrl);
    const encImg    = encodeURIComponent(imgSrc);

    return `
    <div class="episode-card"
         data-stream="${encStream}"
         data-source="${ep.source || 'm3u'}"
         data-title="${ep.title}"
         data-id="${ep.id}"
         data-image="${encImg}">
        <div class="ep-thumb-wrap">
            <img src="${imgSrc}" alt="${ep.title}" loading="lazy" onerror="this.src='${PLACEHOLDER}'">
            <div class="ep-play-overlay"><i class="bi bi-play-circle-fill"></i></div>
            ${epLabel ? `<span class="ep-badge">${epLabel}</span>` : ''}
        </div>
        <div class="ep-info">
            <p class="ep-title">${ep.title}</p>
            ${epLabel ? `<p class="ep-num-label">${epLabel}</p>` : ''}
        </div>
    </div>`;
}

function renderCarousel(items, container) {
    if (!container) return;
    if (!items || !items.length) {
        container.innerHTML = '<p class="no-content">Sin contenido disponible</p>';
        return;
    }
    container.innerHTML = items.map(renderCard).join('');
}

function renderGrid(items, append = false) {
    if (!append) el.moviesGrid.innerHTML = '';
    if (!items || !items.length) {
        if (!append) el.moviesGrid.innerHTML = '<p class="no-content">No se encontraron resultados</p>';
        return;
    }
    el.moviesGrid.insertAdjacentHTML('beforeend', items.map(renderCard).join(''));
}

function renderHero(items) {
    if (!items || !items.length) return;
    const item = items[Math.floor(Math.random() * Math.min(items.length, 5))];
    const heroImg = getImageUrl(item);
    el.heroSlider.innerHTML = `
        <div class="slide active">
            <img src="${heroImg}" alt="${item.title}"
                 style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;"
                 onerror="this.style.display='none'">
            <div class="hero-content">
                <h1 class="hero-title">${item.title}</h1>
                <p class="hero-description">${item.year || ''} &bull; ${(item.genres||[]).slice(0,2).join(', ')}</p>
                <div class="hero-buttons">
                    <button class="btn-play" data-stream="${encodeURIComponent(item.streamUrl)}"
                            data-source="${item.source || 'm3u'}"
                            data-title="${item.title}"
                            data-id="${item.id}"
                            data-image="${encodeURIComponent(heroImg)}">
                        <i class="bi bi-play-fill"></i> Reproducir
                    </button>
                    <button class="btn-info" data-id="${item.id}">
                        <i class="bi bi-info-circle"></i> Más info
                    </button>
                </div>
            </div>
        </div>`;
}

// ── Modal detalles ─────────────────────────────────────────
async function showDetails(id) {
    try {
        const item = await api.item(id);
        const fav = isFav(item.id);
        const modalImg = getImageUrl(item);
        el.modalBody.innerHTML = `
            <div class="modal-details">
                <div class="modal-poster">
                    <img src="${modalImg}"
                         alt="${item.title}"
                         onerror="this.src='${PLACEHOLDER}'">
                </div>
                <div class="modal-info">
                    <h2>${item.title} ${item.year ? '(' + item.year + ')' : ''}</h2>
                    <div class="modal-meta">
                        <span class="type">${item.type === 'movie' ? '🎬 Película' : item.type === 'live' ? '📡 En Directo' : '📺 Serie'}</span>
                        ${item.season ? `<span>S${String(item.season).padStart(2,'0')}E${String(item.episode||0).padStart(2,'0')}</span>` : ''}
                    </div>
                    <div class="modal-genres">
                        ${(item.genres||[]).map(g => `<span class="genre-tag">${g}</span>`).join('')}
                    </div>
                    ${item.groupTitle ? `<p class="text-secondary small">Grupo: ${item.groupTitle}</p>` : ''}
                    <div class="modal-actions">
                        <button class="btn-play"
                                data-stream="${encodeURIComponent(item.streamUrl)}"
                                data-source="${item.source || 'm3u'}"
                                data-title="${item.title}"
                                data-id="${item.id}"
                                data-image="${encodeURIComponent(modalImg)}"
                                ${item.type === 'live' && item.liveUrls && item.liveUrls.length > 1
                                    ? `data-live-urls="${encodeURIComponent(JSON.stringify(item.liveUrls))}"`
                                    : ''}>
                            ${item.source === 'rss'
                                ? '<i class="bi bi-box-arrow-up-right"></i> Abrir en web'
                                : '<i class="bi bi-play-fill"></i> Reproducir'}
                        </button>
                        <a class="btn-trailer"
                           href="https://www.youtube.com/results?search_query=${encodeURIComponent((item.title || '') + (item.year ? ' ' + item.year : '') + ' trailer')}"
                           target="_blank" rel="noopener noreferrer"
                           title="Buscar trailer en YouTube">
                            <i class="bi bi-youtube"></i> Trailer
                        </a>
                        <button class="btn-favorite ${fav ? 'active' : ''}" data-fav="${item.id}">
                            <i class="bi ${fav ? 'bi-heart-fill' : 'bi-heart'}"></i>
                            ${fav ? 'En favoritos' : 'Agregar'}
                        </button>
                    </div>
                </div>
            </div>`;
        el.detailsModal.style.display = 'flex';
    } catch {
        showNotification('Error al cargar los detalles', 'error');
    }
}

// ── Modal de serie: temporadas y episodios ──────────────────
async function showSeriesDetail(baseTitle) {
    const modal = document.getElementById('seriesModal');
    const body  = document.getElementById('seriesModalBody');
    if (!modal || !body) return;

    modal.style.display = 'flex';
    body.innerHTML = '<p class="no-content" style="padding:2rem">Cargando episodios…</p>';

    try {
        const episodes = await api.serieEpisodios(baseTitle);
        if (!episodes.length) {
            body.innerHTML = '<p class="no-content" style="padding:2rem">No se encontraron episodios.</p>';
            return;
        }

        // Agrupar por temporada
        const seasons = {};
        episodes.forEach(ep => {
            const s = ep.season || 1;
            if (!seasons[s]) seasons[s] = [];
            seasons[s].push(ep);
        });
        const seasonKeys = Object.keys(seasons).map(Number).sort((a, b) => a - b);

        // Datos para el hero (primer episodio con imagen)
        const heroEp   = episodes.find(e => e.image) || episodes[0];
        const heroImg  = heroEp.image ? getImageUrl(heroEp) : PLACEHOLDER;
        const totalEps = episodes.length;
        const genreHtml = (heroEp.genres || [])
            .map(g => `<span class="genre-tag">${g}</span>`).join('');

        body.innerHTML = `
        <div class="series-hero"
             style="background-image:url('${heroImg}')">
            <div class="series-hero-content">
                <img class="series-hero-poster"
                     src="${heroImg}"
                     alt="${baseTitle}"
                     onerror="this.style.display='none'">
                <div class="series-hero-info">
                    <h2>${baseTitle}</h2>
                    <div class="series-stats">
                        ${heroEp.year ? `<span>${heroEp.year}</span>` : ''}
                        <span class="stat-pill">${seasonKeys.length} Temp.</span>
                        <span class="stat-pill">${totalEps} Episodios</span>
                    </div>
                    <div class="modal-genres">${genreHtml}</div>
                </div>
            </div>
        </div>

        <div class="season-tabs-bar">
            ${seasonKeys.map((s, i) => `
                <button class="season-tab ${i === 0 ? 'active' : ''}"
                        data-season="${s}">
                    Temporada ${s}
                </button>
            `).join('')}
        </div>

        ${seasonKeys.map((s, i) => `
            <div class="season-panel ${i === 0 ? 'active' : ''}"
                 data-season="${s}">
                <div class="episodes-grid">
                    ${seasons[s].map(renderEpisodeCard).join('')}
                </div>
            </div>
        `).join('')}`;

        // Cambio de temporada
        body.querySelectorAll('.season-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                body.querySelectorAll('.season-tab').forEach(t => t.classList.remove('active'));
                body.querySelectorAll('.season-panel').forEach(p => p.classList.remove('active'));
                tab.classList.add('active');
                body.querySelector(`.season-panel[data-season="${tab.dataset.season}"]`)
                    ?.classList.add('active');
            });
        });

        // Reproducir episodio al hacer click en la tarjeta
        body.querySelectorAll('.episode-card').forEach(card => {
            card.addEventListener('click', () => {
                modal.style.display = 'none';
                playStream(
                    card.dataset.stream,
                    card.dataset.title,
                    card.dataset.source || 'm3u',
                    card.dataset.id,
                    card.dataset.image,
                    null, '', '', ''
                );
            });
        });

    } catch (err) {
        console.error('showSeriesDetail error:', err);
        body.innerHTML = '<p class="no-content" style="padding:2rem">Error al cargar los episodios.</p>';
    }
}

// ── Reproductor ────────────────────────────────────────────
let _hls = null;                  // instancia HLS.js activa
let _failoverUrls = [];           // URLs de respaldo para el stream live actual
let _failoverIdx  = 0;            // índice actual en la cadena de failover
let _isCurrentStreamLive = false; // true cuando LEVEL_LOADED confirma stream live
let _stallTimer = null;           // watchdog: congela live → failover/reconnect

// Detecta Android WebView (workers con limitaciones en versiones antiguas)
const _isWebView = /wv/.test(navigator.userAgent) ||
    (/Android/.test(navigator.userAgent) && /Version\/\d/.test(navigator.userAgent));

/**
 * Config HLS.js optimizada para live/IPTV.
 * Segura también para VOD: liveDurationInfinity solo activa en playlists live;
 * liveBackBufferLength solo aplica cuando la playlist es live.
 *
 * Cambios clave vs versión anterior:
 *  - liveSyncDuration: 3s explícitos (más fiable que count-based en IPTV irregular)
 *  - liveMaxLatencyDuration: 10s → si el player se atrasa más, resync al edge
 *  - liveBackBufferLength: 4 → buffer trasero mínimo para absorber microcortes
 *  - highBufferWatchdogPeriod: 2 → HLS.js detecta stalls cada 2s (default=5s)
 *  - nudgeMaxRetry: 10 → más intentos de nudge antes de rendirse
 *  - fragLoadingMaxRetry: 3 → falla rápido en live (antes: 6 → 15s de pantalla helada)
 *  - fragLoadingMaxRetryTimeout: 6000 → timeout de fragmento más corto
 */
function _buildHlsConfig() {
    return {
        enableWorker:                   !_isWebView,
        // ── Live ──────────────────────────────────────────────────────────────
        liveDurationInfinity:           true,
        // 8s de buffer trasero: absorbe microcortes de 5-7s sin congelar imagen.
        // El valor anterior (4s) era demasiado pequeño para redes IPTV inestables.
        liveBackBufferLength:           8,
        // Sincronizar 5s por detrás del edge: equilibrio entre latencia y estabilidad.
        // Con 3s se producen resync constantes en servidores con segments de 4-6s.
        liveSyncDuration:               5,
        // Reconectar si el player se atrasa más de 15s del edge.
        liveMaxLatencyDuration:         15,
        // Arrancar en el nivel de calidad más bajo para el primer chunk live →
        // evita el buffering inicial mientras se negocia la calidad adecuada.
        startLevel:                     -1,
        // ── Watchdog y stalls ─────────────────────────────────────────────────
        highBufferWatchdogPeriod:       2,
        nudgeMaxRetry:                  10,
        nudgeOffset:                    0.2,
        // ── Buffer general ────────────────────────────────────────────────────
        maxBufferLength:                30,
        maxMaxBufferLength:             60,
        maxBufferSize:                  40 * 1000 * 1000,
        // ── Reintentos de carga ───────────────────────────────────────────────
        manifestLoadingMaxRetry:        10,
        manifestLoadingRetryDelay:      500,
        manifestLoadingMaxRetryTimeout: 32000,
        // 3 reintentos de fragmento → falla rápido en live antes de congelar pantalla
        fragLoadingMaxRetry:            3,
        fragLoadingRetryDelay:          500,
        fragLoadingMaxRetryTimeout:     6000,
        levelLoadingMaxRetry:           4,
        levelLoadingRetryDelay:         500,
        levelLoadingMaxRetryTimeout:    8000,
        xhrSetup: xhr => { xhr.withCredentials = false; },
    };
}

/**
 * Manejadores del watchdog de congelación para streams live.
 * Se registran con addEventListener (named → se pueden eliminar con removeEventListener).
 * _onVideoWaitingLive: arma un temporizador; si el vídeo sigue "esperando" tras 12s
 *   intenta saltar al live edge antes de lanzar error/failover.
 * _onVideoPlayingLive: cancela el temporizador cuando el vídeo vuelve a reproducirse.
 */
function _onVideoWaitingLive() {
    if (!_isCurrentStreamLive) return;
    clearTimeout(_stallTimer);
    _stallTimer = setTimeout(() => {
        if (!_isCurrentStreamLive) return;
        console.warn('[player] live stall watchdog — video congelado >12s');
        // Intentar saltar al live edge antes de reconectar
        if (_hls) {
            const edge = _hls.liveSyncPosition;
            if (edge && edge > 0 && Math.abs(el.videoPlayer.currentTime - edge) > 3) {
                console.warn('[player] saltando al live edge:', edge.toFixed(2));
                el.videoPlayer.currentTime = edge;
                el.videoPlayer.play().catch(() => {});
                return;   // dar otra oportunidad antes de failover
            }
        }
        _showPlayerError('Stream en directo interrumpido');
    }, 12000);
}
function _onVideoPlayingLive() {
    clearTimeout(_stallTimer);
}

/** Muestra badge "🔴 EN VIVO" junto al título del reproductor (solo una vez). */
function _showLiveIndicator() {
    const titleEl = document.getElementById('playerTitle');
    if (!titleEl || titleEl.querySelector('.cc-live-badge')) return;
    const badge = document.createElement('span');
    badge.className = 'cc-live-badge';
    badge.textContent = '🔴 EN VIVO';
    badge.style.cssText = 'margin-left:.5rem;font-size:.68rem;font-weight:700;' +
        'color:#e53;letter-spacing:.05em;vertical-align:middle;' +
        'background:rgba(229,51,51,.15);padding:.1rem .35rem;border-radius:3px;';
    titleEl.appendChild(badge);
}

/**
 * Intenta el siguiente servidor de respaldo cuando el stream actual falla.
 * Muestra un toast no intrusivo y vuelve a cargar sin mostrar pantalla de error.
 * Devuelve true si hay backup disponible (carga iniciada), false si se agotaron las opciones.
 */
function _tryFailover() {
    if (!_failoverUrls.length || _failoverIdx >= _failoverUrls.length - 1) return false;
    _failoverIdx++;
    const nextUrl = _normalizeStreamUrl(_failoverUrls[_failoverIdx]);
    showNotification('Cambiando a servidor de respaldo…');
    _destroyHls();
    _setPlayerLoading(true);
    setTimeout(() => {
        el.player.dataset.streamUrl = nextUrl;
        if (_isLikelyDash(nextUrl)) {
            _loadDashDirect(nextUrl);
        } else if (_isLikelyHls(nextUrl)) {
            _loadHlsDirect(nextUrl);
        } else {
            _tryNative(nextUrl);
        }
    }, 1000);
    return true;
}

/** Muestra/oculta el spinner de carga dentro del reproductor. */
function _setPlayerLoading(on) {
    el.player?.querySelectorAll('.player-loading').forEach(e => e.remove());
    if (on) {
        const div = document.createElement('div');
        div.className = 'player-loading';
        div.innerHTML = '<div class="spinner"></div><span>Cargando stream…</span>';
        el.player?.querySelector('.player-body')?.appendChild(div);
    }
}

/**
 * Destruye la instancia HLS y mpegts (si existen) y cancela descargas activas.
 * También cancela el watchdog de congelación live.
 */
function _destroyHls() {
    // Limpiar watchdog de congelación live
    clearTimeout(_stallTimer);
    _stallTimer = null;
    _isCurrentStreamLive = false;
    el.videoPlayer.removeEventListener('waiting', _onVideoWaitingLive);
    el.videoPlayer.removeEventListener('playing', _onVideoPlayingLive);

    if (window._mpegtsPlayer) {
        try { window._mpegtsPlayer.destroy(); } catch (_) {}
        window._mpegtsPlayer = null;
    }
    if (_hls) {
        _hls.destroy();
        _hls = null;
    }
    if (window._dashPlayer) {
        try { window._dashPlayer.reset(); } catch (_) {}
        window._dashPlayer = null;
    }
    if (window._shakaPlayer) {
        try { window._shakaPlayer.destroy(); } catch (_) {}
        window._shakaPlayer = null;
    }
    el.videoPlayer.pause();
    el.videoPlayer.removeAttribute('src');
    el.videoPlayer.load();   // cancela la descarga HTTP en curso
    el.videoPlayer.onerror = null;
    el.player?.querySelectorAll('.player-error').forEach(e => e.remove());
    // Limpiar badge "EN VIVO" al destruir el reproductor
    document.getElementById('playerTitle')?.querySelector('.cc-live-badge')?.remove();
    _setPlayerLoading(false);
}

/** Muestra overlay de error dentro del reproductor con mensaje amigable + botón Reportar. */
function _showPlayerError(msg, errCode) {
    // Antes de mostrar el error, intentar el siguiente servidor de respaldo
    if (_tryFailover()) return;

    const code = errCode ?? el.videoPlayer?.error?.code;
    const codeNames = {1:'ABORTED',2:'NETWORK',3:'DECODE',4:'SRC_NOT_SUPPORTED'};
    if (code) console.error('[player] error', code, codeNames[code] || '?', '|', msg);
    else console.error('[player] error (no code) |', msg);
    el.player?.querySelectorAll('.player-error').forEach(e => e.remove());
    const itemId   = el.player?.dataset.itemId   || '';
    const streamUrl = el.player?.dataset.streamUrl || '';
    const errDiv = document.createElement('div');
    errDiv.className = 'player-error';
    errDiv.innerHTML = `
        <div style="font-size:2.5rem;margin-bottom:.7rem">📺</div>
        <p style="margin:.3rem 0;font-size:1.1rem;font-weight:600">Este canal no va, prueba otro canal</p>
        <p style="color:#999;font-size:.82rem;margin-top:.4rem;margin-bottom:1.4rem">
          ${code === 4
            ? 'El codec del stream (probablemente H.265/HEVC) no está soportado en Chrome.<br>Prueba con <strong>Edge</strong>, <strong>Safari</strong> o abre en la app.'
            : code === 2
            ? 'El servidor IPTV puede estar bloqueando las peticiones desde el proxy.<br>Pulsa <strong>Ver en pestaña</strong> para reproducirlo directamente desde tu navegador.'
            : 'El stream puede estar caído o no ser compatible con el navegador.'}
        </p>
        <div style="display:flex;gap:.6rem;flex-wrap:wrap;justify-content:center">
            <button class="err-btn" data-action="close-player">
                ← Volver al listado
            </button>
            ${streamUrl && streamUrl.startsWith('http://') ? `
            <button class="err-btn" data-action="open-tab">
                📺 Ver en pestaña
            </button>` : ''}
            ${itemId ? `
            <button class="err-btn" data-action="open-app" data-id="${itemId}">
                📲 Abrir en app
            </button>
            <button class="err-btn err-btn-copy" data-action="copy">
                📋 Copiar enlace
            </button>
            <button class="err-btn err-btn-report" data-action="report" data-id="${itemId}">
                🚩 Reportar
            </button>` : ''}
        </div>
        <div class="err-report-thanks" style="display:none;margin-top:1rem;color:#4caf50;font-size:.85rem">
            ✓ Reporte enviado, lo revisaremos pronto
        </div>`;

    errDiv.querySelectorAll('[data-action]').forEach(btn => {
        btn.addEventListener('click', e => {
            e.stopPropagation();
            const action = btn.dataset.action;
            if (action === 'close-player') {
                document.querySelector('.btn-close-player')?.click();
            } else if (action === 'open-tab') {
                const title = document.getElementById('playerTitle')?.textContent || '';
                const liveUrlsParam = _failoverUrls.length > 1
                    ? '&live_urls=' + encodeURIComponent(JSON.stringify(_failoverUrls))
                    : '';
                window.open(
                    `http://${location.hostname}/player?url=${encodeURIComponent(streamUrl)}&title=${encodeURIComponent(title)}${liveUrlsParam}`,
                    '_blank', 'noopener,noreferrer'
                );
            } else if (action === 'open-app') {
                // Descarga el .m3u del ítem — el SO lo abre en VLC / MX Player / etc.
                const id = btn.dataset.id;
                const a = document.createElement('a');
                a.href = `/api/playlist/${id}.m3u`;
                a.download = `stream_${id}.m3u`;
                a.click();
            } else if (action === 'copy') {
                const urlToCopy = streamUrl || '';
                if (!urlToCopy) return;
                navigator.clipboard?.writeText(urlToCopy)
                    .then(() => {
                        btn.textContent = '✓ Copiado';
                        setTimeout(() => { btn.innerHTML = '📋 Copiar enlace'; }, 2000);
                    })
                    .catch(() => {
                        // Fallback para navegadores sin clipboard API
                        prompt('Copia este enlace:', urlToCopy);
                    });
            } else if (action === 'report') {
                const id = btn.dataset.id;
                btn.disabled = true;
                fetch(`/api/reportar/${id}`, { method: 'POST' })
                    .then(r => r.json())
                    .then(() => {
                        errDiv.querySelector('.err-report-thanks').style.display = 'block';
                        btn.style.display = 'none';
                    })
                    .catch(() => showNotification('No se pudo enviar el reporte', 'error'));
            }
        });
    });

    el.player?.querySelector('.player-body')?.appendChild(errDiv);
}

/**
 * Extrae la URL real de un parámetro de proxy (/api/hls-proxy?url=... o stream-proxy?url=...).
 * Devuelve la URL original, o null si la URL no es una URL de proxy.
 */
function _getUrlFromProxy(proxyUrl) {
    try {
        const u = new URL(proxyUrl, location.origin);
        if (u.pathname.includes('-proxy')) {
            const orig = u.searchParams.get('url');
            return orig ? decodeURIComponent(orig) : null;
        }
    } catch (_) {}
    return null;
}

/**
 * Carga un stream HLS con HLS.js.
 *
 * @param {string}  url       URL a cargar (proxy o directa).
 * @param {boolean} isDirect  true = intento directo (sin proxy). Evita reintentar vía proxy
 *                            en la cadena de fallback y pasa a mpegts si falla.
 *
 * Cadena de fallback cuando el proxy falla (502/403):
 *   1. _loadHls(proxy_url)        → falla 502  → extrae URL original
 *   2. _loadHls(original_url, true) → falla CORS/net → _tryDirectMpegts(streamUrl)
 *   3. _tryDirectMpegts           → mpegts.js directo (sin proxy) → falla → error+botón
 */
function _loadHls(url, isDirect = false) {
    // Para el proxy (isDirect=false): timeout corto — el proxy es same-origin y responde rápido
    // si funciona. Si tarda más de 8s, el servidor IPTV está bloqueando o caído → fallar rápido.
    // Para acceso directo (isDirect=true): hasta 2 reintentos con timeout normal.
    const extraCfg = isDirect
        ? { manifestLoadingMaxRetry: 2 }
        : { manifestLoadingMaxRetry: 0, manifestLoadingTimeOut: 8000 };

    _hls = new Hls({ ..._buildHlsConfig(), ...extraCfg });
    _hls.loadSource(url);
    _hls.attachMedia(el.videoPlayer);
    _hls.on(Hls.Events.MANIFEST_PARSED, () => {
        el.videoPlayer.play().catch(() => {});
    });
    _hls.on(Hls.Events.LEVEL_LOADED, (_, data) => {
        if (data.details && data.details.live) {
            _isCurrentStreamLive = true;
            _showLiveIndicator();
            _hls.config.liveDurationInfinity = true;
        } else {
            // VOD confirmado: ampliar buffer para scrubbing suave
            _hls.config.maxBufferLength    = 60;
            _hls.config.maxMaxBufferLength = 120;
            _hls.config.maxBufferSize      = 120 * 1000 * 1000;
        }
    });
    _hls.on(Hls.Events.ERROR, (_e, data) => {
        if (!data.fatal) {
            // Buffer stall en stream live: intentar saltar al live edge
            if (_isCurrentStreamLive && _hls && (
                data.details === Hls.ErrorDetails.BUFFER_STALLED_ERROR ||
                data.details === Hls.ErrorDetails.BUFFER_NUDGE_ON_STALL
            )) {
                const edge = _hls.liveSyncPosition;
                if (edge && edge > 0) {
                    console.warn('[hls] buffer stall — saltando al live edge:', edge.toFixed(2));
                    el.videoPlayer.currentTime = edge;
                    el.videoPlayer.play().catch(() => {});
                }
            }
            return;
        }

        // ── Error fatal ────────────────────────────────────────────────
        const httpCode = data.response?.code;
        console.warn('[hls] fatal', data.details, 'httpCode:', httpCode, 'isDirect:', isDirect);
        _destroyHls();

        if (!isDirect) {
            const origUrl = _getUrlFromProxy(url);
            if (origUrl) {
                // HTTPS page + HTTP stream → el navegador bloquea peticiones directas (mixed content).
                // No tiene sentido intentar acceso directo ni mpegts: fallarán instantáneamente.
                // Ir directamente a mostrar el error con el botón "Ver en pestaña nueva".
                if (location.protocol === 'https:' && origUrl.startsWith('http://')) {
                    console.warn('[hls] HTTPS + HTTP stream — mixed content, no se puede reproducir en iframe');
                    _setPlayerLoading(false);
                    _showPlayerError('Este canal usa HTTP y la página es HTTPS.\nUsa el botón "Ver en pestaña nueva" para reproducirlo.');
                    return;
                }
                // HTTP o HTTPS stream → intentar acceso directo desde el navegador
                console.warn('[hls] proxy falló — intentando acceso directo:', origUrl);
                _loadHls(origUrl, true);
                return;
            }
        }

        // Modo directo falló (CORS, red, etc.) → intentar mpegts.js sin proxy
        if (isDirect) {
            _tryDirectMpegts(el.player.dataset.streamUrl);
            return;
        }

        // No era una URL de proxy (era directa desde el inicio) → ruta nativa
        const originalUrl = el.player.dataset.streamUrl;
        const isM3u8 = (originalUrl || '').toLowerCase().includes('.m3u8');
        if (!isM3u8) {
            _tryNative(originalUrl);
        } else {
            _setPlayerLoading(false);
            _showPlayerError('Stream no disponible o canal caído');
        }
    });
}

/**
 * Último recurso para canales live que no son accesibles vía proxy.
 * Intenta reproducir el stream directamente desde el navegador usando mpegts.js.
 * Solo se llega aquí si la página NO es HTTPS (mixed content ya filtrado antes).
 */
function _tryDirectMpegts(streamUrl) {
    if (!streamUrl) { _setPlayerLoading(false); _showPlayerError('Stream no disponible'); return; }

    // Doble comprobación: HTTPS + HTTP → mixed content garantizado → error inmediato
    if (location.protocol === 'https:' && (streamUrl).startsWith('http://')) {
        _setPlayerLoading(false);
        _showPlayerError('Este canal usa HTTP y la página es HTTPS.\nUsa el botón "Ver en pestaña nueva" para reproducirlo.');
        return;
    }

    if (typeof mpegts === 'undefined' || !mpegts.isSupported()) {
        _setPlayerLoading(false);
        _showPlayerError('Canal no accesible desde el servidor. Prueba "Ver en pestaña nueva".');
        return;
    }
    // mpegts.js puede reproducir tanto .ts como streams sin extensión (Xtream Codes shorthand).
    console.warn('[player] mpegts.js directo (sin proxy):', streamUrl);
    _playWithMpegts(streamUrl, true);
}

/**
 * Lanza la reproducción según la fuente:
 *  - 'rss' → abre en nueva pestaña
 *  - 'm3u' → player embebido con cascada: directo → proxy → error+VLC
 *
 * @param {string} streamUrl  URL codificada con encodeURIComponent
 * @param {string} title      Título del contenido
 * @param {string} source     'rss' | 'm3u'
 * @param {string|number} itemId  ID de BD del contenido (para playlist .m3u)
 */
/**
 * Lanza la reproducción.
 *
 * Flujo (idéntico al original que funcionaba + capas de proxy como fallback):
 *   1. HLS.js directo   → carga el stream; si es HLS lo parsea, si no HLS falla
 *   2. Error de red/CORS → reintenta a través de /api/hls-proxy (VPS como relay)
 *   3. Error de parseo   → no es HLS → intenta <video src> nativo (MP4, MKV…)
 *   4. Nativo falla      → reintenta a través de /api/stream-proxy
 *   5. Todo falla        → failover a la siguiente URL de respaldo (si las hay)
 *   6. Sin backups       → overlay con botones Reportar / VLC / copiar
 *
 * @param {string[]} liveUrls  Array completo de URLs de respaldo para failover automático.
 *                             Solo aplica a canales live. Si null/vacío, comportamiento idéntico al original.
 */
function playStream(streamUrl, title, source, itemId = '', image = '', liveUrls = null, drmKeyId = '', drmKey = '', drmType = '') {
    const url = decodeURIComponent(streamUrl);
    const imgDecoded = image ? decodeURIComponent(image) : '';

    // ── Inicializar failover para este stream ──────────────────────────────────
    // liveUrls contiene todas las URLs de respaldo del canal; _tryFailover() las
    // consume en orden cuando el stream principal falla. Sin esta asignación el
    // failover del reproductor embebido nunca funciona (los _failoverUrls quedan []).
    _failoverUrls = Array.isArray(liveUrls)
        ? liveUrls.map(_normalizeStreamUrl).filter(Boolean)
        : [];
    const _normalUrl = _normalizeStreamUrl(url);
    _failoverIdx = _failoverUrls.length
        ? Math.max(0, _failoverUrls.indexOf(_normalUrl))
        : 0;

    const hasClearKey = drmType === 'clearkey' && drmKeyId && drmKey;
    if (hasClearKey) {
        console.log('[playStream] DRM detected:', { drmType, drmKeyId });
        window._pendingDrmKeyId = drmKeyId;
        window._pendingDrmKey = drmKey;
    } else {
        window._pendingDrmKeyId = '';
        window._pendingDrmKey = '';
    }

    // Historial local
    let hist = JSON.parse(localStorage.getItem('cc_history') || '[]');
    hist = hist.filter(h => h.url !== url).slice(0, 49);
    hist.unshift({ url, title, source, ts: Date.now(), id: itemId, image: imgDecoded });
    localStorage.setItem('cc_history', JSON.stringify(hist));

    // Registrar en backend para recomendaciones (fire-and-forget, solo ítems M3U con ID)
    if (source !== 'rss' && itemId) {
        api.watch(itemId);
    }

    // RSS → nueva pestaña (cinemacity.cc bloquea iframe)
    if (source === 'rss') {
        window.open(url, '_blank', 'noopener,noreferrer');
        return;
    }

    _destroyHls();
    // Cerrar el modal de detalles si está abierto para que no quede atrapado detrás
    el.detailsModal.style.display = 'none';
    el.player.style.display = 'flex';
    document.getElementById('playerTitle').textContent = title || '';
    el.player.dataset.streamUrl = _normalizeStreamUrl(url);   // normaliza // doble
    el.player.dataset.itemId    = itemId;

    // Thumbnail en la cabecera del reproductor
    const thumb = document.getElementById('playerThumb');
    if (thumb) {
        if (imgDecoded) {
            thumb.src = imgDecoded;
            thumb.style.display = 'block';
            thumb.onerror = () => { thumb.style.display = 'none'; };
        } else {
            thumb.style.display = 'none';
        }
    }

    // (el fullscreen lo activa el usuario con el botón ⛶ o la tecla F)

    // Mostrar spinner de carga
    _setPlayerLoading(true);

    // Ocultar spinner cuando el vídeo empiece a reproducirse
    const _onPlaying = () => {
        _setPlayerLoading(false);
        el.videoPlayer.removeEventListener('playing', _onPlaying);
    };
    el.videoPlayer.addEventListener('playing', _onPlaying);

    // Registrar watchdog de congelación para streams live.
    // Los listeners son named → _destroyHls() los eliminará en la próxima reproducción.
    el.videoPlayer.removeEventListener('waiting', _onVideoWaitingLive);
    el.videoPlayer.removeEventListener('playing', _onVideoPlayingLive);
    el.videoPlayer.addEventListener('waiting', _onVideoWaitingLive);
    el.videoPlayer.addEventListener('playing', _onVideoPlayingLive);

    // Restaurar volumen guardado
    const vol = parseFloat(localStorage.getItem('cc_volume') || '1');
    if (!isNaN(vol)) el.videoPlayer.volume = Math.max(0, Math.min(1, vol));

    // ── Paso 1: decidir si usar Shaka (DRM), HLS.js, DASH.js o ir directo a nativo ──
    const hasPendingDrm = window._pendingDrmKeyId && window._pendingDrmKey;
    if (hasPendingDrm && _isLikelyDash(url)) {
        _loadShakaDrm(url, window._pendingDrmKeyId, window._pendingDrmKey);
        window._pendingDrmKeyId = '';
        window._pendingDrmKey = '';
        return;
    }
    if (_isLikelyDash(url)) {
        _loadDashDirect(url);
        return;
    }
    if (typeof Hls !== 'undefined' && Hls.isSupported() && _isLikelyHls(url)) {
        _loadHlsDirect(url);
    } else if (el.videoPlayer.canPlayType('application/vnd.apple.mpegurl') && _isLikelyHls(url)) {
        el.videoPlayer.src = url;
        el.videoPlayer.play().catch(() => {});
    } else {
        _tryNative(url);
    }
}

/**
 * Detecta si una URL probablemente contiene un stream HLS (.m3u8).
 * Las URLs con extensión de video conocida (.mkv, .mp4, etc.) NO son HLS
 * y se saltan HLS.js + proxy para ir directo a reproducción nativa.
 */
function _isLikelyHls(url) {
    const path = url.toLowerCase().split('?')[0].split('#')[0];
    const NON_HLS = ['.mkv', '.mp4', '.avi', '.mov', '.webm', '.flv', '.wmv', '.mpg', '.mpeg', '.mpd'];
    if (NON_HLS.some(ext => path.endsWith(ext))) return false;
    if (path.endsWith('.m3u8') || path.includes('.m3u8?')) return true;
    return true;
}

function _isLikelyDash(url) {
    const path = decodeURIComponent((url || '').toLowerCase().split('?')[0]);
    return path.endsWith('.mpd') || path.includes('.mpd?');
}

function _loadShakaDrm(url, drmKeyId, drmKey) {
    if (typeof shaka === 'undefined') {
        _showPlayerError('Shaka Player no está disponible en este navegador');
        return;
    }
    _destroyHls();
    console.log('[shaka] DRM load:', url, { keyId: drmKeyId, key: drmKey });

    const proxyUrl = `${location.origin}/api/dash-proxy?url=${encodeURIComponent(url)}`;
    console.log('[shaka] Using dash-proxy:', proxyUrl);

    const player = new shaka.Player(el.videoPlayer);
    window._shakaPlayer = player;

    player.addEventListener('error', (e) => {
        console.error('[shaka] error:', e);
        try { player.destroy(); } catch (_) {}
        window._shakaPlayer = null;
        _showPlayerError('Error DRM: ' + (e.detail?.message || 'ClearKey no disponible'));
    });

    player.addEventListener('loaded', () => {
        console.log('[shaka] loaded');
        _setPlayerLoading(false);
    });

    player.configure({
        drm: {
            clearKeys: {
                [drmKeyId]: drmKey
            }
        }
    });

    player.load(proxyUrl).then(() => {
        console.log('[shaka] stream started');
        el.videoPlayer.play().catch(() => {});
    }).catch((e) => {
        console.error('[shaka] load error:', e);
        _showPlayerError('Error al cargar stream DRM: ' + (e.message || e));
    });
}

function _loadDashDirect(origUrl) {
    if (typeof dashjs === 'undefined' || typeof dashjs.MediaPlayer !== 'function') {
        _showPlayerError('dash.js no está disponible en este navegador');
        return;
    }
    _destroyHls();
    const proxyUrl = `${location.origin}/api/dash-proxy?url=${encodeURIComponent(origUrl)}`;
    console.warn('[dash] Using dash-proxy:', proxyUrl);

    const player = dashjs.MediaPlayer().create();
    window._dashPlayer = player;

    let _videoErrorHandler = null;
    _videoErrorHandler = () => {
        const err = el.videoPlayer.error;
        let msg = 'Stream DASH no disponible.';
        if (err) {
            const code = err.code;
            if (code === 4) msg = 'Formato de video no soportado (error 4) — posible contenido DRM';
            else if (code === 2) msg = 'Error de red en stream DASH';
            else if (code === 1) msg = 'Stream DASH abortado';
            console.warn('[dash] video element error code:', code, 'msg:', err.message);
        }
        el.videoPlayer.removeEventListener('error', _videoErrorHandler);
        try { window._dashPlayer?.reset(); } catch (_) {}
        window._dashPlayer = null;
        _setPlayerLoading(false);
        _showPlayerError(msg);
    };
    el.videoPlayer.addEventListener('error', _videoErrorHandler);

    player.initialize(el.videoPlayer, proxyUrl, true);
}

/**
 * Paso 1 — HLS.js directo.
 * Para URLs IPTV live que acaban en .ts, prueba primero la variante .m3u8
 * (la mayoría de servidores IPTV sirven el mismo canal en ambos formatos).
 * Si falla por red/CORS → proxy del VPS.
 * Si falla por parseo   → no es HLS, prueba como vídeo nativo .ts.
 */
/**
 * Normaliza doble barra en el path de una URL (http://host//live/ → http://host/live/).
 * Algunos servidores IPTV almacenan las URLs con // en la ruta.
 */
function _normalizeStreamUrl(url) {
    try {
        const u = new URL(url);
        u.pathname = u.pathname.replace(/\/{2,}/g, '/');
        return u.toString();
    } catch (_) { return url; }
}

/**
 * Reproduce un stream MPEG-TS usando mpegts.js vía MediaSource API.
 * Chrome no puede decodificar video/mp2t directamente en <video>.
 * @param {string} url  URL del stream (puede ser la URL del proxy)
 * @param {boolean} isLive  true = stream en directo (sin fin conocido)
 */
function _playWithMpegts(url, isLive) {
    _destroyHls(); // destruye instancias anteriores HLS/mpegts
    if (typeof mpegts === 'undefined' || !mpegts.isSupported()) {
        // Fallback: intentar nativo (puede funcionar en Safari/Firefox con fMP4)
        el.videoPlayer.src = url;
        el.videoPlayer.load();
        el.videoPlayer.play().catch(() => {});
        el.videoPlayer.onerror = () => {
            const code = el.videoPlayer.error?.code;
            console.warn('[player] mpegts-fallback native onerror code', code, el.videoPlayer.error?.message);
            el.videoPlayer.onerror = null;
            _setPlayerLoading(false);
            _showPlayerError('Stream no disponible o formato no compatible con el navegador', code);
        };
        return;
    }
    const player = mpegts.createPlayer(
        { type: 'mpegts', url, isLive: isLive !== false },
        { enableWorker: true, lazyLoadMaxDuration: 30, seekType: 'range' }
    );
    player.attachMediaElement(el.videoPlayer);
    player.load();
    // player.play() devuelve void, no Promise — usar el elemento directamente
    el.videoPlayer.play().catch(() => {});
    window._mpegtsPlayer = player;
    player.on(mpegts.Events.ERROR, (errType, errDetail) => {
        console.warn('[mpegts] error', errType, errDetail, '| url:', url);
        try { player.destroy(); } catch (_) {}
        window._mpegtsPlayer = null;
        _setPlayerLoading(false);
        if (errType === mpegts.ErrorTypes.NETWORK_ERROR || errType === 'NetworkError') {
            _showPlayerError('El servidor IPTV puede estar bloqueando las peticiones desde el proxy.', 2);
        } else {
            _showPlayerError('Stream MPEG-TS no disponible o bloqueado en el servidor');
        }
    });
}

function _loadHlsDirect(url) {
    url = _normalizeStreamUrl(url);
    const urlLow = url.toLowerCase().split('?')[0];

    // ── Canales live Xtream Codes (.ts con /live/ en la ruta) ──────────────
    // Estrategia: intentar primero la variante M3U8/HLS (quitando .ts).
    // En Xtream Codes, /live/user/pass/id devuelve un playlist M3U8; los segmentos
    // HLS se sirven con la IP de quien hizo la petición de playlist — como el proxy
    // hace AMBAS peticiones (playlist + segmentos) desde la misma IP del VPS,
    // no hay session IP-lock. Si HLS falla, el error handler cae a _tryNative
    // que finalmente prueba mpegts con el .ts directo como último recurso.
    if (urlLow.endsWith('.ts') && urlLow.includes('/live/')) {
        const m3u8Url = url.replace(/\.ts(\?|$)/i, '$1');
        _loadHls(`/api/hls-proxy?url=${encodeURIComponent(m3u8Url)}`);
        return;
    }

    // ── Resto de streams HLS (URLs .m3u8, o .ts sin /live/) ────────────────
    // Para .ts sin /live/: intentar convertir a .m3u8 (algunas listas IPTV lo admiten)
    const hlsUrl = (urlLow.endsWith('.ts') && !urlLow.includes('/live/'))
        ? url.replace(/\.ts(\?.*)?$/i, '.m3u8')
        : url;

    // Solo usar proxy cuando la página es HTTPS (mixed content bloqueado).
    // En HTTP (local) el navegador puede cargar el stream directamente.
    if (hlsUrl.startsWith('http://') && location.protocol === 'https:') {
        _loadHls(`/api/hls-proxy?url=${encodeURIComponent(hlsUrl)}`);
        return;
    }

    // Para el intento directo usamos manifestLoadingMaxRetry: 2 (en vez de 10)
    // para caer rápido al proxy si el servidor IPTV no responde o bloquea.
    _hls = new Hls({ ..._buildHlsConfig(), manifestLoadingMaxRetry: 2 });
    _hls.loadSource(hlsUrl);
    _hls.attachMedia(el.videoPlayer);
    _hls.on(Hls.Events.MANIFEST_PARSED, () => {
        el.videoPlayer.play().catch(() => {});
    });
    _hls.on(Hls.Events.LEVEL_LOADED, (_, data) => {
        if (data.details && data.details.live) {
            _isCurrentStreamLive = true;
            _showLiveIndicator();
            _hls.config.liveDurationInfinity = true;
        } else {
            _hls.config.maxBufferLength    = 60;
            _hls.config.maxMaxBufferLength = 120;
            _hls.config.maxBufferSize      = 120 * 1000 * 1000;
        }
    });
    _hls.on(Hls.Events.ERROR, (_, data) => {
        if (!data.fatal) {
            if (_isCurrentStreamLive && _hls && (
                data.details === Hls.ErrorDetails.BUFFER_STALLED_ERROR ||
                data.details === Hls.ErrorDetails.BUFFER_NUDGE_ON_STALL
            )) {
                const edge = _hls.liveSyncPosition;
                if (edge && edge > 0) {
                    el.videoPlayer.currentTime = edge;
                    el.videoPlayer.play().catch(() => {});
                }
            }
            return;
        }
        _destroyHls();
        // Reintentar a través del proxy (VLC User-Agent + relay)
        _loadHls(`/api/hls-proxy?url=${encodeURIComponent(hlsUrl)}`);
    });
}

/**
 * Paso 3 — Reproducción nativa (<video src>).
 * Funciona para MP4, MKV con H.264/AAC, WebM, etc.
 * Si el navegador no puede reproducirlo → intenta a través del stream-proxy.
 */
function _tryNative(url) {
    url = _normalizeStreamUrl(url);
    const proxyUrl = `/api/stream-proxy?url=${encodeURIComponent(url)}`;
    const urlLow   = url.toLowerCase().split('?')[0];
    const isTsUrl  = urlLow.endsWith('.ts');
    // Extensiones VOD conocidas: el <video> nativo es el único camino; mpegts no ayuda
    const isKnownVod = ['.mp4','.mkv','.avi','.mov','.webm','.flv','.wmv','.mpg','.mpeg','.m4v']
        .some(ext => urlLow.endsWith(ext));

    // .ts → mpegts.js siempre via proxy (Chrome no puede reproducir video/mp2t nativo)
    if (isTsUrl && typeof mpegts !== 'undefined' && mpegts.isSupported()) {
        _playWithMpegts(proxyUrl, true);
        return;
    }

    // Mixed-content: saltar directo al proxy
    const src = (url.startsWith('http://') && location.protocol === 'https:')
        ? proxyUrl : url;

    // Última bala: mpegts para URLs sin extensión conocida (streams live sin .ts)
    function _lastResort() {
        if (!isKnownVod && typeof mpegts !== 'undefined' && mpegts.isSupported()) {
            _playWithMpegts(proxyUrl, true);
        } else {
            _setPlayerLoading(false);
            _showPlayerError('Stream no disponible o formato no compatible con el navegador');
        }
    }

    el.videoPlayer.onerror = null;
    el.videoPlayer.src = src;
    el.videoPlayer.load();
    el.videoPlayer.play().catch(() => {});
    el.videoPlayer.onerror = () => {
        const code = el.videoPlayer.error?.code;
        console.warn('[player] _tryNative onerror src=proxy?', src === proxyUrl, 'code', code, el.videoPlayer.error?.message);
        el.videoPlayer.onerror = null;
        if (src === proxyUrl) {
            // Probe: determinar si el proxy está bloqueado (502/403) o si es un problema de codec
            fetch(proxyUrl, { method: 'GET', headers: { Range: 'bytes=0-63' } })
                .then(r => r.text().then(t => {
                    console.warn('[proxy-diag] status:', r.status,
                        '| ct:', r.headers.get('content-type'),
                        '| body[0..64]:', JSON.stringify(t.slice(0, 64)));
                    if (r.status === 502 || r.status === 403 || r.status === 401) {
                        // Proxy detectó que el servidor IPTV bloqueó o devolvió respuesta inválida
                        _setPlayerLoading(false);
                        _showPlayerError('El servidor IPTV puede estar bloqueando las peticiones desde el proxy.', 2);
                    } else {
                        _lastResort();
                    }
                }))
                .catch(e => { console.warn('[proxy-diag] fetch error:', e); _lastResort(); });
            return;
        }
        // Directo falló → reintentar via proxy
        el.videoPlayer.onerror = null;
        el.videoPlayer.src = proxyUrl;
        el.videoPlayer.load();
        el.videoPlayer.play().catch(() => {});
        el.videoPlayer.onerror = () => {
            console.warn('[player] _tryNative proxy onerror code', el.videoPlayer.error?.code, el.videoPlayer.error?.message);
            el.videoPlayer.onerror = null;
            _lastResort();
        };
    };
}

// ── Favoritos ──────────────────────────────────────────────
function toggleFav(id) {
    id = String(id);
    const idx = state.favorites.indexOf(id);
    if (idx === -1) {
        state.favorites.push(id);
        showNotification('Agregado a favoritos');
    } else {
        state.favorites.splice(idx, 1);
        showNotification('Eliminado de favoritos');
    }
    localStorage.setItem('cc_favorites', JSON.stringify(state.favorites));

    document.querySelectorAll(`[data-fav="${id}"]`).forEach(btn => {
        const iNow = isFav(id);
        btn.classList.toggle('active', iNow);
        const icon = btn.querySelector('i');
        if (icon) icon.className = `bi ${iNow ? 'bi-heart-fill' : 'bi-heart'}`;
    });
}

// ── Notificaciones ─────────────────────────────────────────
function showNotification(msg, type = 'success') {
    const n = document.createElement('div');
    n.className = 'notification';
    n.style.cssText = `
        position:fixed;top:20px;right:20px;
        background:${type === 'error' ? '#c0070f' : 'var(--primary-color, #e50914)'};
        color:#fff;padding:.8rem 1.2rem;border-radius:8px;
        box-shadow:0 4px 12px rgba(0,0,0,.4);z-index:9999;
        animation:slideIn .3s ease;font-size:.9rem;
    `;
    n.textContent = msg;
    document.body.appendChild(n);
    setTimeout(() => n.remove(), 3000);
}

// ── Filtros y paginación ───────────────────────────────────
async function loadGrid(append = false) {
    if (!append) {
        state.currentPage = 1;
        el.moviesGrid.innerHTML = '<p class="no-content">Cargando...</p>';

        // Actualizar título de sección según filtro de tipo activo
        if (el.gridTitle) {
            const titles = {
                pelicula: '🎬 Películas',
                serie:    '📺 Series',
                live:     '📡 En Directo',
                '':       '🎬 Películas',   // sin filtro → muestra películas por defecto
            };
            el.gridTitle.textContent = titles[state.currentType] ?? '🎬 Películas';
        }
    }

    // Vista En Directo → cargar TODOS los canales de la API (el caché del inicio
    // solo tiene 60 para el carrusel; aquí necesitamos todos para que el filtro
    // de categoría funcione correctamente).
    if (state.currentType === 'live') {
        if (!append) {
            try {
                const data = await api.liveAgrupados({ limit: 5000 });
                if (Array.isArray(data)) state.liveGroups = data;
            } catch { /* mantener lo que haya en caché si la API falla */ }
            const activePill = document.querySelector('.genre-strip-pill.active');
            const activeCat = activePill ? decodeURIComponent(activePill.dataset.cat || '') : '';
            _filterLiveByCategory(activeCat);
            el.loadMore.dataset.hasMore = 'false';
        }
        return;
    }

    try {
        let data;
        if (state.currentType === 'serie') {
            // Series → mostrar agrupadas por título (una tarjeta por serie)
            data = await api.seriesAgrupadas({
                genero: state.currentGenre,
                sort:   state.currentSort || 'year_desc',
                page:   state.currentPage,
                limit:  48,
            });
        } else {
            // Películas / En Directo / Todo
            // Cuando no hay filtro de tipo, mostrar solo películas por defecto
            // (las series se ven agrupadas en su sección — evita ver 42 portadas del mismo episodio)
            const tipoFiltro = state.currentType || 'pelicula';
            data = await api.contenido({
                tipo:   tipoFiltro,
                año:    state.currentYear,
                genero: state.currentGenre,
                sort:   state.currentSort || 'recent',
                page:   state.currentPage,
                limit:  48,
            });
        }

        renderGrid(data.items, append);

        const hasMore = state.currentPage < data.pages;
        el.loadMore.dataset.hasMore = hasMore ? 'true' : 'false';
    } catch {
        if (!append) el.moviesGrid.innerHTML = '<p class="no-content">Error al cargar contenido</p>';
    }
}

// ── Búsqueda con debounce ──────────────────────────────────
let searchTimer;
async function performSearch(q) {
    if (!q.trim()) {
        el.searchResults.style.display = 'none';
        return;
    }
    try {
        const data = await api.search(q);
        if (!data.items.length) {
            el.searchResults.innerHTML = '<div class="no-results">Sin resultados</div>';
        } else {
            el.searchResults.innerHTML = data.items.map(item => {
                const srImg = getImageUrl(item);
                return `
                <div class="search-result-item" data-id="${item.id}">
                    <img src="${srImg}" onerror="this.src='${PLACEHOLDER}'" alt="">
                    <div>
                        <strong>${item.title}</strong>
                        <div class="search-result-meta">
                            <span>${item.year || ''}</span>
                            <span>${item.type === 'movie' ? '🎬' : item.type === 'live' ? '📡' : '📺'}</span>
                        </div>
                    </div>
                </div>`;
            }).join('');
        }
        el.searchResults.style.display = 'block';
    } catch {
        el.searchResults.style.display = 'none';
    }
}

// ── Poblar filtros de año y género ─────────────────────────
async function loadFilters() {
    try {
        const [años, generos] = await Promise.all([api.años(), api.generos()]);
        años.forEach(y => {
            const o = document.createElement('option');
            o.value = y; o.textContent = y;
            el.yearFilter.appendChild(o);
        });
        // Sin límite de 40 — mostrar todos los géneros (ya vienen ordenados A-Z del API)
        // o.value = valor RAW (mayúsculas, para que el filtro API funcione con LIKE)
        // o.textContent = título capitalizado (presentación al usuario)
        generos.forEach(g => {
            const o = document.createElement('option');
            o.value = g; o.textContent = titleCase(g);
            el.genreFilter.appendChild(o);
        });
    } catch { /* silenciar */ }
}

// ── Vista por tipo: oculta/muestra secciones tipo tab ──────
function setView(type) {
    const hero       = document.getElementById('home');
    const novedSec   = document.getElementById('novedades')?.closest('section');
    const pelSec     = document.getElementById('peliculas');
    const serSec     = document.getElementById('series');
    const liveSec    = document.getElementById('live');
    const contSec = document.getElementById('continueSection');

    const recoSec         = document.getElementById('recoSection');
    const porqueSecs      = document.getElementById('porqueVisteContainer');

    const genreStrip = document.getElementById('genreStrip');

    if (!type) {
        // Vista inicio: mostrar todo
        [hero, novedSec, pelSec, serSec, liveSec].forEach(s => {
            if (s) s.style.display = '';
        });
        // continueSection solo si hay historial
        if (contSec) {
            const hist = JSON.parse(localStorage.getItem('cc_history') || '[]');
            contSec.style.display = hist.length ? '' : 'none';
        }
        // recoSection solo si tiene contenido
        if (recoSec && recoSec.querySelector('.movie-card')) recoSec.style.display = '';
        if (porqueSecs) porqueSecs.style.display = '';
        // Ocultar genre strip en la vista inicio
        if (genreStrip) genreStrip.style.display = 'none';
        document.body.classList.remove('has-genre-strip');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    } else {
        // Vista de tipo: ocultar hero, novedades y TODOS los carruseles.
        [hero, novedSec, contSec, pelSec, serSec, liveSec, recoSec, porqueSecs].forEach(s => {
            if (s) s.style.display = 'none';
        });
        // Mostrar lista-bar y genre-strip solo en la vista de directo
        const listaBar = document.getElementById('listaBar');
        const showLive = type === 'live';
        if (listaBar) listaBar.style.display = showLive ? 'flex' : 'none';
        if (genreStrip) {
            genreStrip.style.display = showLive ? 'flex' : 'none';
            document.body.classList.toggle('has-genre-strip', showLive);
        }
        // Ajustar clase para dar espacio si la lista-bar está visible
        const hasListas = listaBar && listaBar.querySelectorAll('option').length > 1;
        document.body.classList.toggle('has-lista-bar', showLive && hasListas);
        document.getElementById('movies')?.scrollIntoView({ behavior: 'smooth' });
    }
}

/** Obtiene el grupo de directo desde el elemento clicado (por índice o título). */
function _getLiveGroup(el) {
    const idx = parseInt(el.dataset.groupIdx, 10);
    if (!isNaN(idx) && state.liveGroups[idx]) return state.liveGroups[idx];
    // Fallback: buscar por título si el índice no coincide
    const title = decodeURIComponent(el.dataset.groupTitle || '');
    if (title) return state.liveGroups.find(g => g.title === title) || null;
    return null;
}

// ── Eventos ────────────────────────────────────────────────
function setupEvents() {
    // Delegación de clicks en cards / botones
    document.addEventListener('click', e => {
        // Botón "Ver episodios" de serie agrupada
        const seriesBtn = e.target.closest('.btn-series-open');
        if (seriesBtn) {
            e.stopPropagation();
            const t = seriesBtn.dataset.seriesTitle;
            if (t) showSeriesDetail(decodeURIComponent(t));
            return;
        }

        // Botón/click en tarjeta de grupo de directo → abrir modal de variantes
        const liveGroupBtn = e.target.closest('.btn-live-group-open');
        if (liveGroupBtn) {
            e.stopPropagation();
            const group = _getLiveGroup(liveGroupBtn);
            if (group) showLiveGroupDetail(group);
            return;
        }
        const liveGroupCard = e.target.closest('.live-group-card');
        if (liveGroupCard && !e.target.closest('button')) {
            const group = _getLiveGroup(liveGroupCard);
            if (group) showLiveGroupDetail(group);
            return;
        }

        // Click en tarjeta de serie agrupada → abrir modal de episodios
        const seriesCard = e.target.closest('.series-card');
        if (seriesCard && !e.target.closest('button')) {
            const t = seriesCard.dataset.seriesTitle;
            if (t) showSeriesDetail(decodeURIComponent(t));
            return;
        }

        // Click en tarjeta normal → abrir detalles
        const card = e.target.closest('.movie-card');
        if (card && !e.target.closest('button')) {
            showDetails(card.dataset.id);
            return;
        }

        // Botón Ver / Reproducir
        const playBtn = e.target.closest('[data-stream]');
        if (playBtn) {
            e.stopPropagation();
            let btnLiveUrls = null;
            if (playBtn.dataset.liveUrls) {
                try { btnLiveUrls = JSON.parse(decodeURIComponent(playBtn.dataset.liveUrls)); } catch (_) {}
            }
            const btnDrmKeyId = playBtn.dataset.drmKeyId || '';
            const btnDrmKey = playBtn.dataset.drmKey || '';
            const btnDrmType = playBtn.dataset.drmType || '';
            playStream(
                playBtn.dataset.stream,
                playBtn.dataset.title,
                playBtn.dataset.source || 'm3u',
                playBtn.dataset.id || '',
                playBtn.dataset.image || '',
                btnLiveUrls,
                btnDrmKeyId, btnDrmKey, btnDrmType
            );
            return;
        }

        // Botón favorito
        const favBtn = e.target.closest('[data-fav]');
        if (favBtn) {
            e.stopPropagation();
            toggleFav(favBtn.dataset.fav);
            return;
        }

        // Botón más info del hero
        const infoBtn = e.target.closest('[data-id].btn-info');
        if (infoBtn) {
            showDetails(infoBtn.dataset.id);
            return;
        }

        // Click en resultado de búsqueda
        const srItem = e.target.closest('.search-result-item');
        if (srItem) {
            showDetails(srItem.dataset.id);
            el.searchResults.style.display = 'none';
            return;
        }

        // Cerrar cualquier modal
        if (e.target.classList.contains('close-modal')) {
            el.detailsModal.style.display = 'none';
            const sm  = document.getElementById('seriesModal');
            const lgm = document.getElementById('liveGroupModal');
            if (sm)  sm.style.display  = 'none';
            if (lgm) lgm.style.display = 'none';
            return;
        }
        if (e.target === el.detailsModal) {
            el.detailsModal.style.display = 'none';
        }
        const sm = document.getElementById('seriesModal');
        if (sm && e.target === sm) sm.style.display = 'none';
        const lgm = document.getElementById('liveGroupModal');
        if (lgm && e.target === lgm) lgm.style.display = 'none';
    });

    // Cerrar reproductor — botón ×
    document.querySelector('.btn-close-player')?.addEventListener('click', () => {
        el.videoPlayer.pause();
        _destroyHls();
        el.player.style.display = 'none';
        el.detailsModal.style.display = 'none';
    });

    // Cerrar reproductor — click en la zona negra fuera del vídeo
    el.player?.addEventListener('click', e => {
        if (e.target === el.player || e.target.classList.contains('player-body')) {
            el.videoPlayer.pause();
            _destroyHls();
            el.player.style.display = 'none';
            el.detailsModal.style.display = 'none';
        }
    });

    // Búsqueda
    el.searchInput?.addEventListener('input', e => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => performSearch(e.target.value), 350);
    });
    el.searchBtn?.addEventListener('click', () => performSearch(el.searchInput.value));

    // Cerrar búsqueda al hacer click fuera
    document.addEventListener('click', e => {
        if (!el.searchInput?.contains(e.target) && !el.searchResults?.contains(e.target)) {
            if (el.searchResults) el.searchResults.style.display = 'none';
        }
    });

    // Filtros desplegables
    el.typeFilter?.addEventListener('change', e => {
        state.currentType = e.target.value;
        setView(e.target.value);
        loadGrid();
    });
    el.yearFilter?.addEventListener('change', e => {
        state.currentYear = e.target.value;
        loadGrid();
    });
    el.genreFilter?.addEventListener('change', e => {
        state.currentGenre = e.target.value;
        loadGrid();
    });

    // Selector de lista de canales en directo
    document.getElementById('listaFilter')?.addEventListener('change', e => {
        _reloadLiveByLista(e.target.value);
    });

    // ── Scroll infinito (sustituye al botón "Cargar más") ────
    // El botón sigue existiendo como señal de "hay más", pero no se muestra.
    // IntersectionObserver lo detecta y carga automáticamente.
    if (el.loadMore) el.loadMore.style.cssText = 'opacity:0;pointer-events:none;height:1px;';
    if ('IntersectionObserver' in window && el.loadMore) {
        let _scrollLoading = false;
        const _scrollObs = new IntersectionObserver(async entries => {
            if (!entries[0].isIntersecting || _scrollLoading) return;
            if (el.loadMore.dataset.hasMore !== 'true') return;
            _scrollLoading = true;
            state.currentPage++;
            await loadGrid(true);
            _scrollLoading = false;
        }, { rootMargin: '400px' });
        _scrollObs.observe(el.loadMore);
    } else {
        // Fallback: botón visible si no hay IntersectionObserver
        el.loadMore.style.cssText = '';
        el.loadMore.addEventListener('click', () => {
            state.currentPage++;
            loadGrid(true);
        });
    }

    // Header scroll
    window.addEventListener('scroll', () => {
        document.querySelector('.header')?.classList.toggle('scrolled', window.scrollY > 80);
    });

    // ── Atajos de teclado ────────────────────────────────────
    document.addEventListener('keydown', e => {
        const playerOpen = el.player.style.display === 'flex';
        const tag = document.activeElement?.tagName;
        const typing = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';

        if (playerOpen && !typing) {
            switch (e.key) {
                case ' ': case 'k':
                    e.preventDefault();
                    el.videoPlayer.paused ? el.videoPlayer.play().catch(()=>{}) : el.videoPlayer.pause();
                    break;
                case 'ArrowRight': case 'l':
                    e.preventDefault();
                    el.videoPlayer.currentTime = Math.min(
                        el.videoPlayer.duration || Infinity,
                        el.videoPlayer.currentTime + 10
                    );
                    break;
                case 'ArrowLeft': case 'j':
                    e.preventDefault();
                    el.videoPlayer.currentTime = Math.max(0, el.videoPlayer.currentTime - 10);
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    el.videoPlayer.volume = Math.min(1, el.videoPlayer.volume + 0.1);
                    localStorage.setItem('cc_volume', el.videoPlayer.volume);
                    break;
                case 'ArrowDown':
                    e.preventDefault();
                    el.videoPlayer.volume = Math.max(0, el.videoPlayer.volume - 0.1);
                    localStorage.setItem('cc_volume', el.videoPlayer.volume);
                    break;
                case 'm': case 'M':
                    e.preventDefault();
                    el.videoPlayer.muted = !el.videoPlayer.muted;
                    break;
                case 'f': case 'F':
                    e.preventDefault();
                    if (document.fullscreenElement) {
                        document.exitFullscreen().catch(()=>{});
                    } else {
                        el.player.requestFullscreen().catch(()=>{});
                    }
                    break;
                case 'p': case 'P':
                    e.preventDefault();
                    if (document.pictureInPictureEnabled) {
                        if (document.pictureInPictureElement) {
                            document.exitPictureInPicture().catch(()=>{});
                        } else if (el.videoPlayer.readyState > 0) {
                            el.videoPlayer.requestPictureInPicture()
                                .then(() => { el.player.style.display = 'none'; })
                                .catch(()=>{});
                        }
                    }
                    break;
                case 'Escape':
                    el.videoPlayer.pause();
                    _destroyHls();
                    el.player.style.display = 'none';
                    el.detailsModal.style.display = 'none';
                    break;
            }
        } else if (!playerOpen && e.key === 'Escape') {
            el.detailsModal.style.display = 'none';
            const sm  = document.getElementById('seriesModal');
            const lgm = document.getElementById('liveGroupModal');
            if (sm)  sm.style.display  = 'none';
            if (lgm) lgm.style.display = 'none';
        }
    });

    // Guardar volumen al cambiar
    el.videoPlayer?.addEventListener('volumechange', () => {
        localStorage.setItem('cc_volume', el.videoPlayer.volume);
        localStorage.setItem('cc_muted',  el.videoPlayer.muted);
    });

    // ── Controles adicionales del player ─────────────────────
    // PiP
    document.getElementById('btnPip')?.addEventListener('click', () => {
        if (!document.pictureInPictureEnabled) {
            showNotification('Tu navegador no soporta PiP', 'error'); return;
        }
        if (document.pictureInPictureElement) {
            document.exitPictureInPicture().catch(()=>{});
        } else if (el.videoPlayer.readyState > 0) {
            el.videoPlayer.requestPictureInPicture()
                .then(() => { el.player.style.display = 'none'; })
                .catch(() => showNotification('No se pudo activar PiP', 'error'));
        } else {
            showNotification('El vídeo aún no está listo', 'error');
        }
    });

    // Velocidad de reproducción
    document.getElementById('speedControl')?.addEventListener('change', e => {
        el.videoPlayer.playbackRate = parseFloat(e.target.value) || 1;
    });

    // ── Navegación con filtro de tipo (Películas / Series / Directo) ──
    document.querySelectorAll('a[data-type]').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            const type = link.dataset.type;
            state.currentType  = type;
            state.currentPage  = 1;
            // Resetear filtros al cambiar de tipo
            state.currentYear  = '';
            state.currentGenre = '';
            state.currentSort  = 'year_desc';
            if (el.typeFilter)  el.typeFilter.value  = type;
            if (el.yearFilter)  el.yearFilter.value  = '';
            if (el.genreFilter) el.genreFilter.value = '';
            const sf = document.getElementById('sortFilter');
            if (sf) sf.value = 'year_desc';
            document.querySelectorAll('.genre-pill').forEach(p => p.classList.remove('active'));
            // Al entrar en Directo: activar pastilla "Todos" del genre strip
            if (type === 'live') {
                document.querySelectorAll('.genre-strip-pill').forEach(p => p.classList.remove('active'));
                const todoPill = document.querySelector('.genre-strip-pill[data-cat=""]');
                if (todoPill) todoPill.classList.add('active');
            }
            setView(type);
            loadGrid();
            document.querySelectorAll('.nav-item, .desktop-nav a').forEach(n => n.classList.remove('active'));
            document.querySelectorAll(`a[data-type="${type}"]`).forEach(n => n.classList.add('active'));
        });
    });

    // ── Inicio: resetear todo y volver a la vista completa ───
    document.querySelectorAll('a[href="#home"]').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            state.currentType  = '';
            state.currentPage  = 1;
            state.currentYear  = '';
            state.currentGenre = '';
            state.currentSort  = 'year_desc';
            if (el.typeFilter)  el.typeFilter.value  = '';
            if (el.yearFilter)  el.yearFilter.value  = '';
            if (el.genreFilter) el.genreFilter.value = '';
            const sf = document.getElementById('sortFilter');
            if (sf) sf.value = 'year_desc';
            document.querySelectorAll('.genre-pill').forEach(p => p.classList.remove('active'));
            hideFavoritesSection();
            setView('');
            loadGrid();
            document.querySelectorAll('.nav-item, .desktop-nav a').forEach(n => n.classList.remove('active'));
            document.querySelectorAll('a[href="#home"]').forEach(n => n.classList.add('active'));
        });
    });

    // ── Géneros: muestra/oculta el panel de filtros (año + género) en la cabecera ──
    document.getElementById('btnGeneros')?.addEventListener('click', e => {
        e.preventDefault();
        const panel = document.getElementById('headerFiltersPanel');
        if (!panel) return;
        const visible = panel.classList.toggle('active');
        e.currentTarget.classList.toggle('active', visible);
    });



    // ── Fullscreen button en cabecera del player ──────────────
    document.getElementById('btnFsPlayer')?.addEventListener('click', () => {
        if (document.fullscreenElement) {
            document.exitFullscreen().catch(() => {});
        } else {
            el.player.requestFullscreen().catch(() => {});
        }
    });

    // Actualizar icono al cambiar estado fullscreen
    document.addEventListener('fullscreenchange', () => {
        const btn = document.getElementById('btnFsPlayer');
        if (!btn) return;
        const icon = btn.querySelector('i');
        if (document.fullscreenElement) {
            icon.className = 'bi bi-fullscreen-exit';
        } else {
            icon.className = 'bi bi-fullscreen';
        }
    });

    // ── Favoritos (nav móvil) ─────────────────────────────────
    document.getElementById('mobileFavBtn')?.addEventListener('click', e => {
        e.preventDefault();
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        e.currentTarget.classList.add('active');
        showFavoritesSection();
    });

    // Limpiar favoritos
    document.getElementById('btnClearFav')?.addEventListener('click', () => {
        state.favorites = [];
        localStorage.removeItem('cc_favorites');
        showFavoritesSection();
        showNotification('Favoritos eliminados');
    });

    // ── Historial (limpiar) ───────────────────────────────────
    document.getElementById('btnClearHistory')?.addEventListener('click', () => {
        localStorage.removeItem('cc_history');
        const sec = document.getElementById('continueSection');
        if (sec) sec.style.display = 'none';
        showNotification('Historial eliminado');
    });


    // ── Búsqueda móvil ────────────────────────────────────────
    document.getElementById('mobileSearchBtn')?.addEventListener('click', e => {
        e.preventDefault();
        const overlay = document.getElementById('mobileSearchOverlay');
        if (overlay) {
            overlay.classList.add('active');
            setTimeout(() => document.getElementById('mobileSearchInput')?.focus(), 100);
        }
    });

    document.getElementById('btnCloseMobileSearch')?.addEventListener('click', () => {
        document.getElementById('mobileSearchOverlay')?.classList.remove('active');
    });

    let mobileSearchTimer;
    document.getElementById('mobileSearchInput')?.addEventListener('input', e => {
        clearTimeout(mobileSearchTimer);
        mobileSearchTimer = setTimeout(() => performMobileSearch(e.target.value), 350);
    });


    // ── Sort filter ───────────────────────────────────────────
    document.getElementById('sortFilter')?.addEventListener('change', e => {
        state.currentSort = e.target.value;
        state.currentPage = 1;
        loadGrid();
    });

    // Navegación móvil — active state para links sin filtro
    document.querySelectorAll('.mobile-nav .nav-item:not([data-type]):not([href="#home"])').forEach(item => {
        if (item.id === 'mobileSearchBtn' || item.id === 'mobileFavBtn') return;
        item.addEventListener('click', () => {
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            item.classList.add('active');
        });
    });
}

// ── Selector de lista para canales en directo ───────────────
async function loadLiveListas() {
    try {
        const listas = await api.liveListas();
        const sel    = document.getElementById('listaFilter');
        const bar    = document.getElementById('listaBar');
        if (!sel || !bar) return;

        if (!listas || listas.length <= 1) {
            // Con 0 ó 1 lista no tiene sentido mostrar el selector
            bar.style.display = 'none';
            document.body.classList.remove('has-lista-bar');
            return;
        }

        // Mantener la opción "Todas las listas" y añadir las listas reales
        sel.innerHTML = '<option value="">📋 Todas las listas</option>' +
            listas.map(l => `<option value="${l.id}">${l.nombre}</option>`).join('');

        // Auto-seleccionar la lista predeterminada (si existe y el usuario no eligió otra)
        const defaultLista = listas.find(l => l.isDefault);
        if (defaultLista && !state.currentListaId) {
            sel.value = String(defaultLista.id);
            await _reloadLiveByLista(defaultLista.id);
        }

        // Mostrar la barra si estamos en vista live
        if (state.currentType === 'live') {
            bar.style.display = 'flex';
            document.body.classList.add('has-lista-bar');
        }
    } catch { /* silenciar */ }
}

/** Recarga los canales en directo filtrando por lista y actualiza las categorías. */
async function _reloadLiveByLista(listaId) {
    state.currentListaId = listaId;
    try {
        const params = { limit: 200 };
        if (listaId) params.lista_id = listaId;

        const [liveData, cats] = await Promise.all([
            api.liveAgrupados(params),
            api.liveCategorias(listaId ? { lista_id: listaId } : {}),
        ]);

        state.liveGroups = Array.isArray(liveData) ? liveData : [];

        // Actualizar carrusel en vista inicio
        if (el.liveCarousel) {
            el.liveCarousel.innerHTML = state.liveGroups.length
                ? state.liveGroups.map((g, i) => renderLiveGroupCard(g, i)).join('')
                : '<p class="no-content">Sin canales disponibles</p>';
        }

        // Actualizar grid si estamos en vista live
        if (state.currentType === 'live' && el.moviesGrid) {
            el.moviesGrid.innerHTML = state.liveGroups.length
                ? state.liveGroups.map((g, i) => renderLiveGroupCard(g, i)).join('')
                : '<p class="no-content">Sin canales disponibles</p>';
        }

        // Regenerar pastillas de categoría
        const strip = document.getElementById('genreStrip');
        if (strip) {
            strip.innerHTML =
                `<button class="genre-strip-pill active" data-cat="">Todos</button>` +
                (cats || []).map(cat =>
                    `<button class="genre-strip-pill" data-cat="${encodeURIComponent(cat)}">${cat}</button>`
                ).join('');
            strip.querySelectorAll('.genre-strip-pill').forEach(pill => {
                pill.addEventListener('click', () => {
                    strip.querySelectorAll('.genre-strip-pill').forEach(p => p.classList.remove('active'));
                    pill.classList.add('active');
                    _filterLiveByCategory(decodeURIComponent(pill.dataset.cat));
                });
            });
        }
    } catch { /* silenciar */ }
}

// ── Género strip (pastillas de categorías de canales en directo) ────────────
async function loadGenrePills() {
    try {
        const cats  = await api.liveCategorias();
        const strip = document.getElementById('genreStrip');
        const btnG  = document.getElementById('btnGeneros');

        if (!cats || !cats.length) {
            // Sin categorías: ocultar el botón Géneros para no confundir
            if (btnG) btnG.style.display = 'none';
            return;
        }

        if (!strip) return;

        // Añadir pastilla "Todos" al inicio
        strip.innerHTML =
            `<button class="genre-strip-pill active" data-cat="">Todos</button>` +
            cats.map(cat =>
                `<button class="genre-strip-pill" data-cat="${encodeURIComponent(cat)}">${cat}</button>`
            ).join('');

        strip.querySelectorAll('.genre-strip-pill').forEach(pill => {
            pill.addEventListener('click', () => {
                strip.querySelectorAll('.genre-strip-pill').forEach(p => p.classList.remove('active'));
                pill.classList.add('active');
                const cat = decodeURIComponent(pill.dataset.cat);
                // Si no estamos en vista live, cambiar a ella primero
                if (state.currentType !== 'live') {
                    state.currentType = 'live';
                    if (el.typeFilter) el.typeFilter.value = 'live';
                    document.querySelectorAll('.nav-item, .desktop-nav a').forEach(n => n.classList.remove('active'));
                    document.querySelectorAll('a[data-type="live"]').forEach(n => n.classList.add('active'));
                    setView('live');
                }
                _filterLiveByCategory(cat);
            });
        });
    } catch { /* silenciar */ }
}

/** Filtra los canales en directo por categoría usando los grupos en memoria.
 *  En vista live (grid) actualiza el grid principal; en vista inicio actualiza el carrusel. */
function _filterLiveByCategory(cat) {
    const catTrim = (cat || '').trim();
    const filtered = catTrim
        ? state.liveGroups.filter(g =>
            (g.groupTitle || '').trim() === catTrim ||
            (g.genres || []).some(gen => (gen || '').trim() === catTrim)
          )
        : state.liveGroups;
    const html = filtered.length
        ? filtered.map((g, i) => renderLiveGroupCard(g, state.liveGroups.indexOf(g))).join('')
        : '<p class="no-content">Sin canales en esta categoría</p>';
    // En vista Directo (grid principal), actualizar el grid
    if (state.currentType === 'live' && el.moviesGrid) {
        el.moviesGrid.innerHTML = html;
    }
    // Siempre actualizar también el carrusel de la sección inicio (puede estar oculto)
    if (el.liveCarousel) {
        el.liveCarousel.innerHTML = html;
    }
}

// ── Recomendaciones personalizadas ─────────────────────────
async function loadRecomendaciones() {
    try {
        const data = await api.recomendaciones();
        if (!data || !data.items || !data.items.length) return;

        // ── "Para ti" carousel ──
        const sec      = document.getElementById('recoSection');
        const carousel = document.getElementById('recoCarousel');
        const subtitle = document.getElementById('recoSubtitle');
        if (sec && carousel) {
            renderCarousel(data.items, carousel);
            sec.style.display = '';
            if (subtitle && data.top_genres && data.top_genres.length) {
                subtitle.textContent = 'Basado en: ' + data.top_genres.map(titleCase).join(', ');
            }
        }

        // ── "Porque viste X" sections ──
        // Read last 3 watched M3U items from local history that have a valid id
        const hist = JSON.parse(localStorage.getItem('cc_history') || '[]');
        const recentM3u = hist.filter(h => h.source !== 'rss' && h.id).slice(0, 3);
        if (!recentM3u.length) return;

        const container = document.getElementById('porqueVisteContainer');
        if (!container) return;
        container.innerHTML = '';

        for (const watched of recentM3u) {
            try {
                const reco = await api.recomendaciones(watched.id);
                if (!reco || !reco.items || !reco.items.length) continue;

                const sec = document.createElement('section');
                sec.className = 'content-section porque-viste-sec';
                sec.dataset.anchor = 'porqueViste_' + watched.id;
                sec.innerHTML = `
                    <h2 class="section-title">
                        <span class="porque-viste-badge">Porque viste</span>
                        ${watched.title}
                    </h2>
                    <div class="carousel porque-viste-carousel"></div>`;
                container.appendChild(sec);
                renderCarousel(reco.items.slice(0, 12), sec.querySelector('.carousel'));
            } catch { /* ignore per-item errors */ }
        }
    } catch { /* silenciar si backend sin historial */ }
}

// ── Continuar viendo ───────────────────────────────────────
function loadContinueWatching() {
    const hist = JSON.parse(localStorage.getItem('cc_history') || '[]');
    const sec  = document.getElementById('continueSection');
    const cont = document.getElementById('continueCarousel');
    if (!sec || !cont || !hist.length) return;

    // Solo los que tienen ID (m3u) o URL (rss)
    const items = hist.slice(0, 12).filter(h => h.title);
    if (!items.length) return;

    sec.style.display = '';
    cont.innerHTML = items.map(h => {
        const typeIcon = h.source === 'rss' ? '🌐' : '▶️';
        const img = h.image || PLACEHOLDER;
        return `
        <div class="movie-card continue-card" data-url="${encodeURIComponent(h.url)}"
             data-source="${h.source || 'm3u'}" data-title="${h.title}"
             data-id="${h.id || ''}" data-image="${encodeURIComponent(img)}">
            <div class="card-img-wrap">
                <img src="${img}" alt="${h.title}" loading="lazy" onerror="this.src='${PLACEHOLDER}'">
                <div class="continue-badge">${typeIcon} Continuar</div>
            </div>
            <div class="movie-info">
                <h3 class="movie-title">${h.title}</h3>
                <div class="movie-meta">
                    <span style="font-size:.68rem;color:#666">${_timeAgo(h.ts)}</span>
                </div>
            </div>
        </div>`;
    }).join('');

    // Clicks en las continue-cards
    cont.querySelectorAll('.continue-card').forEach(card => {
        card.addEventListener('click', () => {
            playStream(card.dataset.url, card.dataset.title, card.dataset.source, card.dataset.id, card.dataset.image);
        });
    });
}

function _timeAgo(ts) {
    const diff = Date.now() - ts;
    const min  = Math.floor(diff / 60000);
    if (min < 60)  return `hace ${min}m`;
    const h = Math.floor(min / 60);
    if (h < 24) return `hace ${h}h`;
    return `hace ${Math.floor(h / 24)}d`;
}

// ── Utilidad: título capitalizado (para mostrar géneros limpios) ──
function titleCase(str) {
    // El API devuelve los géneros en MAYÚSCULAS (ej: "ACCIÓN", "CLÁSICOS ANIMADOS")
    // Los mostramos en formato Título (primera letra de cada palabra en mayúscula)
    return str.toLowerCase().replace(/(?:^|[\s\-])\S/g, c => c.toUpperCase());
}

// ── Favoritos section ──────────────────────────────────────
async function showFavoritesSection() {
    const sec   = document.getElementById('favoritesSection');
    const grid  = document.getElementById('favoritesGrid');
    const empty = document.getElementById('favoritesEmpty');
    if (!sec || !grid) return;

    // Ocultar secciones principales (lista explícita para no romper nada)
    ['home', 'peliculas', 'series', 'live', 'continueSection', 'movies',
     'recoSection', 'porqueVisteContainer'].forEach(id => {
        const s = document.getElementById(id);
        if (s) s.style.display = 'none';
    });
    // Ocultar también la sección tendencias (sin id propio)
    const novedSec = document.getElementById('novedades')?.closest('section');
    if (novedSec) novedSec.style.display = 'none';
    sec.style.display = '';

    if (!state.favorites.length) {
        grid.innerHTML = '';
        if (empty) empty.style.display = '';
        return;
    }
    if (empty) empty.style.display = 'none';

    grid.innerHTML = '<p class="no-content">Cargando favoritos…</p>';

    try {
        const results = await Promise.allSettled(state.favorites.map(id => api.item(id)));
        const items = results.filter(r => r.status === 'fulfilled').map(r => r.value);
        if (!items.length) {
            grid.innerHTML = '';
            if (empty) empty.style.display = '';
            return;
        }
        grid.innerHTML = items.map(renderCard).join('');
    } catch {
        grid.innerHTML = '<p class="no-content">Error cargando favoritos</p>';
    }
}

function hideFavoritesSection() {
    const sec = document.getElementById('favoritesSection');
    if (sec) sec.style.display = 'none';
    // Siempre restaurar el grid
    const movies = document.getElementById('movies');
    if (movies) movies.style.display = '';
    // Restaurar el resto según la vista actual
    setView(state.currentType);
}

// ── Búsqueda móvil ─────────────────────────────────────────
async function performMobileSearch(q) {
    const cont = document.getElementById('mobileSearchResults');
    if (!cont) return;
    if (!q.trim()) { cont.innerHTML = ''; return; }

    cont.innerHTML = '<p class="no-content">Buscando…</p>';
    try {
        const data = await api.search(q);
        if (!data.items.length) {
            cont.innerHTML = '<p class="no-content">Sin resultados para "<em>' + q + '</em>"</p>';
        } else {
            cont.innerHTML = `<div class="movies-grid mso-grid">${data.items.map(renderCard).join('')}</div>`;
        }
    } catch {
        cont.innerHTML = '<p class="no-content">Error en la búsqueda</p>';
    }
}

// ── Inicialización ─────────────────────────────────────────
async function init() {
    el.preloader.style.display = 'flex';

    try {
        // Cargar configuración de live y secciones en paralelo
        const [liveConfig, trending, peliculas, series, liveData] = await Promise.all([
            fetch('/api/live/scan-config').then(r => r.json()).catch(() => ({})),
            api.trending(),
            api.get('contenido', { tipo: 'pelicula', page: 1, limit: 20, sort: 'year_desc' }),
            api.get('series-agrupadas', { page: 1, limit: 20, sort: 'year_desc' }),
            api.liveAgrupados({ limit: 60 }),
        ]);

        // Mostrar live según configuración del admin
        const showLiveInFrontend = liveConfig.show_in_frontend !== false;
        if (showLiveInFrontend) {
            const liveNavLinks = document.querySelectorAll('a.nav-item[data-type="live"], a[data-type="live"]');
            liveNavLinks.forEach(el => el.style.display = '');
            const liveSec = document.getElementById('live');
            if (liveSec) liveSec.style.display = '';
            const liveMobile = document.querySelectorAll('a[href="#live"]');
            liveMobile.forEach(el => el.style.display = '');
        }

        renderHero(trending);
        renderCarousel(trending, el.novedades);
        renderCarousel(peliculas.items, el.peliculasCarousel);
        renderCarousel(series.items, el.seriesCarousel);

        // Canales en directo agrupados (la API devuelve un array directamente)
        state.liveGroups = Array.isArray(liveData) ? liveData : [];
        if (el.liveCarousel) {
            el.liveCarousel.innerHTML = state.liveGroups.length
                ? state.liveGroups.map((g, i) => renderLiveGroupCard(g, i)).join('')
                : '<p class="no-content">Sin canales disponibles</p>';
        }

        // Grid principal y filtros
        await Promise.all([loadGrid(), loadFilters()]);

        // Secciones adicionales (en paralelo, no bloquean el init)
        loadContinueWatching();
        loadRecomendaciones();
        loadGenrePills();
        loadLiveListas();

        setupEvents();
    } catch (err) {
        console.error('Error init:', err);
        el.preloader.innerHTML = `
            <div style="text-align:center;color:#fff">
                <h3>Error al conectar con el servidor</h3>
                <p style="color:#aaa">${err.message}</p>
                <button onclick="location.reload()"
                        style="background:#e50914;border:none;color:#fff;padding:.6rem 1.2rem;border-radius:6px;cursor:pointer">
                    Reintentar
                </button>
            </div>`;
        return;
    }

    // Ocultar preloader
    setTimeout(() => {
        el.preloader.style.opacity = '0';
        el.preloader.style.transition = 'opacity .4s';
        setTimeout(() => { el.preloader.style.display = 'none'; }, 400);
    }, 800);
}

// Animación slideIn + estilos dinámicos del reproductor
const _style = document.createElement('style');
_style.textContent = `
    @keyframes slideIn {
        from { transform:translateX(110%); opacity:0; }
        to   { transform:translateX(0);    opacity:1; }
    }
    /* Badge rojo "🔴 LIVE" sobre las tarjetas de canales en directo */
    .live-badge {
        position:absolute; top:6px; left:6px; z-index:2;
        background:rgba(229,51,51,.88); color:#fff;
        font-size:.6rem; font-weight:700; padding:.15rem .4rem;
        border-radius:3px; letter-spacing:.06em; pointer-events:none;
        text-shadow:0 1px 2px rgba(0,0,0,.5);
    }
`;
document.head.appendChild(_style);

// ── Heartbeat: actualiza presencia del usuario en el servidor cada 30s ─────
(function startHeartbeat() {
    const hb = () => fetch('/api/heartbeat', { method: 'POST' }).catch(() => {});
    hb();
    setInterval(hb, 30_000);
})();

document.addEventListener('DOMContentLoaded', init);
