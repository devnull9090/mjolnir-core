// Routes on a map's navmesh (`mjolnir level navmesh`, crates/blam-cli/src/
// level_navmesh.rs): the AI pathfinding the bake builds, as convex areas
// ("sectors") and the doorways between them. World units throughout, as the
// simulation has them.
//
//   const mesh = Navmesh.load(json)
//   mesh.locate([x, y, z])            the area a point stands in, or -1
//   mesh.route(from, to)              { points, sectors } or null
//   mesh.block([x, y], radius)         keep routes out of the areas a round
//                                     obstacle stands on
//   mesh.firstWall(p, q, z, clear)     the nearest wall within `clear` of the
//                                     line p -> q at a walker's height
//   mesh.wallsAlong(p, q, z, clear)    all of them
//
// `walls` are the sides of collision standing in walkable areas (trees,
// rocks), as the exporter found them: plan ends and a height range.
//
// An area is blocked when the exporter found a wall standing in it, or when
// block() puts an obstacle over it. Routes go around blocked areas; one that
// would have to cross one (the start or the goal is in one, or nothing else
// joins) is planned again over the whole mesh.
//
// A route is A* over the areas through their doorways, pulled tight with a
// funnel, so it runs straight across open ground and turns only at corners.

const CELL = 2; // the grid's cell, wu
// A point stands on an area at or below it, within this much (a player's
// position is ~0.6 wu above their floor; the bake's own lookup allows 0.25).
const ABOVE = 0.25;
const BELOW = 1.2;

function cross(ax, ay, bx, by) {
  return ax * by - ay * bx;
}

/** z of the plane through triangle (a, b, c) at (x, y), or null outside it. */
function triangleZ(a, b, c, x, y) {
  const d = cross(b[0] - a[0], b[1] - a[1], c[0] - a[0], c[1] - a[1]);
  if (Math.abs(d) < 1e-9) return null;
  const u = cross(x - a[0], y - a[1], c[0] - a[0], c[1] - a[1]) / d;
  const v = cross(b[0] - a[0], b[1] - a[1], x - a[0], y - a[1]) / d;
  const eps = 1e-6;
  if (u < -eps || v < -eps || u + v > 1 + eps) return null;
  return a[2] + u * (b[2] - a[2]) + v * (c[2] - a[2]);
}

/** Plan distance from point p to polygon `ring` (0 inside it). */
function distanceToPolygon(ring, p) {
  let inside = true;
  let best = Infinity;
  for (let i = 0; i < ring.length; i++) {
    const a = ring[i];
    const b = ring[(i + 1) % ring.length];
    if (cross(b[0] - a[0], b[1] - a[1], p[0] - a[0], p[1] - a[1]) < 0) inside = false;
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
    best = Math.min(best, Math.hypot(a[0] + t * dx - p[0], a[1] + t * dy - p[1]));
  }
  return inside ? 0 : best;
}

/** Closest approach of plan segments p-q and a-b: the distance, and how far
 *  along p-q (from p) it happens. */
export function segmentDistance(p, q, a, b) {
  const pointTo = (o, s, e) => {
    const dx = e[0] - s[0];
    const dy = e[1] - s[1];
    const t = Math.max(0, Math.min(1, ((o[0] - s[0]) * dx + (o[1] - s[1]) * dy) / (dx * dx + dy * dy || 1)));
    return { d: Math.hypot(s[0] + t * dx - o[0], s[1] + t * dy - o[1]), t };
  };
  const length = Math.hypot(q[0] - p[0], q[1] - p[1]);
  const d1 = cross(q[0] - p[0], q[1] - p[1], a[0] - p[0], a[1] - p[1]);
  const d2 = cross(q[0] - p[0], q[1] - p[1], b[0] - p[0], b[1] - p[1]);
  const d3 = cross(b[0] - a[0], b[1] - a[1], p[0] - a[0], p[1] - a[1]);
  const d4 = cross(b[0] - a[0], b[1] - a[1], q[0] - a[0], q[1] - a[1]);
  if (d1 * d2 < 0 && d3 * d4 < 0) {
    const t = d3 / (d3 - d4);
    return { distance: 0, along: t * length };
  }
  const ca = pointTo(a, p, q);
  const cb = pointTo(b, p, q);
  const cp = pointTo(p, a, b);
  const cq = pointTo(q, a, b);
  const options = [
    { distance: ca.d, along: ca.t * length },
    { distance: cb.d, along: cb.t * length },
    { distance: cp.d, along: 0 },
    { distance: cq.d, along: length },
  ];
  return options.reduce((m, o) => (o.distance < m.distance ? o : m));
}

export class Navmesh {
  constructor(data) {
    if (data.version !== 1) throw new Error(`navmesh version ${data.version}`);
    this.sectors = data.sectors.map((s, i) => {
      const xs = s.ring.map((p) => p[0]);
      const ys = s.ring.map((p) => p[1]);
      const n = s.ring.length;
      const center = [0, 0, 0];
      for (const p of s.ring) for (let k = 0; k < 3; k++) center[k] += p[k] / n;
      return {
        index: i, ring: s.ring, floor: s.floor, component: s.component, center, blocked: Boolean(s.blocked),
        box: [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)],
      };
    });
    this.main = data.main_component;
    // Doorways both ways, each with its left and right ends as seen walking
    // through it. A link's v1 -> v2 runs around its left sector (the bake's
    // rings are counter-clockwise), so leaving that sector v2 is on the left.
    this.next = this.sectors.map(() => []);
    for (const [a, b, v1, v2] of data.doors) {
      this.next[a].push({ to: b, left: v2, right: v1 });
      this.next[b].push({ to: a, left: v1, right: v2 });
    }
    this.walls = (data.walls ?? []).map((w) => ({ a: [w[0], w[1]], b: [w[2], w[3]], lo: w[4], hi: w[5] }));
    this.wallGrid = new Map();
    this.walls.forEach((w, i) => {
      for (let gx = Math.floor(Math.min(w.a[0], w.b[0]) / CELL); gx <= Math.floor(Math.max(w.a[0], w.b[0]) / CELL); gx++) {
        for (let gy = Math.floor(Math.min(w.a[1], w.b[1]) / CELL); gy <= Math.floor(Math.max(w.a[1], w.b[1]) / CELL); gy++) {
          const key = `${gx},${gy}`;
          if (!this.wallGrid.has(key)) this.wallGrid.set(key, []);
          this.wallGrid.get(key).push(i);
        }
      }
    });
    this.grid = new Map();
    for (const s of this.sectors) {
      for (let gx = Math.floor(s.box[0] / CELL); gx <= Math.floor(s.box[2] / CELL); gx++) {
        for (let gy = Math.floor(s.box[1] / CELL); gy <= Math.floor(s.box[3] / CELL); gy++) {
          const key = `${gx},${gy}`;
          if (!this.grid.has(key)) this.grid.set(key, []);
          this.grid.get(key).push(s.index);
        }
      }
    }
  }

  static load(json) {
    return new Navmesh(typeof json === "string" ? JSON.parse(json) : json);
  }

  /** z of sector `s`'s surface at (x, y), or null if (x, y) is not over it. */
  surfaceZ(s, x, y) {
    const r = this.sectors[s].ring;
    for (let i = 1; i + 1 < r.length; i++) {
      const z = triangleZ(r[0], r[i], r[i + 1], x, y);
      if (z !== null) return z;
    }
    return null;
  }

  /** The area point p stands in: the highest surface under it within reach,
   *  else the nearest area's center within 2 wu; -1 for none. */
  locate(p) {
    const cell = this.grid.get(`${Math.floor(p[0] / CELL)},${Math.floor(p[1] / CELL)}`) ?? [];
    let best = -1;
    let bestZ = -Infinity;
    for (const s of cell) {
      const z = this.surfaceZ(s, p[0], p[1]);
      if (z !== null && z <= p[2] + ABOVE && z >= p[2] - BELOW && z > bestZ) {
        best = s;
        bestZ = z;
      }
    }
    if (best >= 0) return best;
    // Off the mesh in plan (a crack, a corner cut close): the nearest area
    // within reach, never one overhead.
    let nearest = Infinity;
    for (const s of cell) {
      if (this.surfaceZ(s, p[0], p[1]) !== null) continue;
      const c = this.sectors[s].center;
      if (c[2] > p[2] + ABOVE || c[2] < p[2] - BELOW) continue;
      const d = Math.hypot(c[0] - p[0], c[1] - p[1], (c[2] - p[2]) * 2);
      if (d < nearest && d < 2) {
        nearest = d;
        best = s;
      }
    }
    return best;
  }

  /** Blocks every area within `radius` of plan point `at` (wu). Returns how many. */
  block(at, radius) {
    let n = 0;
    for (let gx = Math.floor((at[0] - radius) / CELL); gx <= Math.floor((at[0] + radius) / CELL); gx++) {
      for (let gy = Math.floor((at[1] - radius) / CELL); gy <= Math.floor((at[1] + radius) / CELL); gy++) {
        for (const s of this.grid.get(`${gx},${gy}`) ?? []) {
          const sector = this.sectors[s];
          if (sector.blocked) continue;
          if (distanceToPolygon(sector.ring, at) <= radius) {
            sector.blocked = true;
            n++;
          }
        }
      }
    }
    return n;
  }

  /** The wall nearest along p -> q (plan) that comes within `clear` of the
   *  line and stands between `z + 0.12` and `z + 0.6` (a walker's body, z
   *  its feet): { wall, along }, or null when the line is clear. */
  firstWall(p, q, z, clear) {
    const all = this.wallsAlong(p, q, z, clear);
    return all.length ? all.reduce((m, w) => (w.along < m.along ? w : m)) : null;
  }

  /** Every wall within `clear` of p -> q at a walker's height, as
   *  { wall, along, distance }. */
  wallsAlong(p, q, z, clear) {
    const dx = q[0] - p[0];
    const dy = q[1] - p[1];
    const length = Math.hypot(dx, dy);
    if (length < 1e-6) return null;
    const seen = new Set();
    const found = [];
    const x0 = Math.floor((Math.min(p[0], q[0]) - clear) / CELL);
    const x1 = Math.floor((Math.max(p[0], q[0]) + clear) / CELL);
    const y0 = Math.floor((Math.min(p[1], q[1]) - clear) / CELL);
    const y1 = Math.floor((Math.max(p[1], q[1]) + clear) / CELL);
    for (let gx = x0; gx <= x1; gx++) {
      for (let gy = y0; gy <= y1; gy++) {
        for (const i of this.wallGrid.get(`${gx},${gy}`) ?? []) {
          if (seen.has(i)) continue;
          seen.add(i);
          const w = this.walls[i];
          if (w.hi < z + 0.12 || w.lo > z + 0.6) continue;
          const d = segmentDistance(p, q, w.a, w.b);
          if (d.distance >= clear) continue;
          found.push({ wall: w, along: d.along, distance: d.distance });
        }
      }
    }
    return found;
  }

  /** The areas from `start` to `goal` (A*, through doorway midpoints), or null. */
  sectorPath(start, goal, from, to, avoid = true) {
    if (start < 0 || goal < 0) return null;
    if (start === goal) return { sectors: [start], doors: [] };
    const g = new Map([[start, 0]]);
    const at = new Map([[start, from]]);
    const came = new Map();
    const open = [[Math.hypot(to[0] - from[0], to[1] - from[1], to[2] - from[2]), start]];
    const done = new Set();
    while (open.length) {
      // A binary heap would be faster; a few thousand areas do not need one.
      let bi = 0;
      for (let i = 1; i < open.length; i++) if (open[i][0] < open[bi][0]) bi = i;
      const [, s] = open[bi];
      open[bi] = open[open.length - 1];
      open.pop();
      if (done.has(s)) continue;
      done.add(s);
      if (s === goal) break;
      const p = at.get(s);
      for (const door of this.next[s]) {
        if (done.has(door.to)) continue;
        if (avoid && this.sectors[door.to].blocked && door.to !== goal) continue;
        const m = [0, 1, 2].map((k) => (door.left[k] + door.right[k]) / 2);
        const cost = g.get(s) + Math.hypot(m[0] - p[0], m[1] - p[1], m[2] - p[2]);
        if (cost < (g.get(door.to) ?? Infinity)) {
          g.set(door.to, cost);
          at.set(door.to, m);
          came.set(door.to, { from: s, door });
          open.push([cost + Math.hypot(to[0] - m[0], to[1] - m[1], to[2] - m[2]), door.to]);
        }
      }
    }
    if (!came.has(goal)) return null;
    const sectors = [goal];
    const doors = [];
    for (let s = goal; s !== start; ) {
      const step = came.get(s);
      doors.unshift(step.door);
      s = step.from;
      sectors.unshift(s);
    }
    return { sectors, doors };
  }

  /** A route from `from` to `to`: corner points pulled tight through the
   *  doorways (the simple stupid funnel), ending at `to`; null if none. */
  route(from, to) {
    const start = this.locate(from);
    const goal = this.locate(to);
    const path = this.sectorPath(start, goal, from, to, true) ?? this.sectorPath(start, goal, from, to, false);
    if (!path) return null;
    const portals = [{ left: from, right: from }, ...path.doors, { left: to, right: to }];
    const points = [];
    let apex = from;
    let left = portals[0].left;
    let right = portals[0].right;
    let li = 0;
    let ri = 0;
    const area = (a, b, c) => cross(b[0] - a[0], b[1] - a[1], c[0] - a[0], c[1] - a[1]);
    const same = (a, b) => Math.abs(a[0] - b[0]) < 1e-6 && Math.abs(a[1] - b[1]) < 1e-6;
    for (let i = 1; i < portals.length; i++) {
      const pl = portals[i].left;
      const pr = portals[i].right;
      // Tighten the right side: pr must not be right of `right`.
      if (area(apex, right, pr) >= 0) {
        if (same(apex, right) || area(apex, left, pr) < 0) {
          right = pr;
          ri = i;
        } else {
          points.push(left);
          apex = left;
          i = li;
          left = apex;
          right = apex;
          ri = li;
          continue;
        }
      }
      if (area(apex, left, pl) <= 0) {
        if (same(apex, left) || area(apex, right, pl) > 0) {
          left = pl;
          li = i;
        } else {
          points.push(right);
          apex = right;
          i = ri;
          left = apex;
          right = apex;
          li = ri;
          continue;
        }
      }
    }
    points.push(to);
    const tight = points.filter((p, i) => i === 0 || !same(p, points[i - 1]));
    if (tight.length > 1 && same(tight[0], from)) tight.shift();
    return { points: tight, sectors: path.sectors };
  }
}
