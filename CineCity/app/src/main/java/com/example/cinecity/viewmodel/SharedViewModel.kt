package com.example.cinecity.viewmodel

import androidx.lifecycle.ViewModel
import com.example.cinecity.data.model.Contenido

/**
 * Holds transient state for cross-screen navigation:
 *  - item to play in PlayerScreen
 *  - series title for SeriesDetailScreen
 *  - full episode list + current index for auto-next episode
 */
class SharedViewModel : ViewModel() {
    var pendingItem: Contenido? = null
    var pendingSeriesTitle: String = ""
    var pendingEpisodeList: List<Contenido> = emptyList()
    var pendingEpisodeIndex: Int = -1
}
