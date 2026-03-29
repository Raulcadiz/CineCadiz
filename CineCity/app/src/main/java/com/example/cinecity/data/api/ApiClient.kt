package com.example.cinecity.data.api

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

object ApiClient {

    const val BASE_URL = "https://cinecadiz.servegame.com/"

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
     * ExoPlayer uses VLC/3.0.20 as User-Agent, so IPTV servers accept direct connections.
     * We try direct for everything — proxy is only used as a fallback from PlayerScreen.
     *
     * Also normalizes double-slashes in the path (http://host//live/ → http://host/live/)
     * which some IPTV providers store in their M3U playlists.
     */
    fun streamUrl(url: String): String = normalizeUrl(url)

    /**
     * Normalizes a stream URL: removes double slashes in the path segment.
     * e.g. http://dplatino.net:80//live/... → http://dplatino.net:80/live/...
     */
    fun normalizeUrl(url: String): String {
        if (!url.contains("//", startIndex = 8)) return url   // fast-path: no double slash after scheme
        return try {
            val u = java.net.URL(url)
            val cleanPath = u.path.replace(Regex("//{2,}"), "/")
            java.net.URL(u.protocol, u.host, u.port, cleanPath + (if (u.query != null) "?${u.query}" else "")).toString()
        } catch (_: Exception) {
            url  // if parsing fails, return original
        }
    }

    /** Proxy URL for ExoPlayer fallback (stream-proxy). */
    fun streamProxyUrl(url: String): String =
        "${BASE_URL}api/stream-proxy?url=${URLEncoder.encode(normalizeUrl(url), "UTF-8")}"

    /** Proxy URL for ExoPlayer fallback (hls-proxy). */
    fun hlsProxyUrl(url: String): String =
        "${BASE_URL}api/hls-proxy?url=${URLEncoder.encode(normalizeUrl(url), "UTF-8")}"
}
