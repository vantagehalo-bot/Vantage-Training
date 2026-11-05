// English - numbers and distances the way people say them, matching vantage_core.py's phrasing

package com.vantage.glasses.voice

object English {
  private val ONES =
      listOf("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
          "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
  private val TENS = listOf("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")

  fun number(n: Int): String =
      when {
        n < 0 -> "minus ${number(-n)}"
        n < 20 -> ONES[n]
        n < 100 -> TENS[n / 10] + if (n % 10 == 0) "" else "-${ONES[n % 10]}"
        n < 1000 -> "${ONES[n / 100]} hundred" + if (n % 100 == 0) "" else " and ${number(n % 100)}"
        else -> n.toString()
      }

  /** 40 → "forty centimetres", 150 → "one and a half metres", 300 → "three metres". */
  fun distance(cm: Int): String {
    if (cm < 97) {
      val r = maxOf(10, (cm + 2) / 5 * 5)
      return "${number(r)} centimetres"
    }
    val halves = (cm + 25) / 50
    val whole = halves / 2
    val half = halves % 2 == 1
    return when {
      whole == 1 && half -> "one and a half metres"
      whole == 1 -> "one metre"
      half -> "${number(whole)} and a half metres"
      else -> "${number(whole)} metres"
    }
  }

  /** 9.5 → "nine dirhams fifty", 12.0 → "twelve dirhams". */
  fun price(amount: Double, currency: String = "dirhams"): String {
    val whole = amount.toInt()
    val fils = ((amount - whole) * 100 + 0.5).toInt()
    val main = "${number(whole)} $currency"
    return if (fils == 0) main else "$main ${number(fils)}"
  }

  fun join(parts: List<String>): String =
      when (parts.size) {
        0 -> ""
        1 -> parts[0]
        else -> parts.dropLast(1).joinToString(", ") + " and " + parts.last()
      }
}
