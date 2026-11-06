// EyeAvatar - Vee, drawn: the Vantage eye mark that blinks, widens to listen, pulses to speak

package com.vantage.glasses.ui

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.vantage.glasses.assist.AssistPhase
import kotlin.math.cos
import kotlin.math.sin

@Composable
fun EyeAvatar(phase: AssistPhase, size: Dp = 120.dp, modifier: Modifier = Modifier) {
  val t = rememberInfiniteTransition(label = "eye")
  // One slow cycle; the lid closes for a moment near the end, like a blink.
  val cycle by t.animateFloat(0f, 1f, infiniteRepeatable(tween(3600, easing = LinearEasing)), label = "cycle")
  val fast by t.animateFloat(0f, 1f, infiniteRepeatable(tween(900, easing = LinearEasing)), label = "fast")
  val blink = if (cycle in 0.93f..0.97f) 0.12f else 1f
  val irisTarget =
      when (phase) {
        AssistPhase.LISTENING -> 1.25f
        AssistPhase.THINKING, AssistPhase.CAPTURING -> 0.85f
        AssistPhase.SPEAKING -> 1.05f
        AssistPhase.IDLE -> 1f
      }
  val iris by animateFloatAsState(irisTarget, tween(260), label = "iris")
  val pulse = if (phase == AssistPhase.SPEAKING) 1f + 0.08f * sin(fast * 6.2832f) else 1f
  val orbit = if (phase == AssistPhase.THINKING || phase == AssistPhase.CAPTURING) fast * 6.2832f else 0f

  Canvas(modifier = modifier.then(Modifier.size(size))) {
    val c = Offset(this.size.width / 2, this.size.height / 2)
    val r = this.size.minDimension / 2
    scale(scaleX = 1f, scaleY = blink, pivot = c) {
      // Outer ring, warm off-white, like the logo mark.
      drawCircle(color = Vantage.Fg, radius = r * 0.92f, center = c, style = Stroke(width = r * 0.11f))
      // Iris, amber, breathing with speech.
      drawCircle(color = Vantage.Amber, radius = r * 0.5f * iris * pulse, center = c)
      // Pupil; it orbits a little while thinking.
      val pupil = Offset(c.x + r * 0.12f * cos(orbit), c.y + r * 0.12f * sin(orbit))
      drawCircle(color = Vantage.Bg, radius = r * 0.2f * iris, center = pupil)
      // Catchlight.
      drawCircle(color = Vantage.Fg, radius = r * 0.07f, center = Offset(pupil.x - r * 0.1f, pupil.y - r * 0.12f))
    }
  }
}
