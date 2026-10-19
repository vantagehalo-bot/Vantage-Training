// arabic.js — the Halo's voice in Arabic. Modern Standard Arabic, written for the ear:
// counted nouns agree with their numbers (مترين، ثلاثة أمتار، خمسين سنتيمترًا), the Halo
// never assumes the listener's gender (تحذير rather than توقف/توقفي, يُرجى + a verbal noun
// rather than an imperative), and بُعد carries its damma so no engine reads it as بَعد.
// Pure functions, no DOM: halo.js uses it in the ported announcer.

export const AR_NAMES = {
  person: "شخص", bicycle: "دراجة هوائية", car: "سيارة", motorcycle: "دراجة نارية", airplane: "طائرة", bus: "حافلة", train: "قطار",
  truck: "شاحنة", boat: "قارب", "traffic light": "إشارة مرور", "fire hydrant": "صنبور إطفاء", "stop sign": "لافتة توقف",
  "parking meter": "عداد مواقف", bench: "مقعد", bird: "طائر", cat: "قطة", dog: "كلب", horse: "حصان", sheep: "خروف", cow: "بقرة",
  elephant: "فيل", bear: "دب", zebra: "حمار وحشي", giraffe: "زرافة", backpack: "حقيبة ظهر", umbrella: "مظلة", handbag: "حقيبة يد",
  tie: "ربطة عنق", suitcase: "حقيبة سفر", frisbee: "قرص طائر", skis: "زلاجات", snowboard: "لوح تزلج", "sports ball": "كرة",
  kite: "طائرة ورقية", "baseball bat": "مضرب بيسبول", "baseball glove": "قفاز بيسبول", skateboard: "لوح تزلج",
  surfboard: "لوح ركوب الأمواج", "tennis racket": "مضرب تنس", bottle: "زجاجة", "wine glass": "كأس", cup: "كوب", fork: "شوكة",
  knife: "سكين", spoon: "ملعقة", bowl: "وعاء", banana: "موزة", apple: "تفاحة", sandwich: "شطيرة", orange: "برتقالة",
  broccoli: "بروكلي", carrot: "جزرة", "hot dog": "نقانق", pizza: "بيتزا", donut: "كعكة دونات", cake: "كعكة", chair: "كرسي",
  couch: "أريكة", "potted plant": "نبتة", bed: "سرير", "dining table": "طاولة", toilet: "مرحاض", tv: "تلفاز",
  laptop: "حاسوب محمول", mouse: "فأرة", remote: "جهاز تحكم", keyboard: "لوحة مفاتيح", "cell phone": "هاتف",
  microwave: "ميكروويف", oven: "فرن", toaster: "محمصة خبز", sink: "مغسلة", refrigerator: "ثلاجة", book: "كتاب", clock: "ساعة",
  vase: "مزهرية", scissors: "مقص", "teddy bear": "دمية دب", "hair drier": "مجفف شعر", toothbrush: "فرشاة أسنان",
  // the escape room's own classes
  keys: "المفاتيح", wallet: "المحفظة", banknote: "ورقة نقدية", "dog food": "طعام الكلب", door: "باب",
};
export const arLabel = (label) => AR_NAMES[label] || "شيء";
export const OBSTACLE = "عائق";

const DIR = { "on your left": "على يسارك", "on your right": "على يمينك", ahead: "أمامك" };
export const arDirection = (en) => DIR[en] || en;

// ------------------------------------------------------------------ numbers that agree
// Nouns: singular, the accusative singular used after 11–99, dual (nominative, genitive), plural, gender.
export const NOUN = {
  meter: { s: "متر", acc: "مترًا", d: ["متران", "مترين"], pl: "أمتار", g: "m" },
  cm: { s: "سنتيمتر", acc: "سنتيمترًا", d: ["سنتيمتران", "سنتيمترين"], pl: "سنتيمترات", g: "m" },
  person: { s: "شخص", acc: "شخصًا", d: ["شخصان", "شخصين"], pl: "أشخاص", g: "m" },
  minute: { s: "دقيقة", acc: "دقيقة", d: ["دقيقتان", "دقيقتين"], pl: "دقائق", g: "f" },
  second: { s: "ثانية", acc: "ثانية", d: ["ثانيتان", "ثانيتين"], pl: "ثوانٍ", g: "f" },
  dirham: { s: "درهم", acc: "درهمًا", d: ["درهمان", "درهمين"], pl: "دراهم", g: "m" },
};
// 3–9 take the opposite gender of the counted noun: ثلاثة أمتار، ثلاث دقائق
const UNIT_FOR_M = ["", "", "", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة"];
const UNIT_FOR_F = ["", "", "", "ثلاث", "أربع", "خمس", "ست", "سبع", "ثماني", "تسع"];
const TENS = { nom: ["", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"], obl: ["", "", "عشرين", "ثلاثين", "أربعين", "خمسين", "ستين", "سبعين", "ثمانين", "تسعين"] };

/** The number word(s) for 3..99 before a noun of gender g, in case c ("nom" or "gen"; accusative = genitive here). */
export function cardinal(n, g = "m", c = "gen") {
  const U = g === "m" ? UNIT_FOR_M : UNIT_FOR_F, obl = c !== "nom";
  if (n <= 9) return U[n];
  if (n === 10) return g === "m" ? "عشرة" : "عشر";
  if (n === 11) return g === "m" ? "أحد عشر" : "إحدى عشرة";
  if (n === 12) return g === "m" ? (obl ? "اثني عشر" : "اثنا عشر") : (obl ? "اثنتي عشرة" : "اثنتا عشرة");
  if (n < 20) return `${U[n - 10]} ${g === "m" ? "عشر" : "عشرة"}`;
  const t = Math.floor(n / 10), u = n % 10, tens = TENS[obl ? "obl" : "nom"][t];
  if (!u) return tens;
  const one = u === 1 ? (g === "m" ? "واحد" : "إحدى") : u === 2 ? (g === "m" ? (obl ? "اثنين" : "اثنان") : (obl ? "اثنتين" : "اثنتان")) : U[u];
  return `${one} و${tens}`;
}
/** n of a noun, agreeing: 1 متر، 2 مترين، 5 أمتار، 15 مترًا. `bare1` drops the word "one". */
export function count(n, noun, c = "gen", { bare1 = false } = {}) {
  const N = NOUN[noun];
  if (n === 1) return bare1 ? N.s : `${N.s} ${N.g === "m" ? "واحد" : "واحدة"}`;
  if (n === 2) return N.d[c === "nom" ? 0 : 1];
  if (n <= 10) return `${cardinal(n, N.g, c)} ${N.pl}`;
  if (n < 100) return `${cardinal(n, N.g, c)} ${N.acc}`;
  if (n === 100) return `مئة ${N.s}`;
  return `${n} ${N.acc}`;
}

/** A distance after "على بُعد" (genitive): centimetres in fives under a metre, then half metres. */
export function arDistance(cm) {
  if (cm == null) return "";
  if (cm < 97.5) return count(Math.max(10, Math.round(cm / 5) * 5), "cm", "gen");
  const halves = Math.round(cm / 50), whole = Math.floor(halves / 2), half = halves % 2 === 1;
  const w = whole === 1 ? "متر" : count(whole, "meter", "gen");
  return w + (half ? " ونصف" : "");
}
export const at = (cm) => `على بُعد ${arDistance(cm)}`;

/** "أ، ب، وج" */
export function joinAr(parts) { return parts.length < 2 ? (parts[0] || "") : `${parts.slice(0, -1).join("، ")}، و${parts[parts.length - 1]}`; }

// ------------------------------------------------------------------ the announcer's phrases
export const AR = {
  critical: (name, cm) => cm != null ? `تحذير: ${name} أمامك مباشرة، ${at(cm)}` : `تحذير: ${name} أمامك مباشرة`,
  caution: (name, cm, fast) => `${name} أمامك` + (cm != null ? `، ${at(cm)}` : "") + (fast ? "، اقتراب سريع" : ""),
  clear: "الطريق خالٍ",
  nothing: "لا شيء أمامك",
  describe: (name, dirEn) => `${name} ${arDirection(dirEn)}`,
  sceneDistance: (cm) => `أقرب شيء أمامك ${at(cm)}`,
  ready: "فانتاج جاهز",
  describeOn: "وضع الوصف مُفعّل", describeOff: "وضع الوصف متوقف",
  unmuted: "الصوت مُفعّل",
  sos: "أُرسل نداء الاستغاثة، وشُورك موقعك مع جهة الاتصال.",
  byEar: "بالسمع فقط. المهمة: الوصول إلى الباب.",
  zoom: (z) => ({ 1.5: "تكبير مرة ونصف", 2: "تكبير مرتين", 2.5: "تكبير مرتين ونصف", 3: "تكبير ثلاث مرات" })[z] || "تكبير",
  unsure: "قد لا تكون القراءة دقيقة، لكن المكتوب:",
};

/** Seconds as spoken Arabic, nominative: "دقيقتان وعشرون ثانية". */
export function arDuration(t) {
  const m = Math.floor(t / 60), s = Math.round(t % 60), parts = [];
  if (m) parts.push(count(m, "minute", "nom"));
  if (s || !m) parts.push(count(Math.max(1, s), "second", "nom"));
  return parts.join(" و");
}
