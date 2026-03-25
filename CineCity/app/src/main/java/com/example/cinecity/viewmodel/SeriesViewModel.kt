package com.example.cinecity.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.cinecity.data.model.SerieAgrupada
import com.example.cinecity.data.repository.ContentRepository
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class SeriesUiState(
    val items: List<SerieAgrupada> = emptyList(),
    val page: Int = 1,
    val totalPages: Int = 1,
    val isLoading: Boolean = true,
    val isLoadingMore: Boolean = false,
    val error: String? = null,
    val query: String = "",
)

class SeriesViewModel : ViewModel() {
    private val repo = ContentRepository()
    private val _state = MutableStateFlow(SeriesUiState())
    val state: StateFlow<SeriesUiState> = _state
    private var searchJob: Job? = null

    init { load() }

    fun load(reset: Boolean = true) {
        val s = _state.value
        val nextPage = if (reset) 1 else s.page + 1
        viewModelScope.launch {
            if (reset) _state.value = s.copy(isLoading = true, items = emptyList(), page = 1)
            else _state.value = s.copy(isLoadingMore = true)
            try {
                val result = repo.getSeriesAgrupadas(nextPage, s.query, null, "title_asc")
                val all = if (reset) result.items else _state.value.items + result.items
                _state.value = _state.value.copy(
                    items = all,
                    page = result.page,
                    totalPages = result.pages,
                    isLoading = false,
                    isLoadingMore = false,
                    error = null,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false, isLoadingMore = false, error = e.message,
                )
            }
        }
    }

    fun onQueryChange(q: String) {
        _state.value = _state.value.copy(query = q)
        searchJob?.cancel()
        searchJob = viewModelScope.launch { delay(400); load(reset = true) }
    }

    fun loadMore() {
        val s = _state.value
        if (!s.isLoadingMore && s.page < s.totalPages) load(reset = false)
    }
}
