// Theme - the Vantage look, carried over from the Vantage Lens demo and vantagevision.ai
//
// Warm graphite rather than pure black (pure white on pure black causes halation for people with
// astigmatism), warm off-white text, one accent: Signal Amber, the hazard colour the product's own
// clips use. Atkinson Hyperlegible for Latin text, Noto Naskh Arabic for Arabic.

package com.vantage.glasses.ui

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import com.vantage.glasses.R

object AppColor {
  // Kept for Meta's sample screens (mock device sheet, registration).
  val Green = Color(0xFF61BC63)
  val Red = Color(0xFFFF3B30)
  val Yellow = Color(0xFFFFCC00)
  val DeepBlue = Color(0xFF0064E0)
  val DestructiveBackground = Color(0xFFFFD8DB)
  val DestructiveForeground = Color(0xFFAA071E)
  val RecordAccent = Color(0xFFFF453A)
  val UpdateRequiredBackground = Color(0xFFFFF4D6)
  val UpdateRequiredForeground = Color(0xFF8A4B00)
}

object Vantage {
  val Bg = Color(0xFF121110)
  val Surface = Color(0xFF1C1A18)
  val Stage = Color(0xFF050505)
  val Line = Color(0xFF2A2724)
  val LineStrong = Color(0xFF6B655E)
  val Fg = Color(0xFFECE8E1)
  val Muted = Color(0xFFBDB6AC)
  val Amber = Color(0xFFF0A830)
  val AmberDeep = Color(0xFFC86730)
  val Scrim = Color(0x99121110)

  val Sans: FontFamily =
      FontFamily(
          Font(R.font.atkinson_regular, FontWeight.Normal),
          Font(R.font.atkinson_bold, FontWeight.Bold),
      )
  val Arabic: FontFamily = FontFamily(Font(R.font.noto_naskh_arabic, FontWeight.Normal))
}
