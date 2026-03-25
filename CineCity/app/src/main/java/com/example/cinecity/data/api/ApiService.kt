package com.example.cinecity.data.api

import com.example.cinecity.data.model.AddUrlRequest
import com.example.cinecity.data.model.Contenido
import com.example.cinecity.data.model.LiveServersResponse
import com.example.cinecity.data.model.PagedResponse
import com.example.cinecity.data.model.ReportDownRequest
import com.example.cinecity.data.model.ReportDownResponse
import com.example.cinecity.data.model.ScanConfig
import com.example.cinecity.data.model.ScanReport
import com.example.cinecity.data.model.SerieAgrupada
import com.example.cinecity.data.model.SetServerRequest
import com.example.cinecity.data.model.Stats
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface ApiService {

    @GET("api/trending")
    suspend fun getTrending(
        @Query("limit") limit: Int = 30,
    ): List<Contenido>

    @GET("api/peliculas")
    suspend fun getPeliculas(
        @Query("page") page: Int = 1,
        @Query("limit") limit: Int = 24,
        @Query("q") q: String? = null,
        @Query("genero") genero: String? = null,
        @Query("sort") sort: String? = null,
    ): PagedResponse<Contenido>

    @GET("api/series-agrupadas")
    suspend fun getSeriesAgrupadas(
        @Query("page") page: Int = 1,
        @Query("limit") limit: Int = 24,
        @Query("q") q: String? = null,
        @Query("genero") genero: String? = null,
        @Query("sort") sort: String? = null,
    ): PagedResponse<SerieAgrupada>

    @GET("api/live")
    suspend fun getLive(
        @Query("page") page: Int = 1,
        @Query("limit") limit: Int = 100,
    ): PagedResponse<Contenido>

    @GET("api/contenido/{id}")
    suspend fun getContenido(@Path("id") id: Int): Contenido

    @GET("api/serie-episodios")
    suspend fun getSerieEpisodios(@Query("titulo") titulo: String): List<Contenido>

    @GET("api/generos")
    suspend fun getGeneros(): List<String>

    @GET("api/stats")
    suspend fun getStats(): Stats

    @POST("api/reportar/{id}")
    suspend fun reportar(@Path("id") id: Int): Response<Unit>

    // ── Live management ───────────────────────────────────────

    @GET("api/live/scan-config")
    suspend fun getScanConfig(): ScanConfig

    @POST("api/live/scan-config")
    suspend fun updateScanConfig(@Body config: ScanConfig): ScanConfig

    @POST("api/live/{id}/report-down")
    suspend fun reportDown(
        @Path("id") id: Int,
        @Body body: ReportDownRequest,
    ): ReportDownResponse

    @POST("api/live/{id}/add-url")
    suspend fun addLiveUrl(
        @Path("id") id: Int,
        @Body body: AddUrlRequest,
    ): Response<Unit>

    @GET("api/live/scan-reports")
    suspend fun getScanReports(
        @Query("limit") limit: Int = 100,
        @Query("all") all: Int = 0,
    ): List<ScanReport>

    @POST("api/live/scan/run")
    suspend fun runLiveScanNow(): Response<Unit>

    @GET("api/live/{id}/servers")
    suspend fun getLiveServers(@Path("id") id: Int): LiveServersResponse

    @POST("api/live/{id}/set-server")
    suspend fun setLiveServer(
        @Path("id") id: Int,
        @Body body: SetServerRequest,
    ): Response<Unit>
}
