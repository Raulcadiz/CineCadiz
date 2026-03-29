package com.example.cinecity.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.cinecity.data.model.Contenido
import com.example.cinecity.data.model.SerieAgrupada
import com.example.cinecity.data.repository.ContentRepository
import com.example.cinecity.voice.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class VoiceAssistantViewModel : ViewModel() {

    private val repo = ContentRepository()

    // ── UI State ─────────────────────────────────────────────────

    sealed class UiState {
        data object Idle       : UiState()
        data object Listening  : UiState()
        data object Processing : UiState()
        data class  Speaking(val text: String)   : UiState()
        data class  Disambiguation(
            val question: String,
            val options: List<Pair<String, Contenido?>>,  // label + item (null = series navegation)
        ) : UiState()
        data class  Error(val message: String) : UiState()
    }

    private val _uiState = MutableStateFlow<UiState>(UiState.Idle)
    val uiState: StateFlow<UiState> = _uiState

    private val _spokenText = MutableStateFlow("")
    val spokenText: StateFlow<String> = _spokenText

    // ── Callbacks (set from MainActivity) ────────────────────────

    /** Called when assistant wants to navigate to a tab */
    var onNavigate: ((String) -> Unit)? = null

    /** Called when assistant wants to play a specific item */
    var onPlayItem: ((Contenido) -> Unit)? = null

    /** Called when assistant wants to trigger a search on the current screen */
    var onVoiceSearch: ((query: String, type: String?) -> Unit)? = null

    /** Called for player controls (pause, next, etc.) */
    var onPlayerControl: ((PlayerAction) -> Unit)? = null

    /** Speak text via TTS — wired from VoiceAssistantOverlay */
    var speakFn: ((String, (() -> Unit)?) -> Unit)? = null

    // ── Disambiguation state ──────────────────────────────────────

    private var disambiguationOptions: List<Pair<String, Contenido?>> = emptyList()
    private var disambiguationIsLive = false

    // ─────────────────────────────────────────────────────────────

    fun onListeningStarted() {
        _uiState.value = UiState.Listening
        _spokenText.value = ""
    }

    fun onListeningStopped() {
        if (_uiState.value is UiState.Listening) {
            _uiState.value = UiState.Idle
        }
    }

    fun onSpeechResult(text: String) {
        if (text.isBlank()) {
            _uiState.value = UiState.Idle
            return
        }
        _spokenText.value = text
        _uiState.value = UiState.Processing

        viewModelScope.launch {
            // If there's an active disambiguation, re-parse as selection first
            if (disambiguationOptions.isNotEmpty()) {
                val selection = IntentParser.parse(text)
                if (selection is VoiceIntent.SelectOption) {
                    handleDisambiguationSelect(selection.index)
                    return@launch
                }
                // New command — clear disambiguation
                disambiguationOptions = emptyList()
            }
            processIntent(IntentParser.parse(text), text)
        }
    }

    fun dismissDisambiguation() {
        disambiguationOptions = emptyList()
        _uiState.value = UiState.Idle
    }

    fun selectDisambiguationItem(index: Int) {
        handleDisambiguationSelect(index)
    }

    // ── Intent processing ─────────────────────────────────────────

    private suspend fun processIntent(intent: VoiceIntent, rawText: String) {
        when (intent) {

            is VoiceIntent.Help -> speak(
                "Puedes decir: pon el padrino, busca películas de terror, " +
                "ir a series, pausa, siguiente, o el número para elegir."
            )

            is VoiceIntent.Navigate -> {
                val (route, label) = when (intent.destination) {
                    NavDestination.HOME   -> "home"   to "inicio"
                    NavDestination.MOVIES -> "movies" to "películas"
                    NavDestination.SERIES -> "series" to "series"
                    NavDestination.LIVE   -> "live"   to "canales en directo"
                }
                speak("Abriendo $label") { onNavigate?.invoke(route) }
            }

            is VoiceIntent.PlayerControl -> {
                val label = when (intent.action) {
                    PlayerAction.PAUSE       -> "Pausado"
                    PlayerAction.PLAY        -> "Reproduciendo"
                    PlayerAction.NEXT        -> "Siguiente"
                    PlayerAction.PREVIOUS    -> "Anterior"
                    PlayerAction.VOLUME_UP   -> "Volumen arriba"
                    PlayerAction.VOLUME_DOWN -> "Volumen abajo"
                    PlayerAction.BACK        -> "Volviendo"
                }
                speak(label) { onPlayerControl?.invoke(intent.action) }
            }

            is VoiceIntent.FilterByGenre -> {
                val route = when (intent.type) {
                    ContentType.SERIES -> "series"
                    else               -> "movies"
                }
                val typeLabel = if (intent.type == ContentType.SERIES) "series" else "películas"
                speak("Buscando $typeLabel de ${intent.genre}") {
                    onNavigate?.invoke(route)
                    onVoiceSearch?.invoke(intent.genre, route)
                }
            }

            is VoiceIntent.Search -> {
                val route = when (intent.type) {
                    ContentType.LIVE   -> "live"
                    ContentType.SERIES -> "series"
                    ContentType.MOVIE  -> "movies"
                    null               -> null
                }
                speak("Buscando ${intent.query}") {
                    route?.let { onNavigate?.invoke(it) }
                    onVoiceSearch?.invoke(intent.query, route)
                }
            }

            is VoiceIntent.PlayChannel -> {
                speak("Buscando canal ${intent.query}…")
                try {
                    // Fetch all live (page 1, 100 items) and filter client-side
                    val all = repo.getLive(1).items
                    val matches = all.filter { ch ->
                        ch.title.contains(intent.query, ignoreCase = true) ||
                        (ch.groupTitle ?: "").contains(intent.query, ignoreCase = true)
                    }
                    disambiguationIsLive = true
                    handlePlayResults(matches, intent.query)
                } catch (e: Exception) {
                    speak("No pude buscar el canal. Comprueba la conexión.")
                    _uiState.value = UiState.Idle
                }
            }

            is VoiceIntent.PlayItem -> {
                speak("Buscando ${intent.query}…")
                try {
                    val movies = repo.getPeliculas(1, intent.query, null, null).items
                    disambiguationIsLive = false
                    handlePlayResults(movies, intent.query)
                } catch (e: Exception) {
                    speak("No pude buscar. Comprueba la conexión.")
                    _uiState.value = UiState.Idle
                }
            }

            is VoiceIntent.SelectOption -> {
                // Orphan select — ignore
                _uiState.value = UiState.Idle
            }

            is VoiceIntent.Unknown -> {
                // Treat as generic search in movies
                speak("Buscando ${rawText}") {
                    onVoiceSearch?.invoke(rawText, null)
                }
            }
        }
    }

    private fun handlePlayResults(results: List<Contenido>, query: String) {
        when {
            results.isEmpty() -> {
                speak("No encontré ningún resultado para $query.") {
                    _uiState.value = UiState.Idle
                }
            }
            results.size == 1 -> {
                speak("Reproduciendo ${results[0].title}") {
                    onPlayItem?.invoke(results[0])
                    _uiState.value = UiState.Idle
                }
            }
            else -> {
                val top = results.take(5)
                val options = top.map { it.title to it }
                disambiguationOptions = options

                val numbered = top.take(3).mapIndexed { i, item ->
                    "${i + 1}. ${item.title}"
                }.joinToString(". ")
                val question = "Encontré ${top.size} resultados. $numbered. Di el número o elige."

                speak(question)
                _uiState.value = UiState.Disambiguation(question, options)
            }
        }
    }

    private fun handleDisambiguationSelect(index: Int) {
        val item = disambiguationOptions.getOrNull(index)?.second
        disambiguationOptions = emptyList()

        if (item == null) {
            speak("No existe esa opción.")
            _uiState.value = UiState.Idle
            return
        }

        speak("Reproduciendo ${item.title}") {
            onPlayItem?.invoke(item)
            _uiState.value = UiState.Idle
        }
    }

    // ── TTS helper ────────────────────────────────────────────────

    private fun speak(text: String, onDone: (() -> Unit)? = null) {
        _uiState.value = UiState.Speaking(text)
        val fn = speakFn
        if (fn != null) {
            fn(text, onDone)
        } else {
            // No TTS available yet — skip to done directly
            onDone?.invoke()
            _uiState.value = UiState.Idle
        }
    }
}
