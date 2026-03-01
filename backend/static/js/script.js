// ╔══════════════════════════════════════════════════════════╗
// ║  CineCadiz — Frontend JS                                ║
// ║  Consume la API Flask en /api/                          ║
// ╚══════════════════════════════════════════════════════════╝

// Placeholder SVG inline — nunca genera 404
const PLACEHOLDER = '/static/images/placeholder.svg';

// ── Estado global ──────────────────────────────────────────
const state = {
    currentPage: 1,
    currentType: '',
    currentYear: '',
    currentGenre: '',
    currentSort: 'recent',
    favorites: JSON.parse(localStorage.getItem('cc_favorites') || '[]'),
    allItems: [],           // caché local para búsqueda rápida
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
    peliculas: (page = 1) => api.get('contenido', { tipo: 'pelicula', page, limit: 12 }),
    series:    (page = 1) => api.get('series-agrupadas', { page, limit: 12 }),
    live:      (page = 1) => api.get('contenido', { tipo: 'live',     page, limit: 12 }),
    generos:   ()         => api.get('generos'),
    años:      ()         => api.get('anos'),   // endpoint sin tilde
    stats:     ()         => api.get('stats'),

    search: (q) => api.get('contenido', { q, limit: 8 }),

    contenido: (params) => api.get('contenido', params),
    seriesAgrupadas: (params) => api.get('series-agrupadas', params),
    serieEpisodios: (titulo) => api.get('serie-episodios', { titulo }),

    item: (id) => api.get(`contenido/${id}`),
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

    const isRss = item.source === 'rss';
    const playLabel = isRss
        ? '<i class="bi bi-box-arrow-up-right"></i> Abrir'
        : '<i class="bi bi-play-fill"></i> Ver';

    const imgSrc = getImageUrl(item);

    return `
    <div class="movie-card" data-id="${item.id}">
        <div class="card-img-wrap">
            <img src="${imgSrc}"
                 alt="${item.title}"
                 loading="lazy"
                 onerror="this.src='${PLACEHOLDER}'">
            ${isRss ? '<span class="rss-badge">WEB</span>' : ''}
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
                    data-image="${encodeURIComponent(imgSrc)}">
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
                                data-image="${encodeURIComponent(modalImg)}">
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
                );
            });
        });

    } catch (err) {
        console.error('showSeriesDetail error:', err);
        body.innerHTML = '<p class="no-content" style="padding:2rem">Error al cargar los episodios.</p>';
    }
}

// ── Reproductor ────────────────────────────────────────────
let _hls = null;   // instancia HLS.js activa

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
 * Destruye la instancia HLS y cancela cualquier descarga activa del video.
 */
function _destroyHls() {
    if (_hls) {
        _hls.destroy();
        _hls = null;
    }
    el.videoPlayer.pause();
    el.videoPlayer.removeAttribute('src');
    el.videoPlayer.load();   // cancela la descarga HTTP en curso
    el.videoPlayer.onerror = null;
    el.player?.querySelectorAll('.player-error').forEach(e => e.remove());
    _setPlayerLoading(false);
}

/** Muestra overlay de error dentro del reproductor con opciones de acción. */
function _showPlayerError(msg) {
    el.player?.querySelectorAll('.player-error').forEach(e => e.remove());
    const itemId  = el.player?.dataset.itemId  || '';
    const rawUrl  = el.player?.dataset.streamUrl || '';
    const errDiv  = document.createElement('div');
    errDiv.className = 'player-error';
    errDiv.innerHTML = `
        <div style="font-size:2.5rem;margin-bottom:.7rem">⚠️</div>
        <p style="margin:.3rem 0;font-size:1rem">${msg}</p>
        <p style="color:#999;font-size:.8rem;margin-top:.3rem;margin-bottom:1.2rem">
          El stream puede haber expirado o el formato no es compatible con el navegador.
        </p>
        <div style="display:flex;gap:.6rem;flex-wrap:wrap;justify-content:center">
            ${itemId ? `
            <button class="err-btn err-btn-primary" data-action="open-vlc" data-id="${itemId}">
                📺 Abrir en VLC / Kodi
            </button>` : ''}
            <button class="err-btn" data-action="copy-url">
                📋 Copiar enlace
            </button>
            <button class="err-btn" data-action="try-hls">
                🔄 Intentar HLS
            </button>
        </div>`;

    // Listeners de los botones de error
    errDiv.querySelectorAll('[data-action]').forEach(btn => {
        btn.addEventListener('click', e => {
            e.stopPropagation();
            const action = btn.dataset.action;
            if (action === 'open-vlc') {
                window.open(`/api/playlist/${btn.dataset.id}.m3u`, '_blank');
            } else if (action === 'copy-url') {
                navigator.clipboard?.writeText(rawUrl)
                    .then(() => showNotification('Enlace copiado'))
                    .catch(() => showNotification('No se pudo copiar', 'error'));
            } else if (action === 'try-hls') {
                _destroyHls();
                _loadHls(`/api/hls-proxy?url=${encodeURIComponent(rawUrl)}`);
            }
        });
    });

    el.player?.querySelector('.player-body')?.appendChild(errDiv);
}

/** Carga un stream HLS con HLS.js (vía proxy). Si falla, cae a native. */
function _loadHls(url) {
    _hls = new Hls({
        maxBufferLength:   30,
        maxBufferSize:     60 * 1000 * 1000,
        xhrSetup: (xhr) => { xhr.withCredentials = false; },
    });
    _hls.loadSource(url);
    _hls.attachMedia(el.videoPlayer);
    _hls.on(Hls.Events.MANIFEST_PARSED, () => {
        el.videoPlayer.play().catch(() => {});
    });
    _hls.on(Hls.Events.ERROR, (_e, data) => {
        if (data.fatal) {
            _destroyHls();
            // El proxy también falló → último recurso: reproducción nativa HTML5
            const originalUrl = el.player.dataset.streamUrl;
            if (originalUrl) {
                _tryNative(originalUrl);
            } else {
                _showPlayerError('Stream HLS no disponible — puede ser un problema de CORS o el stream expiró');
            }
        }
    });
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
 *   5. Todo falla        → overlay con botones VLC / copiar / intentar HLS
 */
function playStream(streamUrl, title, source, itemId = '', image = '') {
    const url = decodeURIComponent(streamUrl);
    const imgDecoded = image ? decodeURIComponent(image) : '';

    // Historial local
    let hist = JSON.parse(localStorage.getItem('cc_history') || '[]');
    hist = hist.filter(h => h.url !== url).slice(0, 49);
    hist.unshift({ url, title, source, ts: Date.now(), id: itemId, image: imgDecoded });
    localStorage.setItem('cc_history', JSON.stringify(hist));

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
    el.player.dataset.streamUrl = url;
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

    // Restaurar volumen guardado
    const vol = parseFloat(localStorage.getItem('cc_volume') || '1');
    if (!isNaN(vol)) el.videoPlayer.volume = Math.max(0, Math.min(1, vol));

    // ── Paso 1: decidir si usar HLS.js o ir directo a nativo ──
    if (typeof Hls !== 'undefined' && Hls.isSupported() && _isLikelyHls(url)) {
        // URL parece HLS (m3u8 o sin extensión clara) → intentar HLS.js
        _loadHlsDirect(url);
    } else if (el.videoPlayer.canPlayType('application/vnd.apple.mpegurl') && _isLikelyHls(url)) {
        // Safari con URL HLS → HLS nativo
        el.videoPlayer.src = url;
        el.videoPlayer.play().catch(() => {});
    } else {
        // URL es .mkv/.mp4/etc. o navegador sin soporte HLS → nativo directo
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
    // Extensiones definitivamente NO-HLS → nativo directo
    const NON_HLS = ['.mkv', '.mp4', '.avi', '.mov', '.webm', '.flv', '.wmv', '.mpg', '.mpeg'];
    if (NON_HLS.some(ext => path.endsWith(ext))) return false;
    // Extensión HLS confirmada
    if (path.endsWith('.m3u8') || path.includes('.m3u8?')) return true;
    // Sin extensión conocida (IPTV, streams de IPTV sin extensión) → intentar HLS
    return true;
}

/**
 * Paso 1 — HLS.js directo.
 * Para URLs IPTV live que acaban en .ts, prueba primero la variante .m3u8
 * (la mayoría de servidores IPTV sirven el mismo canal en ambos formatos).
 * Si falla por red/CORS → proxy del VPS.
 * Si falla por parseo   → no es HLS, prueba como vídeo nativo .ts.
 */
function _loadHlsDirect(url) {
    // Para canales live con .ts: intentar el manifest HLS (.m3u8) del mismo servidor
    const urlLow = url.toLowerCase().split('?')[0];
    const hlsUrl = (urlLow.endsWith('.ts') && urlLow.includes('/live/'))
        ? url.replace(/\.ts(\?.*)?$/i, '.m3u8')
        : url;

    _hls = new Hls({
        maxBufferLength: 30,
        maxBufferSize:   60 * 1000 * 1000,
        xhrSetup: xhr => { xhr.withCredentials = false; },
    });
    _hls.loadSource(hlsUrl);
    _hls.attachMedia(el.videoPlayer);
    _hls.on(Hls.Events.MANIFEST_PARSED, () => {
        el.videoPlayer.play().catch(() => {});
    });
    _hls.on(Hls.Events.ERROR, (_, data) => {
        if (!data.fatal) return;
        _destroyHls();
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
            // CORS u otro error de red → intentar a través del proxy del VPS
            _loadHls(`/api/hls-proxy?url=${encodeURIComponent(hlsUrl)}`);
        } else {
            // Error de parseo: el stream no es HLS → probar como vídeo nativo
            _tryNative(url);
        }
    });
}

/**
 * Paso 3 — Reproducción nativa (<video src>).
 * Funciona para MP4, MKV con H.264/AAC, WebM, etc.
 * Si el navegador no puede reproducirlo → intenta a través del stream-proxy.
 */
function _tryNative(url) {
    el.videoPlayer.onerror = null;
    el.videoPlayer.src = url;
    el.videoPlayer.load();
    el.videoPlayer.play().catch(() => {});
    el.videoPlayer.onerror = () => {
        el.videoPlayer.onerror = null;
        // Paso 4: a través del stream-proxy del VPS
        el.videoPlayer.src = `/api/stream-proxy?url=${encodeURIComponent(url)}`;
        el.videoPlayer.load();
        el.videoPlayer.play().catch(() => {});
        el.videoPlayer.onerror = () => {
            el.videoPlayer.onerror = null;
            // Paso 5: todo falló — limpiar spinner y mostrar error
            _setPlayerLoading(false);
            _showPlayerError('Stream no disponible o formato no compatible con el navegador');
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

    try {
        let data;
        if (state.currentType === 'serie') {
            // Series → mostrar agrupadas por título (una tarjeta por serie)
            data = await api.seriesAgrupadas({
                genero: state.currentGenre,
                sort:   state.currentSort === 'recent' ? 'recent' : 'title_asc',
                page:   state.currentPage,
                limit:  24,
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
                limit:  24,
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
    const nov2026Sec = document.getElementById('novedades2026Section');
    const contSec    = document.getElementById('continueSection');

    if (!type) {
        // Vista inicio: mostrar todo
        [hero, novedSec, pelSec, serSec, liveSec, nov2026Sec].forEach(s => {
            if (s) s.style.display = '';
        });
        // continueSection solo si hay historial
        if (contSec) {
            const hist = JSON.parse(localStorage.getItem('cc_history') || '[]');
            contSec.style.display = hist.length ? '' : 'none';
        }
        window.scrollTo({ top: 0, behavior: 'smooth' });
    } else {
        // Vista de tipo: ocultar hero, novedades y TODOS los carruseles.
        // El grid (#movies) muestra el contenido completo del tipo seleccionado.
        [hero, novedSec, nov2026Sec, contSec, pelSec, serSec, liveSec].forEach(s => {
            if (s) s.style.display = 'none';
        });
        document.getElementById('movies')?.scrollIntoView({ behavior: 'smooth' });
    }
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
            playStream(
                playBtn.dataset.stream,
                playBtn.dataset.title,
                playBtn.dataset.source || 'm3u',
                playBtn.dataset.id || '',
                playBtn.dataset.image || '',
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
            const sm = document.getElementById('seriesModal');
            if (sm) sm.style.display = 'none';
            return;
        }
        if (e.target === el.detailsModal) {
            el.detailsModal.style.display = 'none';
        }
        const sm = document.getElementById('seriesModal');
        if (sm && e.target === sm) {
            sm.style.display = 'none';
        }
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
            const sm = document.getElementById('seriesModal');
            if (sm) sm.style.display = 'none';
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

    // Abrir en app (descarga .m3u → VLC/Kodi lo abre automáticamente)
    document.getElementById('btnOpenApp')?.addEventListener('click', () => {
        const id  = el.player.dataset.itemId || '';
        const url = el.player.dataset.streamUrl || '';
        if (id) {
            window.open(`/api/playlist/${id}.m3u`, '_blank');
        } else if (url) {
            // Fallback: crear .m3u en memoria y descargar
            const blob = new Blob([`#EXTM3U\n#EXTINF:-1,Stream\n${url}\n`], { type: 'audio/x-mpegurl' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'stream.m3u';
            a.click();
        }
    });

    // Copiar enlace
    document.getElementById('btnCopyUrl')?.addEventListener('click', () => {
        const url = el.player.dataset.streamUrl || '';
        navigator.clipboard?.writeText(url)
            .then(() => showNotification('Enlace copiado al portapapeles'))
            .catch(() => {
                const inp = document.createElement('input');
                inp.value = url;
                document.body.appendChild(inp);
                inp.select(); document.execCommand('copy'); inp.remove();
                showNotification('Enlace copiado');
            });
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
            // Resetear filtros al cambiar de tipo para evitar grids vacíos
            state.currentYear  = '';
            state.currentGenre = '';
            state.currentSort  = 'recent';
            if (el.typeFilter)  el.typeFilter.value  = type;
            if (el.yearFilter)  el.yearFilter.value  = '';
            if (el.genreFilter) el.genreFilter.value = '';
            const sf = document.getElementById('sortFilter');
            if (sf) sf.value = 'recent';
            document.querySelectorAll('.genre-pill').forEach(p => p.classList.remove('active'));
            setView(type);     // ocultar hero, novedades y carruseles; mostrar sólo el grid
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
            state.currentSort  = 'recent';
            if (el.typeFilter)  el.typeFilter.value  = '';
            if (el.yearFilter)  el.yearFilter.value  = '';
            if (el.genreFilter) el.genreFilter.value = '';
            const sf = document.getElementById('sortFilter');
            if (sf) sf.value = 'recent';
            document.querySelectorAll('.genre-pill').forEach(p => p.classList.remove('active'));
            hideFavoritesSection();
            setView('');       // restaurar todas las secciones
            loadGrid();
            document.querySelectorAll('.nav-item, .desktop-nav a').forEach(n => n.classList.remove('active'));
            document.querySelectorAll('a[href="#home"]').forEach(n => n.classList.add('active'));
        });
    });

    // ── Novedades: resetea vista y muestra tendencias ─────────
    document.querySelectorAll('a[href="#novedades"], #novedadesNavLink').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            // Asegurarse de que la vista home esté activa (puede estar en películas/series)
            state.currentType  = '';
            state.currentPage  = 1;
            state.currentYear  = '';
            state.currentGenre = '';
            if (el.typeFilter)  el.typeFilter.value  = '';
            if (el.yearFilter)  el.yearFilter.value  = '';
            if (el.genreFilter) el.genreFilter.value = '';
            hideFavoritesSection();
            setView('');
            // Scroll a la sección tendencias
            setTimeout(() => {
                const sec = document.getElementById('novedades')?.closest('section');
                if (sec) sec.scrollIntoView({ behavior: 'smooth' });
            }, 120);
            document.querySelectorAll('.nav-item, .desktop-nav a').forEach(n => n.classList.remove('active'));
        });
    });

    // ── Géneros: scroll a la sección de pills ─────────────────
    document.getElementById('generosNavLink')?.addEventListener('click', e => {
        e.preventDefault();
        state.currentType  = '';
        if (el.typeFilter) el.typeFilter.value = '';
        hideFavoritesSection();
        setView('');
        setTimeout(() => {
            const wrap = document.getElementById('genrePillsWrap');
            if (wrap) {
                wrap.style.display = '';
                wrap.scrollIntoView({ behavior: 'smooth' });
            } else {
                document.getElementById('movies')?.scrollIntoView({ behavior: 'smooth' });
            }
        }, 120);
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

    // ── Ver todas 2026 ────────────────────────────────────────
    document.getElementById('ver2026Link')?.addEventListener('click', e => {
        e.preventDefault();
        state.currentType  = '';
        state.currentYear  = '2026';
        state.currentPage  = 1;
        state.currentGenre = '';
        if (el.yearFilter)  el.yearFilter.value  = '2026';
        if (el.typeFilter)  el.typeFilter.value  = '';
        if (el.genreFilter) el.genreFilter.value = '';
        hideFavoritesSection();
        setView('');
        loadGrid();
        document.getElementById('movies')?.scrollIntoView({ behavior: 'smooth' });
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

    // ── Pills de género ───────────────────────────────────────
    document.getElementById('genrePills')?.addEventListener('click', e => {
        const pill = e.target.closest('.genre-pill');
        if (!pill) return;
        const genre = pill.dataset.genre;
        // Toggle: si ya está activo, limpia; si no, filtra
        const isActive = pill.classList.contains('active');
        document.querySelectorAll('.genre-pill').forEach(p => p.classList.remove('active'));
        state.currentGenre = isActive ? '' : genre;
        if (el.genreFilter) el.genreFilter.value = state.currentGenre;
        if (!isActive) pill.classList.add('active');
        state.currentPage = 1;
        loadGrid();
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

// ── Novedades 2026 ─────────────────────────────────────────
async function loadNovedades2026() {
    try {
        const data = await api.contenido({ año: 2026, limit: 20 });
        const cont = document.getElementById('novedades2026Carousel');
        const sec  = document.getElementById('novedades2026Section');
        if (!cont) return;
        if (!data.items || !data.items.length) {
            if (sec) sec.style.display = 'none';
            return;
        }
        renderCarousel(data.items, cont);
    } catch { /* silenciar */ }
}

// ── Utilidad: título capitalizado (para mostrar géneros limpios) ──
function titleCase(str) {
    // El API devuelve los géneros en MAYÚSCULAS (ej: "ACCIÓN", "CLÁSICOS ANIMADOS")
    // Los mostramos en formato Título (primera letra de cada palabra en mayúscula)
    return str.toLowerCase().replace(/(?:^|[\s\-])\S/g, c => c.toUpperCase());
}

// ── Genre Pills ────────────────────────────────────────────
async function loadGenrePills() {
    try {
        const generos = await api.generos();
        const wrap  = document.getElementById('genrePillsWrap');
        const pills = document.getElementById('genrePills');
        if (!wrap || !pills || !generos.length) return;

        // Mostrar solo los primeros 20 géneros más comunes (ya vienen del API)
        const top = generos.slice(0, 20);
        // data-genre almacena el valor RAW (en mayúsculas) que se envía a la API para filtrar.
        // El texto visible se convierte a Título para una presentación más limpia.
        pills.innerHTML = top.map(g =>
            `<button class="genre-pill" data-genre="${g}">${titleCase(g)}</button>`
        ).join('');
        wrap.style.display = '';
    } catch { /* silenciar */ }
}

// ── Favoritos section ──────────────────────────────────────
async function showFavoritesSection() {
    const sec   = document.getElementById('favoritesSection');
    const grid  = document.getElementById('favoritesGrid');
    const empty = document.getElementById('favoritesEmpty');
    if (!sec || !grid) return;

    // Ocultar secciones principales (lista explícita para no romper nada)
    ['home', 'peliculas', 'series', 'live', 'novedades2026Section',
     'continueSection', 'movies'].forEach(id => {
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
        // Cargar secciones en paralelo
        const [trending, peliculas, series, live] = await Promise.all([
            api.trending(),
            api.peliculas(1),
            api.series(1),
            api.live(1),
        ]);

        renderHero(trending);
        renderCarousel(trending, el.novedades);
        renderCarousel(peliculas.items, el.peliculasCarousel);
        renderCarousel(series.items, el.seriesCarousel);
        renderCarousel(live.items, el.liveCarousel);

        // Grid principal y filtros
        await Promise.all([loadGrid(), loadFilters()]);

        // Secciones adicionales (en paralelo, no bloquean el init)
        loadContinueWatching();
        loadNovedades2026();
        loadGenrePills();

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

// Animación slideIn para notificaciones (no se puede poner en CSS estático fácilmente)
const _style = document.createElement('style');
_style.textContent = `
    @keyframes slideIn {
        from { transform:translateX(110%); opacity:0; }
        to   { transform:translateX(0);    opacity:1; }
    }
`;
document.head.appendChild(_style);

document.addEventListener('DOMContentLoaded', init);
