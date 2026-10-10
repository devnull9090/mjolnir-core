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
use crate::visibility::ClusterVis;
use rayon::prelude::*;
use std::path::Path;

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
    /// merged scene's transparent pieces) pass light tinted when the
    /// collision BSP carries their shader (glass), and are not in a ray's
    /// way at all when it does not (water, light strips: tool.exe traces
    /// the collision BSP, and Death Island's sea floor is lit through its
    /// water); every triangle of `extra` blocks (the placed objects'
    /// collision models, which is what tool.exe traces: CE's lightmaps
    /// carry the trees' trunks' shadows, not their boughs'). Placed
    /// objects' rendered meshes occlude only when `objects`.
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
                if !staging.collision_shaders.is_empty() && !staging.collision_shaders.contains(&m.shader) {
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
    /// `sun`: part of the sky's sun (its narrowest light), whose visibility
    /// the pages record for the masters' Unreal sun share.
    Directional { towards: V3, colour: V3, sun: bool },
    /// A placed light (a `light` tag at a placed object's marker): at
    /// `pos` (glTF metres), `colour` = the tag's radiosity colour x
    /// intensity, reaching `reach` metres (where intensity / d^2, d in
    /// world units, falls to 1/255), a spot when `cone` (its axis, cos
    /// falloff, cos cutoff: full inside the falloff angle, nothing past the
    /// cutoff, a cosine ramp between), in `cluster` (-1: reaches everything).
    Point { pos: V3, colour: V3, reach: f32, cone: Option<(V3, f32, f32)>, cluster: i32 },
}

/// The placed lights (`scene_lights.json` beside the scene, written by
/// `merge_ce_scene.py --lights`: CE's light fixtures and the lamps scenery
/// carries) and, per light, the clusters it reaches: its own and those its
/// cluster sees, as a shooting element's.
#[derive(Default)]
pub struct PlacedLights {
    pub lights: Vec<Light>,
    /// Per light, per cluster: reached. An empty row reaches every cluster.
    pub reach: Vec<Vec<bool>>,
}

impl PlacedLights {
    /// Whether light `i` reaches a receiver in `cluster`.
    pub fn reaches(&self, i: usize, cluster: i32) -> bool {
        match self.reach.get(i) {
            Some(row) if !row.is_empty() && cluster >= 0 => row.get(cluster as usize).copied().unwrap_or(false),
            _ => true,
        }
    }

    /// Load the lights, placing each in the cluster of the nearest lit
    /// surface and giving it that cluster's visibility row.
    pub fn load(path: &Path, elements: &Elements, visible: &[Vec<u32>]) -> Result<PlacedLights, String> {
        let json: serde_json::Value = serde_json::from_slice(&std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?)
            .map_err(|e| format!("{}: {e}", path.display()))?;
        let centroids: Vec<(V3, i32)> = elements
            .elements
            .iter()
            .filter(|e| e.cluster >= 0)
            .map(|e| {
                let v = &elements.pool.vertices;
                let c = mul(add(add(v[e.patch.v[0] as usize].p, v[e.patch.v[1] as usize].p), v[e.patch.v[2] as usize].p), 1.0 / 3.0);
                (c, e.cluster)
            })
            .collect();
        let mut out = PlacedLights::default();
        for l in json["lights"].as_array().map(|a| a.as_slice()).unwrap_or(&[]) {
            let v3 = |k: &str| -> Option<V3> {
                let a = l[k].as_array()?;
                if a.len() < 3 {
                    return None;
                }
                Some([a[0].as_f64()? as f32, a[1].as_f64()? as f32, a[2].as_f64()? as f32])
            };
            let Some(pos) = v3("pos") else { continue };
            let colour = v3("colour").unwrap_or([1.0; 3]);
            let intensity = l["intensity"].as_f64().unwrap_or(0.0) as f32;
            if intensity <= 0.0 || colour.iter().all(|c| *c <= 0.0) {
                continue;
            }
            let reach = (255.0 * intensity).sqrt() * WU_TO_M;
            let cutoff = l["cutoff_angle"].as_f64().unwrap_or(0.0) as f32;
            let falloff = l["falloff_angle"].as_f64().unwrap_or(0.0) as f32;
            let cone = match v3("dir") {
                Some(d) if cutoff > 1e-3 && cutoff < std::f32::consts::PI - 1e-3 => Some((norm(d), falloff.min(cutoff).cos(), cutoff.cos())),
                _ => None,
            };
            let cluster = centroids
                .iter()
                .map(|(c, k)| (dot(sub(*c, pos), sub(*c, pos)), *k))
                .min_by(|a, b| a.0.partial_cmp(&b.0).unwrap())
                .map(|x| x.1)
                .unwrap_or(-1);
            let row = if cluster >= 0 && (cluster as usize) < visible.len() {
                let mut r = vec![false; visible.len()];
                for &h in &visible[cluster as usize] {
                    if (h as usize) < r.len() {
                        r[h as usize] = true;
                    }
                }
                r
            } else {
                Vec::new()
            };
            out.lights.push(Light::Point { pos, colour: mul(colour, intensity), reach, cone, cluster });
            out.reach.push(row);
        }
        Ok(out)
    }
}

/// What a placed light gives a point with a normal: its colour over the
/// squared distance in world units, times the spot factor and the
/// receiver cosine, times the ray's transmission; None out of reach,
/// facing away or blocked. With it, the direction towards the light.
pub fn point_gain(l: &Light, occ: &Occluders, p: V3, n: V3) -> Option<(V3, V3)> {
    let Light::Point { pos, colour, reach, cone, .. } = l else { return None };
    let v = sub(*pos, p);
    let d = len(v);
    if d > *reach || d < 1e-3 {
        return None;
    }
    let dir = mul(v, 1.0 / d);
    let cos = dot(n, dir);
    if cos <= 0.0 {
        return None;
    }
    let spot = match cone {
        Some((axis, cf, cc)) => {
            let c = dot(mul(dir, -1.0), *axis);
            if c >= *cf {
                1.0
            } else if c <= *cc {
                0.0
            } else {
                (c - cc) / (cf - cc).max(1e-6)
            }
        }
        None => 1.0,
    };
    if spot <= 0.0 {
        return None;
    }
    let t = occ.transmission(p, *pos, false);
    if t.iter().all(|x| *x <= 0.0) {
        return None;
    }
    let dw = d / WU_TO_M;
    let s = spot * cos / (dw * dw);
    Some(([colour[0] * t[0] * s, colour[1] * t[1] * s, colour[2] * t[2] * s], dir))
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
    /// tool.exe prints 0.01 as its final target, but its pages hold more
    /// bounce than a solve stopped there: Death Island's exterior pages
    /// score 25.6 -> 20.4/255 going from 0.01 to 0.001, Danger Canyon's
    /// 15.6 -> 15.4, nothing worsens, and the solve costs about twice the
    /// shots.
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
        Options { quality: Quality::final_(), stop: 0.001, batch: 64, sun_cosine: true, adaptive: true, sun_ray: 1.0e4, fill_spread: 1.0, texel_direct: true, solid_test: false, progress: None }
    }
}

/// The sky's lights for one set: every matching sky light as an n x n grid
/// fanned across its diameter, then the set's ambient.
pub fn sky_lights(staging: &Staging, set: Set, grid: usize, spread: f32) -> Vec<Light> {
    let mut out = Vec::new();
    let n = grid.max(1);
    // The sun: the narrowest of the sky's lit lights (gen_ce_level.py's
    // choice too), ties to the stronger.
    let sun_index = staging
        .sky
        .lights
        .iter()
        .enumerate()
        .filter(|(_, l)| l.power > 0.0 && l.color.iter().any(|c| *c > 0.0))
        .min_by(|a, b| (a.1.diameter, -a.1.power).partial_cmp(&(b.1.diameter, -b.1.power)).unwrap())
        .map(|(i, _)| i);
    for (li, l) in staging.sky.lights.iter().enumerate() {
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
                out.push(Light::Directional { towards: norm([cx, cz, -cy]), colour: mul(l.color, power), sun: Some(li) == sun_index });
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
        if let Light::Directional { towards, colour, .. } = l {
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

/// How much of the sky's sun a point with a normal sees: the mean over the
/// sun's grid of its rays' transmission (0 facing away, or when the set has
/// no sun), what the masters take as "where CE's sun reaches".
pub fn sun_visibility(occ: &Occluders, lights: &[Light], p: V3, n: V3, opt: &Options) -> f32 {
    let (mut sum, mut count) = (0.0f32, 0usize);
    for l in lights {
        if let Light::Directional { towards, sun: true, .. } = l {
            count += 1;
            if dot(n, *towards) <= 0.0 {
                continue;
            }
            let t = occ.transmission(p, add(p, mul(*towards, opt.sun_ray)), false);
            sum += (t[0] + t[1] + t[2]) / 3.0;
        }
    }
    if count == 0 {
        0.0
    } else {
        sum / count as f32
    }
}

/// Everything the sky's directional lights give a point with a normal, in
/// one pass over the rays: (all of it, the sun's part of it, the sun's part
/// had nothing blocked it, the sun's visibility). The sun is the sky's
/// narrowest light (`Light::Directional::sun`).
pub fn direct_terms(occ: &Occluders, lights: &[Light], p: V3, n: V3, opt: &Options) -> (V3, V3, V3, f32) {
    let (mut gain, mut sun, mut potential) = ([0.0f32; 3], [0.0f32; 3], [0.0f32; 3]);
    let (mut vis, mut count) = (0.0f32, 0usize);
    for l in lights {
        if let Light::Directional { towards, colour, sun: is_sun } = l {
            let cos = if opt.sun_cosine { dot(n, *towards).max(0.0) } else { 1.0 };
            if *is_sun {
                count += 1;
            }
            if cos <= 0.0 {
                continue;
            }
            let unblocked = [colour[0] * cos, colour[1] * cos, colour[2] * cos];
            if *is_sun {
                potential = add(potential, unblocked);
            }
            let t = occ.transmission(p, add(p, mul(*towards, opt.sun_ray)), false);
            if t.iter().all(|x| *x <= 0.0) {
                continue;
            }
            let c = [unblocked[0] * t[0], unblocked[1] * t[1], unblocked[2] * t[2]];
            gain = add(gain, c);
            if *is_sun {
                sun = add(sun, c);
                vis += (t[0] + t[1] + t[2]) / 3.0;
            }
        }
    }
    (gain, sun, potential, if count == 0 { 0.0 } else { vis / count as f32 })
}

/// `direct_terms` plus the placed lights that reach `cluster`, which join
/// the whole but not the sun's part.
pub fn direct_terms_placed(occ: &Occluders, lights: &[Light], placed: &PlacedLights, cluster: i32, p: V3, n: V3, opt: &Options) -> (V3, V3, V3, f32) {
    let (mut gain, sun, potential, vis) = direct_terms(occ, lights, p, n, opt);
    for (i, l) in placed.lights.iter().enumerate() {
        if !placed.reaches(i, cluster) {
            continue;
        }
        if let Some((c, _)) = point_gain(l, occ, p, n) {
            gain = add(gain, c);
        }
    }
    (gain, sun, potential, vis)
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
    /// The placed lights, when the scene has any.
    pub placed: PlacedLights,
    /// Per cluster, the clusters it sees (itself included).
    visible: Vec<Vec<u32>>,
    /// Per cluster, its elements.
    by_cluster: Vec<Vec<u32>>,
    /// Which shooter lights which vertex: each shooter only the clusters
    /// its own cluster sees, as tool.exe shoots.
    vis: ClusterVis,
    /// Per element, its unshot energy `(r+g+b) x area`, kept in step with
    /// `delta`: choosing the shooters and the residual read 4 bytes an
    /// element instead of the whole element, every batch.
    energy: Vec<f32>,
    /// The last few batches' receivers and their vertices, the latest
    /// first: a map with interiors flips between a few sets of clusters seen.
    reach: Vec<Reach>,
    /// The last generation handed to a target list.
    generations: u64,
    pub steps: usize,
    pub splits: usize,
    /// Where the solve's time went.
    pub timings: Timings,
    /// Casts the gather's rays when set; a failure drops it (and records
    /// why) and the solve goes on on the CPU.
    pub gpu: Option<crate::gpu::Gpu>,
    pub gpu_error: Option<String>,
}

/// A batch's receivers: the elements of the clusters its shooters see, and
/// their vertices. The next batch reuses them while it sees the same
/// clusters (on an outdoor map, every batch).
struct Reach {
    seen: Vec<bool>,
    receivers: Vec<u32>,
    /// Per element, its index in `receivers` (`u32::MAX`: not one).
    receiving: Vec<u32>,
    targets: Targets,
}

/// The receivers' vertices. A split only adds vertices to the split
/// element's own patches, so the list grows with the splits rather than
/// being found again (a scan of every element's patches, which on a map of
/// a million elements cost more than the batch's rays).
struct Targets {
    list: Vec<u32>,
    /// Per pool vertex, its index in `list` (`u32::MAX`: not one).
    slot: Vec<u32>,
    /// Names this list's contents (unique across the cached lists), so the
    /// GPU uploads it only when it changes.
    generation: u64,
    /// Grown since `generation` was handed out.
    dirty: bool,
}

impl Targets {
    fn add(&mut self, v: u32) {
        let v = v as usize;
        if v >= self.slot.len() {
            self.slot.resize(v + 1, u32::MAX);
        }
        if self.slot[v] == u32::MAX {
            self.slot[v] = self.list.len() as u32;
            self.list.push(v as u32);
            self.dirty = true;
        }
    }
}

/// An element's unshot energy, what the brightest-first order sorts by.
fn energy_of(e: &Element) -> f32 {
    e.delta.iter().sum::<f32>() * e.patch.area
}

/// Seconds spent in each part of a solve, for `--verbose` and profiling.
#[derive(Clone, Copy, Debug, Default)]
pub struct Timings {
    /// The light phase's sky and placed lights (not its emitters' shots).
    pub light: f64,
    /// Choosing each batch's shooters and listing their receivers.
    pub select: f64,
    /// The receivers' gather: the form factors and their visibility rays.
    pub gather: f64,
    /// Adding the gathered light and splitting the receivers' patches.
    pub settle: f64,
    /// Drawing the pages (filled in by `solve`).
    pub draw: f64,
    /// ... of which the per-texel sun and fill.
    pub texel_direct: f64,
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
        let energy = elements.elements.iter().map(energy_of).collect();
        let vis = ClusterVis::new(&visible, &elements, |i| {
            let e = &elements.elements[i];
            if clusters.is_some() && e.cluster >= 0 && (e.cluster as usize) < n { e.cluster as usize } else { 0 }
        });
        Solver {
            staging,
            occluders,
            elements,
            placed: PlacedLights::default(),
            visible,
            by_cluster,
            vis,
            energy,
            reach: Vec::new(),
            generations: 0,
            steps: 0,
            splits: 0,
            timings: Timings::default(),
            gpu: None,
            gpu_error: None,
        }
    }

    /// The placed lights of `scene_lights.json`, each in the cluster of
    /// the nearest lit surface with that cluster's visibility; how many.
    pub fn load_placed(&mut self, path: &Path) -> Result<usize, String> {
        self.placed = PlacedLights::load(path, &self.elements, &self.visible)?;
        Ok(self.placed.lights.len())
    }

    fn cluster_of(&self, e: &Element) -> usize {
        if self.staging.clusters.is_some() && e.cluster >= 0 && (e.cluster as usize) < self.visible.len() {
            e.cluster as usize
        } else {
            0
        }
    }

    /// The leaf patches of an element: its children, or itself.
    fn leaves(e: &Element) -> &[Patch] {
        if e.children.is_empty() {
            std::slice::from_ref(&e.patch)
        } else {
            &e.children
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

    /// Whether a leaf patch whose corners got `s` this step splits: its
    /// corners disagree past the row's tolerance and it is not yet at the
    /// row's finest (or the element's texel floor).
    fn splits(leaf: &Patch, s: &[V3; 3], row: crate::elements::Row, floor: f32, opt: &Options) -> bool {
        opt.adaptive
            && row.gradient < f32::MAX
            && leaf.segment > 2.0 * (row.minimum * WU_TO_M).max(floor)
            && s.iter().any(|c| c.iter().any(|x| *x > 0.0))
            && (0..3).any(|k| {
                let (a, b) = (s[k], s[(k + 1) % 3]);
                (0..3).any(|c| (a[c] - b[c]).abs() >= (a[c].max(b[c]) * row.gradient).max(0.005))
            })
    }

    /// After a batch: each receiver's element gains what its leaf patches
    /// reflect of `step` (their corners' mean, weighted by area), and leaves
    /// whose corners disagree past the row's tolerance split. Both depend
    /// only on the light the existing corners got, so every receiver's gain
    /// and whether it splits are found in parallel; the splits then run in
    /// receiver order, as they add vertices to the pool.
    fn settle(&mut self, receivers: &[u32], receiving: Option<&[u32]>, step: &mut Vec<V3>, opt: &Options) -> Vec<u32> {
        let own;
        let slot = match receiving {
            Some(s) => s,
            None => {
                let mut s = vec![u32::MAX; self.elements.elements.len()];
                for (k, &ei) in receivers.iter().enumerate() {
                    s[ei as usize] = k as u32;
                }
                own = s;
                &own
            }
        };
        // One pass over the elements: each receiver's gain lands in its
        // `delta`, and whether it splits is noted (the splits leave `delta`
        // alone, so they can follow).
        let lit: &[V3] = step;
        let materials = &self.elements.materials;
        let splitting: Vec<bool> = self
            .elements
            .elements
            .par_iter_mut()
            .zip(self.energy.par_iter_mut())
            .zip(slot.par_iter())
            .map(|((e, energy), &k)| {
                if k == u32::MAX {
                    return false;
                }
                let row = opt.quality.rows[materials[e.material as usize].detail_level];
                let area = e.patch.area.max(1e-12);
                let mut gain = [0.0f32; 3];
                let mut split = false;
                for leaf in Self::leaves(e) {
                    let s = [lit[leaf.v[0] as usize], lit[leaf.v[1] as usize], lit[leaf.v[2] as usize]];
                    let mean = mul(add(add(s[0], s[1]), s[2]), 1.0 / 3.0);
                    gain = add(gain, mul(mean, leaf.area / area));
                    split = split || Self::splits(leaf, &s, row, e.floor, opt);
                }
                let r = e.reflectance;
                e.delta = add(e.delta, [gain[0] * r[0], gain[1] * r[1], gain[2] * r[2]]);
                *energy = energy_of(e);
                split
            })
            .collect();
        let mut split = Vec::new();
        for &ei in receivers {
            if splitting[ei as usize] {
                self.split_element(ei, step, opt);
                split.push(ei);
            }
        }
        split
    }

    /// The cached target lists take the corners of the patches `split`
    /// made, in the elements they receive for.
    fn note_splits(&mut self, split: &[u32]) {
        let elements = &self.elements.elements;
        for r in self.reach.iter_mut() {
            for &ei in split {
                if r.receiving[ei as usize] != u32::MAX {
                    for leaf in &elements[ei as usize].children {
                        for &v in &leaf.v {
                            r.targets.add(v);
                        }
                    }
                }
            }
            if r.targets.dirty {
                self.generations += 1;
                r.targets.generation = self.generations;
                r.targets.dirty = false;
            }
        }
    }

    /// Split the leaves of element `ei` whose corners disagree about
    /// `step`; the new vertices take their edge's light for this step.
    fn split_element(&mut self, ei: u32, step: &mut Vec<V3>, opt: &Options) {
        let (row, floor) = {
            let e = &self.elements.elements[ei as usize];
            (opt.quality.rows[self.elements.materials[e.material as usize].detail_level], e.floor)
        };
        let leaves = Self::leaves(&self.elements.elements[ei as usize]).to_vec();
        let mut new_leaves: Vec<Patch> = Vec::with_capacity(leaves.len() + 4);
        for leaf in leaves {
            let s = [step[leaf.v[0] as usize], step[leaf.v[1] as usize], step[leaf.v[2] as usize]];
            if !Self::splits(&leaf, &s, row, floor, opt) {
                new_leaves.push(leaf);
                continue;
            }
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
        }
        self.elements.elements[ei as usize].children = new_leaves;
        // The new patches' corners are on this element's cluster.
        let cluster = self.cluster_of(&self.elements.elements[ei as usize]) as u32;
        for leaf in &self.elements.elements[ei as usize].children {
            for &v in &leaf.v {
                self.vis.add(v, cluster);
            }
        }
    }

    /// The light phase: every sky light onto every vertex of its set.
    pub fn light(&mut self, opt: &Options) {
        let started = std::time::Instant::now();
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
                            Light::Point { .. } => {}
                            Light::Ambient { colour } => {
                                gain = add(gain, *colour);
                                ambient = add(ambient, *colour);
                                dir = add(dir, mul(v.n, luma(*colour)));
                            }
                            Light::Directional { towards, colour, .. } => {
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
            let split = self.settle(&receivers, None, &mut step, opt);
            self.note_splits(&split);
        }

        // The placed lights: each onto every vertex of the clusters it
        // reaches, within its reach, through its own shadow ray.
        if !self.placed.lights.is_empty() {
            let n_clusters = self.visible.len();
            let reached: Vec<bool> = (0..n_clusters).map(|c| (0..self.placed.lights.len()).any(|i| self.placed.reaches(i, c as i32))).collect();
            let receivers: Vec<u32> = (0..self.elements.elements.len() as u32)
                .filter(|&i| {
                    let c = self.elements.elements[i as usize].cluster;
                    c < 0 || reached.get(c as usize).copied().unwrap_or(true)
                })
                .collect();
            let mut seen = vec![false; self.elements.pool.vertices.len()];
            let mut targets: Vec<(u32, i32)> = Vec::new();
            for &ei in &receivers {
                let e = &self.elements.elements[ei as usize];
                for p in Self::leaves(e) {
                    for v in p.v {
                        if !seen[v as usize] {
                            seen[v as usize] = true;
                            targets.push((v, e.cluster));
                        }
                    }
                }
            }
            let vertices = &self.elements.pool.vertices;
            let placed = &self.placed;
            let gains: Vec<(V3, V3)> = targets
                .par_iter()
                .map(|&(vi, cluster)| {
                    let v = &vertices[vi as usize];
                    let mut gain = [0.0f32; 3];
                    let mut dir = [0.0f32; 3];
                    for (i, l) in placed.lights.iter().enumerate() {
                        if !placed.reaches(i, cluster) {
                            continue;
                        }
                        if let Some((c, d)) = point_gain(l, occ, v.p, v.n) {
                            gain = add(gain, c);
                            dir = add(dir, mul(d, luma(c)));
                        }
                    }
                    (gain, dir)
                })
                .collect();
            let mut step = vec![[0.0f32; 3]; self.elements.pool.vertices.len()];
            for (&(vi, _), (gain, dir)) in targets.iter().zip(&gains) {
                let v = &mut self.elements.pool.vertices[vi as usize];
                v.total = add(v.total, *gain);
                v.dir = add(v.dir, *dir);
                v.placed = add(v.placed, *gain);
                step[vi as usize] = *gain;
            }
            let split = self.settle(&receivers, None, &mut step, opt);
            self.note_splits(&split);
        }

        self.timings.light += started.elapsed().as_secs_f64();

        // The emitting surfaces (shaders with a radiosity power: lamps,
        // light strips) shoot now, every one, as the lights they are. The
        // progressive loop's stop is an area-weighted mean, which starves a
        // few bright square metres on a large map: Death Island's strips
        // never shot, while tool.exe's pages carry their light.
        let emitters: Vec<u32> = (0..self.elements.elements.len() as u32)
            .filter(|&i| {
                let e = &self.elements.elements[i as usize];
                e.delta.iter().any(|c| *c > 0.0) && self.elements.materials[e.material as usize].emission.iter().any(|c| *c > 0.0)
            })
            .collect();
        for batch in emitters.chunks(opt.batch.max(1)) {
            self.shoot(batch, opt);
        }
    }

    /// tool.exe's lightmap shows an emitting surface its own emission on
    /// top of what it gathers (a patch's radiosity starts at its emission:
    /// the strips' own charts are saturated in CE's pages). Each vertex of
    /// an emitting element takes the brightest emission among its elements.
    pub fn add_emission(&mut self) {
        let mut best: Vec<Option<V3>> = vec![None; self.elements.pool.vertices.len()];
        for e in &self.elements.elements {
            let em = self.elements.materials[e.material as usize].emission;
            if em.iter().all(|c| *c <= 0.0) {
                continue;
            }
            for p in Self::leaves(e) {
                for v in p.v {
                    let b = &mut best[v as usize];
                    if b.map(|x| luma(em) > luma(x)).unwrap_or(true) {
                        *b = Some(em);
                    }
                }
            }
        }
        for (vi, b) in best.into_iter().enumerate() {
            if let Some(em) = b {
                let v = &mut self.elements.pool.vertices[vi];
                v.total = add(v.total, em);
            }
        }
    }

    /// The area-weighted mean unshot energy, tool.exe's printed residual.
    pub fn residual(&self) -> f32 {
        // In element order, as the sum always ran (a different order rounds
        // differently, and the stop would move).
        let total: f32 = self.energy.iter().sum();
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
        let started = std::time::Instant::now();
        // The `batch` brightest, ties in element order (what a stable sort of
        // the whole list gives): a few dozen chunks each keep their own best
        // few, sorted, and their lists sort together. (A rayon fold merged
        // thousands of pieces, K x K each: 5 ms a batch on a million
        // elements.)
        let k = opt.batch.max(1);
        let brighter = |a: &(f32, u32), b: &(f32, u32)| b.0.partial_cmp(&a.0).unwrap().then(a.1.cmp(&b.1));
        let chunk = (self.energy.len() / (rayon::current_num_threads() * 2).max(1)).max(4096);
        let mut order: Vec<(f32, u32)> = self
            .energy
            .par_chunks(chunk)
            .enumerate()
            .flat_map_iter(|(c, part)| {
                let mut top: Vec<(f32, u32)> = Vec::with_capacity(k + 1);
                for (j, &energy) in part.iter().enumerate() {
                    if energy <= 0.0 {
                        continue;
                    }
                    let x = (energy, (c * chunk + j) as u32);
                    if top.len() == k && brighter(&x, top.last().unwrap()) != std::cmp::Ordering::Less {
                        continue;
                    }
                    let at = top.partition_point(|y| brighter(y, &x) == std::cmp::Ordering::Less);
                    top.insert(at, x);
                    top.truncate(k);
                }
                top
            })
            .collect();
        order.sort_by(brighter);
        order.truncate(k);
        if order.is_empty() {
            return false;
        }
        let shooters: Vec<u32> = order.iter().map(|x| x.1).collect();
        self.timings.select += started.elapsed().as_secs_f64();
        self.shoot(&shooters, opt);
        true
    }

    /// `shooters` shoot their unshot energy; every vertex they can reach
    /// gathers, and the receivers settle.
    fn shoot(&mut self, shooters: &[u32], opt: &Options) {
        let started = std::time::Instant::now();
        // The receivers: every element in a cluster any shooter sees.
        let mut seen = vec![false; self.visible.len()];
        for &s in shooters {
            let g = self.cluster_of(&self.elements.elements[s as usize]);
            for &h in &self.visible[g] {
                seen[h as usize] = true;
            }
        }
        let reach = match self.reach.iter().position(|r| r.seen == seen) {
            Some(i) => self.reach.remove(i),
            None => {
                let mut receivers: Vec<u32> = Vec::new();
                for (g, &on) in seen.iter().enumerate() {
                    if on {
                        receivers.extend(self.by_cluster[g].iter().copied());
                    }
                }
                let list = self.vertices_of(&receivers);
                let mut slot = vec![u32::MAX; self.elements.pool.vertices.len()];
                for (k, &v) in list.iter().enumerate() {
                    slot[v as usize] = k as u32;
                }
                let mut receiving = vec![u32::MAX; self.elements.elements.len()];
                for (k, &ei) in receivers.iter().enumerate() {
                    receiving[ei as usize] = k as u32;
                }
                self.generations += 1;
                Reach { seen, receivers, receiving, targets: Targets { list, slot, generation: self.generations, dirty: false } }
            }
        };
        let targets = &reach.targets.list;

        let elements = &self.elements;
        let occ = self.occluders;
        let cull = 1e-4;
        let shooter_data: Vec<(&Element, [V3; 3], usize)> = shooters
            .iter()
            .map(|&s| {
                let e = &elements.elements[s as usize];
                let sv = [
                    elements.pool.vertices[e.patch.v[0] as usize].p,
                    elements.pool.vertices[e.patch.v[1] as usize].p,
                    elements.pool.vertices[e.patch.v[2] as usize].p,
                ];
                (e, sv, self.cluster_of(e))
            })
            .collect();
        let gathering = std::time::Instant::now();
        // The rays, on the GPU when there is one (the solid test needs the
        // vertices' faces, which only the CPU path has).
        let on_gpu = match self.gpu.as_mut() {
            Some(g) if !opt.solid_test => match g.gather(elements, shooters, &shooter_data.iter().map(|x| x.2 as u32).collect::<Vec<_>>(), targets, reach.targets.generation, cull, &mut self.vis) {
                Ok(v) => Some(v),
                Err(e) => {
                    self.gpu = None;
                    self.gpu_error = Some(e);
                    None
                }
            },
            _ => None,
        };
        let vis = &self.vis;
        let gains: Vec<(V3, V3)> = if let Some(v) = on_gpu {
            v
        } else {
            targets
            .par_iter()
            .map(|&vi| {
                let rv = &elements.pool.vertices[vi as usize];
                let mut gain = [0.0f32; 3];
                let mut dir = [0.0f32; 3];
                for (e, sv, cluster) in &shooter_data {
                    if !vis.sees(*cluster, vi) {
                        continue;
                    }
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
            .collect()
        };

        let gathered = std::time::Instant::now();
        self.timings.gather += (gathered - gathering).as_secs_f64();
        self.timings.select += (gathering - started).as_secs_f64();
        let mut step = vec![[0.0f32; 3]; self.elements.pool.vertices.len()];
        self.elements.pool.vertices.par_iter_mut().zip(step.par_iter_mut()).zip(reach.targets.slot.par_iter()).for_each(|((v, s), &k)| {
            if k != u32::MAX {
                let (gain, dir) = gains[k as usize];
                v.total = add(v.total, gain);
                v.dir = add(v.dir, dir);
                *s = gain;
            }
        });
        for &s in shooters {
            self.elements.elements[s as usize].delta = [0.0; 3];
            self.energy[s as usize] = 0.0;
        }
        let split = self.settle(&reach.receivers, Some(&reach.receiving), &mut step, opt);
        self.reach.insert(0, reach);
        self.reach.truncate(4);
        self.note_splits(&split);
        self.timings.settle += gathered.elapsed().as_secs_f64();
        self.steps += shooters.len();
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
        self.add_emission();
    }
}
