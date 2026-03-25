package com.example.cinecity.data.repository

import com.example.cinecity.data.api.ApiClient
import com.example.cinecity.data.model.AddUrlRequest
import com.example.cinecity.data.model.SetServerRequest
import com.example.cinecity.data.model.Contenido
import com.example.cinecity.data.model.PagedResponse
import com.example.cinecity.data.model.ReportDownRequest
import com.example.cinecity.data.model.ReportDownResponse
import com.example.cinecity.data.model.ScanConfig
import com.example.cinecity.data.model.ScanReport
import com.example.cinecity.data.model.SerieAgrupada

class ContentRepository {
    private val api = ApiClient.api

    suspend fun getTrending(limit: Int = 30): List<Contenido> = api.getTrending(limit)

    suspend fun getPeliculas(
        page: Int = 1,
        query: String? = null,
        genero: String? = null,
        sort: String? = null,
    ): PagedResponse<Contenido> = api.getPeliculas(page, 24, query?.ifBlank { null }, genero?.ifBlank { null }, sort)

    suspend fun getSeriesAgrupadas(
        page: Int = 1,
        query: String? = null,
        genero: String? = null,
        sort: String? = null,
    ): PagedResponse<SerieAgrupada> = api.getSeriesAgrupadas(page, 24, query?.ifBlank { null }, genero?.ifBlank { null }, sort)

    suspend fun getLive(page: Int = 1): PagedResponse<Contenido> = api.getLive(page, 100)

    suspend fun getContenido(id: Int): Contenido = api.getContenido(id)

    suspend fun getSerieEpisodios(titulo: String): List<Contenido> = api.getSerieEpisodios(titulo)

    suspend fun getGeneros(): List<String> = api.getGeneros()

    // ── Live management ───────────────────────────────────────

    suspend fun getScanConfig(): ScanConfig = api.getScanConfig()

    suspend fun updateScanConfig(config: ScanConfig): ScanConfig = api.updateScanConfig(config)

    suspend fun reportDown(channelId: Int, url: String): ReportDownResponse =
        api.reportDown(channelId, ReportDownRequest(url))

    suspend fun addLiveUrl(channelId: Int, url: String) =
        api.addLiveUrl(channelId, AddUrlRequest(url))

    suspend fun getScanReports(onlyFailed: Boolean = true): List<ScanReport> =
        api.getScanReports(all = if (onlyFailed) 0 else 1)

    suspend fun runLiveScanNow() = api.runLiveScanNow()

    suspend fun getLiveServers(channelId: Int) = api.getLiveServers(channelId)

    suspend fun setLiveServer(channelId: Int, index: Int) =
        api.setLiveServer(channelId, SetServerRequest(index))
}
