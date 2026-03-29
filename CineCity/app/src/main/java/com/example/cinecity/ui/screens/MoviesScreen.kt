package com.example.cinecity.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.cinecity.data.model.Contenido
import com.example.cinecity.ui.components.CineSearchBar
import com.example.cinecity.ui.components.ContentCard
import com.example.cinecity.ui.components.ErrorState
import com.example.cinecity.ui.components.LoadingIndicator
import com.example.cinecity.viewmodel.MoviesViewModel

@Composable
fun MoviesScreen(
    onItemClick: (Contenido) -> Unit,
    voiceQuery: String? = null,
    onVoiceQueryConsumed: () -> Unit = {},
    viewModel: MoviesViewModel = viewModel(),
) {
    val state by viewModel.state.collectAsState()
    val gridState = rememberLazyGridState()
    val focusManager = LocalFocusManager.current

    // Prevent keyboard from opening automatically on screen enter
    LaunchedEffect(Unit) { focusManager.clearFocus() }

    // Voice search — apply when a new voice query arrives
    LaunchedEffect(voiceQuery) {
        if (!voiceQuery.isNullOrBlank()) {
            viewModel.onQueryChange(voiceQuery)
            onVoiceQueryConsumed()
        }
    }

    // Infinite scroll trigger
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
            placeholder = "Buscar película...",
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
                    items(state.items, key = { it.id }) { item ->
                        ContentCard(
                            imageUrl = item.image,
                            title = item.title,
                            subtitle = item.year?.toString(),
                            onClick = { onItemClick(item) },
                        )
                    }
                    if (state.isLoadingMore) {
                        item(span = { GridItemSpan(maxLineSpan) }) {
                            Box(
                                Modifier
                                    .fillMaxWidth()
                                    .padding(16.dp),
                                contentAlignment = androidx.compose.ui.Alignment.Center,
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
