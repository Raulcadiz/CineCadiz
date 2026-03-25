package com.example.cinecity

import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import android.os.Bundle
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.LiveTv
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.Tv
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.example.cinecity.data.WatchProgress
import com.example.cinecity.data.WatchProgressManager
import com.example.cinecity.data.model.Contenido
import com.example.cinecity.ui.screens.*
import com.example.cinecity.ui.theme.CineCityTheme
import com.example.cinecity.viewmodel.SharedViewModel

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WatchProgressManager.init(this)
        enableEdgeToEdge()
        setContent {
            CineCityTheme {
                CineCityApp()
            }
        }
    }
}

// ── Navigation destinations ────────────────────────────────────

private sealed class Tab(val route: String, val label: String, val icon: ImageVector) {
    data object Home   : Tab("home",   "Inicio",    Icons.Default.Home)
    data object Movies : Tab("movies", "Películas", Icons.Default.Movie)
    data object Series : Tab("series", "Series",    Icons.Default.Tv)
    data object Live   : Tab("live",   "Directo",   Icons.Default.LiveTv)
}

private val TABS = listOf(Tab.Home, Tab.Movies, Tab.Series, Tab.Live)

// ── Root composable ────────────────────────────────────────────

@Composable
fun CineCityApp() {
    val navController = rememberNavController()
    val shared: SharedViewModel = viewModel()

    NavHost(navController = navController, startDestination = "home") {
        composable("home") {
            MainScaffold(navController = navController) {
                HomeScreen(
                    onMovieClick = { item ->
                        shared.pendingItem = item
                        shared.pendingEpisodeList = emptyList()
                        shared.pendingEpisodeIndex = -1
                        shared.pendingSeriesTitle = ""
                        navController.navigate("player")
                    },
                    onSeriesClick = { title ->
                        shared.pendingSeriesTitle = title
                        navController.navigate("series_detail")
                    },
                    onContinueWatchingClick = { progress ->
                        shared.pendingItem = Contenido(
                            id = progress.itemId,
                            title = progress.title,
                            type = progress.type,
                            streamUrl = progress.streamUrl,
                            image = progress.image,
                            season = progress.season,
                            episode = progress.episode,
                        )
                        shared.pendingSeriesTitle = progress.seriesTitle ?: ""
                        shared.pendingEpisodeList = emptyList()
                        shared.pendingEpisodeIndex = -1
                        navController.navigate("player")
                    },
                )
            }
        }

        composable("movies") {
            MainScaffold(navController = navController) {
                MoviesScreen(
                    onItemClick = { item ->
                        shared.pendingItem = item
                        shared.pendingEpisodeList = emptyList()
                        shared.pendingEpisodeIndex = -1
                        shared.pendingSeriesTitle = ""
                        navController.navigate("player")
                    },
                )
            }
        }

        composable("series") {
            MainScaffold(navController = navController) {
                SeriesScreen(
                    onSeriesClick = { title ->
                        shared.pendingSeriesTitle = title
                        navController.navigate("series_detail")
                    },
                )
            }
        }

        composable("live") {
            MainScaffold(navController = navController) {
                LiveScreen(
                    onChannelClick = { channel ->
                        shared.pendingItem = channel
                        shared.pendingEpisodeList = emptyList()
                        shared.pendingEpisodeIndex = -1
                        shared.pendingSeriesTitle = ""
                        navController.navigate("player")
                    },
                    onSettingsClick = { navController.navigate("live_scan_config") },
                )
            }
        }

        composable("series_detail") {
            val title = shared.pendingSeriesTitle
            SeriesDetailScreen(
                seriesTitle = title,
                onBack = { navController.popBackStack() },
                onEpisodeClick = { episode, allEpisodes, index ->
                    shared.pendingItem = episode
                    shared.pendingEpisodeList = allEpisodes
                    shared.pendingEpisodeIndex = index
                    navController.navigate("player")
                },
            )
        }

        composable("player") {
            val item = shared.pendingItem
            if (item != null) {
                PlayerScreen(
                    item = item,
                    episodeList = shared.pendingEpisodeList,
                    episodeIndex = shared.pendingEpisodeIndex,
                    seriesTitle = shared.pendingSeriesTitle.ifBlank { null },
                    onBack = { navController.popBackStack() },
                )
            }
        }

        composable("live_scan_config") {
            LiveScanConfigScreen(
                onBack = { navController.popBackStack() },
            )
        }
    }
}

// ── Scaffold with bottom nav ───────────────────────────────────

@Composable
private fun MainScaffold(
    navController: NavController,
    content: @Composable () -> Unit,
) {
    val backStack by navController.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route

    Scaffold(
        bottomBar = {
            NavigationBar(
                containerColor = MaterialTheme.colorScheme.surface,
            ) {
                TABS.forEach { tab ->
                    NavigationBarItem(
                        selected = currentRoute == tab.route,
                        onClick = {
                            if (currentRoute != tab.route) {
                                navController.navigate(tab.route) {
                                    popUpTo("home") { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            }
                        },
                        icon = { Icon(tab.icon, contentDescription = tab.label) },
                        label = { Text(tab.label) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = MaterialTheme.colorScheme.primary,
                            selectedTextColor = MaterialTheme.colorScheme.primary,
                            unselectedIconColor = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                            unselectedTextColor = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                            indicatorColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.15f),
                        ),
                    )
                }
            }
        },
        containerColor = MaterialTheme.colorScheme.background,
    ) { innerPadding ->
        androidx.compose.foundation.layout.Box(
            modifier = Modifier.padding(innerPadding),
        ) {
            content()
        }
    }
}
