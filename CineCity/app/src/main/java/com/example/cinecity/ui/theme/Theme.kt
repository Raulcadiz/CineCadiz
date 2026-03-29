package com.example.cinecity.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.sp

// ── Colores tema normal ────────────────────────────────────────
val CinePrimary    = Color(0xFFE50914)
val CineBackground = Color(0xFF0A0A0A)
val CineSurface    = Color(0xFF181818)
val CineCard       = Color(0xFF252525)
val CineOnSurface  = Color(0xFFEEEEEE)
val CineSubtext    = Color(0xFF888888)
val CineDivider    = Color(0xFF333333)

// ── Colores alto contraste ─────────────────────────────────────
// Fondo negro puro, texto blanco puro, primario amarillo (más visible que rojo)
val HcPrimary    = Color(0xFFFFDD00)   // amarillo accesible
val HcBackground = Color(0xFF000000)
val HcSurface    = Color(0xFF111111)
val HcCard       = Color(0xFF1A1A1A)
val HcOnSurface  = Color(0xFFFFFFFF)
val HcSubtext    = Color(0xFFCCCCCC)
val HcDivider    = Color(0xFF555555)

private val DarkColorScheme = darkColorScheme(
    primary         = CinePrimary,
    background      = CineBackground,
    surface         = CineSurface,
    onPrimary       = Color.White,
    onBackground    = Color.White,
    onSurface       = CineOnSurface,
    surfaceVariant  = CineCard,
    outline         = CineDivider,
)

private val HighContrastColorScheme = darkColorScheme(
    primary         = HcPrimary,
    background      = HcBackground,
    surface         = HcSurface,
    onPrimary       = Color.Black,
    onBackground    = HcOnSurface,
    onSurface       = HcOnSurface,
    surfaceVariant  = HcCard,
    outline         = HcDivider,
)

// ── Composition locals para accesibilidad ─────────────────────
/** true → usar esquema de alto contraste */
val LocalHighContrast = compositionLocalOf { false }

/** Multiplicador de tamaño de texto: 1f normal, 1.25f grande */
val LocalTextScale = compositionLocalOf { 1f }

/** true → TTS anuncia el título al obtener el foco */
val LocalTtsOnFocus = compositionLocalOf { false }

/** Función para hablar texto. null si TTS no está disponible. */
val LocalTtsSpeakFn = compositionLocalOf<((String) -> Unit)?> { null }

// ── Helper: escala de texto ────────────────────────────────────
/** Aplica el multiplicador de texto global al sp recibido. */
@Composable
fun scaledSp(base: Float): TextUnit {
    val scale = LocalTextScale.current
    return (base * scale).sp
}

// ── Tema raíz ──────────────────────────────────────────────────
@Composable
fun CineCityTheme(
    highContrast: Boolean = false,
    largeText:    Boolean = false,
    ttsOnFocus:   Boolean = false,
    content: @Composable () -> Unit,
) {
    val colorScheme = if (highContrast) HighContrastColorScheme else DarkColorScheme
    val textScale   = if (largeText) 1.3f else 1f

    CompositionLocalProvider(
        LocalHighContrast provides highContrast,
        LocalTextScale    provides textScale,
        LocalTtsOnFocus   provides ttsOnFocus,
    ) {
        MaterialTheme(
            colorScheme = colorScheme,
            content     = content,
        )
    }
}
