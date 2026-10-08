//! Bake what a converted CE level's lightmaps leave out, one texture per
//! lightmap page, on the same UVs.
//!
//! ```text
//! cargo run --release -p ue-texture --example lightmap_bake -- \
//!     <scene.gltf> <lightmap page 0.png> <out dir> \
//!     [--max-size 2048] [--max-scale 16] [--ao-radius 1.0] [--ao-rays 48] \
//!     [--sun-rays 8] [--threads 6] [--ao-smooth 0] [--ao-knee 0.85]
//!     [--ao-curve 1.3] [--sun-mask-cell 1.0] [--sun x,y,z]
//! ```
//!
//! CE lit its levels with radiosity lightmaps of a few metres a texel, so the
//! seams where a wall meets the floor are as bright as the open floor, and an
//! Unreal object shadow cannot tell a CE shadow from lamp light (the base
//! interiors are bright from their lights, not the sun). Per texel, traced
//! against the level's own geometry (`merge_ce_scene.py`'s scene: the BSP and
//! the scenery placed on it):
//!
//! - R: ambient occlusion, how open the texel is within `--ao-radius`
//!   (cosine-weighted, hits weighted by closeness), 1 = open, optionally
//!   smoothed over the surface within `--ao-smooth` metres, then divided by
//!   `--ao-knee` (capped at 1) and raised to `--ao-curve`, so mild folds read
//!   as open and real corners keep their darkness;
//! - G: sun visibility, the share of `--sun-rays` rays inside a 1 degree cone
//!   around the sun that leave the level, 1 = in the sun;
//! - B: sky visibility, the share of `--sky-rays` cosine-weighted rays that
//!   leave the level, smoothed over `--sky-fine` m of surface.
//! - A: the texel's chart (chart_ids, 1-255; 0 none), so the masters'
//!   filters never reach into a neighbouring chart.
//!
//! The sun is CE's own, from the lightmap vertices' incident directions over
//! flat ground (as `tools/level/gen_ce_level.py` finds it for the Unreal
//! sun). A page is baked at a multiple of its lightmap's size, the largest
//! that keeps it within `--max-size` and `--max-scale`: the lightmaps are far
//! too coarse to hold a corner. Pages are named for the glTF materials' `__lmN`
//! suffix: page N is `<page 0 stem>_N.png` beside page 0; the output is named
//! for the cooked lightmap texture it goes with (`T_<stem>`, `T_<stem>_nN`).
//! glTF units are metres, y up.

use std::path::{Path, PathBuf};

type V3 = [f32; 3];

fn sub(a: V3, b: V3) -> V3 {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}
fn add(a: V3, b: V3) -> V3 {
    [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
}
fn mul(a: V3, s: f32) -> V3 {
    [a[0] * s, a[1] * s, a[2] * s]
}
fn dot(a: V3, b: V3) -> f32 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}
fn cross(a: V3, b: V3) -> V3 {
    [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
}
fn norm(a: V3) -> V3 {
    let l = dot(a, a).sqrt();
    if l > 1e-12 {
        mul(a, 1.0 / l)
    } else {
        [0.0, 1.0, 0.0]
    }
}

// --- glTF ---------------------------------------------------------------

struct Gltf {
    doc: serde_json::Value,
    bin: Vec<u8>,
}

impl Gltf {
    fn load(path: &Path) -> Gltf {
        let doc: serde_json::Value =
            serde_json::from_slice(&std::fs::read(path).expect("read glTF")).expect("parse glTF");
        let uri = doc["buffers"][0]["uri"].as_str().expect("buffer uri");
        let bin = std::fs::read(path.parent().unwrap().join(uri)).expect("read glTF buffer");
        Gltf { doc, bin }
    }

    fn view(&self, index: usize) -> (usize, usize, usize, u64) {
        let acc = &self.doc["accessors"][index];
        let count = acc["count"].as_u64().unwrap() as usize;
        let view = &self.doc["bufferViews"][acc["bufferView"].as_u64().unwrap() as usize];
        let base = view["byteOffset"].as_u64().unwrap_or(0) as usize
            + acc["byteOffset"].as_u64().unwrap_or(0) as usize;
        let stride = view["byteStride"].as_u64().unwrap_or(0) as usize;
        (count, base, stride, acc["componentType"].as_u64().unwrap())
    }

    fn floats(&self, index: usize, comps: usize) -> Vec<f32> {
        let (count, base, stride, _) = self.view(index);
        let step = if stride > 0 { stride } else { comps * 4 };
        let mut out = Vec::with_capacity(count * comps);
        for i in 0..count {
            for c in 0..comps {
                let at = base + i * step + c * 4;
                out.push(f32::from_le_bytes(self.bin[at..at + 4].try_into().unwrap()));
            }
        }
        out
    }

    fn indices(&self, index: usize) -> Vec<u32> {
        let (count, base, _, kind) = self.view(index);
        (0..count)
            .map(|i| match kind {
                5125 => u32::from_le_bytes(self.bin[base + i * 4..base + i * 4 + 4].try_into().unwrap()),
                5123 => u16::from_le_bytes(self.bin[base + i * 2..base + i * 2 + 2].try_into().unwrap()) as u32,
                5121 => self.bin[base + i] as u32,
                k => panic!("index component type {k}"),
            })
            .collect()
    }
}

// --- BVH ----------------------------------------------------------------

struct Node {
    min: V3,
    max: V3,
    /// Leaf: first triangle; inner: right child (left is the next node).
    index: u32,
    /// Leaf: triangle count; inner: 0.
    count: u32,
}

struct Bvh {
    nodes: Vec<Node>,
    tris: Vec<[V3; 3]>,
}

impl Bvh {
    fn build(mut tris: Vec<[V3; 3]>) -> Bvh {
        let mut nodes = Vec::new();
        let n = tris.len();
        Self::split(&mut tris, 0, n, &mut nodes);
        Bvh { nodes, tris }
    }

    fn split(tris: &mut [[V3; 3]], first: usize, end: usize, nodes: &mut Vec<Node>) -> usize {
        let mut min = [f32::MAX; 3];
        let mut max = [f32::MIN; 3];
        for t in &tris[first..end] {
            for v in t {
                for k in 0..3 {
                    min[k] = min[k].min(v[k]);
                    max[k] = max[k].max(v[k]);
                }
            }
        }
        let me = nodes.len();
        nodes.push(Node { min, max, index: first as u32, count: (end - first) as u32 });
        if end - first <= 4 {
            return me;
        }
        let ext = sub(max, min);
        let axis = if ext[0] >= ext[1] && ext[0] >= ext[2] { 0 } else if ext[1] >= ext[2] { 1 } else { 2 };
        let centre = |t: &[V3; 3]| t[0][axis] + t[1][axis] + t[2][axis];
        tris[first..end].sort_by(|a, b| centre(a).partial_cmp(&centre(b)).unwrap());
        let mid = (first + end) / 2;
        Self::split(tris, first, mid, nodes);
        let right = Self::split(tris, mid, end, nodes);
        nodes[me].index = right as u32;
        nodes[me].count = 0;
        me
    }

    /// Whether anything lies along `o + t d` for `t` in (0, `tmax`); the
    /// nearest hit's `t` when `nearest`.
    fn hit(&self, o: V3, d: V3, tmax: f32, nearest: bool) -> Option<f32> {
        let inv = [1.0 / d[0], 1.0 / d[1], 1.0 / d[2]];
        let mut best = tmax;
        let mut found = false;
        let mut stack = [0u32; 64];
        let mut sp = 1;
        while sp > 0 {
            sp -= 1;
            let node = &self.nodes[stack[sp] as usize];
            let mut t0 = 0.0f32;
            let mut t1 = best;
            for k in 0..3 {
                let a = (node.min[k] - o[k]) * inv[k];
                let b = (node.max[k] - o[k]) * inv[k];
                t0 = t0.max(a.min(b));
                t1 = t1.min(a.max(b));
            }
            if t0 > t1 {
                continue;
            }
            if node.count > 0 {
                for tri in &self.tris[node.index as usize..(node.index + node.count) as usize] {
                    // Moller-Trumbore, both faces.
                    let e1 = sub(tri[1], tri[0]);
                    let e2 = sub(tri[2], tri[0]);
                    let p = cross(d, e2);
                    let det = dot(e1, p);
                    if det.abs() < 1e-12 {
                        continue;
                    }
                    let inv_det = 1.0 / det;
                    let s = sub(o, tri[0]);
                    let u = dot(s, p) * inv_det;
                    if !(0.0..=1.0).contains(&u) {
                        continue;
                    }
                    let q = cross(s, e1);
                    let v = dot(d, q) * inv_det;
                    if v < 0.0 || u + v > 1.0 {
                        continue;
                    }
                    let t = dot(e2, q) * inv_det;
                    if t > 1e-5 && t < best {
                        if !nearest {
                            return Some(t);
                        }
                        best = t;
                        found = true;
                    }
                }
            } else {
                let me = stack[sp] as usize;
                stack[sp] = (me + 1) as u32;
                stack[sp + 1] = node.index;
                sp += 2;
            }
        }
        found.then_some(best)
    }
}

// --- sampling -----------------------------------------------------------

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> f32 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        (self.0 >> 40) as f32 / (1u64 << 24) as f32
    }
}

/// An orthonormal frame around `n`.
fn frame(n: V3) -> (V3, V3) {
    let a = if n[0].abs() > 0.9 { [0.0, 1.0, 0.0] } else { [1.0, 0.0, 0.0] };
    let t = norm(cross(a, n));
    (t, cross(n, t))
}

struct Sample {
    pixel: usize,
    p: V3,
    face: V3,
}

struct Settings {
    ao_radius: f32,
    ao_rays: usize,
    sun_rays: usize,
    sky_rays: usize,
    sun: V3,
}

/// (ao, sun visibility) for one texel.
fn bake(bvh: &Bvh, s: &Sample, cfg: &Settings, rng: &mut Rng) -> (f32, f32, f32) {
    // Off the surface along its own face, so the ray never meets the
    // triangle it starts on.
    let o = add(s.p, mul(s.face, 0.02));
    // The hemisphere is the face's own: CE's vertex normals are smoothed
    // across corners, and a tilted one sends rays into the surface (streaks
    // along every seam, varying vertex to vertex).
    let (t, b) = frame(s.face);
    let side = (cfg.ao_rays as f32).sqrt().ceil() as usize;
    let mut occluded = 0.0;
    let mut rays = 0;
    for i in 0..side {
        for j in 0..side {
            if rays == cfg.ao_rays {
                break;
            }
            rays += 1;
            // Cosine-weighted, stratified.
            let u1 = (i as f32 + rng.next()) / side as f32;
            let u2 = (j as f32 + rng.next()) / side as f32;
            let r = u1.sqrt();
            let phi = std::f32::consts::TAU * u2;
            let z = (1.0 - u1).max(0.0).sqrt();
            let d = norm(add(add(mul(t, r * phi.cos()), mul(b, r * phi.sin())), mul(s.face, z)));
            if dot(d, s.face) <= 0.0 {
                occluded += 1.0;
                continue;
            }
            if let Some(hit) = bvh.hit(o, d, cfg.ao_radius, true) {
                occluded += 1.0 - hit / cfg.ao_radius;
            }
        }
    }
    let ao = 1.0 - occluded / rays as f32;

    let mut lit = 0;
    if dot(s.face, cfg.sun) > 0.0 {
        let (st, sb) = frame(cfg.sun);
        let cone = 1.0f32.to_radians().tan();
        for _ in 0..cfg.sun_rays {
            let r = rng.next().sqrt() * cone;
            let phi = std::f32::consts::TAU * rng.next();
            let d = norm(add(cfg.sun, add(mul(st, r * phi.cos()), mul(sb, r * phi.sin()))));
            if bvh.hit(o, d, 1e5, false).is_none() {
                lit += 1;
            }
        }
    }
    // Sky visibility: cosine-weighted about the face, the share of rays that
    // leave the level at any distance.
    let mut open = 0;
    let (ft, fb) = frame(s.face);
    for _ in 0..cfg.sky_rays {
        let (u1, u2) = (rng.next(), rng.next());
        let r = u1.sqrt();
        let phi = std::f32::consts::TAU * u2;
        let z = (1.0 - u1).max(0.0).sqrt();
        let d = norm(add(add(mul(ft, r * phi.cos()), mul(fb, r * phi.sin())), mul(s.face, z)));
        if bvh.hit(o, d, 1e5, false).is_none() {
            open += 1;
        }
    }
    let sky = if cfg.sky_rays > 0 { open as f32 / cfg.sky_rays as f32 } else { 1.0 };
    (ao, lit as f32 / cfg.sun_rays as f32, sky)
}

/// The covered texels' charts, 4-connected islands of a page, as alpha
/// values 1..=255 spread so that neighbouring charts differ; 0 is no chart.
fn chart_ids(have: &[bool], w: usize, h: usize) -> Vec<u8> {
    let mut label = vec![0u32; w * h];
    let mut next = 0u32;
    let mut stack = Vec::new();
    for start in 0..w * h {
        if !have[start] || label[start] != 0 {
            continue;
        }
        next += 1;
        label[start] = next;
        stack.push(start);
        while let Some(i) = stack.pop() {
            let (x, y) = (i % w, i / w);
            let mut visit = |j: usize| {
                if have[j] && label[j] == 0 {
                    label[j] = next;
                    stack.push(j);
                }
            };
            if x > 0 { visit(i - 1); }
            if x + 1 < w { visit(i + 1); }
            if y > 0 { visit(i - w); }
            if y + 1 < h { visit(i + w); }
        }
    }
    label
        .iter()
        .map(|&l| if l == 0 { 0 } else { (1 + (l.wrapping_mul(97) % 255)) as u8 })
        .collect()
}

/// One lightmap page, baked and not yet written.
struct Baked {
    page: usize,
    name: String,
    lw: usize,
    lh: usize,
    scale: usize,
    w: usize,
    h: usize,
    samples: Vec<Sample>,
    /// (pixel, ao, sun visibility), in `samples`' order.
    results: Vec<(usize, f32, f32)>,
    /// Sky visibility, in the same order.
    sky: Vec<f32>,
    secs: f32,
}

/// The corners' occlusion averaged over the surface around each texel, in
/// world space: a Gaussian out to `radius`, across facets and pages alike,
/// leaving out surfaces that face away (the far side of a thin wall). Traced
/// per texel, the occlusion steps at every fold of a low-poly cliff, and
/// texels of ~0.4 m against a 1 m radius drew a crease's darkest line as
/// teeth (Blood Gulch, 2026-10-05); CE smoothed its own shading over the
/// same facets. Only surfaces within 45 degrees of each other blend.
/// Returns the texels smoothed.
fn smooth_ao(baked: &mut [Baked], radius: f32, threads: usize) -> usize {
    let pts: Vec<(V3, V3, f32)> = baked
        .iter()
        .flat_map(|b| b.samples.iter().zip(&b.results).map(|(s, r)| (s.p, s.face, r.1)))
        .collect();
    let smoothed = world_blur(&pts, radius, threads);
    let mut k = 0;
    for b in baked.iter_mut() {
        for r in b.results.iter_mut() {
            r.1 = smoothed[k];
            k += 1;
        }
    }
    k
}

/// Each point's value averaged over the points around it in world space: a
/// Gaussian out to `radius`, over surfaces within 45 degrees of its own (so
/// a wall does not take a floor's values, nor the far side of a thin wall
/// its near side's), across facets and pages alike.
fn world_blur(pts: &[(V3, V3, f32)], radius: f32, threads: usize) -> Vec<f32> {
    use std::collections::HashMap;
    let key = |p: V3| ((p[0] / radius).floor() as i32, (p[1] / radius).floor() as i32, (p[2] / radius).floor() as i32);
    let mut grid: HashMap<(i32, i32, i32), Vec<u32>> = HashMap::new();
    for (i, pt) in pts.iter().enumerate() {
        grid.entry(key(pt.0)).or_default().push(i as u32);
    }
    let two_sigma2 = 2.0 * (radius * 0.5) * (radius * 0.5);
    let chunk = pts.len().div_ceil(threads.max(1)).max(1);
    std::thread::scope(|scope| {
        let handles: Vec<_> = (0..pts.len())
            .collect::<Vec<_>>()
            .chunks(chunk)
            .map(|part| {
                let part = part.to_vec();
                let grid = &grid;
                scope.spawn(move || {
                    part.iter()
                        .map(|&i| {
                            let (p, n, own) = pts[i];
                            let (kx, ky, kz) = key(p);
                            let (mut sum, mut wsum) = (0.0f32, 0.0f32);
                            for dx in -1..=1 {
                                for dy in -1..=1 {
                                    for dz in -1..=1 {
                                        let Some(cell) = grid.get(&(kx + dx, ky + dy, kz + dz)) else { continue };
                                        for &j in cell {
                                            let (q, m, v) = pts[j as usize];
                                            let d = sub(q, p);
                                            let d2 = dot(d, d);
                                            if d2 > radius * radius || dot(m, n) < 0.707 {
                                                continue;
                                            }
                                            let wt = (-d2 / two_sigma2).exp();
                                            sum += wt * v;
                                            wsum += wt;
                                        }
                                    }
                                }
                            }
                            if wsum > 0.0 { sum / wsum } else { own }
                        })
                        .collect::<Vec<_>>()
                })
            })
            .collect();
        handles.into_iter().flat_map(|h| h.join().unwrap()).collect()
    })
}


fn arg<T: std::str::FromStr>(args: &[String], name: &str, default: T) -> T {
    args.iter()
        .position(|a| a == name)
        .and_then(|i| args.get(i + 1))
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
}

/// The cooked lightmap texture's name for a page stem, as
/// `tools/level/ce_material_spec.py`'s `asset_name` makes it: `T_`, anything
/// outside `[A-Za-z0-9_]` as `_`, and a trailing `_<digits>` as `_n<digits>`
/// (Unreal would read it as an FName instance number).
fn asset_name(stem: &str) -> String {
    let name: String = format!("T_{stem}")
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() || c == '_' { c } else { '_' })
        .collect();
    match name.rsplit_once('_') {
        Some((head, digits)) if !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_digit()) => {
            format!("{head}_n{digits}")
        }
        _ => name,
    }
}

fn read_png_size(path: &Path) -> Option<(usize, usize)> {
    let decoder = png::Decoder::new(std::fs::File::open(path).ok()?);
    let reader = decoder.read_info().ok()?;
    let info = reader.info();
    Some((info.width as usize, info.height as usize))
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 4 {
        eprintln!("usage: lightmap_bake <scene.gltf> <lightmap page 0.png> <out dir> [options]");
        std::process::exit(2);
    }
    let gltf = Gltf::load(Path::new(&args[1]));
    let page0 = PathBuf::from(&args[2]);
    let out = PathBuf::from(&args[3]);
    std::fs::create_dir_all(&out).expect("out dir");
    let max_size: usize = arg(&args, "--max-size", 2048);
    let max_scale: usize = arg(&args, "--max-scale", 16);
    let threads: usize = arg(&args, "--threads", 6);
    // `--sun-mask-only`: no trace and no bake pages, only the sun mask, from
    // the pages in `--sun-mask-pages` (default: page 0's folder) at whatever
    // size they are (sharpen_lightmap.py's, at the bake's resolution).
    let mask_only = args.iter().any(|a| a == "--sun-mask-only");
    let mask_pages: Option<PathBuf> =
        args.iter().position(|a| a == "--sun-mask-pages").and_then(|i| args.get(i + 1)).map(PathBuf::from);

    // Every triangle occludes; the ones on a lightmap page are also baked.
    struct Receiver {
        page: usize,
        p: [V3; 3],
        n: [V3; 3],
        uv: [[f32; 2]; 3],
    }
    let mut tris = Vec::new();
    let mut receivers = Vec::new();
    let mut sun_sum = [0.0f32; 3];
    // The box over every position, as mesh_rewrite bounds the mesh: the
    // spawned terrain sits at its centre (SunMask's frame).
    let mut lo = [f32::MAX; 3];
    let mut hi = [f32::MIN; 3];
    for mesh in gltf.doc["meshes"].as_array().unwrap() {
        for prim in mesh["primitives"].as_array().unwrap() {
            let at = &prim["attributes"];
            let pos = gltf.floats(at["POSITION"].as_u64().unwrap() as usize, 3);
            for v in pos.chunks_exact(3) {
                for k in 0..3 {
                    lo[k] = lo[k].min(v[k]);
                    hi[k] = hi[k].max(v[k]);
                }
            }
            let nrm = at["NORMAL"].as_u64().map(|i| gltf.floats(i as usize, 3));
            let idx = gltf.indices(prim["indices"].as_u64().unwrap() as usize);
            let v = |i: u32| -> V3 { let i = i as usize * 3; [pos[i], pos[i + 1], pos[i + 2]] };
            let page = prim["material"]
                .as_u64()
                .and_then(|m| gltf.doc["materials"][m as usize]["name"].as_str())
                .and_then(|name| name.rsplit_once("__lm"))
                .and_then(|(_, n)| n.parse::<usize>().ok());
            let uv1 = at["TEXCOORD_1"].as_u64().map(|i| gltf.floats(i as usize, 2));
            if let (Some(inc), Some(n)) = (at["_INCIDENT"].as_u64(), &nrm) {
                let inc = gltf.floats(inc as usize, 3);
                for i in 0..pos.len() / 3 {
                    let d = [inc[i * 3], inc[i * 3 + 1], inc[i * 3 + 2]];
                    if n[i * 3 + 1] > 0.95 && dot(d, d).sqrt() > 0.5 {
                        sun_sum = add(sun_sum, d);
                    }
                }
            }
            for t in idx.chunks_exact(3) {
                let p = [v(t[0]), v(t[1]), v(t[2])];
                tris.push(p);
                if let (Some(page), Some(uv1), Some(n)) = (page, &uv1, &nrm) {
                    let nv = |i: u32| -> V3 { let i = i as usize * 3; [n[i], n[i + 1], n[i + 2]] };
                    let uv = |i: u32| -> [f32; 2] { let i = i as usize * 2; [uv1[i], uv1[i + 1]] };
                    receivers.push(Receiver {
                        page,
                        p,
                        n: [nv(t[0]), nv(t[1]), nv(t[2])],
                        uv: [uv(t[0]), uv(t[1]), uv(t[2])],
                    });
                }
            }
        }
    }
    // `--sun x,y,z`: the direction towards the sun in glTF space (metres, y
    // up), e.g. from the sky tag's own sun. Without it, the lightmap
    // vertices' incident directions over flat ground, which blend the sun
    // with the sky's fill and sit far too steep (Danger Canyon 87 against
    // the sky tag's 35 degrees, 2026-10-07).
    let sun = match args.iter().position(|a| a == "--sun").and_then(|i| args.get(i + 1)) {
        Some(v) => {
            let c: Vec<f32> = v.split(',').map(|x| x.trim().parse().expect("--sun x,y,z")).collect();
            assert!(c.len() == 3, "--sun takes x,y,z");
            norm([c[0], c[1], c[2]])
        }
        None => norm(sun_sum),
    };
    println!("{} triangle(s), {} on lightmap pages; sun (towards) {:?}", tris.len(), receivers.len(), sun);
    let bvh = Bvh::build(tris);
    let cfg = Settings {
        ao_radius: arg(&args, "--ao-radius", 1.0),
        ao_rays: arg(&args, "--ao-rays", 48),
        sun_rays: arg(&args, "--sun-rays", 8),
        sky_rays: arg(&args, "--sky-rays", 128),
        sun,
    };

    let stem = page0.file_stem().unwrap().to_string_lossy().to_string();
    let dir = page0.parent().unwrap().to_path_buf();
    let mut pages: Vec<usize> = receivers.iter().map(|r| r.page).collect();
    pages.sort();
    pages.dedup();
    let mut baked = Vec::new();
    for page in pages {
        let name = if page == 0 { stem.clone() } else { format!("{stem}_{page}") };
        let Some((lw, lh)) = read_png_size(&dir.join(format!("{name}.png"))) else {
            println!("page {page}: no {name}.png, skipped");
            continue;
        };
        let scale = (max_size / lw.max(lh)).clamp(1, max_scale);
        let (w, h) = (lw * scale, lh * scale);

        // Rasterise the page's triangles in UV space, one sample per texel
        // centre they cover.
        let mut taken = vec![false; w * h];
        let mut samples = Vec::new();
        for r in receivers.iter().filter(|r| r.page == page) {
            let px: Vec<[f32; 2]> = r.uv.iter().map(|uv| [uv[0] * w as f32, uv[1] * h as f32]).collect();
            let area = (px[1][0] - px[0][0]) * (px[2][1] - px[0][1]) - (px[2][0] - px[0][0]) * (px[1][1] - px[0][1]);
            if area.abs() < 1e-12 {
                continue;
            }
            let face0 = norm(cross(sub(r.p[1], r.p[0]), sub(r.p[2], r.p[0])));
            let avg = add(add(r.n[0], r.n[1]), r.n[2]);
            let face = if dot(face0, avg) < 0.0 { mul(face0, -1.0) } else { face0 };
            let x0 = px.iter().map(|p| p[0]).fold(f32::MAX, f32::min).floor().max(0.0) as usize;
            let x1 = (px.iter().map(|p| p[0]).fold(f32::MIN, f32::max).ceil() as usize).min(w);
            let y0 = px.iter().map(|p| p[1]).fold(f32::MAX, f32::min).floor().max(0.0) as usize;
            let y1 = (px.iter().map(|p| p[1]).fold(f32::MIN, f32::max).ceil() as usize).min(h);
            for y in y0..y1 {
                for x in x0..x1 {
                    let (cx, cy) = (x as f32 + 0.5, y as f32 + 0.5);
                    let w0 = ((px[1][0] - cx) * (px[2][1] - cy) - (px[2][0] - cx) * (px[1][1] - cy)) / area;
                    let w1 = ((px[2][0] - cx) * (px[0][1] - cy) - (px[0][0] - cx) * (px[2][1] - cy)) / area;
                    let w2 = 1.0 - w0 - w1;
                    let e = -1e-4;
                    if w0 < e || w1 < e || w2 < e || taken[y * w + x] {
                        continue;
                    }
                    taken[y * w + x] = true;
                    let p = add(add(mul(r.p[0], w0), mul(r.p[1], w1)), mul(r.p[2], w2));
                    samples.push(Sample { pixel: y * w + x, p, face });
                }
            }
        }

        let started = std::time::Instant::now();
        if mask_only {
            baked.push(Baked { page, name, lw, lh, scale, w, h, samples, results: Vec::new(), sky: Vec::new(), secs: 0.0 });
            continue;
        }
        let chunk = samples.len().div_ceil(threads).max(1);
        let full: Vec<(usize, f32, f32, f32)> = std::thread::scope(|scope| {
            let handles: Vec<_> = samples
                .chunks(chunk)
                .enumerate()
                .map(|(k, part)| {
                    let bvh = &bvh;
                    let cfg = &cfg;
                    scope.spawn(move || {
                        let _ = k;
                        part.iter()
                            .map(|s| {
                                // Seeded per texel, so neighbours never share
                                // a run of the sequence.
                                let mut seed = (s.pixel as u64 + 1).wrapping_mul(0x9E37_79B9_7F4A_7C15)
                                    ^ ((page as u64) << 48);
                                seed ^= seed >> 31;
                                let mut rng = Rng(seed | 1);
                                let (ao, vis, sky) = bake(bvh, s, cfg, &mut rng);
                                (s.pixel, ao, vis, sky)
                            })
                            .collect::<Vec<_>>()
                    })
                })
                .collect();
            handles.into_iter().flat_map(|h| h.join().unwrap()).collect()
        });
        let results: Vec<(usize, f32, f32)> = full.iter().map(|r| (r.0, r.1, r.2)).collect();
        let sky: Vec<f32> = full.iter().map(|r| r.3).collect();
        baked.push(Baked { page, name, lw, lh, scale, w, h, samples, results, sky, secs: started.elapsed().as_secs_f32() });
    }

    // Off by default: smoothed over the AO radius, a wall's foot lost the
    // darkness it had and drew dashes (Blood Gulch, 2026-10-06), and the
    // knee and the masters' 3 x 3 tent already take the cliffs' facets out.
    // B is the sky visibility itself, smoothed against the rays' noise
    // (`--sky-fine`). The masters tell a coarse lightmap's sun leak (an open
    // face) from lamp light (an interior) by it.
    if cfg.sky_rays > 0 && !mask_only {
        let pts: Vec<(V3, V3, f32)> = baked
            .iter()
            .flat_map(|b| b.samples.iter().zip(&b.sky).map(|(s, &v)| (s.p, s.face, v)))
            .collect();
        let smooth = world_blur(&pts, arg(&args, "--sky-fine", 0.5), threads);
        let mut k = 0;
        for b in baked.iter_mut() {
            for v in b.sky.iter_mut() {
                *v = smooth[k];
                k += 1;
            }
        }
    }
    let ao_smooth: f32 = arg(&args, "--ao-smooth", 0.0);
    if ao_smooth > 0.0 {
        let started = std::time::Instant::now();
        let n = smooth_ao(&mut baked, ao_smooth, threads);
        println!("ao smoothed over {ao_smooth} across {n} texel(s), {:.1}s", started.elapsed().as_secs_f32());
    }
    // The knee: occlusion down to it counts as open. A mild fold between two
    // facets of a cliff (20-40 degrees) occludes 10-20% at its edge, which the
    // masters' corner strength turned into a dark line along every fold, the
    // cliffs drawn as their triangles; CE never darkened those. Corners that
    // close in (a wall's foot, a crevice) go well below it and keep theirs.
    // Past the knee, `--ao-curve` takes real corners back down to the
    // darkness they had before it (the knee alone lightened a wall's foot
    // from 0.5 to 0.59): (0.5 / 0.85)^1.3 = 0.50.
    let ao_knee: f32 = arg(&args, "--ao-knee", 0.85);
    let ao_curve: f32 = arg(&args, "--ao-curve", 1.3);
    if ao_knee > 0.0 && ao_knee < 1.0 {
        for b in baked.iter_mut() {
            for r in b.results.iter_mut() {
                r.1 = (r.1 / ao_knee).min(1.0).powf(ao_curve);
            }
        }
    }

    // The sun's visibility from the lightmap solver (`<page>_sunvis.png`
    // beside the pages, `mjolnir level lightmaps`): the same rays that lit
    // the page, antialiased over its supersamples, so the masters' Unreal
    // sun share and the lightmap's shadow share one edge. Our own trace is
    // a hard per-texel test, and its stair-stepped edge against the shadow
    // proxy's darkened a sliver twice (Blood Gulch base roof, 2026-10-08).
    for b in baked.iter_mut().filter(|_| !mask_only) {
        let file = dir.join(format!("{}_sunvis.png", b.name));
        let Some((sw, rgb)) = read_png_rgb(&file) else { continue };
        let sh = rgb.len() / 3 / sw.max(1);
        if sw == 0 || sh == 0 {
            continue;
        }
        let at = |x: usize, y: usize| rgb[(y.min(sh - 1) * sw + x.min(sw - 1)) * 3] as f32 / 255.0;
        for r in b.results.iter_mut() {
            let (x, y) = (r.0 % b.w, r.0 / b.w);
            let u = (x as f32 + 0.5) / b.w as f32 * sw as f32 - 0.5;
            let v = (y as f32 + 0.5) / b.h as f32 * sh as f32 - 0.5;
            let (x0, y0) = (u.floor().max(0.0) as usize, v.floor().max(0.0) as usize);
            let (fx, fy) = ((u - x0 as f32).clamp(0.0, 1.0), (v - y0 as f32).clamp(0.0, 1.0));
            let top = at(x0, y0) * (1.0 - fx) + at(x0 + 1, y0) * fx;
            let bottom = at(x0, y0 + 1) * (1.0 - fx) + at(x0 + 1, y0 + 1) * fx;
            r.2 = top * (1.0 - fy) + bottom * fy;
        }
        println!("page {}: sun visibility from {}", b.page, file.display());
    }

    for b in baked.iter().filter(|_| !mask_only) {
        let Baked { page, ref name, lw, lh, scale, w, h, ref results, secs, .. } = *b;
        let detail = &b.sky;

        // RGBA, then dilate covered texels outwards so bilinear filtering at
        // a chart's edge never reads an empty texel. A: the texel's chart,
        // so the masters' filters stay inside it (chart_ids).
        let mut rgba = vec![0u8; w * h * 4];
        let mut have = vec![false; w * h];
        for (k, (pixel, ao, vis)) in results.iter().enumerate() {
            let at = pixel * 4;
            rgba[at] = (ao.clamp(0.0, 1.0) * 255.0).round() as u8;
            rgba[at + 1] = (vis.clamp(0.0, 1.0) * 255.0).round() as u8;
            rgba[at + 2] = (detail[k].clamp(0.0, 1.0) * 255.0).round() as u8;
            have[*pixel] = true;
        }
        let ids = chart_ids(&have, w, h);
        for i in 0..w * h {
            rgba[i * 4 + 3] = ids[i];
        }
        // Bilinear filtering reaches one texel past a chart, the masters'
        // 3 x 3 filters a few more: a gutter texel takes one chart's values
        // only (the first neighbour's), never an average of two charts.
        for _ in 0..6 {
            let prev = have.clone();
            let src = rgba.clone();
            for y in 0..h {
                for x in 0..w {
                    if prev[y * w + x] {
                        continue;
                    }
                    let (mut r, mut g, mut bl, mut n, mut id) = (0u32, 0u32, 0u32, 0u32, 0u8);
                    for (dx, dy) in [(-1i32, 0i32), (1, 0), (0, -1), (0, 1)] {
                        let (nx, ny) = (x as i32 + dx, y as i32 + dy);
                        if nx < 0 || ny < 0 || nx >= w as i32 || ny >= h as i32 {
                            continue;
                        }
                        let q = ny as usize * w + nx as usize;
                        if prev[q] && (n == 0 || src[q * 4 + 3] == id) {
                            id = src[q * 4 + 3];
                            r += src[q * 4] as u32;
                            g += src[q * 4 + 1] as u32;
                            bl += src[q * 4 + 2] as u32;
                            n += 1;
                        }
                    }
                    if n > 0 {
                        let at = (y * w + x) * 4;
                        rgba[at] = (r / n) as u8;
                        rgba[at + 1] = (g / n) as u8;
                        rgba[at + 2] = (bl / n) as u8;
                        rgba[at + 3] = id;
                        have[y * w + x] = true;
                    }
                }
            }
        }
        for (i, px) in rgba.chunks_exact_mut(4).enumerate() {
            if !have[i] {
                // Open, sunlit, CE's sky: and chart 0, which no chart is.
                px.copy_from_slice(&[255, 255, 255, 0]);
            }
        }

        let file = out.join(format!("{}.png", asset_name(&name)));
        let mut enc = png::Encoder::new(std::fs::File::create(&file).expect("create png"), w as u32, h as u32);
        enc.set_color(png::ColorType::Rgba);
        enc.set_depth(png::BitDepth::Eight);
        enc.write_header().unwrap().write_image_data(&rgba).unwrap();
        let mean = |k: usize| {
            results.iter().map(|r| if k == 0 { r.1 } else { r.2 }).sum::<f32>() / results.len().max(1) as f32
        };
        println!(
            "page {page:2} {lw}x{lh} -> {w}x{h} (x{scale}): {} texel(s), ao {:.2}, sun {:.2}, {:.1}s -> {}",
            results.len(),
            mean(0),
            mean(1),
            secs,
            file.display()
        );
    }

    let cell: f32 = arg(&args, "--sun-mask-cell", 1.0);
    if cell > 0.0 {
        let centre = [(lo[0] + hi[0]) * 0.5, (lo[1] + hi[1]) * 0.5, (lo[2] + hi[2]) * 0.5];
        sun_mask(&baked, mask_pages.as_deref().unwrap_or(&dir), &out, &asset_name(&stem), centre, cell);
    }
}

/// CE's light seen from above (`<stem>_sunmask.png` and `.json`): per cell
/// of `cell` metres, the lightmap's luminance on the topmost surface that
/// faces up, in R (gamma space, as the lightmap holds it), G 255 where a
/// surface covered the cell or its neighbours filled it. The JSON places it
/// in Unreal centimetres, x and y relative to the spawned terrain (the box
/// centre: glTF (x, y, z) is Unreal (x, z, y) times 100). MJOLNIRLevelLoader
/// puts it on the level's sun as a light function, so the sun leaves alone
/// what CE drew in shade: its lightmaps hold shadows metres wide and soft,
/// which the traced geometry knows nothing of, and a player in Blood Gulch's
/// side passages stood in full sun on ground CE had dark (2026-10-05).
fn sun_mask(baked: &[Baked], dir: &Path, out: &Path, stem: &str, centre: V3, cell: f32) {
    let cm = cell * 100.0;
    let mut pts: Vec<(f32, f32, f32, f32)> = Vec::new();
    for b in baked {
        let file = dir.join(format!("{}.png", b.name));
        let Some((lw, rgb)) = read_png_rgb(&file) else {
            println!("sun mask: no {}, page {} left out", file.display(), b.page);
            continue;
        };
        // The page at its own size: CE's, or a sharpened one at the bake's.
        let lh = rgb.len() / 3 / lw.max(1);
        for s in &b.samples {
            if s.face[1] < 0.3 {
                continue;
            }
            let (x, y) = (s.pixel % b.w, s.pixel / b.w);
            let (lx, ly) = ((x * lw / b.w).min(lw - 1), (y * lh / b.h).min(lh - 1));
            let at = (ly * lw + lx) * 3;
            let l = (0.2126 * rgb[at] as f32 + 0.7152 * rgb[at + 1] as f32 + 0.0722 * rgb[at + 2] as f32) / 255.0;
            pts.push((
                (s.p[0] - centre[0]) * 100.0,
                (s.p[2] - centre[2]) * 100.0,
                (s.p[1] - centre[1]) * 100.0,
                l,
            ));
        }
    }
    if pts.is_empty() {
        println!("sun mask: no up-facing surface, none written");
        return;
    }
    let (mut x0, mut y0, mut x1, mut y1) = (f32::MAX, f32::MAX, f32::MIN, f32::MIN);
    for p in &pts {
        x0 = x0.min(p.0);
        y0 = y0.min(p.1);
        x1 = x1.max(p.0);
        y1 = y1.max(p.1);
    }
    let (w, h) = (((x1 - x0) / cm).ceil() as usize + 1, ((y1 - y0) / cm).ceil() as usize + 1);
    let mut top = vec![(f32::MIN, 1.0f32); w * h];
    for p in &pts {
        let (ix, iy) = (((p.0 - x0) / cm) as usize, ((p.1 - y0) / cm) as usize);
        let c = &mut top[iy * w + ix];
        if p.2 > c.0 {
            *c = (p.2, p.3);
        }
    }
    let mut have: Vec<bool> = top.iter().map(|c| c.0 > f32::MIN).collect();
    let mut l: Vec<f32> = top.iter().map(|c| c.1).collect();
    // Gaps between samples (a cell finer than a texel, steep ground) take
    // their neighbours' light.
    for _ in 0..3 {
        let (prev, src) = (have.clone(), l.clone());
        for y in 0..h {
            for x in 0..w {
                if prev[y * w + x] {
                    continue;
                }
                let (mut sum, mut n) = (0.0, 0);
                for (dx, dy) in [(-1i32, 0i32), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)] {
                    let (nx, ny) = (x as i32 + dx, y as i32 + dy);
                    if nx >= 0 && ny >= 0 && (nx as usize) < w && (ny as usize) < h && prev[ny as usize * w + nx as usize] {
                        sum += src[ny as usize * w + nx as usize];
                        n += 1;
                    }
                }
                if n > 0 {
                    l[y * w + x] = sum / n as f32;
                    have[y * w + x] = true;
                }
            }
        }
    }
    let mut rgba = vec![0u8; w * h * 4];
    for i in 0..w * h {
        rgba[i * 4] = (l[i].clamp(0.0, 1.0) * 255.0).round() as u8;
        rgba[i * 4 + 1] = if have[i] { 255 } else { 0 };
        rgba[i * 4 + 3] = 255;
    }
    let png_file = out.join(format!("{stem}_sunmask.png"));
    let mut enc = png::Encoder::new(std::fs::File::create(&png_file).expect("create png"), w as u32, h as u32);
    enc.set_color(png::ColorType::Rgba);
    enc.set_depth(png::BitDepth::Eight);
    enc.write_header().unwrap().write_image_data(&rgba).unwrap();
    let json = format!(
        "{{
  \"cell_cm\": {cm},
  \"width\": {w},
  \"height\": {h},
  \"min\": [{x0:.1}, {y0:.1}]
}}
"
    );
    std::fs::write(out.join(format!("{stem}_sunmask.json")), json).expect("write json");
    println!("sun mask {w}x{h} at {cell} m from {} surface texel(s) -> {}", pts.len(), png_file.display());
}

fn read_png_rgb(path: &Path) -> Option<(usize, Vec<u8>)> {
    let decoder = png::Decoder::new(std::fs::File::open(path).ok()?);
    let mut reader = decoder.read_info().ok()?;
    let mut buf = vec![0; reader.output_buffer_size()];
    let info = reader.next_frame(&mut buf).ok()?;
    let (w, h) = (info.width as usize, info.height as usize);
    let ch = match info.color_type {
        png::ColorType::Rgb => 3,
        png::ColorType::Rgba => 4,
        png::ColorType::Grayscale => 1,
        png::ColorType::GrayscaleAlpha => 2,
        _ => return None,
    };
    if info.bit_depth != png::BitDepth::Eight {
        return None;
    }
    let mut rgb = Vec::with_capacity(w * h * 3);
    for px in buf[..w * h * ch].chunks_exact(ch) {
        match ch {
            1 | 2 => rgb.extend_from_slice(&[px[0], px[0], px[0]]),
            _ => rgb.extend_from_slice(&px[..3]),
        }
    }
    Some((w, rgb))
}
