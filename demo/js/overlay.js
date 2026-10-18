// overlay.js — draws the Halo preview exactly as the device does: a coloured box per
// tracked object with label and confidence, the target in red with its distance, the
// LiDAR aim crosshair, the distance bar with 50/100 cm ticks, the flashing banner and
// the "Spoken:" line. Frame space is the firmware's 640x480.
import { Level, levelName, priorityName, spokenLabel } from "./halo.js";

export const COLORS = {
  [Level.CRITICAL]: "#eb2828", [Level.CAUTION]: "#ffbe00",
  [Level.CLEAR]: "#5ad25a", [Level.UNKNOWN]: "#a0a0a0",
};
const RED = "#eb2828", MONO = "11px ui-monospace, SFMono-Regular, Menlo, monospace";

export function drawOverlay(ctx, W, H, p, opts = {}) {
  const { tracks = [], hazard, lidarSample: lid, speech, cfg } = p;
  const now = performance.now() / 1000;
  const sx = W / cfg.width, sy = H / cfg.height;
  ctx.save();
  ctx.lineWidth = 2;

  // Tracks
  for (const t of tracks) {
    const [x, y, w, h] = t.box;
    const isTarget = hazard && hazard.target === t;
    const col = isTarget ? COLORS[Math.max(hazard.level, Level.CAUTION)] : "#8fd3ff";
    ctx.strokeStyle = col; ctx.lineWidth = isTarget ? 3 : 1.5;
    ctx.strokeRect(x * sx, y * sy, w * sx, h * sy);
    const txt = `${spokenLabel(t.label)} ${t.score.toFixed(2)}`;
    ctx.font = MONO; const tw = ctx.measureText(txt).width + 8;
    ctx.fillStyle = col; ctx.fillRect(x * sx, y * sy - 15, tw, 15);
    ctx.fillStyle = "#000"; ctx.fillText(txt, x * sx + 4, y * sy - 4);
    if (isTarget && hazard.distanceCm != null) {
      const d = `${hazard.distanceCm.toFixed(0)} cm`;
      ctx.font = "bold 16px ui-monospace, Menlo, monospace";
      ctx.fillStyle = col; ctx.fillText(d, x * sx + 4, (y + h) * sy - 6);
    }
  }

  // LiDAR aim crosshair
  if (hazard) {
    const [ax, ay, aw, ah] = hazard.aimBox;
    const cx = (ax + aw / 2) * sx, cy = (ay + ah / 2) * sy, r = Math.max(8, aw * sx / 2);
    ctx.strokeStyle = lid && lid.valid ? "#ffffff" : "#808080"; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx - r * 1.8, cy); ctx.lineTo(cx - r * 0.6, cy); ctx.moveTo(cx + r * 0.6, cy); ctx.lineTo(cx + r * 1.8, cy);
    ctx.moveTo(cx, cy - r * 1.8); ctx.lineTo(cx, cy - r * 0.6); ctx.moveTo(cx, cy + r * 0.6); ctx.lineTo(cx, cy + r * 1.8);
    ctx.stroke();
  }

  // Distance bar on the right edge: 0 at the bottom, 300 cm at the top
  const bx = W - 26, by = 40, bh = H - 110, maxCm = 300;
  ctx.fillStyle = "rgba(0,0,0,0.45)"; ctx.fillRect(bx - 6, by - 6, 30, bh + 12);
  ctx.strokeStyle = "#666"; ctx.lineWidth = 1; ctx.strokeRect(bx, by, 12, bh);
  const yFor = cm => by + bh - Math.min(1, cm / maxCm) * bh;
  ctx.fillStyle = "rgba(235,40,40,0.25)"; ctx.fillRect(bx, yFor(cfg.criticalCm), 12, by + bh - yFor(cfg.criticalCm));
  ctx.fillStyle = "rgba(255,190,0,0.2)"; ctx.fillRect(bx, yFor(cfg.warningCm), 12, yFor(cfg.criticalCm) - yFor(cfg.warningCm));
  ctx.font = "9px ui-monospace, Menlo, monospace"; ctx.fillStyle = "#ccc"; ctx.textAlign = "right";
  for (const cm of [cfg.criticalCm, cfg.warningCm, 200, 300]) {
    ctx.fillRect(bx - 4, yFor(cm), 4, 1); ctx.fillText(`${cm}`, bx - 6, yFor(cm) + 3);
  }
  ctx.textAlign = "left";
  if (lid && lid.valid && lid.distanceCm != null) {
    const y = yFor(lid.distanceCm);
    ctx.fillStyle = COLORS[hazard ? hazard.level : Level.CLEAR];
    ctx.beginPath(); ctx.moveTo(bx + 12, y); ctx.lineTo(bx + 20, y - 5); ctx.lineTo(bx + 20, y + 5); ctx.fill();
    ctx.fillRect(bx + 1, y, 10, by + bh - y);
  }

  // Top-left status: FPS, LiDAR
  ctx.font = MONO; ctx.fillStyle = "rgba(0,0,0,0.5)"; ctx.fillRect(6, 6, 230, 34);
  ctx.fillStyle = "#ddd";
  ctx.fillText(`IMX500  ${p.fps ? p.fps.toFixed(0) : "--"} fps   ${tracks.length} obj`, 12, 19);
  let ls = "LiDAR --";
  if (lid) {
    if (lid.valid) ls = `LiDAR ${lid.distanceCm.toFixed(0)} cm  str ${lid.strength}` + (lid.ttcS != null && lid.ttcS < 5 ? `  TTC ${lid.ttcS.toFixed(1)}s` : "");
    else if (lid.stale) ls = "LiDAR stale";
    else ls = lid.strength ? `LiDAR weak signal (str ${lid.strength})` : "LiDAR no return";
  }
  ctx.fillText(ls, 12, 33);

  // Haptic indicator (the device's L/R motors; marked as in integration)
  if (opts.haptics !== false) {
    const on = hazard && hazard.level === Level.CRITICAL && Math.floor(now * 4) % 2 === 0;
    const side = hazard && hazard.target ? (hazard.target.center[0] < cfg.width / 2 ? "L" : "R") : null;
    ctx.font = "10px ui-monospace, Menlo, monospace";
    ctx.fillStyle = "rgba(0,0,0,0.5)"; ctx.fillRect(W - 112, 6, 76, 20);
    ctx.fillStyle = on && side === "L" ? RED : "#555"; ctx.beginPath(); ctx.arc(W - 100, 16, 5, 0, 7); ctx.fill();
    ctx.fillStyle = "#aaa"; ctx.fillText("haptic", W - 90, 20);
    ctx.fillStyle = on && side === "R" ? RED : "#555"; ctx.beginPath(); ctx.arc(W - 46, 16, 5, 0, 7); ctx.fill();
  }

  // Banner
  if (hazard && hazard.level === Level.CRITICAL && hazard.message) {
    const flash = Math.floor(now * 3) % 2 === 0;
    let msg = `!! ${hazard.message.toUpperCase()}`;
    if (hazard.ttcS != null && hazard.ttcS < 5) msg += `  (TTC ${hazard.ttcS.toFixed(1)}s)`;
    ctx.fillStyle = flash ? "rgba(235,40,40,0.92)" : "rgba(120,10,10,0.92)";
    ctx.fillRect(0, H - 66, W, 30);
    ctx.fillStyle = "#fff"; ctx.font = "bold 15px ui-monospace, Menlo, monospace";
    ctx.fillText(msg, 10, H - 45);
  } else if (hazard && hazard.level === Level.CAUTION && hazard.message) {
    ctx.fillStyle = "rgba(255,190,0,0.85)"; ctx.fillRect(0, H - 66, W, 30);
    ctx.fillStyle = "#000"; ctx.font = "bold 14px ui-monospace, Menlo, monospace";
    ctx.fillText(hazard.message, 10, H - 45);
  }

  // Spoken line
  ctx.fillStyle = "rgba(0,0,0,0.75)"; ctx.fillRect(0, H - 32, W, 32);
  ctx.font = "13px ui-monospace, Menlo, monospace";
  if (speech) {
    const cur = speech.current;
    const text = cur ? cur.text : speech.lastSpoken;
    const prio = cur ? cur.priority : speech.lastPriority;
    const fresh = cur || (now - speech.lastSpokenAt < 4);
    ctx.fillStyle = fresh ? "#fff" : "#777";
    const tag = prio != null ? `[${priorityName(prio)}] ` : "";
    ctx.fillText(`Spoken: ${speech.muted ? "(muted) " : ""}${tag}${text || "-"}`, 10, H - 11);
    if (hazard) {
      ctx.fillStyle = "#777"; ctx.textAlign = "right";
      ctx.fillText(`fusion: ${hazard.source}  ${levelName(hazard.level)}`, W - 10, H - 11);
      ctx.textAlign = "left";
    }
  }
  ctx.restore();
}
