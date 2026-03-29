package com.example.cinecity.ui.components

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.*
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.example.cinecity.ui.theme.CineCard
import com.example.cinecity.viewmodel.VoiceAssistantViewModel
import java.util.Locale

@Composable
fun VoiceAssistantOverlay(
    viewModel: VoiceAssistantViewModel,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val uiState by viewModel.uiState.collectAsState()
    val spokenText by viewModel.spokenText.collectAsState()

    // ── TTS ──────────────────────────────────────────────────────
    var tts by remember { mutableStateOf<TextToSpeech?>(null) }
    DisposableEffect(Unit) {
        // Use var so the lambda captures the reference after assignment
        var instance: TextToSpeech? = null
        instance = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                instance?.language = Locale("es", "ES")
                instance?.setSpeechRate(0.9f)
            }
        }
        tts = instance
        // Wire TTS into ViewModel
        viewModel.speakFn = { text, onDone ->
            instance?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "VA_UTT")
            if (onDone != null) {
                val delayMs = (text.length * 70L).coerceIn(500L, 8000L)
                android.os.Handler(android.os.Looper.getMainLooper()).postDelayed(onDone, delayMs)
            }
        }
        onDispose {
            instance?.stop()
            instance?.shutdown()
            viewModel.speakFn = null
        }
    }

    // ── SpeechRecognizer ─────────────────────────────────────────
    var recognizer by remember { mutableStateOf<SpeechRecognizer?>(null) }
    DisposableEffect(Unit) {
        onDispose { recognizer?.destroy() }
    }

    fun startListening() {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) return
        tts?.stop()
        recognizer?.destroy()
        val sr = SpeechRecognizer.createSpeechRecognizer(context)
        sr.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(p: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(v: Float) {}
            override fun onBufferReceived(b: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onError(code: Int) {
                viewModel.onListeningStopped()
            }
            override fun onResults(results: Bundle?) {
                val text = results
                    ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull() ?: ""
                viewModel.onSpeechResult(text)
            }
            override fun onPartialResults(p: Bundle?) {}
            override fun onEvent(t: Int, p: Bundle?) {}
        })
        sr.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "es-ES")
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "es-ES")
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        })
        recognizer = sr
        viewModel.onListeningStarted()
    }

    fun stopListening() {
        recognizer?.stopListening()
        viewModel.onListeningStopped()
    }

    // ── Pulse animation ───────────────────────────────────────────
    val pulseAnim = rememberInfiniteTransition(label = "pulse")
    val pulse by pulseAnim.animateFloat(
        initialValue = 1f, targetValue = 1.25f,
        animationSpec = infiniteRepeatable(
            animation = tween(700, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "pulseScale",
    )

    val isListening = uiState is VoiceAssistantViewModel.UiState.Listening

    // ── FAB mic button ────────────────────────────────────────────
    Box(modifier = modifier) {
        FloatingActionButton(
            onClick = {
                if (isListening) stopListening() else startListening()
            },
            containerColor = if (isListening)
                MaterialTheme.colorScheme.primary
            else
                MaterialTheme.colorScheme.surface,
            contentColor = if (isListening)
                Color.White
            else
                MaterialTheme.colorScheme.onSurface,
            modifier = if (isListening)
                Modifier.scale(pulse)
            else
                Modifier,
            shape = CircleShape,
        ) {
            Icon(
                imageVector = if (isListening) Icons.Default.Mic else Icons.Default.MicOff,
                contentDescription = if (isListening) "Detener escucha" else "Hablar",
            )
        }
    }

    // ── Overlay modal — estado, desambiguación ────────────────────
    val showOverlay = uiState !is VoiceAssistantViewModel.UiState.Idle &&
                      uiState !is VoiceAssistantViewModel.UiState.Listening

    AnimatedVisibility(
        visible = showOverlay,
        enter = fadeIn() + slideInVertically { it / 2 },
        exit  = fadeOut() + slideOutVertically { it / 2 },
    ) {
        Dialog(
            onDismissRequest = { viewModel.dismissDisambiguation() },
            properties = DialogProperties(usePlatformDefaultWidth = false),
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 24.dp),
                contentAlignment = Alignment.Center,
            ) {
                when (val s = uiState) {

                    is VoiceAssistantViewModel.UiState.Processing -> {
                        VoiceCard {
                            CircularProgressIndicator(
                                modifier = Modifier.size(32.dp),
                                color = MaterialTheme.colorScheme.primary,
                            )
                            Spacer(Modifier.height(12.dp))
                            Text("Procesando…", color = Color.White, fontSize = 15.sp)
                        }
                    }

                    is VoiceAssistantViewModel.UiState.Speaking -> {
                        VoiceCard {
                            Text("🔊", fontSize = 28.sp)
                            Spacer(Modifier.height(8.dp))
                            Text(
                                s.text,
                                color = Color.White,
                                fontSize = 15.sp,
                                textAlign = TextAlign.Center,
                            )
                            if (spokenText.isNotBlank()) {
                                Spacer(Modifier.height(6.dp))
                                Text(
                                    "\"$spokenText\"",
                                    color = Color.Gray,
                                    fontSize = 12.sp,
                                    textAlign = TextAlign.Center,
                                )
                            }
                        }
                    }

                    is VoiceAssistantViewModel.UiState.Disambiguation -> {
                        VoiceCard {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Text(
                                    "¿Cuál quieres?",
                                    color = Color.White,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 16.sp,
                                )
                                IconButton(
                                    onClick = { viewModel.dismissDisambiguation() },
                                    modifier = Modifier.size(32.dp),
                                ) {
                                    Icon(Icons.Default.Close, null, tint = Color.Gray)
                                }
                            }
                            Spacer(Modifier.height(4.dp))
                            Text(
                                "Di el número o toca una opción",
                                color = Color.Gray,
                                fontSize = 12.sp,
                            )
                            Spacer(Modifier.height(12.dp))
                            s.options.forEachIndexed { index, (label, _) ->
                                DisambiguationRow(
                                    number = index + 1,
                                    label = label,
                                    onClick = {
                                        viewModel.selectDisambiguationItem(index)
                                    },
                                )
                                if (index < s.options.lastIndex) {
                                    Divider(color = Color(0xFF333333), thickness = 0.5.dp)
                                }
                            }
                            Spacer(Modifier.height(8.dp))
                            // Mic to continue speaking
                            OutlinedButton(
                                onClick = { startListening() },
                                modifier = Modifier.fillMaxWidth(),
                                colors = ButtonDefaults.outlinedButtonColors(
                                    contentColor = MaterialTheme.colorScheme.primary,
                                ),
                            ) {
                                Icon(Icons.Default.Mic, null, modifier = Modifier.size(16.dp))
                                Spacer(Modifier.width(6.dp))
                                Text("Di el número", fontSize = 13.sp)
                            }
                        }
                    }

                    is VoiceAssistantViewModel.UiState.Error -> {
                        VoiceCard {
                            Text("❌", fontSize = 24.sp)
                            Spacer(Modifier.height(8.dp))
                            Text(s.message, color = Color(0xFFFF6B6B), fontSize = 14.sp, textAlign = TextAlign.Center)
                        }
                    }

                    else -> {}
                }
            }
        }
    }
}

@Composable
private fun VoiceCard(content: @Composable ColumnScope.() -> Unit) {
    Surface(
        shape = RoundedCornerShape(20.dp),
        color = CineCard,
        tonalElevation = 8.dp,
        shadowElevation = 8.dp,
    ) {
        Column(
            modifier = Modifier.padding(20.dp).fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
            content = content,
        )
    }
}

@Composable
private fun DisambiguationRow(number: Int, label: String, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 10.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Surface(
            shape = CircleShape,
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(26.dp),
        ) {
            Box(contentAlignment = Alignment.Center) {
                Text(
                    "$number",
                    color = Color.White,
                    fontWeight = FontWeight.Bold,
                    fontSize = 12.sp,
                )
            }
        }
        Spacer(Modifier.width(12.dp))
        Text(
            label,
            color = Color.White,
            fontSize = 14.sp,
            modifier = Modifier.weight(1f),
            maxLines = 2,
        )
    }
}
