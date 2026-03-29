package com.example.cinecity.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.cinecity.data.model.Contenido
import com.example.cinecity.data.model.ScanConfig
import com.example.cinecity.data.model.ScanReport
import com.example.cinecity.data.repository.ContentRepository
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class LiveUiState(
    val items: List<Contenido> = emptyList(),
    val curados: List<Contenido> = emptyList(),   // canales curados por el admin
    val isLoading: Boolean = true,
    val error: String? = null,
    val query: String = "",
)

data class ScanConfigUiState(
    val config: ScanConfig = ScanConfig(),
    val isLoading: Boolean = false,
    val isSaving: Boolean = false,
    val reports: List<ScanReport> = emptyList(),
    val reportsLoading: Boolean = false,
    val scanRunning: Boolean = false,
    val message: String? = null,
)

class LiveViewModel : ViewModel() {
    private val repo = ContentRepository()

    private val _state = MutableStateFlow(LiveUiState())
    val state: StateFlow<LiveUiState> = _state

    private val _scanState = MutableStateFlow(ScanConfigUiState())
    val scanState: StateFlow<ScanConfigUiState> = _scanState

    private var allItems: List<Contenido> = emptyList()

    init { load() }

    fun load() {
        viewModelScope.launch {
            _state.value = LiveUiState(isLoading = true)
            try {
                // Cargar canales curados y todos los canales live en paralelo
                val curadosDeferred = kotlinx.coroutines.async {
                    try { repo.getCanalesCurados() } catch (_: Exception) { emptyList() }
                }
                val collected = mutableListOf<Contenido>()
                var page = 1
                while (true) {
                    val result = repo.getLive(page)
                    collected += result.items
                    if (page >= result.pages) break
                    page++
                }
                allItems = collected
                val curados = curadosDeferred.await()
                _state.value = LiveUiState(isLoading = false, items = allItems, curados = curados)
            } catch (e: Exception) {
                _state.value = LiveUiState(isLoading = false, error = e.message)
            }
        }
    }

    fun onQueryChange(q: String) {
        val filtered = if (q.isBlank()) allItems
        else allItems.filter { it.title.contains(q, ignoreCase = true) }
        val curadoFiltered = if (q.isBlank()) _state.value.curados
        else _state.value.curados.filter { it.title.contains(q, ignoreCase = true) }
        _state.value = _state.value.copy(query = q, items = filtered, curados = curadoFiltered)
    }

    // ── Scan config ───────────────────────────────────────────

    fun loadScanConfig() {
        viewModelScope.launch {
            _scanState.value = _scanState.value.copy(isLoading = true, message = null)
            try {
                val config = repo.getScanConfig()
                _scanState.value = _scanState.value.copy(config = config, isLoading = false)
            } catch (e: Exception) {
                _scanState.value = _scanState.value.copy(
                    isLoading = false,
                    message = "Error al cargar configuración: ${e.message}",
                )
            }
        }
    }

    fun saveScanConfig(autoEnabled: Boolean, intervalHours: Int) {
        viewModelScope.launch {
            _scanState.value = _scanState.value.copy(isSaving = true, message = null)
            try {
                val updated = repo.updateScanConfig(
                    ScanConfig(autoScanEnabled = autoEnabled, intervalHours = intervalHours),
                )
                _scanState.value = _scanState.value.copy(
                    config = updated,
                    isSaving = false,
                    message = "Configuración guardada",
                )
            } catch (e: Exception) {
                _scanState.value = _scanState.value.copy(
                    isSaving = false,
                    message = "Error al guardar: ${e.message}",
                )
            }
        }
    }

    fun loadScanReports() {
        viewModelScope.launch {
            _scanState.value = _scanState.value.copy(reportsLoading = true)
            try {
                val reports = repo.getScanReports(onlyFailed = true)
                _scanState.value = _scanState.value.copy(
                    reports = reports,
                    reportsLoading = false,
                )
            } catch (e: Exception) {
                _scanState.value = _scanState.value.copy(reportsLoading = false)
            }
        }
    }

    fun runScanNow() {
        viewModelScope.launch {
            _scanState.value = _scanState.value.copy(scanRunning = true, message = null)
            try {
                repo.runLiveScanNow()
                _scanState.value = _scanState.value.copy(
                    scanRunning = false,
                    message = "Escaneo iniciado en el servidor",
                )
            } catch (e: Exception) {
                _scanState.value = _scanState.value.copy(
                    scanRunning = false,
                    message = "Error al iniciar escaneo: ${e.message}",
                )
            }
        }
    }

    fun clearMessage() {
        _scanState.value = _scanState.value.copy(message = null)
    }
}
