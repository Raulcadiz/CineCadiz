package com.example.cinecity.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.cinecity.ui.theme.LocalHighContrast
import com.example.cinecity.ui.theme.scaledSp
import com.example.cinecity.viewmodel.AppPreferencesViewModel

@Composable
fun SettingsScreen(prefsVm: AppPreferencesViewModel) {

    val highContrast by prefsVm.highContrast.collectAsState()
    val largeText    by prefsVm.largeText.collectAsState()
    val ttsOnFocus   by prefsVm.ttsOnFocus.collectAsState()
    val simplified   by prefsVm.simplified.collectAsState()
    val isHc         = LocalHighContrast.current

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 24.dp),
    ) {
        Text(
            "Accesibilidad",
            fontSize = scaledSp(22f),
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onBackground,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            "Ajustes pensados para facilitar el uso con poca visión",
            fontSize = scaledSp(13f),
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
        )

        Spacer(Modifier.height(28.dp))

        // ── Sección Visual ────────────────────────────────────────
        SectionHeader("Visual", isHc)

        SettingsToggle(
            icon    = Icons.Default.Contrast,
            title   = "Alto contraste",
            desc    = "Fondo negro, texto blanco y colores más vivos para mayor legibilidad",
            checked = highContrast,
            onCheckedChange = prefsVm::setHighContrast,
        )

        SettingsDivider(isHc)

        SettingsToggle(
            icon    = Icons.Default.TextFields,
            title   = "Texto grande",
            desc    = "Aumenta todos los textos un 30% (equivale a letra 'grande' del sistema)",
            checked = largeText,
            onCheckedChange = prefsVm::setLargeText,
        )

        Spacer(Modifier.height(28.dp))

        // ── Sección Voz ───────────────────────────────────────────
        SectionHeader("Voz", isHc)

        SettingsToggle(
            icon    = Icons.Default.RecordVoiceOver,
            title   = "Narración al enfocar",
            desc    = "El asistente lee en voz alta el título de cada elemento al seleccionarlo",
            checked = ttsOnFocus,
            onCheckedChange = prefsVm::setTtsOnFocus,
        )

        Spacer(Modifier.height(28.dp))

        // ── Sección Interfaz ──────────────────────────────────────
        SectionHeader("Interfaz", isHc)

        SettingsToggle(
            icon    = Icons.Default.ViewModule,
            title   = "Modo simplificado",
            desc    = "Muestra solo 3 botones grandes: Películas, Series y Directo. " +
                      "Ideal para uso con voz o baja visión.",
            checked = simplified,
            onCheckedChange = prefsVm::setSimplified,
        )

        Spacer(Modifier.height(40.dp))

        // ── Nota informativa ─────────────────────────────────────
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = MaterialTheme.colorScheme.surface,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Row(
                modifier = Modifier.padding(14.dp),
                verticalAlignment = Alignment.Top,
            ) {
                Icon(
                    Icons.Default.Info,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(18.dp).padding(top = 2.dp),
                )
                Spacer(Modifier.width(10.dp))
                Text(
                    "El asistente de voz (botón del micrófono) siempre está disponible. " +
                    "Puedes decir: \"busca el padrino\", \"ir a series\", \"pon el canal de deportes\".",
                    fontSize = scaledSp(12f),
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.75f),
                    lineHeight = 18.sp,
                )
            }
        }
    }
}

// ── Componentes auxiliares ─────────────────────────────────────

@Composable
private fun SectionHeader(title: String, highContrast: Boolean) {
    Text(
        title.uppercase(),
        fontSize = 11.sp,
        fontWeight = FontWeight.Bold,
        color = if (highContrast) Color(0xFFFFDD00) else MaterialTheme.colorScheme.primary,
        letterSpacing = 1.2.sp,
        modifier = Modifier.padding(bottom = 8.dp),
    )
}

@Composable
private fun SettingsDivider(highContrast: Boolean) {
    HorizontalDivider(
        modifier = Modifier.padding(vertical = 2.dp),
        color = MaterialTheme.colorScheme.outline.copy(alpha = if (highContrast) 0.8f else 0.4f),
    )
}

@Composable
private fun SettingsToggle(
    icon:           ImageVector,
    title:          String,
    desc:           String,
    checked:        Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    Surface(
        color = Color.Transparent,
        modifier = Modifier
            .fillMaxWidth()
            .semantics { contentDescription = "$title: ${if (checked) "activado" else "desactivado"}" },
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                icon,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
                modifier = Modifier.size(24.dp),
            )
            Spacer(Modifier.width(16.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    title,
                    fontSize = scaledSp(15f),
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                Text(
                    desc,
                    fontSize = scaledSp(12f),
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
                    lineHeight = 16.sp,
                    modifier = Modifier.padding(top = 2.dp),
                )
            }
            Spacer(Modifier.width(12.dp))
            Switch(
                checked = checked,
                onCheckedChange = onCheckedChange,
                colors = SwitchDefaults.colors(
                    checkedThumbColor  = MaterialTheme.colorScheme.primary,
                    checkedTrackColor  = MaterialTheme.colorScheme.primary.copy(alpha = 0.35f),
                ),
            )
        }
    }
}
