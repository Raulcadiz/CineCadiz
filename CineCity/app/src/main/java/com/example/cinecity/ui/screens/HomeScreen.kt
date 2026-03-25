package com.example.cinecity.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.example.cinecity.data.WatchProgress
import com.example.cinecity.data.WatchProgressManager
import com.example.cinecity.data.api.ApiClient
import com.example.cinecity.data.model.Contenido
import com.example.cinecity.ui.components.ContentCard
import com.example.cinecity.ui.components.ErrorState
import com.example.cinecity.ui.components.LoadingIndicator
import com.example.cinecity.ui.theme.CineCard
import com.example.cinecity.ui.theme.CineSubtext
import com.example.cinecity.viewmodel.HomeViewModel

@Composable
fun HomeScreen(
    onMovieClick: (Contenido) -> Unit,
    onSeriesClick: (String) -> Unit,
    onContinueWatchingClick: (WatchProgress) -> Unit,
    viewModel: HomeViewModel = viewModel(),
) {
    val state by viewModel.state.collectAsState()
    val continueWatching by WatchProgressManager.items.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState()),
    ) {
        // Header
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surface)
                .padding(horizontal = 20.dp, vertical = 16.dp),
        ) {
            Text(
                text = "CineCadiz",
                style = MaterialTheme.typography.headlineMedium,
                color = MaterialTheme.colorScheme.primary,
            )
        }

        Spacer(Modifier.height(8.dp))

        // Continue Watching
        if (continueWatching.isNotEmpty()) {
            ContinueWatchingSection(
                items = continueWatching,
                onClick = onContinueWatchingClick,
            )
        }

        when {
            state.isLoading -> LoadingIndicator()
            state.error != null -> ErrorState(state.error, onRetry = { viewModel.load() })
            else -> {
                val movies = state.trending.filter { it.type == "movie" }

                // For series: deduplicate by base title, keep most recent per series
                val seriesGrouped = state.trending
                    .filter { it.type == "series" || it.season != null }
                    .groupBy { extractBaseTitle(it.title) }
                    .map { (_, episodes) -> episodes.first() }  // keep first (most recent)

                if (state.trending.isNotEmpty()) {
                    TrendingSection(
                        label = "Novedades",
                        items = (movies + seriesGrouped)
                            .sortedByDescending { it.addedAt }
                            .take(20),
                        onMovieClick = onMovieClick,
                        onSeriesClick = onSeriesClick,
                    )
                }
                if (movies.isNotEmpty()) {
                    TrendingSection(
                        label = "Películas recientes",
                        items = movies,
                        onMovieClick = onMovieClick,
                        onSeriesClick = onSeriesClick,
                    )
                }
                if (seriesGrouped.isNotEmpty()) {
                    TrendingSection(
                        label = "Series",
                        items = seriesGrouped,
                        onMovieClick = onMovieClick,
                        onSeriesClick = onSeriesClick,
                    )
                }
            }
        }

        Spacer(Modifier.height(80.dp))
    }
}

@Composable
private fun ContinueWatchingSection(
    items: List<WatchProgress>,
    onClick: (WatchProgress) -> Unit,
) {
    Column(modifier = Modifier.padding(top = 8.dp)) {
        Text(
            text = "Continuar viendo",
            style = MaterialTheme.typography.titleSmall,
            color = MaterialTheme.colorScheme.onBackground,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
        )
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items.forEach { progress ->
                ContinueWatchingCard(progress = progress, onClick = { onClick(progress) })
            }
        }
    }
}

@Composable
private fun ContinueWatchingCard(progress: WatchProgress, onClick: () -> Unit) {
    Column(
        modifier = Modifier
            .width(140.dp)
            .clickable(onClick = onClick),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(16f / 9f)
                .clip(RoundedCornerShape(8.dp))
                .background(CineCard),
        ) {
            val proxied = ApiClient.imageProxyUrl(progress.image)
            if (!proxied.isNullOrBlank()) {
                AsyncImage(
                    model = proxied,
                    contentDescription = progress.title,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize(),
                )
            }
            // Red progress bar
            Box(
                modifier = Modifier
                    .align(Alignment.BottomStart)
                    .fillMaxWidth()
                    .height(3.dp)
                    .background(Color(0xFF333333)),
            )
            Box(
                modifier = Modifier
                    .align(Alignment.BottomStart)
                    .fillMaxWidth(progress.progressFraction)
                    .height(3.dp)
                    .background(Color(0xFFE50914)),
            )
        }
        Spacer(Modifier.height(4.dp))
        Text(
            text = if (progress.season != null && progress.episode != null)
                "T${progress.season} E${progress.episode}"
            else progress.title,
            style = MaterialTheme.typography.labelSmall,
            color = CineSubtext,
            maxLines = 1,
        )
        Text(
            text = if (progress.season != null) progress.seriesTitle ?: progress.title
            else progress.title,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun TrendingSection(
    label: String,
    items: List<Contenido>,
    onMovieClick: (Contenido) -> Unit,
    onSeriesClick: (String) -> Unit,
) {
    Column(modifier = Modifier.padding(top = 16.dp)) {
        Text(
            text = label,
            style = MaterialTheme.typography.titleSmall,
            color = MaterialTheme.colorScheme.onBackground,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
        )
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items.forEach { item ->
                ContentCard(
                    imageUrl = item.image,
                    title = if (item.type == "series" || item.season != null)
                        extractBaseTitle(item.title)
                    else item.title,
                    subtitle = item.year?.toString() ?: item.genres.firstOrNull(),
                    onClick = {
                        if (item.type == "series" || item.season != null) {
                            onSeriesClick(extractBaseTitle(item.title))
                        } else {
                            onMovieClick(item)
                        }
                    },
                )
            }
        }
    }
}

private fun extractBaseTitle(title: String): String {
    val patterns = listOf(
        Regex("""\s+[Ss]\d{1,3}\s*[Ee]\d{1,3}.*$"""),
        Regex("""\s+\d{1,2}[xX]\d{1,3}.*$"""),
        Regex("""\s+[Ss]\d{1,2}\b.*$"""),
    )
    var result = title.trim()
    for (p in patterns) {
        val new = p.replace(result, "").trim(' ', '-', '–', ':')
        if (new.isNotBlank()) result = new
    }
    return result
}
