// VantageOverlay - everything Vantage draws over the glasses stream
//
// Audio first, screen second. The screen is for the sighted person beside the wearer and for the
// demo: a hazard glow at the edge that grows as something gets closer, one line of what Vantage just
// said (in both scripts when Arabic is on), a hazard readout, and controls that fade after four
// seconds. The wearer never has to find a button: the whole screen is the control (GestureLayer).

package com.vantage.glasses.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Replay
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vantage.glasses.assist.AssistLanguage
import com.vantage.glasses.assist.AssistPhase
import com.vantage.glasses.assist.AssistUiState
import com.vantage.glasses.assist.ShelfItem
import com.vantage.glasses.assist.ShelfTalk
import com.vantage.glasses.awareness.AwarenessState
import com.vantage.glasses.awareness.HazardLevel
import com.vantage.glasses.voice.Settings
import kotlin.math.abs

// MARK: - Hazard glow

/** Amber light at the frame edge: faint on CAUTION, strong and pulsing on STOP. */
@Composable
fun HazardGlow(level: HazardLevel, modifier: Modifier = Modifier) {
  val target =
      when (level) {
        HazardLevel.CLEAR -> 0f
        HazardLevel.CAUTION -> 0.45f
        HazardLevel.STOP -> 1f
      }
  val base by animateFloatAsState(targetValue = target, animationSpec = tween(250), label = "glow")
  val pulse = rememberInfiniteTransition(label = "pulse")
  val beat by
      pulse.animateFloat(
          initialValue = 0.7f,
          targetValue = 1f,
          animationSpec = infiniteRepeatable(tween(420), RepeatMode.Reverse),
          label = "beat",
      )
  val alpha = if (level == HazardLevel.STOP) base * beat else base
  if (alpha <= 0.01f) return
  val width = if (level == HazardLevel.STOP) 26.dp else 14.dp
  Box(
      modifier =
          modifier
              .fillMaxSize()
              .alpha(alpha)
              .border(
                  BorderStroke(
                      width,
                      Brush.verticalGradient(listOf(Vantage.Amber, Vantage.AmberDeep, Vantage.Amber)),
                  ),
              ),
  )
}

// MARK: - Hazard line

@Composable
fun HazardLine(aw: AwarenessState, modifier: Modifier = Modifier) {
  if (!aw.running) return
  val word =
      when (aw.level) {
        HazardLevel.CLEAR -> "CLEAR"
        HazardLevel.CAUTION -> "CAUTION"
        HazardLevel.STOP -> "STOP"
      }
  val colour =
      when (aw.level) {
        HazardLevel.CLEAR -> Vantage.Muted
        HazardLevel.CAUTION -> Vantage.Amber
        HazardLevel.STOP -> Vantage.Amber
      }
  val detail =
      if (aw.targetLabel != null && aw.targetCm != null) " · ${aw.targetLabel} ${aw.targetCm} cm" else ""
  Row(
      modifier =
          modifier
              .clip(RoundedCornerShape(percent = 50))
              .background(Vantage.Scrim)
              .padding(horizontal = 12.dp, vertical = 6.dp)
              .testTag("hazard_line"),
      verticalAlignment = Alignment.CenterVertically,
      horizontalArrangement = Arrangement.spacedBy(8.dp),
  ) {
    Box(modifier = Modifier.size(8.dp).clip(CircleShape).background(colour))
    Text(
        text = word + detail,
        color = colour,
        fontSize = 13.sp,
        fontFamily = FontFamily.Monospace,
        fontWeight = FontWeight.Bold,
    )
  }
}

// MARK: - Caption

@Composable
fun CaptionCard(
    ui: AssistUiState,
    nowSpeaking: String?,
    isPreviewLive: Boolean,
    modifier: Modifier = Modifier,
) {
  val arabic = ui.language == AssistLanguage.ARABIC
  val line = nowSpeaking ?: ui.spoken
  val status =
      when {
        !isPreviewLive -> "Start the preview to use Vantage."
        !ui.hasApiKey -> "Add meta_api_key to local.properties to enable answers."
        ui.phase == AssistPhase.LISTENING -> "Listening…"
        ui.phase == AssistPhase.CAPTURING -> "Taking one picture…"
        ui.phase == AssistPhase.THINKING -> "Checking…"
        ui.phase == AssistPhase.SPEAKING -> "Speaking"
        else -> "Vee is listening for a tap. Tap: look · double tap: read · hold: ask"
      }
  Column(
      modifier =
          modifier
              .fillMaxWidth()
              .clip(RoundedCornerShape(22.dp))
              .background(Vantage.Scrim)
              .padding(horizontal = 18.dp, vertical = 14.dp),
      verticalArrangement = Arrangement.spacedBy(6.dp),
  ) {
    Row(verticalAlignment = Alignment.CenterVertically) {
      EyeAvatar(phase = ui.phase, size = 28.dp)
      Spacer(modifier = Modifier.width(10.dp))
      Text(
          text = status,
          color = Vantage.Muted,
          fontSize = 13.sp,
          fontFamily = Vantage.Sans,
          modifier = Modifier.weight(1f).testTag("assist_status"),
      )
      if (ui.ackMillis != null && ui.totalMillis != null) {
        Text(
            text = "%.1fs · %.1fs".format(ui.ackMillis / 1000f, ui.totalMillis / 1000f),
            color = Vantage.Muted,
            fontSize = 12.sp,
            fontFamily = FontFamily.Monospace,
        )
      }
    }
    ui.errorDetail?.let { detail ->
      Text(
          text = detail,
          color = Vantage.Amber,
          fontSize = 11.sp,
          fontFamily = FontFamily.Monospace,
          modifier = Modifier.fillMaxWidth().testTag("assist_error_detail"),
      )
    }
    if (ui.heard.isNotBlank()) {
      Text(
          text = ui.heard,
          color = Vantage.Muted,
          fontSize = 15.sp,
          fontFamily = if (arabic) Vantage.Arabic else Vantage.Sans,
          textAlign = if (arabic) TextAlign.Right else TextAlign.Left,
          modifier = Modifier.fillMaxWidth().testTag("assist_heard"),
      )
    }
    if (line.isNotBlank()) {
      Text(
          text = line,
          color = if (ui.lastWasError) Vantage.Amber else Vantage.Fg,
          fontSize = if (arabic) 24.sp else 21.sp,
          lineHeight = if (arabic) 34.sp else 27.sp,
          fontWeight = FontWeight.Bold,
          fontFamily = if (arabic) Vantage.Arabic else Vantage.Sans,
          textAlign = if (arabic) TextAlign.Right else TextAlign.Left,
          modifier = Modifier.fillMaxWidth().testTag("assist_spoken"),
      )
    }
  }
}

// MARK: - Shelf list

@Composable
fun ShelfList(items: List<ShelfItem>, language: AssistLanguage, onItem: (ShelfItem) -> Unit, modifier: Modifier = Modifier) {
  if (items.isEmpty()) return
  LazyColumn(
      modifier =
          modifier
              .fillMaxWidth()
              .heightIn(max = 220.dp)
              .clip(RoundedCornerShape(18.dp))
              .background(Vantage.Scrim),
      contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 6.dp),
  ) {
    items(items) { item ->
      Row(
          modifier =
              Modifier.fillMaxWidth()
                  .clickable { onItem(item) }
                  .padding(horizontal = 16.dp, vertical = 8.dp),
          verticalAlignment = Alignment.CenterVertically,
      ) {
        Column(modifier = Modifier.weight(1f)) {
          Text(
              text = item.name,
              color = Vantage.Fg,
              fontSize = 16.sp,
              fontWeight = FontWeight.Bold,
              fontFamily = if (language == AssistLanguage.ARABIC) Vantage.Arabic else Vantage.Sans,
          )
          Text(
              text = listOf(item.position, item.row, item.note).filter { it.isNotBlank() }.joinToString(" · "),
              color = Vantage.Muted,
              fontSize = 12.sp,
              fontFamily = Vantage.Sans,
          )
        }
        val p = item.price
        if (p != null) {
          Text(
              text = "${item.currency} ${"%.2f".format(p)}",
              color = Vantage.Amber,
              fontSize = 15.sp,
              fontWeight = FontWeight.Bold,
              fontFamily = FontFamily.Monospace,
          )
        }
      }
    }
  }
}

// MARK: - Gestures: the whole screen is the control

@Composable
fun GestureLayer(
    enabled: Boolean,
    onTap: () -> Unit,
    onDoubleTap: () -> Unit,
    onLongPress: () -> Unit,
    onSwipeDown: () -> Unit,
    onSwipeBack: () -> Unit,
    onSwipeUp: () -> Unit,
    modifier: Modifier = Modifier,
) {
  if (!enabled) return
  Box(
      modifier =
          modifier
              .fillMaxSize()
              .semantics {
                role = Role.Button
                contentDescription = "Vantage. Tap to look, double tap to read, hold to ask, swipe down to stop, swipe back to repeat, swipe up for the shelf."
              }
              .pointerInput(Unit) {
                detectTapGestures(
                    onTap = { onTap() },
                    onDoubleTap = { onDoubleTap() },
                    onLongPress = { onLongPress() },
                )
              }
              .pointerInput(Unit) {
                var total = Offset.Zero
                detectDragGestures(
                    onDragStart = { total = Offset.Zero },
                    onDrag = { change, drag ->
                      total += drag
                      change.consume()
                    },
                    onDragEnd = {
                      val dx = total.x
                      val dy = total.y
                      when {
                        abs(dy) > abs(dx) && dy > 120f -> onSwipeDown()
                        abs(dy) > abs(dx) && dy < -120f -> onSwipeUp()
                        abs(dx) > 120f -> onSwipeBack()
                      }
                    },
                )
              },
  )
}

// MARK: - Controls

@Composable
fun VantageControls(
    ui: AssistUiState,
    isPreviewLive: Boolean,
    onLook: () -> Unit,
    onRead: () -> Unit,
    onShelf: () -> Unit,
    onAsk: () -> Unit,
    onAgain: () -> Unit,
    onStop: () -> Unit,
    onToggleLanguage: () -> Unit,
    onSettings: () -> Unit,
    alertsOn: Boolean,
    onToggleAlerts: () -> Unit,
    modifier: Modifier = Modifier,
) {
  val enabled = isPreviewLive && !ui.isBusy
  Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
      Pill(Modifier.weight(1f).testTag("assist_look"), Icons.Filled.Visibility, "Look", enabled, onLook)
      Pill(Modifier.weight(1f).testTag("assist_read"), Icons.Filled.MenuBook, "Read", enabled, onRead)
      Pill(Modifier.weight(1f).testTag("assist_shelf"), Icons.Filled.ShoppingCart, "Shelf", enabled, onShelf)
      Pill(Modifier.weight(1f).testTag("assist_ask"), Icons.Filled.Mic, "Ask", enabled, onAsk, accent = true)
    }
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
      Small(Icons.Filled.Replay, "Again", ui.canRepeat && ui.phase == AssistPhase.IDLE, onAgain)
      Small(Icons.Filled.Stop, "Stop", ui.phase != AssistPhase.IDLE, onStop)
      Spacer(modifier = Modifier.weight(1f))
      Text(
          text = if (alertsOn) "Obstacles on" else "Obstacles",
          color = if (alertsOn) Vantage.Bg else Vantage.Fg,
          fontSize = 13.sp,
          fontWeight = FontWeight.Bold,
          fontFamily = Vantage.Sans,
          modifier =
              Modifier.clip(RoundedCornerShape(percent = 50))
                  .background(if (alertsOn) Vantage.Amber else Vantage.Surface)
                  .border(BorderStroke(1.dp, Vantage.Line), RoundedCornerShape(percent = 50))
                  .clickable(enabled = isPreviewLive, onClick = onToggleAlerts)
                  .padding(horizontal = 12.dp, vertical = 5.dp)
                  .testTag("assist_alerts"),
      )
      Text(
          text = ui.language.label,
          color = Vantage.Bg,
          fontSize = 13.sp,
          fontWeight = FontWeight.Bold,
          fontFamily = Vantage.Sans,
          modifier =
              Modifier.clip(RoundedCornerShape(percent = 50))
                  .background(Vantage.Amber)
                  .clickable(enabled = !ui.isBusy, onClick = onToggleLanguage)
                  .padding(horizontal = 12.dp, vertical = 5.dp)
                  .testTag("assist_language"),
      )
      Icon(
          imageVector = Icons.Filled.Settings,
          contentDescription = "Settings",
          tint = Vantage.Fg,
          modifier = Modifier.size(26.dp).clickable(onClick = onSettings),
      )
    }
    Text(
        text = "One picture is taken when you tap. Sent, answered, deleted. Nothing is stored.",
        color = Vantage.Muted,
        fontSize = 11.sp,
        fontFamily = Vantage.Sans,
        modifier = Modifier.fillMaxWidth().testTag("assist_privacy_line"),
    )
  }
}

@Composable
private fun Pill(
    modifier: Modifier,
    icon: ImageVector,
    label: String,
    enabled: Boolean,
    onClick: () -> Unit,
    accent: Boolean = false,
) {
  val bg =
      when {
        !enabled -> Vantage.Surface.copy(alpha = 0.6f)
        accent -> Vantage.Amber
        else -> Vantage.Surface
      }
  val fg = if (!enabled) Vantage.LineStrong else if (accent) Vantage.Bg else Vantage.Fg
  Row(
      modifier =
          modifier
              .height(54.dp)
              .clip(RoundedCornerShape(percent = 50))
              .background(bg)
              .border(BorderStroke(1.dp, if (accent) Vantage.Amber else Vantage.Line), RoundedCornerShape(percent = 50))
              .clickable(enabled = enabled, onClick = onClick)
              .semantics { contentDescription = label },
      horizontalArrangement = Arrangement.Center,
      verticalAlignment = Alignment.CenterVertically,
  ) {
    Icon(imageVector = icon, contentDescription = null, tint = fg, modifier = Modifier.size(20.dp))
    Spacer(modifier = Modifier.width(6.dp))
    Text(text = label, color = fg, fontSize = 16.sp, fontWeight = FontWeight.Bold, fontFamily = Vantage.Sans)
  }
}

@Composable
private fun Small(icon: ImageVector, label: String, enabled: Boolean, onClick: () -> Unit) {
  val c = if (enabled) Vantage.Fg else Vantage.LineStrong
  Row(
      modifier = Modifier.clickable(enabled = enabled, onClick = onClick).padding(vertical = 4.dp),
      verticalAlignment = Alignment.CenterVertically,
  ) {
    Icon(imageVector = icon, contentDescription = null, tint = c, modifier = Modifier.size(16.dp))
    Spacer(modifier = Modifier.width(4.dp))
    Text(text = label, color = c, fontSize = 13.sp, fontWeight = FontWeight.Bold, fontFamily = Vantage.Sans)
  }
}

// MARK: - Settings sheet (the same options as vantage_core.py)

private val ARABIC_CHIPS =
    listOf(
        "ماذا يوجد أمامي؟", "هل الطريق خالٍ؟", "اقرأ لي هذا", "ماذا تقول اللافتة؟", "كم شخصًا هنا؟",
        "أين أنا؟", "أين الباب؟", "ماذا في قائمة الطعام؟", "ما هذا المنتج؟", "ما لون هذا؟", "الرف", "الأرخص",
    )
private val ENGLISH_CHIPS =
    listOf(
        "What's in front of me?", "Is the way clear?", "Read this to me", "What does the sign say?", "How many people are here?",
        "Where am I?", "Where is the door?", "What's on the menu?", "What is this product?", "What colour is this?", "Shelf", "Cheapest",
    )

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsSheet(
    settings: Settings,
    queueEvents: List<String>,
    onDismiss: () -> Unit,
    onCritical: (Int) -> Unit,
    onWarning: (Int) -> Unit,
    onRepeat: (Float) -> Unit,
    onRate: (Float) -> Unit,
    onToggleAwareness: () -> Unit,
    onToggleDescribe: () -> Unit,
    onToggleBeep: () -> Unit,
    onToggleGestures: () -> Unit,
    onToggleLanguage: () -> Unit,
    onChip: (String) -> Unit,
) {
  val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
  ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState, containerColor = Vantage.Surface) {
    LazyColumn(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 40.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
      item { Heading("Halo", "The same options as vantage_core.py. Changes apply at once.") }
      item {
        SliderRow("Too close (critical)", "${settings.criticalCm} cm", settings.criticalCm.toFloat(), 20f..120f) { onCritical(it.toInt()) }
      }
      item {
        SliderRow("Ahead (warning)", "${settings.warningCm} cm", settings.warningCm.toFloat(), 60f..250f) { onWarning(it.toInt()) }
      }
      item {
        SliderRow("Repeat a critical alert every", "%.1f s".format(settings.repeatSec), settings.repeatSec, 1f..6f, onRepeat)
      }
      item {
        SliderRow("Speech rate", "%.2f×".format(settings.speechRate), settings.speechRate, 0.8f..2f, onRate)
      }
      item { SwitchRow("Awareness: on-device obstacle alerts", settings.awarenessOn, onToggleAwareness) }
      item { SwitchRow("Describe mode: name new things with a direction", settings.describeMode, onToggleDescribe) }
      item { SwitchRow("Two tones before a critical alert", settings.beepOn, onToggleBeep) }
      item { SwitchRow("Whole-screen gestures", settings.gesturesOn, onToggleGestures) }
      item { Heading("Voice language", "Alerts, answers and reading in English or Arabic. The screens stay in English.") }
      item {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
          Seg("English", settings.language == AssistLanguage.ENGLISH) { if (settings.language != AssistLanguage.ENGLISH) onToggleLanguage() }
          Seg("العربية", settings.language == AssistLanguage.ARABIC, arabic = true) { if (settings.language != AssistLanguage.ARABIC) onToggleLanguage() }
        }
      }
      item { Heading("Ask", "Tap a question. It is answered from the current frame.") }
      val chips = if (settings.language == AssistLanguage.ARABIC) ARABIC_CHIPS else ENGLISH_CHIPS
      items(chips) { chip ->
        Text(
            text = chip,
            color = Vantage.Fg,
            fontSize = 16.sp,
            fontFamily = if (settings.language == AssistLanguage.ARABIC) Vantage.Arabic else Vantage.Sans,
            textAlign = if (settings.language == AssistLanguage.ARABIC) TextAlign.Right else TextAlign.Left,
            modifier =
                Modifier.fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(Vantage.Bg)
                    .clickable { onChip(chip) }
                    .padding(horizontal = 14.dp, vertical = 10.dp),
        )
      }
      item { Heading("Pipeline", "Speech queue events: priority, stale drops, sweeps.") }
      items(queueEvents.reversed()) { line ->
        Text(text = line, color = Vantage.Muted, fontSize = 12.sp, fontFamily = FontFamily.Monospace)
      }
    }
  }
}

@Composable
private fun Heading(title: String, sub: String) {
  Column(modifier = Modifier.padding(top = 8.dp)) {
    Text(text = title, color = Vantage.Amber, fontSize = 13.sp, fontWeight = FontWeight.Bold, fontFamily = Vantage.Sans)
    Text(text = sub, color = Vantage.Muted, fontSize = 13.sp, fontFamily = Vantage.Sans)
  }
}

@Composable
private fun SliderRow(label: String, value: String, current: Float, range: ClosedFloatingPointRange<Float>, onChange: (Float) -> Unit) {
  Column {
    Row {
      Text(text = label, color = Vantage.Fg, fontSize = 15.sp, fontFamily = Vantage.Sans, modifier = Modifier.weight(1f))
      Text(text = value, color = Vantage.Amber, fontSize = 15.sp, fontFamily = FontFamily.Monospace)
    }
    Slider(value = current, onValueChange = onChange, valueRange = range)
  }
}

@Composable
private fun SwitchRow(label: String, checked: Boolean, onToggle: () -> Unit) {
  Row(verticalAlignment = Alignment.CenterVertically) {
    Text(text = label, color = Vantage.Fg, fontSize = 15.sp, fontFamily = Vantage.Sans, modifier = Modifier.weight(1f))
    Switch(checked = checked, onCheckedChange = { onToggle() })
  }
}

@Composable
private fun Seg(label: String, on: Boolean, arabic: Boolean = false, onClick: () -> Unit) {
  Text(
      text = label,
      color = if (on) Vantage.Bg else Vantage.Fg,
      fontSize = 15.sp,
      fontWeight = FontWeight.Bold,
      fontFamily = if (arabic) Vantage.Arabic else Vantage.Sans,
      modifier =
          Modifier.clip(RoundedCornerShape(percent = 50))
              .background(if (on) Vantage.Amber else Vantage.Bg)
              .clickable(onClick = onClick)
              .padding(horizontal = 16.dp, vertical = 8.dp),
  )
}

/** Fades the controls in and out. */
@Composable
fun Chrome(visible: Boolean, content: @Composable () -> Unit) {
  AnimatedVisibility(visible = visible, enter = fadeIn(tween(150)), exit = fadeOut(tween(400))) { content() }
}
