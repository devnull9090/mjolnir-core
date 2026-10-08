//! The light: the sky's lights and ambient onto every vertex, then
//! progressive shooting from the brightest elements until the unshot
//! energy is spent. tool.exe shoots one element a step; here a batch of the
//! brightest shoot together and every receiver gathers from the batch in
//! parallel, which lands the same energy in the same places. After each
//! batch, a receiving patch whose corners disagree about the light is split
//! (tool.exe's adaptive subdivision), so shadow edges get finer patches.

use crate::bvh::Bvh;
use crate::elements::{Element, Elements, Patch, Quality, Vertex, WU_TO_M};
use crate::gltf::Scene;
use crate::math::{add, dot, len, lerp, luma, mul, norm, sub, V3};
use crate::staging::Staging;
use rayon::prelude::*;

/// What a ray meets: nothing, a blocker, or glass it passes through tinted.
pub struct Occluders {
    pub bvh: Bvh,
    /// Per BVH triangle: `None` blocks, `Some(tint)` lets light through
    /// multiplied by it (a transparent shader's `tint_color`).
    pub tint: Vec<Option<V3>>,
    /// The level's collision BSP: a ray starting or ending 1 mm inside its
    /// solid is blocked, as tool.exe's walk reports.
    pub solid: Option<crate::collision::Collision>,
}

impl Occluders {
    /// The scene's opaque triangles block; those of `translucent` (the
    /// merged scene's transparent pieces) pass light tinted; every triangle
    /// of `extra` blocks (the placed objects' collision models, which is
    /// what tool.exe traces: CE's lightmaps carry the trees' trunks'
    /// shadows, not their boughs'). Placed objects' rendered meshes occlude
    /// only when `objects`.
    pub fn build(scene: &Scene, translucent: Option<&Scene>, extra: Option<&Scene>, staging: &Staging, objects: bool) -> Occluders {
        let mut tris = Vec::new();
        let mut tint = Vec::new();
        if let Some(x) = extra {
            for t in &x.tris {
                tris.push(t.p);
                tint.push(None);
            }
        }
        for t in &scene.tris {
            let m = &scene.materials[t.material];
            if m.sky || (m.object && !objects) {
                continue;
            }
            tris.push(t.p);
            tint.push(None);
        }
        if let Some(tr) = translucent {
            for t in &tr.tris {
                let m = &tr.materials[t.material];
                if m.sky || (m.object && !objects) {
                    continue;
                }
                let colour = staging.shaders.get(&m.shader).map(|s| s.tint).unwrap_or([1.0; 3]);
                tris.push(t.p);
                tint.push(Some(colour));
            }
        }
        Occluders { bvh: Bvh::build(tris), tint, solid: None }
    }

    /// The light that gets from `from` to `to`: 1 in the clear, 0 behind
    /// anything opaque, the tints' product through glass. The segment is
    /// shrunk 1 mm at both ends so neither surface shadows itself. With
    /// the collision BSP, a start inside its solid blocks, and so does an
    /// end inside it when `to` is a surface point (`end_in_level`); a sun
    /// ray's end is the sky, outside the sealed hull.
    pub fn transmission(&self, from: V3, to: V3, end_in_level: bool) -> V3 {
        let v = sub(to, from);
        let l = len(v);
        if l <= 0.002 {
            return [1.0; 3];
        }
        let d = mul(v, 1.0 / l);
        let mut t0 = 0.001;
        let end = l - 0.001;
        if let Some(c) = &self.solid {
            if c.in_solid(add(from, mul(d, t0))) || (end_in_level && c.in_solid(add(from, mul(d, end)))) {
                return [0.0; 3];
            }
        }
        let mut t = [1.0f32; 3];
        for _ in 0..16 {
            let o = add(from, mul(d, t0));
            match self.bvh.trace(o, d, end - t0, false) {
                None => return t,
                Some(hit) => match self.tint[hit.tri as usize] {
                    None => return [0.0; 3],
                    Some(c) => {
                        t = [t[0] * c[0], t[1] * c[1], t[2] * c[2]];
                        if t.iter().all(|x| *x <= 1e-4) {
                            return [0.0; 3];
                        }
                        t0 += hit.t + 0.001;
                        if t0 >= end {
                            return t;
                        }
                    }
                },
            }
        }
        t
    }
}

/// A light of the light phase.
#[derive(Clone, Debug)]
pub enum Light {
    /// Everywhere, no ray.
    Ambient { colour: V3 },
    /// From infinitely far along `-towards`; one ray towards the sun.
    Directional { towards: V3, colour: V3 },
}

/// The groups a light reaches: the clusters whose sky is a real sky
/// (`Exterior`) or none (`Interior`).
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Set {
    Exterior,
    Interior,
}

pub struct Options {
    pub quality: Quality,
    /// Stop when the area-weighted unshot energy (r+g+b) falls below this.
    pub stop: f32,
    /// Shooters per batch.
    pub batch: usize,
    /// Scale a directional light by the receiver's cosine. tool.exe's
    /// output says it does (the difference to its lightmap halves).
    pub sun_cosine: bool,
    /// Split patches where the light's gradient exceeds the quality row's
    /// tolerance (tool.exe does).
    pub adaptive: bool,
    /// How far a directional light's shadow ray reaches, in metres: the
    /// sky light's test distance (tool.exe stops there).
    pub sun_ray: f32,
    /// The sky lights' grid spread as a multiple of their diameter (1: the
    /// diameter is the half-width, as tool.exe's code reads).
    pub fill_spread: f32,
    /// Evaluate the sun and fill per texel when drawing the pages (the
    /// vertices keep the bounce and ambient), for shadow edges that follow
    /// the geometry rather than the patches.
    pub texel_direct: bool,
    /// Block a ray that leaves its vertex into an adjacent face (as a BSP
    /// walk from inside the solid would). Off: tool.exe's lightmap says
    /// it does not (Danger Canyon creases got darker than CE's).
    pub solid_test: bool,
    /// Called with (step, residual) as the solve goes.
    pub progress: Option<Box<dyn Fn(usize, f32) + Sync>>,
}

impl Default for Options {
    fn default() -> Options {
        Options { quality: Quality::final_(), stop: 0.01, batch: 64, sun_cosine: true, adaptive: true, sun_ray: 1.0e4, fill_spread: 1.0, texel_direct: true, solid_test: false, progress: None }
    }
}

/// The sky's lights for one set: every matching sky light as an n x n grid
/// fanned across its diameter, then the set's ambient.
pub fn sky_lights(staging: &Staging, set: Set, grid: usize, spread: f32) -> Vec<Light> {
    let mut out = Vec::new();
    let n = grid.max(1);
    for l in &staging.sky.lights {
        let wanted = match set {
            Set::Exterior => l.affects_exteriors,
            Set::Interior => l.affects_interiors,
        };
        if !wanted || l.color.iter().all(|c| *c == 0.0) || l.power <= 0.0 {
            continue;
        }
        let power = l.power / (n * n) as f32;
        for i in 0..n {
            for j in 0..n {
                let (mut yaw, mut pitch) = (l.yaw, l.pitch);
                if n > 1 {
                    let d = l.diameter * spread;
                    yaw += (2 * j) as f32 * d / (n - 1) as f32 - d;
                    pitch += (2 * i) as f32 * d / (n - 1) as f32 - d;
                }
                // CE, z up: towards the light. The scene is glTF (x, z, -y).
                let (cx, cy, cz) = (pitch.cos() * yaw.cos(), pitch.cos() * yaw.sin(), pitch.sin());
                out.push(Light::Directional { towards: norm([cx, cz, -cy]), colour: mul(l.color, power) });
            }
        }
    }
    let amb = match set {
        Set::Exterior => &staging.sky.outdoor_ambient,
        Set::Interior => &staging.sky.indoor_ambient,
    };
    out.push(Light::Ambient { colour: mul(amb.color, amb.power) });
    out
}

/// Which set a cluster belongs to.
pub fn cluster_set(staging: &Staging, cluster: i32) -> Set {
    match staging.clusters.as_ref().and_then(|c| c.clusters.get(cluster.max(0) as usize)) {
        Some(c) if c.sky >= 0 => Set::Exterior,
        Some(_) => Set::Interior,
        // Without cluster data everything is outdoors, which every stock
        // multiplayer map is.
        None => Set::Exterior,
    }
}

/// The sky's directional lights at a point with a normal: each light's
/// colour times its ray's transmission and the receiver cosine. (The
/// ambient is not in it: a vertex value, not a texel one.)
pub fn direct_light(occ: &Occluders, lights: &[Light], p: V3, n: V3, opt: &Options) -> V3 {
    let mut gain = [0.0f32; 3];
    for l in lights {
        if let Light::Directional { towards, colour } = l {
            let cos = if opt.sun_cosine { dot(n, *towards).max(0.0) } else { 1.0 };
            if cos <= 0.0 {
                continue;
            }
            let far = add(p, mul(*towards, opt.sun_ray));
            let t = occ.transmission(p, far, false);
            if t.iter().all(|x| *x <= 0.0) {
                continue;
            }
            gain = add(gain, [colour[0] * t[0] * cos, colour[1] * t[1] * cos, colour[2] * t[2] * cos]);
        }
    }
    gain
}

/// The three sample points on a shooter: barycentric (u, v) of its corners.
const SAMPLES: [[f32; 2]; 3] = [[1.0 / 6.0, 1.0 / 6.0], [2.0 / 3.0, 1.0 / 6.0], [1.0 / 6.0, 2.0 / 3.0]];

/// The form factor from a shooter element to a receiver vertex, and the
/// direction the light arrives from: tool.exe's three samples of
/// `cos_s cos_r (A/3) / (pi r^2 + A/3)`, each visible or not.
fn form_factor(occ: &Occluders, shooter: &Element, sv: [V3; 3], rv: &Vertex, ignore_normals: bool, cull: f32, solid_test: bool) -> (V3, V3) {
    let side = dot(shooter.normal, rv.p) - shooter.d;
    if side <= 0.0 {
        return ([0.0; 3], [0.0; 3]);
    }
    let da = shooter.patch.area / 3.0;
    let mut f = [0.0f32; 3];
    let mut dir = [0.0f32; 3];
    for s in SAMPLES {
        let q = add(add(mul(sv[0], 1.0 - s[0] - s[1]), mul(sv[1], s[0])), mul(sv[2], s[1]));
        let v = sub(q, rv.p);
        let facing = dot(v, rv.n);
        if facing <= 0.0 && !ignore_normals {
            continue;
        }
        let r = len(v);
        if r < 1e-4 {
            continue;
        }
        let d = mul(v, 1.0 / r);
        if solid_test && rv.enters_solid(d) {
            continue;
        }
        let cos_r = if ignore_normals { 1.0 } else { dot(rv.n, d) };
        let cos_s = dot(shooter.normal, mul(d, -1.0));
        if cos_s <= 0.0 {
            continue;
        }
        let fi = cos_s * da * cos_r / (std::f32::consts::PI * r * r + da);
        if fi * shooter.delta.iter().sum::<f32>() <= cull {
            continue;
        }
        let t = occ.transmission(rv.p, q, true);
        if t.iter().all(|x| *x <= 0.0) {
            continue;
        }
        f = add(f, mul(t, fi));
        dir = d;
    }
    for c in f.iter_mut() {
        *c = c.clamp(0.0, 1.0);
    }
    (f, dir)
}

pub struct Solver<'a> {
    pub staging: &'a Staging,
    pub occluders: &'a Occluders,
    pub elements: Elements,
    /// Per cluster, the clusters it sees (itself included).
    visible: Vec<Vec<u32>>,
    /// Per cluster, its elements.
    by_cluster: Vec<Vec<u32>>,
    pub steps: usize,
    pub splits: usize,
}

impl<'a> Solver<'a> {
    pub fn new(staging: &'a Staging, occluders: &'a Occluders, elements: Elements) -> Solver<'a> {
        let clusters = staging.clusters.as_ref();
        let n = clusters.map(|c| c.clusters.len()).unwrap_or(0).max(1);
        let mut visible: Vec<Vec<u32>> = (0..n).map(|g| vec![g as u32]).collect();
        if let Some(c) = clusters {
            for (g, row) in c.visibility.iter().enumerate().take(n) {
                for &h in row {
                    if (h as usize) < n && !visible[g].contains(&h) {
                        visible[g].push(h);
                    }
                }
            }
        }
        let mut by_cluster: Vec<Vec<u32>> = vec![Vec::new(); n];
        for (i, e) in elements.elements.iter().enumerate() {
            let g = if clusters.is_some() && e.cluster >= 0 && (e.cluster as usize) < n { e.cluster as usize } else { 0 };
            by_cluster[g].push(i as u32);
        }
        Solver { staging, occluders, elements, visible, by_cluster, steps: 0, splits: 0 }
    }

    fn cluster_of(&self, e: &Element) -> usize {
        if self.staging.clusters.is_some() && e.cluster >= 0 && (e.cluster as usize) < self.visible.len() {
            e.cluster as usize
        } else {
            0
        }
    }

    /// The leaf patches of an element: its children, or itself.
    fn leaves(e: &Element) -> Vec<Patch> {
        if e.children.is_empty() {
            vec![e.patch.clone()]
        } else {
            e.children.clone()
        }
    }

    /// The vertices of `elements`, each once.
    fn vertices_of(&self, elements: &[u32]) -> Vec<u32> {
        let mut seen = vec![false; self.elements.pool.vertices.len()];
        for &ei in elements {
            let e = &self.elements.elements[ei as usize];
            for p in Self::leaves(e) {
                for v in p.v {
                    seen[v as usize] = true;
                }
            }
        }
        (0..seen.len() as u32).filter(|&i| seen[i as usize]).collect()
    }

    /// After a batch: each receiver's element gains what its leaf patches
    /// reflect of `step` (their corners' mean, weighted by area), and leaves
    /// whose corners disagree past the row's tolerance split.
    fn settle(&mut self, receivers: &[u32], step: &mut Vec<V3>, opt: &Options) {
        for &ei in receivers {
            let (row, reflectance, area) = {
                let e = &self.elements.elements[ei as usize];
                let m = &self.elements.materials[e.material as usize];
                (opt.quality.rows[m.detail_level], e.reflectance, e.patch.area.max(1e-12))
            };
            let leaves = Self::leaves(&self.elements.elements[ei as usize]);
            let mut gain = [0.0f32; 3];
            let mut new_leaves: Vec<Patch> = Vec::new();
            let mut changed = false;
            for leaf in leaves {
                let s = [step[leaf.v[0] as usize], step[leaf.v[1] as usize], step[leaf.v[2] as usize]];
                let mean = mul(add(add(s[0], s[1]), s[2]), 1.0 / 3.0);
                gain = add(gain, mul(mean, leaf.area / area));
                let split = opt.adaptive
                    && row.gradient < f32::MAX
                    && leaf.segment > 2.0 * row.minimum * WU_TO_M
                    && s.iter().any(|c| c.iter().any(|x| *x > 0.0))
                    && (0..3).any(|k| {
                        let (a, b) = (s[k], s[(k + 1) % 3]);
                        (0..3).any(|c| (a[c] - b[c]).abs() >= (a[c].max(b[c]) * row.gradient).max(0.005))
                    });
                if split {
                    let mut p = leaf.clone();
                    p.segment *= 0.5;
                    let before = self.elements.pool.vertices.len();
                    let face = self.elements.elements[ei as usize].normal;
                    let subs = self.elements.split_patch(p, face);
                    // New vertices take their endpoints' light for this step too.
                    for vi in before..self.elements.pool.vertices.len() {
                        let vp = self.elements.pool.vertices[vi].p;
                        let mut best: Option<(f32, V3)> = None;
                        for k in 0..3 {
                            let (a, b) = (leaf.v[k], leaf.v[(k + 1) % 3]);
                            let (pa, pb) = (self.elements.pool.vertices[a as usize].p, self.elements.pool.vertices[b as usize].p);
                            let e = sub(pb, pa);
                            let t = (dot(sub(vp, pa), e) / dot(e, e).max(1e-12)).clamp(0.0, 1.0);
                            let q = add(pa, mul(e, t));
                            let d = len(sub(q, vp));
                            if best.map(|b| d < b.0).unwrap_or(true) {
                                best = Some((d, lerp(step[a as usize], step[b as usize], t)));
                            }
                        }
                        let s = best.map(|b| b.1).unwrap_or([0.0; 3]);
                        if step.len() <= vi {
                            step.resize(vi + 1, [0.0; 3]);
                        }
                        step[vi] = s;
                    }
                    self.splits += 1;
                    new_leaves.extend(subs);
                    changed = true;
                } else {
                    new_leaves.push(leaf);
                }
            }
            let e = &mut self.elements.elements[ei as usize];
            e.delta = add(e.delta, [gain[0] * reflectance[0], gain[1] * reflectance[1], gain[2] * reflectance[2]]);
            if changed {
                e.children = new_leaves;
            }
        }
    }

    /// The light phase: every sky light onto every vertex of its set.
    pub fn light(&mut self, opt: &Options) {
        let staging = self.staging;
        let occ = self.occluders;
        for set in [Set::Exterior, Set::Interior] {
            let lights = sky_lights(staging, set, opt.quality.sun_grid, opt.fill_spread);
            let receivers: Vec<u32> = (0..self.elements.elements.len() as u32)
                .filter(|&i| cluster_set(staging, self.elements.elements[i as usize].cluster) == set)
                .collect();
            if receivers.is_empty() {
                continue;
            }
            let targets = self.vertices_of(&receivers);
            let vertices = &self.elements.pool.vertices;
            let gains: Vec<(V3, V3, V3, V3)> = targets
                .par_iter()
                .map(|&vi| {
                    let v = &vertices[vi as usize];
                    let mut gain = [0.0f32; 3];
                    let mut dir = [0.0f32; 3];
                    let mut sun = [0.0f32; 3];
                    let mut ambient = [0.0f32; 3];
                    for l in &lights {
                        match l {
                            Light::Ambient { colour } => {
                                gain = add(gain, *colour);
                                ambient = add(ambient, *colour);
                                dir = add(dir, mul(v.n, luma(*colour)));
                            }
                            Light::Directional { towards, colour } => {
                                let cos = if opt.sun_cosine { dot(v.n, *towards).max(0.0) } else { 1.0 };
                                if cos <= 0.0 || (opt.solid_test && v.enters_solid(*towards)) {
                                    continue;
                                }
                                let far = add(v.p, mul(*towards, opt.sun_ray));
                                let t = occ.transmission(v.p, far, false);
                                if t.iter().all(|x| *x <= 0.0) {
                                    continue;
                                }
                                let c = [colour[0] * t[0] * cos, colour[1] * t[1] * cos, colour[2] * t[2] * cos];
                                gain = add(gain, c);
                                sun = add(sun, c);
                                dir = add(dir, mul(*towards, luma(c)));
                            }
                        }
                    }
                    (gain, dir, sun, ambient)
                })
                .collect();
            let mut step = vec![[0.0f32; 3]; self.elements.pool.vertices.len()];
            for (&vi, (gain, dir, sun, ambient)) in targets.iter().zip(&gains) {
                let v = &mut self.elements.pool.vertices[vi as usize];
                v.total = add(v.total, *gain);
                v.dir = add(v.dir, *dir);
                v.sun = add(v.sun, *sun);
                v.ambient = add(v.ambient, *ambient);
                step[vi as usize] = *gain;
            }
            self.settle(&receivers, &mut step, opt);
        }
    }

    /// The area-weighted mean unshot energy, tool.exe's printed residual.
    pub fn residual(&self) -> f32 {
        let total: f32 = self.elements.elements.iter().map(|e| e.delta.iter().sum::<f32>() * e.patch.area).sum();
        total / self.elements.total_area.max(1e-12)
    }

    /// How many vertices belong to the exterior and the interior set.
    pub fn set_vertex_counts(&self) -> (usize, usize) {
        let mut ext = vec![false; self.elements.pool.vertices.len()];
        let mut int = vec![false; self.elements.pool.vertices.len()];
        for e in &self.elements.elements {
            let m = if cluster_set(self.staging, e.cluster) == Set::Exterior { &mut ext } else { &mut int };
            for p in Self::leaves(e) {
                for v in p.v {
                    m[v as usize] = true;
                }
            }
        }
        (ext.iter().filter(|x| **x).count(), int.iter().filter(|x| **x).count())
    }

    /// One batch: the brightest `opt.batch` elements shoot; every vertex
    /// they can reach gathers. Returns false when nothing is left to shoot.
    pub fn step(&mut self, opt: &Options) -> bool {
        let mut order: Vec<(f32, u32)> = self
            .elements
            .elements
            .iter()
            .enumerate()
            .filter_map(|(i, e)| {
                let energy = e.delta.iter().sum::<f32>() * e.patch.area;
                (energy > 0.0).then_some((energy, i as u32))
            })
            .collect();
        if order.is_empty() {
            return false;
        }
        order.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap());
        let shooters: Vec<u32> = order.iter().take(opt.batch.max(1)).map(|x| x.1).collect();

        // The receivers: every element in a cluster any shooter sees.
        let mut seen = vec![false; self.visible.len()];
        for &s in &shooters {
            let g = self.cluster_of(&self.elements.elements[s as usize]);
            for &h in &self.visible[g] {
                seen[h as usize] = true;
            }
        }
        let mut receivers: Vec<u32> = Vec::new();
        for (g, &on) in seen.iter().enumerate() {
            if on {
                receivers.extend(self.by_cluster[g].iter().copied());
            }
        }
        let targets = self.vertices_of(&receivers);

        let elements = &self.elements;
        let occ = self.occluders;
        let cull = 1e-4;
        let shooter_data: Vec<(&Element, [V3; 3])> = shooters
            .iter()
            .map(|&s| {
                let e = &elements.elements[s as usize];
                let sv = [
                    elements.pool.vertices[e.patch.v[0] as usize].p,
                    elements.pool.vertices[e.patch.v[1] as usize].p,
                    elements.pool.vertices[e.patch.v[2] as usize].p,
                ];
                (e, sv)
            })
            .collect();
        let gains: Vec<(V3, V3)> = targets
            .par_iter()
            .map(|&vi| {
                let rv = &elements.pool.vertices[vi as usize];
                let mut gain = [0.0f32; 3];
                let mut dir = [0.0f32; 3];
                for (e, sv) in &shooter_data {
                    let ignore = elements.materials[e.material as usize].ignore_normals;
                    let (f, d) = form_factor(occ, e, *sv, rv, ignore, cull, opt.solid_test);
                    if f.iter().all(|x| *x <= 0.0) {
                        continue;
                    }
                    let c = [f[0] * e.delta[0], f[1] * e.delta[1], f[2] * e.delta[2]];
                    gain = add(gain, c);
                    dir = add(dir, mul(d, luma(c)));
                }
                (gain, dir)
            })
            .collect();

        let mut step = vec![[0.0f32; 3]; self.elements.pool.vertices.len()];
        for (&vi, (gain, dir)) in targets.iter().zip(&gains) {
            let v = &mut self.elements.pool.vertices[vi as usize];
            v.total = add(v.total, *gain);
            v.dir = add(v.dir, *dir);
            step[vi as usize] = *gain;
        }
        for &s in &shooters {
            self.elements.elements[s as usize].delta = [0.0; 3];
        }
        self.settle(&receivers, &mut step, opt);
        self.steps += shooters.len();
        true
    }

    /// The whole solve: the light phase, then batches until the residual
    /// drops below `opt.stop`.
    pub fn run(&mut self, opt: &Options) {
        self.light(opt);
        loop {
            let r = self.residual();
            if let Some(p) = &opt.progress {
                p(self.steps, r);
            }
            if r < opt.stop || !self.step(opt) {
                break;
            }
        }
    }
}
