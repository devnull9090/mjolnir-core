//! Walkable ground on instanced geometry, as input for
//! [`crate::pathfinding::Pathfinding::build`].
//!
//! The pathfinding builder makes one sector per walkable collision surface of
//! a welded shell. A map whose ground is instanced geometry (every shipped
//! campaign BSP, and any large converted terrain) is neither welded nor small:
//! Pelican Warfare's ground is 1.2 million triangles that share no edge. This
//! module turns such a triangle soup into a welded [`Collision`] whose walkable
//! surfaces are **convex polygons merged from whole triangles**, so the same
//! builder, with its steps and crack seams, yields sectors a 16-bit link index
//! can hold. docs/engine_ai_pathfinding.md says how the simulation reads them.
//!
//! What it does, in order:
//!
//! 1. **Weld** each object's polygons by position (objects stay apart: the
//!    simulation's own data lays sectors out object after object and joins
//!    them with intersection links, which the builder's crack seams write).
//! 2. **Choose floors**: not breakable, no steeper than the walkable slope,
//!    accepted by the caller's filter (deep water, say), and part of a
//!    connected patch of at least [`Options::min_island_area`] (a rock's top
//!    is not worth a sector).
//! 3. **Merge** floors that share an edge while the union stays convex in
//!    plan, within [`Options::plane_tolerance`] of one plane, no steeper than
//!    walkable and no longer than [`Options::max_ring`] corners. Shipped
//!    sectors stray from a plane by 0.2 wu at the 99th percentile and 0.01 at
//!    the median (`examples/pf_stats.rs`).
//! 4. **Drop corners** that lie on a straight run between the same two
//!    neighbours, so a long shared border is one link, not one per triangle.
//!
//! A sector is always a union of whole source polygons, so every source
//! surface names one sector (or none) and no `bsp2d nodes` are needed.
use crate::ce::{Collision, Edge, Plane, Surface, Vertex};
use crate::pathfinding::{Pathfinding, WALKABLE_NZ};
use std::collections::HashMap;

/// One source collision polygon, in world space.
#[derive(Debug, Clone)]
pub struct Polygon {
    /// The pathfinding object it belongs to (an instance, say).
    pub object: u32,
    /// Its surface index in that object's collision.
    pub surface: u32,
    /// Its corners, counter-clockwise seen from outside.
    pub ring: Vec<[f32; 3]>,
    /// A surface that can break under an AI: never a floor.
    pub breakable: bool,
}

#[derive(Debug, Clone, Copy)]
pub struct Options {
    /// Points of one object closer than this are one vertex.
    pub weld: f32,
    /// How far a merged floor's points may lie from its plane.
    pub plane_tolerance: f32,
    /// The most corners a merged floor may have, not counting those on a
    /// straight run.
    pub max_ring: usize,
    /// Connected floor smaller than this (wu^2) is left out.
    pub min_island_area: f32,
    /// How far a merged floor's corner may lie inside its convex hull, in
    /// plan: 0 keeps every floor convex.
    pub dent: f32,
    /// How far the border between two merged floors may move in plan when
    /// its corners are dropped: 0 drops only corners that are in line.
    pub border: f32,
    /// How far apart in height two floors' edges may be and still be joined
    /// by a seam.
    pub seam_step: f32,
}

impl Default for Options {
    fn default() -> Self {
        Options {
            weld: 0.002,
            plane_tolerance: 0.2,
            max_ring: 16,
            min_island_area: 0.0,
            dent: 0.0,
            border: 0.0,
            seam_step: crate::pathfinding::STEP_HEIGHT,
        }
    }
}

/// The surface flag the pathfinding builder never walks (`breakable`): how a
/// floor that was filtered out is kept out.
const NOT_FLOOR: u8 = 0x8;

#[derive(Debug, Default)]
pub struct Mesh {
    /// Welded collision: merged floors and every other source polygon.
    pub collision: Collision,
    /// For each collision surface, the source polygons it stands for.
    pub members: Vec<Vec<u32>>,
    /// For each source polygon, its collision surface (none: degenerate).
    pub surface_of: Vec<Option<u32>>,
    /// Source polygons that were floors before islands were dropped.
    pub floors: usize,
    /// Floors left out as part of a small island.
    pub island_floors: usize,
    /// Merged floors.
    pub merged: usize,
    /// Corners dropped from straight runs.
    pub corners_dropped: usize,
    pub blocked: Blocked,
}

fn sub(a: [f32; 3], b: [f32; 3]) -> [f64; 3] {
    [0, 1, 2].map(|k| a[k] as f64 - b[k] as f64)
}

/// Newell's normal (unnormalised: twice the area) and the centroid of a ring.
fn newell(points: &[[f32; 3]], ring: &[u32]) -> ([f64; 3], [f64; 3]) {
    let (mut n, mut c) = ([0f64; 3], [0f64; 3]);
    for i in 0..ring.len() {
        let (p, q) = (points[ring[i] as usize], points[ring[(i + 1) % ring.len()] as usize]);
        n[0] += (p[1] as f64 - q[1] as f64) * (p[2] as f64 + q[2] as f64);
        n[1] += (p[2] as f64 - q[2] as f64) * (p[0] as f64 + q[0] as f64);
        n[2] += (p[0] as f64 - q[0] as f64) * (p[1] as f64 + q[1] as f64);
        for k in 0..3 {
            c[k] += p[k] as f64 / ring.len() as f64;
        }
    }
    (n, c)
}

fn unit(n: [f64; 3]) -> Option<[f64; 3]> {
    let len = (n[0] * n[0] + n[1] * n[1] + n[2] * n[2]).sqrt();
    (len > 1e-12).then(|| n.map(|x| x / len))
}

/// How many corners of a ring turn left in plan, when none turns right:
/// none for a ring that is not convex.
fn corners(points: &[[f32; 3]], ring: &[u32]) -> Option<usize> {
    let n = ring.len();
    let mut turns = 0;
    for i in 0..n {
        let p = points[ring[i] as usize];
        let q = points[ring[(i + 1) % n] as usize];
        let r = points[ring[(i + 2) % n] as usize];
        let (ax, ay) = ((q[0] - p[0]) as f64, (q[1] - p[1]) as f64);
        let (bx, by) = ((r[0] - q[0]) as f64, (r[1] - q[1]) as f64);
        let (la, lb) = ((ax * ax + ay * ay).sqrt(), (bx * bx + by * by).sqrt());
        if la < 1e-9 || lb < 1e-9 {
            return None;
        }
        // The sine of the turn: a right turn of more than ~0.06 degrees fails,
        // and less than that either way is a straight run.
        let sine = (ax * by - ay * bx) / (la * lb);
        if sine < -1e-3 {
            return None;
        }
        if sine > 1e-3 {
            turns += 1;
        }
    }
    Some(turns)
}

fn convex(points: &[[f32; 3]], ring: &[u32]) -> bool {
    corners(points, ring).is_some()
}

/// [`corners`] for a ring that may dent inward by up to `dent` wu: the corners
/// of its convex hull in plan, when the ring winds counter-clockwise once
/// round the hull's middle and no corner lies further than `dent` inside the
/// hull. Shipped sectors dent too (about one in twelve on A30's largest BSP).
fn near_convex(points: &[[f32; 3]], ring: &[u32], dent: f64) -> Option<usize> {
    if let Some(turns) = corners(points, ring) {
        return Some(turns);
    }
    if dent <= 0.0 {
        return None;
    }
    let at = |v: u32| (points[v as usize][0] as f64, points[v as usize][1] as f64);
    let cross = |o: (f64, f64), a: (f64, f64), b: (f64, f64)| (a.0 - o.0) * (b.1 - o.1) - (a.1 - o.1) * (b.0 - o.0);
    // The hull, counter-clockwise (Andrew's monotone chain).
    let mut sorted: Vec<(f64, f64)> = ring.iter().map(|&v| at(v)).collect();
    sorted.sort_by(|a, b| a.0.total_cmp(&b.0).then(a.1.total_cmp(&b.1)));
    let mut hull: Vec<(f64, f64)> = Vec::with_capacity(sorted.len() + 1);
    for pass in 0..2 {
        let start = hull.len();
        let list: Box<dyn Iterator<Item = &(f64, f64)>> =
            if pass == 0 { Box::new(sorted.iter()) } else { Box::new(sorted.iter().rev()) };
        for &p in list {
            while hull.len() >= start + 2 && cross(hull[hull.len() - 2], hull[hull.len() - 1], p) <= 0.0 {
                hull.pop();
            }
            hull.push(p);
        }
        hull.pop();
    }
    if hull.len() < 3 {
        return None;
    }
    // Every corner on the hull or within `dent` of its edge.
    for &v in ring {
        let p = at(v);
        let mut nearest = f64::MAX;
        for i in 0..hull.len() {
            let (a, b) = (hull[i], hull[(i + 1) % hull.len()]);
            let (dx, dy) = (b.0 - a.0, b.1 - a.1);
            let t = (((p.0 - a.0) * dx + (p.1 - a.1) * dy) / (dx * dx + dy * dy).max(1e-18)).clamp(0.0, 1.0);
            let (ex, ey) = (p.0 - (a.0 + dx * t), p.1 - (a.1 + dy * t));
            nearest = nearest.min((ex * ex + ey * ey).sqrt());
        }
        if nearest > dent {
            return None;
        }
    }
    // Once round the hull's middle, always counter-clockwise.
    let n = hull.len() as f64;
    let mid = hull.iter().fold((0.0, 0.0), |m, p| (m.0 + p.0 / n, m.1 + p.1 / n));
    let mut turned = 0.0;
    for i in 0..ring.len() {
        let (a, b) = (at(ring[i]), at(ring[(i + 1) % ring.len()]));
        let step = cross(mid, a, b).atan2((a.0 - mid.0) * (b.0 - mid.0) + (a.1 - mid.1) * (b.1 - mid.1));
        if step < -1e-6 {
            return None;
        }
        turned += step;
    }
    ((turned - std::f64::consts::TAU).abs() < 1e-3).then_some(hull.len())
}

/// A floor while it merges.
#[derive(Default)]
struct Floor {
    ring: Vec<u32>,
    /// Source polygons.
    members: Vec<u32>,
    /// Every welded vertex of its members, for the plane test.
    points: Vec<u32>,
    alive: bool,
}

struct Merger<'a> {
    points: &'a [[f32; 3]],
    floors: Vec<Floor>,
    /// Directed edge (a, b) -> the floor whose ring runs a to b.
    edge: HashMap<(u32, u32), u32>,
    max_ring: usize,
    dent: f64,
    /// Why unions were turned down in the current sweep.
    blocked: std::cell::Cell<Blocked>,
}

/// Why neighbouring floors stayed apart, counted over the last sweep (the one
/// that merged nothing): what a tuning pass should look at.
#[derive(Debug, Default, Clone, Copy)]
pub struct Blocked {
    /// They meet along more than one run of edges (a hole would open).
    pub runs: usize,
    /// The union is not convex enough, or has too many corners.
    pub shape: usize,
    /// The union is steeper than walkable.
    pub slope: usize,
    /// A point lies further from the union's plane than the tolerance.
    pub plane: usize,
}

impl Merger<'_> {
    fn block(&self, f: impl Fn(&mut Blocked)) {
        let mut b = self.blocked.get();
        f(&mut b);
        self.blocked.set(b);
    }

    /// The union of floors `a` and `b` across the edge `u -> v` of `a`, when
    /// they meet along one unbroken run of edges and the union is a convex
    /// floor within `tolerance` of a plane.
    fn union(&self, a: u32, b: u32, u: u32, tolerance: f64) -> Option<Vec<u32>> {
        let (ra, rb) = (&self.floors[a as usize].ring, &self.floors[b as usize].ring);
        let n = ra.len();
        let shared = |i: usize| self.edge.get(&(ra[(i + 1) % n], ra[i])) == Some(&b);
        let total = (0..n).filter(|&i| shared(i)).count();
        if total == 0 || total == n {
            return None;
        }
        // The run of shared edges through u: edges `start .. start + run`.
        let at = ra.iter().position(|&x| x == u)?;
        if !shared(at) {
            return None;
        }
        let mut start = at;
        while shared((start + n - 1) % n) {
            start = (start + n - 1) % n;
        }
        let mut run = 0;
        while shared((start + run) % n) {
            run += 1;
        }
        if run != total {
            self.block(|b| b.runs += 1);
            return None;
        }
        // a's ring from the run's end round to its start, then b's corners
        // strictly between.
        let (first, last) = (ra[start], ra[(start + run) % n]);
        let mut ring: Vec<u32> = (0..=n - run).map(|k| ra[(start + run + k) % n]).collect();
        let m = rb.len();
        let from = rb.iter().position(|&x| x == first)?;
        for k in 1..m {
            let x = rb[(from + k) % m];
            if x == last {
                break;
            }
            ring.push(x);
        }
        // The corners of straight runs go later, so they do not count.
        if ring.len() < 3 || ring.len() > 250 {
            return None;
        }
        let mut seen = ring.clone();
        seen.sort_unstable();
        if seen.windows(2).any(|w| w[0] == w[1]) {
            self.block(|b| b.runs += 1);
            return None;
        }
        if near_convex(self.points, &ring, self.dent).is_none_or(|corners| corners > self.max_ring) {
            self.block(|b| b.shape += 1);
            return None;
        }
        let (normal, centre) = newell(self.points, &ring);
        let normal = unit(normal)?;
        if normal[2] < WALKABLE_NZ as f64 {
            self.block(|b| b.slope += 1);
            return None;
        }
        let far = |list: &[u32]| {
            list.iter().any(|&v| {
                let d = sub(self.points[v as usize], [0.0; 3]);
                ((d[0] - centre[0]) * normal[0] + (d[1] - centre[1]) * normal[1] + (d[2] - centre[2]) * normal[2]).abs()
                    > tolerance
            })
        };
        if far(&self.floors[a as usize].points) || far(&self.floors[b as usize].points) {
            self.block(|b| b.plane += 1);
            return None;
        }
        Some(ring)
    }

    fn merge(&mut self, a: u32, b: u32, ring: Vec<u32>) {
        for f in [a, b] {
            let old = self.floors[f as usize].ring.clone();
            for i in 0..old.len() {
                self.edge.remove(&(old[i], old[(i + 1) % old.len()]));
            }
        }
        for i in 0..ring.len() {
            self.edge.insert((ring[i], ring[(i + 1) % ring.len()]), a);
        }
        let gone = std::mem::take(&mut self.floors[b as usize]);
        let keep = &mut self.floors[a as usize];
        keep.ring = ring;
        keep.members.extend(gone.members);
        keep.points.extend(gone.points);
        keep.points.sort_unstable();
        keep.points.dedup();
    }
}

/// Weld, choose and merge (the module docs say how). `walk` is the caller's
/// say on a polygon (by its index) that could be a floor.
pub fn merge(polygons: &[Polygon], walk: &dyn Fn(usize, &Polygon) -> bool, o: &Options) -> Mesh {
    // 1. Weld per object; `global` welds across objects, for islands only.
    let key = |p: [f32; 3]| [0, 1, 2].map(|k| (p[k] / o.weld).round() as i64);
    let mut points: Vec<[f32; 3]> = Vec::new();
    let mut own: HashMap<(u32, [i64; 3]), u32> = HashMap::new();
    let mut global: HashMap<[i64; 3], u32> = HashMap::new();
    let mut global_of: Vec<u32> = Vec::new();
    let mut rings: Vec<Vec<u32>> = Vec::with_capacity(polygons.len());
    for p in polygons {
        let mut ring: Vec<u32> = Vec::with_capacity(p.ring.len());
        for &x in &p.ring {
            let k = key(x);
            let v = *own.entry((p.object, k)).or_insert_with(|| {
                points.push(x);
                let next = global.len() as u32;
                global_of.push(*global.entry(k).or_insert(next));
                points.len() as u32 - 1
            });
            if ring.last() != Some(&v) {
                ring.push(v);
            }
        }
        while ring.len() > 1 && ring.first() == ring.last() {
            ring.pop();
        }
        let mut seen = ring.clone();
        seen.sort_unstable();
        if ring.len() < 3 || seen.windows(2).any(|w| w[0] == w[1]) {
            ring.clear();
        }
        rings.push(ring);
    }

    // 2. Floors, less the small islands.
    let area = |ring: &[u32]| {
        let (n, _) = newell(&points, ring);
        (n[0] * n[0] + n[1] * n[1] + n[2] * n[2]).sqrt() / 2.0
    };
    let mut floor: Vec<bool> = polygons
        .iter()
        .zip(&rings)
        .enumerate()
        .map(|(i, (p, ring))| {
            !ring.is_empty()
                && !p.breakable
                && unit(newell(&points, ring).0).is_some_and(|n| n[2] >= WALKABLE_NZ as f64)
                && convex(&points, ring)
                && walk(i, p)
        })
        .collect();
    let floor_count = floor.iter().filter(|&&f| f).count();
    let mut island_floors = 0;
    if o.min_island_area > 0.0 {
        let mut parent: Vec<u32> = (0..polygons.len() as u32).collect();
        fn find(p: &mut [u32], x: u32) -> u32 {
            let mut r = x;
            while p[r as usize] != r {
                r = p[r as usize];
            }
            let mut y = x;
            while p[y as usize] != r {
                let next = p[y as usize];
                p[y as usize] = r;
                y = next;
            }
            r
        }
        let mut first: HashMap<(u32, u32), u32> = HashMap::new();
        for (i, ring) in rings.iter().enumerate() {
            if !floor[i] {
                continue;
            }
            for k in 0..ring.len() {
                let (a, b) = (global_of[ring[k] as usize], global_of[ring[(k + 1) % ring.len()] as usize]);
                let e = (a.min(b), a.max(b));
                match first.get(&e) {
                    Some(&j) => {
                        let (x, y) = (find(&mut parent, i as u32), find(&mut parent, j));
                        if x != y {
                            parent[x as usize] = y;
                        }
                    }
                    None => {
                        first.insert(e, i as u32);
                    }
                }
            }
        }
        let mut total = vec![0f64; polygons.len()];
        for (i, ring) in rings.iter().enumerate() {
            if floor[i] {
                total[find(&mut parent, i as u32) as usize] += area(ring);
            }
        }
        for i in 0..polygons.len() {
            if floor[i] && total[find(&mut parent, i as u32) as usize] < o.min_island_area as f64 {
                floor[i] = false;
                island_floors += 1;
            }
        }
    }

    // 3. Merge. Each source floor starts as its own; an edge two floors run
    // opposite ways along is a candidate, longest first, in passes of rising
    // tolerance so the flattest unions form before the rougher ones.
    let mut merger = Merger { points: &points, floors: Vec::new(), edge: HashMap::new(), max_ring: o.max_ring, dent: o.dent as f64, blocked: Default::default() };
    let mut floor_of: Vec<Option<u32>> = vec![None; polygons.len()];
    // A directed edge two floors both claim (non-manifold) joins nothing.
    let mut twice: Vec<(u32, u32)> = Vec::new();
    for (i, ring) in rings.iter().enumerate() {
        if !floor[i] {
            continue;
        }
        let id = merger.floors.len() as u32;
        floor_of[i] = Some(id);
        merger.floors.push(Floor { ring: ring.clone(), members: vec![i as u32], points: ring.clone(), alive: true });
        for k in 0..ring.len() {
            let e = (ring[k], ring[(k + 1) % ring.len()]);
            if merger.edge.insert(e, id).is_some() {
                twice.push(e);
            }
        }
    }
    for e in twice {
        merger.edge.remove(&e);
    }
    let mut candidates: Vec<(f32, u32, u32)> = Vec::new();
    for f in &merger.floors {
        for k in 0..f.ring.len() {
            let (a, b) = (f.ring[k], f.ring[(k + 1) % f.ring.len()]);
            if a < b && merger.edge.contains_key(&(a, b)) && merger.edge.contains_key(&(b, a)) {
                let d = sub(points[a as usize], points[b as usize]);
                candidates.push(((d[0] * d[0] + d[1] * d[1] + d[2] * d[2]).sqrt() as f32, a, b));
            }
        }
    }
    candidates.sort_by(|x, y| y.0.total_cmp(&x.0).then(x.1.cmp(&y.1)).then(x.2.cmp(&y.2)));
    for pass in [0.125, 0.25, 0.5, 1.0] {
        let tolerance = o.plane_tolerance as f64 * pass;
        loop {
            let mut any = false;
            merger.blocked.set(Blocked::default());
            for &(_, u, v) in &candidates {
                let (Some(&a), Some(&b)) = (merger.edge.get(&(u, v)), merger.edge.get(&(v, u))) else {
                    continue;
                };
                if a == b {
                    continue;
                }
                if let Some(ring) = merger.union(a, b, u, tolerance) {
                    merger.merge(a, b, ring);
                    any = true;
                }
            }
            if !any {
                break;
            }
        }
    }
    let blocked = merger.blocked.get();
    let Merger { mut floors, .. } = merger;
    let merged_floors = floors.iter().filter(|f| f.alive).count();

    // The output polygons: each merged floor where its first member stood,
    // every other source polygon as it is.
    struct Out {
        ring: Vec<u32>,
        members: Vec<u32>,
        flags: u8,
        floor: bool,
    }
    let mut out: Vec<Out> = Vec::new();
    let mut surface_of: Vec<Option<u32>> = vec![None; polygons.len()];
    for (i, ring) in rings.iter().enumerate() {
        if ring.is_empty() {
            continue;
        }
        match floor_of[i] {
            Some(f) => {
                // A floor that merged away follows the one it joined.
                let f = &mut floors[f as usize];
                if f.alive {
                    f.alive = false;
                    for &m in &f.members {
                        surface_of[m as usize] = Some(out.len() as u32);
                    }
                    out.push(Out { ring: std::mem::take(&mut f.ring), members: std::mem::take(&mut f.members), flags: 0, floor: true });
                }
            }
            None => {
                surface_of[i] = Some(out.len() as u32);
                // A would-be floor that was filtered out must not be walked.
                let level = unit(newell(&points, ring).0).is_some_and(|n| n[2] >= WALKABLE_NZ as f64);
                let flags = if polygons[i].breakable || level { NOT_FLOOR } else { 0 };
                out.push(Out { ring: ring.clone(), members: vec![i as u32], flags, floor: false });
            }
        }
    }

    // 4. Drop the corners of straight runs: a vertex only two polygons (or
    // one) touch, between the same two neighbours in both, in line in plan
    // and within the plane tolerance in height. Between two floors "in line"
    // is within `border`: the border moves by no more than that, measured
    // against every corner the stretch has lost, and both floors must keep
    // their shape.
    let mut touch = vec![0u32; points.len()];
    let mut edge: HashMap<(u32, u32), u32> = HashMap::new();
    let mut twice = Vec::new();
    for (s, p) in out.iter().enumerate() {
        for k in 0..p.ring.len() {
            touch[p.ring[k] as usize] += 1;
            let e = (p.ring[k], p.ring[(k + 1) % p.ring.len()]);
            if edge.insert(e, s as u32).is_some() {
                twice.push(e);
            }
        }
    }
    let twice: std::collections::HashSet<(u32, u32)> = twice.into_iter().collect();
    // The corners each stretch (keyed low vertex first) has already lost.
    let mut lost: HashMap<(u32, u32), Vec<u32>> = HashMap::new();
    let stretch = |a: u32, b: u32| (a.min(b), a.max(b));
    let shape = (o.dent.max(o.border)) as f64;
    let mut corners_dropped = 0;
    for s in 0..out.len() {
        if !out[s].floor || out[s].members.len() < 2 {
            continue;
        }
        let mut k = 0;
        while k < out[s].ring.len() && out[s].ring.len() > 3 {
            let n = out[s].ring.len();
            let (u, v, w) = (out[s].ring[(k + n - 1) % n], out[s].ring[k], out[s].ring[(k + 1) % n]);
            k += 1;
            let across = (edge.get(&(v, u)).copied(), edge.get(&(w, v)).copied());
            let other = match across {
                (None, None) if touch[v as usize] == 1 => None,
                (Some(x), Some(y)) if x == y && x != s as u32 && touch[v as usize] == 2 && out[x as usize].ring.len() > 3 => Some(x),
                _ => continue,
            };
            if [(u, v), (v, w), (v, u), (w, v)].iter().any(|e| twice.contains(e)) || edge.contains_key(&(u, w)) || edge.contains_key(&(w, u)) {
                continue;
            }
            let loose = other.is_some_and(|x| out[x as usize].floor) && o.border > 0.002;
            let limit = if loose { o.border as f64 } else { 0.002 };
            let (pu, pw) = (points[u as usize], points[w as usize]);
            let (dx, dy) = ((pw[0] - pu[0]) as f64, (pw[1] - pu[1]) as f64);
            let len = (dx * dx + dy * dy).sqrt();
            if len < 1e-9 {
                continue;
            }
            let mut gone: Vec<u32> = lost.get(&stretch(u, v)).cloned().unwrap_or_default();
            gone.push(v);
            gone.extend(lost.get(&stretch(v, w)).into_iter().flatten());
            let fits = gone.iter().all(|&q| {
                let pq = points[q as usize];
                let t = ((pq[0] - pu[0]) as f64 * dx + (pq[1] - pu[1]) as f64 * dy) / (len * len);
                let off = (((pq[0] - pu[0]) as f64) * dy - ((pq[1] - pu[1]) as f64) * dx).abs() / len;
                let dz = (pu[2] as f64 + (pw[2] - pu[2]) as f64 * t - pq[2] as f64).abs();
                (0.0..=1.0).contains(&t) && off <= limit && dz <= o.plane_tolerance as f64
            });
            if !fits {
                continue;
            }
            let without = |ring: &[u32]| -> Vec<u32> { ring.iter().copied().filter(|&q| q != v).collect() };
            let mine = without(&out[s].ring);
            let theirs = other.map(|x| without(&out[x as usize].ring));
            if loose
                && (near_convex(&points, &mine, shape).is_none()
                    || theirs.as_ref().is_some_and(|r| near_convex(&points, r, shape).is_none()))
            {
                continue;
            }
            out[s].ring = mine;
            edge.remove(&(u, v));
            edge.remove(&(v, w));
            edge.insert((u, w), s as u32);
            if let (Some(x), Some(ring)) = (other, theirs) {
                out[x as usize].ring = ring;
                edge.remove(&(w, v));
                edge.remove(&(v, u));
                edge.insert((w, u), x);
            }
            lost.remove(&stretch(u, v));
            lost.remove(&stretch(v, w));
            lost.insert(stretch(u, w), gone);
            touch[v as usize] = 0;
            corners_dropped += 1;
            // The corner before this one may now be in line too.
            k = k.saturating_sub(2);
        }
    }

    // The collision: used vertices, a plane per polygon, winged edges.
    let mut c = Collision::default();
    let mut vertex_of = vec![-1i32; points.len()];
    let mut edge_of: HashMap<(u32, u32), usize> = HashMap::new();
    let mut members = Vec::with_capacity(out.len());
    for (s, p) in out.into_iter().enumerate() {
        let (normal, centre) = newell(&points, &p.ring);
        let n = unit(normal).unwrap_or([0.0, 0.0, 1.0]).map(|x| x as f32);
        c.planes.push(Plane {
            n,
            d: n[0] * centre[0] as f32 + n[1] * centre[1] as f32 + n[2] * centre[2] as f32,
        });
        let ids: Vec<i32> = p
            .ring
            .iter()
            .map(|&v| {
                if vertex_of[v as usize] < 0 {
                    vertex_of[v as usize] = c.vertices.len() as i32;
                    c.vertices.push(Vertex { point: points[v as usize], first_edge: -1 });
                }
                vertex_of[v as usize]
            })
            .collect();
        let ring: Vec<usize> = (0..ids.len())
            .map(|i| {
                let (a, b) = (p.ring[i], p.ring[(i + 1) % ids.len()]);
                if let Some(e) = edge_of.remove(&(b, a)) {
                    c.edges[e].right = s as i32;
                    return e;
                }
                c.edges.push(Edge {
                    start: ids[i],
                    end: ids[(i + 1) % ids.len()],
                    forward: -1,
                    reverse: -1,
                    left: s as i32,
                    right: -1,
                });
                // A second polygon running the same way gets its own edge.
                edge_of.entry((a, b)).or_insert(c.edges.len() - 1);
                c.edges.len() - 1
            })
            .collect();
        for (i, &e) in ring.iter().enumerate() {
            let next = ring[(i + 1) % ring.len()] as i32;
            if c.edges[e].left == s as i32 {
                c.edges[e].forward = next;
            } else {
                c.edges[e].reverse = next;
            }
        }
        c.surfaces.push(Surface { plane: s as i32, first_edge: ring[0] as i32, flags: p.flags, breakable: -1, material: 0 });
        members.push(p.members);
    }
    Mesh { collision: c, members, surface_of, floors: floor_count, island_floors, merged: merged_floors, corners_dropped, blocked }
}

/// What [`cut_covered`] did.
#[derive(Debug, Default, Clone)]
pub struct Cut {
    /// Floors that lost some or all of their area.
    pub cut: usize,
    /// Of those, floors that were covered whole.
    pub gone: usize,
    /// The pieces the others were left as.
    pub pieces: usize,
    /// Plan area taken away, wu^2.
    pub area: f64,
    /// Corners added to neighbours so a cut edge still meets them.
    pub inserted: usize,
    /// For each polygon that came out, the polygon that went in.
    pub source: Vec<u32>,
    /// For each polygon that went in, whether it lost any floor.
    pub touched: Vec<bool>,
}

/// Where a floor has another floor less than `headroom` above it, nobody
/// stands on it: the upper one is the ground there. This takes the lower one
/// away. A pad laid on the terrain, the foot of a ramp, a trim strip on a
/// deck, a slab sunk into a slope: the lower floor is cut along the upper
/// one's outline, or along the line the two cross on, so both end on the same
/// line and a seam can join them ([`Options::seam_step`] is how far apart in
/// height they may be there). Of two floors in the same place, the one of the
/// smaller piece of ground goes. Shipped data joins separate pieces the same
/// way: its seams lie on both pieces' edges to within 0.005 wu.
///
/// The upper floor always wins because that rule cannot go round in a
/// circle: of any stack of floors, the top one stays.
///
/// Only floors of **different pieces of ground** act on each other: `piece`
/// names, for each polygon, the connected ground it is part of
/// ([`ground_pieces`]; `u32::MAX` for none, which is left alone). Ground that
/// is already one piece gains nothing from a cut, and a terrain made of
/// sheets that cross each other all over would be cut to ribbons.
///
/// The rule looks only at the geometry. A cut floor comes back as convex
/// pieces that keep its object and surface; a neighbour of the same object
/// gets the new corners that fall on its edges, so the pieces still share
/// whole edges with it.
pub fn cut_covered(polygons: &[Polygon], piece: &[u32], headroom: f32) -> (Vec<Polygon>, Cut) {
    type P = [f64; 3];
    const CELL: f64 = 4.0;
    // Closer than this, two floors are in the same place.
    const ABOVE: f64 = 0.002;
    const MIN_AREA: f64 = 1e-4;
    let plan_area = |r: &[P]| -> f64 {
        let mut twice = 0.0;
        for i in 0..r.len() {
            let (p, q) = (r[i], r[(i + 1) % r.len()]);
            twice += p[0] * q[1] - q[0] * p[1];
        }
        twice / 2.0
    };
    // The part of `r` where g = a x + b y + c is positive (or negative).
    let clip = |r: &[P], g: [f64; 3], positive: bool| -> Vec<P> {
        let sign = if positive { 1.0 } else { -1.0 };
        let at = |p: P| sign * (g[0] * p[0] + g[1] * p[1] + g[2]);
        let mut out = Vec::with_capacity(r.len() + 1);
        for i in 0..r.len() {
            let (p, q) = (r[i], r[(i + 1) % r.len()]);
            let (gp, gq) = (at(p), at(q));
            if gp >= 0.0 {
                out.push(p);
            }
            if (gp >= 0.0) != (gq >= 0.0) {
                // From the same end whichever side is kept, so both sides of
                // a cut get the same point.
                let (p, q, gp, gq) = if (gp >= 0.0) == positive { (p, q, gp, gq) } else { (q, p, -gq, -gp) };
                let t = gp.abs() / (gp.abs() + gq.abs());
                out.push([0, 1, 2].map(|k| p[k] + (q[k] - p[k]) * t));
            }
        }
        out
    };

    // The floors, with their plane as z = a x + b y + c.
    struct Floor {
        ring: Vec<P>,
        z: [f64; 3],
        lo: P,
        hi: P,
    }
    let floors: Vec<Option<Floor>> = polygons
        .iter()
        .enumerate()
        .map(|(i, p)| {
            if p.breakable || p.ring.len() < 3 || piece[i] == u32::MAX {
                return None;
            }
            let ids: Vec<u32> = (0..p.ring.len() as u32).collect();
            let (normal, centre) = newell(&p.ring, &ids);
            let n = unit(normal)?;
            if n[2] < WALKABLE_NZ as f64 || !convex(&p.ring, &ids) {
                return None;
            }
            let ring: Vec<P> = p.ring.iter().map(|v| v.map(|x| x as f64)).collect();
            let (mut lo, mut hi) = ([f64::MAX; 3], [f64::MIN; 3]);
            for v in &ring {
                for k in 0..3 {
                    lo[k] = lo[k].min(v[k]);
                    hi[k] = hi[k].max(v[k]);
                }
            }
            let z = [-n[0] / n[2], -n[1] / n[2], centre[2] + (n[0] * centre[0] + n[1] * centre[1]) / n[2]];
            Some(Floor { ring, z, lo, hi })
        })
        .collect();
    let mut grid: HashMap<(i32, i32), Vec<u32>> = HashMap::new();
    let cells = |lo: P, hi: P| {
        let (x0, x1) = ((lo[0] / CELL).floor() as i32, (hi[0] / CELL).floor() as i32);
        let (y0, y1) = ((lo[1] / CELL).floor() as i32, (hi[1] / CELL).floor() as i32);
        (x0..=x1).flat_map(move |x| (y0..=y1).map(move |y| (x, y)))
    };
    for (i, f) in floors.iter().enumerate() {
        if let Some(f) = f {
            for c in cells(f.lo, f.hi) {
                grid.entry(c).or_default().push(i as u32);
            }
        }
    }

    let h = headroom as f64;
    let mut stats = Cut { touched: vec![false; polygons.len()], ..Default::default() };
    // One point for every place: the same cut point reached from two
    // polygons differs in its last digit, and the weld would then sometimes
    // put the two on either side of a rounding boundary. Every corner of an
    // object is known here, so a new one within `NEAR` of a known one becomes
    // that one.
    const NEAR: f32 = 0.001;
    let mut known: HashMap<(u32, [i32; 3]), Vec<[f32; 3]>> = HashMap::new();
    let spot = |v: [f32; 3]| v.map(|x| (x / (NEAR * 4.0)).floor() as i32);
    for p in polygons {
        for &v in &p.ring {
            let at = known.entry((p.object, spot(v))).or_default();
            if !at.contains(&v) {
                at.push(v);
            }
        }
    }
    let mut snap = |object: u32, v: [f32; 3]| -> [f32; 3] {
        let c = spot(v);
        for dx in -1..=1 {
            for dy in -1..=1 {
                for dz in -1..=1 {
                    for &q in known.get(&(object, [c[0] + dx, c[1] + dy, c[2] + dz])).into_iter().flatten() {
                        if (q[0] - v[0]).abs() < NEAR && (q[1] - v[1]).abs() < NEAR && (q[2] - v[2]).abs() < NEAR {
                            return q;
                        }
                    }
                }
            }
        }
        known.entry((object, c)).or_default().push(v);
        v
    };
    let mut out: Vec<Polygon> = Vec::with_capacity(polygons.len());
    // New corners, by object.
    let mut corners: HashMap<u32, Vec<[f32; 3]>> = HashMap::new();
    for (i, p) in polygons.iter().enumerate() {
        let Some(b) = &floors[i] else {
            out.push(p.clone());
            stats.source.push(i as u32);
            continue;
        };
        let mut above: Vec<u32> = cells(b.lo, b.hi).filter_map(|c| grid.get(&c)).flatten().copied().collect();
        above.sort_unstable();
        above.dedup();
        let mut pieces: Vec<Vec<P>> = vec![b.ring.clone()];
        let mut touched = false;
        for a in above {
            let Some(f) = floors[a as usize].as_ref().filter(|_| piece[a as usize] != piece[i]) else { continue };
            if f.lo[0] >= b.hi[0] || f.hi[0] <= b.lo[0] || f.lo[1] >= b.hi[1] || f.hi[1] <= b.lo[1] {
                continue;
            }
            if f.hi[2] <= b.lo[2] - ABOVE || f.lo[2] >= b.hi[2] + h {
                continue;
            }
            // Inside the other floor's outline, where it lies above by less
            // than the headroom. `gap` is how far above it is.
            let gap = [f.z[0] - b.z[0], f.z[1] - b.z[1], f.z[2] - b.z[2]];
            let outline: Vec<[f64; 3]> = (0..f.ring.len())
                .map(|k| {
                    let (p, q) = (f.ring[k], f.ring[(k + 1) % f.ring.len()]);
                    let (dx, dy) = (q[0] - p[0], q[1] - p[1]);
                    [-dy, dx, dy * p[0] - dx * p[1]]
                })
                .collect();
            // Two floors in the same place: the one of the smaller piece
            // goes.
            let same = if piece[i] > piece[a as usize] { -ABOVE } else { ABOVE };
            {
                let band = [same, h];
                let mut planes = outline.clone();
                planes.push([gap[0], gap[1], gap[2] - band[0]]);
                planes.push([-gap[0], -gap[1], band[1] - gap[2]]);
                let mut next: Vec<Vec<P>> = Vec::new();
                for piece in &pieces {
                    let mut inside = piece.clone();
                    let mut outside: Vec<Vec<P>> = Vec::new();
                    for &g in &planes {
                        let o = clip(&inside, g, false);
                        if o.len() >= 3 && plan_area(&o) > MIN_AREA {
                            outside.push(o);
                        }
                        inside = clip(&inside, g, true);
                        if inside.len() < 3 {
                            break;
                        }
                    }
                    let covered = if inside.len() >= 3 { plan_area(&inside) } else { 0.0 };
                    if covered > MIN_AREA {
                        stats.area += covered;
                        touched = true;
                        next.extend(outside);
                    } else {
                        next.push(piece.clone());
                    }
                }
                pieces = next;
            }
            if pieces.is_empty() {
                break;
            }
        }
        if !touched {
            out.push(p.clone());
            stats.source.push(i as u32);
            continue;
        }
        stats.touched[i] = true;
        stats.cut += 1;
        if pieces.is_empty() {
            stats.gone += 1;
        }
        stats.pieces += pieces.len();
        for piece in pieces {
            let mut ring: Vec<[f32; 3]> = Vec::with_capacity(piece.len());
            for v in piece {
                let v = snap(p.object, v.map(|x| x as f32));
                if ring.last() != Some(&v) {
                    ring.push(v);
                }
            }
            while ring.len() > 1 && ring.first() == ring.last() {
                ring.pop();
            }
            if ring.len() < 3 {
                stats.pieces -= 1;
                continue;
            }
            for v in &ring {
                if !p.ring.contains(v) {
                    corners.entry(p.object).or_default().push(*v);
                }
            }
            out.push(Polygon { object: p.object, surface: p.surface, ring, breakable: p.breakable });
            stats.source.push(i as u32);
        }
    }

    // A new corner that falls on another polygon's edge joins that edge.
    let mut near: HashMap<(u32, i32, i32), Vec<[f32; 3]>> = HashMap::new();
    let cell = |x: f32| (x / CELL as f32).floor() as i32;
    for (&object, points) in &corners {
        for &v in points {
            near.entry((object, cell(v[0]), cell(v[1]))).or_default().push(v);
        }
    }
    if !near.is_empty() {
        for p in &mut out {
            let mut ring: Vec<[f32; 3]> = Vec::with_capacity(p.ring.len());
            for k in 0..p.ring.len() {
                let (a, b) = (p.ring[k], p.ring[(k + 1) % p.ring.len()]);
                ring.push(a);
                let d = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
                let len2 = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
                if len2 < 1e-8 {
                    continue;
                }
                let mut on: Vec<(f32, [f32; 3])> = Vec::new();
                for cx in cell(a[0].min(b[0]) - NEAR)..=cell(a[0].max(b[0]) + NEAR) {
                    for cy in cell(a[1].min(b[1]) - NEAR)..=cell(a[1].max(b[1]) + NEAR) {
                        for &v in near.get(&(p.object, cx, cy)).into_iter().flatten() {
                            let w = [v[0] - a[0], v[1] - a[1], v[2] - a[2]];
                            let t = (w[0] * d[0] + w[1] * d[1] + w[2] * d[2]) / len2;
                            let off = [0, 1, 2].map(|k| w[k] - d[k] * t);
                            let ends = t * t * len2 > NEAR * NEAR && (1.0 - t) * (1.0 - t) * len2 > NEAR * NEAR;
                            if (0.0..=1.0).contains(&t) && ends && off[0] * off[0] + off[1] * off[1] + off[2] * off[2] < NEAR * NEAR {
                                on.push((t, v));
                            }
                        }
                    }
                }
                on.sort_by(|x, y| x.0.total_cmp(&y.0));
                on.dedup_by(|x, y| (x.0 - y.0).abs() * len2.sqrt() < NEAR);
                stats.inserted += on.len();
                ring.extend(on.into_iter().map(|(_, v)| v));
            }
            p.ring = ring;
        }
    }
    (out, stats)
}

/// The plan area of each connected piece of a mesh's sectors, by component id.
fn component_areas(mesh: &Mesh, pf: &Pathfinding) -> HashMap<usize, f64> {
    let mut areas: HashMap<usize, f64> = HashMap::new();
    for (s, &surface) in pf.sector_surface.iter().enumerate() {
        let ring = crate::unpack16::polygon(&mesh.collision, surface);
        let mut twice = 0f64;
        for i in 0..ring.len() {
            let (p, q) = (ring[i], ring[(i + 1) % ring.len()]);
            twice += p[0] as f64 * q[1] as f64 - q[0] as f64 * p[1] as f64;
        }
        *areas.entry(pf.component[s]).or_default() += twice.abs() / 2.0;
    }
    areas
}

/// Which connected piece of ground each polygon is part of, as the generator
/// would build it with nothing cut: 0 for the largest piece in plan, 1 for
/// the next, and so on (`u32::MAX`: not ground).
pub fn ground_pieces(polygons: &[Polygon], walk: &dyn Fn(usize, &Polygon) -> bool, o: &Options) -> Result<Vec<u32>, String> {
    let mesh = merge(polygons, walk, o);
    let pf = Pathfinding::build_with(&mesh.collision, false, o.seam_step)?;
    let mut by_area: Vec<(usize, f64)> = component_areas(&mesh, &pf).into_iter().collect();
    by_area.sort_by(|x, y| y.1.total_cmp(&x.1).then(x.0.cmp(&y.0)));
    let rank: HashMap<usize, u32> = by_area.iter().enumerate().map(|(n, c)| (c.0, n as u32)).collect();
    Ok((0..polygons.len())
        .map(|i| mesh.surface_of[i].and_then(|s| pf.surface_sector[s as usize]).map_or(u32::MAX, |sector| rank[&pf.component[sector]]))
        .collect())
}

/// Sectors for a polygon soup: [`merge`], then the pathfinding builder, and
/// when `min_ground` is above zero a second round without the ground an AI
/// could never reach from anywhere that matters: every connected piece (crack
/// seams between objects count as connections) smaller than `min_ground` wu^2
/// in plan. A rock's top or a roof costs sectors and links and serves nobody.
pub fn generate(
    polygons: &[Polygon],
    walk: &dyn Fn(usize, &Polygon) -> bool,
    o: &Options,
    min_ground: f32,
) -> Result<(Mesh, Pathfinding), String> {
    let mesh = merge(polygons, walk, o);
    if min_ground <= 0.0 {
        let pf = Pathfinding::build_with(&mesh.collision, true, o.seam_step)?;
        return Ok((mesh, pf));
    }
    let pf = Pathfinding::build_with(&mesh.collision, false, o.seam_step)?;
    let areas = component_areas(&mesh, &pf);
    if areas.values().all(|&a| a >= min_ground as f64) {
        pf.check_limits()?;
        return Ok((mesh, pf));
    }
    // Source polygons whose sector lies on ground that is too small.
    let mut small = vec![false; polygons.len()];
    for (i, flag) in small.iter_mut().enumerate() {
        if let Some(sector) = mesh.surface_of[i].and_then(|s| pf.surface_sector[s as usize]) {
            *flag = areas[&pf.component[sector]] < min_ground as f64;
        }
    }
    let keep = |i: usize, p: &Polygon| !small[i] && walk(i, p);
    let mesh = merge(polygons, &keep, o);
    let pf = Pathfinding::build_with(&mesh.collision, true, o.seam_step)?;
    Ok((mesh, pf))
}

/// One instance of a structure BSP's instanced geometry.
#[derive(Debug, Clone, Copy)]
pub struct Instance {
    pub definition: usize,
    /// The instance's `pathfinding policy`: 0 cut-out, 1 static, 2 none. The
    /// simulation reads an instance's sectors only when this is not none.
    pub policy: u8,
    /// Its definition's collision surface count: how many 2D refs its
    /// pathfinding object must carry.
    pub surfaces: usize,
}

/// The byte of an `instanced geometry instances` element that holds its
/// pathfinding policy.
pub const INSTANCE_POLICY: usize = 0x7c;
pub const POLICY_STATIC: u8 = 1;
pub const POLICY_NONE: u8 = 2;

/// Set the pathfinding policy of the given instances in a structure BSP's
/// payload, in place. Returns how many changed.
pub fn set_instance_policy(sbsp: &mut [u8], instances: &[usize], policy: u8) -> Result<usize, String> {
    use blam_tag::blockedit::find_block;
    let at: Vec<usize> = {
        let tag = blam_tag::TagFile::parse(sbsp, None).map_err(|e| e.to_string())?;
        let layout = tag.layout().map_err(|e| e.to_string())?;
        let root = tag.read_data(&layout).map_err(|e| e.to_string())?;
        let block = find_block(&layout, sbsp, &root, "instanced geometry instances").map_err(|e| format!("{e:?}"))?.block;
        let size = block.element_size as usize;
        if size <= INSTANCE_POLICY {
            return Err(format!("instance elements are {size} bytes: no pathfinding policy"));
        }
        let base = block.elements.as_ptr() as usize - sbsp.as_ptr() as usize;
        instances
            .iter()
            .map(|&i| {
                if i < block.count as usize {
                    Ok(base + i * size + INSTANCE_POLICY)
                } else {
                    Err(format!("instance {i} of {}", block.count))
                }
            })
            .collect::<Result<_, _>>()?
    };
    let mut changed = 0;
    for o in at {
        if sbsp[o] != policy {
            sbsp[o] = policy;
            changed += 1;
        }
    }
    Ok(changed)
}

/// Every instance of a structure BSP and, for those `take` accepts, its
/// collision polygons placed in the world (`object` = the instance index).
pub fn instance_polygons(
    sbsp: &[u8],
    take: &dyn Fn(usize, &Instance) -> bool,
) -> Result<(Vec<Instance>, Vec<Polygon>), String> {
    use blam_tag::blockedit::find_block;
    let tag = blam_tag::TagFile::parse(sbsp, None).map_err(|e| e.to_string())?;
    let layout = tag.layout().map_err(|e| e.to_string())?;
    let root = tag.read_data(&layout).map_err(|e| e.to_string())?;
    let found = find_block(&layout, sbsp, &root, "instanced geometry instances").map_err(|e| format!("{e:?}"))?;
    let f = |b: &[u8], o: usize| f32::from_le_bytes(b[o..o + 4].try_into().unwrap());
    let mut definitions: HashMap<usize, Option<Collision>> = HashMap::new();
    let (mut instances, mut polygons) = (Vec::new(), Vec::new());
    for i in 0..found.block.count as usize {
        let b = found.block.element(i).ok_or_else(|| format!("instance {i}"))?;
        let def = i16::from_le_bytes([b[52], b[53]]);
        let policy = b.get(INSTANCE_POLICY).copied().unwrap_or(POLICY_NONE);
        if def < 0 {
            instances.push(Instance { definition: usize::MAX, policy, surfaces: 0 });
            continue;
        }
        let d = definitions.entry(def as usize).or_insert_with(|| {
            let base = crate::transplant::definition(def as usize);
            let get = |n: &str| -> &[u8] {
                find_block(&layout, sbsp, &root, &format!("{base}.{n}")).map(|f| f.block.elements).unwrap_or(&[])
            };
            let t = crate::unpack16::Tables {
                bsp3d_nodes: get("bsp3d nodes"),
                planes: get("planes"),
                leaves: get("leaves"),
                bsp2d_references: get("bsp2d references"),
                bsp2d_nodes: get("bsp2d nodes"),
                surfaces: get("surfaces"),
                edges: get("edges"),
                vertices: get("vertices"),
            };
            crate::unpack16::unpack(&t).ok().map(|(c, _)| c)
        });
        let instance = Instance { definition: def as usize, policy, surfaces: d.as_ref().map_or(0, |d| d.surfaces.len()) };
        instances.push(instance);
        let Some(d) = d.as_ref() else { continue };
        if !take(i, &instance) {
            continue;
        }
        let scale = f(b, 0);
        let axes = [[f(b, 4), f(b, 8), f(b, 12)], [f(b, 16), f(b, 20), f(b, 24)], [f(b, 28), f(b, 32), f(b, 36)]];
        let pos = [f(b, 40), f(b, 44), f(b, 48)];
        let place = |p: [f32; 3]| -> [f32; 3] {
            [0, 1, 2].map(|k| pos[k] + scale * (p[0] * axes[0][k] + p[1] * axes[1][k] + p[2] * axes[2][k]))
        };
        for s in 0..d.surfaces.len() {
            let mut ring: Vec<[f32; 3]> = crate::unpack16::polygon(d, s).into_iter().map(place).collect();
            // Counter-clockwise about the surface's outward normal.
            let n = crate::pathfinding::surface_normal(d, s);
            let world = [0, 1, 2].map(|k| n[0] * axes[0][k] + n[1] * axes[1][k] + n[2] * axes[2][k]);
            let ids: Vec<u32> = (0..ring.len() as u32).collect();
            let (newell, _) = newell(&ring, &ids);
            if newell[0] * world[0] as f64 + newell[1] * world[1] as f64 + newell[2] * (world[2] as f64) < 0.0 {
                ring.reverse();
            }
            polygons.push(Polygon { object: i as u32, surface: s as u32, ring, breakable: d.surfaces[s].flags & 0x8 != 0 });
        }
    }
    Ok((instances, polygons))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A grid of unwelded triangles over `nx` x `ny` unit cells at height
    /// `z(x, y)`, as object `object`.
    fn grid(object: u32, x0: f32, nx: usize, ny: usize, z: &dyn Fn(f32, f32) -> f32) -> Vec<Polygon> {
        let p = |x: usize, y: usize| {
            let (x, y) = (x0 + x as f32, y as f32);
            [x, y, z(x, y)]
        };
        let mut out = Vec::new();
        for y in 0..ny {
            for x in 0..nx {
                for ring in [vec![p(x, y), p(x + 1, y), p(x + 1, y + 1)], vec![p(x, y), p(x + 1, y + 1), p(x, y + 1)]] {
                    out.push(Polygon { object, surface: out.len() as u32, ring, breakable: false });
                }
            }
        }
        out
    }

    fn build(polygons: &[Polygon], o: &Options) -> (Mesh, Pathfinding) {
        let mesh = merge(polygons, &|_, _| true, o);
        let pf = Pathfinding::build(&mesh.collision).expect("build");
        pf.check_rings().expect("rings");
        pf.check_hints().expect("hints");
        (mesh, pf)
    }

    #[test]
    fn a_flat_grid_of_loose_triangles_is_one_square_sector() {
        let (mesh, pf) = build(&grid(0, 0.0, 6, 4, &|_, _| 2.0), &Options::default());
        assert_eq!(pf.sectors.len(), 1);
        assert_eq!(pf.links.len(), 4, "the straight runs' corners are gone");
        assert_eq!(pf.vertices.len(), 4);
        assert_eq!(mesh.members[0].len(), 48);
        assert!(mesh.surface_of.iter().all(|s| *s == Some(0)));
    }

    #[test]
    fn a_ridge_taller_than_the_tolerance_splits_the_ground() {
        // A roof: rises 0.5 wu per cell to x = 3, then falls.
        let z = |x: f32, _: f32| 0.5 * (3.0 - (x - 3.0).abs());
        let (_, pf) = build(&grid(0, 0.0, 6, 2, &z), &Options::default());
        assert_eq!(pf.sectors.len(), 2);
        // The two slopes share the ridge as one link between sectors.
        assert_eq!(pf.links.iter().filter(|l| l.right >= 0).count(), 1);
        let (_, loose) = build(&grid(0, 0.0, 6, 2, &z), &Options { plane_tolerance: 2.0, ..Options::default() });
        assert_eq!(loose.sectors.len(), 1);
    }

    #[test]
    fn a_notch_keeps_the_sectors_convex() {
        // An L: a 4 x 4 square less its upper right 2 x 2.
        let polygons: Vec<Polygon> = grid(0, 0.0, 4, 4, &|_, _| 0.0)
            .into_iter()
            .filter(|p| !p.ring.iter().all(|v| v[0] >= 2.0 && v[1] >= 2.0))
            .collect();
        let (_, pf) = build(&polygons, &Options::default());
        assert_eq!(pf.sectors.len(), 2);
        assert_eq!(pf.component.iter().collect::<std::collections::HashSet<_>>().len(), 1);
    }

    #[test]
    fn two_objects_join_through_an_intersection_link() {
        let mut polygons = grid(0, 0.0, 2, 2, &|_, _| 0.0);
        polygons.extend(grid(1, 2.0, 2, 2, &|_, _| 0.0));
        let (mesh, pf) = build(&polygons, &Options::default());
        assert_eq!(pf.sectors.len(), 2);
        assert_eq!(pf.hints.len(), 2);
        assert_eq!(pf.component[0], pf.component[1]);
        // Each object's polygons name its own sector.
        let sector = |i: usize| pf.surface_sector[mesh.surface_of[i].unwrap() as usize];
        assert_eq!(sector(0), sector(7));
        assert_ne!(sector(0), sector(8));
    }

    #[test]
    fn small_islands_and_filtered_floors_are_left_out() {
        let mut polygons = grid(0, 0.0, 4, 4, &|_, _| 0.0);
        polygons.extend(grid(0, 10.0, 1, 1, &|_, _| 3.0));
        let o = Options { min_island_area: 2.0, ..Options::default() };
        let (mesh, pf) = build(&polygons, &o);
        assert_eq!(pf.sectors.len(), 1);
        assert_eq!(mesh.island_floors, 2);
        assert_eq!(pf.surface_sector[mesh.surface_of[32].unwrap() as usize], None);
        // The caller's filter: nothing right of x = 2.
        let mesh = merge(&polygons, &|_, p| p.ring.iter().all(|v| v[0] <= 2.0), &Options::default());
        let pf = Pathfinding::build(&mesh.collision).unwrap();
        assert_eq!(pf.sectors.len(), 1);
        assert_eq!(pf.vertices.iter().map(|v| v[0]).fold(0.0, f32::max), 2.0);
    }

    #[test]
    fn ground_too_small_to_matter_gets_no_sectors() {
        // A 4 x 4 field, and a 2 x 2 roof nothing leads to; the roof slopes,
        // so it is several sectors.
        let mut polygons = grid(0, 0.0, 4, 4, &|_, _| 0.0);
        polygons.extend(grid(1, 10.0, 2, 2, &|x, y| 5.0 + 0.3 * (x - 11.0).abs() + 0.3 * (y - 1.0).abs()));
        let (mesh, pf) = generate(&polygons, &|_, _| true, &Options::default(), 0.0).unwrap();
        assert!(pf.sectors.len() > 2);
        assert!(mesh.surface_of[32].and_then(|s| pf.surface_sector[s as usize]).is_some());
        let (mesh, pf) = generate(&polygons, &|_, _| true, &Options::default(), 8.0).unwrap();
        assert_eq!(pf.sectors.len(), 1);
        assert!((32..40).all(|i| mesh.surface_of[i].and_then(|s| pf.surface_sector[s as usize]).is_none()));
        pf.check_rings().unwrap();
    }

    #[test]
    fn a_border_between_two_floors_straightens_within_its_tolerance() {
        // Two slopes meeting along a ridge that wanders 0.2 wu in plan.
        let ridge = |y: f32| 3.0 + if (y as i32) % 2 == 0 { 0.0 } else { 0.2 };
        let p = |x: f32, y: f32| [x, y, 2.0 - (x - ridge(y)).abs()];
        let mut polygons = Vec::new();
        for y in 0..4 {
            let (y0, y1) = (y as f32, y as f32 + 1.0);
            for (a, b, a1, b1) in [(0.0, ridge(y0), 0.0, ridge(y1)), (ridge(y0), 6.0, ridge(y1), 6.0)] {
                for ring in [vec![p(a, y0), p(b, y0), p(b1, y1)], vec![p(a, y0), p(b1, y1), p(a1, y1)]] {
                    polygons.push(Polygon { object: 0, surface: polygons.len() as u32, ring, breakable: false });
                }
            }
        }
        let strict = Options { plane_tolerance: 0.5, ..Options::default() };
        let (_, pf) = build(&polygons, &strict);
        assert!(pf.sectors.len() > 2, "the wandering ridge keeps convex pieces small");
        let loose = Options { dent: 0.25, border: 0.25, ..strict };
        let (_, pf) = build(&polygons, &loose);
        assert_eq!(pf.sectors.len(), 2);
        assert_eq!(pf.links.len(), 7, "two quads sharing one straight border");
    }

    #[test]
    fn steep_and_breakable_polygons_stay_as_they_are() {
        let mut polygons = grid(0, 0.0, 2, 1, &|_, _| 0.0);
        polygons[1].breakable = true;
        // A wall standing on the far edge.
        polygons.push(Polygon { object: 0, surface: 4, ring: vec![[0.0, 1.0, 0.0], [2.0, 1.0, 0.0], [2.0, 1.0, 2.0]], breakable: false });
        let (mesh, pf) = build(&polygons, &Options::default());
        assert_eq!(mesh.collision.surfaces.len(), 3);
        assert_eq!(pf.sectors.len(), 1);
        assert_eq!(pf.surface_sector[mesh.surface_of[1].unwrap() as usize], None);
        assert_eq!(pf.surface_sector[mesh.surface_of[4].unwrap() as usize], None);
    }

    /// A 2 x 2 square of two triangles at height `z` with its corner at
    /// (`x`, `y`), as object `object`.
    fn slab(object: u32, x: f32, y: f32, z: f32) -> Vec<Polygon> {
        let p = |dx: f32, dy: f32| [x + dx, y + dy, z];
        [vec![p(0.0, 0.0), p(2.0, 0.0), p(2.0, 2.0)], vec![p(0.0, 0.0), p(2.0, 2.0), p(0.0, 2.0)]]
            .into_iter()
            .enumerate()
            .map(|(n, ring)| Polygon { object, surface: n as u32, ring, breakable: false })
            .collect()
    }

    fn pieces(pf: &Pathfinding) -> usize {
        pf.component.iter().collect::<std::collections::HashSet<_>>().len()
    }

    #[test]
    fn a_pad_on_the_ground_cuts_it_and_joins() {
        // A 2 x 2 pad 0.3 wu over the middle of a 6 x 6 ground.
        let o = Options { seam_step: 0.35, ..Options::default() };
        let mut polygons = grid(0, 0.0, 6, 6, &|_, _| 0.0);
        polygons.extend(slab(1, 2.0, 2.0, 0.3));
        let piece = ground_pieces(&polygons, &|_, _| true, &o).expect("pieces");
        assert_eq!((piece[0], piece[72], piece[73]), (0, 1, 1));
        let before = merge(&polygons, &|_, _| true, &o);
        assert_eq!(pieces(&Pathfinding::build_with(&before.collision, true, o.seam_step).unwrap()), 2);
        let (cut, stats) = cut_covered(&polygons, &piece, 0.5);
        assert!((stats.area - 4.0).abs() < 1e-6, "the ground under the pad: {}", stats.area);
        assert!(stats.touched[14 * 2] && !stats.touched[72] && !stats.touched[73]);
        let (mesh, pf) = generate(&cut, &|_, _| true, &o, 0.0).expect("generate");
        pf.check_rings().expect("rings");
        pf.check_hints().expect("hints");
        assert_eq!(pieces(&pf), 1, "the pad joins the ground all the way round");
        let area: f64 = component_areas(&mesh, &pf).values().sum();
        assert!((area - 36.0).abs() < 1e-3, "36 - 4 of ground + 4 of pad: {area}");
        // A step too tall for the seam leaves them apart.
        let (_, apart) = generate(&cut, &|_, _| true, &Options::default(), 0.0).expect("generate");
        assert_eq!(pieces(&apart), 2);
        // A deck with room to stand under covers nothing.
        let mut high = grid(0, 0.0, 6, 6, &|_, _| 0.0);
        high.extend(slab(1, 2.0, 2.0, 0.6));
        assert_eq!(cut_covered(&high, &piece, 0.5).1.cut, 0);
    }

    #[test]
    fn the_top_of_a_stack_of_floors_is_the_ground() {
        // Ground, a pad 0.15 wu over it, a trim 0.15 wu over half the pad.
        let o = Options { seam_step: 0.2, ..Options::default() };
        let mut polygons = grid(0, 0.0, 6, 6, &|_, _| 0.0);
        polygons.extend(slab(1, 2.0, 2.0, 0.15));
        polygons.push(Polygon { object: 2, surface: 0, ring: vec![[2.0, 2.0, 0.3], [3.0, 2.0, 0.3], [3.0, 4.0, 0.3], [2.0, 4.0, 0.3]], breakable: false });
        let piece = ground_pieces(&polygons, &|_, _| true, &o).expect("pieces");
        let (cut, _) = cut_covered(&polygons, &piece, 0.5);
        let (mesh, pf) = generate(&cut, &|_, _| true, &o, 0.0).expect("generate");
        pf.check_hints().expect("hints");
        assert_eq!(pieces(&pf), 1);
        // Nowhere is ground twice, and nowhere is it missing.
        let area: f64 = component_areas(&mesh, &pf).values().sum();
        assert!((area - 36.0).abs() < 1e-3, "{area}");
    }

    #[test]
    fn a_slab_sunk_into_a_slope_meets_it_on_the_line_they_cross() {
        // Ground rising 0.1 wu per wu; a level slab at 0.3 that the ground
        // passes through at x = 3.
        let o = Options { seam_step: 0.25, ..Options::default() };
        let mut polygons = grid(0, 0.0, 6, 2, &|x, _| 0.1 * x);
        polygons.extend(slab(1, 2.0, 0.0, 0.3));
        let piece = ground_pieces(&polygons, &|_, _| true, &o).expect("pieces");
        let (cut, _) = cut_covered(&polygons, &piece, 0.5);
        let (mesh, pf) = generate(&cut, &|_, _| true, &o, 0.0).expect("generate");
        pf.check_hints().expect("hints");
        assert_eq!(pieces(&pf), 1);
        // Left of x = 3 the slab is on top, right of it the slope.
        let area: f64 = component_areas(&mesh, &pf).values().sum();
        assert!((area - 12.0).abs() < 1e-3, "{area}");
    }

    #[test]
    fn floors_of_one_piece_of_ground_do_not_cut_each_other() {
        // Two sheets of one object that cross, joined along an edge.
        let mut polygons = grid(0, 0.0, 4, 2, &|x, _| 0.1 * x);
        polygons.extend(grid(0, 0.0, 4, 2, &|x, _| 0.2 - 0.1 * (x - 4.0).abs().min(4.0) + 0.2));
        let same = vec![0u32; polygons.len()];
        let (cut, stats) = cut_covered(&polygons, &same, 0.5);
        assert_eq!((stats.cut, cut.len()), (0, polygons.len()));
    }
}
