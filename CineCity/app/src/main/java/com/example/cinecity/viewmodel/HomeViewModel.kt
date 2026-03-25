package com.example.cinecity.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.cinecity.data.model.Contenido
import com.example.cinecity.data.repository.ContentRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class HomeUiState(
    val trending: List<Contenido> = emptyList(),
    val isLoading: Boolean = true,
    val error: String? = null,
)

class HomeViewModel : ViewModel() {
    private val repo = ContentRepository()
    private val _state = MutableStateFlow(HomeUiState())
    val state: StateFlow<HomeUiState> = _state

    init { load() }

    fun load() {
        viewModelScope.launch {
            _state.value = HomeUiState(isLoading = true)
            try {
                _state.value = HomeUiState(isLoading = false, trending = repo.getTrending(30))
            } catch (e: Exception) {
                _state.value = HomeUiState(isLoading = false, error = e.message)
            }
        }
    }
}
