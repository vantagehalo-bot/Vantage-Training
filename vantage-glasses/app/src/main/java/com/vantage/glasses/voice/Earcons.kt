// Earcons - the firmware's two-tone beep and three short cues, synthesised, no asset files
//
// The alert beep is _write_beep() from vantage_core.py: 150 ms of silence (covers Bluetooth
// wake-up clipping), 880 Hz for 90 ms, a 40 ms gap, 1320 Hz for 120 ms. The others are single or
// paired tones that never imitate the phone's system sounds.

package com.vantage.glasses.voice

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import kotlin.math.PI
import kotlin.math.sin

class Earcons {
  private val rate = 22_050
  private val cache = HashMap<String, ShortArray>()

  private fun tone(hz: Double, ms: Int, gain: Double = 0.6): ShortArray {
    val n = rate * ms / 1000
    val out = ShortArray(n)
    val fade = minOf(n / 6, rate / 100)
    for (i in 0 until n) {
      val env =
          when {
            i < fade -> i.toDouble() / fade
            i > n - fade -> (n - i).toDouble() / fade
            else -> 1.0
          }
      out[i] = (sin(2 * PI * hz * i / rate) * gain * env * Short.MAX_VALUE).toInt().toShort()
    }
    return out
  }

  private fun silence(ms: Int) = ShortArray(rate * ms / 1000)

  private fun seq(vararg parts: ShortArray): ShortArray {
    val total = parts.sumOf { it.size }
    val out = ShortArray(total)
    var p = 0
    for (part in parts) {
      part.copyInto(out, p)
      p += part.size
    }
    return out
  }

  private fun pcm(name: String): ShortArray =
      cache.getOrPut(name) {
        when (name) {
          "alert" -> seq(silence(150), tone(880.0, 90), silence(40), tone(1320.0, 120))
          "listening" -> seq(silence(60), tone(660.0, 70), silence(30), tone(990.0, 70))
          "working" -> seq(silence(40), tone(880.0, 60))
          "done" -> seq(silence(40), tone(1320.0, 60), silence(20), tone(880.0, 90))
          "error" -> seq(silence(40), tone(330.0, 160))
          "click" -> seq(silence(20), tone(1800.0, 25, 0.4))
          else -> tone(880.0, 60)
        }
      }

  fun play(name: String) {
    val data = pcm(name)
    val track =
        AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build(),
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(rate)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build(),
            )
            .setTransferMode(AudioTrack.MODE_STATIC)
            .setBufferSizeInBytes(data.size * 2)
            .build()
    track.write(data, 0, data.size)
    track.setNotificationMarkerPosition(data.size)
    track.setPlaybackPositionUpdateListener(
        object : AudioTrack.OnPlaybackPositionUpdateListener {
          override fun onMarkerReached(t: AudioTrack?) {
            runCatching { t?.release() }
          }

          override fun onPeriodicNotification(t: AudioTrack?) = Unit
        },
    )
    track.play()
  }
}
