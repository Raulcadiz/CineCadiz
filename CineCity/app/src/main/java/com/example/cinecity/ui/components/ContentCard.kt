package com.example.cinecity.ui.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Tv
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.example.cinecity.data.api.ApiClient
import com.example.cinecity.ui.theme.CineCard
import com.example.cinecity.ui.theme.CineSubtext
import com.example.cinecity.ui.theme.LocalTtsOnFocus
import com.example.cinecity.ui.theme.LocalTtsSpeakFn

private val FocusColor = Color(0xFFFFD700)

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun ContentCard(
    imageUrl: String?,
    title: String,
    subtitle: String? = null,
    onClick: () -> Unit,
    width: Dp = 120.dp,
    modifier: Modifier = Modifier,
) {
    var isFocused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(
        targetValue = if (isFocused) 1.08f else 1f,
        animationSpec = tween(150),
        label = "cardScale",
    )
    val bringIntoViewRequester = remember { BringIntoViewRequester() }
    val ttsOnFocus  = LocalTtsOnFocus.current
    val ttsSpeakFn  = LocalTtsSpeakFn.current

    LaunchedEffect(isFocused) {
        if (isFocused) {
            bringIntoViewRequester.bringIntoView()
            if (ttsOnFocus) ttsSpeakFn?.invoke(title)
        }
    }

    val desc = if (subtitle != null) "$title · $subtitle" else title
    Column(
        modifier = modifier
            .width(width)
            .scale(scale)
            .bringIntoViewRequester(bringIntoViewRequester)
            .semantics { contentDescription = desc }
            .onFocusChanged { isFocused = it.isFocused }
            .clickable(onClick = onClick),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(2f / 3f)
                .clip(RoundedCornerShape(8.dp))
                .background(CineCard)
                .then(
                    if (isFocused) Modifier.border(2.dp, FocusColor, RoundedCornerShape(8.dp))
                    else Modifier
                ),
            contentAlignment = Alignment.Center,
        ) {
            val proxied = ApiClient.imageProxyUrl(imageUrl)
            if (!proxied.isNullOrBlank()) {
                AsyncImage(
                    model = proxied,
                    contentDescription = title,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize(),
                )
            } else {
                Icon(
                    Icons.Default.Movie,
                    contentDescription = null,
                    tint = Color(0xFF555555),
                    modifier = Modifier.size(40.dp),
                )
            }
        }
        Spacer(Modifier.height(6.dp))
        Text(
            text = title,
            style = MaterialTheme.typography.bodySmall,
            color = if (isFocused) FocusColor else MaterialTheme.colorScheme.onSurface,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        if (subtitle != null) {
            Text(
                text = subtitle,
                style = MaterialTheme.typography.labelSmall,
                color = CineSubtext,
                maxLines = 1,
            )
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun LiveChannelRow(
    imageUrl: String?,
    title: String,
    groupTitle: String?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var isFocused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(
        targetValue = if (isFocused) 1.03f else 1f,
        animationSpec = tween(150),
        label = "rowScale",
    )
    val bringIntoViewRequester = remember { BringIntoViewRequester() }
    val ttsOnFocus  = LocalTtsOnFocus.current
    val ttsSpeakFn  = LocalTtsSpeakFn.current

    LaunchedEffect(isFocused) {
        if (isFocused) {
            bringIntoViewRequester.bringIntoView()
            if (ttsOnFocus) ttsSpeakFn?.invoke(title)
        }
    }

    val desc = if (!groupTitle.isNullOrBlank()) "$title · $groupTitle" else title
    Row(
        modifier = modifier
            .fillMaxWidth()
            .scale(scale)
            .bringIntoViewRequester(bringIntoViewRequester)
            .semantics { contentDescription = desc }
            .onFocusChanged { isFocused = it.isFocused }
            .then(
                if (isFocused) Modifier.border(1.dp, FocusColor, RoundedCornerShape(6.dp))
                else Modifier
            )
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(52.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(CineCard),
            contentAlignment = Alignment.Center,
        ) {
            val proxied = ApiClient.imageProxyUrl(imageUrl)
            if (!proxied.isNullOrBlank()) {
                AsyncImage(
                    model = proxied,
                    contentDescription = title,
                    contentScale = ContentScale.Fit,
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(4.dp),
                )
            } else {
                Icon(Icons.Default.Tv, contentDescription = null, tint = Color(0xFF555555))
            }
        }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(
                text = title,
                style = MaterialTheme.typography.bodyMedium,
                color = if (isFocused) FocusColor else MaterialTheme.colorScheme.onSurface,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (!groupTitle.isNullOrBlank()) {
                Text(
                    text = groupTitle,
                    style = MaterialTheme.typography.labelSmall,
                    color = CineSubtext,
                )
            }
        }
        Icon(
            Icons.Default.PlayArrow,
            contentDescription = "Reproducir",
            tint = if (isFocused) FocusColor else MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(24.dp),
        )
    }
}

@Composable
fun ErrorState(message: String?, onRetry: () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(32.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                text = message ?: "Error al cargar",
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
            )
            Spacer(Modifier.height(12.dp))
            Button(
                onClick = onRetry,
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
            ) {
                Text("Reintentar")
            }
        }
    }
}

@Composable
fun LoadingIndicator() {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(32.dp),
        contentAlignment = Alignment.Center,
    ) {
        CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
    }
}
