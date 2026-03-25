package com.example.cinecity.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.cinecity.data.model.Contenido
import com.example.cinecity.ui.components.ErrorState
import com.example.cinecity.ui.components.LoadingIndicator
import com.example.cinecity.ui.theme.CineDivider
import com.example.cinecity.ui.theme.CineSubtext
import com.example.cinecity.viewmodel.SeriesDetailViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SeriesDetailScreen(
    seriesTitle: String,
    onBack: () -> Unit,
    onEpisodeClick: (Contenido, List<Contenido>, Int) -> Unit,
    viewModel: SeriesDetailViewModel = viewModel(),
) {
    LaunchedEffect(seriesTitle) {
        viewModel.loadEpisodes(seriesTitle)
    }

    val state by viewModel.state.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = seriesTitle,
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface,
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Volver",
                            tint = MaterialTheme.colorScheme.onSurface,
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                ),
            )
        },
        containerColor = MaterialTheme.colorScheme.background,
    ) { padding ->
        when {
            state.isLoading -> {
                Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                    LoadingIndicator()
                }
            }
            state.error != null -> {
                Box(Modifier.fillMaxSize().padding(padding)) {
                    ErrorState(state.error, onRetry = { viewModel.loadEpisodes(seriesTitle) })
                }
            }
            state.episodesBySeason.isEmpty() -> {
                Box(
                    Modifier.fillMaxSize().padding(padding),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("No se encontraron episodios", color = CineSubtext)
                }
            }
            else -> {
                // Flatten all episodes in order for auto-next navigation
                val allEpisodes = state.episodesBySeason.values.flatten()

                LazyColumn(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    contentPadding = PaddingValues(bottom = 24.dp),
                ) {
                    state.episodesBySeason.forEach { (season, episodes) ->
                        item {
                            Text(
                                text = "Temporada $season",
                                style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold),
                                color = MaterialTheme.colorScheme.primary,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .background(MaterialTheme.colorScheme.surface)
                                    .padding(horizontal = 16.dp, vertical = 10.dp),
                            )
                        }
                        items(episodes, key = { it.id }) { episode ->
                            val globalIndex = allEpisodes.indexOf(episode)
                            EpisodeRow(
                                episode = episode,
                                onClick = { onEpisodeClick(episode, allEpisodes, globalIndex) },
                            )
                            HorizontalDivider(color = CineDivider, thickness = 0.5.dp)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun EpisodeRow(episode: Contenido, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Surface(
            shape = MaterialTheme.shapes.small,
            color = MaterialTheme.colorScheme.surfaceVariant,
        ) {
            Text(
                text = episode.episode?.toString()?.padStart(2, '0') ?: "–",
                style = MaterialTheme.typography.labelMedium,
                color = CineSubtext,
                modifier = Modifier
                    .padding(horizontal = 8.dp, vertical = 4.dp)
                    .widthIn(min = 28.dp),
            )
        }

        Spacer(Modifier.width(12.dp))

        Column(Modifier.weight(1f)) {
            Text(
                text = episode.title,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface,
                maxLines = 2,
            )
            if (!episode.server.isNullOrBlank()) {
                Text(
                    text = episode.server!!,
                    style = MaterialTheme.typography.labelSmall,
                    color = CineSubtext,
                )
            }
        }

        Icon(
            Icons.Default.PlayArrow,
            contentDescription = "Reproducir",
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(28.dp),
        )
    }
}
