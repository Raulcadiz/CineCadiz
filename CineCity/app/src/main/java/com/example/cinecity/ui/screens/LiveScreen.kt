package com.example.cinecity.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.cinecity.data.model.Contenido
import com.example.cinecity.ui.components.CineSearchBar
import com.example.cinecity.ui.components.ErrorState
import com.example.cinecity.ui.components.LiveChannelRow
import com.example.cinecity.ui.components.LoadingIndicator
import com.example.cinecity.ui.theme.CineDivider
import com.example.cinecity.viewmodel.LiveViewModel

@Composable
fun LiveScreen(
    onChannelClick: (Contenido) -> Unit,
    onSettingsClick: (() -> Unit)? = null,
    viewModel: LiveViewModel = viewModel(),
) {
    val state by viewModel.state.collectAsState()

    // Categoría seleccionada para filtrar ("" = todas)
    var selectedGroup by remember { mutableStateOf("") }

    // Resetear filtro cuando cambia la búsqueda
    LaunchedEffect(state.query) {
        if (state.query.isNotBlank()) selectedGroup = ""
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        // ── Barra de búsqueda + botón de ajustes ──────────────
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(modifier = Modifier.weight(1f)) {
                CineSearchBar(
                    query = state.query,
                    onQueryChange = viewModel::onQueryChange,
                    placeholder = "Buscar canal...",
                )
            }
            if (onSettingsClick != null) {
                IconButton(onClick = onSettingsClick) {
                    Icon(
                        Icons.Default.Settings,
                        contentDescription = "Configuración de escaneo",
                        tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
                    )
                }
            }
        }

        when {
            state.isLoading -> LoadingIndicator()
            state.error != null && state.items.isEmpty() ->
                ErrorState(state.error, onRetry = { viewModel.load() })
            state.items.isEmpty() -> {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(32.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = "No se encontraron canales",
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                    )
                }
            }
            else -> {
                // ── Chips de categorías ───────────────────────
                val groups = remember(state.items) {
                    state.items
                        .mapNotNull { it.groupTitle?.takeIf { g -> g.isNotBlank() } }
                        .distinct()
                        .sorted()
                }

                if (groups.isNotEmpty() && state.query.isBlank()) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .horizontalScroll(rememberScrollState())
                            .background(MaterialTheme.colorScheme.background)
                            .padding(horizontal = 12.dp, vertical = 6.dp),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        // Chip "Todas"
                        FilterChip(
                            selected = selectedGroup.isEmpty(),
                            onClick = { selectedGroup = "" },
                            label = { Text("Todas") },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = MaterialTheme.colorScheme.primary,
                                selectedLabelColor = MaterialTheme.colorScheme.onPrimary,
                            ),
                        )
                        groups.forEach { group ->
                            FilterChip(
                                selected = selectedGroup == group,
                                onClick = { selectedGroup = if (selectedGroup == group) "" else group },
                                label = { Text(group) },
                                colors = FilterChipDefaults.filterChipColors(
                                    selectedContainerColor = MaterialTheme.colorScheme.primary,
                                    selectedLabelColor = MaterialTheme.colorScheme.onPrimary,
                                ),
                            )
                        }
                    }
                    HorizontalDivider(thickness = 0.5.dp, color = CineDivider)
                }

                // ── Lista de canales filtrada ─────────────────
                val visibleItems = if (selectedGroup.isEmpty()) {
                    state.items
                } else {
                    state.items.filter { it.groupTitle == selectedGroup }
                }

                val grouped = visibleItems.groupBy { it.groupTitle ?: "" }

                // Contador de canales
                Text(
                    text = "${visibleItems.size} canal${if (visibleItems.size != 1) "es" else ""}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f),
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                )

                LazyColumn(
                    modifier = Modifier.weight(1f),
                    contentPadding = PaddingValues(bottom = 80.dp),
                ) {
                    grouped.forEach { (group, channels) ->
                        // Solo mostrar header de grupo si no hay filtro activo
                        // (con filtro, el grupo ya es obvio)
                        if (group.isNotBlank() && selectedGroup.isEmpty()) {
                            item {
                                Text(
                                    text = group,
                                    style = MaterialTheme.typography.labelMedium,
                                    color = MaterialTheme.colorScheme.primary,
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .background(MaterialTheme.colorScheme.surface)
                                        .padding(horizontal = 16.dp, vertical = 6.dp),
                                )
                            }
                        }
                        items(channels, key = { it.id }) { channel ->
                            LiveChannelRow(
                                imageUrl = channel.image,
                                title = channel.title,
                                groupTitle = null,
                                onClick = { onChannelClick(channel) },
                            )
                            HorizontalDivider(color = CineDivider, thickness = 0.5.dp)
                        }
                    }
                }
            }
        }
    }
}
