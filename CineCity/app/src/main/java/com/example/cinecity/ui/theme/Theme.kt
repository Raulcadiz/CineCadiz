package com.example.cinecity.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

val CinePrimary    = Color(0xFFE50914)  // Rojo cine
val CineBackground = Color(0xFF0A0A0A)
val CineSurface    = Color(0xFF181818)
val CineCard       = Color(0xFF252525)
val CineOnSurface  = Color(0xFFEEEEEE)
val CineSubtext    = Color(0xFF888888)
val CineDivider    = Color(0xFF333333)

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

@Composable
fun CineCityTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkColorScheme,
        content = content,
    )
}
