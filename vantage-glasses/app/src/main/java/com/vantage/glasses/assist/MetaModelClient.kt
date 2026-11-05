// MetaModelClient - one frame + one question to Muse Spark on Meta Model API
//
// Meta Model API is OpenAI-compatible: POST {base}/chat/completions with a system prompt, the user's
// question and the frame as a base64 JPEG data URL. Plain HttpURLConnection keeps the sample free of
// extra dependencies.
//
// Privacy by design (docs/PRIVACY.md): the frame is downscaled, sent once and dropped. No frame,
// transcript or token is ever logged; only timings and status codes are.

package com.vantage.glasses.assist

import android.graphics.Bitmap
import android.util.Base64
import android.util.Log
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL
import java.net.UnknownHostException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

sealed interface ModelResult {
  data class Answer(val text: String) : ModelResult

  /** The call could not be made or did not return an answer. [spoken] is safe to say out loud. */
  data class Failure(val kind: Kind, val detail: String) : ModelResult {
    enum class Kind {
      NO_KEY,
      OFFLINE,
      TIMEOUT,
      REJECTED,
      EMPTY,
    }
  }
}

class MetaModelClient(
    private val apiKey: String,
    private val modelId: String,
    private val apiBase: String,
) {
  companion object {
    private const val TAG = "Vantage:Model"
    private const val CONNECT_TIMEOUT_MS = 8_000
    private const val READ_TIMEOUT_MS = 20_000
    // Long edge of the frame sent to the model. Enough for signs and medicine boxes, small enough
    // to keep the round trip near the 3 s budget on a phone connection.
    private const val MAX_EDGE_PX = 768
    private const val JPEG_QUALITY = 70
    private const val MAX_TOKENS = 160
  }

  val hasKey: Boolean
    get() = apiKey.isNotBlank()

  suspend fun ask(frame: Bitmap, systemPrompt: String, question: String): ModelResult =
      withContext(Dispatchers.IO) {
        if (!hasKey) return@withContext ModelResult.Failure(ModelResult.Failure.Kind.NO_KEY, "no key")
        val jpeg = encodeFrame(frame)
        val body = buildBody(systemPrompt, question, jpeg)
        var connection: HttpURLConnection? = null
        try {
          connection =
              (URL("${apiBase.trimEnd('/')}/chat/completions").openConnection()
                      as HttpURLConnection)
                  .apply {
                    requestMethod = "POST"
                    connectTimeout = CONNECT_TIMEOUT_MS
                    readTimeout = READ_TIMEOUT_MS
                    doOutput = true
                    setRequestProperty("Authorization", "Bearer $apiKey")
                    setRequestProperty("Content-Type", "application/json")
                    setRequestProperty("Accept", "application/json")
                  }
          connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
          val code = connection.responseCode
          if (code !in 200..299) {
            val err = connection.errorStream?.bufferedReader()?.use { it.readText() }.orEmpty()
            Log.w(TAG, "Model API rejected the call: HTTP $code")
            return@withContext ModelResult.Failure(
                ModelResult.Failure.Kind.REJECTED,
                "HTTP $code ${summarizeError(err)}",
            )
          }
          val text = connection.inputStream.bufferedReader().use { it.readText() }
          val answer = parseAnswer(text)
          if (answer.isNullOrBlank()) {
            ModelResult.Failure(ModelResult.Failure.Kind.EMPTY, "empty answer")
          } else {
            ModelResult.Answer(answer.trim())
          }
        } catch (e: SocketTimeoutException) {
          Log.w(TAG, "Model API timed out")
          ModelResult.Failure(ModelResult.Failure.Kind.TIMEOUT, "timeout")
        } catch (e: UnknownHostException) {
          Log.w(TAG, "Model API unreachable (no network)")
          ModelResult.Failure(ModelResult.Failure.Kind.OFFLINE, "offline")
        } catch (e: IOException) {
          Log.w(TAG, "Model API I/O failure: ${e.javaClass.simpleName}")
          ModelResult.Failure(ModelResult.Failure.Kind.OFFLINE, e.javaClass.simpleName)
        } finally {
          connection?.disconnect()
        }
      }

  private fun encodeFrame(frame: Bitmap): String {
    val longEdge = maxOf(frame.width, frame.height)
    val scaled =
        if (longEdge > MAX_EDGE_PX) {
          val scale = MAX_EDGE_PX.toFloat() / longEdge
          Bitmap.createScaledBitmap(
              frame,
              (frame.width * scale).toInt().coerceAtLeast(1),
              (frame.height * scale).toInt().coerceAtLeast(1),
              true,
          )
        } else frame
    val out = ByteArrayOutputStream()
    scaled.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out)
    if (scaled !== frame) scaled.recycle()
    return Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
  }

  private fun buildBody(systemPrompt: String, question: String, jpegBase64: String): String {
    val content =
        JSONArray()
            .put(JSONObject().put("type", "text").put("text", question))
            .put(
                JSONObject()
                    .put("type", "image_url")
                    .put(
                        "image_url",
                        JSONObject().put("url", "data:image/jpeg;base64,$jpegBase64"),
                    ),
            )
    val messages =
        JSONArray()
            .put(JSONObject().put("role", "system").put("content", systemPrompt))
            .put(JSONObject().put("role", "user").put("content", content))
    return JSONObject()
        .put("model", modelId)
        .put("messages", messages)
        .put("max_tokens", MAX_TOKENS)
        .put("temperature", 0.2)
        .toString()
  }

  private fun parseAnswer(json: String): String? {
    return try {
      val root = JSONObject(json)
      val choices = root.optJSONArray("choices") ?: return null
      if (choices.length() == 0) return null
      val message = choices.getJSONObject(0).optJSONObject("message") ?: return null
      when (val content = message.opt("content")) {
        is String -> content
        is JSONArray -> {
          // Some OpenAI-compatible servers return content as a list of parts.
          buildString {
            for (i in 0 until content.length()) {
              val part = content.optJSONObject(i) ?: continue
              if (part.optString("type") == "text") append(part.optString("text"))
            }
          }
        }
        else -> null
      }
    } catch (e: Exception) {
      Log.w(TAG, "Could not parse model response: ${e.javaClass.simpleName}")
      null
    }
  }

  private fun summarizeError(body: String): String =
      try {
        JSONObject(body).optJSONObject("error")?.optString("message")?.take(120) ?: ""
      } catch (e: Exception) {
        ""
      }
}
