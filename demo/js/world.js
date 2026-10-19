// world.js — renders a scene from the Halo wearer's eye line and simulates the two
// sensors from ground truth:
//   IMX500   every labelled prop that is visible is projected to a 640x480 box, with the
//            jitter, confidence spread and occasional misses a real detector has.
//   TFmini   a raycast from the camera (plus the mount offset) inside a 3.6° cone;
//            glass and gloss-black return a weak signal, which the firmware discards.
import * as THREE from "../vendor/three/three.module.js";

const EYE_HEIGHT = 1.55;             // the Sensor Visor sits on the forehead
const WALK_SPEED = 1.0;              // m/s, free mode
const GUIDE_SPEED = 0.7;             // m/s, "Guide me"
const PLAYER_RADIUS = 0.28;

export class World {
  constructor(canvas, cfg) {
    this.cfg = cfg; this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping; this.renderer.toneMappingExposure = 1.0;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.shadowMap.enabled = true; this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.camera = new THREE.PerspectiveCamera(cfg.camVfovDeg, cfg.width / cfg.height, 0.05, 60);
    this.scene = null; this.def = null; this.props = []; this.actors = []; this.solids = [];
    this.player = { x: 0, z: 0, yaw: 0, pitch: 0, lookYaw: 0, lookPitch: 0 };
    this.mode = "guide"; this.rail = null; this.railS = 0; this.railLen = 0;
    this.input = { jx: 0, jy: 0, hold: false, dx: 0, dy: 0 };
    this.ray = new THREE.Raycaster(); this.ray.firstHitOnly = false;
    this.t = 0; this.bumps = []; this.onBump = () => {}; this.onRailEnd = () => {};
    this.frozen = false; this._railEnded = false;
    this._v = new THREE.Vector3(); this._box = new THREE.Box3(); this._dir = new THREE.Vector3();
    this._detectT = 0; this._lastDets = [];
  }

  resize(w, h) {
    this.renderer.setSize(w, h, false);
    // Keep the firmware's 4:3 field of view regardless of the pane's shape
    this.camera.aspect = w / h;
    const vf = this.cfg.camVfovDeg, hf = this.cfg.camHfovDeg;
    const wantAspect = Math.tan(hf / 2 * Math.PI / 180) / Math.tan(vf / 2 * Math.PI / 180);
    this.camera.fov = this.camera.aspect >= wantAspect ? vf : 2 * Math.atan(Math.tan(hf / 2 * Math.PI / 180) / this.camera.aspect) * 180 / Math.PI;
    this.camera.updateProjectionMatrix();
  }

  load(def) {
    this.def = def;
    const scene = new THREE.Scene();
    const lights = {
      evening: { sky: 0xffe2c0, ground: 0x3a2d22, hemi: 0.55, sun: 0xffc080, sunI: 1.1, sunPos: [-3, 4, 2], bg: 0x1b1611, fog: 0x1b1611 },
      morning: { sky: 0xcfe6ff, ground: 0x6a6a60, hemi: 0.8, sun: 0xfff2d8, sunI: 1.6, sunPos: [5, 10, 3], bg: 0xbcd3ea, fog: 0xbcd3ea },
      indoor: { sky: 0xfff4e6, ground: 0x4a4038, hemi: 0.7, sun: 0xffe8c8, sunI: 0.9, sunPos: [2, 5, 2], bg: 0x241f1b, fog: 0x241f1b },
      "morning-in": { sky: 0xfff6ea, ground: 0x5a5046, hemi: 0.95, sun: 0xfff0d8, sunI: 1.2, sunPos: [3, 6, 2], bg: 0x2a2520, fog: 0x2a2520 },
    }[def.light] || {};
    scene.background = new THREE.Color(lights.bg ?? 0x202020);
    scene.fog = new THREE.Fog(lights.fog ?? 0x202020, 14, 30);
    scene.add(new THREE.HemisphereLight(lights.sky, lights.ground, lights.hemi));
    const sun = new THREE.DirectionalLight(lights.sun, lights.sunI); sun.position.set(...lights.sunPos); scene.add(sun);
    sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048); sun.shadow.bias = -0.0005; sun.shadow.normalBias = 0.02;
    const b = def.bounds, span = Math.max(b.maxX - b.minX, b.maxZ - b.minZ) + 6;
    Object.assign(sun.shadow.camera, { left: -span / 2, right: span / 2, top: span / 2, bottom: -span / 2, near: 0.5, far: 40 });
    sun.target.position.set((b.minX + b.maxX) / 2, 0, (b.minZ + b.maxZ) / 2); scene.add(sun.target);
    sun.position.set(sun.target.position.x + lights.sunPos[0] * 2, lights.sunPos[1] * 2, sun.target.position.z + lights.sunPos[2] * 2);
    scene.add(new THREE.AmbientLight(0xffffff, 0.15));
    for (const p of def.props) scene.add(p);
    this.props = def.props.filter(p => p.userData && (p.userData.label || p.userData.solid || p.userData.material));
    this.actors = def.actors || [];
    this.scene = scene;
    this.player.x = def.start.x; this.player.z = def.start.z; this.player.yaw = def.start.yaw;
    this.player.pitch = 0; this.player.lookYaw = 0; this.player.lookPitch = 0;
    this.rail = def.rail ? def.rail.map(([x, z]) => new THREE.Vector2(x, z)) : null;
    this.railS = 0; this._railEnded = false;
    if (this.rail) { this.railLen = 0; for (let i = 1; i < this.rail.length; i++) this.railLen += this.rail[i].distanceTo(this.rail[i - 1]); }
    this.t = 0; this.bumps = []; this._lastDets = [];
    this.updateActors(0);
    this._updateCamera();
  }

  setMode(m) { this.mode = m; if (m === "guide" && this.rail) this._snapToRail(); }
  _snapToRail() {
    // nearest point on the rail to the player
    let best = Infinity, bestS = 0, acc = 0;
    for (let i = 1; i < this.rail.length; i++) {
      const a = this.rail[i - 1], b = this.rail[i], ab = b.clone().sub(a), len = ab.length();
      const t = Math.max(0, Math.min(1, new THREE.Vector2(this.player.x, this.player.z).sub(a).dot(ab) / (len * len)));
      const p = a.clone().addScaledVector(ab, t), d = p.distanceTo(new THREE.Vector2(this.player.x, this.player.z));
      if (d < best) { best = d; bestS = acc + t * len; }
      acc += len;
    }
    this.railS = bestS;
  }
  _railPoint(s) {
    let acc = 0;
    for (let i = 1; i < this.rail.length; i++) {
      const a = this.rail[i - 1], b = this.rail[i], len = a.distanceTo(b);
      if (s <= acc + len || i === this.rail.length - 1) {
        const t = len > 0 ? Math.max(0, Math.min(1, (s - acc) / len)) : 0;
        return { p: a.clone().lerp(b, t), dir: b.clone().sub(a).normalize() };
      }
      acc += len;
    }
    return { p: this.rail[this.rail.length - 1].clone(), dir: new THREE.Vector2(0, -1) };
  }

  setPose(x, z, yaw, pitch = 0) { this.player.x = x; this.player.z = z; this.player.yaw = yaw; this.player.pitch = pitch; this.player.lookYaw = 0; this.player.lookPitch = 0; this._updateCamera(); }
  getPose() { const p = this.player; return { x: p.x, z: p.z, yaw: p.yaw + p.lookYaw, pitch: p.pitch + p.lookPitch }; }
  get railProgress() { return this.rail ? this.railS / this.railLen : 0; }

  updateActors(t) { for (const a of this.actors) a.update(t); }

  /** Advance the simulation by dt seconds. */
  update(dt, now) {
    this.t += dt;
    this.updateActors(this.t);
    const pl = this.player, inp = this.input;
    // look-around from drag
    pl.lookYaw -= inp.dx * 0.004; pl.lookPitch = Math.max(-0.6, Math.min(0.5, pl.lookPitch - inp.dy * 0.004));
    inp.dx = 0; inp.dy = 0;
    if (!this.frozen) {
      if (this.mode === "guide" && this.rail) {
        if (inp.hold || inp.jy < -0.2) {
          const prev = this.railS;
          this.railS = Math.min(this.railLen, this.railS + GUIDE_SPEED * dt);
          const { p, dir } = this._railPoint(this.railS);
          const yawTarget = Math.atan2(-dir.x, -dir.y);   // facing along the rail (camera looks down -z at yaw 0)
          let dy = yawTarget - pl.yaw; while (dy > Math.PI) dy -= 2 * Math.PI; while (dy < -Math.PI) dy += 2 * Math.PI;
          pl.yaw += dy * Math.min(1, dt * 2.2);
          const moved = this._tryMove(p.x - pl.x, p.y - pl.z, now);
          if (!moved) this.railS = prev;             // blocked by an actor in the way: wait
          if (this.railS >= this.railLen - 1e-3 && !this._railEnded) { this._railEnded = true; this.onRailEnd(); }
        }
        // drag offset decays back to the rail direction
        pl.lookYaw *= Math.exp(-dt * 1.2); pl.lookPitch *= Math.exp(-dt * 1.2);
      } else {
        const mag = Math.hypot(inp.jx, inp.jy);
        if (mag > 0.08) {
          const yaw = pl.yaw + pl.lookYaw;
          const fwd = -inp.jy * WALK_SPEED * dt, side = inp.jx * WALK_SPEED * dt;
          const dx = -Math.sin(yaw) * fwd + Math.cos(yaw) * side;
          const dz = -Math.cos(yaw) * fwd - Math.sin(yaw) * side;
          this._tryMove(dx, dz, now);
        }
        // in free mode, the drag is the heading
        pl.yaw += pl.lookYaw; pl.lookYaw = 0;
        pl.pitch = Math.max(-0.6, Math.min(0.5, pl.pitch + pl.lookPitch)); pl.lookPitch = 0;
      }
    }
    this._updateCamera();
  }

  _tryMove(dx, dz, now) {
    const pl = this.player, b = this.def.bounds;
    const nx = Math.max(b.minX, Math.min(b.maxX, pl.x + dx)), nz = Math.max(b.minZ, Math.min(b.maxZ, pl.z + dz));
    // circle vs. prop AABB (solids only)
    for (const p of this.props) {
      if (!p.userData.solid || !p.visible) continue;
      this._box.setFromObject(p);
      if (this._box.max.y < 0.2 || this._box.min.y > 1.9) continue;      // floor-level trim or above the head
      const cx = Math.max(this._box.min.x, Math.min(nx, this._box.max.x)), cz = Math.max(this._box.min.z, Math.min(nz, this._box.max.z));
      if (Math.hypot(nx - cx, nz - cz) < PLAYER_RADIUS) {
        const last = this.bumps[this.bumps.length - 1];
        if (!last || now - last.t > 1.5 || last.obj !== p) { this.bumps.push({ t: now, obj: p, label: p.userData.label || "obstacle" }); this.onBump(p); }
        return false;
      }
    }
    pl.x = nx; pl.z = nz; return true;
  }

  _updateCamera() {
    const pl = this.player, yaw = pl.yaw + pl.lookYaw, pitch = pl.pitch + pl.lookPitch;
    this.camera.position.set(pl.x, EYE_HEIGHT, pl.z);
    this.camera.rotation.set(0, 0, 0); this.camera.rotation.order = "YXZ";
    this.camera.rotation.y = yaw; this.camera.rotation.x = pitch;
    this.camera.updateMatrixWorld();
  }

  render() { if (this.scene) this.renderer.render(this.scene, this.camera); }

  // ------------------------------------------------------------------ IMX500 simulation

  /** Returns detections in the firmware's 640x480 frame, or null on a missed tensor. */
  detect(now) {
    // the sensor delivers a tensor about every frame; simulate ~20 Hz and occasional misses
    if (now - this._detectT < 0.05) return this._lastDets;
    this._detectT = now;
    if (Math.random() < 0.06) { this._lastDets = null; return null; }
    const W = this.cfg.width, H = this.cfg.height, dets = [];
    const camPos = this.camera.position;
    const consider = [];
    for (const p of this.props) {
      if (!p.visible) continue;
      if (p.userData.label) consider.push(p);
      if (p.userData.parts) for (const q of p.userData.parts) if (q.userData.label) consider.push(q);
    }
    for (const p of consider) {
      this._box.setFromObject(p);
      if (this._box.isEmpty()) continue;
      const center = this._box.getCenter(this._v.clone());
      const dist = center.distanceTo(camPos);
      if (dist > 14) continue;
      // in front of the camera?
      const toObj = center.clone().sub(camPos).normalize();
      this.camera.getWorldDirection(this._dir);
      if (toObj.dot(this._dir) < 0.2) continue;
      // occlusion: the first thing the camera hits toward the object must be the object
      this.ray.set(camPos, toObj); this.ray.far = dist + 0.5;
      const hits = this.ray.intersectObjects(this.scene.children, true);
      let blocked = false;
      for (const h of hits) {
        if (h.object.userData.ground || h.object.userData.seeThrough) continue;
        if (isDescendant(h.object, p)) break;
        if (h.distance < dist - 0.05) { blocked = true; break; }
      }
      if (blocked) continue;
      // project the 8 corners
      let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
      for (let i = 0; i < 8; i++) {
        this._v.set(i & 1 ? this._box.max.x : this._box.min.x, i & 2 ? this._box.max.y : this._box.min.y, i & 4 ? this._box.max.z : this._box.min.z);
        this._v.project(this.camera);
        if (this._v.z > 1) continue;
        const sx = (this._v.x + 1) / 2 * W, sy = (1 - this._v.y) / 2 * H;
        minX = Math.min(minX, sx); maxX = Math.max(maxX, sx); minY = Math.min(minY, sy); maxY = Math.max(maxY, sy);
      }
      if (minX > 1e8) continue;
      if (p.userData.small) {   // a set of keys is a few pixels tall: the fine-tuned model still boxes it, a little generously
        const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2, hw = Math.max(9, (maxX - minX) / 2), hh = Math.max(9, (maxY - minY) / 2);
        minX = cx - hw; maxX = cx + hw; minY = cy - hh; maxY = cy + hh;
      }
      const fullW = maxX - minX, fullH = maxY - minY;
      const x0 = Math.max(0, minX), y0 = Math.max(0, minY), x1 = Math.min(W, maxX), y1 = Math.min(H, maxY);
      const w = x1 - x0, h = y1 - y0;
      if (w < 8 || h < 8) continue;
      const visibleFrac = (w * h) / Math.max(1, fullW * fullH);
      if (visibleFrac < 0.25) continue;
      // detector character: jitter, confidence by class, less sure when small or clipped, misses
      const [lo, hi] = p.userData.conf || [0.5, 0.8];
      let score = lo + Math.random() * (hi - lo);
      if (h < 40) score -= 0.15; if (visibleFrac < 0.6) score -= 0.1;
      if (Math.random() < 0.05) continue;
      const jx = (Math.random() - 0.5) * 0.04 * w, jy = (Math.random() - 0.5) * 0.04 * h, jw = (Math.random() - 0.5) * 0.06 * w, jh = (Math.random() - 0.5) * 0.06 * h;
      dets.push({ label: p.userData.label, score: Math.round(Math.max(0.3, Math.min(0.99, score)) * 100) / 100, box: [x0 + jx, y0 + jy, Math.max(4, w + jw), Math.max(4, h + jh)], obj: p });
    }
    dets.sort((a, b) => b.score - a.score);
    this._lastDets = dets.slice(0, this.cfg.maxDetections);
    return this._lastDets;
  }

  // ------------------------------------------------------------------ TFmini simulation

  /** One TFmini reading: { cm, strength, material } or { cm: null, strength: 0 } when nothing in range. */
  lidar() {
    const cfg = this.cfg;
    const origin = this.camera.position.clone();
    // mount offset in camera space (cm → m), +x right, +y below
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(this.camera.quaternion);
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(this.camera.quaternion);
    origin.addScaledVector(right, cfg.lidarOffsetXCm / 100).addScaledVector(up, -cfg.lidarOffsetYCm / 100);
    this.camera.getWorldDirection(this._dir);
    const half = (cfg.lidarBeamDeg / 2) * Math.PI / 180;
    let best = null;
    const dirs = [this._dir.clone()];
    for (let k = 0; k < 4; k++) {
      const a = k * Math.PI / 2;
      dirs.push(this._dir.clone().addScaledVector(right, Math.cos(a) * Math.tan(half)).addScaledVector(up, Math.sin(a) * Math.tan(half)).normalize());
    }
    for (const d of dirs) {
      this.ray.set(origin, d); this.ray.far = cfg.lidarMaxRangeCm / 100 + 0.5;
      const hits = this.ray.intersectObjects(this.scene.children, true);
      for (const h of hits) {
        if (h.object.userData.ground) continue;
        if (!best || h.distance < best.distance) {
          const root = rootProp(h.object); best = { distance: h.distance, material: root ? root.userData.material : undefined, obj: root };
        }
        break;
      }
    }
    if (!best || best.distance * 100 > cfg.lidarMaxRangeCm) return { cm: null, strength: 0, material: null, obj: null };
    const cm = best.distance * 100 + (Math.random() - 0.5) * 2;
    let strength;
    if (best.material === "glass") strength = 20 + Math.floor(Math.random() * 50);
    else if (best.material === "black") strength = 40 + Math.floor(Math.random() * 60);
    else strength = Math.round(Math.max(120, Math.min(2500, 60000 / Math.max(cm, 30))));
    if (cm < 10) return { cm: null, strength: 0, material: best.material, obj: best.obj, tooClose: true };
    return { cm, strength, material: best.material, obj: best.obj };
  }

  /** The visitor is inside the goal circle (by-ear mode). */
  atGoal() { const g = this.def.goal; return g && Math.hypot(this.player.x - g.x, this.player.z - g.z) < g.r; }
}

function isDescendant(obj, root) { let o = obj; while (o) { if (o === root) return true; o = o.parent; } return false; }
function rootProp(obj) { let o = obj, found = null; while (o) { if (o.userData && (o.userData.label || o.userData.material || o.userData.solid)) found = o; o = o.parent; } return found; }
