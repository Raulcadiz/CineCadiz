package com.example.cinecity.voice

sealed class VoiceIntent {
    /** "busca el padrino", "el padrino" → search + navigate to screen */
    data class Search(val query: String, val type: ContentType? = null) : VoiceIntent()

    /** "pon el padrino", "reproduce breaking bad" → direct play */
    data class PlayItem(val query: String) : VoiceIntent()

    /** "pon el canal de deportes" → live channel */
    data class PlayChannel(val query: String) : VoiceIntent()

    /** "ir a películas", "series" → switch tab */
    data class Navigate(val destination: NavDestination) : VoiceIntent()

    /** "pausa", "siguiente", "sube el volumen" → player controls */
    data class PlayerControl(val action: PlayerAction) : VoiceIntent()

    /** "películas de terror" → navigate + filter by genre */
    data class FilterByGenre(val genre: String, val type: ContentType? = null) : VoiceIntent()

    /** "el primero", "dos" → select from disambiguation list */
    data class SelectOption(val index: Int) : VoiceIntent()

    data object Help    : VoiceIntent()
    data object Unknown : VoiceIntent()
}

enum class ContentType { MOVIE, SERIES, LIVE }
enum class NavDestination { HOME, MOVIES, SERIES, LIVE }
enum class PlayerAction { PLAY, PAUSE, NEXT, PREVIOUS, VOLUME_UP, VOLUME_DOWN, BACK }
