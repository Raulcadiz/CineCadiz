package com.example.cinecity

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.speech.tts.TextToSpeech
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import android.os.Bundle
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.LiveTv
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SystemUpdate
import androidx.compose.material.icons.filled.Tv
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.example.cinecity.data.WatchProgressManager
import com.example.cinecity.data.api.ApiClient
import com.example.cinecity.data.model.Contenido
import com.example.cinecity.ui.components.VoiceAssistantOverlay
import com.example.cinecity.ui.screens.*
import com.example.cinecity.ui.theme.CineCityTheme
import com.example.cinecity.ui.theme.LocalTtsSpeakFn
import com.example.cinecity.viewmodel.AppPreferencesViewModel
import com.example.cinecity.viewmodel.SharedViewModel
import com.example.cinecity.viewmodel.VoiceAssistantViewModel

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WatchProgressManager.init(this)
        enableEdgeToEdge()
        setContent {
            val prefsVm: AppPreferencesViewModel = viewModel()
            val highContrast by prefsVm.highContrast.collectAsState()
            val largeText    by prefsVm.largeText.collectAsState()
            val ttsOnFocus   by prefsVm.ttsOnFocus.collectAsState()

            CineCityTheme(
                highContrast = highContrast,
                largeText    = largeText,
                ttsOnFocus   = ttsOnFocus,
            ) {
                CineCityApp(prefsVm)
            }
        }
    }
}

// ── Navigation destinations ────────────────────────────────────

private sealed class Tab(val route: String, val label: String, val icon: ImageVector) {
    data object Home     : Tab("home",     "Inicio",    Icons.Default.Home)
    data object Movies   : Tab("movies",   "Películas", Icons.Default.Movie)
    data object Series   : Tab("series",   "Series",    Icons.Default.Tv)
    data object Live     : Tab("live",     "Directo",   Icons.Default.LiveTv)
    data object Settings : Tab("settings", "Ajustes",   Icons.Default.Settings)
}

private val TABS = listOf(Tab.Home, Tab.Movies, Tab.Series, Tab.Live, Tab.Settings)

// ── Root composable ────────────────────────────────────────────

@Composable
fun CineCityApp(prefsVm: AppPreferencesViewModel) {
    val navController = rememberNavController()
    val shared: SharedViewModel = viewModel()
    val voiceVm: VoiceAssistantViewModel = viewModel()
    val context = LocalContext.current

    val simplified  by prefsVm.simplified.collectAsState()
    val ttsOnFocus  by prefsVm.ttsOnFocus.collectAsState()

    // ── Shared TTS for focus narration ────────────────────────
    var focusTts by remember { mutableStateOf<TextToSpeech?>(null) }
    DisposableEffect(context) {
        var instance: TextToSpeech? = null
        instance = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                instance?.language = java.util.Locale("es", "ES")
                instance?.setSpeechRate(0.95f)
                focusTts = instance
            }
        }
        onDispose {
            instance?.stop()
            instance?.shutdown()
            focusTts = null
        }
    }
    val ttsSpeakFn: ((String) -> Unit)? = if (ttsOnFocus && focusTts != null) {
        { text -> focusTts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "FOCUS_UTT") }
    } else null

    // ── Update check ──────────────────────────────────────────
    val currentVersion = "2.1"
    var updateAvailable  by remember { mutableStateOf(false) }
    var updateUrl        by remember { mutableStateOf("") }
    var showUpdateBanner by remember { mutableStateOf(true) }

    LaunchedEffect(Unit) {
        try {
            val resp = ApiClient.api.getAppVersion()
            if (resp.version != currentVersion) {
                updateAvailable = true
                updateUrl = resp.apk_url
            }
        } catch (_: Exception) {}
    }

    // ── Microphone permission ──────────────────────────────────
    var hasMicPerm by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO)
                    == PackageManager.PERMISSION_GRANTED
        )
    }
    val permLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> hasMicPerm = granted }

    LaunchedEffect(Unit) {
        if (!hasMicPerm) permLauncher.launch(Manifest.permission.RECORD_AUDIO)
    }

    // ── Wire voice assistant callbacks ─────────────────────────
    LaunchedEffect(voiceVm) {
        voiceVm.onNavigate = { route ->
            navController.navigate(route) {
                popUpTo("home") { saveState = true }
                launchSingleTop = true
                restoreState    = true
            }
        }
        voiceVm.onPlayItem = { item ->
            shared.pendingItem = item
            shared.pendingEpisodeList  = emptyList()
            shared.pendingEpisodeIndex = -1
            shared.pendingSeriesTitle  = ""
            navController.navigate("player")
        }
        voiceVm.onVoiceSearch = { query, type ->
            shared.postVoiceSearch(query, type)
        }
        voiceVm.onPlayerControl = { _ -> }
    }

    // ── Observe voice search → navigate ───────────────────────
    val voiceSearch by shared.voiceSearch.collectAsState()
    LaunchedEffect(voiceSearch) {
        voiceSearch?.let { cmd ->
            val route = when (cmd.type) {
                "live"   -> "live"
                "series" -> "series"
                "movies" -> "movies"
                else     -> null
            }
            route?.let {
                navController.navigate(it) {
                    popUpTo("home") { saveState = true }
                    launchSingleTop = true
                    restoreState    = true
                }
            }
        }
    }

    // ── Simplified mode: bypass normal nav ────────────────────
    CompositionLocalProvider(LocalTtsSpeakFn provides ttsSpeakFn) {
    if (simplified) {
        Column(modifier = Modifier.fillMaxSize()) {
            AnimatedVisibility(
                visible = updateAvailable && showUpdateBanner,
                enter = slideInVertically { -it },
                exit  = slideOutVertically { -it },
            ) {
                UpdateBanner(apkUrl = updateUrl, onDismiss = { showUpdateBanner = false })
            }
            SimplifiedModeScreen(
                onMovies = {
                    navController.navigate("movies") {
                        popUpTo("home") { saveState = true }
                        launchSingleTop = true
                    }
                    prefsVm.setSimplified(false)
                },
                onSeries = {
                    navController.navigate("series") {
                        popUpTo("home") { saveState = true }
                        launchSingleTop = true
                    }
                    prefsVm.setSimplified(false)
                },
                onLive = {
                    navController.navigate("live") {
                        popUpTo("home") { saveState = true }
                        launchSingleTop = true
                    }
                    prefsVm.setSimplified(false)
                },
                onContinue = { progress ->
                    shared.pendingItem = Contenido(
                        id        = progress.itemId,
                        title     = progress.title,
                        type      = progress.type,
                        streamUrl = progress.streamUrl,
                        image     = progress.image,
                        season    = progress.season,
                        episode   = progress.episode,
                    )
                    shared.pendingSeriesTitle  = progress.seriesTitle ?: ""
                    shared.pendingEpisodeList  = emptyList()
                    shared.pendingEpisodeIndex = -1
                    navController.navigate("player")
                },
            )
        }
    } else {
    Column(modifier = Modifier.fillMaxSize()) {
        AnimatedVisibility(
            visible = updateAvailable && showUpdateBanner,
            enter = slideInVertically { -it },
            exit  = slideOutVertically { -it },
        ) {
            UpdateBanner(apkUrl = updateUrl, onDismiss = { showUpdateBanner = false })
        }

        NavHost(
            navController    = navController,
            startDestination = "home",
            modifier         = Modifier.weight(1f),
        ) {
            composable("home") {
                MainScaffold(navController, if (hasMicPerm) voiceVm else null) {
                    HomeScreen(
                        onMovieClick = { item ->
                            shared.pendingItem = item
                            shared.pendingEpisodeList  = emptyList()
                            shared.pendingEpisodeIndex = -1
                            shared.pendingSeriesTitle  = ""
                            navController.navigate("player")
                        },
                        onSeriesClick = { title ->
                            shared.pendingSeriesTitle = title
                            navController.navigate("series_detail")
                        },
                        onContinueWatchingClick = { progress ->
                            shared.pendingItem = Contenido(
                                id        = progress.itemId,
                                title     = progress.title,
                                type      = progress.type,
                                streamUrl = progress.streamUrl,
                                image     = progress.image,
                                season    = progress.season,
                                episode   = progress.episode,
                            )
                            shared.pendingSeriesTitle  = progress.seriesTitle ?: ""
                            shared.pendingEpisodeList  = emptyList()
                            shared.pendingEpisodeIndex = -1
                            navController.navigate("player")
                        },
                    )
                }
            }

            composable("movies") {
                val cmd by shared.voiceSearch.collectAsState()
                val voiceQuery = cmd?.takeIf { it.type == "movies" || it.type == null }?.query
                MainScaffold(navController, if (hasMicPerm) voiceVm else null) {
                    MoviesScreen(
                        onItemClick = { item ->
                            shared.pendingItem = item
                            shared.pendingEpisodeList  = emptyList()
                            shared.pendingEpisodeIndex = -1
                            shared.pendingSeriesTitle  = ""
                            navController.navigate("player")
                        },
                        voiceQuery = voiceQuery,
                        onVoiceQueryConsumed = { shared.consumeVoiceSearch() },
                    )
                }
            }

            composable("series") {
                val cmd by shared.voiceSearch.collectAsState()
                val voiceQuery = cmd?.takeIf { it.type == "series" || it.type == null }?.query
                MainScaffold(navController, if (hasMicPerm) voiceVm else null) {
                    SeriesScreen(
                        onSeriesClick = { title ->
                            shared.pendingSeriesTitle = title
                            navController.navigate("series_detail")
                        },
                        voiceQuery = voiceQuery,
                        onVoiceQueryConsumed = { shared.consumeVoiceSearch() },
                    )
                }
            }

            composable("live") {
                val cmd by shared.voiceSearch.collectAsState()
                val voiceQuery = cmd?.takeIf { it.type == "live" || it.type == null }?.query
                MainScaffold(navController, if (hasMicPerm) voiceVm else null) {
                    LiveScreen(
                        onChannelClick = { channel ->
                            shared.pendingItem = channel
                            shared.pendingEpisodeList  = emptyList()
                            shared.pendingEpisodeIndex = -1
                            shared.pendingSeriesTitle  = ""
                            navController.navigate("player")
                        },
                        onSettingsClick = { navController.navigate("live_scan_config") },
                        voiceQuery = voiceQuery,
                        onVoiceQueryConsumed = { shared.consumeVoiceSearch() },
                    )
                }
            }

            composable("settings") {
                MainScaffold(navController, if (hasMicPerm) voiceVm else null) {
                    SettingsScreen(prefsVm = prefsVm)
                }
            }

            composable("series_detail") {
                SeriesDetailScreen(
                    seriesTitle = shared.pendingSeriesTitle,
                    onBack = { navController.popBackStack() },
                    onEpisodeClick = { episode, allEpisodes, index ->
                        shared.pendingItem = episode
                        shared.pendingEpisodeList  = allEpisodes
                        shared.pendingEpisodeIndex = index
                        navController.navigate("player")
                    },
                )
            }

            composable("player") {
                val item = shared.pendingItem
                if (item != null) {
                    PlayerScreen(
                        item         = item,
                        episodeList  = shared.pendingEpisodeList,
                        episodeIndex = shared.pendingEpisodeIndex,
                        seriesTitle  = shared.pendingSeriesTitle.ifBlank { null },
                        onBack       = { navController.popBackStack() },
                    )
                }
            }

            composable("live_scan_config") {
                LiveScanConfigScreen(onBack = { navController.popBackStack() })
            }
        }
    }
    } // end else
    } // end CompositionLocalProvider(LocalTtsSpeakFn)
}


// ── Update banner ──────────────────────────────────────────────

@Composable
private fun UpdateBanner(apkUrl: String, onDismiss: () -> Unit) {
    val context = LocalContext.current
    Surface(color = Color(0xFF1A3A1A)) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                Icons.Default.SystemUpdate,
                contentDescription = null,
                tint = Color(0xFF66BB6A),
                modifier = Modifier.size(20.dp),
            )
            Column(modifier = Modifier.weight(1f).padding(start = 8.dp)) {
                Text("Nueva versión disponible", color = Color.White, fontSize = 13.sp)
                TextButton(
                    onClick = {
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(apkUrl)))
                    },
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp),
                ) {
                    Text("Descargar actualización", color = Color(0xFF66BB6A), fontSize = 12.sp)
                }
            }
            IconButton(onClick = onDismiss, modifier = Modifier.size(32.dp)) {
                Icon(Icons.Default.Close, null, tint = Color.Gray, modifier = Modifier.size(16.dp))
            }
        }
    }
}

// ── Scaffold with bottom nav + voice FAB ──────────────────────

@Composable
private fun MainScaffold(
    navController: NavController,
    voiceVm: VoiceAssistantViewModel?,
    content: @Composable () -> Unit,
) {
    val backStack by navController.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route

    Scaffold(
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
                TABS.forEach { tab ->
                    NavigationBarItem(
                        selected = currentRoute == tab.route,
                        onClick  = {
                            if (currentRoute != tab.route) {
                                navController.navigate(tab.route) {
                                    popUpTo("home") { saveState = true }
                                    launchSingleTop = true
                                    restoreState    = true
                                }
                            }
                        },
                        icon    = { Icon(tab.icon, contentDescription = tab.label) },
                        label   = { Text(tab.label) },
                        colors  = NavigationBarItemDefaults.colors(
                            selectedIconColor   = MaterialTheme.colorScheme.primary,
                            selectedTextColor   = MaterialTheme.colorScheme.primary,
                            unselectedIconColor = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                            unselectedTextColor = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                            indicatorColor      = MaterialTheme.colorScheme.primary.copy(alpha = 0.15f),
                        ),
                    )
                }
            }
        },
        containerColor = MaterialTheme.colorScheme.background,
    ) { innerPadding ->
        Box(modifier = Modifier.padding(innerPadding)) {
            content()

            if (voiceVm != null) {
                VoiceAssistantOverlay(
                    viewModel = voiceVm,
                    modifier  = Modifier
                        .align(Alignment.BottomEnd)
                        .padding(end = 16.dp, bottom = 16.dp)
                        .size(56.dp),
                )
            }
        }
    }
}
