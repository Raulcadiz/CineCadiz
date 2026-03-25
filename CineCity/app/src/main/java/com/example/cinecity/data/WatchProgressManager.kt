package com.example.cinecity.data

import android.content.Context
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class WatchProgress(
    val itemId: Int,
    val title: String,
    val image: String?,
    val streamUrl: String,       // original (non-proxied) URL
    val type: String,            // "movie" | "series"
    val seriesTitle: String?,
    val season: Int?,
    val episode: Int?,
    val positionMs: Long,
    val durationMs: Long,
    val savedAt: Long = System.currentTimeMillis(),
) {
    val progressFraction: Float
        get() = if (durationMs > 0) (positionMs.toFloat() / durationMs).coerceIn(0f, 1f) else 0f
}

object WatchProgressManager {
    private const val PREFS_NAME = "watch_progress"
    private const val KEY_LIST = "progress_list"
    private const val MAX_ITEMS = 20

    private val gson = Gson()
    private val _items = MutableStateFlow<List<WatchProgress>>(emptyList())
    val items: StateFlow<List<WatchProgress>> = _items.asStateFlow()

    /** Call once at app start to load persisted data into the StateFlow. */
    fun init(context: Context) {
        _items.value = loadFromPrefs(context)
    }

    fun save(context: Context, progress: WatchProgress) {
        val list = _items.value.toMutableList()
        list.removeAll { it.itemId == progress.itemId }
        list.add(0, progress)
        if (list.size > MAX_ITEMS) list.subList(MAX_ITEMS, list.size).clear()
        _items.value = list
        saveToPrefs(context, list)
    }

    fun remove(context: Context, itemId: Int) {
        val list = _items.value.toMutableList()
        if (list.removeAll { it.itemId == itemId }) {
            _items.value = list
            saveToPrefs(context, list)
        }
    }

    private fun loadFromPrefs(context: Context): List<WatchProgress> {
        val json = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_LIST, null) ?: return emptyList()
        return try {
            val type = object : TypeToken<List<WatchProgress>>() {}.type
            gson.fromJson(json, type) ?: emptyList()
        } catch (_: Exception) { emptyList() }
    }

    private fun saveToPrefs(context: Context, list: List<WatchProgress>) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_LIST, gson.toJson(list))
            .apply()
    }
}
