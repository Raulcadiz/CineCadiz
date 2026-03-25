package com.example.cinecity.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.cinecity.data.model.Contenido
import com.example.cinecity.data.repository.ContentRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class SeriesDetailUiState(
    val title: String = "",
    val episodesBySeason: Map<Int, List<Contenido>> = emptyMap(),
    val isLoading: Boolean = true,
    val error: String? = null,
)

class SeriesDetailViewModel : ViewModel() {
    private val repo = ContentRepository()
    private val _state = MutableStateFlow(SeriesDetailUiState())
    val state: StateFlow<SeriesDetailUiState> = _state

    fun loadEpisodes(titulo: String) {
        if (_state.value.title == titulo && !_state.value.isLoading) return
        viewModelScope.launch {
            _state.value = SeriesDetailUiState(title = titulo, isLoading = true)
            try {
                val episodes = repo.getSerieEpisodios(titulo)
                val grouped = episodes
                    .groupBy { it.season ?: 1 }
                    .toSortedMap()
                _state.value = SeriesDetailUiState(
                    title = titulo,
                    episodesBySeason = grouped,
                    isLoading = false,
                )
            } catch (e: Exception) {
                _state.value = SeriesDetailUiState(
                    title = titulo,
                    isLoading = false,
                    error = e.message,
                )
            }
        }
    }
}
