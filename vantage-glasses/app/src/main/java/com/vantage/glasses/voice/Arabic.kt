// Arabic - the Halo's voice in Arabic, ported from the Vantage Lens demo (demo/js/arabic.js)
//
// Modern Standard Arabic written for the ear: counted nouns agree with their numbers (مترين،
// ثلاثة أمتار، خمسين سنتيمترًا), the voice never assumes the listener's gender (يُرجى + a verbal
// noun rather than an imperative), and بُعد carries its damma so no engine reads it as بَعد.
// Pure functions, no Android.

package com.vantage.glasses.voice

object Arabic {
  val NAMES: Map<String, String> =
      mapOf(
          "person" to "شخص", "bicycle" to "دراجة هوائية", "car" to "سيارة", "motorcycle" to "دراجة نارية",
          "airplane" to "طائرة", "bus" to "حافلة", "train" to "قطار", "truck" to "شاحنة", "boat" to "قارب",
          "traffic light" to "إشارة مرور", "fire hydrant" to "صنبور إطفاء", "stop sign" to "لافتة توقف",
          "parking meter" to "عداد مواقف", "bench" to "مقعد", "bird" to "طائر", "cat" to "قطة", "dog" to "كلب",
          "horse" to "حصان", "sheep" to "خروف", "cow" to "بقرة", "elephant" to "فيل", "bear" to "دب",
          "zebra" to "حمار وحشي", "giraffe" to "زرافة", "backpack" to "حقيبة ظهر", "umbrella" to "مظلة",
          "handbag" to "حقيبة يد", "tie" to "ربطة عنق", "suitcase" to "حقيبة سفر", "frisbee" to "قرص طائر",
          "skis" to "زلاجات", "snowboard" to "لوح تزلج", "sports ball" to "كرة", "kite" to "طائرة ورقية",
          "baseball bat" to "مضرب بيسبول", "baseball glove" to "قفاز بيسبول", "skateboard" to "لوح تزلج",
          "surfboard" to "لوح ركوب الأمواج", "tennis racket" to "مضرب تنس", "bottle" to "زجاجة",
          "wine glass" to "كأس", "cup" to "كوب", "fork" to "شوكة", "knife" to "سكين", "spoon" to "ملعقة",
          "bowl" to "وعاء", "banana" to "موزة", "apple" to "تفاحة", "sandwich" to "شطيرة", "orange" to "برتقالة",
          "broccoli" to "بروكلي", "carrot" to "جزرة", "hot dog" to "نقانق", "pizza" to "بيتزا",
          "donut" to "كعكة دونات", "cake" to "كعكة", "chair" to "كرسي", "couch" to "أريكة",
          "potted plant" to "نبتة", "bed" to "سرير", "dining table" to "طاولة", "toilet" to "مرحاض",
          "tv" to "تلفاز", "laptop" to "حاسوب محمول", "mouse" to "فأرة", "remote" to "جهاز تحكم",
          "keyboard" to "لوحة مفاتيح", "cell phone" to "هاتف", "microwave" to "ميكروويف", "oven" to "فرن",
          "toaster" to "محمصة خبز", "sink" to "مغسلة", "refrigerator" to "ثلاجة", "book" to "كتاب",
          "clock" to "ساعة", "vase" to "مزهرية", "scissors" to "مقص", "teddy bear" to "دمية دب",
          "hair drier" to "مجفف شعر", "toothbrush" to "فرشاة أسنان", "door" to "باب",
      )

  const val OBSTACLE = "عائق"

  fun label(en: String): String = NAMES[en] ?: "شيء"

  fun direction(en: String): String =
      when (en) {
        "on your left" -> "على يسارك"
        "on your right" -> "على يمينك"
        "ahead" -> "أمامك"
        else -> en
      }

  /** Singular, accusative singular (after 11–99), dual (nominative, genitive), plural, gender. */
  class Noun(val s: String, val acc: String, val dNom: String, val dGen: String, val pl: String, val g: Char)

  val NOUNS: Map<String, Noun> =
      mapOf(
          "meter" to Noun("متر", "مترًا", "متران", "مترين", "أمتار", 'm'),
          "cm" to Noun("سنتيمتر", "سنتيمترًا", "سنتيمتران", "سنتيمترين", "سنتيمترات", 'm'),
          "person" to Noun("شخص", "شخصًا", "شخصان", "شخصين", "أشخاص", 'm'),
          "step" to Noun("خطوة", "خطوة", "خطوتان", "خطوتين", "خطوات", 'f'),
          "item" to Noun("صنف", "صنفًا", "صنفان", "صنفين", "أصناف", 'm'),
          "dirham" to Noun("درهم", "درهمًا", "درهمان", "درهمين", "دراهم", 'm'),
          "fils" to Noun("فلس", "فلسًا", "فلسان", "فلسين", "فلوس", 'm'),
      )

  private val UNIT_M = listOf("", "", "", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة")
  private val UNIT_F = listOf("", "", "", "ثلاث", "أربع", "خمس", "ست", "سبع", "ثماني", "تسع")
  private val TENS_NOM = listOf("", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون")
  private val TENS_OBL = listOf("", "", "عشرين", "ثلاثين", "أربعين", "خمسين", "ستين", "سبعين", "ثمانين", "تسعين")

  /** The number word(s) for 3..99 before a noun of gender [g], oblique (genitive/accusative) unless [nominative]. */
  fun cardinal(n: Int, g: Char = 'm', nominative: Boolean = false): String {
    val units = if (g == 'm') UNIT_M else UNIT_F
    val obl = !nominative
    return when {
      n <= 9 -> units[n]
      n == 10 -> if (g == 'm') "عشرة" else "عشر"
      n == 11 -> if (g == 'm') "أحد عشر" else "إحدى عشرة"
      n == 12 -> if (g == 'm') (if (obl) "اثني عشر" else "اثنا عشر") else (if (obl) "اثنتي عشرة" else "اثنتا عشرة")
      n < 20 -> "${units[n - 10]} ${if (g == 'm') "عشر" else "عشرة"}"
      else -> {
        val t = n / 10
        val u = n % 10
        val tens = (if (obl) TENS_OBL else TENS_NOM)[t]
        if (u == 0) tens
        else {
          val one =
              when (u) {
                1 -> if (g == 'm') "واحد" else "إحدى"
                2 -> if (g == 'm') (if (obl) "اثنين" else "اثنان") else (if (obl) "اثنتين" else "اثنتان")
                else -> units[u]
              }
          "$one و$tens"
        }
      }
    }
  }

  /** n of a noun, agreeing: 1 متر، 2 مترين، 5 أمتار، 15 مترًا. */
  fun count(n: Int, noun: String, nominative: Boolean = false, bare1: Boolean = false): String {
    val N = NOUNS[noun] ?: return "$n"
    return when {
      n == 1 -> if (bare1) N.s else "${N.s} ${if (N.g == 'm') "واحد" else "واحدة"}"
      n == 2 -> if (nominative) N.dNom else N.dGen
      n <= 10 -> "${cardinal(n, N.g, nominative)} ${N.pl}"
      n < 100 -> "${cardinal(n, N.g, nominative)} ${N.acc}"
      n == 100 -> "مئة ${N.s}"
      else -> "$n ${N.acc}"
    }
  }

  /** A distance after "على بُعد": centimetres in fives under a metre, then half metres. */
  fun distance(cm: Int): String {
    if (cm < 97) return count(maxOf(10, (cm + 2) / 5 * 5), "cm")
    val halves = (cm + 25) / 50
    val whole = halves / 2
    val half = halves % 2 == 1
    val w = if (whole == 1) "متر" else count(whole, "meter")
    return w + if (half) " ونصف" else ""
  }

  fun at(cm: Int): String = "على بُعد ${distance(cm)}"

  /** "أ، ب، وج" */
  fun join(parts: List<String>): String =
      when (parts.size) {
        0 -> ""
        1 -> parts[0]
        else -> parts.dropLast(1).joinToString("، ") + "، و" + parts.last()
      }

  /** A price in dirhams, spoken: 9.50 → تسعة دراهم ونصف; 12 → اثنا عشر درهمًا. */
  fun price(amount: Double): String {
    val whole = amount.toInt()
    val fils = ((amount - whole) * 100 + 0.5).toInt()
    val main = if (whole == 0) "" else count(whole, "dirham", nominative = true)
    val frac =
        when {
          fils == 0 -> ""
          fils == 50 -> "ونصف"
          fils == 25 -> "وربع"
          else -> "و${count(fils, "fils", nominative = true)}"
        }
    return listOf(main, frac).filter { it.isNotBlank() }.joinToString(" ")
  }
}
