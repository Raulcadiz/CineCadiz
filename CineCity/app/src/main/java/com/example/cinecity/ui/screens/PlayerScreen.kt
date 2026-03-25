package com.example.cinecity.ui.screens

import android.app.Activity
import android.content.pm.ActivityInfo
import android.net.Uri
import android.view.KeyEvent as AndroidKeyEvent
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.*
import androidx.compose.foundation.focusable
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.Tracks
import androidx.media3.common.TrackSelectionOverride
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.PlayerView
import com.example.cinecity.data.WatchProgress
import com.example.cinecity.data.WatchProgressManager
import com.example.cinecity.data.api.ApiClient
import com.example.cinecity.data.model.Contenido
import com.example.cinecity.data.model.LiveServer
import com.example.cinecity.data.repository.ContentRepository
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

// ── Datos de pistas de audio / subtítulos ─────────────────────
private data class AudioTrackInfo(
    val groupIndex: Int,
    val label: String,
    val selected: Boolean,
)

private data class SubtitleTrackInfo(
    val groupIndex: Int,
    val label: String,
    val selected: Boolean,
)

// ── Formateador de tiempo ──────────────────────────────────────
private fun Long.toTimeString(): String {
    val totalSecs = this / 1_000
    val hours = totalSecs / 3600
    val minutes = (totalSecs % 3600) / 60
    val seconds = totalSecs % 60
    return if (hours > 0) "%d:%02d:%02d".format(hours, minutes, seconds)
    else "%d:%02d".format(minutes, seconds)
}

// ══════════════════════════════════════════════════════════════
// PlayerScreen
// ══════════════════════════════════════════════════════════════

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlayerScreen(
    item: Contenido,
    episodeList: List<Contenido> = emptyList(),
    episodeIndex: Int = -1,
    seriesTitle: String? = null,
    onBack: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // ── Estado del episodio ───────────────────────────────────
    var currentItem by remember { mutableStateOf(item) }
    var currentEpisodeIndex by remember { mutableIntStateOf(episodeIndex) }
    val hasNextEpisode = episodeList.isNotEmpty()
        && currentEpisodeIndex >= 0
        && currentEpisodeIndex < episodeList.size - 1

    // ── Forzar landscape ──────────────────────────────────────
    DisposableEffect(Unit) {
        val activity = context as? Activity
        activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        onDispose {
            activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
        }
    }

    // ── Live failover state ───────────────────────────────────
    var liveActiveUrl by remember(currentItem) { mutableStateOf(currentItem.streamUrl) }
    var liveFailoverTried by remember(currentItem) { mutableStateOf(false) }
    var liveHlsFallbackTried by remember(currentItem) { mutableStateOf(false) }
    var liveUnavailable by remember(currentItem) { mutableStateOf(false) }

    // ── Server picker state ───────────────────────────────────
    val liveUrls = currentItem.liveUrls
    val hasMultipleServers = currentItem.type == "live" && (liveUrls?.size ?: 0) > 1
    var showServerPicker by remember { mutableStateOf(false) }
    var servers by remember(currentItem) { mutableStateOf<List<LiveServer>>(emptyList()) }
    var serversLoading by remember(currentItem) { mutableStateOf(false) }

    // ── URL del stream ────────────────────────────────────────
    val streamUrl = remember(currentItem, liveActiveUrl) {
        ApiClient.streamUrl(
            if (currentItem.type == "live") liveActiveUrl else currentItem.streamUrl
        )
    }

    // ── Estado de error y fallback ────────────────────────────
    var playerError by remember(currentItem) { mutableStateOf<String?>(null) }
    var reportSent by remember(currentItem) { mutableStateOf(false) }
    var proxyFallbackTried by remember(currentItem) { mutableStateOf(false) }

    val rawUrl = remember(streamUrl) {
        if (streamUrl.contains("/api/hls-proxy?url=")) {
            try {
                java.net.URLDecoder.decode(
                    streamUrl.substringAfter("/api/hls-proxy?url="), "UTF-8"
                )
            } catch (_: Exception) { null }
        } else null
    }

    // ── Estado del OSD ────────────────────────────────────────
    var osdVisible by remember { mutableStateOf(false) }
    val osdHideJob = remember { mutableStateOf<Job?>(null) }

    fun showOsd() {
        osdVisible = true
        osdHideJob.value?.cancel()
        osdHideJob.value = scope.launch {
            delay(4_000)
            osdVisible = false
        }
    }

    // ── Estado de reproducción para el OSD ───────────────────
    var isPlaying by remember { mutableStateOf(false) }
    var playbackState by remember { mutableIntStateOf(Player.STATE_IDLE) }
    var currentPosition by remember { mutableLongStateOf(0L) }
    var totalDuration by remember { mutableLongStateOf(0L) }
    var audioTracks by remember { mutableStateOf<List<AudioTrackInfo>>(emptyList()) }
    var subtitleTracks by remember { mutableStateOf<List<SubtitleTrackInfo>>(emptyList()) }
    var subtitlesEnabled by remember { mutableStateOf(false) }
    var showAudioPicker by remember { mutableStateOf(false) }

    // ── Auto-next countdown ───────────────────────────────────
    var showNextCountdown by remember { mutableStateOf(false) }
    var countdownSeconds by remember { mutableIntStateOf(5) }

    // ── Progress guardado ─────────────────────────────────────
    val savedProgress = remember(currentItem.id) {
        WatchProgressManager.items.value.find { it.itemId == currentItem.id }
    }
    var hasRestored by remember(currentItem.id) { mutableStateOf(false) }

    // ── ExoPlayer ─────────────────────────────────────────────
    val exoPlayer = remember(streamUrl) {
        val httpDataSourceFactory = DefaultHttpDataSource.Factory()
            .setUserAgent("VLC/3.0.20 LibVLC/3.0.20")
            .setDefaultRequestProperties(mapOf("Icy-MetaData" to "0"))
            .setConnectTimeoutMs(if (currentItem.type == "live") 10_000 else 15_000)
            .setReadTimeoutMs(if (currentItem.type == "live") 15_000 else 30_000)
        ExoPlayer.Builder(context)
            .setMediaSourceFactory(DefaultMediaSourceFactory(httpDataSourceFactory))
            .build().apply {
                val mediaItem = when {
                    streamUrl.contains("/api/hls-proxy") ||
                    streamUrl.lowercase().contains(".m3u8") ->
                        MediaItem.Builder()
                            .setUri(Uri.parse(streamUrl))
                            .setMimeType(MimeTypes.APPLICATION_M3U8)
                            .build()
                    else -> MediaItem.fromUri(Uri.parse(streamUrl))
                }
                setMediaItem(mediaItem)
                prepare()
                playWhenReady = true
            }
    }

    // ── Listener único del player ──────────────────────────────
    LaunchedEffect(exoPlayer) {
        exoPlayer.addListener(object : Player.Listener {

            override fun onIsPlayingChanged(playing: Boolean) {
                isPlaying = playing
            }

            override fun onPlaybackStateChanged(state: Int) {
                playbackState = state
                if (state == Player.STATE_READY && !hasRestored) {
                    hasRestored = true
                    savedProgress?.let { exoPlayer.seekTo(it.positionMs) }
                }
                if (state == Player.STATE_ENDED && hasNextEpisode) {
                    showNextCountdown = true
                }
            }

            override fun onTracksChanged(tracks: Tracks) {
                // Audio tracks
                audioTracks = tracks.groups
                    .mapIndexedNotNull { gi, group ->
                        if (group.type != C.TRACK_TYPE_AUDIO) return@mapIndexedNotNull null
                        val fmt = group.getTrackFormat(0)
                        val lang = fmt.language?.uppercase() ?: "Pista ${gi + 1}"
                        val label = fmt.label?.takeIf { it.isNotBlank() }
                            ?: buildString {
                                append(lang)
                                if (fmt.channelCount > 0) append(" ${fmt.channelCount}ch")
                            }
                        AudioTrackInfo(
                            groupIndex = gi,
                            label = label,
                            selected = group.isSelected,
                        )
                    }

                // Subtitle tracks
                subtitleTracks = tracks.groups
                    .mapIndexedNotNull { gi, group ->
                        if (group.type != C.TRACK_TYPE_TEXT) return@mapIndexedNotNull null
                        val fmt = group.getTrackFormat(0)
                        val lang = fmt.language?.uppercase() ?: "Sub ${gi + 1}"
                        SubtitleTrackInfo(
                            groupIndex = gi,
                            label = fmt.label?.takeIf { it.isNotBlank() } ?: lang,
                            selected = group.isSelected,
                        )
                    }
                subtitlesEnabled = subtitleTracks.any { it.selected }
            }

            override fun onPlayerError(error: PlaybackException) {
                // Fallback para VOD
                if (currentItem.type != "live" && !proxyFallbackTried) {
                    proxyFallbackTried = true
                    exoPlayer.stop()
                    val fallbackItem = if (rawUrl != null) {
                        MediaItem.fromUri(Uri.parse(rawUrl))
                    } else {
                        val enc = java.net.URLEncoder.encode(currentItem.streamUrl, "UTF-8")
                        MediaItem.fromUri(Uri.parse("${ApiClient.BASE_URL}api/stream-proxy?url=$enc"))
                    }
                    exoPlayer.setMediaItem(fallbackItem)
                    exoPlayer.prepare()
                    exoPlayer.play()
                    return
                }

                // Live: stream-proxy → hls-proxy
                if (currentItem.type == "live" && !liveHlsFallbackTried
                    && streamUrl.contains("/api/stream-proxy")) {
                    liveHlsFallbackTried = true
                    val hlsUrl = "${ApiClient.BASE_URL}api/hls-proxy?url=" +
                        java.net.URLEncoder.encode(liveActiveUrl, "UTF-8")
                    exoPlayer.stop()
                    exoPlayer.setMediaItem(
                        MediaItem.Builder()
                            .setUri(Uri.parse(hlsUrl))
                            .setMimeType(MimeTypes.APPLICATION_M3U8)
                            .build()
                    )
                    exoPlayer.prepare()
                    exoPlayer.play()
                    return
                }

                // Live: failover al siguiente servidor
                if (currentItem.type == "live" && !liveFailoverTried) {
                    liveFailoverTried = true
                    scope.launch {
                        try {
                            val repo = ContentRepository()
                            val response = repo.reportDown(currentItem.id, liveActiveUrl)
                            if (response.channelStillAlive && response.nextUrl != null) {
                                liveActiveUrl = response.nextUrl
                                liveFailoverTried = false
                                val newStreamUrl = ApiClient.streamUrl(response.nextUrl)
                                exoPlayer.stop()
                                exoPlayer.setMediaItem(
                                    MediaItem.Builder()
                                        .setUri(Uri.parse(newStreamUrl))
                                        .apply {
                                            if (newStreamUrl.contains("/api/hls-proxy") ||
                                                newStreamUrl.lowercase().contains(".m3u8")) {
                                                setMimeType(MimeTypes.APPLICATION_M3U8)
                                            }
                                        }.build()
                                )
                                exoPlayer.prepare()
                                exoPlayer.play()
                            } else {
                                liveUnavailable = true
                                playerError = "Canal temporalmente no disponible — todos los servidores están caídos"
                            }
                        } catch (_: Exception) {
                            playerError = "Canal no disponible — error al conectar con el servidor"
                        }
                    }
                    return
                }

                playerError = when {
                    error.errorCode == PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_FAILED
                        || error.message?.contains("Unable to connect") == true ->
                        if (currentItem.type == "live") "Canal no disponible — el servidor está caído"
                        else "Sin conexión al servidor"
                    error.errorCode == PlaybackException.ERROR_CODE_IO_BAD_HTTP_STATUS
                        || error.message?.contains("404") == true ->
                        if (currentItem.type == "live") "Canal no encontrado" else "Stream no disponible"
                    error.errorCode == PlaybackException.ERROR_CODE_TIMEOUT ->
                        if (currentItem.type == "live") "El canal tardó demasiado en responder"
                        else "Tiempo de espera agotado"
                    else ->
                        if (currentItem.type == "live") "Error al reproducir el canal"
                        else "Error al reproducir: ${error.localizedMessage}"
                }
            }

            override fun onPlayerErrorChanged(error: PlaybackException?) {
                if (error == null) playerError = null
            }
        })
    }

    // ── Actualización de posición cada 500ms ──────────────────
    LaunchedEffect(exoPlayer) {
        while (true) {
            currentPosition = exoPlayer.currentPosition
            totalDuration = exoPlayer.duration.coerceAtLeast(0)
            delay(500)
        }
    }

    // ── Guardado periódico del progreso ───────────────────────
    LaunchedEffect(exoPlayer) {
        while (true) {
            delay(10_000)
            val pos = exoPlayer.currentPosition
            val dur = exoPlayer.duration
            if (dur > 0 && pos > 5_000 && currentItem.type != "live") {
                WatchProgressManager.save(
                    context,
                    WatchProgress(
                        itemId = currentItem.id,
                        title = currentItem.title,
                        image = currentItem.image,
                        streamUrl = currentItem.streamUrl,
                        type = currentItem.type,
                        seriesTitle = seriesTitle,
                        season = currentItem.season,
                        episode = currentItem.episode,
                        positionMs = pos,
                        durationMs = dur,
                    ),
                )
            }
        }
    }

    // ── Auto-next countdown ───────────────────────────────────
    LaunchedEffect(showNextCountdown) {
        if (!showNextCountdown) return@LaunchedEffect
        countdownSeconds = 5
        repeat(5) { delay(1_000); countdownSeconds-- }
        if (showNextCountdown && hasNextEpisode) {
            showNextCountdown = false
            currentEpisodeIndex++
            currentItem = episodeList[currentEpisodeIndex]
        }
    }

    // ── Guardar progreso y liberar player al salir ────────────
    val saveProgress = {
        val pos = exoPlayer.currentPosition
        val dur = exoPlayer.duration
        if (dur > 0 && pos > 5_000 && currentItem.type != "live") {
            if (pos.toFloat() / dur >= 0.95f) {
                WatchProgressManager.remove(context, currentItem.id)
            } else {
                WatchProgressManager.save(
                    context,
                    WatchProgress(
                        itemId = currentItem.id,
                        title = currentItem.title,
                        image = currentItem.image,
                        streamUrl = currentItem.streamUrl,
                        type = currentItem.type,
                        seriesTitle = seriesTitle,
                        season = currentItem.season,
                        episode = currentItem.episode,
                        positionMs = pos,
                        durationMs = dur,
                    ),
                )
            }
        }
    }

    DisposableEffect(exoPlayer) {
        onDispose {
            saveProgress()
            exoPlayer.release()
        }
    }

    // ── BackHandler: OSD oculto → mostrar; OSD visible → salir ─
    BackHandler {
        if (!osdVisible && playerError == null) {
            showOsd()
        } else {
            saveProgress()
            onBack()
        }
    }

    // ── Focus del reproductor para recibir eventos DPAD ───────
    val playerFocusRequester = remember { FocusRequester() }
    LaunchedEffect(Unit) {
        try { playerFocusRequester.requestFocus() } catch (_: Exception) {}
    }

    // ── UI ────────────────────────────────────────────────────
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black)
            .focusRequester(playerFocusRequester)
            .focusable()
            .onPreviewKeyEvent { event ->
                if (event.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
                when (event.key.nativeKeyCode) {
                    // OK / Enter → toggle OSD o play/pause si OSD visible
                    AndroidKeyEvent.KEYCODE_DPAD_CENTER,
                    AndroidKeyEvent.KEYCODE_ENTER -> {
                        if (!osdVisible) showOsd()
                        else {
                            if (exoPlayer.isPlaying) exoPlayer.pause() else exoPlayer.play()
                            showOsd()
                        }
                        true
                    }
                    // Media keys
                    AndroidKeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> {
                        if (exoPlayer.isPlaying) exoPlayer.pause() else exoPlayer.play()
                        showOsd(); true
                    }
                    AndroidKeyEvent.KEYCODE_MEDIA_PLAY  -> { exoPlayer.play(); showOsd(); true }
                    AndroidKeyEvent.KEYCODE_MEDIA_PAUSE -> { exoPlayer.pause(); showOsd(); true }
                    // D-pad izq/der: mostrar OSD si estaba oculto; si visible → slider lo maneja
                    AndroidKeyEvent.KEYCODE_DPAD_LEFT,
                    AndroidKeyEvent.KEYCODE_DPAD_RIGHT -> {
                        if (!osdVisible) { showOsd(); true } else false
                    }
                    else -> false
                }
            },
    ) {
        // ── Video ─────────────────────────────────────────────
        AndroidView(
            factory = { ctx ->
                PlayerView(ctx).apply {
                    player = exoPlayer
                    useController = false          // OSD propio, no el de ExoPlayer
                    setKeepContentOnPlayerReset(true)
                }
            },
            modifier = Modifier.fillMaxSize(),
            update = { view -> view.player = exoPlayer },
        )

        // ── OSD overlay animado ───────────────────────────────
        AnimatedVisibility(
            visible = osdVisible && playerError == null,
            enter = fadeIn(),
            exit = fadeOut(),
        ) {
            PlayerOsd(
                title = if (seriesTitle != null)
                    "$seriesTitle — ${currentItem.title}" else currentItem.title,
                isLive = currentItem.type == "live",
                isPlaying = isPlaying,
                isBuffering = playbackState == Player.STATE_BUFFERING,
                currentPosition = currentPosition,
                totalDuration = totalDuration,
                hasMultipleServers = hasMultipleServers,
                audioTracks = audioTracks,
                subtitleTracks = subtitleTracks,
                subtitlesEnabled = subtitlesEnabled,
                onBack = { saveProgress(); osdVisible = false; onBack() },
                onPlayPause = {
                    if (exoPlayer.isPlaying) exoPlayer.pause() else exoPlayer.play()
                    showOsd()
                },
                onSeek = { pos ->
                    exoPlayer.seekTo(pos)
                    currentPosition = pos
                    showOsd()
                },
                onRewind = {
                    exoPlayer.seekTo((exoPlayer.currentPosition - 10_000).coerceAtLeast(0))
                    showOsd()
                },
                onForward = {
                    exoPlayer.seekTo(exoPlayer.currentPosition + 10_000)
                    showOsd()
                },
                onAudioTracks = { showAudioPicker = true; showOsd() },
                onSubtitleToggle = {
                    val newEnabled = !subtitlesEnabled
                    subtitlesEnabled = newEnabled
                    exoPlayer.trackSelectionParameters = exoPlayer.trackSelectionParameters
                        .buildUpon()
                        .setTrackTypeDisabled(C.TRACK_TYPE_TEXT, !newEnabled)
                        .build()
                    showOsd()
                },
                onServerPicker = {
                    showServerPicker = true
                    if (servers.isEmpty()) {
                        serversLoading = true
                        scope.launch {
                            try {
                                val repo = ContentRepository()
                                servers = repo.getLiveServers(currentItem.id).servers
                            } catch (_: Exception) {
                                servers = liveUrls?.mapIndexed { i, url ->
                                    LiveServer(i, url, url == liveActiveUrl, "Servidor ${i + 1}")
                                } ?: emptyList()
                            } finally { serversLoading = false }
                        }
                    }
                },
            )
        }

        // ── Spinner de buffering ──────────────────────────────
        if (playbackState == Player.STATE_BUFFERING && playerError == null) {
            CircularProgressIndicator(
                modifier = Modifier.align(Alignment.Center),
                color = Color.White,
                strokeWidth = 3.dp,
            )
        }

        // ── Audio track picker ────────────────────────────────
        if (showAudioPicker && audioTracks.size > 1) {
            AlertDialog(
                onDismissRequest = { showAudioPicker = false },
                containerColor = Color(0xFF1A1A1A),
                title = { Text("Pista de audio", color = Color.White) },
                text = {
                    Column {
                        audioTracks.forEach { track ->
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable {
                                        val group = exoPlayer.currentTracks.groups
                                            .getOrNull(track.groupIndex)
                                        if (group != null) {
                                            exoPlayer.trackSelectionParameters =
                                                exoPlayer.trackSelectionParameters
                                                    .buildUpon()
                                                    .setOverrideForType(
                                                        TrackSelectionOverride(
                                                            group.mediaTrackGroup, listOf(0)
                                                        )
                                                    ).build()
                                        }
                                        showAudioPicker = false
                                    }
                                    .padding(vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                RadioButton(
                                    selected = track.selected,
                                    onClick = null,
                                    colors = RadioButtonDefaults.colors(
                                        selectedColor = MaterialTheme.colorScheme.primary,
                                    ),
                                )
                                Spacer(Modifier.width(8.dp))
                                Text(track.label, color = Color.White)
                            }
                        }
                    }
                },
                confirmButton = {
                    TextButton(onClick = { showAudioPicker = false }) {
                        Text("Cerrar", color = MaterialTheme.colorScheme.primary)
                    }
                },
            )
        }

        // ── Server picker bottom sheet ────────────────────────
        if (showServerPicker) {
            ModalBottomSheet(
                onDismissRequest = { showServerPicker = false },
                containerColor = Color(0xFF1A1A1A),
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 32.dp),
                ) {
                    Text(
                        text = currentItem.title,
                        style = MaterialTheme.typography.titleMedium,
                        color = Color.White,
                        modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        "Selecciona un servidor",
                        style = MaterialTheme.typography.bodySmall,
                        color = Color.White.copy(alpha = 0.5f),
                        modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp),
                    )
                    HorizontalDivider(
                        modifier = Modifier.padding(vertical = 8.dp),
                        color = Color.White.copy(alpha = 0.12f),
                    )
                    if (serversLoading) {
                        Box(
                            Modifier.fillMaxWidth().padding(32.dp),
                            contentAlignment = Alignment.Center,
                        ) { CircularProgressIndicator(color = MaterialTheme.colorScheme.primary) }
                    } else {
                        val displayServers = servers.ifEmpty {
                            liveUrls?.mapIndexed { i, url ->
                                LiveServer(i, url, url == liveActiveUrl, "Servidor ${i + 1}")
                            } ?: emptyList()
                        }
                        displayServers.forEach { srv ->
                            val current = srv.url == liveActiveUrl
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable {
                                        showServerPicker = false
                                        liveActiveUrl = srv.url
                                        liveFailoverTried = false
                                        liveUnavailable = false
                                        playerError = null
                                        val newUrl = ApiClient.streamUrl(srv.url)
                                        exoPlayer.stop()
                                        exoPlayer.setMediaItem(
                                            MediaItem.Builder()
                                                .setUri(Uri.parse(newUrl))
                                                .apply {
                                                    if (newUrl.contains("/api/hls-proxy") ||
                                                        newUrl.lowercase().contains(".m3u8")) {
                                                        setMimeType(MimeTypes.APPLICATION_M3U8)
                                                    }
                                                }.build()
                                        )
                                        exoPlayer.prepare()
                                        exoPlayer.play()
                                        scope.launch {
                                            try { ContentRepository().setLiveServer(currentItem.id, srv.index) }
                                            catch (_: Exception) {}
                                        }
                                    }
                                    .background(
                                        if (current) MaterialTheme.colorScheme.primary.copy(alpha = 0.15f)
                                        else Color.Transparent
                                    )
                                    .padding(horizontal = 20.dp, vertical = 12.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Column(Modifier.weight(1f)) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text(
                                            srv.label,
                                            style = MaterialTheme.typography.bodyMedium,
                                            color = if (current) MaterialTheme.colorScheme.primary
                                                    else Color.White,
                                        )
                                        if (current) {
                                            Spacer(Modifier.width(6.dp))
                                            Text(
                                                "● EN USO",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = MaterialTheme.colorScheme.primary,
                                            )
                                        }
                                    }
                                    Text(
                                        text = try { java.net.URL(srv.url).host }
                                              catch (_: Exception) { srv.url },
                                        style = MaterialTheme.typography.bodySmall.copy(
                                            fontFamily = FontFamily.Monospace,
                                        ),
                                        color = Color.White.copy(alpha = 0.45f),
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                }
                                val aliveColor = when (srv.alive) {
                                    true  -> Color(0xFF4CAF50)
                                    false -> Color(0xFFF44336)
                                    else  -> Color.Transparent
                                }
                                if (srv.alive != null) {
                                    Column(
                                        horizontalAlignment = Alignment.End,
                                        modifier = Modifier.padding(start = 8.dp),
                                    ) {
                                        Text(
                                            if (srv.alive == true) "ONLINE" else "OFFLINE",
                                            style = MaterialTheme.typography.labelSmall,
                                            color = aliveColor,
                                        )
                                        if (srv.latencyMs != null && srv.alive == true) {
                                            Text(
                                                "${srv.latencyMs}ms",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = Color.White.copy(alpha = 0.4f),
                                            )
                                        }
                                    }
                                }
                            }
                            HorizontalDivider(color = Color.White.copy(alpha = 0.07f))
                        }
                    }
                }
            }
        }

        // ── Countdown al siguiente episodio ───────────────────
        if (showNextCountdown && hasNextEpisode) {
            Box(
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    .padding(24.dp)
                    .background(Color.Black.copy(alpha = 0.80f), RoundedCornerShape(12.dp))
                    .padding(horizontal = 20.dp, vertical = 14.dp),
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    val nextEp = episodeList[currentEpisodeIndex + 1]
                    Text("Siguiente episodio en ${countdownSeconds}s", color = Color.White,
                        style = MaterialTheme.typography.bodyMedium)
                    Text(nextEp.title, color = Color.White.copy(alpha = 0.7f),
                        style = MaterialTheme.typography.bodySmall, maxLines = 1)
                    Spacer(Modifier.height(10.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(
                            onClick = { showNextCountdown = false },
                            colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White),
                        ) { Text("Cancelar") }
                        Button(
                            onClick = {
                                showNextCountdown = false
                                currentEpisodeIndex++
                                currentItem = episodeList[currentEpisodeIndex]
                            },
                            colors = ButtonDefaults.buttonColors(
                                containerColor = MaterialTheme.colorScheme.primary,
                            ),
                        ) {
                            Icon(Icons.Default.SkipNext, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Ver ahora")
                        }
                    }
                }
            }
        }

        // ── Error overlay ─────────────────────────────────────
        if (playerError != null) {
            Box(
                modifier = Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.82f)),
                contentAlignment = Alignment.Center,
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.padding(horizontal = 32.dp),
                ) {
                    Text("⚠️", style = MaterialTheme.typography.displaySmall)
                    Spacer(Modifier.height(12.dp))
                    Text(
                        playerError!!, color = Color.White,
                        style = MaterialTheme.typography.bodyLarge,
                        textAlign = TextAlign.Center,
                    )
                    Spacer(Modifier.height(20.dp))
                    Button(
                        onClick = {
                            playerError = null
                            reportSent = false
                            proxyFallbackTried = false
                            liveFailoverTried = false
                            liveHlsFallbackTried = false
                            liveUnavailable = false
                            exoPlayer.prepare()
                            exoPlayer.play()
                        },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.primary,
                        ),
                    ) { Text("Reintentar") }
                    Spacer(Modifier.height(8.dp))
                    if (currentItem.id > 0) {
                        if (reportSent) {
                            Text("✓ Reporte enviado", color = Color(0xFF4CAF50),
                                style = MaterialTheme.typography.bodySmall)
                        } else {
                            OutlinedButton(
                                onClick = {
                                    scope.launch {
                                        try { ApiClient.api.reportar(currentItem.id); reportSent = true }
                                        catch (_: Exception) {}
                                    }
                                },
                                colors = ButtonDefaults.outlinedButtonColors(
                                    contentColor = Color(0xFFFF9800),
                                ),
                            ) { Text("📢 Reportar canal caído") }
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                    TextButton(onClick = { saveProgress(); onBack() }) {
                        Text("Volver", color = Color.White)
                    }
                }
            }
        }
    }
}

// ══════════════════════════════════════════════════════════════
// OSD — On Screen Display
// ══════════════════════════════════════════════════════════════

@Composable
private fun PlayerOsd(
    title: String,
    isLive: Boolean,
    isPlaying: Boolean,
    isBuffering: Boolean,
    currentPosition: Long,
    totalDuration: Long,
    hasMultipleServers: Boolean,
    audioTracks: List<AudioTrackInfo>,
    subtitleTracks: List<SubtitleTrackInfo>,
    subtitlesEnabled: Boolean,
    onBack: () -> Unit,
    onPlayPause: () -> Unit,
    onSeek: (Long) -> Unit,
    onRewind: () -> Unit,
    onForward: () -> Unit,
    onAudioTracks: () -> Unit,
    onSubtitleToggle: () -> Unit,
    onServerPicker: () -> Unit,
) {
    Box(modifier = Modifier.fillMaxSize()) {

        // ── Gradiente superior: botón atrás + título + controles ─
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .align(Alignment.TopCenter)
                .background(
                    Brush.verticalGradient(
                        colors = listOf(Color.Black.copy(alpha = 0.75f), Color.Transparent),
                    )
                )
                .padding(horizontal = 4.dp, vertical = 4.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth(),
            ) {
                // Botón atrás
                IconButton(onClick = onBack) {
                    Icon(
                        Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = "Volver",
                        tint = Color.White,
                        modifier = Modifier.size(26.dp),
                    )
                }

                // Título
                Text(
                    text = title,
                    color = Color.White,
                    style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f).padding(horizontal = 4.dp),
                )

                // Selector de pista de audio
                if (audioTracks.size > 1) {
                    IconButton(onClick = onAudioTracks) {
                        Icon(Icons.Default.Audiotrack, "Pistas de audio", tint = Color.White,
                            modifier = Modifier.size(22.dp))
                    }
                }

                // Toggle subtítulos
                if (subtitleTracks.isNotEmpty()) {
                    IconButton(onClick = onSubtitleToggle) {
                        Icon(
                            if (subtitlesEnabled) Icons.Default.ClosedCaption
                            else Icons.Default.ClosedCaptionDisabled,
                            "Subtítulos",
                            tint = if (subtitlesEnabled) MaterialTheme.colorScheme.primary
                                   else Color.White,
                            modifier = Modifier.size(22.dp),
                        )
                    }
                }

                // Selector de servidor (live)
                if (hasMultipleServers) {
                    IconButton(onClick = onServerPicker) {
                        Icon(Icons.Default.Dns, "Cambiar servidor", tint = Color.White,
                            modifier = Modifier.size(22.dp))
                    }
                }
            }
        }

        // ── Gradiente inferior: barra de progreso + controles ─
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .align(Alignment.BottomCenter)
                .background(
                    Brush.verticalGradient(
                        colors = listOf(Color.Transparent, Color.Black.copy(alpha = 0.88f)),
                    )
                )
                .padding(horizontal = 8.dp)
                .padding(bottom = 12.dp, top = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            // Barra de progreso (solo VOD)
            if (!isLive && totalDuration > 0) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        currentPosition.toTimeString(),
                        color = Color.White,
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.width(48.dp),
                        textAlign = TextAlign.Center,
                    )
                    Slider(
                        value = (currentPosition.toFloat() / totalDuration).coerceIn(0f, 1f),
                        onValueChange = { fraction ->
                            onSeek((fraction * totalDuration).toLong())
                        },
                        modifier = Modifier.weight(1f),
                        colors = SliderDefaults.colors(
                            thumbColor = Color(0xFFE50914),
                            activeTrackColor = Color(0xFFE50914),
                            inactiveTrackColor = Color.White.copy(alpha = 0.35f),
                        ),
                    )
                    Text(
                        totalDuration.toTimeString(),
                        color = Color.White.copy(alpha = 0.7f),
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.width(48.dp),
                        textAlign = TextAlign.Center,
                    )
                }
            } else if (isLive) {
                // Badge EN DIRECTO
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(
                        modifier = Modifier
                            .background(Color(0xFFE50914), RoundedCornerShape(4.dp))
                            .padding(horizontal = 8.dp, vertical = 3.dp),
                    ) {
                        Text(
                            "● EN DIRECTO",
                            color = Color.White,
                            style = MaterialTheme.typography.labelSmall.copy(
                                fontWeight = FontWeight.Bold, fontSize = 11.sp,
                            ),
                        )
                    }
                }
            }

            Spacer(Modifier.height(6.dp))

            // Botones de control
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (!isLive) {
                    IconButton(
                        onClick = onRewind,
                        modifier = Modifier.size(52.dp),
                    ) {
                        Icon(
                            Icons.Default.Replay10,
                            contentDescription = "Retroceder 10s",
                            tint = Color.White,
                            modifier = Modifier.size(30.dp),
                        )
                    }
                    Spacer(Modifier.width(12.dp))
                }

                // Play / Pause central
                FilledIconButton(
                    onClick = onPlayPause,
                    modifier = Modifier.size(60.dp),
                    colors = IconButtonDefaults.filledIconButtonColors(
                        containerColor = Color.White.copy(alpha = 0.18f),
                    ),
                    shape = RoundedCornerShape(50),
                ) {
                    Icon(
                        imageVector = when {
                            isBuffering -> Icons.Default.HourglassEmpty
                            isPlaying   -> Icons.Default.Pause
                            else        -> Icons.Default.PlayArrow
                        },
                        contentDescription = if (isPlaying) "Pausar" else "Reproducir",
                        tint = Color.White,
                        modifier = Modifier.size(34.dp),
                    )
                }

                if (!isLive) {
                    Spacer(Modifier.width(12.dp))
                    IconButton(
                        onClick = onForward,
                        modifier = Modifier.size(52.dp),
                    ) {
                        Icon(
                            Icons.Default.Forward10,
                            contentDescription = "Avanzar 10s",
                            tint = Color.White,
                            modifier = Modifier.size(30.dp),
                        )
                    }
                }
            }
        }
    }
}
