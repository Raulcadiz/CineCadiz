package com.example.cinecity.ui.screens

import androidx.compose.foundation.background
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
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.cinecity.viewmodel.LiveViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LiveScanConfigScreen(
    onBack: () -> Unit,
    viewModel: LiveViewModel = viewModel(),
) {
    val scanState by viewModel.scanState.collectAsState()

    // Cargar config y reportes al entrar
    LaunchedEffect(Unit) {
        viewModel.loadScanConfig()
        viewModel.loadScanReports()
    }

    // Estado local para los controles (se sincronizan con la config cargada)
    var autoEnabled by remember { mutableStateOf(true) }
    var intervalHours by remember { mutableIntStateOf(24) }

    // Sincronizar controles cuando llega la config del servidor
    LaunchedEffect(scanState.config) {
        autoEnabled = scanState.config.autoScanEnabled
        intervalHours = scanState.config.intervalHours
    }

    // Snackbar para mensajes
    val snackbarHostState = remember { SnackbarHostState() }
    LaunchedEffect(scanState.message) {
        if (scanState.message != null) {
            snackbarHostState.showSnackbar(scanState.message!!)
            viewModel.clearMessage()
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        topBar = {
            TopAppBar(
                title = { Text("Configuración de escaneo") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Volver")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                ),
            )
        },
        containerColor = MaterialTheme.colorScheme.background,
    ) { innerPadding ->

        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {

            // ── Sección: Escaneo automático ──────────────────
            item {
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surface,
                    ),
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(
                            text = "Escaneo automático",
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onSurface,
                        )
                        Spacer(Modifier.height(12.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = "Activar escaneo automático",
                                    style = MaterialTheme.typography.bodyMedium,
                                )
                                Text(
                                    text = "Verifica canales caídos y hace failover automáticamente",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                                )
                            }
                            Switch(
                                checked = autoEnabled,
                                onCheckedChange = { autoEnabled = it },
                            )
                        }

                        if (autoEnabled) {
                            Spacer(Modifier.height(16.dp))
                            Text(
                                text = "Intervalo de escaneo",
                                style = MaterialTheme.typography.bodyMedium,
                            )
                            Spacer(Modifier.height(8.dp))

                            Row(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                listOf(24, 48, 72).forEach { h ->
                                    FilterChip(
                                        selected = intervalHours == h,
                                        onClick = { intervalHours = h },
                                        label = { Text("${h}h") },
                                        colors = FilterChipDefaults.filterChipColors(
                                            selectedContainerColor = MaterialTheme.colorScheme.primary,
                                            selectedLabelColor = MaterialTheme.colorScheme.onPrimary,
                                        ),
                                    )
                                }
                            }

                            if (scanState.config.lastScan != null) {
                                Spacer(Modifier.height(8.dp))
                                Text(
                                    text = "Último scan: ${scanState.config.lastScan?.take(19)?.replace('T', ' ')}",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                                )
                            }
                        }

                        Spacer(Modifier.height(16.dp))

                        Button(
                            onClick = { viewModel.saveScanConfig(autoEnabled, intervalHours) },
                            enabled = !scanState.isSaving,
                            modifier = Modifier.fillMaxWidth(),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = MaterialTheme.colorScheme.primary,
                            ),
                        ) {
                            if (scanState.isSaving) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(16.dp),
                                    color = MaterialTheme.colorScheme.onPrimary,
                                    strokeWidth = 2.dp,
                                )
                                Spacer(Modifier.width(8.dp))
                            }
                            Text("Guardar configuración")
                        }
                    }
                }
            }

            // ── Sección: Escanear ahora ──────────────────────
            item {
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surface,
                    ),
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(
                            text = "Escaneo manual",
                            style = MaterialTheme.typography.titleMedium,
                        )
                        Spacer(Modifier.height(8.dp))
                        Text(
                            text = "Lanza una verificación inmediata de todos los canales en directo, independientemente de la configuración automática.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                        )
                        Spacer(Modifier.height(12.dp))

                        OutlinedButton(
                            onClick = {
                                viewModel.runScanNow()
                                viewModel.loadScanReports()
                            },
                            enabled = !scanState.scanRunning,
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            if (scanState.scanRunning) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(16.dp),
                                    strokeWidth = 2.dp,
                                )
                                Spacer(Modifier.width(8.dp))
                                Text("Escaneando...")
                            } else {
                                Icon(
                                    Icons.Default.PlayArrow,
                                    contentDescription = null,
                                    modifier = Modifier.size(18.dp),
                                )
                                Spacer(Modifier.width(6.dp))
                                Text("Escanear ahora")
                            }
                        }
                    }
                }
            }

            // ── Sección: Reportes de caídas ──────────────────
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = "URLs caídas (últimos 7 días)",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    if (scanState.reportsLoading) {
                        CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                    } else {
                        TextButton(onClick = { viewModel.loadScanReports() }) {
                            Text("Actualizar")
                        }
                    }
                }
            }

            if (scanState.reports.isEmpty() && !scanState.reportsLoading) {
                item {
                    Text(
                        text = "No se han detectado caídas recientes",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                        modifier = Modifier.padding(vertical = 8.dp),
                    )
                }
            }

            items(scanState.reports, key = { it.id }) { report ->
                ScanReportRow(
                    channelTitle = report.channelTitle,
                    url = report.urlProbada,
                    timestamp = report.timestamp.take(19).replace('T', ' '),
                    latencyMs = report.latenciaMs,
                )
            }
        }
    }
}

@Composable
private fun ScanReportRow(
    channelTitle: String,
    url: String,
    timestamp: String,
    latencyMs: Int?,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(
                MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.15f),
                MaterialTheme.shapes.small,
            )
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = channelTitle,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.error,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = url,
                style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = timestamp,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f),
            )
        }
        if (latencyMs != null && latencyMs > 0) {
            Text(
                text = "${latencyMs}ms",
                style = MaterialTheme.typography.labelSmall,
                color = Color(0xFFFF9800),
                modifier = Modifier.padding(start = 8.dp),
            )
        }
    }
}
