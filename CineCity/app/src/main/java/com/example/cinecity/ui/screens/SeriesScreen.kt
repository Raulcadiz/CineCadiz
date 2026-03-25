package com.example.cinecity.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlaylistPlay
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.example.cinecity.data.api.ApiClient
import com.example.cinecity.data.model.SerieAgrupada
import com.example.cinecity.ui.components.CineSearchBar
import com.example.cinecity.ui.components.ErrorState
import com.example.cinecity.ui.components.LoadingIndicator
import com.example.cinecity.ui.theme.CineCard
import com.example.cinecity.ui.theme.CineSubtext
import com.example.cinecity.viewmodel.SeriesViewModel

@Composable
fun SeriesScreen(
    onSeriesClick: (String) -> Unit,
    viewModel: SeriesViewModel = viewModel(),
) {
    val state by viewModel.state.collectAsState()
    val gridState = rememberLazyGridState()
    val focusManager = LocalFocusManager.current

    // Prevent keyboard from opening automatically on screen enter
    LaunchedEffect(Unit) { focusManager.clearFocus() }

    val shouldLoadMore by remember {
        derivedStateOf {
            val lastVisible = gridState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0
            val total = gridState.layoutInfo.totalItemsCount
            lastVisible >= total - 6
        }
    }
    LaunchedEffect(shouldLoadMore) {
        if (shouldLoadMore && state.items.isNotEmpty()) viewModel.loadMore()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        CineSearchBar(
            query = state.query,
            onQueryChange = viewModel::onQueryChange,
            placeholder = "Buscar serie...",
        )

        when {
            state.isLoading -> LoadingIndicator()
            state.error != null && state.items.isEmpty() ->
                ErrorState(state.error, onRetry = { viewModel.load() })
            else -> {
                LazyVerticalGrid(
                    columns = GridCells.Adaptive(minSize = 110.dp),
                    state = gridState,
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                    modifier = Modifier.weight(1f),
                ) {
                    items(state.items, key = { it.id }) { serie ->
                        SerieCard(serie = serie, onClick = { onSeriesClick(serie.title) })
                    }
                    if (state.isLoadingMore) {
                        item(span = { GridItemSpan(maxLineSpan) }) {
                            Box(
                                Modifier
                                    .fillMaxWidth()
                                    .padding(16.dp),
                                contentAlignment = Alignment.Center,
                            ) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(28.dp),
                                    color = MaterialTheme.colorScheme.primary,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SerieCard(serie: SerieAgrupada, onClick: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(2f / 3f)
                .clip(RoundedCornerShape(8.dp))
                .background(CineCard),
            contentAlignment = Alignment.Center,
        ) {
            val proxied = ApiClient.imageProxyUrl(serie.image)
            if (!proxied.isNullOrBlank()) {
                AsyncImage(
                    model = proxied,
                    contentDescription = serie.title,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .fillMaxSize()
                        .clip(RoundedCornerShape(8.dp)),
                )
            } else {
                Icon(
                    Icons.Default.PlaylistPlay,
                    contentDescription = null,
                    tint = Color(0xFF555555),
                    modifier = Modifier.size(40.dp),
                )
            }

            // Episode count badge
            Surface(
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    .padding(4.dp),
                shape = MaterialTheme.shapes.extraSmall,
                color = Color.Black.copy(alpha = 0.75f),
            ) {
                Text(
                    text = "${serie.episodeCount} ep",
                    style = MaterialTheme.typography.labelSmall,
                    color = Color.White,
                    modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp),
                )
            }
        }

        Spacer(Modifier.height(6.dp))
        Text(
            text = serie.title,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            text = buildString {
                serie.year?.let { append(it) }
                if (serie.seasonCount > 1) {
                    if (isNotEmpty()) append(" · ")
                    append("${serie.seasonCount}T")
                }
            }.ifBlank { serie.genres.firstOrNull() ?: "" },
            style = MaterialTheme.typography.labelSmall,
            color = CineSubtext,
            maxLines = 1,
        )
    }
}
