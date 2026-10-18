// inside.js — the Halo V2 split-pack as a 3D twin built from primitives: the Sensor
// Visor and the Compute Pack, one slider from assembled to apart, a card per part.
// Status on each card is honest to the mid-October build: working / in integration / planned.
import * as THREE from "../vendor/three/three.module.js";
import { OrbitControls } from "../vendor/three/OrbitControls.js";

const STATUS = { working: "Working", integration: "In integration", planned: "Planned" };

// Dimensions in metres. The visor is a band around a ~190 mm head; the pack is 110x80x35 mm.
const PARTS = [
  // ---------------- Sensor Visor
  { id: "band", title: "Sensor Visor band", status: "working", group: "visor",
    line: "The headband. Under 100 grams with everything on it.",
    detail: "Printed in ASA with a TPU inner for comfort. The all-in-one V01 headset was too heavy; splitting compute off to the waist is what made the head light. The front is covered with a 1 mm black acrylic sheet with a slot that holds the headset.",
    spec: "Fusion 360 v4 · FDM ASA/TPU · 1 mm acrylic face",
    build: (m) => { const t = new THREE.Mesh(new THREE.TorusGeometry(0.098, 0.011, 12, 48, Math.PI * 1.55), m.shell); t.rotation.z = Math.PI * 1.725; t.rotation.x = Math.PI / 2; return t; },
    pos: [0, 0, 0], explode: [0, 0.04, 0] },
  { id: "face", title: "Acrylic face plate", status: "working", group: "visor",
    line: "The black front. It hides the sensors and holds the headset.",
    detail: "Laser-cut 1 mm black acrylic, bent to the band. The cameras and the laser look through cut-outs; the bone-conduction headset slides through a slot underneath.",
    spec: "1 mm black acrylic · laser cut",
    build: (m) => { const g = new THREE.Mesh(new THREE.CylinderGeometry(0.1035, 0.1035, 0.03, 48, 1, true, -Math.PI * 0.32, Math.PI * 0.64), m.acrylic); return g; },
    pos: [0, 0, 0], explode: [0, 0, 0.07] },
  { id: "imx500", title: "Raspberry Pi AI Camera · Sony IMX500", status: "working", group: "visor",
    line: "Sees and recognises. The neural network runs on the sensor itself.",
    detail: "The processor never sees pixels. The sensor runs MobileNet-SSD on COCO's 80 classes and hands the Compute Module boxes, labels and scores at frame rate. A small tracker needs two frames before it trusts an object, which keeps the voice from stuttering. YOLO on the Hailo accelerator is the next step.",
    spec: "12.3 MP · 78° diagonal · on-sensor NPU · CSI CAM0",
    build: (m) => { const g = new THREE.Group(); g.add(box(0.025, 0.024, 0.009, m.pcb)); const l = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.008, 16), m.black); l.rotation.x = Math.PI / 2; l.position.z = 0.008; g.add(l); return g; },
    pos: [0, 0.004, 0.1], explode: [0, 0.015, 0.13] },
  { id: "mod3wide", title: "Camera Module 3 · wide", status: "integration", group: "visor",
    line: "A wide, autofocus eye for reading and for the edges of the scene.",
    detail: "120° field of view and autofocus, which the AI camera lacks. It takes over for text at arm's length and watches the sides the narrow camera cannot.",
    spec: "12 MP · 120° · autofocus · CSI CAM1",
    build: (m) => { const g = new THREE.Group(); g.add(box(0.025, 0.024, 0.009, m.pcb)); const l = new THREE.Mesh(new THREE.CylinderGeometry(0.0045, 0.0045, 0.007, 16), m.black); l.rotation.x = Math.PI / 2; l.position.z = 0.007; g.add(l); return g; },
    pos: [-0.036, 0.004, 0.094], explode: [-0.08, 0.015, 0.11] },
  { id: "noir", title: "Camera Module 3 · NoIR", status: "integration", group: "visor",
    line: "Low light. Streets at night, unlit stairwells.",
    detail: "No infrared filter, so with a small IR illuminator it sees in the dark. The detector runs on its frames when the main camera's picture gets too dim.",
    spec: "12 MP · no IR-cut filter",
    build: (m) => { const g = new THREE.Group(); g.add(box(0.025, 0.024, 0.009, m.pcb)); const l = new THREE.Mesh(new THREE.CylinderGeometry(0.0045, 0.0045, 0.007, 16), m.black); l.rotation.x = Math.PI / 2; l.position.z = 0.007; g.add(l); return g; },
    pos: [0.036, 0.004, 0.094], explode: [0.08, 0.015, 0.11] },
  { id: "tfmini", title: "Benewake TFmini Plus LiDAR", status: "working", group: "visor",
    line: "Measures distance with a laser, 100 times a second.",
    detail: "A single beam, 3.6° wide, 10 cm to 12 m. The firmware checks every frame's checksum, drops weak returns (black cloth, glass) and saturated ones, median-filters the rest, and fits the closing speed to get a time-to-contact. The beam is projected into the camera image so the distance is attached to the right object.",
    spec: "0.1–12 m · 100 Hz · 3.6° · UART 115200",
    build: (m) => { const g = new THREE.Group(); g.add(box(0.035, 0.0185, 0.021, m.black)); const a = new THREE.Mesh(new THREE.CylinderGeometry(0.0055, 0.0055, 0.004, 16), m.lens); a.rotation.x = Math.PI / 2; a.position.set(-0.008, 0, 0.011); g.add(a); const b = a.clone(); b.position.x = 0.008; g.add(b); return g; },
    pos: [0, -0.02, 0.097], explode: [0, -0.07, 0.12] },
  { id: "tofF", title: "VL53L5CX ToF · F1 front", status: "integration", group: "visor",
    line: "Sixty-four depth zones, angled at the ground. Kerbs and steps.",
    detail: "A multi-zone time-of-flight sensor tilted toward the floor so it sees the drop of a kerb or the rise of a step before the foot gets there. The single-beam laser looks ahead; this one looks down.",
    spec: "8×8 zones · 63° · up to 4 m · I²C",
    build: (m) => { const g = new THREE.Mesh(new THREE.BoxGeometry(0.014, 0.01, 0.003), m.pcb); g.rotation.x = 0.5; return g; },
    pos: [0.018, -0.028, 0.093], explode: [0.03, -0.1, 0.1] },
  { id: "tofR", title: "VL53L5CX ToF · R1 right", status: "integration", group: "visor",
    line: "The right flank. Toward near-360° awareness.",
    detail: "A second multi-zone sensor on the right temple covers what the cameras cannot see. A left one mirrors it in the next revision.",
    spec: "8×8 zones · I²C",
    build: (m) => { const g = new THREE.Mesh(new THREE.BoxGeometry(0.003, 0.01, 0.014), m.pcb); return g; },
    pos: [0.1, -0.005, 0.02], explode: [0.17, -0.02, 0.02] },
  { id: "boneL", title: "Bone-conduction headset · Shokz OpenMove", status: "working", group: "visor",
    line: "Speech through the cheekbones. Ears stay open to the world.",
    detail: "Paired over Bluetooth to the Compute Pack. The firmware watches the audio sink, switches to the headset when it connects and reconnects it if it drops. Critical alerts lead with two rising tones so they are felt before the words arrive.",
    spec: "Bluetooth A2DP · 6 h · IP55",
    build: (m) => { const g = new THREE.Group(); const t = new THREE.Mesh(new THREE.TorusGeometry(0.1, 0.004, 8, 48, Math.PI * 1.1), m.rubber); t.rotation.z = Math.PI * 1.45; t.rotation.x = Math.PI / 2; t.position.y = -0.02; g.add(t); for (const s of [-1, 1]) { const p = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.016, 0.02), m.rubber); p.position.set(s * 0.086, -0.03, 0.05); g.add(p); } return g; },
    pos: [0, 0, 0], explode: [0, -0.16, 0] },
  { id: "hapL", title: "Haptic motor · left", status: "integration", group: "visor",
    line: "A pulse on the side the hazard is on. Felt, not heard.",
    detail: "Coin vibration motors at each temple give a non-audio channel: left or right, soft or urgent. Early blindfolded trials showed voice alone is tiring; the haptic 'bat sonar' lowers the load. Pulses are timed by the auxiliary microcontroller in the pack.",
    spec: "10 mm ERM · PWM via XIAO",
    build: (m) => { const c = new THREE.Mesh(new THREE.CylinderGeometry(0.005, 0.005, 0.003, 16), m.metal); c.rotation.z = Math.PI / 2; return c; },
    pos: [-0.1, 0.01, 0.0], explode: [-0.17, 0.05, 0] },
  { id: "hapR", title: "Haptic motor · right", status: "integration", group: "visor",
    line: "Its twin on the right temple.",
    detail: "Same motor as the left. Together they encode direction without a word being spoken.",
    spec: "10 mm ERM",
    build: (m) => { const c = new THREE.Mesh(new THREE.CylinderGeometry(0.005, 0.005, 0.003, 16), m.metal); c.rotation.z = Math.PI / 2; return c; },
    pos: [0.1, 0.01, 0.0], explode: [0.17, 0.05, 0] },
  { id: "cable", title: "Type-C link", status: "working", group: "visor",
    line: "One cable from the head to the waist. That is the whole split.",
    detail: "Power up, camera and sensor data down. Keeping the compute, battery and radios at the waist is why the visor can stay under 100 g.",
    spec: "USB-C · 0.9 m",
    build: (m) => { const curve = new THREE.CatmullRomCurve3([new THREE.Vector3(0.09, -0.02, -0.02), new THREE.Vector3(0.12, -0.08, -0.05), new THREE.Vector3(0.1, -0.16, -0.02), new THREE.Vector3(0.06, -0.19, 0.0)]); return new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.0025, 8), m.rubber); },
    pos: [0, 0, 0], explode: [0.04, -0.02, 0] },
  // ---------------- Compute Pack (worn at the waist; drawn below the visor)
  { id: "pack", title: "Vantage Compute Pack", status: "working", group: "pack",
    line: "Everything heavy, on the belt.",
    detail: "A printed enclosure for the Compute Module, carrier, battery and radios. It takes the weight and the heat off the head, which is what the first testers asked for.",
    spec: "110 × 80 × 35 mm · printed PAHT-CF",
    build: (m) => { const g = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.035, 0.08), m.shellDark); return g; },
    pos: [0, -0.27, 0], explode: [0, -0.4, 0] },
  { id: "cm5", title: "Raspberry Pi Compute Module 5", status: "working", group: "pack",
    line: "Fuses camera and laser, decides what to say.",
    detail: "Runs vantage_core.py: the tracker, the beam-to-box fusion, the announcer with its priority queue, and the text reader. Chosen after the RB5 shortage and a system-on-module pivot that did not survive incomplete datasheets. 16 GB; 64 GB for the production unit.",
    spec: "BCM2712 · 4× A76 2.4 GHz · 16 GB · PCIe 2.0",
    build: (m) => { const g = new THREE.Group(); g.add(box(0.055, 0.0047, 0.04, m.pcbGreen)); const soc = box(0.012, 0.002, 0.012, m.black); soc.position.y = 0.0035; g.add(soc); return g; },
    pos: [-0.015, -0.255, 0.0], explode: [-0.02, -0.17, 0.0] },
  { id: "carrier", title: "Waveshare Nano base board", status: "working", group: "pack",
    line: "The carrier under the Compute Module.",
    detail: "Brings out the camera ports, the UART for the LiDAR, USB, and the PCIe slot for the AI accelerator. The custom PCB that replaces it is in fabrication at PCBWay.",
    spec: "CM5 carrier · 2× CSI · PCIe · UART",
    build: (m) => box(0.1, 0.0016, 0.07, m.pcbGreen),
    pos: [0, -0.262, 0], explode: [0, -0.25, 0] },
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
    pos: [0, -0.28, 0.02], explode: [0, -0.37, 0.09] },
  { id: "lora", title: "LoRa ESP32 radio", status: "planned", group: "pack",
    line: "Distress backup when there is no phone network.",
    detail: "The SOS button sends the wearer's position over the companion app first, and over long-range radio if the phone has no signal.",
    spec: "ESP32 · LoRa 868 MHz",
    build: (m) => { const g = new THREE.Group(); g.add(box(0.025, 0.002, 0.05, m.pcb)); const a = new THREE.Mesh(new THREE.CylinderGeometry(0.0015, 0.0015, 0.03, 8), m.metal); a.position.set(0, 0.015, -0.025); g.add(a); return g; },
    pos: [0.035, -0.278, -0.015], explode: [0.1, -0.3, -0.07] },
  { id: "xiao", title: "XIAO SAMD21", status: "planned", group: "pack",
    line: "A small helper for the fast, simple loops.",
    detail: "Times the haptic pulses and reads the buttons so the main processor stays on perception.",
    spec: "SAMD21 · 48 MHz",
    build: (m) => box(0.021, 0.002, 0.018, m.pcb),
    pos: [-0.04, -0.278, -0.02], explode: [-0.1, -0.3, -0.07] },
  { id: "sosbtn", title: "SOS button", status: "working", group: "pack",
    line: "One press. Location to a trusted contact.",
    detail: "Shares the wearer's position through the Vantage View companion app, where family can see it on a map. Falls back to the LoRa radio.",
    spec: "Tactile · debounced in firmware",
    build: (m) => { const c = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.004, 16), m.red); return c; },
    pos: [0.045, -0.25, 0.03], explode: [0.11, -0.22, 0.07] },
];

function box(w, h, d, m) { return new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); }

export function initInside(el) {
  const { canvas, video, slider, card, xray, reset, hint } = el;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 10); camera.position.set(0.32, 0.08, 0.42);
  const controls = new OrbitControls(camera, canvas); controls.enableDamping = true; controls.target.set(0, -0.1, 0); controls.minDistance = 0.15; controls.maxDistance = 1.2;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x222228, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 1.4); key.position.set(0.5, 0.8, 0.6); scene.add(key);
  const rim = new THREE.DirectionalLight(0x9fd0e8, 0.6); rim.position.set(-0.6, 0.2, -0.5); scene.add(rim);

  const M = {
    shell: new THREE.MeshStandardMaterial({ color: 0xe7e3dc, roughness: 0.55 }),
    shellDark: new THREE.MeshStandardMaterial({ color: 0x2a2a30, roughness: 0.6 }),
    acrylic: new THREE.MeshPhysicalMaterial({ color: 0x0a0a0c, roughness: 0.15, metalness: 0.1, clearcoat: 0.8, side: THREE.DoubleSide, transparent: true, opacity: 0.92 }),
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
    const mesh = p.build(M); mesh.traverse(o => { o.userData.part = p; });
    mesh.position.set(...p.pos); root.add(mesh);
    return { def: p, mesh, home: new THREE.Vector3(...p.pos), out: new THREE.Vector3(...p.explode) };
  });
  let explode = 0, selected = null, raf = 0, running = false;
  const ray = new THREE.Raycaster(), ptr = new THREE.Vector2();

  function layout() {
    for (const p of parts) p.mesh.position.lerpVectors(p.home, p.out, explode);
  }
  function select(part) {
    selected = part;
    for (const p of parts) p.mesh.traverse(o => { if (o.isMesh) { o.material = o.material; o.visible = true; } });
    if (part) {
      for (const p of parts) if (p !== part) p.mesh.traverse(o => { if (o.isMesh) { if (!o.userData.wire) { o.userData.orig = o.material; o.userData.wire = new THREE.MeshBasicMaterial({ color: 0x55555f, wireframe: true, transparent: true, opacity: 0.35 }); } o.material = o.userData.wire; } });
      part.mesh.traverse(o => { if (o.isMesh && o.userData.orig) o.material = o.userData.orig; });
      card.title.textContent = part.def.title; card.status.textContent = STATUS[part.def.status]; card.status.className = `badge ${part.def.status}`;
      card.line.textContent = part.def.line; card.detail.textContent = part.def.detail; card.spec.textContent = part.def.spec;
      card.root.hidden = false; hint.hidden = true;
    } else {
      for (const p of parts) p.mesh.traverse(o => { if (o.isMesh && o.userData.orig) o.material = o.userData.orig; });
      card.root.hidden = true; hint.hidden = false;
    }
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
  slider.addEventListener("input", e => { explode = +e.target.value / 1000; layout(); });
  reset.addEventListener("click", () => { camera.position.set(0.32, 0.08, 0.42); controls.target.set(0, -0.1, 0); slider.value = 0; explode = 0; layout(); select(null); });

  // "Hold over the model": the tablet camera behind the twin, so the parts can be lined up on the real Halo
  let stream = null;
  xray.addEventListener("click", async () => {
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; video.hidden = true; xray.classList.remove("on"); return; }
    try { stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false }); video.srcObject = stream; await video.play(); video.hidden = false; xray.classList.add("on"); }
    catch (_) { hint.hidden = false; hint.textContent = "Camera not available here; the twin works without it."; }
  });

  function resize() { const w = canvas.clientWidth, h = canvas.clientHeight; if (!w || !h) return; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }
  function loop() { if (!running) return; raf = requestAnimationFrame(loop); controls.update(); root.rotation.y += selected ? 0 : 0.0015; renderer.render(scene, camera); }
  layout();
  return {
    start() { running = true; resize(); window.addEventListener("resize", resize); loop(); },
    stop() { running = false; cancelAnimationFrame(raf); window.removeEventListener("resize", resize); if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; video.hidden = true; xray.classList.remove("on"); } },
    parts: PARTS,
  };
}
