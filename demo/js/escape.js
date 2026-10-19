// escape.js — "Leaving for work": a small escape room played with low vision. The picture is
// blurred the way a lot of blind and partially sighted people see; the Halo's boxes and voice
// are what find the keys, the dog's food and the money. Walk up to a thing and face it to
// pick it up or use it. The front door opens when everything is done.
import { Priority } from "./halo.js";
import { isAr, tr } from "./lang.js";
import { arDuration, joinAr } from "./arabic.js";

const REACH = 1.2, FACE_DEG = 32, DWELL_S = 0.35, NAG_S = 5;

export class Escape {
  constructor({ world, speech, ui, onFinish = () => {} }) {
    Object.assign(this, { world, speech, ui, onFinish });
    this.active = false;
  }

  start(def) {
    this.def = def; this.active = true; this.done = false;
    this.items = new Map(def.items.map(i => [i.id, { ...i, used: false, dwell: 0 }]));
    this.s = { keys: false, food: false, fed: false, wallet: false, note: false, t0: performance.now() / 1000, nagAt: 0, said: new Set() };
    this.ui.card.hidden = true; this.ui.panel.hidden = false;
    this.render();
    this.say(tr("Leaving for work. Find your keys, feed the dog, and make sure you have a hundred dirhams. Then the front door.",
      "حان وقت الخروج إلى العمل. المطلوب: العثور على المفاتيح، وإطعام الكلب، والتأكد من وجود مئة درهم في المحفظة، ثم الخروج من الباب الأمامي."), 10);
  }
  stop() { this.active = false; this.ui.panel.hidden = true; this.ui.card.hidden = true; }

  say(text, age = 6, prio = Priority.INFO) { this.speech.say(text, prio, false, age); }
  get money() { return (this.s.wallet ? 50 : 0) + (this.s.note ? 50 : 0); }
  get elapsed() { return performance.now() / 1000 - this.s.t0; }

  /** Called every frame after the world moves. */
  update(dt) {
    if (!this.active || this.done) return;
    const p = this.world.getPose();
    // the camera looks down -z at yaw 0
    const fx = -Math.sin(p.yaw), fz = -Math.cos(p.yaw);
    let target = null, best = Infinity;
    for (const it of this.items.values()) {
      if (it.used && it.id !== "door" && it.id !== "bowl") continue;
      const o = it.obj; if (!o.visible) continue;
      const dx = o.position.x - p.x, dz = o.position.z - p.z, d = Math.hypot(dx, dz);
      const reach = it.reach || REACH;
      if (d > reach) { it.dwell = 0; continue; }
      const ang = Math.acos(Math.max(-1, Math.min(1, (dx * fx + dz * fz) / Math.max(d, 1e-3)))) * 180 / Math.PI;
      if (ang > FACE_DEG && d > 0.45) { it.dwell = 0; continue; }
      if (d < best) { best = d; target = it; }
    }
    for (const it of this.items.values()) if (it !== target) it.dwell = 0;
    if (target) { target.dwell += dt; if (target.dwell >= DWELL_S) { target.dwell = -1e9; this.use(target); } }
    this.renderClock();
  }

  use(it) {
    const s = this.s, now = performance.now() / 1000;
    const nag = (key, text) => { if (now - s.nagAt < NAG_S && s.lastNag === key) return; s.nagAt = now; s.lastNag = key; this.say(text); };
    switch (it.id) {
      case "keys": it.used = true; it.obj.visible = false; s.keys = true; this.say(tr("Keys. In your pocket.", "المفاتيح. صارت في الجيب.")); break;
      case "food": it.used = true; it.obj.visible = false; s.food = true;
        this.say(s.fed ? tr("Dog food.", "طعام الكلب.") : tr("Dog food. Now the dog's bowl.", "طعام الكلب. والآن وعاء الكلب.")); break;
      case "wallet": it.used = true; it.obj.visible = false; s.wallet = true;
        this.say(s.note ? tr("Wallet. With the note, one hundred dirhams.", "المحفظة. ومع الورقة النقدية صار المبلغ مئة درهم.")
          : tr("Wallet. The Halo reads fifty dirhams inside. You need a hundred.", "المحفظة. فيها خمسون درهمًا، والمطلوب مئة.")); break;
      case "note": it.used = true; it.obj.visible = false; s.note = true;
        this.say(s.wallet ? tr("Fifty dirhams. That makes one hundred.", "ورقة من فئة خمسين درهمًا. صار المجموع مئة درهم.")
          : tr("A fifty dirham note. Put it with your wallet.", "ورقة من فئة خمسين درهمًا. ما زالت المحفظة مطلوبة.")); break;
      case "bowl":
        if (s.fed) { it.dwell = 0; return; }
        if (!s.food) { it.dwell = 0; nag("bowl", tr("The dog's bowl. It's empty. Find the dog food first.", "وعاء الكلب فارغ. المطلوب أولًا طعام الكلب.")); return; }
        s.fed = true; it.used = true; const k = it.obj.getObjectByName("kibble"); if (k) k.visible = true;
        this.say(tr("Bowl filled. The dog is eating.", "امتلأ الوعاء. الكلب يأكل الآن.")); break;
      case "dog": it.dwell = 0; if (!s.said.has("dog")) { s.said.add("dog");
        this.say(s.fed ? tr("The dog, eating.", "الكلب يأكل.") : tr("The dog. Hungry. Its bowl is close by.", "الكلب جائع، ووعاؤه قريب منه.")); } return;
      case "door": {
        it.dwell = 0;
        const missing = [];
        if (!s.keys) missing.push(tr("your keys", "المفاتيح"));
        if (!s.fed) missing.push(tr("the dog's breakfast", "إطعام الكلب"));
        if (this.money < 100) missing.push(this.money ? tr("another fifty dirhams", "خمسون درهمًا أخرى") : tr("your wallet", "المحفظة"));
        if (missing.length) {
          nag("door", isAr() ? `الباب الأمامي. ليس بعد، ما زال المطلوب: ${joinAr(missing)}.`
            : `The front door. Not yet: ${missing.length > 1 ? missing.slice(0, -1).join(", ") + " and " + missing[missing.length - 1] : missing[0]}.`);
          return;
        }
        this.finish(); return;
      }
    }
    this.render();
  }

  finish() {
    this.done = true; const t = this.elapsed, bumps = this.world.bumps.length;
    const mm = Math.floor(t / 60), ss = Math.round(t % 60);
    this.say(isAr() ? `فُتح الباب. انتهت المهمة، والوقت: ${arDuration(t)}.` : `Door open. Out for work in ${mm ? `${mm} minute${mm > 1 ? "s" : ""} ` : ""}${ss} seconds.`, 10);
    this.render();
    this.ui.cardTime.textContent = clock(t);
    this.ui.cardLine.textContent = `${bumps ? `${bumps} bump${bumps === 1 ? "" : "s"} on the way. ` : "Not a single bump. "}Everything was found with the Halo's boxes and voice through a blurred picture.`;
    this.ui.card.hidden = false;
    this.onFinish({ t, bumps });
  }

  render() {
    const s = this.s, ui = this.ui;
    const rows = [
      ["Find your keys", s.keys, ""],
      ["Feed the dog", s.fed, s.fed ? "" : s.food ? "food found, now the bowl" : ""],
      ["100 dirhams in your wallet", this.money >= 100, `${this.money} / 100`],
      ["Out the front door", this.done, ""],
    ];
    ui.list.innerHTML = rows.map(([t, ok, sub]) => `<li class="${ok ? "done" : ""}"><i></i><span>${t}${sub ? `<em>${sub}</em>` : ""}</span></li>`).join("");
    this.renderClock();
  }
  renderClock() { const c = clock(this.elapsed); if (this.ui.clock.textContent !== c) this.ui.clock.textContent = c; }
}
const clock = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
