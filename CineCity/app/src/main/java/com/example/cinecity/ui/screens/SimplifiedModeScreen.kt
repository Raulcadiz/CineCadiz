package com.example.cinecity.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.cinecity.data.WatchProgress
import com.example.cinecity.data.WatchProgressManager
import com.example.cinecity.ui.theme.LocalHighContrast
import com.example.cinecity.ui.theme.scaledSp

/**
 * Interfaz simplificada para usuarios con baja visión.
 * Muestra 3 botones grandes y las últimas reproducciones.
 */
@Composable
fun SimplifiedModeScreen(
    onMovies:   () -> Unit,
    onSeries:   () -> Unit,
    onLive:     () -> Unit,
    onContinue: (WatchProgress) -> Unit,
) {
    val isHc = LocalHighContrast.current
    val recent by WatchProgressManager.items.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(16.dp))

        Text(
            "¿Qué quieres ver?",
            fontSize = scaledSp(26f),
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onBackground,
            textAlign = TextAlign.Center,
        )

        Spacer(Modifier.height(32.dp))

        // ── 3 botones principales ──────────────────────────────────
        BigButton(
            icon        = Icons.Default.Movie,
            label       = "Películas",
            description = "Ver películas",
            color       = if (isHc) Color(0xFFFFDD00) else Color(0xFFE50914),
            onClick     = onMovies,
        )

        Spacer(Modifier.height(16.dp))

        BigButton(
            icon        = Icons.Default.Tv,
            label       = "Series",
            description = "Ver series",
            color       = if (isHc) Color(0xFFFFDD00) else Color(0xFF1565C0),
            onClick     = onSeries,
        )

        Spacer(Modifier.height(16.dp))

        BigButton(
            icon        = Icons.Default.LiveTv,
            label       = "Directo",
            description = "Ver canales en directo",
            color       = if (isHc) Color(0xFFFFDD00) else Color(0xFF2E7D32),
            onClick     = onLive,
        )

        // ── Últimas reproducciones ─────────────────────────────────
        if (recent.isNotEmpty()) {
            Spacer(Modifier.height(36.dp))
            HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.3f))
            Spacer(Modifier.height(20.dp))

            Text(
                "Continuar viendo",
                fontSize = scaledSp(18f),
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onBackground,
                modifier = Modifier.fillMaxWidth(),
            )

            Spacer(Modifier.height(12.dp))

            recent.take(3).forEach { progress ->
                RecentItem(progress = progress, onClick = { onContinue(progress) })
                Spacer(Modifier.height(8.dp))
            }
        }

        Spacer(Modifier.height(24.dp))
    }
}

// ── Botón grande ──────────────────────────────────────────────

@Composable
private fun BigButton(
    icon:        ImageVector,
    label:       String,
    description: String,
    color:       Color,
    onClick:     () -> Unit,
) {
    Surface(
        shape  = RoundedCornerShape(20.dp),
        color  = color.copy(alpha = 0.15f),
        border = androidx.compose.foundation.BorderStroke(2.dp, color),
        modifier = Modifier
            .fillMaxWidth()
            .height(100.dp)
            .clickable(onClick = onClick)
            .semantics { contentDescription = description },
    ) {
        Row(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 28.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.Start,
        ) {
            Icon(
                icon,
                contentDescription = null,
                tint   = color,
                modifier = Modifier.size(44.dp),
            )
            Spacer(Modifier.width(20.dp))
            Text(
                label,
                fontSize   = scaledSp(24f),
                fontWeight = FontWeight.Bold,
                color      = MaterialTheme.colorScheme.onBackground,
            )
        }
    }
}

// ── Ítem de "continuar viendo" ────────────────────────────────

@Composable
private fun RecentItem(progress: WatchProgress, onClick: () -> Unit) {
    Surface(
        shape  = RoundedCornerShape(12.dp),
        color  = MaterialTheme.colorScheme.surface,
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .semantics { contentDescription = "Continuar: ${progress.title}" },
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                Icons.Default.PlayCircle,
                contentDescription = null,
                tint     = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(32.dp),
            )
            Spacer(Modifier.width(14.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    progress.title,
                    fontSize   = scaledSp(15f),
                    fontWeight = FontWeight.Medium,
                    color      = MaterialTheme.colorScheme.onSurface,
                    maxLines   = 1,
                    overflow   = TextOverflow.Ellipsis,
                )
                val typeLabel = when (progress.type) {
                    "live"   -> "En directo"
                    "series" -> "Serie"
                    else     -> "Película"
                }
                Text(
                    typeLabel,
                    fontSize = scaledSp(12f),
                    color    = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
                )
            }
            Icon(
                Icons.Default.ChevronRight,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f),
            )
        }
    }
}
