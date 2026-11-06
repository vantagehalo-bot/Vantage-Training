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

/** Free-tier Gemini models, best first; lite models carry a usable daily quota. */
val GEMINI_FALLBACKS = listOf("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash")

class MetaModelClient(
    private val apiKey: String,
    private val modelId: String,
    private val apiBase: String,
    /** Tried in order when a model is missing (404), out of quota (429) or down (503). */
    private val fallbackModels: List<String> = emptyList(),
) {
  companion object {
    private const val TAG = "Vantage:Model"
    private const val CONNECT_TIMEOUT_MS = 8_000
    private const val READ_TIMEOUT_MS = 20_000
    // Long edge of the frame sent to the model. Enough for signs and medicine boxes, small enough
    // to keep the round trip near the 3 s budget on a phone connection.
    private const val MAX_EDGE_PX = 768
    private const val JPEG_QUALITY = 70
    // Muse Spark is a reasoning model: hidden reasoning counts against this limit, so it must be
    // far above the ~40 spoken tokens we want or the visible answer comes back empty.
    private const val MAX_TOKENS = 4096
  }

  val hasKey: Boolean
    get() = apiKey.isNotBlank()

  /** The model that answered last, so the chain starts from one that works. */
  @Volatile private var preferred: String = modelId

  /**
   * [history] is earlier (question, answer) pairs of this conversation, text only, oldest first, so
   * follow-ups like "the left one" make sense. Frames from earlier turns are never resent.
   */
  suspend fun ask(
      frame: Bitmap,
      systemPrompt: String,
      question: String,
      history: List<Pair<String, String>> = emptyList(),
  ): ModelResult =
      withContext(Dispatchers.IO) {
        if (!hasKey) return@withContext ModelResult.Failure(ModelResult.Failure.Kind.NO_KEY, "no key")
        val jpeg = encodeFrame(frame)
        val chain = (listOf(preferred, modelId) + fallbackModels).distinct()
        var last: ModelResult = ModelResult.Failure(ModelResult.Failure.Kind.EMPTY, "no model")
        for (model in chain) {
          val result = askModel(model, systemPrompt, question, jpeg, history)
          if (result is ModelResult.Answer) {
            preferred = model
            return@withContext result
          }
          last = result
          val retryable =
              result is ModelResult.Failure &&
                  result.kind == ModelResult.Failure.Kind.REJECTED &&
                  (result.detail.startsWith("HTTP 404") || result.detail.startsWith("HTTP 429") ||
                      result.detail.startsWith("HTTP 503") || result.detail.startsWith("HTTP 500"))
          if (!retryable) return@withContext result
          Log.w(TAG, "model $model unavailable (${result.detail.take(12)}); trying the next")
        }
        last
      }

  private fun askModel(
      model: String,
      systemPrompt: String,
      question: String,
      jpeg: String,
      history: List<Pair<String, String>>,
  ): ModelResult {
        val body = buildBody(model, systemPrompt, question, jpeg, history)
        var connection: HttpURLConnection? = null
        return try {
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
            Log.w(TAG, "Model API rejected the call: HTTP $code ($model)")
            return ModelResult.Failure(
                ModelResult.Failure.Kind.REJECTED,
                "HTTP $code $model ${summarizeError(err)}",
            )
          }
          val text = connection.inputStream.bufferedReader().use { it.readText() }
          val answer = parseAnswer(text)
          if (answer.isNullOrBlank()) {
            // Shape only, never the content: enough to see why nothing came back.
            Log.w(TAG, "Empty answer; response shape: ${describeShape(text)}")
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

  private fun buildBody(
      model: String,
      systemPrompt: String,
      question: String,
      jpegBase64: String,
      history: List<Pair<String, String>>,
  ): String {
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
    val messages = JSONArray().put(JSONObject().put("role", "system").put("content", systemPrompt))
    for ((q, a) in history) {
      messages.put(JSONObject().put("role", "user").put("content", q))
      messages.put(JSONObject().put("role", "assistant").put("content", a))
    }
    messages.put(JSONObject().put("role", "user").put("content", content))
    val body =
        JSONObject()
            .put("model", model)
            .put("messages", messages)
            .put("max_tokens", MAX_TOKENS)
            .put("temperature", 0.2)
    // Gemini's OpenAI-compatible endpoint: keep hidden reasoning short so the answer fits the cap.
    if (apiBase.contains("googleapis.com")) body.put("reasoning_effort", "low")
    return body.toString()
  }

  private fun parseAnswer(json: String): String? {
    return try {
      val root = JSONObject(json)
      // Chat-completions shape.
      root.optJSONArray("choices")?.let { choices ->
        if (choices.length() > 0) {
          val choice = choices.getJSONObject(0)
          val message = choice.optJSONObject("message")
          val fromContent = message?.let { textOf(it.opt("content")) }
          if (!fromContent.isNullOrBlank()) return fromContent
          // Some servers put a streamed/alternate text here.
          val fromText = textOf(choice.opt("text"))
          if (!fromText.isNullOrBlank()) return fromText
        }
      }
      // Responses-API shape (output_text, or output[].content[].text).
      val outputText = root.optString("output_text", "")
      if (outputText.isNotBlank()) return outputText
      root.optJSONArray("output")?.let { output ->
        val sb = StringBuilder()
        for (i in 0 until output.length()) {
          val item = output.optJSONObject(i) ?: continue
          val content = item.optJSONArray("content") ?: continue
          for (j in 0 until content.length()) {
            val part = content.optJSONObject(j) ?: continue
            val type = part.optString("type")
            if (type == "output_text" || type == "text") sb.append(part.optString("text"))
          }
        }
        if (sb.isNotBlank()) return sb.toString()
      }
      null
    } catch (e: Exception) {
      Log.w(TAG, "Could not parse model response: ${e.javaClass.simpleName}")
      null
    }
  }

  /** Text from a content field that may be a string or a list of typed parts. */
  private fun textOf(content: Any?): String? =
      when (content) {
        is String -> content
        is JSONArray ->
            buildString {
              for (i in 0 until content.length()) {
                val part = content.optJSONObject(i) ?: continue
                val type = part.optString("type")
                if (type == "text" || type == "output_text") append(part.optString("text"))
              }
            }
        else -> null
      }

  /** Top-level keys, finish reason and content length only; no answer text or frame. */
  private fun describeShape(json: String): String =
      try {
        val root = JSONObject(json)
        val keys = root.keys().asSequence().joinToString(",")
        val choice = root.optJSONArray("choices")?.optJSONObject(0)
        val finish = choice?.optString("finish_reason") ?: "-"
        val message = choice?.optJSONObject("message")
        val messageKeys = message?.keys()?.asSequence()?.joinToString(",") ?: "-"
        val contentLen = message?.optString("content", "")?.length ?: -1
        "keys=[$keys] finish=$finish messageKeys=[$messageKeys] contentLen=$contentLen"
      } catch (e: Exception) {
        "unparseable (${json.length} chars)"
      }

  private fun summarizeError(body: String): String =
      try {
        JSONObject(body).optJSONObject("error")?.optString("message")?.take(120) ?: ""
      } catch (e: Exception) {
        ""
      }
}
