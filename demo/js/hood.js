// hood.js — "Under the hood": the live pipeline, the speech queue with its pre-emptions
// and drops, the terminal dashboard the device shows over SSH, and log lines in the
// exact format vantage_core.py writes to vantage.log (SAY[PRIORITY]: text).
import { levelName, priorityName, spokenLabel } from "./halo.js";

export function initHood(el) {
  const { pipelineRoot, queueList, queueEvents, dash, logLines } = el;
  const stage = (name) => pipelineRoot.querySelector(`[data-stage="${name}"]`);
  const st = { running: false, events: [], log: [], scene: null, lastDash: 0, queue: [] };
  const $em = (name) => stage(name).querySelector("em");

  function pulse(name, crit = false) {
    const s = stage(name); s.classList.add("pulse"); s.classList.toggle("crit", crit);
    clearTimeout(s._t); s._t = setTimeout(() => { s.classList.remove("pulse"); s.classList.remove("crit"); }, 220);
  }
  function pushEvent(text, cls = "") {
    st.events.unshift({ text, cls }); st.events.length = Math.min(st.events.length, 14);
    if (st.running) renderEvents();
  }
  function addLog(line) {
    const t = new Date(); const ts = t.toTimeString().slice(0, 8) + "." + String(t.getMilliseconds()).padStart(3, "0");
    st.log.unshift(`${ts} ${line}`); st.log.length = Math.min(st.log.length, 40);
    if (st.running) logLines.textContent = st.log.join("\n");
  }
  function renderEvents() { queueEvents.innerHTML = st.events.map(e => `<li class="${e.cls}">${esc(e.text)}</li>`).join(""); }
  function renderQueue(q) {
    st.queue = q;
    queueList.innerHTML = q.length ? q.map(u => `<li class="p${u.priority}">[${priorityName(u.priority)}] ${esc(u.text)} <span class="dim">· max age ${u.maxAgeS.toFixed(1)}s</span></li>`).join("") : '<li class="dim">empty</li>';
  }

  return {
    start() { st.running = true; renderEvents(); renderQueue(st.queue); logLines.textContent = st.log.join("\n"); },
    stop() { st.running = false; },
    setScene(def) { st.scene = def; addLog(`INFO Scene loaded: ${def.title}`); },
    onSpeechEvent(ev) {
      if (!ev.utt && !ev.killed) return;
      switch (ev.type) {
        case "queued": pulse("queue", ev.utt.priority === 0); renderQueue(ev.queue); pushEvent(`queued  [${priorityName(ev.utt.priority)}] ${ev.utt.text}`, `p${ev.utt.priority}`); break;
        case "preempt": pushEvent(`PRE-EMPT [${priorityName(ev.by.priority)}] cut off "${ev.killed.text}"`, "p0"); addLog(`WARNING pre-empted: ${ev.killed.text}`); break;
        case "drained": pushEvent(`drained [${priorityName(ev.utt.priority)}] ${ev.utt.text}`, "drop"); break;
        case "dropped": pushEvent(`DROPPED stale [${priorityName(ev.utt.priority)}] ${ev.utt.text}`, "drop"); addLog(`INFO dropped stale: ${ev.utt.text}`); break;
        case "speaking": pulse("headset", ev.utt.priority === 0); renderQueue(ev.queue || []); $em("headset").textContent = ev.utt.text; addLog(`INFO SAY[${priorityName(ev.utt.priority)}]: ${ev.utt.text}`); break;
        case "spoken": break;
      }
    },
    onPipelineEvent(ev) { if (ev.type === "alert") { pulse("announcer", true); addLog(`WARNING ALERT ${ev.message}`); } },
    setDashboard(d) {
      const now = performance.now() / 1000; if (now - st.lastDash < 0.2 || !st.running) return; st.lastDash = now;
      const { fps, lidar, raw, tracks, hazard, speech, cfg, pose } = d;
      $em("camera").textContent = `${fps.toFixed(0)} fps · ${tracks.length} boxes`;
      $em("tracker").textContent = tracks.map(t => `${spokenLabel(t.label)}#${t.trackId}`).slice(0, 3).join(" ") || "—";
      $em("fusion").textContent = hazard ? `${hazard.source} → ${levelName(hazard.level)}` : "—";
      $em("announcer").textContent = hazard && hazard.message ? hazard.message : "—";
      $em("queue").textContent = `${st.queue.length} waiting${speech.current ? " · speaking" : ""}`;
      $em("lidar").textContent = lidar && lidar.valid ? `${lidar.distanceCm.toFixed(0)} cm · str ${lidar.strength}${lidar.ttcS != null && lidar.ttcS < 5 ? ` · TTC ${lidar.ttcS.toFixed(1)}s` : ""}` : raw && raw.strength ? `weak signal (str ${raw.strength})` : "no return";
      pulse("camera"); pulse("tracker"); pulse("fusion", hazard && hazard.level === 2); pulse("lidar");
      const vel = lidar && lidar.velocity != null ? `${lidar.velocity >= 0 ? "+" : ""}${lidar.velocity.toFixed(0)} cm/s` : "   -- cm/s";
      const ttc = lidar && lidar.ttcS != null ? `TTC ${lidar.ttcS.toFixed(1)}s` : "TTC   --";
      const lines = [
        `Vantage core (tablet twin)   fps ${fps.toFixed(1).padStart(5)}   audio sink: ${speech.muted ? "MUTED" : "bluez_output (Shokz)"}`,
        `LiDAR  ${lidar && lidar.valid ? String(lidar.distanceCm.toFixed(0)).padStart(4) + " cm" : "  -- cm"}  str ${String(lidar ? lidar.strength ?? 0 : 0).padStart(5)}  ${vel}  ${ttc}  ${raw && raw.material ? "(" + raw.material + ")" : ""}`,
        `Hazard ${hazard ? levelName(hazard.level).padEnd(8) : "--"} ${hazard && hazard.target ? spokenLabel(hazard.target.label) : "-"}  src ${hazard ? hazard.source : "-"}`,
        `Pose   x ${pose.x.toFixed(2)}  z ${pose.z.toFixed(2)}  yaw ${(pose.yaw * 180 / Math.PI).toFixed(0)}°`,
        `Objects:`, ...tracks.slice(0, 6).map(t => `  #${String(t.trackId).padStart(3)} ${t.label.padEnd(14)} ${t.score.toFixed(2)}  hits ${String(t.hits).padStart(3)}  box ${t.box.map(v => v.toFixed(0)).join(",")}`),
        `Thresholds: critical ${cfg.criticalCm} cm  warning ${cfg.warningCm} cm  hysteresis ${cfg.hysteresisCm} cm  repeat ${cfg.criticalRepeatS}s  describe ${cfg.describe ? "on" : "off"}`,
      ];
      dash.textContent = lines.join("\n");
    },
  };
}
const esc = s => String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
