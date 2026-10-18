// props.js — low-poly furniture, people and street pieces built from primitives.
// Each prop is a THREE.Group with userData:
//   label     COCO class the IMX500 would report (omit for walls/floors)
//   conf      [lo, hi] confidence range for the simulated detector
//   material  "glass" | "black" | undefined  — what the TFmini beam returns
//   solid     blocks walking
//   seeThrough the camera sees through it (glass), so it does not occlude
import * as THREE from "../vendor/three/three.module.js";

const mat = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0.02, ...extra });
export const PALETTE = {
  wall: 0xd9d2c5, floor: 0x8b7355, wood: 0x9c7a4f, dark: 0x2b2b2e, metal: 0x8a8f96,
  fabric: 0x5b6b7a, skin: 0xc9a27e, shirt: 0x3e5a7e, trousers: 0x2f2f36, dog: 0x6b4a2b,
  pavement: 0x9a9a98, road: 0x3c3c40, kerb: 0xb9b8b2, grass: 0x6c8a4c, plant: 0x3f7a3a, pot: 0x9b5a3c,
  glass: 0x9fd0e8, black: 0x111113, red: 0xb8322d, white: 0xeeeeea, yellow: 0xe8c14a,
};

function box(w, h, d, m, x = 0, y = 0, z = 0) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); mesh.position.set(x, y, z); mesh.castShadow = mesh.receiveShadow = true; return mesh;
}
function cyl(r, h, m, x = 0, y = 0, z = 0, seg = 14) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, seg), m); mesh.position.set(x, y, z); mesh.castShadow = mesh.receiveShadow = true; return mesh;
}
/** A tiling surface drawn once into a canvas: planks, slabs or tiles. */
function surface(kind, base) {
  const c = document.createElement("canvas"); c.width = c.height = 512; const x = c.getContext("2d");
  const col = "#" + base.toString(16).padStart(6, "0");
  x.fillStyle = col; x.fillRect(0, 0, 512, 512);
  const shade = (a) => `rgba(0,0,0,${a})`, light = (a) => `rgba(255,255,255,${a})`;
  if (kind === "planks") {
    for (let i = 0; i < 8; i++) { x.fillStyle = i % 2 ? shade(0.08) : light(0.04); x.fillRect(0, i * 64, 512, 64); x.fillStyle = shade(0.35); x.fillRect(0, i * 64, 512, 2); x.fillRect((i * 173) % 512, i * 64, 2, 64); }
    for (let i = 0; i < 400; i++) { x.fillStyle = shade(0.05 + 0.05 * ((i * 7) % 3)); x.fillRect((i * 97) % 512, (i * 53) % 512, 40 + (i * 13) % 90, 1); }
  } else if (kind === "slabs") {
    for (let i = 0; i <= 4; i++) { x.fillStyle = shade(0.4); x.fillRect(0, i * 128 - 1, 512, 3); x.fillRect(i * 128 - 1, 0, 3, 512); }
    for (let i = 0; i < 1600; i++) { x.fillStyle = (i % 2 ? shade : light)(0.06); x.fillRect((i * 97) % 512, (i * 53) % 512, 2, 2); }
  } else if (kind === "tiles") {
    for (let i = 0; i <= 8; i++) { x.fillStyle = shade(0.3); x.fillRect(0, i * 64 - 1, 512, 2); x.fillRect(i * 64 - 1, 0, 2, 512); }
    for (let i = 0; i < 64; i++) { x.fillStyle = (i % 3 ? light : shade)(0.03); x.fillRect((i % 8) * 64, Math.floor(i / 8) * 64, 64, 64); }
  } else if (kind === "asphalt") {
    for (let i = 0; i < 3000; i++) { x.fillStyle = (i % 2 ? shade : light)(0.07); x.fillRect((i * 97) % 512, (i * 53) % 512, 2, 2); }
  } else if (kind === "grass") {
    for (let i = 0; i < 2500; i++) { x.fillStyle = (i % 2 ? shade : light)(0.08); x.fillRect((i * 97) % 512, (i * 53) % 512, 1, 3 + (i % 4)); }
  }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t;
}
function group(label, conf, extra = {}) {
  const g = new THREE.Group();
  g.userData = { label, conf, solid: true, ...extra };
  return g;
}

export function chair(color = PALETTE.wood) {
  const g = group("chair", [0.58, 0.82]); const m = mat(color);
  g.add(box(0.44, 0.04, 0.44, m, 0, 0.45, 0));
  for (const [x, z] of [[-0.19, -0.19], [0.19, -0.19], [-0.19, 0.19], [0.19, 0.19]]) g.add(box(0.04, 0.45, 0.04, m, x, 0.225, z));
  g.add(box(0.44, 0.45, 0.04, m, 0, 0.7, -0.2));
  return g;
}

export function table(w = 1.4, d = 0.8) {
  const g = group("dining table", [0.6, 0.85]); const m = mat(PALETTE.wood);
  g.add(box(w, 0.04, d, m, 0, 0.75, 0));
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(box(0.06, 0.75, 0.06, m, sx * (w / 2 - 0.06), 0.375, sz * (d / 2 - 0.06)));
  return g;
}

/** Wall cupboard with its door left open at head height. Unrecognised by COCO on
 *  purpose: the Halo says "Obstacle too close". */
export function openCupboard() {
  const g = group(null, null); const m = mat(PALETTE.white, { roughness: 0.6 });
  g.add(box(0.8, 0.7, 0.35, m, 0, 1.75, 0));
  const door = box(0.4, 0.68, 0.02, m, 0, 0, 0);
  door.position.set(0.2, 0, 0.2); door.rotation.y = -Math.PI / 2 + 0.25;
  const hinge = new THREE.Group(); hinge.position.set(-0.4, 1.75, 0.175); hinge.add(door);
  g.add(hinge);
  return g;
}

export function counter(w = 2.4) {
  const g = group(null, null); const m = mat(PALETTE.dark, { roughness: 0.5 });
  g.add(box(w, 1.05, 0.6, m, 0, 0.525, 0));
  g.add(box(w + 0.1, 0.05, 0.7, mat(PALETTE.wood), 0, 1.075, 0));
  return g;
}

export function couch() {
  const g = group("couch", [0.62, 0.86]); const m = mat(PALETTE.fabric);
  g.add(box(1.8, 0.4, 0.85, m, 0, 0.25, 0)); g.add(box(1.8, 0.45, 0.2, m, 0, 0.65, -0.33));
  g.add(box(0.2, 0.3, 0.85, m, -0.8, 0.6, 0)); g.add(box(0.2, 0.3, 0.85, m, 0.8, 0.6, 0));
  return g;
}

export function tv() {
  const g = group("tv", [0.7, 0.9], { material: "black" }); const m = mat(PALETTE.black, { roughness: 0.3 });
  g.add(box(1.1, 0.62, 0.04, m, 0, 0.95, 0)); g.add(box(0.5, 0.03, 0.2, m, 0, 0.64, 0));
  g.userData.solid = false;
  return g;
}

export function plant() {
  const g = group("potted plant", [0.55, 0.8]);
  g.add(cyl(0.16, 0.3, mat(PALETTE.pot), 0, 0.15, 0));
  const leaf = mat(PALETTE.plant);
  g.add(cyl(0.02, 0.5, leaf, 0, 0.55, 0));
  for (let i = 0; i < 5; i++) { const s = new THREE.Mesh(new THREE.SphereGeometry(0.16, 8, 6), leaf); s.position.set(Math.cos(i * 1.26) * 0.14, 0.75 + (i % 2) * 0.12, Math.sin(i * 1.26) * 0.14); g.add(s); }
  return g;
}

export function cup() {
  const g = group("cup", [0.5, 0.72]); g.add(cyl(0.04, 0.09, mat(PALETTE.white), 0, 0.045, 0, 10)); g.userData.solid = false; return g;
}
export function bottle() {
  const g = group("bottle", [0.5, 0.75]); const m = mat(PALETTE.glass, { transparent: true, opacity: 0.7 });
  g.add(cyl(0.035, 0.22, m, 0, 0.11, 0, 10)); g.add(cyl(0.015, 0.06, m, 0, 0.25, 0, 8)); g.userData.solid = false; return g;
}
export function laptop() {
  const g = group("laptop", [0.6, 0.86], { material: "black" }); const m = mat(PALETTE.dark);
  g.add(box(0.33, 0.015, 0.23, m, 0, 0.0075, 0)); const lid = box(0.33, 0.22, 0.01, m, 0, 0.11, -0.115); lid.rotation.x = -0.3; g.add(lid); g.userData.solid = false; return g;
}

export function person(opts = {}) {
  const g = group("person", [0.78, 0.95]);
  const shirt = mat(opts.shirt ?? PALETTE.shirt), trousers = mat(PALETTE.trousers), skin = mat(PALETTE.skin);
  g.add(box(0.36, 0.55, 0.22, shirt, 0, 1.15, 0));
  g.add(box(0.15, 0.85, 0.18, trousers, -0.1, 0.425, 0)); g.add(box(0.15, 0.85, 0.18, trousers, 0.1, 0.425, 0));
  g.add(box(0.09, 0.5, 0.1, shirt, -0.25, 1.15, 0)); g.add(box(0.09, 0.5, 0.1, shirt, 0.25, 1.15, 0));
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.11, 10, 8), skin); head.position.y = 1.58; g.add(head);
  g.userData.height = 1.7;
  return g;
}

export function dog() {
  const g = group("dog", [0.6, 0.85]); const m = mat(PALETTE.dog);
  g.add(box(0.5, 0.22, 0.2, m, 0, 0.38, 0));
  for (const [x, z] of [[-0.18, -0.07], [0.18, -0.07], [-0.18, 0.07], [0.18, 0.07]]) g.add(box(0.05, 0.3, 0.05, m, x, 0.15, z));
  g.add(box(0.16, 0.16, 0.16, m, 0.3, 0.52, 0)); g.add(box(0.05, 0.05, 0.22, m, -0.3, 0.46, 0));
  return g;
}

/** Full-height glass door in a frame: the camera sees through it, the TFmini does not get a return. */
export function glassDoor(w = 1.0, h = 2.1) {
  const g = group(null, null, { material: "glass", seeThrough: true });
  const frame = mat(PALETTE.metal, { roughness: 0.4, metalness: 0.4 });
  g.add(box(0.05, h, 0.05, frame, -w / 2, h / 2, 0)); g.add(box(0.05, h, 0.05, frame, w / 2, h / 2, 0)); g.add(box(w, 0.05, 0.05, frame, 0, h, 0));
  const glass = new THREE.Mesh(new THREE.PlaneGeometry(w - 0.05, h - 0.05), new THREE.MeshPhysicalMaterial({ color: PALETTE.glass, transparent: true, opacity: 0.18, roughness: 0.05, metalness: 0, side: THREE.DoubleSide }));
  glass.position.set(0, h / 2, 0); glass.userData.seeThrough = true; g.add(glass);
  g.add(box(0.03, 0.3, 0.03, frame, w / 2 - 0.12, 1.05, 0.04));
  return g;
}

export function wall(w, h, d, color = PALETTE.wall) {
  const g = group(null, null); g.add(box(w, h, d, mat(color), 0, h / 2, 0)); return g;
}
export function floor(w, d, color = PALETTE.floor, kind = "planks", tile = 1.2) {
  const tex = surface(kind, color); tex.repeat.set(w / tile, d / tile);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, d), new THREE.MeshStandardMaterial({ color: 0xffffff, map: tex, roughness: 0.95 }));
  m.rotation.x = -Math.PI / 2; m.userData.ground = true; m.receiveShadow = true; return m;
}

export function bollard() {
  const g = group(null, null, { material: "black" }); g.add(cyl(0.08, 0.95, mat(PALETTE.black, { roughness: 0.5 }), 0, 0.475, 0)); return g;
}
export function bench() {
  const g = group("bench", [0.6, 0.85]); const m = mat(PALETTE.wood);
  g.add(box(1.6, 0.05, 0.45, m, 0, 0.45, 0)); g.add(box(1.6, 0.4, 0.05, m, 0, 0.7, -0.2));
  for (const x of [-0.7, 0.7]) g.add(box(0.06, 0.45, 0.45, mat(PALETTE.metal), x, 0.225, 0));
  return g;
}
export function bicycle() {
  const g = group("bicycle", [0.6, 0.88]); const m = mat(PALETTE.metal, { metalness: 0.5, roughness: 0.4 });
  for (const x of [-0.5, 0.5]) { const t = new THREE.Mesh(new THREE.TorusGeometry(0.33, 0.025, 8, 24), mat(PALETTE.black)); t.position.set(x, 0.35, 0); t.rotation.y = Math.PI / 2; g.add(t); }
  g.add(box(1.0, 0.04, 0.04, m, 0, 0.6, 0)); g.add(box(0.04, 0.55, 0.04, m, 0.1, 0.65, 0)); g.add(box(0.04, 0.6, 0.04, m, -0.4, 0.6, 0));
  g.add(box(0.25, 0.04, 0.06, mat(PALETTE.black), 0.1, 0.92, 0)); g.add(box(0.05, 0.03, 0.45, m, -0.4, 0.9, 0));
  return g;
}
export function cyclist() {
  const g = group("person", [0.7, 0.92]); const b = bicycle(); b.userData.label = "bicycle"; g.add(b);
  const p = person({ shirt: PALETTE.yellow }); p.scale.set(0.95, 0.9, 0.95); p.position.set(0, 0.3, 0); p.rotation.y = -Math.PI / 2; g.add(p);
  g.userData.parts = [b]; // the detector reports the bicycle too
  return g;
}
export function parkedCar() {
  const g = group("car", [0.8, 0.96]); const m = mat(0x5a6c7e, { metalness: 0.4, roughness: 0.35 });
  g.add(box(4.2, 0.7, 1.8, m, 0, 0.6, 0)); g.add(box(2.4, 0.6, 1.7, mat(PALETTE.black, { roughness: 0.2 }), -0.2, 1.25, 0));
  for (const [x, z] of [[-1.4, -0.9], [1.4, -0.9], [-1.4, 0.9], [1.4, 0.9]]) { const w = cyl(0.33, 0.22, mat(PALETTE.black), x, 0.33, z); w.rotation.x = Math.PI / 2; g.add(w); }
  return g;
}
export function trafficLight() {
  const g = group("traffic light", [0.6, 0.85], { material: "black" }); const m = mat(PALETTE.black);
  g.add(cyl(0.06, 3.2, m, 0, 1.6, 0)); g.add(box(0.3, 0.8, 0.25, m, 0, 3.4, 0));
  for (const [y, c] of [[3.65, 0xff3b30], [3.4, 0xffcc00], [3.15, 0x34c759]]) { const l = new THREE.Mesh(new THREE.SphereGeometry(0.08, 8, 8), new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: 0.6 })); l.position.set(0, y, 0.13); g.add(l); }
  return g;
}
export function fireHydrant() {
  const g = group("fire hydrant", [0.6, 0.85]); const m = mat(PALETTE.red);
  g.add(cyl(0.12, 0.7, m, 0, 0.35, 0)); g.add(box(0.4, 0.1, 0.12, m, 0, 0.5, 0)); return g;
}

/** A sign with readable text, rendered to a canvas texture. */
export function sign(lines, opts = {}) {
  const w = opts.w ?? 0.9, h = opts.h ?? 0.6, y = opts.y ?? 2.1;
  const g = group(opts.label ?? null, opts.conf ?? null, { material: opts.material });
  const cvs = document.createElement("canvas"); cvs.width = 512; cvs.height = Math.round(512 * h / w);
  const c = cvs.getContext("2d");
  c.fillStyle = opts.bg ?? "#1d2b4f"; c.fillRect(0, 0, cvs.width, cvs.height);
  c.fillStyle = opts.fg ?? "#ffffff"; c.textAlign = "center"; c.textBaseline = "middle";
  const fs = Math.min(64, (cvs.height / (lines.length + 0.6)) * 0.8);
  c.font = `600 ${fs}px -apple-system, Helvetica, Arial, sans-serif`;
  lines.forEach((l, i) => c.fillText(l, cvs.width / 2, (i + 0.8) * (cvs.height / (lines.length + 0.6))));
  const tex = new THREE.CanvasTexture(cvs); tex.colorSpace = THREE.SRGBColorSpace;
  const panel = new THREE.Mesh(new THREE.BoxGeometry(w, h, 0.04), [mat(PALETTE.metal), mat(PALETTE.metal), mat(PALETTE.metal), mat(PALETTE.metal), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.6 }), mat(PALETTE.metal)]);
  panel.position.set(0, y, 0); g.add(panel);
  if (opts.post !== false) g.add(cyl(0.035, y - h / 2, mat(PALETTE.metal), 0, (y - h / 2) / 2, 0));
  g.userData.solid = opts.post !== false;
  return g;
}

export function kerb(len) {
  const g = group(null, null); g.add(box(len, 0.12, 0.3, mat(PALETTE.kerb), 0, 0.06, 0)); return g;
}
export function tree() {
  const g = group(null, null); g.add(cyl(0.12, 2.2, mat(0x5a4330), 0, 1.1, 0));
  const c = new THREE.Mesh(new THREE.SphereGeometry(1.1, 10, 8), mat(PALETTE.plant)); c.position.y = 2.8; g.add(c); return g;
}
export function backpack() {
  const g = group("backpack", [0.55, 0.8]); g.add(box(0.3, 0.42, 0.18, mat(0x7a2e2e), 0, 0.21, 0)); return g;
}
export function suitcase() {
  const g = group("suitcase", [0.6, 0.86], { material: "black" }); g.add(box(0.4, 0.6, 0.25, mat(PALETTE.black, { roughness: 0.4 }), 0, 0.3, 0)); return g;
}
export function shelf(w = 2.0) {
  const g = group(null, null); const m = mat(PALETTE.white, { roughness: 0.7 });
  g.add(box(w, 2.0, 0.4, mat(0xe6e2d8), 0, 1.0, 0));
  for (let i = 0; i < 4; i++) {
    for (let j = 0; j < Math.floor(w / 0.25); j++) {
      const b = box(0.16, 0.2, 0.1, mat([0xd9534f, 0x3f7fbf, 0xf0c050, 0x7cb342][(i + j) % 4]), -w / 2 + 0.15 + j * 0.25, 0.4 + i * 0.45, 0.17); g.add(b);
    }
  }
  return g;
}
