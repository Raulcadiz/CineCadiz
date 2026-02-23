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
    series:    (page = 1) => api.get('contenido', { tipo: 'serie',    page, limit: 12 }),
    live:      (page = 1) => api.get('contenido', { tipo: 'live',     page, limit: 12 }),
    generos:   ()         => api.get('generos'),
    años:      ()         => api.get('anos'),   // endpoint sin tilde
    stats:     ()         => api.get('stats'),

    search: (q) => api.get('contenido', { q, limit: 8 }),

    contenido: (params) => api.get('contenido', params),

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
        <img src="${imgSrc}"
             alt="${item.title}"
             loading="lazy"
             onerror="this.src='${PLACEHOLDER}'">
        ${isRss ? '<span class="rss-badge">WEB</span>' : ''}
        <div class="movie-info">
            <h3 class="movie-title">${item.title}</h3>
            <div class="movie-meta">
                <span>${item.year || ''}</span>
                <span>${typeIcon}</span>
                ${epBadge}
            </div>
        </div>
        <div class="movie-overlay">
            <button class="btn-watch"
                    data-stream="${encodeURIComponent(item.streamUrl)}"
                    data-source="${item.source || 'm3u'}"
                    data-title="${item.title}"
                    data-id="${item.id}">
                ${playLabel}
            </button>
            <button class="btn-favorite ${fav ? 'active' : ''}" data-fav="${item.id}">
                <i class="bi ${fav ? 'bi-heart-fill' : 'bi-heart'}"></i>
            </button>
            <p class="movie-genres">${(item.genres || []).slice(0,2).join(', ') || 'Sin género'}</p>
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
                 style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.4"
                 onerror="this.style.display='none'">
            <div class="hero-content">
                <h1 class="hero-title">${item.title}</h1>
                <p class="hero-description">${item.year || ''} &bull; ${(item.genres||[]).slice(0,2).join(', ')}</p>
                <div class="hero-buttons">
                    <button class="btn-play" data-stream="${encodeURIComponent(item.streamUrl)}"
                            data-source="${item.source || 'm3u'}"
                            data-title="${item.title}"
                            data-id="${item.id}">
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
                                data-id="${item.id}">
                            ${item.source === 'rss'
                                ? '<i class="bi bi-box-arrow-up-right"></i> Abrir en web'
                                : '<i class="bi bi-play-fill"></i> Reproducir'}
                        </button>
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

// ── Reproductor ────────────────────────────────────────────
let _hls = null;   // instancia HLS.js activa

/**
 * Destruye la instancia HLS anterior antes de cargar un nuevo stream.
 */
function _destroyHls() {
    if (_hls) {
        _hls.destroy();
        _hls = null;
    }
    el.videoPlayer.removeAttribute('src');
    el.videoPlayer.onerror = null;
    el.player?.querySelectorAll('.player-error').forEach(e => e.remove());
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

/** Carga un stream HLS con HLS.js. */
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
            _showPlayerError('Stream HLS no disponible — puede ser un problema de CORS o el stream expiró');
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
function playStream(streamUrl, title, source, itemId = '') {
    const url = decodeURIComponent(streamUrl);

    // Historial local
    let hist = JSON.parse(localStorage.getItem('cc_history') || '[]');
    hist = hist.filter(h => h.url !== url).slice(0, 49);
    hist.unshift({ url, title, source, ts: Date.now() });
    localStorage.setItem('cc_history', JSON.stringify(hist));

    // RSS → nueva pestaña (cinemacity.cc bloquea iframe)
    if (source === 'rss') {
        window.open(url, '_blank', 'noopener,noreferrer');
        return;
    }

    _destroyHls();
    el.player.style.display = 'flex';
    document.getElementById('playerTitle').textContent = title || '';
    el.player.dataset.streamUrl = url;
    el.player.dataset.itemId    = itemId;

    // Restaurar volumen guardado
    const vol = parseFloat(localStorage.getItem('cc_volume') || '1');
    if (!isNaN(vol)) el.videoPlayer.volume = Math.max(0, Math.min(1, vol));

    // ── Paso 1: HLS.js directo (igual que la versión original que funcionaba) ──
    if (typeof Hls !== 'undefined' && Hls.isSupported()) {
        _loadHlsDirect(url);
    } else if (el.videoPlayer.canPlayType('application/vnd.apple.mpegurl')) {
        // Safari: HLS nativo
        el.videoPlayer.src = url;
        el.videoPlayer.play().catch(() => {});
    } else {
        // Navegador sin soporte HLS → ir directo a nativo
        _tryNative(url);
    }
}

/**
 * Paso 1 — HLS.js directo (reproducción original que funcionaba).
 * Detecta si el stream es HLS inspeccionando el contenido (no la URL).
 * Si falla por red/CORS → pasa por hls-proxy del VPS.
 * Si falla por parseo   → no es HLS, prueba como vídeo nativo.
 */
function _loadHlsDirect(url) {
    _hls = new Hls({
        maxBufferLength: 30,
        maxBufferSize:   60 * 1000 * 1000,
        xhrSetup: xhr => { xhr.withCredentials = false; },
    });
    _hls.loadSource(url);
    _hls.attachMedia(el.videoPlayer);
    _hls.on(Hls.Events.MANIFEST_PARSED, () => {
        el.videoPlayer.play().catch(() => {});
    });
    _hls.on(Hls.Events.ERROR, (_, data) => {
        if (!data.fatal) return;
        _destroyHls();
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
            // CORS u otro error de red → intentar a través del proxy del VPS
            _loadHls(`/api/hls-proxy?url=${encodeURIComponent(url)}`);
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
            // Paso 5: todo falló
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
            };
            el.gridTitle.textContent = titles[state.currentType] || '🎬 Todo el contenido';
        }
    }

    try {
        const data = await api.contenido({
            tipo:   state.currentType,
            año:    state.currentYear,
            genero: state.currentGenre,
            page:   state.currentPage,
            limit:  24,
        });

        renderGrid(data.items, append);

        const hasMore = state.currentPage < data.pages;
        el.loadMore.style.display = hasMore ? 'block' : 'none';
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
        generos.slice(0, 40).forEach(g => {
            const o = document.createElement('option');
            o.value = g; o.textContent = g;
            el.genreFilter.appendChild(o);
        });
    } catch { /* silenciar */ }
}

// ── Eventos ────────────────────────────────────────────────
function setupEvents() {
    // Delegación de clicks en cards / botones
    document.addEventListener('click', e => {
        // Click en tarjeta → abrir detalles
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

        // Cerrar modal
        if (e.target === el.detailsModal || e.target.classList.contains('close-modal')) {
            el.detailsModal.style.display = 'none';
        }
    });

    // Cerrar reproductor — botón ×
    document.querySelector('.btn-close-player')?.addEventListener('click', () => {
        el.videoPlayer.pause();
        _destroyHls();
        el.player.style.display = 'none';
    });

    // Cerrar reproductor — click en la zona negra fuera del vídeo
    el.player?.addEventListener('click', e => {
        if (e.target === el.player || e.target.classList.contains('player-body')) {
            el.videoPlayer.pause();
            _destroyHls();
            el.player.style.display = 'none';
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

    // Cargar más
    el.loadMore?.addEventListener('click', () => {
        state.currentPage++;
        loadGrid(true);
    });

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
                    break;
            }
        } else if (!playerOpen && e.key === 'Escape') {
            el.detailsModal.style.display = 'none';
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

    // ── Navegación con filtro de tipo (Películas / Series) ──
    document.querySelectorAll('a[data-type]').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            const type = link.dataset.type;
            state.currentType = type;
            state.currentPage  = 1;
            if (el.typeFilter) el.typeFilter.value = type;
            loadGrid();
            document.getElementById('movies')?.scrollIntoView({ behavior: 'smooth' });
            document.querySelectorAll('.nav-item, .desktop-nav a').forEach(n => n.classList.remove('active'));
            document.querySelectorAll(`a[data-type="${type}"]`).forEach(n => n.classList.add('active'));
        });
    });

    // ── Inicio: resetear filtro y volver arriba ──────────────
    document.querySelectorAll('a[href="#home"]').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            state.currentType  = '';
            state.currentPage  = 1;
            state.currentYear  = '';
            state.currentGenre = '';
            if (el.typeFilter)  el.typeFilter.value  = '';
            if (el.yearFilter)  el.yearFilter.value  = '';
            if (el.genreFilter) el.genreFilter.value = '';
            loadGrid();
            document.getElementById('home')?.scrollIntoView({ behavior: 'smooth' });
            document.querySelectorAll('.nav-item, .desktop-nav a').forEach(n => n.classList.remove('active'));
            document.querySelectorAll('a[href="#home"]').forEach(n => n.classList.add('active'));
        });
    });

    // ── Novedades: scroll a la sección ───────────────────────
    document.querySelectorAll('a[href="#novedades"]').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            document.getElementById('novedades')?.scrollIntoView({ behavior: 'smooth' });
        });
    });

    // Navegación móvil — active state para links sin filtro (Buscar, Favoritos)
    document.querySelectorAll('.mobile-nav .nav-item:not([data-type]):not([href="#home"])').forEach(item => {
        item.addEventListener('click', () => {
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            item.classList.add('active');
        });
    });
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

// Estilos de notificación (inline para no depender de CSS adicional)
const _style = document.createElement('style');
_style.textContent = `
    @keyframes slideIn { from { transform:translateX(120%);opacity:0 } to { transform:translateX(0);opacity:1 } }
    .no-content { text-align:center;padding:2rem;color:#666;font-style:italic }
    .badge-ep { background:#333;color:#aaa;font-size:.7rem;padding:.15rem .4rem;border-radius:4px }
    /* Badge RSS en tarjetas */
    .rss-badge {
        position:absolute;top:8px;left:8px;
        background:rgba(229,9,20,.85);color:#fff;
        font-size:.65rem;font-weight:700;padding:.1rem .4rem;
        border-radius:4px;letter-spacing:.04em;z-index:2;
    }
    .movie-card { position:relative }
    .modal { display:none;position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:1000;align-items:center;justify-content:center }
    /* ── Player ── */
    .player { display:none;position:fixed;inset:0;background:#000;z-index:2000;flex-direction:column }
    .player-header {
        display:flex;align-items:center;gap:.5rem;
        padding:.35rem .7rem;background:rgba(0,0,0,.7);flex-shrink:0;
    }
    #playerTitle { color:#fff;font-size:.9rem;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap }
    .player-esc-hint { color:rgba(255,255,255,.35);font-size:.72rem;white-space:nowrap }
    .btn-close-player {
        background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.28);
        color:#fff;font-size:1.1rem;cursor:pointer;
        padding:.2rem .75rem;border-radius:6px;line-height:1.5;
        transition:background .2s;flex-shrink:0;
    }
    .btn-close-player:hover { background:rgba(255,255,255,.28); }
    .player-body { flex:1;display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden }
    .player-body video { max-width:100%;max-height:100%;width:100%;height:100%;object-fit:contain;z-index:1 }
    /* Barra inferior del player */
    .player-footer { background:rgba(0,0,0,.7);padding:.35rem .7rem .4rem;flex-shrink:0 }
    .player-actions { display:flex;gap:.4rem;align-items:center;flex-wrap:wrap;margin-bottom:.25rem }
    .btn-pa {
        background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);
        color:#fff;cursor:pointer;padding:.18rem .65rem;border-radius:5px;
        font-size:.78rem;line-height:1.5;transition:background .15s;
    }
    .btn-pa:hover { background:rgba(255,255,255,.22); }
    select.btn-pa option { background:#1a1a1a;color:#fff }
    .player-keys { color:rgba(255,255,255,.28);font-size:.66rem;margin:0 }
    .player-keys kbd {
        background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.18);
        padding:.02rem .28rem;border-radius:3px;font-size:.65rem;
    }
    /* Overlay de error dentro del reproductor */
    .player-error {
        position:absolute;inset:0;z-index:5;
        display:flex;flex-direction:column;align-items:center;justify-content:center;
        background:rgba(0,0,0,.82);color:#fff;text-align:center;padding:2rem;
    }
    .err-btn {
        background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.28);
        color:#fff;cursor:pointer;padding:.42rem 1.1rem;border-radius:7px;
        font-size:.88rem;transition:background .2s;
    }
    .err-btn:hover { background:rgba(255,255,255,.26); }
    .err-btn-primary { background:#e50914;border-color:#e50914; }
    .err-btn-primary:hover { background:#c0070f; }
`;
document.head.appendChild(_style);

document.addEventListener('DOMContentLoaded', init);
