package com.example.cinecity.data.api

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

object ApiClient {

    // Usa la IP del VPS directamente hasta que el dominio esté configurado.
    // Cuando cinecadiz.servegame.com apunte a 57.129.126.202, cambia a:
    // const val BASE_URL = "http://cinecadiz.servegame.com/"
    const val BASE_URL = "http://57.129.126.202/"

    private val okHttp = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .addInterceptor(HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        })
        .build()

    private val retrofit = Retrofit.Builder()
        .baseUrl(BASE_URL)
        .client(okHttp)
        .addConverterFactory(GsonConverterFactory.create())
        .build()

    val api: ApiService = retrofit.create(ApiService::class.java)

    /** Proxied image URL (bypasses hotlink protection) */
    fun imageProxyUrl(url: String?): String? {
        if (url.isNullOrBlank()) return null
        val encoded = URLEncoder.encode(url, "UTF-8")
        return "${BASE_URL}api/proxy-image?url=$encoded"
    }

    /**
     * Returns the URL ExoPlayer should open.
     *
     * - Direct video files (.mkv, .mp4, …)  → sin proxy (ExoPlayer conecta directo con UA VLC).
     * - Manifiestos HLS explícitos (.m3u8)   → hls-proxy (reescribe segmentos para que pasen
     *                                          por el VPS, necesario si el servidor IPTV filtra IPs).
     * - Todo lo demás (streams IPTV sin ext, .ts, etc.) → stream-proxy (retransmite el contenido
     *   real con el Content-Type original; ExoPlayer detecta el formato automáticamente).
     *   La web usa hls-proxy para todo por CORS; ExoPlayer NO tiene CORS y no necesita eso.
     */
    fun streamUrl(url: String): String {
        val lower = url.lowercase().split("?")[0]
        val directExtensions = listOf(
            ".mkv", ".mp4", ".avi", ".mov", ".webm",
            ".flv", ".wmv", ".mpg", ".mpeg"
        )
        return when {
            directExtensions.any { lower.endsWith(it) } ->
                url
            lower.endsWith(".m3u8") || lower.endsWith(".m3u") ->
                "${BASE_URL}api/hls-proxy?url=${URLEncoder.encode(url, "UTF-8")}"
            else ->
                "${BASE_URL}api/stream-proxy?url=${URLEncoder.encode(url, "UTF-8")}"
        }
    }
}
