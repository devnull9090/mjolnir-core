//! Radiosity elements: the lit triangles split until every edge fits the
//! quality row's segment length, as tool.exe's initial subdivision does.

use crate::gltf::{Scene, Tri};
use crate::math::{add, cross, dot, len, lerp, mul, norm, sub, V3};
use crate::staging::{Shader, Staging};
use std::collections::HashMap;

/// CE world units per glTF metre: the quality table's lengths are world
/// units, the scene is metres.
pub const WU_TO_M: f32 = 3.048;

/// One quality row (`radiosity_qualities[q].surface_constants[detail]`).
#[derive(Clone, Copy, Debug)]
pub struct Row {
    /// Split an element when its vertices' irradiance differs across an
    /// edge by more than this share of the larger one; `f32::MAX` never.
    pub gradient: f32,
    /// The segment length an adaptive split stops at (twice this).
    pub minimum: f32,
    /// The initial segment length of an emitting element.
    pub emissive: f32,
    /// ... and of one that only reflects.
    pub plain: f32,
}

/// tool.exe's two qualities: 0 draft, 1 final. The sun's sample grid is
/// `sun_grid x sun_grid`.
#[derive(Clone, Copy, Debug)]
pub struct Quality {
    pub rows: [Row; 4],
    pub sun_grid: usize,
}

impl Quality {
    pub fn draft() -> Quality {
        Quality {
            rows: [
                Row { gradient: 1.0, minimum: 0.5, emissive: 2.0, plain: 4.0 },
                Row { gradient: 2.0, minimum: 1.0, emissive: 4.0, plain: 8.0 },
                Row { gradient: 3.0, minimum: 2.0, emissive: 8.0, plain: 16.0 },
                Row { gradient: f32::MAX, minimum: 20.0, emissive: 40.0, plain: 80.0 },
            ],
            sun_grid: 2,
        }
    }

    pub fn final_() -> Quality {
        Quality {
            rows: [
                Row { gradient: 0.5, minimum: 0.125, emissive: 0.5, plain: 0.9 },
                Row { gradient: 0.7, minimum: 0.3, emissive: 1.2, plain: 2.4 },
                Row { gradient: 0.8, minimum: 0.5, emissive: 2.0, plain: 4.0 },
                Row { gradient: f32::MAX, minimum: 20.0, emissive: 40.0, plain: 80.0 },
            ],
            sun_grid: 4,
        }
    }

    /// The final rows with every segment length divided by `k`: finer
    /// elements, hence finer lightmaps, than tool.exe would make.
    pub fn finer(k: f32) -> Quality {
        let mut q = Quality::final_();
        for r in q.rows.iter_mut() {
            r.minimum /= k;
            r.emissive /= k;
            r.plain /= k;
        }
        q
    }
}

/// A radiosity vertex, shared by the elements that meet at it.
#[derive(Clone, Debug)]
pub struct Vertex {
    pub p: V3,
    pub n: V3,
    /// Irradiance gathered so far (what the lightmap shows).
    pub total: V3,
    /// Sum of incoming directions weighted by their light's luminance.
    pub dir: V3,
    /// What the sky's directional lights gave directly (for analysis).
    pub sun: V3,
    /// ... and the ambient.
    pub ambient: V3,
    /// The face normals of the elements meeting here. A ray leaving the
    /// vertex into any of them starts inside the level's solid, where
    /// tool.exe's BSP walk reports a block; the rendered mesh has no far
    /// side there, so a ray would otherwise escape (lit creases that CE
    /// has dark, Danger Canyon 2026-10-07).
    pub faces: Vec<V3>,
}

impl Vertex {
    pub fn add_face(&mut self, n: V3) {
        if !self.faces.iter().any(|f| dot(*f, n) > 0.999) {
            self.faces.push(n);
        }
    }

    /// Whether a ray along `d` from this vertex goes into the solid.
    pub fn enters_solid(&self, d: V3) -> bool {
        self.faces.iter().any(|f| dot(*f, d) < -1e-4)
    }
}

/// A patch: a triangle over the vertex pool, with its own base-map UVs.
#[derive(Clone, Debug)]
pub struct Patch {
    pub v: [u32; 3],
    pub uv0: [[f32; 2]; 3],
    /// Lightmap UVs on the material's page.
    pub uv1: [[f32; 2]; 3],
    pub area: f32,
    pub segment: f32,
}

/// An element: a patch that shoots and gathers, split into child patches
/// where the light changes quickly across it.
#[derive(Clone, Debug)]
pub struct Element {
    pub patch: Patch,
    pub normal: V3,
    /// `normal . p = d` on the plane.
    pub d: f32,
    /// Unshot energy.
    pub delta: V3,
    pub reflectance: V3,
    pub material: u32,
    /// The BSP cluster, -1 when unknown.
    pub cluster: i32,
    /// The scene triangle it came from.
    pub tri: u32,
    pub children: Vec<Patch>,
}

/// A lit surface group: one shader on one lightmap page.
#[derive(Clone, Debug)]
pub struct MaterialInfo {
    pub shader: String,
    pub page: usize,
    pub detail_level: usize,
    pub ignore_normals: bool,
    pub emission: V3,
    pub area: f32,
}

pub struct Elements {
    pub pool: Pool,
    pub elements: Vec<Element>,
    pub materials: Vec<MaterialInfo>,
    pub total_area: f32,
}

/// Vertices keyed on position and normal, tool.exe's equality (5e-4).
pub struct Pool {
    pub vertices: Vec<Vertex>,
    index: HashMap<[i32; 6], u32>,
}

impl Pool {
    fn key(p: V3, n: V3) -> [i32; 6] {
        let q = |x: f32, scale: f32| (x * scale).round() as i32;
        [q(p[0], 2000.0), q(p[1], 2000.0), q(p[2], 2000.0), q(n[0], 1000.0), q(n[1], 1000.0), q(n[2], 1000.0)]
    }

    fn get(&mut self, p: V3, n: V3) -> u32 {
        let key = Self::key(p, n);
        if let Some(&i) = self.index.get(&key) {
            return i;
        }
        let i = self.vertices.len() as u32;
        self.vertices.push(Vertex { p, n, total: [0.0; 3], dir: [0.0; 3], sun: [0.0; 3], ambient: [0.0; 3], faces: Vec::new() });
        self.index.insert(key, i);
        i
    }

    /// The vertex at `t` along `a -> b`: position lerped, normal the
    /// normalised lerp. A vertex made during the solve starts with its
    /// endpoints' light lerped, as tool.exe's does; one that already
    /// exists keeps its own. `face` is the splitting element's normal.
    pub fn between(&mut self, a: u32, b: u32, t: f32, face: Option<V3>) -> u32 {
        let (va, vb) = (self.vertices[a as usize].clone(), self.vertices[b as usize].clone());
        let before = self.vertices.len();
        let i = self.get(lerp(va.p, vb.p, t), norm(lerp(va.n, vb.n, t)));
        if self.vertices.len() > before {
            let v = &mut self.vertices[i as usize];
            v.total = lerp(va.total, vb.total, t);
            v.dir = lerp(va.dir, vb.dir, t);
            v.sun = lerp(va.sun, vb.sun, t);
            v.ambient = lerp(va.ambient, vb.ambient, t);
        }
        if let Some(f) = face {
            self.vertices[i as usize].add_face(f);
        }
        i
    }
}

fn area_of(p: [V3; 3]) -> f32 {
    len(cross(sub(p[1], p[0]), sub(p[2], p[0]))) * 0.5
}

/// The split of a patch until no edge needs more than one segment.
/// `emit` takes each finished patch; `face` is the patch's element's normal.
fn subdivide(pool: &mut Pool, patch: Patch, face: Option<V3>, emit: &mut dyn FnMut(&mut Pool, Patch)) {
    let p = [pool.vertices[patch.v[0] as usize].p, pool.vertices[patch.v[1] as usize].p, pool.vertices[patch.v[2] as usize].p];
    // Segments per edge (edge k runs from vertex k to k+1), the shortest
    // edge of one segment, and the edge of most segments (longer wins a tie).
    let mut segs = [1usize; 3];
    let mut lens = [0.0f32; 3];
    for k in 0..3 {
        lens[k] = len(sub(p[(k + 1) % 3], p[k]));
        segs[k] = if patch.segment > 0.0 { (lens[k] / patch.segment).ceil().max(1.0) as usize } else { 1 };
    }
    let mut most = 0;
    for k in 1..3 {
        if segs[k] > segs[most] || (segs[k] == segs[most] && lens[k] > lens[most]) {
            most = k;
        }
    }
    let whole = (0..3).filter(|&k| segs[k] == 1).min_by(|&a, &b| lens[a].partial_cmp(&lens[b]).unwrap());
    if segs[most] <= 1 {
        emit(pool, patch);
        return;
    }
    // Where an edge is cut: at k/n, k on the side of the foot of the
    // altitude from the opposite vertex.
    let cut = |pool: &mut Pool, k: usize| -> (u32, bool) {
        let (a, b, c) = (patch.v[k], patch.v[(k + 1) % 3], patch.v[(k + 2) % 3]);
        let (pa, pb, pc) = (pool.vertices[a as usize].p, pool.vertices[b as usize].p, pool.vertices[c as usize].p);
        let e = sub(pb, pa);
        let foot = dot(sub(pc, pa), e) / dot(e, e).max(1e-12);
        let n = segs[k] as f32;
        let i = if foot * n > (n * 0.5).floor() { (n * 0.5).ceil() } else { (n * 0.5).floor() };
        let t = (i / n).clamp(0.0, 1.0);
        if t <= 0.0 || t >= 1.0 {
            return (a, false);
        }
        (pool.between(a, b, t, face), true)
    };
    let child = |pool: &mut Pool, v: [u32; 3], uv0: [[f32; 2]; 3], uv1: [[f32; 2]; 3]| -> Patch {
        let p = [pool.vertices[v[0] as usize].p, pool.vertices[v[1] as usize].p, pool.vertices[v[2] as usize].p];
        Patch { v, uv0, uv1, area: area_of(p), segment: patch.segment }
    };
    let uv_at = |uv: &[[f32; 2]; 3], k: usize, t: f32| -> [f32; 2] {
        let (a, b) = (uv[k], uv[(k + 1) % 3]);
        [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
    };
    if whole.is_none() {
        // Every edge needs splitting: four children, the corners and the centre.
        let mut m = [0u32; 3];
        let mut muv = [[0.0f32; 2]; 3];
        let mut muv1 = [[0.0f32; 2]; 3];
        for k in 0..3 {
            let (v, ok) = cut(pool, k);
            if !ok {
                emit(pool, patch);
                return;
            }
            m[k] = v;
            let t = {
                let (a, b) = (pool.vertices[patch.v[k] as usize].p, pool.vertices[patch.v[(k + 1) % 3] as usize].p);
                let e = sub(b, a);
                dot(sub(pool.vertices[v as usize].p, a), e) / dot(e, e).max(1e-12)
            };
            muv[k] = uv_at(&patch.uv0, k, t);
            muv1[k] = uv_at(&patch.uv1, k, t);
        }
        let (v0, v1, v2) = (patch.v[0], patch.v[1], patch.v[2]);
        let (u0, u1, u2) = (patch.uv0[0], patch.uv0[1], patch.uv0[2]);
        let (w0, w1, w2) = (patch.uv1[0], patch.uv1[1], patch.uv1[2]);
        for (v, uv, uv1) in [
            ([v0, m[0], m[2]], [u0, muv[0], muv[2]], [w0, muv1[0], muv1[2]]),
            ([m[0], v1, m[1]], [muv[0], u1, muv[1]], [muv1[0], w1, muv1[1]]),
            ([m[2], m[1], v2], [muv[2], muv[1], u2], [muv1[2], muv1[1], w2]),
            ([m[0], m[1], m[2]], [muv[0], muv[1], muv[2]], [muv1[0], muv1[1], muv1[2]]),
        ] {
            let c = child(pool, v, uv, uv1);
            subdivide(pool, c, face, emit);
        }
    } else {
        // Bisect the edge of most segments: two children.
        let (mv, ok) = cut(pool, most);
        if !ok {
            emit(pool, patch);
            return;
        }
        let t = {
            let (a, b) = (pool.vertices[patch.v[most] as usize].p, pool.vertices[patch.v[(most + 1) % 3] as usize].p);
            let e = sub(b, a);
            dot(sub(pool.vertices[mv as usize].p, a), e) / dot(e, e).max(1e-12)
        };
        let muv = uv_at(&patch.uv0, most, t);
        let muv1 = uv_at(&patch.uv1, most, t);
        let (a, b, c) = (most, (most + 1) % 3, (most + 2) % 3);
        let first = child(pool, [patch.v[a], mv, patch.v[c]], [patch.uv0[a], muv, patch.uv0[c]], [patch.uv1[a], muv1, patch.uv1[c]]);
        let second = child(pool, [mv, patch.v[b], patch.v[c]], [muv, patch.uv0[b], patch.uv0[c]], [muv1, patch.uv1[b], patch.uv1[c]]);
        subdivide(pool, first, face, emit);
        subdivide(pool, second, face, emit);
    }
}

fn reflectance(shader: &Shader, uv0: &[[f32; 2]; 3], flat: bool) -> V3 {
    match &shader.base_map {
        Some(img) if flat => img.mean(),
        Some(img) => {
            let mut sum = [0.0f32; 3];
            for uv in uv0 {
                let c = img.sample(*uv);
                sum = add(sum, c);
            }
            mul(sum, 1.0 / 3.0)
        }
        None => [0.0; 3],
    }
}

impl Elements {
    /// A patch split at its own (already halved) segment length into leaf
    /// patches, for the adaptive refinement during the solve.
    pub fn split_patch(&mut self, patch: Patch, face: V3) -> Vec<Patch> {
        let mut out = Vec::new();
        subdivide(&mut self.pool, patch, Some(face), &mut |_, p: Patch| {
            if p.area > 0.0 {
                out.push(p);
            }
        });
        out
    }

    /// Every lit triangle of the scene split for `quality`, and of
    /// `translucent` (the merged scene's transparent pieces: CE's lamps are
    /// transparent shaders with emission, and they are what lights the
    /// interiors). Triangles of placed objects and the sky only occlude.
    /// A lit surface without a lightmap page (the emitters, on tool.exe's
    /// "no lightmap" entry) still shoots and bounces; only pages get drawn.
    pub fn build(scene: &Scene, translucent: Option<&Scene>, staging: &Staging, quality: &Quality, flat_reflectance: bool) -> Elements {
        let mut pool = Pool { vertices: Vec::new(), index: HashMap::new() };
        let mut materials: Vec<MaterialInfo> = Vec::new();
        let mut material_index: HashMap<(String, usize), u32> = HashMap::new();
        let mut elements = Vec::new();
        // The opaque BSP triangles' centroids and clusters, to place the
        // transparent scene's emitters (which the cluster table does not
        // cover) in the cluster of the nearest surface.
        let placed: Vec<(V3, i32)> = match &staging.clusters {
            Some(c) => scene
                .tris
                .iter()
                .filter(|t| !scene.materials[t.material].object && !scene.materials[t.material].sky)
                .map(|t| (mul(add(add(t.p[0], t.p[1]), t.p[2]), 1.0 / 3.0), c.of(t.prim, t.index)))
                .filter(|(_, c)| *c >= 0)
                .collect(),
            None => Vec::new(),
        };
        let nearest_cluster = |p: V3| -> i32 {
            let mut best = (f32::MAX, -1);
            for (q, c) in &placed {
                let d = dot(sub(*q, p), sub(*q, p));
                if d < best.0 {
                    best = (d, *c);
                }
            }
            best.1
        };
        let scenes: Vec<(&Scene, bool)> = std::iter::once((scene, false)).chain(translucent.map(|t| (t, true))).collect();
        for (sc, is_translucent) in scenes {
            for (ti, tri) in sc.tris.iter().enumerate() {
            let mat = &sc.materials[tri.material];
            if mat.object || mat.sky {
                continue;
            }
            let Some(shader) = staging.shaders.get(&mat.shader) else { continue };
            if !shader.lit() {
                continue;
            }
            // The transparent scene's primitives keep the BSP glTF's
            // material names, which the cluster table's primitives carry;
            // failing that, the cluster of the nearest opaque surface.
            let cluster = if is_translucent {
                let by_name = staging
                    .clusters
                    .as_ref()
                    .map(|c| c.of_material(&staging.bsp_material_names, &mat.name, tri.index))
                    .unwrap_or(-1);
                if by_name >= 0 { by_name } else { nearest_cluster(mul(add(add(tri.p[0], tri.p[1]), tri.p[2]), 1.0 / 3.0)) }
            } else {
                staging.clusters.as_ref().map(|c| c.of(tri.prim, tri.index)).unwrap_or(-1)
            };
            let page = tri.page.unwrap_or(usize::MAX);
            let uv1 = tri.uv1.unwrap_or([[0.0; 2]; 3]);
            let ti = if is_translucent { usize::MAX - ti } else { ti };
            let mi = *material_index.entry((mat.shader.clone(), page)).or_insert_with(|| {
                materials.push(MaterialInfo {
                    shader: mat.shader.clone(),
                    page,
                    detail_level: shader.detail_level,
                    ignore_normals: shader.ignore_normals,
                    emission: shader.emission,
                    area: 0.0,
                });
                (materials.len() - 1) as u32
            });
            let row = quality.rows[shader.detail_level];
            let emissive = shader.emission.iter().sum::<f32>() > 0.0;
            // Segment lengths are CE world units; the scene is metres.
            let segment = if emissive { row.emissive } else { row.plain } * WU_TO_M;
            let v = [
                pool.get(tri.p[0], tri.n[0]),
                pool.get(tri.p[1], tri.n[1]),
                pool.get(tri.p[2], tri.n[2]),
            ];
            let root = Patch { v, uv0: tri.uv0, uv1, area: area_of(tri.p), segment };
            let normal = face_normal(tri);
            let d = dot(normal, tri.p[0]);
            let delta = shader.emission;
            for &vi in &v {
                pool.vertices[vi as usize].add_face(normal);
            }
            subdivide(&mut pool, root, Some(normal), &mut |pool: &mut Pool, patch: Patch| {
                if patch.area <= 0.0 {
                    return;
                }
                let reflectance = reflectance(shader, &patch.uv0, flat_reflectance);
                for &vi in &patch.v {
                    pool.vertices[vi as usize].add_face(normal);
                }
                elements.push(Element {
                    patch,
                    normal,
                    d,
                    delta,
                    reflectance,
                    material: mi,
                    cluster,
                    tri: ti as u32,
                    children: Vec::new(),
                });
            });
            }
        }
        let mut total_area = 0.0;
        for e in &elements {
            materials[e.material as usize].area += e.patch.area;
            total_area += e.patch.area;
        }
        Elements { pool, elements, materials, total_area }
    }
}

/// The triangle's face normal, on the side of its vertex normals.
pub fn face_normal(tri: &Tri) -> V3 {
    let f = norm(cross(sub(tri.p[1], tri.p[0]), sub(tri.p[2], tri.p[0])));
    let avg = add(add(tri.n[0], tri.n[1]), tri.n[2]);
    if dot(f, avg) < 0.0 {
        mul(f, -1.0)
    } else {
        f
    }
}
