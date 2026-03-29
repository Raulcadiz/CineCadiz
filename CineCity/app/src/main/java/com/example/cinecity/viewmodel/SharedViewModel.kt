package com.example.cinecity.viewmodel

import androidx.lifecycle.ViewModel
import com.example.cinecity.data.model.Contenido
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Holds transient state shared across screens:
 *  - item to play in PlayerScreen
 *  - series title for SeriesDetailScreen
 *  - full episode list + current index for auto-next episode
 *  - voice search command to trigger search in the target screen
 */
class SharedViewModel : ViewModel() {

    // ── Navigation state ──────────────────────────────────────────
    var pendingItem: Contenido? = null
    var pendingSeriesTitle: String = ""
    var pendingEpisodeList: List<Contenido> = emptyList()
    var pendingEpisodeIndex: Int = -1

    // ── Voice search command ───────────────────────────────────────
    /**
     * type: "movies" | "series" | "live" | null (search everywhere)
     */
    data class VoiceSearchCommand(val query: String, val type: String?)

    private val _voiceSearch = MutableStateFlow<VoiceSearchCommand?>(null)
    val voiceSearch: StateFlow<VoiceSearchCommand?> = _voiceSearch

    fun postVoiceSearch(query: String, type: String?) {
        _voiceSearch.value = VoiceSearchCommand(query, type)
    }

    fun consumeVoiceSearch() {
        _voiceSearch.value = null
    }
}
