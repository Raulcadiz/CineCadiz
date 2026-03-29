package com.example.cinecity.viewmodel

import android.app.Application
import android.content.Context
import androidx.lifecycle.AndroidViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Persiste las preferencias de accesibilidad en SharedPreferences y
 * expone cada ajuste como StateFlow para que la UI reaccione en tiempo real.
 */
class AppPreferencesViewModel(app: Application) : AndroidViewModel(app) {

    private val prefs = app.getSharedPreferences("accessibility_prefs", Context.MODE_PRIVATE)

    // ── Alto contraste ─────────────────────────────────────────────
    private val _highContrast = MutableStateFlow(prefs.getBoolean(KEY_HIGH_CONTRAST, false))
    val highContrast: StateFlow<Boolean> = _highContrast

    fun setHighContrast(v: Boolean) {
        prefs.edit().putBoolean(KEY_HIGH_CONTRAST, v).apply()
        _highContrast.value = v
    }

    // ── Texto grande ───────────────────────────────────────────────
    private val _largeText = MutableStateFlow(prefs.getBoolean(KEY_LARGE_TEXT, false))
    val largeText: StateFlow<Boolean> = _largeText

    fun setLargeText(v: Boolean) {
        prefs.edit().putBoolean(KEY_LARGE_TEXT, v).apply()
        _largeText.value = v
    }

    // ── TTS al enfocar ─────────────────────────────────────────────
    private val _ttsOnFocus = MutableStateFlow(prefs.getBoolean(KEY_TTS_FOCUS, false))
    val ttsOnFocus: StateFlow<Boolean> = _ttsOnFocus

    fun setTtsOnFocus(v: Boolean) {
        prefs.edit().putBoolean(KEY_TTS_FOCUS, v).apply()
        _ttsOnFocus.value = v
    }

    // ── Modo simplificado ─────────────────────────────────────────
    private val _simplified = MutableStateFlow(prefs.getBoolean(KEY_SIMPLIFIED, false))
    val simplified: StateFlow<Boolean> = _simplified

    fun setSimplified(v: Boolean) {
        prefs.edit().putBoolean(KEY_SIMPLIFIED, v).apply()
        _simplified.value = v
    }

    companion object {
        private const val KEY_HIGH_CONTRAST = "high_contrast"
        private const val KEY_LARGE_TEXT    = "large_text"
        private const val KEY_TTS_FOCUS     = "tts_on_focus"
        private const val KEY_SIMPLIFIED    = "simplified_mode"
    }
}
