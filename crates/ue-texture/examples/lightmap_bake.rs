//! Bake what a converted CE level's lightmaps leave out, one texture per
//! lightmap page, on the same UVs.
//!
//! ```text
//! cargo run --release -p ue-texture --example lightmap_bake -- \
//!     <scene.gltf> <lightmap page 0.png> <out dir> \
//!     [--max-size 2048] [--max-scale 16] [--ao-radius 1.0] [--ao-rays 48] \
//!     [--sun-rays 8] [--threads 6]
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
//!   (cosine-weighted, hits weighted by closeness), 1 = open;
//! - G: sun visibility, the share of `--sun-rays` rays inside a 1 degree cone
//!   around the sun that leave the level, 1 = in the sun;
//! - B: 255 where a triangle covers the texel, 0 where dilation filled it.
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
    sun: V3,
}

/// (ao, sun visibility) for one texel.
fn bake(bvh: &Bvh, s: &Sample, cfg: &Settings, rng: &mut Rng) -> (f32, f32) {
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
    (ao, lit as f32 / cfg.sun_rays as f32)
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
    for mesh in gltf.doc["meshes"].as_array().unwrap() {
        for prim in mesh["primitives"].as_array().unwrap() {
            let at = &prim["attributes"];
            let pos = gltf.floats(at["POSITION"].as_u64().unwrap() as usize, 3);
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
    let sun = norm(sun_sum);
    println!("{} triangle(s), {} on lightmap pages; sun (towards) {:?}", tris.len(), receivers.len(), sun);
    let bvh = Bvh::build(tris);
    let cfg = Settings {
        ao_radius: arg(&args, "--ao-radius", 1.0),
        ao_rays: arg(&args, "--ao-rays", 48),
        sun_rays: arg(&args, "--sun-rays", 8),
        sun,
    };

    let stem = page0.file_stem().unwrap().to_string_lossy().to_string();
    let dir = page0.parent().unwrap().to_path_buf();
    let mut pages: Vec<usize> = receivers.iter().map(|r| r.page).collect();
    pages.sort();
    pages.dedup();
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
        let chunk = samples.len().div_ceil(threads).max(1);
        let results: Vec<(usize, f32, f32)> = std::thread::scope(|scope| {
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
                                let (ao, vis) = bake(bvh, s, cfg, &mut rng);
                                (s.pixel, ao, vis)
                            })
                            .collect::<Vec<_>>()
                    })
                })
                .collect();
            handles.into_iter().flat_map(|h| h.join().unwrap()).collect()
        });

        // RGBA, then dilate covered texels outwards so bilinear filtering at
        // a chart's edge never reads an empty texel.
        let mut rgba = vec![0u8; w * h * 4];
        let mut have = vec![false; w * h];
        for (pixel, ao, vis) in &results {
            let at = pixel * 4;
            rgba[at] = (ao.clamp(0.0, 1.0) * 255.0).round() as u8;
            rgba[at + 1] = (vis.clamp(0.0, 1.0) * 255.0).round() as u8;
            rgba[at + 2] = 255;
            rgba[at + 3] = 255;
            have[*pixel] = true;
        }
        // Bilinear filtering reaches one texel past a chart; a few more
        // cover rounding at the chart's own edge.
        for _ in 0..4 {
            let prev = have.clone();
            let src = rgba.clone();
            for y in 0..h {
                for x in 0..w {
                    if prev[y * w + x] {
                        continue;
                    }
                    let (mut r, mut g, mut n) = (0u32, 0u32, 0u32);
                    for (dx, dy) in [(-1i32, 0i32), (1, 0), (0, -1), (0, 1)] {
                        let (nx, ny) = (x as i32 + dx, y as i32 + dy);
                        if nx < 0 || ny < 0 || nx >= w as i32 || ny >= h as i32 {
                            continue;
                        }
                        let q = ny as usize * w + nx as usize;
                        if prev[q] {
                            r += src[q * 4] as u32;
                            g += src[q * 4 + 1] as u32;
                            n += 1;
                        }
                    }
                    if n > 0 {
                        let at = (y * w + x) * 4;
                        rgba[at] = (r / n) as u8;
                        rgba[at + 1] = (g / n) as u8;
                        rgba[at + 3] = 255;
                        have[y * w + x] = true;
                    }
                }
            }
        }
        for px in rgba.chunks_exact_mut(4) {
            if px[3] == 0 {
                px.copy_from_slice(&[255, 255, 0, 255]);
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
            started.elapsed().as_secs_f32(),
            file.display()
        );
    }
}
