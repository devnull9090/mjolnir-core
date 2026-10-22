//! The structure BSP's render geometry as the staging's `bsp/bsp_0.gltf`,
//! its shaders as `materials.json` summaries, and their bitmaps and the
//! lightmap pages as `textures/*.png` (+ `.dds` mip chains).
//!
//! The glTF follows halo2ue's contract (docs/ce_map_conversion.md; the
//! staging report in the Halo 2 work): metres, +Y up, Halo (x, y, z) as
//! (x, z, -y) * 3.048; one primitive per (shader, lightmap page), named
//! `<shader>__lm<page>`, every primitive with POSITION, NORMAL, TANGENT,
//! TEXCOORD_0 (the base map's coordinates), TEXCOORD_1 (the lightmap's) and
//! `_INCIDENT` (the incident light direction, zero where Halo 2 has none),
//! and `extras.halo` naming the shader and the page. Halo 2's triangles wind
//! counter-clockwise already, so their order is kept (CE's are flipped).
//!
//! Clusters take their lightmap page from the lightmap tag's cluster render
//! info, instanced geometry from its instance render info; an instance's
//! definition carries the lightmap coordinates, and the page is its own.
//! Vertex-lit definitions (no lightmap coordinates) get no page.
//!
//! Shaders: MCC's caches keep no parameter names, so each template's bitmap
//! slots and tiling constants are read in the template's own order
//! ([`template`], after TagTool's and Reclaimer's tables, checked on
//! Lockout). Opaque shaders become environment summaries
//! (`shader_class: "shad"`, which tools/level/ce_material_spec.py draws on
//! its environment masters, alpha tested on the base map when the template
//! is); transparent ones chicago summaries (`schi`, a single stage, alpha
//! blended or additive), so tools/level/merge_ce_scene.py puts them in the
//! translucent mesh.

use std::collections::BTreeMap;
use std::path::Path;

use serde_json::{json, Value};

use crate::h2::bitmap;
use crate::h2::geometry::{self, Compression, Section};
use crate::h2::stage::{sanitize, Summary};
use crate::h2::{Cache, CacheFile, Struct, Tag};
use crate::Error;

const WU_TO_M: f32 = 3.048;

/// Halo 2 stores its lightmaps at half their light and doubles them in the
/// shader (Lockout's pages average 20-45% where CE's sit near 70%; the
/// interiors came out nearly black on the CE masters, which take a lightmap
/// as it is, 2026-10-21). The pages are staged doubled, clamped at white.
const LIGHTMAP_GAIN: f32 = 2.0;

fn to_gltf(v: [f32; 3]) -> [f32; 3] {
    [v[0], v[2], -v[1]]
}

/// What a template's bitmap slots and vertex constants hold.
pub struct Template {
    /// Per bitmap slot: `base`, `detail`, `detail2`, `bump`, `self_illum`,
    /// `alpha_test`, or `""` for one the conversion does not draw.
    pub slots: &'static [&'static str],
    /// The vertex constant (u scale, v scale) index of each tiled role.
    pub tiling: &'static [(&'static str, usize)],
    /// 0 opaque; else the chicago framebuffer blend (0 alpha blend, 3 add)
    /// plus one.
    pub transparent: u8,
    pub alpha_tested: bool,
}

/// A shader template's slot layout, by its name (`tex_bump`, ...).
pub fn template(name: &str) -> Template {
    let t = |slots, tiling, transparent, alpha_tested| Template { slots, tiling, transparent, alpha_tested };
    const BUMP_FIRST: &[(&str, usize)] = &[("bump", 0), ("base", 1), ("detail", 2), ("detail2", 3)];
    // tex_bump_detail_blend alone keeps its details' constants first (25
    // shaders on the 24 maps, base always constant 2 at (1, 1)); its
    // siblings (_keep, _overlay, _blend_detail, two and three detail) are
    // bump-first like tex_bump, base at constant 1 (Coagulation's ground
    // tiled 60 times when read the other way).
    const DETAIL_FIRST: &[(&str, usize)] = &[("detail", 0), ("detail2", 1), ("base", 2), ("bump", 3)];
    let mut tpl = match name {
        n if n.starts_with("tex_bump_alpha_test") && n.contains("single_pass") => {
            t(&["bump", "", "base", "detail"], BUMP_FIRST, 0, true)
        }
        n if n.starts_with("tex_bump_alpha_test") => {
            t(&["bump", "", "", "base", "detail"], &[("detail", 0), ("base", 1), ("bump", 2)], 0, true)
        }
        "tex_bump_detail_blend" => t(&["bump", "base", "detail", "detail2"], DETAIL_FIRST, 0, false),
        n if n.starts_with("tex_bump_detail_blend_detail") => {
            t(&["bump", "base", "detail", "detail2", ""], BUMP_FIRST, 0, false)
        }
        n if n.starts_with("tex_bump_detail") || n == "tex_bump_two_detail" || n == "tex_bump_three_detail_blend" => {
            t(&["bump", "base", "detail", "detail2"], BUMP_FIRST, 0, false)
        }
        n if n.starts_with("tex_bump_illum") => t(&["bump", "base", "detail", "self_illum"], BUMP_FIRST, 0, false),
        n if n.starts_with("tex_bump_env_illum_3_channel") => {
            t(&["bump", "base", "detail", "", "self_illum"], BUMP_FIRST, 0, false)
        }
        n if n.starts_with("tex_bump_env_illum") => {
            t(&["bump", "", "base", "detail", "", "self_illum"], &[("detail", 0), ("base", 1), ("bump", 2)], 0, false)
        }
        n if n.starts_with("tex_bump_env_no_detail") => t(&["bump", "", "base"], BUMP_FIRST, 0, false),
        n if n.starts_with("tex_bump_one_change_color") => t(&["bump", "base"], BUMP_FIRST, 0, false),
        n if n.starts_with("tex_bump_env") || n.starts_with("tex_bump_dprs_env") => {
            t(&["bump", "", "base", "detail"], BUMP_FIRST, 0, false)
        }
        n if n.starts_with("tex_bump") => t(&["bump", "", "base", "detail"], BUMP_FIRST, 0, false),
        n if n.starts_with("tex_alpha_test") => t(&["", "base", "detail"], &[], 0, true),
        "tex_env" => t(&["base", "detail"], &[], 0, false),
        n if n.starts_with("illum") => t(&["self_illum"], &[], 0, false),
        n if n.ends_with("one_alpha_env") || n.ends_with("one_alpha_env_illum") => t(&["", "", "base"], &[], 1, false),
        "plasma_alpha" => t(&["base"], &[], 4, false),
        n if n.contains("add") => t(&["", "base"], &[], 4, false),
        "overlay" => t(&["base"], &[], 1, false),
        n if n.contains("alpha") && !n.contains("alpha_test") => t(&["base"], &[], 1, false),
        // Anything else: the runtime properties' diffuse map, opaque.
        _ => t(&[], &[], 0, false),
    };
    // Every opaque alpha-test variant (tex_bump_env_alpha_test, ...) cuts out
    // on the base map's alpha, whatever family its slots follow.
    if tpl.transparent == 0 && name.contains("alpha_test") {
        tpl.alpha_tested = true;
    }
    tpl
}

/// Placeholder bitmaps a template binds when a slot is unused.
fn is_placeholder(path: &str) -> bool {
    let p = path.to_ascii_lowercase();
    p.contains("default_bitmaps") || p.starts_with("rasterizer\\") || p.ends_with("gray_50_percent") || p.ends_with("color_white")
}

/// Staged bitmaps: PNG (and DDS) per (bitm datum in its file, submap).
#[derive(Default)]
struct Textures {
    done: BTreeMap<(usize, u32, u32), Option<String>>,
    names: BTreeMap<String, usize>,
}

impl Textures {
    /// Stage one submap of a bitmap tag; its PNG's file name, or `None`
    /// (with a note) when it cannot be decoded.
    fn stage(&mut self, cache: &Cache, tag: &Tag<'_>, index: u32, dir: &Path, notes: &mut Vec<String>) -> Option<String> {
        self.stage_with(cache, tag, index, dir, notes, 1.0)
    }

    /// As [`Textures::stage`], the colour scaled by `gain` (clamped).
    fn stage_with(
        &mut self,
        cache: &Cache,
        tag: &Tag<'_>,
        index: u32,
        dir: &Path,
        notes: &mut Vec<String>,
        gain: f32,
    ) -> Option<String> {
        let key = (tag.file as *const CacheFile as usize, tag.entry.datum, index);
        if let Some(done) = self.done.get(&key) {
            return done.clone();
        }
        let result = (|| -> Result<String, Error> {
            let textures = cache.textures.as_ref().ok_or_else(|| Error::Unsupported("no textures.dat".into()))?;
            let infos = bitmap::infos(tag);
            let info = infos.get(index as usize).ok_or_else(|| Error::Format(format!("no bitmap {index}")))?;
            let data = bitmap::read_entry(textures, info.offset, info.size)?;
            let mut mips = bitmap::decode(info, &data)?;
            if gain != 1.0 {
                for m in &mut mips {
                    for p in m.rgba.chunks_exact_mut(4) {
                        for c in &mut p[..3] {
                            *c = (*c as f32 * gain).round().min(255.0) as u8;
                        }
                    }
                }
            }
            let mut stem = sanitize(tag.name());
            if index > 0 {
                stem = format!("{stem}_{index}");
            }
            let n = self.names.entry(stem.clone()).or_default();
            *n += 1;
            if *n > 1 {
                stem = format!("{stem}_{}", *n - 1);
            }
            bitmap::write_png(&dir.join("textures").join(format!("{stem}.png")), &mips[0])?;
            if mips.len() > 1 {
                bitmap::write_dds(&dir.join("textures").join(format!("{stem}.dds")), &mips)?;
            }
            Ok(format!("{stem}.png"))
        })();
        let out = match result {
            Ok(png) => Some(png),
            Err(e) => {
                notes.push(format!("bitmap {}[{index}]: {e}", tag.name()));
                None
            }
        };
        self.done.insert(key, out.clone());
        out
    }
}

/// A shader's staged summary and the glTF facts it implies.
struct Shader {
    key: String,
    class: &'static str,
    alpha_mode: &'static str,
    double_sided: bool,
    base: Option<String>,
    /// The base map's tiling, baked into TEXCOORD_0.
    base_scale: [f32; 2],
    summary: Value,
}

fn shader_summary(cache: &Cache, shader: Option<Tag<'_>>, dir: &Path, tex: &mut Textures, notes: &mut Vec<String>) -> Shader {
    let Some(shader) = shader else {
        return Shader {
            key: "halo_shader_missing".into(),
            class: "shad",
            alpha_mode: "OPAQUE",
            double_sided: true,
            base: None,
            base_scale: [1.0, 1.0],
            summary: json!({"tag_path": "", "shader_class": "shad", "shader_type": 0, "shader_flags": 0,
                            "base_map": Value::Null, "detail": {}, "bump": {}, "self_illum": {}, "specular": {}}),
        };
    };
    let root = shader.root;
    let template_name = root
        .tagref(0x00)
        .map(|r| r.name().rsplit('\\').next().unwrap_or("").to_string())
        .unwrap_or_default();
    let tpl = template(&template_name);
    // Postprocess definition 0: bitmaps (12 bytes: datum, submap, log size)
    // and vertex constants (float4: per-map u and v scale first).
    let post = root.block(0x20, 0x7C).get(0);
    let mut roles: BTreeMap<&str, Option<String>> = BTreeMap::new();
    let mut constants: Vec<[f32; 4]> = Vec::new();
    if let Some(p) = post {
        for (slot, b) in p.block(0x04, 0x0C).iter().enumerate() {
            let Some(&role) = tpl.slots.get(slot) else { break };
            if role.is_empty() || roles.contains_key(role) {
                continue;
            }
            let Some(t) = cache.tag(shader.file, b.u32(0)) else { continue };
            if is_placeholder(t.name()) {
                continue;
            }
            roles.insert(role, tex.stage(cache, &t, b.u32(4).max(0), dir, notes));
        }
        constants = p.block(0x14, 0x10).iter().map(|c| [c.f32(0), c.f32(4), c.f32(8), c.f32(12)]).collect();
    }
    // The runtime properties' diffuse map when the template table found no base.
    if roles.get("base").cloned().flatten().is_none() {
        if let Some(t) = root.block(0x0C, 0x50).get(0).and_then(|rp| rp.tagref(0x00)).and_then(|r| cache.follow(r)) {
            if !is_placeholder(t.name()) {
                roles.insert("base", tex.stage(cache, &t, 0, dir, notes));
            }
        }
    }
    let role = |r: &str| roles.get(r).cloned().flatten();
    let scale = |r: &str| -> [f32; 2] {
        tpl.tiling
            .iter()
            .find(|(n, _)| *n == r)
            .and_then(|&(_, i)| constants.get(i))
            .map(|c| [if c[0] == 0.0 { 1.0 } else { c[0] }, if c[1] == 0.0 { 1.0 } else { c[1] }])
            .unwrap_or([1.0, 1.0])
    };
    let base_scale = scale("base");
    let rel = |r: &str| scale(r)[0] / base_scale[0];
    let key = sanitize(shader.name());
    let base = role("base");
    let (class, alpha_mode, double_sided, summary) = if tpl.transparent > 0 {
        let blend = (tpl.transparent - 1) as i64;
        let maps = vec![json!({"map": {"file": base}, "color_function": 0, "alpha_function": 0,
                               "map_u_scale": base_scale[0], "map_v_scale": base_scale[1]})];
        let s = json!({
            "tag_path": shader.name(), "shader_class": "schi", "h2_template": template_name,
            "shader_flags": 4, "framebuffer_blend_function": blend, "base_map": base,
            "tag": {"flags": 4, "framebuffer_blend_function": blend, "maps": maps},
        });
        ("schi", "BLEND", true, s)
    } else {
        let detail2 = role("detail2");
        let s = json!({
            "tag_path": shader.name(), "shader_class": "shad", "h2_template": template_name,
            "h2_material": root.sid(0x08),
            // A second detail blends over the first by the base map's alpha,
            // CE's "blended" environment type.
            "shader_type": if detail2.is_some() { 1 } else { 0 },
            "shader_flags": 0,
            "base_map": base,
            "base_map_has_alpha": tpl.alpha_tested,
            "detail": {
                "function": 0,
                "primary": role("detail"), "primary_scale": rel("detail"),
                "secondary": detail2, "secondary_scale": rel("detail2"),
                "micro": Value::Null, "micro_scale": 1.0, "micro_function": 0,
            },
            "bump": {"map": role("bump"), "scale": rel("bump")},
            "self_illum": {"map": role("self_illum"), "map_scale": 1.0, "on_color": [1.0, 1.0, 1.0]},
            "specular": {"flags": 0, "brightness": 0.0},
        });
        ("shad", if tpl.alpha_tested { "MASK" } else { "OPAQUE" }, false, s)
    };
    Shader { key, class, alpha_mode, double_sided, base, base_scale, summary }
}

/// One primitive under construction.
#[derive(Default)]
struct Prim {
    positions: Vec<[f32; 3]>,
    normals: Vec<[f32; 3]>,
    tangents: Vec<[f32; 4]>,
    uv0: Vec<[f32; 2]>,
    uv1: Vec<[f32; 2]>,
    incident: Vec<[f32; 3]>,
    indices: Vec<u32>,
}

/// A frame placing definition-space geometry in the world.
#[derive(Clone, Copy)]
struct Frame {
    scale: f32,
    axes: [[f32; 3]; 3],
    origin: [f32; 3],
}

impl Frame {
    const IDENTITY: Frame = Frame { scale: 1.0, axes: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], origin: [0.0; 3] };
    fn point(&self, v: [f32; 3]) -> [f32; 3] {
        std::array::from_fn(|k| self.origin[k] + self.scale * (v[0] * self.axes[0][k] + v[1] * self.axes[1][k] + v[2] * self.axes[2][k]))
    }
    fn dir(&self, v: [f32; 3]) -> [f32; 3] {
        std::array::from_fn(|k| v[0] * self.axes[0][k] + v[1] * self.axes[1][k] + v[2] * self.axes[2][k])
    }
}

fn normalize(v: [f32; 3]) -> [f32; 3] {
    let l = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt();
    if l < 1e-12 {
        [0.0, 1.0, 0.0]
    } else {
        [v[0] / l, v[1] / l, v[2] / l]
    }
}

fn cross(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
}

impl Prim {
    /// Add a part's triangles; `uv1` replaces every vertex's lightmap
    /// coordinate when given (a vertex-lit piece on its flat page).
    fn add(&mut self, section: &Section, part: &geometry::Part, frame: Frame, base_scale: [f32; 2], uv1: Option<[f32; 2]>) {
        let tris = section.triangles(part);
        let mut remap: BTreeMap<u32, u32> = BTreeMap::new();
        for t in tris {
            for i in t {
                let next = self.positions.len() as u32;
                let out = *remap.entry(i).or_insert_with(|| {
                    let v = &section.vertices[i as usize];
                    let p = frame.point(v.position);
                    let n = normalize(frame.dir(v.normal));
                    let tg = normalize(frame.dir(v.tangent));
                    let b = frame.dir(v.binormal);
                    let w = if cross(n, tg).iter().zip(b).map(|(a, b)| a * b).sum::<f32>() < 0.0 { -1.0 } else { 1.0 };
                    let pg = to_gltf(p);
                    self.positions.push([pg[0] * WU_TO_M, pg[1] * WU_TO_M, pg[2] * WU_TO_M]);
                    self.normals.push(to_gltf(n));
                    let tg = to_gltf(tg);
                    self.tangents.push([tg[0], tg[1], tg[2], w]);
                    self.uv0.push([v.uv[0] * base_scale[0], v.uv[1] * base_scale[1]]);
                    self.uv1.push(uv1.unwrap_or(v.lightmap_uv));
                    self.incident.push(if section.has_incident { to_gltf(frame.dir(v.incident)) } else { [0.0; 3] });
                    next
                });
                self.indices.push(out);
            }
        }
    }
}

/// The mean colour of the staged lightmap pages, as the flat page for
/// vertex-lit geometry.
fn average_light(dir: &Path, pages: &[String]) -> Option<[u8; 3]> {
    let (mut sum, mut n) = ([0f64; 3], 0f64);
    for page in pages.iter().filter(|p| !p.is_empty()) {
        let file = std::fs::File::open(dir.join(page)).ok()?;
        let mut reader = png::Decoder::new(std::io::BufReader::new(file)).read_info().ok()?;
        let mut buf = vec![0; reader.output_buffer_size()];
        let info = reader.next_frame(&mut buf).ok()?;
        for px in buf[..info.buffer_size()].chunks_exact(4) {
            for k in 0..3 {
                sum[k] += px[k] as f64;
            }
            n += 1.0;
        }
    }
    (n > 0.0).then(|| sum.map(|v| (v / n).round() as u8))
}

/// A BSP section's packing (section info: flags at +0x16, bounds at
/// +0x18). Lockout's clusters and instanced geometry carry no bounds: plain
/// world positions.
fn section_compression(s: Struct<'_>) -> Compression {
    Compression::from(s.u16(0x16), s.block(0x18, 0x38).get(0))
}

/// The scenario BSP's lightmap: its bitmap group and each cluster's and
/// instance's submap.
struct Lightmap<'a> {
    bitmap: Option<Tag<'a>>,
    clusters: Vec<i16>,
    instances: Vec<i16>,
}

fn lightmap<'a>(cache: &'a Cache, bsp_entry: Struct<'a>) -> Lightmap<'a> {
    let group = bsp_entry.tagref(0x18).and_then(|r| cache.follow(r)).and_then(|t| t.root.block(0x80, 0x68).get(0));
    let Some(g) = group else { return Lightmap { bitmap: None, clusters: vec![], instances: vec![] } };
    Lightmap {
        bitmap: g.tagref(0x18).and_then(|r| cache.follow(r)),
        clusters: g.block(0x28, 4).iter().map(|e| e.i16(0)).collect(),
        instances: g.block(0x48, 4).iter().map(|e| e.i16(0)).collect(),
    }
}

/// The staging's render side: one texture bank and one shader table for the
/// BSP and every model, written out as `materials.json` by [`Renderer::finish`].
pub struct Renderer<'c> {
    cache: &'c Cache,
    dir: std::path::PathBuf,
    tex: Textures,
    /// Shader summaries by the shader tag's (file, datum).
    shaders: Vec<Shader>,
    shader_index: BTreeMap<(usize, u32), usize>,
    models: BTreeMap<String, Option<Value>>,
    pub notes: Vec<String>,
}

impl<'c> Renderer<'c> {
    pub fn new(cache: &'c Cache, dir: &Path) -> Renderer<'c> {
        Renderer {
            cache,
            dir: dir.to_path_buf(),
            tex: Textures::default(),
            shaders: Vec::new(),
            shader_index: BTreeMap::new(),
            models: BTreeMap::new(),
            notes: Vec::new(),
        }
    }

    /// The summary index of the shader a reference names (a missing
    /// shader's summary when it names none).
    fn shader(&mut self, tag: Option<Tag<'c>>) -> usize {
        let key = tag.map(|t| (t.file as *const CacheFile as usize, t.entry.datum)).unwrap_or((0, u32::MAX));
        if let Some(&i) = self.shader_index.get(&key) {
            return i;
        }
        let sh = shader_summary(self.cache, tag, &self.dir, &mut self.tex, &mut self.notes);
        self.shaders.push(sh);
        self.shader_index.insert(key, self.shaders.len() - 1);
        self.shaders.len() - 1
    }

    /// Stage the BSP's render geometry; the manifest fields it fills.
    pub fn bsp(&mut self, sbsp: &Tag<'c>, bsp_entry: Struct<'c>) -> Result<Value, Error> {
        let cache = self.cache;
        let lm = lightmap(cache, bsp_entry);
        // Every lightmap submap, as the manifest's page list (index = page).
        let mut pages: Vec<String> = Vec::new();
        if let Some(b) = &lm.bitmap {
            for k in 0..bitmap::infos(b).len() as u32 {
                pages.push(self.tex.stage_with(cache, b, k, &self.dir, &mut self.notes, LIGHTMAP_GAIN).unwrap_or_default());
            }
        }
        // sbsp materials (32 bytes: old shader ref, shader ref, ...).
        let materials: Vec<usize> = sbsp
            .root
            .block(0xA4, 0x20)
            .iter()
            .map(|m| m.tagref(0x08).or_else(|| m.tagref(0x00)).and_then(|r| cache.follow(r)))
            .collect::<Vec<_>>()
            .into_iter()
            .map(|t| self.shader(t))
            .collect();

        // Vertex-lit pieces (instanced geometry Halo 2 lights from per-vertex
        // buckets, not read yet) go on a flat page of the level's average
        // light, the page after the last, rather than drawing fullbright.
        let flat_page = pages.len() as i16;
        // (shader, page) -> primitive, in first-seen order.
        let mut order: Vec<(usize, Option<i16>)> = Vec::new();
        let mut prims: BTreeMap<(usize, Option<i16>), Prim> = BTreeMap::new();
        let shaders = &self.shaders;
        let mut add_section = |section: &Section, frame: Frame, page: Option<i16>| {
            let (page, uv1) = match page.filter(|&p| p >= 0 && section.has_lightmap_uv) {
                Some(p) => (p, None),
                None => (flat_page, Some([0.5, 0.5])),
            };
            for part in section.parts.iter().filter(|p| p.is_drawn()) {
                let Some(&s) = materials.get(part.material.max(0) as usize) else { continue };
                let key = (s, Some(page));
                if !prims.contains_key(&key) {
                    order.push(key);
                }
                prims.entry(key).or_default().add(section, part, frame, shaders[s].base_scale, uv1);
            }
        };
        for (i, c) in sbsp.root.block(0x9C, 0xB0).iter().enumerate() {
            let section = geometry::read(cache, sbsp.file, c.at(0x28), c.u16(0) as usize, section_compression(c))?;
            add_section(&section, Frame::IDENTITY, lm.clusters.get(i).copied());
        }
        let defs: Vec<Section> = sbsp
            .root
            .block(0x138, 0xC8)
            .iter()
            .map(|d| geometry::read(cache, sbsp.file, d.at(0x28), d.u16(0) as usize, section_compression(d)))
            .collect::<Result<_, _>>()?;
        for (i, inst) in sbsp.root.block(0x140, 0x58).iter().enumerate() {
            let Some(def) = defs.get(inst.i16(0x34).max(0) as usize) else { continue };
            let scale = if inst.f32(0) == 0.0 { 1.0 } else { inst.f32(0) };
            let frame = Frame { scale, axes: [inst.vec3(0x04), inst.vec3(0x10), inst.vec3(0x1C)], origin: inst.vec3(0x28) };
            add_section(def, frame, lm.instances.get(i).copied());
        }

        if order.iter().any(|k| k.1 == Some(flat_page)) {
            // Named as the pages after page 0 are (`<page 0 stem>_<N>`):
            // lightmap_bake finds page N by that name, not by the manifest.
            let png = match pages.first().and_then(|p| p.strip_suffix(".png")) {
                Some(stem) if !stem.is_empty() => format!("{stem}_{flat_page}.png"),
                _ => "h2_vertex_lit.png".to_string(),
            };
            let mean = average_light(&self.dir.join("textures"), &pages).unwrap_or([128, 128, 128]);
            let img = bitmap::Image { width: 4, height: 4, rgba: [mean[0], mean[1], mean[2], 255].repeat(16) };
            bitmap::write_png(&self.dir.join("textures").join(&png), &img)?;
            self.notes.push(format!("vertex-lit geometry drawn on a flat page of the level's average light {mean:?}"));
            pages.push(png);
        }

        // The glTF: one buffer, one mesh, a primitive per (shader, page).
        let mut gltf = Gltf::default();
        let mut primitives = Vec::new();
        let (mut vertices, mut triangles) = (0usize, 0usize);
        for key in &order {
            let p = &prims[key];
            let sh = &self.shaders[key.0];
            let page = key.1.and_then(|k| pages.get(k as usize).filter(|s| !s.is_empty()).cloned());
            let name = match key.1 {
                Some(k) => format!("{}__lm{k}", sh.key),
                None => sh.key.clone(),
            };
            let extras = json!({"halo": {
                "tag_path": sh.summary["tag_path"], "shader_class": sh.class, "material": sh.key,
                "lightmap_index": key.1, "lightmap_texture": page,
            }});
            let material = gltf.material(&name, sh.base.as_deref(), sh.alpha_mode, sh.double_sided, extras);
            vertices += p.positions.len();
            triangles += p.indices.len() / 3;
            primitives.push(gltf.primitive(p, material));
        }
        gltf.write(&self.dir.join("bsp"), "bsp_0", primitives)?;
        Ok(json!({
            "surfaces": order.len(),
            "vertices": vertices,
            "triangles": triangles,
            "lightmap_pages": pages,
        }))
    }

    /// Stage a render model (`mode`) as `models/<name>__<class>.gltf`, in
    /// model space: every region's first permutation at its most detailed
    /// level, one primitive per shader, named for the shader (the scene
    /// merge adds the object lighting suffix). Returns the manifest's model
    /// record (`gltf` relative to the staging), or `None` when the model has
    /// no drawable geometry.
    pub fn model(&mut self, mode: &Tag<'c>, object: &str, class: &str) -> Result<Option<Value>, Error> {
        let rel = format!("models/{}__{class}.gltf", sanitize(object));
        if let Some(done) = self.models.get(&rel) {
            return Ok(done.clone());
        }
        let cache = self.cache;
        let root = mode.root;
        // MCC's mode: regions 0x1C (16 bytes: name, i16, i16, permutations
        // 0x08), sections 0x24 (0x5C: u32 classification, the section info
        // from 0x04, geometry block info at 0x38), nodes 0x48, materials
        // 0x60 (0x20: old shader ref, shader ref at 0x08).
        let materials: Vec<usize> = root
            .block(0x60, 0x20)
            .iter()
            .map(|m| m.tagref(0x08).or_else(|| m.tagref(0x00)).and_then(|r| cache.follow(r)))
            .collect::<Vec<_>>()
            .into_iter()
            .map(|t| self.shader(t))
            .collect();
        if root.block(0x48, 0x60).count > 1 {
            self.notes.push(format!("{}: {} nodes; sections are staged in model space without node transforms", mode.name(), root.block(0x48, 0x60).count));
        }
        let sections = root.block(0x24, 0x5C);
        let mut wanted = Vec::new();
        for region in root.block(0x1C, 0x10).iter() {
            let Some(perm) = region.block(0x08, 0x10).get(0) else { continue };
            // L1 (super low) .. L6 (super high): the last that is set.
            if let Some(s) = (0..6).rev().map(|k| perm.i16(0x04 + 2 * k)).find(|&s| s >= 0) {
                if !wanted.contains(&s) {
                    wanted.push(s);
                }
            }
        }
        let mut order: Vec<usize> = Vec::new();
        let mut prims: BTreeMap<usize, Prim> = BTreeMap::new();
        for s in wanted {
            let Some(sec) = sections.get(s as usize) else { continue };
            // The section info starts at +0x04 here: its compression flags
            // at +0x1A, its own bounds (rarely set) at +0x1C, else the
            // model's at the root's +0x14.
            let bounds = sec.block(0x1C, 0x38).get(0).or_else(|| root.block(0x14, 0x38).get(0));
            let compression = Compression::from(sec.u16(0x1A), bounds);
            let section = match geometry::read(cache, mode.file, sec.at(0x38), sec.u16(0x04) as usize, compression) {
                Ok(s) => s,
                Err(e) => {
                    self.notes.push(format!("{} section {s}: {e}; left out", mode.name()));
                    continue;
                }
            };
            for part in section.parts.iter().filter(|p| p.is_drawn()) {
                let Some(&m) = materials.get(part.material.max(0) as usize) else { continue };
                if !prims.contains_key(&m) {
                    order.push(m);
                }
                prims.entry(m).or_default().add(&section, part, Frame::IDENTITY, self.shaders[m].base_scale, Some([0.0, 0.0]));
            }
        }
        if order.is_empty() {
            self.models.insert(rel, None);
            return Ok(None);
        }
        let mut gltf = Gltf::default();
        let mut primitives = Vec::new();
        let mut triangles = 0;
        for m in &order {
            let sh = &self.shaders[*m];
            let extras = json!({"halo": {"tag_path": sh.summary["tag_path"], "shader_class": sh.class, "material": sh.key}});
            let material = gltf.material(&sh.key, sh.base.as_deref(), sh.alpha_mode, sh.double_sided, extras);
            triangles += prims[m].indices.len() / 3;
            primitives.push(gltf.primitive(&prims[m], material));
        }
        let stem = rel.trim_start_matches("models/").trim_end_matches(".gltf").to_string();
        gltf.write(&self.dir.join("models"), &stem, primitives)?;
        let record = json!({"tag_path": object, "tag_class": class, "gltf": rel, "skeletal": false, "triangles": triangles});
        self.models.insert(rel, Some(record.clone()));
        Ok(Some(record))
    }

    /// Write `materials.json` (every shader the BSP and models used, keyed by
    /// the glTF material name without its lightmap suffix); the model records.
    pub fn finish(self, summary: &mut Summary) -> Result<Vec<Value>, Error> {
        let mut materials = serde_json::Map::new();
        for sh in &self.shaders {
            materials.entry(sh.key.clone()).or_insert_with(|| {
                json!({"tag_path": sh.summary["tag_path"], "shader_class": sh.class, "alpha_mode": sh.alpha_mode,
                       "double_sided": sh.double_sided, "base_map": sh.base, "shader": sh.summary})
            });
        }
        let text = serde_json::to_string_pretty(&Value::Object(materials)).map_err(|e| Error::Format(e.to_string()))?;
        let path = self.dir.join("materials.json");
        std::fs::write(&path, text + "\n").map_err(|e| Error::Io(path, e))?;
        summary.notes.extend(self.notes);
        Ok(self.models.into_values().flatten().collect())
    }
}

/// A minimal glTF 2.0 writer for the staging's meshes.
#[derive(Default)]
pub(crate) struct Gltf {
    bin: Vec<u8>,
    views: Vec<Value>,
    accessors: Vec<Value>,
    materials: Vec<Value>,
    material_index: BTreeMap<String, usize>,
    images: Vec<Value>,
    image_index: BTreeMap<String, usize>,
}

impl Gltf {
    fn view(&mut self, bytes: &[u8], target: u32) -> usize {
        while self.bin.len() % 4 != 0 {
            self.bin.push(0);
        }
        let at = self.bin.len();
        self.bin.extend_from_slice(bytes);
        self.views.push(json!({"buffer": 0, "byteOffset": at, "byteLength": bytes.len(), "target": target}));
        self.views.len() - 1
    }

    fn floats<const N: usize>(&mut self, data: &[[f32; N]], kind: &str, bounds: bool) -> usize {
        let mut bytes = Vec::with_capacity(data.len() * N * 4);
        for v in data {
            for x in v {
                bytes.extend_from_slice(&x.to_le_bytes());
            }
        }
        let view = self.view(&bytes, 34962);
        let mut a = json!({"bufferView": view, "componentType": 5126, "count": data.len(), "type": kind});
        if bounds && !data.is_empty() {
            let lo: Vec<f32> = (0..N).map(|k| data.iter().map(|v| v[k]).fold(f32::INFINITY, f32::min)).collect();
            let hi: Vec<f32> = (0..N).map(|k| data.iter().map(|v| v[k]).fold(f32::NEG_INFINITY, f32::max)).collect();
            a["min"] = json!(lo);
            a["max"] = json!(hi);
        }
        self.accessors.push(a);
        self.accessors.len() - 1
    }

    fn primitive(&mut self, p: &Prim, material: usize) -> Value {
        let pos = self.floats(&p.positions, "VEC3", true);
        let nrm = self.floats(&p.normals, "VEC3", false);
        let tan = self.floats(&p.tangents, "VEC4", false);
        let uv0 = self.floats(&p.uv0, "VEC2", false);
        let uv1 = self.floats(&p.uv1, "VEC2", false);
        let inc = self.floats(&p.incident, "VEC3", false);
        let idx_bytes: Vec<u8> = p.indices.iter().flat_map(|i| i.to_le_bytes()).collect();
        let view = self.view(&idx_bytes, 34963);
        self.accessors.push(json!({"bufferView": view, "componentType": 5125, "count": p.indices.len(), "type": "SCALAR"}));
        let idx = self.accessors.len() - 1;
        json!({
            "attributes": {"POSITION": pos, "NORMAL": nrm, "TANGENT": tan, "TEXCOORD_0": uv0, "TEXCOORD_1": uv1, "_INCIDENT": inc},
            "indices": idx, "material": material, "mode": 4,
        })
    }

    fn material(&mut self, name: &str, base: Option<&str>, alpha: &str, double_sided: bool, extras: Value) -> usize {
        if let Some(&i) = self.material_index.get(name) {
            return i;
        }
        let mut pbr = json!({"baseColorFactor": [1.0, 1.0, 1.0, 1.0], "metallicFactor": 0.0, "roughnessFactor": 1.0});
        if let Some(png) = base {
            let uri = format!("../textures/{png}");
            let image = match self.image_index.get(&uri) {
                Some(&i) => i,
                None => {
                    self.images.push(json!({"uri": uri}));
                    self.image_index.insert(uri.clone(), self.images.len() - 1);
                    self.images.len() - 1
                }
            };
            pbr["baseColorTexture"] = json!({"index": image, "texCoord": 0});
        }
        let mut m = json!({"name": name, "pbrMetallicRoughness": pbr, "extras": extras});
        match alpha {
            "MASK" => {
                m["alphaMode"] = json!("MASK");
                m["alphaCutoff"] = json!(0.5);
            }
            "BLEND" => m["alphaMode"] = json!("BLEND"),
            _ => {}
        }
        if double_sided {
            m["doubleSided"] = json!(true);
        }
        self.materials.push(m);
        self.material_index.insert(name.to_string(), self.materials.len() - 1);
        self.materials.len() - 1
    }

    pub(crate) fn write(self, dir: &Path, name: &str, primitives: Vec<Value>) -> Result<(), Error> {
        // Textures index images one to one, through one sampler.
        let textures: Vec<Value> = (0..self.images.len()).map(|i| json!({"source": i, "sampler": 0})).collect();
        let doc = json!({
            "asset": {"version": "2.0", "generator": "mjolnir cache stage"},
            "scene": 0,
            "scenes": [{"nodes": [0]}],
            "nodes": [{"name": name, "mesh": 0}],
            "meshes": [{"name": name, "primitives": primitives}],
            "buffers": [{"uri": format!("{name}.bin"), "byteLength": self.bin.len()}],
            "bufferViews": self.views,
            "accessors": self.accessors,
            "materials": self.materials,
            "images": self.images,
            "textures": textures,
            "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
        });
        std::fs::write(dir.join(format!("{name}.bin")), &self.bin).map_err(|e| Error::Io(dir.join(format!("{name}.bin")), e))?;
        let text = serde_json::to_string(&doc).map_err(|e| Error::Format(e.to_string()))?;
        std::fs::write(dir.join(format!("{name}.gltf")), text).map_err(|e| Error::Io(dir.join(format!("{name}.gltf")), e))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The slot tables put the base map where Lockout's shaders have it.
    #[test]
    fn templates_find_their_base_maps() {
        assert_eq!(template("tex_bump").slots[2], "base");
        assert_eq!(template("tex_bump_illum").slots[1], "base");
        assert_eq!(template("tex_bump_detail_blend").slots[1], "base");
        assert_eq!(template("tex_bump_alpha_test").slots[3], "base");
        assert!(template("tex_bump_alpha_test").alpha_tested);
        assert_eq!(template("one_alpha_env").transparent, 1);
        assert_eq!(template("plasma_alpha").transparent, 4);
        assert_eq!(template("one_add_two_plus_two").transparent, 4);
        assert_eq!(template("tex_bump_env_illum_combined").slots[5], "self_illum");
    }

    /// Only tex_bump_detail_blend keeps its details' tiling first; its
    /// siblings are bump-first (on the 24 maps their constant 1 is always
    /// (1, 1), the base). Every alpha-test variant cuts out.
    #[test]
    fn detail_templates_read_the_base_tiling_where_it_is() {
        let base = |n: &str| template(n).tiling.iter().find(|t| t.0 == "base").map(|t| t.1);
        assert_eq!(base("tex_bump_detail_blend"), Some(2));
        assert_eq!(base("tex_bump_detail_keep"), Some(1));
        assert_eq!(base("tex_bump_detail_blend_detail"), Some(1));
        assert_eq!(base("tex_bump_three_detail_blend"), Some(1));
        assert!(template("tex_bump_env_alpha_test").alpha_tested);
        assert_eq!(template("tex_bump_alpha_test_single_pass").slots[2], "base");
        assert_eq!(template("tex_bump_alpha_test_single_pass").transparent, 0);
    }

    /// Halo (x, y, z) is glTF (x, z, -y): a rotation, so winding survives.
    #[test]
    fn the_axis_swap_is_a_rotation() {
        let (x, y, z) = (to_gltf([1.0, 0.0, 0.0]), to_gltf([0.0, 1.0, 0.0]), to_gltf([0.0, 0.0, 1.0]));
        assert_eq!(cross(x, y), z);
    }
}
