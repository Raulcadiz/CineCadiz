package com.example.cinecity.data.model

import com.google.gson.annotations.SerializedName

data class Contenido(
    val id: Int = 0,
    val title: String = "",
    val type: String = "",           // "movie" | "series" | "live"
    val streamUrl: String = "",
    val source: String? = null,
    val server: String? = null,
    val image: String? = null,
    val description: String? = null,
    val year: Int? = null,
    val genres: List<String> = emptyList(),
    val groupTitle: String? = null,
    val season: Int? = null,
    val episode: Int? = null,
    val active: Boolean = true,
    val addedAt: String? = null,
    // Campos exclusivos para canales en directo (type="live")
    val liveUrls: List<String>? = null,
    val activeUrlIndex: Int? = null,
)

data class SerieAgrupada(
    val id: Int = 0,
    val title: String = "",
    val type: String = "series",
    val image: String? = null,
    val year: Int? = null,
    val genres: List<String> = emptyList(),
    val seasonCount: Int = 1,
    val episodeCount: Int = 1,
    val groupTitle: String? = null,
    val addedAt: String? = null,
)

data class PagedResponse<T>(
    val items: List<T> = emptyList(),
    val total: Int = 0,
    val page: Int = 1,
    val pages: Int = 1,
    val per_page: Int = 24,
)

data class Stats(
    val peliculas: Int = 0,
    val series: Int = 0,
    val live: Int = 0,
    val total: Int = 0,
)

// ── Live management models ────────────────────────────────────

data class ScanConfig(
    @SerializedName("auto_scan_enabled") val autoScanEnabled: Boolean = true,
    @SerializedName("interval_hours")    val intervalHours: Int = 24,
    @SerializedName("last_scan")         val lastScan: String? = null,
)

data class ReportDownResponse(
    @SerializedName("next_url")            val nextUrl: String? = null,
    @SerializedName("channel_still_alive") val channelStillAlive: Boolean = false,
)

data class ScanReport(
    val id: Int = 0,
    @SerializedName("contenido_id")  val contenidoId: Int = 0,
    @SerializedName("channel_title") val channelTitle: String = "",
    @SerializedName("url_probada")   val urlProbada: String = "",
    val resultado: Boolean = false,
    @SerializedName("latencia_ms")   val latenciaMs: Int? = null,
    val timestamp: String = "",
)

data class AddUrlRequest(val url: String)

data class ReportDownRequest(val url: String)

data class SetServerRequest(val index: Int)

data class LiveServer(
    val index: Int = 0,
    val url: String = "",
    val active: Boolean = false,
    val label: String = "",
    val alive: Boolean? = null,
    @SerializedName("latency_ms")  val latencyMs: Int? = null,
    @SerializedName("checked_at")  val checkedAt: String? = null,
)

data class LiveServersResponse(
    val servers: List<LiveServer> = emptyList(),
    @SerializedName("active_index") val activeIndex: Int = 0,
)
