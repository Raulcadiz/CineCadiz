package com.example.cinecity.voice

/**
 * Convierte texto libre en español a un VoiceIntent estructurado.
 * Sin dependencias externas — 100% local, sin internet.
 */
object IntentParser {

    // ── Verbos de acción ──────────────────────────────────────────
    private val PLAY_VERBS = listOf(
        "quiero ver", "quiero poner", "pon", "poner", "reproduce", "reproducir",
        "abre", "abrir", "play", "mira", "mirar", "echa", "ver",
    )
    private val SEARCH_VERBS = listOf(
        "busca", "buscar", "encuentra", "encontrar", "search",
        "búscame", "buscame", "muéstrame", "mostrame", "muestra",
        "dónde está", "donde esta",
    )

    // ── Navegación ────────────────────────────────────────────────
    private val NAV_VERBS = listOf(
        "ir a", "ve a", "abre", "ir al", "ve al", "mostrar",
        "muéstrame", "cambia a", "llévame a", "llevame a", "switch",
    )
    private val NAV_HOME    = listOf("inicio", "home", "principal", "portada", "start")
    private val NAV_MOVIES  = listOf("películas", "peliculas", "película", "pelicula", "cine", "films", "movies")
    private val NAV_SERIES  = listOf("series", "serie")
    private val NAV_LIVE    = listOf("directo", "directos", "live", "en vivo", "canales", "televisión", "television")

    // ── Control de reproductor ─────────────────────────────────────
    private val CTRL_PAUSE   = setOf("pausa", "pausar", "para", "parar", "stop", "detén", "deten", "detener")
    private val CTRL_PLAY    = setOf("play", "continúa", "continua", "reanudar", "resume", "seguir", "sigue")
    private val CTRL_NEXT    = setOf("siguiente", "próximo", "proximo", "adelanta", "next", "saltar", "pasa")
    private val CTRL_PREV    = setOf("anterior", "retrocede", "retroceder", "prev", "previous")
    private val CTRL_VOL_UP  = setOf("sube el volumen", "subir volumen", "más volumen", "mas volumen", "más alto", "mas alto", "volumen arriba")
    private val CTRL_VOL_DN  = setOf("baja el volumen", "bajar volumen", "menos volumen", "más bajo", "mas bajo", "silenciar", "silencia", "volumen abajo")
    private val CTRL_BACK    = setOf("volver", "salir", "cerrar", "atrás", "atras")

    // ── Tipos de contenido ────────────────────────────────────────
    private val TYPE_MOVIE  = listOf("película", "pelicula", "peli", "film", "movie", "películas", "peliculas")
    private val TYPE_SERIES = listOf("serie", "series", "temporada")
    private val TYPE_LIVE   = listOf("canal", "directo", "en vivo", "live", "cadena", "canales", "televisión", "tele")

    // ── Géneros ───────────────────────────────────────────────────
    private val GENRES = mapOf(
        "acción"          to "Acción",
        "accion"          to "Acción",
        "terror"          to "Terror",
        "miedo"           to "Terror",
        "suspenso"        to "Terror",
        "comedia"         to "Comedia",
        "cómica"          to "Comedia",
        "comica"          to "Comedia",
        "drama"           to "Drama",
        "dramática"       to "Drama",
        "dramatica"       to "Drama",
        "thriller"        to "Thriller",
        "ciencia ficción" to "Ciencia ficción",
        "ciencia ficcion" to "Ciencia ficción",
        "sci-fi"          to "Ciencia ficción",
        "animación"       to "Animación",
        "animacion"       to "Animación",
        "animada"         to "Animación",
        "anime"           to "Animación",
        "dibujos"         to "Animación",
        "romance"         to "Romance",
        "romántica"       to "Romance",
        "romantica"       to "Romance",
        "aventura"        to "Aventura",
        "fantasía"        to "Fantasía",
        "fantasia"        to "Fantasía",
        "documental"      to "Documental",
        "histórica"       to "Historia",
        "historica"       to "Historia",
        "historia"        to "Historia",
        "deportes"        to "Deporte",
        "deporte"         to "Deporte",
        "fútbol"          to "Deporte",
        "futbol"          to "Deporte",
        "musical"         to "Musical",
        "western"         to "Western",
        "biografía"       to "Biografía",
        "biografia"       to "Biografía",
        "familiar"        to "Familia",
        "familia"         to "Familia",
        "niños"           to "Familia",
        "infantil"        to "Familia",
        "crimen"          to "Crimen",
        "policiaca"       to "Crimen",
        "policíaca"       to "Crimen",
        "misterio"        to "Misterio",
    )

    // ── Selección por número (para desambiguación) ─────────────────
    private val ORDINALS = mapOf(
        "primero" to 0, "primera" to 0, "uno" to 0, "1" to 0,
        "segundo" to 1, "segunda" to 1, "dos"  to 1, "2" to 1,
        "tercero" to 2, "tercera" to 2, "tres" to 2, "3" to 2,
        "cuarto"  to 3, "cuarta"  to 3, "cuatro" to 3, "4" to 3,
        "quinto"  to 4, "quinta"  to 4, "cinco"  to 4, "5" to 4,
    )

    // ─────────────────────────────────────────────────────────────

    fun parse(rawText: String): VoiceIntent {
        val t = rawText.lowercase().trim().removeSuffix(".")

        // 1. Selección de opción (desambiguación activa)
        ORDINALS.entries.firstOrNull { (word, _) ->
            t == word || t == "el $word" || t == "la $word" || t == "número $word" || t == "numero $word"
        }?.let { return VoiceIntent.SelectOption(it.value) }

        // 2. Ayuda
        if (t == "ayuda" || t == "help" || t == "comandos" || t == "qué puedes hacer" || t == "que puedes hacer")
            return VoiceIntent.Help

        // 3. Control del reproductor (palabras exactas o frases cortas)
        if (CTRL_PAUSE.any   { t == it }) return VoiceIntent.PlayerControl(PlayerAction.PAUSE)
        if (CTRL_PLAY.any    { t == it }) return VoiceIntent.PlayerControl(PlayerAction.PLAY)
        if (CTRL_NEXT.any    { t == it }) return VoiceIntent.PlayerControl(PlayerAction.NEXT)
        if (CTRL_PREV.any    { t == it }) return VoiceIntent.PlayerControl(PlayerAction.PREVIOUS)
        if (CTRL_VOL_UP.any  { t.contains(it) }) return VoiceIntent.PlayerControl(PlayerAction.VOLUME_UP)
        if (CTRL_VOL_DN.any  { t.contains(it) }) return VoiceIntent.PlayerControl(PlayerAction.VOLUME_DOWN)
        if (CTRL_BACK.any    { t == it }) return VoiceIntent.PlayerControl(PlayerAction.BACK)

        // 4. Navegación — requiere verbo de nav + keyword de destino
        val hasNavVerb   = NAV_VERBS.any   { t.contains(it) }
        val exactHome    = NAV_HOME.any    { t == it }
        val exactMovies  = NAV_MOVIES.any  { t == it }
        val exactSeries  = NAV_SERIES.any  { t == it }
        val exactLive    = NAV_LIVE.any    { t == it }
        val containsHome    = NAV_HOME.any    { t.contains(it) }
        val containsMovies  = NAV_MOVIES.any  { t.contains(it) }
        val containsSeries  = NAV_SERIES.any  { t.contains(it) }
        val containsLive    = NAV_LIVE.any    { t.contains(it) }
        if (hasNavVerb || exactHome || exactMovies || exactSeries || exactLive) {
            when {
                containsHome   && (hasNavVerb || exactHome)   -> return VoiceIntent.Navigate(NavDestination.HOME)
                containsMovies && (hasNavVerb || exactMovies) -> return VoiceIntent.Navigate(NavDestination.MOVIES)
                containsSeries && (hasNavVerb || exactSeries) -> return VoiceIntent.Navigate(NavDestination.SERIES)
                containsLive   && (hasNavVerb || exactLive)   -> return VoiceIntent.Navigate(NavDestination.LIVE)
            }
        }

        // 5. Detectar tipo de contenido en la frase
        val contentType = when {
            TYPE_LIVE.any   { t.contains(it) } -> ContentType.LIVE
            TYPE_MOVIE.any  { t.contains(it) } -> ContentType.MOVIE
            TYPE_SERIES.any { t.contains(it) } -> ContentType.SERIES
            else -> null
        }

        // 6. Filtro por género — "películas de terror", "series de acción"
        val genre = GENRES.entries.firstOrNull { (key, _) -> t.contains(key) }?.value
        if (genre != null && (t.contains(" de ") || t.contains("tipo") || t.contains("género") || t.contains("genero"))) {
            return VoiceIntent.FilterByGenre(genre, contentType)
        }

        // 7. Intención de reproducir
        val playVerb = PLAY_VERBS.firstOrNull { verb -> t.startsWith(verb) }
        if (playVerb != null) {
            val query = extractAfterVerb(t, playVerb)
            if (query.isNotBlank()) {
                return if (contentType == ContentType.LIVE)
                    VoiceIntent.PlayChannel(query)
                else
                    VoiceIntent.PlayItem(cleanQuery(query, contentType))
            }
        }

        // 8. Intención de búsqueda
        val searchVerb = SEARCH_VERBS.firstOrNull { verb -> t.startsWith(verb) }
        if (searchVerb != null) {
            val query = extractAfterVerb(t, searchVerb)
            if (query.isNotBlank()) {
                return VoiceIntent.Search(cleanQuery(query, contentType), contentType)
            }
        }

        // 9. Fallback: tratar como búsqueda si la frase es sustancial
        if (t.length >= 3) {
            return VoiceIntent.Search(t, contentType)
        }

        return VoiceIntent.Unknown
    }

    private fun extractAfterVerb(text: String, verb: String): String {
        val idx = text.indexOf(verb)
        if (idx < 0) return text
        return text.substring(idx + verb.length).trim()
    }

    /** Elimina artículos y palabras de tipo del inicio de la query */
    private fun cleanQuery(query: String, type: ContentType?): String {
        var q = query
        val prefixes = listOf("el ", "la ", "los ", "las ", "un ", "una ",
            "película ", "pelicula ", "peli ", "serie ", "series ", "canal ")
        for (p in prefixes) {
            if (q.startsWith(p)) { q = q.removePrefix(p).trim(); break }
        }
        return q
    }
}
