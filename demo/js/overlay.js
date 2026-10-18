// overlay.js — draws the Halo preview exactly as the device does: a coloured box per
// tracked object with label and confidence, the target in red with its distance, the
// LiDAR aim crosshair, the distance bar with 50/100 cm ticks, the flashing banner and
// the "Spoken:" line. Frame space is the firmware's 640x480.
//   opts.view   {x,y,w,h} where the frame lands on the canvas (default: the whole canvas)
//   opts.live   true on the tablet camera: range is estimated from box size, say so
//   opts.quiet  boxes and crosshair only (the Ask panel)
import { Level, levelName, priorityName, spokenLabel } from "./halo.js";

export const COLORS = {
  [Level.CRITICAL]: "#e24b3b", [Level.CAUTION]: "#f0a830",
  [Level.CLEAR]: "#5ad25a", [Level.UNKNOWN]: "#8e8a83",
};
const RED = "#e24b3b", MONO = "11px 'Atkinson Hyperlegible Mono', ui-monospace, SFMono-Regular, Menlo, monospace";
const MONO_B = "bold 15px 'Atkinson Hyperlegible Mono', ui-monospace, Menlo, monospace";

export function drawOverlay(ctx, W, H, p, opts = {}) {
  const { tracks = [], hazard, lidarSample: lid, speech, cfg } = p;
  const now = performance.now() / 1000;
  const view = opts.view || { x: 0, y: 0, w: W, h: H };
  const HB = H - (opts.bottomInset || 0);   // HUD bottom edge
  const sx = view.w / cfg.width, sy = view.h / cfg.height, ox = view.x, oy = view.y;
  ctx.save();
  ctx.lineWidth = 2;

  // Tracks
  for (const t of tracks) {
    const [x, y, w, h] = t.box;
    const isTarget = hazard && hazard.target === t;
    const col = isTarget ? COLORS[Math.max(hazard.level, Level.CAUTION)] : "rgba(236,232,225,0.75)";
    ctx.strokeStyle = col; ctx.lineWidth = isTarget ? 3 : 1;
    ctx.strokeRect(ox + x * sx, oy + y * sy, w * sx, h * sy);
    const txt = `${spokenLabel(t.label)} ${t.score.toFixed(2)}`;
    ctx.font = MONO; const tw = ctx.measureText(txt).width + 8;
    const ly = Math.max(44, oy + y * sy);   // label stays below the status box when the box runs off the top
    ctx.fillStyle = isTarget ? col : "rgba(5,5,5,0.72)"; ctx.fillRect(ox + x * sx, ly - 15, tw, 15);
    ctx.fillStyle = isTarget ? "#000" : "#ece8e1"; ctx.fillText(txt, ox + x * sx + 4, ly - 4);
    const cm = isTarget && hazard.distanceCm != null ? hazard.distanceCm : (opts.live && t.rangeCm != null ? t.rangeCm : null);
    if (cm != null) {
      const d = cm < 100 ? `${cm.toFixed(0)} cm` : `${(cm / 100).toFixed(1)} m`;
      ctx.font = MONO_B; ctx.fillStyle = isTarget ? col : "rgba(255,255,255,0.85)";
      const by2 = Math.min(HB - 40, oy + (y + h) * sy - 6);   // and above the banner when it runs off the bottom
      ctx.fillText(opts.live && !isTarget ? `~${d}` : d, ox + x * sx + 4, by2);
    }
  }

  // LiDAR aim crosshair
  if (hazard) {
    const [ax, ay, aw, ah] = hazard.aimBox;
    const cx = ox + (ax + aw / 2) * sx, cy = oy + (ay + ah / 2) * sy, r = Math.max(8, aw * sx / 2);
    ctx.strokeStyle = lid && lid.valid ? "#ffffff" : "#8e8a83"; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx - r * 1.8, cy); ctx.lineTo(cx - r * 0.6, cy); ctx.moveTo(cx + r * 0.6, cy); ctx.lineTo(cx + r * 1.8, cy);
    ctx.moveTo(cx, cy - r * 1.8); ctx.lineTo(cx, cy - r * 0.6); ctx.moveTo(cx, cy + r * 0.6); ctx.lineTo(cx, cy + r * 1.8);
    ctx.stroke();
  }
  if (opts.quiet) { ctx.restore(); return; }

  // Distance bar on the right edge: 0 at the bottom, 300 cm at the top
  const bx = W - 26, by = 40, bh = HB - 110, maxCm = 300;
  ctx.fillStyle = "rgba(0,0,0,0.45)"; ctx.fillRect(bx - 6, by - 6, 30, bh + 12);
  ctx.strokeStyle = "#5e5a54"; ctx.lineWidth = 1; ctx.strokeRect(bx, by, 12, bh);
  const yFor = cm => by + bh - Math.min(1, cm / maxCm) * bh;
  ctx.fillStyle = "rgba(226,75,59,0.25)"; ctx.fillRect(bx, yFor(cfg.criticalCm), 12, by + bh - yFor(cfg.criticalCm));
  ctx.fillStyle = "rgba(240,168,48,0.2)"; ctx.fillRect(bx, yFor(cfg.warningCm), 12, yFor(cfg.criticalCm) - yFor(cfg.warningCm));
  ctx.font = "9px 'Atkinson Hyperlegible Mono', ui-monospace, Menlo, monospace"; ctx.fillStyle = "#cfcac2"; ctx.textAlign = "right";
  for (const cm of [cfg.criticalCm, cfg.warningCm, 200, 300]) { ctx.fillRect(bx - 4, yFor(cm), 4, 1); ctx.fillText(`${cm}`, bx - 6, yFor(cm) + 3); }
  ctx.textAlign = "left";
  if (lid && lid.valid && lid.distanceCm != null) {
    const y = yFor(lid.distanceCm);
    ctx.fillStyle = COLORS[hazard ? hazard.level : Level.CLEAR];
    ctx.beginPath(); ctx.moveTo(bx + 12, y); ctx.lineTo(bx + 20, y - 5); ctx.lineTo(bx + 20, y + 5); ctx.fill();
    ctx.fillRect(bx + 1, y, 10, by + bh - y);
  }

  // Top-left status: FPS, range source
  ctx.font = MONO; ctx.fillStyle = "rgba(0,0,0,0.5)"; ctx.fillRect(6, 6, 236, 34);
  ctx.fillStyle = "#e8e3da";
  ctx.fillText(`${opts.live ? "camera" : "IMX500"}  ${p.fps ? p.fps.toFixed(0) : "--"} fps   ${tracks.length} obj`, 12, 19);
  let ls = opts.live ? "range --" : "LiDAR --";
  if (lid) {
    if (lid.valid) ls = (opts.live ? `range ~${lid.distanceCm.toFixed(0)} cm (est.)` : `LiDAR ${lid.distanceCm.toFixed(0)} cm  str ${lid.strength}`) + (lid.ttcS != null && lid.ttcS < 5 ? `  TTC ${lid.ttcS.toFixed(1)}s` : "");
    else if (lid.stale) ls = opts.live ? "range stale" : "LiDAR stale";
    else ls = opts.live ? "range: nothing on the beam" : (lid.strength ? `LiDAR weak signal (str ${lid.strength})` : "LiDAR no return");
  }
  ctx.fillText(ls, 12, 33);

  // Haptic indicator (the device's L/R motors; in integration)
  if (opts.haptics !== false) {
    const on = hazard && hazard.level === Level.CRITICAL && Math.floor(now * 4) % 2 === 0;
    const side = hazard && hazard.target ? (hazard.target.center[0] < cfg.width / 2 ? "L" : "R") : null;
    ctx.font = "10px 'Atkinson Hyperlegible Mono', ui-monospace, Menlo, monospace";
    ctx.fillStyle = "rgba(0,0,0,0.5)"; ctx.fillRect(W - 112, 6, 76, 20);
    ctx.fillStyle = on && side === "L" ? RED : "#5e5a54"; ctx.beginPath(); ctx.arc(W - 100, 16, 5, 0, 7); ctx.fill();
    ctx.fillStyle = "#bdb6ac"; ctx.fillText("haptic", W - 90, 20);
    ctx.fillStyle = on && side === "R" ? RED : "#5e5a54"; ctx.beginPath(); ctx.arc(W - 46, 16, 5, 0, 7); ctx.fill();
  }

  // Banner
  if (hazard && hazard.level === Level.CRITICAL && hazard.message) {
    const flash = Math.floor(now * 3) % 2 === 0;
    let msg = `!! ${hazard.message.toUpperCase()}`;
    if (hazard.ttcS != null && hazard.ttcS < 5) msg += `  (TTC ${hazard.ttcS.toFixed(1)}s)`;
    ctx.fillStyle = flash ? "rgba(226,75,59,0.92)" : "rgba(120,24,16,0.92)";
    ctx.fillRect(0, HB - 66, W, 30);
    ctx.fillStyle = "#fff"; ctx.font = MONO_B;
    ctx.fillText(msg, 10, HB - 45);
  } else if (hazard && hazard.level === Level.CAUTION && hazard.message) {
    ctx.fillStyle = "rgba(240,168,48,0.88)"; ctx.fillRect(0, HB - 66, W, 30);
    ctx.fillStyle = "#120f0c"; ctx.font = "bold 14px 'Atkinson Hyperlegible Mono', ui-monospace, Menlo, monospace";
    ctx.fillText(hazard.message, 10, HB - 45);
  }

  // Spoken line
  ctx.fillStyle = "rgba(0,0,0,0.75)"; ctx.fillRect(0, HB - 32, W, 32);
  ctx.font = "13px 'Atkinson Hyperlegible Mono', ui-monospace, Menlo, monospace";
  if (speech) {
    const cur = speech.current;
    const text = cur ? cur.text : speech.lastSpoken;
    const prio = cur ? cur.priority : speech.lastPriority;
    const fresh = cur || (now - speech.lastSpokenAt < 4);
    ctx.fillStyle = fresh ? "#fff" : "#8e8a83";
    const tag = prio != null ? `[${priorityName(prio)}] ` : "";
    const line = `Spoken: ${speech.muted ? "(muted) " : ""}${tag}${text || "-"}`;
    ctx.fillText(line.length > 70 ? line.slice(0, 68) + "…" : line, 10, HB - 11);
    if (hazard) {
      ctx.fillStyle = "#8e8a83"; ctx.textAlign = "right";
      const src = opts.live ? (hazard.source === "none" ? "none" : hazard.source.replace("lidar", "est. range")) : hazard.source;
      ctx.fillText(`${src}  ${levelName(hazard.level)}`, W - 10, HB - 11);
      ctx.textAlign = "left";
    }
  }
  ctx.restore();
}
