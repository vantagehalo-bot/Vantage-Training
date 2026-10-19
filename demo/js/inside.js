// inside.js — the Halo V2 split-pack as a 3D twin. The visor shell and its two arms are
// the real printed part (the Fusion 360 export in assets/halo-visor.glb); the electronics
// inside it and the Compute Pack are drawn from primitives at their true sizes. One slider
// from assembled to apart, a label on every part when apart, and a card per part with the
// component photo. Status on each card is honest to the mid-October build.
import * as THREE from "../vendor/three/three.module.js";
import { OrbitControls } from "../vendor/three/OrbitControls.js";
import { GLTFLoader } from "../vendor/three/GLTFLoader.js";

const STATUS = { working: "Working", integration: "In integration", planned: "Planned" };

// Dimensions in metres, centred on the visor. +z is the wearer's front, +x their right.
// The printed shell is 130 mm wide and hollow: 20 mm from its face to the inner wall.
const PARTS = [
  // ---------------- Sensor Visor (printed shell: real geometry)
  { id: "shell", title: "Sensor Visor shell", status: "working", group: "visor", glb: "shell",
    line: "The front of the Halo, straight from the Fusion 360 file.",
    detail: "Printed in ASA. The hollow front holds the cameras, the laser and the ground-facing depth sensor behind their windows; the Vantage eye is raised 2 mm on the left cheek. This is the v4 headband, the one on the table.",
    spec: "130 × 78 × 45 mm front · FDM ASA · Fusion 360 v4",
    pos: [0, 0, 0], explode: [0, 0.03, 0.13] },
  { id: "armL", title: "Left arm", status: "working", group: "visor", glb: "armL",
    line: "Carries the left haptic motor and the headset's left pod.",
    detail: "Printed with the shell, joined at the temple. A TPU inner pad sits against the head.",
    spec: "FDM ASA · TPU pad", pos: [0, 0, 0], explode: [-0.09, 0.0, -0.02] },
  { id: "armR", title: "Right arm", status: "working", group: "visor", glb: "armR",
    line: "Carries the right haptic motor, the side depth sensor and the cable exit.",
    detail: "The Type-C cable to the Compute Pack leaves from the back of this arm.",
    spec: "FDM ASA · TPU pad", pos: [0, 0, 0], explode: [0.09, 0.0, -0.02] },
  // ---------------- electronics inside the shell
  { id: "imx500", title: "Raspberry Pi AI Camera · Sony IMX500", status: "working", group: "visor", img: "assets/parts/part-ai-camera.png",
    line: "Sees and recognises. The neural network runs on the sensor itself.",
    detail: "The processor never sees pixels. The sensor runs MobileNet-SSD on COCO's 80 classes and hands the Compute Module boxes, labels and scores at frame rate. A small tracker needs two frames before it trusts an object, which keeps the voice from stuttering. YOLO on the Hailo accelerator is the next step.",
    spec: "12.3 MP · 78° diagonal · on-sensor NPU · CSI CAM0",
    build: (m) => camModule(m), pos: [0, 0.006, 0.044], explode: [0, 0.03, 0.08] },
  { id: "mod3wide", title: "Camera Module 3 · wide", status: "integration", group: "visor", img: "assets/parts/part-ai-camera.png",
    line: "A wide, autofocus eye for reading and for the edges of the scene.",
    detail: "120° field of view and autofocus, which the AI camera lacks. It takes over for text at arm's length and watches the sides the narrow camera cannot.",
    spec: "12 MP · 120° · autofocus · CSI CAM1",
    build: (m) => camModule(m), pos: [-0.03, 0.006, 0.039], rotY: 0.25, explode: [-0.07, 0.03, 0.06] },
  { id: "noir", title: "Camera Module 3 · NoIR", status: "integration", group: "visor", img: "assets/parts/part-ai-camera.png",
    line: "Low light. Streets at night, unlit stairwells.",
    detail: "No infrared filter, so with a small IR illuminator it sees in the dark. The detector runs on its frames when the main camera's picture gets too dim.",
    spec: "12 MP · no IR-cut filter",
    build: (m) => camModule(m), pos: [0.03, 0.006, 0.039], rotY: -0.25, explode: [0.07, 0.03, 0.06] },
  { id: "tfmini", title: "Benewake TFmini Plus LiDAR", status: "working", group: "visor", img: "assets/parts/part-lidar.png",
    line: "Measures distance with a laser, 100 times a second.",
    detail: "A single beam, 3.6° wide, 10 cm to 12 m. The firmware checks every frame's checksum, drops weak returns (black cloth, glass) and saturated ones, median-filters the rest, and fits the closing speed to get a time-to-contact. The beam is projected into the camera image so the distance is attached to the right object.",
    spec: "0.1–12 m · 100 Hz · 3.6° · UART 115200",
    build: (m) => { const g = new THREE.Group(); g.add(box(0.035, 0.0185, 0.021, m.black)); const a = new THREE.Mesh(new THREE.CylinderGeometry(0.0055, 0.0055, 0.004, 16), m.lens); a.rotation.x = Math.PI / 2; a.position.set(-0.008, 0, 0.011); g.add(a); const b = a.clone(); b.position.x = 0.008; g.add(b); return g; },
    pos: [0, -0.018, 0.042], explode: [0, -0.05, 0.08] },
  { id: "tofF", title: "VL53L5CX ToF · F1 front", status: "integration", group: "visor", img: "assets/parts/part-tof.png",
    line: "Sixty-four depth zones, angled at the ground. Kerbs and steps.",
    detail: "A multi-zone time-of-flight sensor tilted toward the floor so it sees the drop of a kerb or the rise of a step before the foot gets there. The single-beam laser looks ahead; this one looks down.",
    spec: "8×8 zones · 63° · up to 4 m · I²C",
    build: (m) => { const g = new THREE.Mesh(new THREE.BoxGeometry(0.018, 0.012, 0.003), m.pcb); g.rotation.x = 0.5; return g; },
    pos: [0.02, -0.032, 0.04], explode: [0.04, -0.09, 0.07] },
  { id: "tofR", title: "VL53L5CX ToF · R1 right", status: "integration", group: "visor", img: "assets/parts/part-tof.png",
    line: "The right flank. Toward near-360° awareness.",
    detail: "A second multi-zone sensor on the right temple covers what the cameras cannot see. A left one mirrors it in the next revision.",
    spec: "8×8 zones · I²C",
    build: (m) => new THREE.Mesh(new THREE.BoxGeometry(0.003, 0.012, 0.018), m.pcb),
    pos: [0.092, 0.0, 0.01], explode: [0.17, -0.01, 0.03] },
  { id: "bone", title: "Bone-conduction headset · Shokz OpenMove", status: "working", group: "visor", img: "assets/parts/part-openmove.png",
    line: "Speech through the cheekbones. Ears stay open to the world.",
    detail: "Paired over Bluetooth to the Compute Pack. The firmware watches the audio sink, switches to the headset when it connects and reconnects it if it drops. Critical alerts lead with two rising tones so they are felt before the words arrive. The shell has a slot that holds it.",
    spec: "Bluetooth A2DP · 6 h · IP55",
    build: (m) => { const g = new THREE.Group(); const t = new THREE.Mesh(new THREE.TorusGeometry(0.088, 0.0035, 8, 48, Math.PI * 1.1), m.rubber); t.rotation.z = Math.PI * 1.45; t.rotation.x = Math.PI / 2; t.position.y = -0.05; g.add(t); for (const s of [-1, 1]) { const p = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.016, 0.02), m.rubber); p.position.set(s * 0.083, -0.056, 0.025); g.add(p); } return g; },
    pos: [0, 0, 0], explode: [0, -0.15, 0.02] },
  { id: "hapL", title: "Haptic motor · left", status: "integration", group: "visor",
    line: "A pulse on the side the hazard is on. Felt, not heard.",
    detail: "Coin vibration motors at each temple give a non-audio channel: left or right, soft or urgent. Early blindfolded trials showed voice alone is tiring; the haptic 'bat sonar' lowers the load. Pulses are timed by the auxiliary microcontroller in the pack.",
    spec: "10 mm ERM · PWM via XIAO",
    build: (m) => { const c = new THREE.Mesh(new THREE.CylinderGeometry(0.005, 0.005, 0.003, 16), m.metal); c.rotation.z = Math.PI / 2; return c; },
    pos: [-0.086, 0.008, -0.015], explode: [-0.17, 0.06, -0.02] },
  { id: "hapR", title: "Haptic motor · right", status: "integration", group: "visor",
    line: "Its twin on the right temple.",
    detail: "Same motor as the left. Together they encode direction without a word being spoken.",
    spec: "10 mm ERM",
    build: (m) => { const c = new THREE.Mesh(new THREE.CylinderGeometry(0.005, 0.005, 0.003, 16), m.metal); c.rotation.z = Math.PI / 2; return c; },
    pos: [0.086, 0.008, -0.015], explode: [0.17, 0.06, -0.02] },
  { id: "cable", title: "Type-C link", status: "working", group: "visor",
    line: "One cable from the head to the waist. That is the whole split.",
    detail: "Power up, camera and sensor data down. Keeping the compute, battery and radios at the waist is why the visor can stay under 100 g.",
    spec: "USB-C · 0.9 m",
    build: (m) => { const curve = new THREE.CatmullRomCurve3([new THREE.Vector3(0.1, -0.01, -0.05), new THREE.Vector3(0.12, -0.08, -0.07), new THREE.Vector3(0.09, -0.17, -0.03), new THREE.Vector3(0.05, -0.2, 0.0)]); return new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.0025, 8), m.rubber); },
    pos: [0, 0, 0], explode: [0.05, -0.03, -0.02] },
  // ---------------- Compute Pack (worn at the waist; drawn below the visor)
  { id: "pack", title: "Vantage Compute Pack", status: "working", group: "pack",
    line: "Everything heavy, on the belt.",
    detail: "A printed enclosure for the Compute Module, carrier, battery and radios. It takes the weight and the heat off the head, which is what the first testers asked for.",
    spec: "110 × 80 × 35 mm · printed PAHT-CF",
    build: (m) => new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.035, 0.08), m.shellDark),
    pos: [0, -0.27, 0], explode: [0, -0.42, 0] },
  { id: "cm5", title: "Raspberry Pi Compute Module 5", status: "working", group: "pack", img: "assets/parts/part-cm5.png",
    line: "Fuses camera and laser, decides what to say.",
    detail: "Runs vantage_core.py: the tracker, the beam-to-box fusion, the announcer with its priority queue, and the text reader. Chosen after the RB5 shortage and a system-on-module pivot that did not survive incomplete datasheets. 16 GB; 64 GB for the production unit.",
    spec: "BCM2712 · 4× A76 2.4 GHz · 16 GB · PCIe 2.0",
    build: (m) => { const g = new THREE.Group(); g.add(box(0.055, 0.0047, 0.04, m.pcbGreen)); const soc = box(0.012, 0.002, 0.012, m.black); soc.position.y = 0.0035; g.add(soc); return g; },
    pos: [-0.015, -0.255, 0.0], explode: [-0.02, -0.17, 0.0] },
  { id: "carrier", title: "Waveshare Nano base board", status: "working", group: "pack", img: "assets/parts/part-nano-base.png",
    line: "The carrier under the Compute Module.",
    detail: "Brings out the camera ports, the UART for the LiDAR, USB, and the PCIe slot for the AI accelerator. The custom PCB that replaces it is in fabrication at PCBWay.",
    spec: "CM5 carrier · 2× CSI · PCIe · UART",
    build: (m) => box(0.1, 0.0016, 0.07, m.pcbGreen),
    pos: [0, -0.262, 0], explode: [0, -0.26, 0] },
  { id: "hailo", title: "Hailo-8L AI accelerator", status: "planned", group: "pack",
    line: "Thirteen trillion operations a second for YOLO and depth.",
    detail: "Sits on the Compute Module's PCIe lane. Lets the heavier networks (YOLO detection, monocular depth, scene description) run on-device without the cloud.",
    spec: "M.2 2242 · 13 TOPS · PCIe",
    build: (m) => box(0.022, 0.0015, 0.042, m.pcb),
    pos: [0.03, -0.258, -0.01], explode: [0.08, -0.2, -0.03] },
  { id: "battery", title: "LiPo battery · 2S 7.4 V 6800 mAh", status: "working", group: "pack",
    line: "A day out on a charge.",
    detail: "50 Wh. Powers the Compute Module, the sensors on the visor over the Type-C link and the radios. Runtime under full load is being measured in the current integration pass.",
    spec: "2S 7.4 V · 6800 mAh · ~50 Wh",
    build: (m) => box(0.1, 0.018, 0.034, m.battery),
    pos: [0, -0.28, 0.02], explode: [0, -0.38, 0.1] },
  { id: "lora", title: "LoRa ESP32 radio", status: "planned", group: "pack",
    line: "Distress backup when there is no phone network.",
    detail: "The SOS button sends the wearer's position over the companion app first, and over long-range radio if the phone has no signal.",
    spec: "ESP32 · LoRa 868 MHz",
    build: (m) => { const g = new THREE.Group(); g.add(box(0.025, 0.002, 0.05, m.pcb)); const a = new THREE.Mesh(new THREE.CylinderGeometry(0.0015, 0.0015, 0.03, 8), m.metal); a.position.set(0, 0.015, -0.025); g.add(a); return g; },
    pos: [0.035, -0.278, -0.015], explode: [0.11, -0.31, -0.08] },
  { id: "xiao", title: "XIAO SAMD21", status: "planned", group: "pack",
    line: "A small helper for the fast, simple loops.",
    detail: "Times the haptic pulses and reads the buttons so the main processor stays on perception.",
    spec: "SAMD21 · 48 MHz",
    build: (m) => box(0.021, 0.002, 0.018, m.pcb),
    pos: [-0.04, -0.278, -0.02], explode: [-0.11, -0.31, -0.08] },
  { id: "sosbtn", title: "SOS button", status: "working", group: "pack",
    line: "One press. Location to a trusted contact.",
    detail: "Shares the wearer's position through the Vantage View companion app, where family can see it on a map. Falls back to the LoRa radio.",
    spec: "Tactile · debounced in firmware",
    build: (m) => new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.004, 16), m.red),
    pos: [0.045, -0.25, 0.03], explode: [0.12, -0.22, 0.08] },
];

function box(w, h, d, m) { return new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); }
function camModule(m) { const g = new THREE.Group(); g.add(box(0.025, 0.024, 0.009, m.pcb)); const l = new THREE.Mesh(new THREE.CylinderGeometry(0.0055, 0.0055, 0.008, 16), m.black); l.rotation.x = Math.PI / 2; l.position.z = 0.008; g.add(l); return g; }

export function initInside(el) {
  const { canvas, video, slider, card, xray, reset, hint, labels, list, poster, posterBtn } = el;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(36, 1, 0.01, 10); const HOME = new THREE.Vector3(0.34, 0.14, 0.5);
  camera.position.copy(HOME);
  const controls = new OrbitControls(camera, canvas); controls.enableDamping = true; controls.target.set(0, -0.09, 0); controls.minDistance = 0.12; controls.maxDistance = 1.4;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x3a3630, 1.1));
  const key = new THREE.DirectionalLight(0xffffff, 1.5); key.position.set(0.5, 0.8, 0.6); scene.add(key);
  const rim = new THREE.DirectionalLight(0x9fd0e8, 0.7); rim.position.set(-0.6, 0.2, -0.5); scene.add(rim);
  const fill = new THREE.DirectionalLight(0xffe0c0, 0.4); fill.position.set(0.2, -0.5, 0.8); scene.add(fill);

  const M = {
    shell: new THREE.MeshPhysicalMaterial({ color: 0x202024, roughness: 0.48, metalness: 0.1, clearcoat: 0.5, clearcoatRoughness: 0.4 }),
    shellDark: new THREE.MeshStandardMaterial({ color: 0x2a2a30, roughness: 0.6 }),
    pcb: new THREE.MeshStandardMaterial({ color: 0x1d5a3a, roughness: 0.6 }),
    pcbGreen: new THREE.MeshStandardMaterial({ color: 0x1f6b3f, roughness: 0.55 }),
    black: new THREE.MeshStandardMaterial({ color: 0x111114, roughness: 0.4 }),
    lens: new THREE.MeshPhysicalMaterial({ color: 0x2b3f6b, roughness: 0.1, metalness: 0.3, clearcoat: 1 }),
    metal: new THREE.MeshStandardMaterial({ color: 0x9a9fa6, roughness: 0.35, metalness: 0.7 }),
    rubber: new THREE.MeshStandardMaterial({ color: 0x1a1a1d, roughness: 0.9 }),
    battery: new THREE.MeshStandardMaterial({ color: 0x3b6fb6, roughness: 0.5 }),
    red: new THREE.MeshStandardMaterial({ color: 0xeb2828, roughness: 0.4, emissive: 0x3a0a0a }),
  };
  const root = new THREE.Group(); scene.add(root);
  const parts = PARTS.map(p => {
    const mesh = p.build ? p.build(M) : new THREE.Group();
    if (p.rotY) mesh.rotation.y = p.rotY;
    mesh.traverse(o => { o.userData.part = p; });
    mesh.position.set(...p.pos); root.add(mesh);
    const label = document.createElement("div"); label.className = "twin-label"; label.textContent = p.title.split(" · ")[0]; label.dataset.status = p.status;
    label.addEventListener("click", () => select(parts.find(q => q.def === p)));
    labels.appendChild(label);
    return { def: p, mesh, home: new THREE.Vector3(...p.pos), out: new THREE.Vector3(...p.explode), label };
  });
  // the printed visor, from the Fusion 360 export
  new GLTFLoader().load("assets/halo-visor.glb", (gltf) => {
    for (const p of parts) {
      if (!p.def.glb) continue;
      const node = gltf.scene.getObjectByName(p.def.glb); if (!node) continue;
      node.traverse(o => { if (o.isMesh) { o.material = M.shell; o.userData.part = p.def; } });
      p.mesh.add(node);
    }
    hint.textContent = "Drag to orbit. Pinch to zoom. Tap a part.";
  }, undefined, () => { hint.textContent = "Visor model did not load; showing the components."; });

  let explode = 0, selected = null, raf = 0, running = false;
  const ray = new THREE.Raycaster(), ptr = new THREE.Vector2(), tmp = new THREE.Vector3(), bb = new THREE.Box3();

  // list of every distinct part, grouped
  for (const group of ["visor", "pack"]) {
    const h = document.createElement("li"); h.className = "twin-list-head"; h.textContent = group === "visor" ? "Sensor Visor" : "Compute Pack"; list.appendChild(h);
    for (const p of parts.filter(p => p.def.group === group)) {
      const li = document.createElement("li"); li.innerHTML = `<span class="dot ${p.def.status}"></span>${p.def.title}`;
      li.addEventListener("click", () => { select(p); if (explode < 0.4) { slider.value = 700; slider.dispatchEvent(new Event("input", { bubbles: true })); } });
      p.li = li; list.appendChild(li);
    }
  }

  function layout() { for (const p of parts) p.mesh.position.lerpVectors(p.home, p.out, explode); }
  function select(part) {
    selected = part;
    for (const p of parts) {
      p.mesh.traverse(o => { if (o.isMesh) { if (!o.userData.orig) { o.userData.orig = o.material; o.userData.wire = new THREE.MeshBasicMaterial({ color: 0x55555f, wireframe: true, transparent: true, opacity: 0.3 }); } o.material = part && p !== part ? o.userData.wire : o.userData.orig; } });
      if (p.li) p.li.classList.toggle("on", p === part); p.label.classList.toggle("on", p === part);
    }
    if (part) {
      const d = part.def;
      card.title.textContent = d.title; card.status.textContent = STATUS[d.status]; card.status.className = `badge ${d.status}`;
      card.line.textContent = d.line; card.detail.textContent = d.detail; card.spec.textContent = d.spec;
      if (d.img) { card.img.src = d.img; card.img.hidden = false; } else card.img.hidden = true;
      card.root.hidden = false; hint.hidden = true;
    } else { card.root.hidden = true; hint.hidden = false; }
  }
  let downAt = null;
  canvas.addEventListener("pointerdown", e => { downAt = [e.clientX, e.clientY, performance.now()]; });
  canvas.addEventListener("pointerup", e => {
    if (!downAt) return; const moved = Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 8 || performance.now() - downAt[2] > 400; downAt = null; if (moved) return;
    const r = canvas.getBoundingClientRect(); ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ptr, camera); const hits = ray.intersectObjects(root.children, true);
    const hit = hits.find(h => h.object.userData.part);
    select(hit ? parts.find(p => p.def === hit.object.userData.part) : null);
  });
  card.close.addEventListener("click", () => select(null));
  let lastExplode = 0;
  slider.addEventListener("input", e => {
    explode = +e.target.value / 1000; layout();
    const dir = camera.position.clone().sub(controls.target); const d = dir.length();
    const base = d / (1 + 0.7 * lastExplode); dir.setLength(base * (1 + 0.7 * explode)); camera.position.copy(controls.target).add(dir);
    lastExplode = explode;
  });
  reset.addEventListener("click", () => { camera.position.copy(HOME); controls.target.set(0, -0.09, 0); slider.value = 0; explode = 0; lastExplode = 0; layout(); select(null); });
  posterBtn.addEventListener("click", () => { poster.hidden = !poster.hidden; posterBtn.classList.toggle("on", !poster.hidden); posterBtn.setAttribute("aria-pressed", !poster.hidden); });
  poster.addEventListener("click", () => { poster.hidden = true; posterBtn.classList.remove("on"); posterBtn.setAttribute("aria-pressed", "false"); });

  // "Hold over the model": the tablet camera behind the twin, so the parts can be lined up on the real Halo
  let stream = null;
  xray.addEventListener("click", async () => {
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; video.hidden = true; xray.classList.remove("on"); xray.setAttribute("aria-pressed", "false"); return; }
    try { stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false }); video.srcObject = stream; await video.play(); video.hidden = false; xray.classList.add("on"); xray.setAttribute("aria-pressed", "true"); }
    catch (_) { hint.hidden = false; hint.textContent = "Camera not available here; the twin works without it."; }
  });

  function placeLabels() {
    const w = canvas.clientWidth, h = canvas.clientHeight; const show = explode > 0.35;
    labels.classList.toggle("show", show);
    if (!show) return;
    const placed = [];
    for (const p of parts) {
      bb.setFromObject(p.mesh); if (bb.isEmpty()) { p.label.style.display = "none"; continue; }
      bb.getCenter(tmp); tmp.y = bb.max.y; tmp.project(camera);
      const x = (tmp.x + 1) / 2 * w; let y = (1 - tmp.y) / 2 * h - 10;
      const vis = tmp.z < 1 && x > 0 && x < w && y > 112 && y < h - 60;
      p.label.style.display = vis ? "block" : "none";
      if (!vis) continue;
      // nudge a label down when it would sit on one already placed
      for (let k = 0; k < 6; k++) { const hit = placed.find(q => Math.abs(q.x - x) < 150 && Math.abs(q.y - y) < 20); if (!hit) break; y = hit.y + 20; }
      placed.push({ x, y });
      p.label.style.transform = `translate(${x.toFixed(0)}px, ${y.toFixed(0)}px)`;
      p.label.style.opacity = Math.min(1, (explode - 0.35) / 0.3);
    }
  }
  function resize() { const w = canvas.clientWidth, h = canvas.clientHeight; if (!w || !h) return; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }
  function loop() { if (!running) return; raf = requestAnimationFrame(loop); controls.update(); if (!selected && explode < 0.05) root.rotation.y += 0.0012; renderer.render(scene, camera); placeLabels(); }
  layout();
  return {
    start() { running = true; resize(); window.addEventListener("resize", resize); loop(); },
    stop() { running = false; cancelAnimationFrame(raf); window.removeEventListener("resize", resize); if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; video.hidden = true; xray.classList.remove("on"); } },
    parts: PARTS,
  };
}
