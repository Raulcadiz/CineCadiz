package com.example.cinecity.ui.screens

import android.app.Activity
import android.content.pm.ActivityInfo
import android.net.Uri
import android.view.View
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Dns
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
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
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

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

    // Current episode state (can switch to next within same screen)
    var currentItem by remember { mutableStateOf(item) }
    var currentEpisodeIndex by remember { mutableIntStateOf(episodeIndex) }
    val hasNextEpisode = episodeList.isNotEmpty()
        && currentEpisodeIndex >= 0
        && currentEpisodeIndex < episodeList.size - 1

    // Force landscape while in player
    DisposableEffect(Unit) {
        val activity = context as? Activity
        activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        onDispose {
            activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
        }
    }

    // Live failover state — debe estar ANTES de streamUrl porque streamUrl lo usa
    var liveActiveUrl by remember(currentItem) {
        mutableStateOf(currentItem.streamUrl)
    }
    var liveFailoverTried by remember(currentItem) { mutableStateOf(false) }
    // Fallback intermedio live: stream-proxy falla → probar hls-proxy antes de reportar down
    var liveHlsFallbackTried by remember(currentItem) { mutableStateOf(false) }
    var liveUnavailable by remember(currentItem) { mutableStateOf(false) }

    // Server picker state (solo para canales live con múltiples URLs)
    val liveUrls = currentItem.liveUrls
    val hasMultipleServers = currentItem.type == "live" && (liveUrls?.size ?: 0) > 1
    var showServerPicker by remember { mutableStateOf(false) }
    var servers by remember(currentItem) { mutableStateOf<List<LiveServer>>(emptyList()) }
    var serversLoading by remember(currentItem) { mutableStateOf(false) }

    // Para canales live, usar liveActiveUrl (puede cambiar por failover/selector)
    val streamUrl = remember(currentItem, liveActiveUrl) {
        ApiClient.streamUrl(
            if (currentItem.type == "live") liveActiveUrl else currentItem.streamUrl
        )
    }

    var playerError by remember(currentItem) { mutableStateOf<String?>(null) }
    var reportSent by remember(currentItem) { mutableStateOf(false) }
    var proxyFallbackTried by remember(currentItem) { mutableStateOf(false) }
    var isControllerVisible by remember { mutableStateOf(true) }
    var showNextCountdown by remember { mutableStateOf(false) }
    var countdownSeconds by remember { mutableIntStateOf(5) }

    val rawUrl = remember(streamUrl) {
        if (streamUrl.contains("/api/hls-proxy?url=")) {
            try {
                java.net.URLDecoder.decode(
                    streamUrl.substringAfter("/api/hls-proxy?url="), "UTF-8"
                )
            } catch (_: Exception) { null }
        } else null
    }

    // Saved progress for this item (seek on start)
    val savedProgress = remember(currentItem.id) {
        WatchProgressManager.items.value.find { it.itemId == currentItem.id }
    }

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

    // Seek to saved position when player is ready (only once per item)
    var hasRestored by remember(currentItem.id) { mutableStateOf(false) }

    // Periodic progress saving (every 10 seconds)
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

    // Auto-next countdown
    LaunchedEffect(showNextCountdown) {
        if (!showNextCountdown) return@LaunchedEffect
        countdownSeconds = 5
        repeat(5) {
            delay(1_000)
            countdownSeconds--
        }
        // Auto-play next
        if (showNextCountdown && hasNextEpisode) {
            showNextCountdown = false
            val next = episodeList[currentEpisodeIndex + 1]
            currentEpisodeIndex++
            currentItem = next
        }
    }

    LaunchedEffect(exoPlayer) {
        exoPlayer.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(playbackState: Int) {
                if (playbackState == Player.STATE_READY && !hasRestored) {
                    hasRestored = true
                    savedProgress?.let { exoPlayer.seekTo(it.positionMs) }
                }
                if (playbackState == Player.STATE_ENDED && hasNextEpisode) {
                    showNextCountdown = true
                }
            }

            override fun onPlayerError(error: PlaybackException) {
                if (currentItem.type != "live" && !proxyFallbackTried) {
                    proxyFallbackTried = true
                    exoPlayer.stop()

                    val fallbackItem: MediaItem = if (rawUrl != null) {
                        // Caso A: estaba usando proxy (hls-proxy) → probar URL directa
                        MediaItem.fromUri(Uri.parse(rawUrl))
                    } else {
                        // Caso B: estaba usando URL directa (.mp4/.mkv/etc.) →
                        // probar via stream-proxy del VPS (añade cabeceras VLC, Referer, etc.)
                        val encoded = java.net.URLEncoder.encode(currentItem.streamUrl, "UTF-8")
                        MediaItem.fromUri(Uri.parse("${ApiClient.BASE_URL}api/stream-proxy?url=$encoded"))
                    }

                    exoPlayer.setMediaItem(fallbackItem)
                    exoPlayer.prepare()
                    exoPlayer.play()
                    return
                }

                // Paso 2a: live con stream-proxy → si falla, probar hls-proxy (reescribe segmentos)
                if (currentItem.type == "live" && !liveHlsFallbackTried
                    && streamUrl.contains("/api/stream-proxy")) {
                    liveHlsFallbackTried = true
                    val hlsUrl = "${ApiClient.BASE_URL}api/hls-proxy?url=" +
                        java.net.URLEncoder.encode(liveActiveUrl, "UTF-8")
                    val hlsItem = MediaItem.Builder()
                        .setUri(Uri.parse(hlsUrl))
                        .setMimeType(MimeTypes.APPLICATION_M3U8)
                        .build()
                    exoPlayer.stop()
                    exoPlayer.setMediaItem(hlsItem)
                    exoPlayer.prepare()
                    exoPlayer.play()
                    return
                }

                // Paso 2b: para canales live → failover al siguiente servidor
                if (currentItem.type == "live" && !liveFailoverTried) {
                    liveFailoverTried = true
                    scope.launch {
                        try {
                            val repo = ContentRepository()
                            val response = repo.reportDown(currentItem.id, liveActiveUrl)
                            if (response.channelStillAlive && response.nextUrl != null) {
                                // Failover transparente: cambiar URL y recargar sin mostrar error
                                liveActiveUrl = response.nextUrl
                                liveFailoverTried = false  // Permitir otro failover si este también falla
                                val newStreamUrl = ApiClient.streamUrl(response.nextUrl)
                                val newItem = MediaItem.Builder()
                                    .setUri(Uri.parse(newStreamUrl))
                                    .apply {
                                        if (newStreamUrl.contains("/api/hls-proxy") ||
                                            newStreamUrl.lowercase().contains(".m3u8")) {
                                            setMimeType(MimeTypes.APPLICATION_M3U8)
                                        }
                                    }
                                    .build()
                                exoPlayer.stop()
                                exoPlayer.setMediaItem(newItem)
                                exoPlayer.prepare()
                                exoPlayer.play()
                                return@launch
                            } else {
                                // Todos los servidores caídos
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
                        if (currentItem.type == "live") "Canal no encontrado en el servidor"
                        else "Stream no disponible"

                    error.errorCode == PlaybackException.ERROR_CODE_TIMEOUT ->
                        if (currentItem.type == "live") "El canal tardó demasiado en responder"
                        else "Tiempo de espera agotado"

                    else -> if (currentItem.type == "live")
                        "Error al reproducir el canal"
                    else
                        "Error al reproducir: ${error.localizedMessage}"
                }
            }

            override fun onPlayerErrorChanged(error: PlaybackException?) {
                if (error == null) playerError = null
            }
        })
    }

    // Save progress on exit and release player
    val saveProgress = {
        val pos = exoPlayer.currentPosition
        val dur = exoPlayer.duration
        if (dur > 0 && pos > 5_000 && currentItem.type != "live") {
            val fraction = pos.toFloat() / dur
            if (fraction >= 0.95f) {
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

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black),
    ) {
        AndroidView(
            factory = { ctx ->
                PlayerView(ctx).apply {
                    player = exoPlayer
                    useController = true
                    setShowNextButton(false)
                    setShowPreviousButton(false)
                    setControllerVisibilityListener(PlayerView.ControllerVisibilityListener { visibility ->
                        isControllerVisible = (visibility == View.VISIBLE)
                    })
                }
            },
            modifier = Modifier.fillMaxSize(),
            update = { view -> view.player = exoPlayer },
        )

        // Back button + server picker — solo visibles con controles visibles
        if (isControllerVisible && playerError == null) {
            IconButton(
                onClick = {
                    saveProgress()
                    onBack()
                },
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .padding(8.dp),
            ) {
                Icon(
                    Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "Volver",
                    tint = Color.White,
                    modifier = Modifier.size(28.dp),
                )
            }

            // Botón selector de servidor (solo live con múltiples servidores)
            if (hasMultipleServers) {
                IconButton(
                    onClick = {
                        showServerPicker = true
                        if (servers.isEmpty()) {
                            serversLoading = true
                            scope.launch {
                                try {
                                    val repo = ContentRepository()
                                    val resp = repo.getLiveServers(currentItem.id)
                                    servers = resp.servers
                                } catch (_: Exception) {
                                    // Fallback: construir lista desde liveUrls
                                    servers = liveUrls!!.mapIndexed { i, url ->
                                        LiveServer(
                                            index = i,
                                            url = url,
                                            active = url == liveActiveUrl,
                                            label = "Servidor ${i + 1}",
                                        )
                                    }
                                } finally {
                                    serversLoading = false
                                }
                            }
                        }
                    },
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(8.dp),
                ) {
                    Icon(
                        Icons.Default.Dns,
                        contentDescription = "Cambiar servidor",
                        tint = Color.White,
                        modifier = Modifier.size(24.dp),
                    )
                }
            }
        }

        // ── Modal Bottom Sheet: selector de servidor ─────────────
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
                        text = "Selecciona un servidor",
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
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(32.dp),
                            contentAlignment = Alignment.Center,
                        ) {
                            CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
                        }
                    } else {
                        val displayServers = servers.ifEmpty {
                            liveUrls?.mapIndexed { i, url ->
                                LiveServer(
                                    index = i,
                                    url = url,
                                    active = url == liveActiveUrl,
                                    label = "Servidor ${i + 1}",
                                )
                            } ?: emptyList()
                        }

                        displayServers.forEach { srv ->
                            val isCurrentlyPlaying = srv.url == liveActiveUrl
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable {
                                        showServerPicker = false
                                        scope.launch {
                                            try {
                                                val repo = ContentRepository()
                                                repo.setLiveServer(currentItem.id, srv.index)
                                            } catch (_: Exception) { /* no crítico */ }
                                        }
                                        // Cambiar reproducción de forma transparente
                                        liveActiveUrl = srv.url
                                        liveFailoverTried = false
                                        liveUnavailable = false
                                        playerError = null
                                        val newStreamUrl = ApiClient.streamUrl(srv.url)
                                        val newItem = MediaItem.Builder()
                                            .setUri(Uri.parse(newStreamUrl))
                                            .apply {
                                                if (newStreamUrl.contains("/api/hls-proxy") ||
                                                    newStreamUrl.lowercase().contains(".m3u8")) {
                                                    setMimeType(MimeTypes.APPLICATION_M3U8)
                                                }
                                            }
                                            .build()
                                        exoPlayer.stop()
                                        exoPlayer.setMediaItem(newItem)
                                        exoPlayer.prepare()
                                        exoPlayer.play()
                                    }
                                    .background(
                                        if (isCurrentlyPlaying)
                                            MaterialTheme.colorScheme.primary.copy(alpha = 0.15f)
                                        else Color.Transparent
                                    )
                                    .padding(horizontal = 20.dp, vertical = 12.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text(
                                            text = srv.label,
                                            style = MaterialTheme.typography.bodyMedium,
                                            color = if (isCurrentlyPlaying)
                                                MaterialTheme.colorScheme.primary
                                            else Color.White,
                                        )
                                        if (isCurrentlyPlaying) {
                                            Spacer(Modifier.width(6.dp))
                                            Text(
                                                text = "● EN USO",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = MaterialTheme.colorScheme.primary,
                                            )
                                        }
                                    }
                                    Text(
                                        text = try {
                                            java.net.URL(srv.url).host
                                        } catch (_: Exception) { srv.url },
                                        style = MaterialTheme.typography.bodySmall.copy(
                                            fontFamily = FontFamily.Monospace,
                                        ),
                                        color = Color.White.copy(alpha = 0.45f),
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                }

                                // Badge de estado del servidor
                                val aliveColor = when {
                                    srv.alive == true  -> Color(0xFF4CAF50)
                                    srv.alive == false -> Color(0xFFF44336)
                                    else               -> Color.Transparent
                                }
                                if (srv.alive != null) {
                                    Column(
                                        horizontalAlignment = Alignment.End,
                                        modifier = Modifier.padding(start = 8.dp),
                                    ) {
                                        Text(
                                            text = if (srv.alive == true) "ONLINE" else "OFFLINE",
                                            style = MaterialTheme.typography.labelSmall,
                                            color = aliveColor,
                                        )
                                        if (srv.latencyMs != null && srv.alive == true) {
                                            Text(
                                                text = "${srv.latencyMs}ms",
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

        // Auto-next episode countdown overlay
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
                    Text(
                        text = "Siguiente episodio en ${countdownSeconds}s",
                        color = Color.White,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Text(
                        text = nextEp.title,
                        color = Color.White.copy(alpha = 0.7f),
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                    )
                    Spacer(Modifier.height(10.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(
                            onClick = { showNextCountdown = false },
                            colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White),
                        ) { Text("Cancelar") }
                        Button(
                            onClick = {
                                showNextCountdown = false
                                val next = episodeList[currentEpisodeIndex + 1]
                                currentEpisodeIndex++
                                currentItem = next
                            },
                            colors = ButtonDefaults.buttonColors(
                                containerColor = MaterialTheme.colorScheme.primary,
                            ),
                        ) {
                            Icon(Icons.Default.SkipNext, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Ver ahora")
                        }
                    }
                }
            }
        }

        // Error overlay
        if (playerError != null) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.82f)),
                contentAlignment = Alignment.Center,
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.padding(horizontal = 32.dp),
                ) {
                    Text(text = "⚠️", style = MaterialTheme.typography.displaySmall)
                    Spacer(Modifier.height(12.dp))
                    Text(
                        text = playerError!!,
                        color = Color.White,
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
                            Text(
                                text = "✓ Reporte enviado, gracias",
                                color = Color(0xFF4CAF50),
                                style = MaterialTheme.typography.bodySmall,
                            )
                        } else {
                            OutlinedButton(
                                onClick = {
                                    scope.launch {
                                        try {
                                            ApiClient.api.reportar(currentItem.id)
                                            reportSent = true
                                        } catch (_: Exception) {}
                                    }
                                },
                                colors = ButtonDefaults.outlinedButtonColors(
                                    contentColor = Color(0xFFFF9800),
                                ),
                            ) { Text("📢 Reportar canal caído") }
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                    TextButton(onClick = onBack) { Text("Volver", color = Color.White) }
                }
            }
        }
    }
}
