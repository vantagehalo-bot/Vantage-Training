// WelcomeScreen - "Welcome to Vantage on Meta": Vee introduces herself, one tap opens the eyes

package com.vantage.glasses.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vantage.glasses.assist.AssistLanguage
import com.vantage.glasses.assist.AssistPhase

@Composable
fun WelcomeScreen(
    phase: AssistPhase,
    language: AssistLanguage,
    canBegin: Boolean,
    onGreet: () -> Unit,
    onBegin: () -> Unit,
    onToggleLanguage: () -> Unit,
    onMockSetup: () -> Unit,
) {
  LaunchedEffect(Unit) { onGreet() }
  val arabic = language == AssistLanguage.ARABIC
  Box(
      modifier =
          Modifier.fillMaxSize()
              .background(Brush.verticalGradient(listOf(Vantage.Bg, Vantage.Surface, Vantage.Bg)))
              .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null, enabled = canBegin, onClick = onBegin)
              .statusBarsPadding()
              .navigationBarsPadding()
              .padding(28.dp),
  ) {
    Row(modifier = Modifier.align(Alignment.TopEnd)) {
      Text(
          text = language.label,
          color = Vantage.Bg,
          fontSize = 13.sp,
          fontWeight = FontWeight.Bold,
          fontFamily = Vantage.Sans,
          modifier =
              Modifier.clip(RoundedCornerShape(percent = 50))
                  .background(Vantage.Amber)
                  .clickable(onClick = onToggleLanguage)
                  .padding(horizontal = 12.dp, vertical = 5.dp),
      )
    }
    Column(
        modifier = Modifier.align(Alignment.Center).fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
      EyeAvatar(phase = phase, size = 150.dp)
      Text(
          text = "Welcome to Vantage",
          color = Vantage.Fg,
          fontSize = 34.sp,
          fontWeight = FontWeight.Bold,
          fontFamily = Vantage.Sans,
          textAlign = TextAlign.Center,
      )
      Text(
          text = "on Meta glasses",
          color = Vantage.Amber,
          fontSize = 18.sp,
          fontWeight = FontWeight.Bold,
          fontFamily = Vantage.Sans,
          letterSpacing = 3.sp,
          textAlign = TextAlign.Center,
      )
      Text(
          text =
              if (arabic) "أنا ڤي، عيناك على هذه النظارة. اضغط لأنظر، مرتين لأقرأ، مطولاً لتسألني."
              else "I'm Vee, your eyes on these glasses.\nTap and I look. Double tap and I read.\nHold and ask me anything.",
          color = Vantage.Muted,
          fontSize = if (arabic) 20.sp else 17.sp,
          lineHeight = if (arabic) 32.sp else 26.sp,
          fontFamily = if (arabic) Vantage.Arabic else Vantage.Sans,
          textAlign = TextAlign.Center,
          modifier = Modifier.padding(horizontal = 12.dp),
      )
    }
    Column(
        modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
      Text(
          text = if (canBegin) "Begin" else "Waiting for glasses…",
          color = if (canBegin) Vantage.Bg else Vantage.Muted,
          fontSize = 20.sp,
          fontWeight = FontWeight.Bold,
          fontFamily = Vantage.Sans,
          textAlign = TextAlign.Center,
          modifier =
              Modifier.fillMaxWidth()
                  .clip(RoundedCornerShape(percent = 50))
                  .background(if (canBegin) Vantage.Amber else Vantage.Surface)
                  .clickable(enabled = canBegin, onClick = onBegin)
                  .padding(vertical = 18.dp)
                  .testTag("welcome_begin"),
      )
      Text(
          text = if (canBegin) "or tap anywhere" else "No glasses? Open the mock device kit.",
          color = Vantage.Muted,
          fontSize = 13.sp,
          fontFamily = Vantage.Sans,
          modifier = Modifier.clickable(enabled = !canBegin, onClick = onMockSetup),
      )
      Spacer(modifier = Modifier.height(4.dp))
    }
  }
}
