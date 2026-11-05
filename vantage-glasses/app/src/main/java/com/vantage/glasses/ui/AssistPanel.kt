// AssistPanel - Vantage's controls over the live preview
//
// Three big pills (Look, Read, Ask) are the silent path; Ask is the voice path. The card above them
// shows what was heard and what was said, so a sighted helper (or a mentor at a demo) can follow the
// conversation. The privacy line is always visible: it is the app's capture notice.

package com.vantage.glasses.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Hearing
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material.icons.filled.Replay
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vantage.glasses.R
import com.vantage.glasses.assist.AssistPhase
import com.vantage.glasses.assist.AssistUiState

@Composable
fun AssistPanel(
    ui: AssistUiState,
    isPreviewLive: Boolean,
    onLook: () -> Unit,
    onRead: () -> Unit,
    onAsk: () -> Unit,
    onAgain: () -> Unit,
    onStop: () -> Unit,
    modifier: Modifier = Modifier,
) {
  val enabled = isPreviewLive && !ui.isBusy
  Column(
      modifier = modifier.fillMaxWidth().padding(horizontal = 20.dp),
      verticalArrangement = Arrangement.spacedBy(10.dp),
  ) {
    ConversationCard(ui = ui, isPreviewLive = isPreviewLive, onAgain = onAgain, onStop = onStop)

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
      AssistPill(
          modifier = Modifier.weight(1f).testTag("assist_look"),
          icon = Icons.Filled.Visibility,
          label = stringResource(R.string.assist_look),
          enabled = enabled,
          accent = AppColor.Green,
          onClick = onLook,
      )
      AssistPill(
          modifier = Modifier.weight(1f).testTag("assist_read"),
          icon = Icons.Filled.MenuBook,
          label = stringResource(R.string.assist_read),
          enabled = enabled,
          accent = AppColor.Yellow,
          onClick = onRead,
      )
      AssistPill(
          modifier = Modifier.weight(1f).testTag("assist_ask"),
          icon = Icons.Filled.Mic,
          label = stringResource(R.string.assist_ask),
          enabled = enabled,
          accent = AppColor.DeepBlue,
          onClick = onAsk,
      )
    }

    Text(
        text = stringResource(R.string.assist_privacy_line),
        color = Color.White.copy(alpha = 0.6f),
        fontSize = 11.sp,
        modifier = Modifier.fillMaxWidth().testTag("assist_privacy_line"),
    )
  }
}

@Composable
private fun ConversationCard(
    ui: AssistUiState,
    isPreviewLive: Boolean,
    onAgain: () -> Unit,
    onStop: () -> Unit,
) {
  val status =
      when {
        !isPreviewLive -> stringResource(R.string.assist_needs_preview)
        !ui.hasApiKey -> stringResource(R.string.assist_no_key)
        ui.phase == AssistPhase.LISTENING -> stringResource(R.string.assist_listening)
        ui.phase == AssistPhase.CAPTURING -> stringResource(R.string.assist_capturing)
        ui.phase == AssistPhase.THINKING -> stringResource(R.string.assist_thinking)
        ui.phase == AssistPhase.SPEAKING -> stringResource(R.string.assist_speaking)
        else -> stringResource(R.string.assist_idle)
      }
  Column(
      modifier =
          Modifier.fillMaxWidth()
              .clip(RoundedCornerShape(20.dp))
              .background(Color.Black.copy(alpha = 0.55f))
              .padding(horizontal = 16.dp, vertical = 12.dp),
      verticalArrangement = Arrangement.spacedBy(6.dp),
  ) {
    Row(verticalAlignment = Alignment.CenterVertically) {
      if (ui.isBusy) {
        CircularProgressIndicator(
            color = Color.White,
            strokeWidth = 2.dp,
            modifier = Modifier.size(14.dp),
        )
        Spacer(modifier = Modifier.width(8.dp))
      }
      Text(
          text = status,
          color = Color.White.copy(alpha = 0.8f),
          fontSize = 13.sp,
          fontWeight = FontWeight.Medium,
          modifier = Modifier.weight(1f).testTag("assist_status"),
      )
      if (ui.ackMillis != null && ui.totalMillis != null) {
        Text(
            text =
                stringResource(
                    R.string.assist_latency,
                    "%.1f".format(ui.ackMillis / 1000f),
                    "%.1f".format(ui.totalMillis / 1000f),
                ),
            color = Color.White.copy(alpha = 0.55f),
            fontSize = 11.sp,
            fontFamily = FontFamily.Monospace,
        )
      }
    }
    if (ui.heard.isNotBlank()) {
      Row(verticalAlignment = Alignment.Top) {
        Icon(
            imageVector = Icons.Filled.Hearing,
            contentDescription = null,
            tint = Color.White.copy(alpha = 0.6f),
            modifier = Modifier.size(16.dp),
        )
        Spacer(modifier = Modifier.width(8.dp))
        Text(
            text = ui.heard,
            color = Color.White.copy(alpha = 0.75f),
            fontSize = 14.sp,
            modifier = Modifier.testTag("assist_heard"),
        )
      }
    }
    if (ui.spoken.isNotBlank()) {
      Text(
          text = ui.spoken,
          color = if (ui.lastWasError) AppColor.Yellow else Color.White,
          fontSize = 17.sp,
          fontWeight = FontWeight.SemiBold,
          lineHeight = 22.sp,
          modifier = Modifier.testTag("assist_spoken"),
      )
      Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        SmallAction(
            icon = Icons.Filled.Replay,
            label = stringResource(R.string.assist_again),
            enabled = ui.canRepeat && ui.phase == AssistPhase.IDLE,
            onClick = onAgain,
        )
        SmallAction(
            icon = Icons.Filled.Stop,
            label = stringResource(R.string.assist_stop),
            enabled = ui.phase != AssistPhase.IDLE,
            onClick = onStop,
        )
      }
    }
  }
}

@Composable
private fun AssistPill(
    icon: ImageVector,
    label: String,
    enabled: Boolean,
    accent: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
  Row(
      modifier =
          modifier
              .height(56.dp)
              .clip(RoundedCornerShape(percent = 50))
              .background(if (enabled) accent.copy(alpha = 0.85f) else Color.White.copy(alpha = 0.08f))
              .clickable(enabled = enabled, onClick = onClick)
              .semantics { contentDescription = label },
      horizontalArrangement = Arrangement.Center,
      verticalAlignment = Alignment.CenterVertically,
  ) {
    Icon(
        imageVector = icon,
        contentDescription = null,
        tint = if (enabled) Color.White else Color.White.copy(alpha = 0.45f),
        modifier = Modifier.size(22.dp),
    )
    Spacer(modifier = Modifier.width(8.dp))
    Text(
        text = label,
        color = if (enabled) Color.White else Color.White.copy(alpha = 0.45f),
        fontSize = 17.sp,
        fontWeight = FontWeight.Bold,
    )
  }
}

@Composable
private fun SmallAction(icon: ImageVector, label: String, enabled: Boolean, onClick: () -> Unit) {
  Row(
      modifier = Modifier.clickable(enabled = enabled, onClick = onClick).padding(vertical = 4.dp),
      verticalAlignment = Alignment.CenterVertically,
  ) {
    Icon(
        imageVector = icon,
        contentDescription = null,
        tint = Color.White.copy(alpha = if (enabled) 0.9f else 0.35f),
        modifier = Modifier.size(16.dp),
    )
    Spacer(modifier = Modifier.width(4.dp))
    Text(
        text = label,
        color = Color.White.copy(alpha = if (enabled) 0.9f else 0.35f),
        fontSize = 13.sp,
        fontWeight = FontWeight.Medium,
    )
  }
}
