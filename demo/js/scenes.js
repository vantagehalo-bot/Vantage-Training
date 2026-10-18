// scenes.js — Abdullah's trip to the coffee shop, the journey the pitch deck opens with:
// his flat in the evening, the pavement outside, and the café. Units are metres; y is up.
// Each scene returns { props, actors, rail, start, goal, bounds }.
//   props   static groups (see props.js)
//   actors  { obj, update(t) } moving things
//   rail    waypoints for "Guide me" ([x, z] pairs)
//   start   { x, z, yaw }
//   goal    { x, z, r } the door to reach in the by-ear mode
import * as THREE from "../vendor/three/three.module.js";
import * as P from "./props.js";

function place(obj, x, z, yaw = 0) { obj.position.set(x, 0, z); obj.rotation.y = yaw; return obj; }

/** Seeded pseudo-random for the shuffled by-ear layout. */
function rng(seed) { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

// ----------------------------------------------------------------------------- HOME
export function home({ shuffle = 0 } = {}) {
  const r = rng(shuffle); const j = (a) => (shuffle ? (r() - 0.5) * a : 0);
  const props = [], actors = [];
  // Room 7 x 6, player starts at the hallway end (z = +2.6) and walks toward the patio door at z = -2.9
  props.push(P.floor(7, 6, P.PALETTE.floor, "planks", 1.4));
  const wallH = 2.6;
  props.push(place(P.wall(7, wallH, 0.15), 0, -3.0));
  props.push(place(P.wall(7, wallH, 0.15), 0, 3.0));
  props.push(place(P.wall(0.15, wallH, 6), -3.5, 0));
  props.push(place(P.wall(0.15, wallH, 6), 3.5, 0));
  // Patio glass door set into the back wall
  const door = P.glassDoor(1.1, 2.1); place(door, -0.4 + j(1.2), -2.92); props.push(door);
  // Kitchen run along the right wall, with the cupboard door left open at head height
  props.push(place(P.counter(3.0), 2.4, -1.6, Math.PI / 2));
  props.push(place(P.openCupboard(), 1.65 + j(0.5), -0.6 + j(0.8), Math.PI));   // door swings into the walkway
  // Dining table with chairs; one chair pulled out into the path
  const tx = -1.1 + j(0.8), tz = 0.3 + j(0.8);
  props.push(place(P.table(1.4, 0.8), tx, tz));
  props.push(place(P.chair(), tx - 0.9, tz, Math.PI / 2));
  props.push(place(P.chair(), tx + 0.25, tz + 0.85 + j(0.3), Math.PI));          // pulled out
  props.push(place(P.chair(), tx + 0.45, tz - 0.75, 0));
  const cupOn = P.cup(); cupOn.position.set(tx + 0.3, 0.77, tz - 0.1); props.push(cupOn);
  const lap = P.laptop(); lap.position.set(tx - 0.3, 0.77, tz + 0.05); props.push(lap);
  // Living corner
  props.push(place(P.couch(), -2.2 + j(0.4), -1.9, Math.PI / 2 * 0 + 0.0));
  props.push(place(P.tv(), -3.35, -1.9, Math.PI / 2));
  props.push(place(P.plant(), 3.0, 2.4)); props.push(place(P.plant(), -3.0, 2.5));
  props.push(place(P.backpack(), 0.9 + j(0.6), 1.9 + j(0.4)));
  // The dog wanders between the couch and the table
  const d = P.dog(); props.push(d);
  const path = [[-1.0, 1.8], [0.6, 1.2], [1.2, -0.2], [-0.2, -1.2], [-1.8, -0.6]];
  actors.push(walker(d, path, 0.55, { pause: 1.8, loop: true }));
  const rail = [[0.3, 2.5], [0.3, 1.6], [0.0, 0.9], [-0.1, 0.2], [0.6, -0.6], [0.3, -1.3], [-0.4 + j(1.2), -1.6], [-0.4 + j(1.2), -2.0]];
  return {
    id: "home", title: "Home, evening", props, actors, rail,
    start: { x: 0.3, z: 2.55, yaw: 0 },    // yaw 0 looks down -z
    goal: { x: -0.4 + j(1.2), z: -2.6, r: 0.6 },
    bounds: { minX: -3.3, maxX: 3.3, minZ: -2.8, maxZ: 2.8 },
    light: "evening",
    beats: ["Chair pulled out into the path", "Cupboard door open at head height", "Dog crossing", "Glass patio door: the laser gets no return"],
  };
}

// ----------------------------------------------------------------------------- STREET
export function street({ shuffle = 0 } = {}) {
  const props = [], actors = [];
  // Pavement runs along z from +12 to -12, x in [-1.5, 1.5]; road to the +x side.
  props.push(P.floor(3, 26, P.PALETTE.pavement, "slabs", 1.0));
  const road = P.floor(8, 26, P.PALETTE.road, "asphalt", 2.0); road.position.x = 5.5; props.push(road);
  const grass = P.floor(4, 26, P.PALETTE.grass, "grass", 1.5); grass.position.x = -3.5; props.push(grass);
  props.push(place(P.kerb(26), 1.65, 0));
  // Building face on the left
  props.push(place(P.wall(0.3, 3.5, 26, 0xc8bfae), -5.6, 0));
  for (let z = -10; z <= 10; z += 5) props.push(place(P.tree(), -3.4, z));
  // Street furniture on the pavement
  props.push(place(P.bollard(), 0.9, 6.0)); props.push(place(P.bollard(), 0.9, 5.0));
  props.push(place(P.bench(), -0.9, 2.5, Math.PI / 2));
  props.push(place(P.fireHydrant(), 1.1, -1.5));
  props.push(place(P.bicycle(), -1.1, -3.5, 0.3));
  props.push(place(P.trafficLight(), 1.2, -9.0));
  props.push(place(P.parkedCar(), 3.2, 4.0)); props.push(place(P.parkedCar(), 3.2, -6.5));
  props.push(place(P.suitcase(), 0.4, -5.5));
  props.push(place(P.sign(["Trains to Central Station", "Next departure 10:45"], { w: 1.1, h: 0.5, y: 2.1 }), -1.1, 0.0, Math.PI / 2));
  props.push(place(P.sign(["BUS 12  →  Marina"], { w: 0.8, h: 0.3, y: 2.4, bg: "#8a1c1c" }), 1.2, -7.0, -Math.PI / 2));
  // People: one walking toward the user, one crossing, one standing at the stop
  const p1 = P.person(); props.push(p1);
  actors.push(walker(p1, [[0.2, -8.0], [0.2, 9.0]], 1.2, { loop: true, pingpong: true }));
  const p2 = P.person({ shirt: 0x7a3b5a }); props.push(p2);
  actors.push(walker(p2, [[-1.2, 3.0], [-1.2, -11.0]], 1.0, { loop: true, pingpong: true, phase: 6 }));
  const p3 = P.person({ shirt: 0x3a6b4a }); place(p3, 0.9, -7.6, Math.PI / 2); props.push(p3);
  // The cyclist cuts across the pavement from the road every 12 s
  const c = P.cyclist(); props.push(c);
  actors.push(crosser(c, [5.5, -4.0], [-1.2, 0.8], 5.0, 12.0));
  const rail = [[0.3, 11.0], [0.3, 7.5], [-0.2, 4.5], [0.2, 1.5], [0.0, -2.0], [0.3, -5.0], [0.0, -8.0], [0.0, -10.5]];
  return {
    id: "street", title: "Street, morning", props, actors, rail,
    start: { x: 0.3, z: 11.2, yaw: 0 },
    goal: { x: 0.0, z: -10.5, r: 0.8 },
    bounds: { minX: -1.4, maxX: 1.45, minZ: -11.5, maxZ: 11.5 },
    light: "morning",
    beats: ["Bollards", "Person approaching: time-to-contact", "Cyclist cutting across: a CRITICAL pre-empts", "Sign to read"],
  };
}

// ----------------------------------------------------------------------------- CAFÉ
export function cafe({ shuffle = 0 } = {}) {
  const r = rng(shuffle); const j = (a) => (shuffle ? (r() - 0.5) * a : 0);
  const props = [], actors = [];
  props.push(P.floor(8, 8, 0x8a7a6a, "tiles", 0.6));
  props.push(place(P.wall(8, 2.8, 0.15, 0xe3dccd), 0, -4.0)); props.push(place(P.wall(8, 2.8, 0.15, 0xe3dccd), 0, 4.0));
  props.push(place(P.wall(0.15, 2.8, 8, 0xe3dccd), -4.0, 0)); props.push(place(P.wall(0.15, 2.8, 8, 0xe3dccd), 4.0, 0));
  // Entrance glass door behind the start
  const door = P.glassDoor(1.1, 2.1); place(door, 0.0, 3.92); props.push(door);
  // Counter at the back with a barista and a menu board
  props.push(place(P.counter(3.2), 0.0, -3.0));
  const barista = P.person({ shirt: 0x2f2f36 }); place(barista, 0.3, -3.5, 0); props.push(barista);
  props.push(place(P.sign(["Flat white  18", "Cappuccino  17", "Karak chai  8"], { w: 1.6, h: 0.7, y: 2.0, bg: "#2b2420", fg: "#f3e9d2", post: false }), 0, -3.9));
  props.push(place(P.shelf(1.8), 2.9, -3.7, 0));
  // Tables and chairs, a few pulled out; a basket of stock on the floor
  const spots = [[-2.2 + j(0.5), 0.8 + j(0.5)], [1.9 + j(0.5), 1.0 + j(0.5)], [-1.8 + j(0.5), -1.4 + j(0.5)], [2.1 + j(0.5), -1.2 + j(0.5)]];
  for (const [x, z] of spots) {
    props.push(place(P.table(0.8, 0.8), x, z));
    props.push(place(P.chair(), x, z + 0.75, Math.PI)); props.push(place(P.chair(), x - 0.75, z, Math.PI / 2));
    const cu = P.cup(); cu.position.set(x + 0.15, 0.77, z - 0.1); props.push(cu);
  }
  props.push(place(P.chair(), -0.6 + j(0.6), 1.4 + j(0.6), 0.6));   // stray chair in the aisle
  props.push(place(P.suitcase(), 0.7 + j(0.6), -0.4 + j(0.6), 0.3)); // someone's black suitcase (weak return)
  props.push(place(P.plant(), -3.5, -3.5)); props.push(place(P.plant(), 3.5, 3.4));
  const bt = P.bottle(); bt.position.set(1.0, 1.1, -3.0); props.push(bt);
  // A customer carrying a tray crosses the aisle
  const cust = P.person({ shirt: 0x8a6a3a }); props.push(cust);
  actors.push(walker(cust, [[-2.8, -2.2], [0.0, -1.8], [2.6, 0.2]], 0.9, { loop: true, pingpong: true, pause: 2.0 }));
  const rail = [[0.0, 3.3], [0.0, 2.2], [-0.2, 1.0], [0.1, -0.2], [0.0, -1.4], [0.0, -2.3]];
  return {
    id: "cafe", title: "The coffee shop", props, actors, rail,
    start: { x: 0.0, z: 3.4, yaw: 0 },
    goal: { x: 0.0, z: -2.3, r: 0.7 },
    bounds: { minX: -3.8, maxX: 3.8, minZ: -2.4, maxZ: 3.8 },
    light: "indoor",
    beats: ["Stray chair in the aisle", "Black suitcase: weak laser return, vision fallback", "Customer crossing with a tray", "Menu board to read at the counter"],
  };
}

export const SCENES = { home, street, cafe };
export const ORDER = ["home", "street", "cafe"];

// ----------------------------------------------------------------------------- actors

/** Walks obj along waypoints at speed m/s. Options: loop, pingpong, pause (s at each point), phase (s). */
function walker(obj, pts, speed, { loop = true, pingpong = false, pause = 0, phase = 0 } = {}) {
  const segs = []; let total = 0;
  const seq = pingpong ? [...pts, ...pts.slice(1, -1).reverse()] : pts;
  for (let i = 0; i < seq.length; i++) {
    const a = seq[i], b = seq[(i + 1) % seq.length];
    if (!loop && i === seq.length - 1) break;
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    segs.push({ a, b, len, t0: total, dur: len / speed + pause });
    total += len / speed + pause;
  }
  obj.position.set(pts[0][0], 0, pts[0][1]);
  return {
    obj, update(t) {
      let u = (t + phase) % total; if (u < 0) u += total;
      const s = segs.find(s => u >= s.t0 && u < s.t0 + s.dur) || segs[segs.length - 1];
      const k = Math.min(1, Math.max(0, (u - s.t0 - pause) / (s.len / speed)));
      const x = s.a[0] + (s.b[0] - s.a[0]) * k, z = s.a[1] + (s.b[1] - s.a[1]) * k;
      obj.position.set(x, 0, z);
      if (s.len > 0.01) obj.rotation.y = Math.atan2(s.b[0] - s.a[0], s.b[1] - s.a[1]);
      obj.userData.velocity = k > 0 && k < 1 ? speed : 0;
    },
  };
}

/** Crosses from `from` to `to` at speed every `period` seconds, parked out of sight otherwise. */
function crosser(obj, from, to, speed, period) {
  const len = Math.hypot(to[0] - from[0], to[1] - from[1]); const dur = len / speed;
  obj.rotation.y = Math.atan2(to[0] - from[0], to[1] - from[1]);
  return {
    obj, update(t) {
      const u = t % period;
      if (u > dur) { obj.position.set(from[0], -5, from[1]); obj.visible = false; return; }  // parked below the floor
      obj.visible = true; const k = u / dur;
      obj.position.set(from[0] + (to[0] - from[0]) * k, 0, from[1] + (to[1] - from[1]) * k);
      obj.userData.velocity = speed;
    },
  };
}
