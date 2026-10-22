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

/// The vertex-lit page: one block per vertex-lit instance.
const TEXEL_BLOCK: usize = 4;
const TEXELS_PER_ROW: usize = 16;
const TEXEL_ROWS_MAX: usize = 16;

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
        // Glass: an environment cube through a specular mask, the base map
        // blended by its alpha, a self-illumination map (the sky dome's
        // layers use the same slots with a black cube).
        n if n.ends_with("one_alpha_env") => t(&["env", "mask", "base", "", "self_illum"], &[], 1, false),
        n if n.ends_with("one_alpha_env_illum") => t(&["env", "mask", "base", "self_illum"], &[], 1, false),
        // Plasma: two scrolling noise maps banded against each other, through
        // the mask's alpha, added to the frame.
        "plasma_alpha" => t(&["noise_a", "noise_b", "mask"], &[], 4, false),
        // "two plus two": the mask and two tiled, scrolling layers multiplied
        // together and alpha blended (the sky's cloud banks, the containment
        // gas); the compiled shader is a product, whatever the name says. The
        // maps' transforms are 2 x 4 rows per map in the vertex constants,
        // read by [`two_plus_two_maps`].
        n if n.contains("two_plus_two") => t(&["mask", "base", "base2"], &[], 1, false),
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

/// Staged bitmaps: PNG (and DDS) per (bitm datum in its file, submap,
/// tint), cube maps as six face PNGs.
#[derive(Default)]
struct Textures {
    done: BTreeMap<(usize, u32, u32, String), Option<String>>,
    cubes: BTreeMap<(usize, u32), Option<Vec<String>>>,
    names: BTreeMap<String, usize>,
}

/// A colour multiplier, as the suffix of a tinted copy's file name.
fn tint_suffix(gain: [f32; 3]) -> String {
    if gain == [1.0; 3] {
        String::new()
    } else {
        format!("__t{:02x}{:02x}{:02x}", (gain[0] * 100.0).round().min(255.0) as u8, (gain[1] * 100.0).round().min(255.0) as u8, (gain[2] * 100.0).round().min(255.0) as u8)
    }
}

impl Textures {
    /// Stage one submap of a bitmap tag; its PNG's file name, or `None`
    /// (with a note) when it cannot be decoded.
    fn stage(&mut self, cache: &Cache, tag: &Tag<'_>, index: u32, dir: &Path, notes: &mut Vec<String>) -> Option<String> {
        self.stage_with(cache, tag, index, dir, notes, [1.0; 3], "")
    }

    /// As [`Textures::stage`], each channel scaled by `gain` (clamped), the
    /// file named with `suffix` (a tinted copy of a map is
    /// `<stem>__t<rrggbb>.png`, the tint in hundredths; the lightmap pages,
    /// doubled, keep their plain names, which the bake finds page N by).
    fn stage_with(
        &mut self,
        cache: &Cache,
        tag: &Tag<'_>,
        index: u32,
        dir: &Path,
        notes: &mut Vec<String>,
        gain: [f32; 3],
        suffix: &str,
    ) -> Option<String> {
        let key = (tag.file as *const CacheFile as usize, tag.entry.datum, index, suffix.to_string());
        if let Some(done) = self.done.get(&key) {
            return done.clone();
        }
        let result = (|| -> Result<String, Error> {
            let textures = cache.textures.as_ref().ok_or_else(|| Error::Unsupported("no textures.dat".into()))?;
            let infos = bitmap::infos(tag);
            let info = infos.get(index as usize).ok_or_else(|| Error::Format(format!("no bitmap {index}")))?;
            let data = bitmap::read_entry(textures, info.offset, info.size)?;
            let mut mips = bitmap::decode(info, &data)?;
            if gain != [1.0; 3] {
                for m in &mut mips {
                    for p in m.rgba.chunks_exact_mut(4) {
                        for (c, g) in p[..3].iter_mut().zip(gain) {
                            *c = (*c as f32 * g).round().min(255.0) as u8;
                        }
                    }
                }
            }
            let mut stem = sanitize(tag.name());
            if index > 0 {
                stem = format!("{stem}_{index}");
            }
            stem.push_str(suffix);
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

    /// Stage a cube map's six faces as `<stem>__face<k>.png` in D3D order
    /// (what tools/level/ce_material_spec.py's `cube()` assembles into a
    /// TextureCube); the six names, or `None` with a note.
    fn stage_cube(&mut self, cache: &Cache, tag: &Tag<'_>, dir: &Path, notes: &mut Vec<String>) -> Option<Vec<String>> {
        let key = (tag.file as *const CacheFile as usize, tag.entry.datum);
        if let Some(done) = self.cubes.get(&key) {
            return done.clone();
        }
        let result = (|| -> Result<Vec<String>, Error> {
            let textures = cache.textures.as_ref().ok_or_else(|| Error::Unsupported("no textures.dat".into()))?;
            let infos = bitmap::infos(tag);
            let info = infos.first().ok_or_else(|| Error::Format("no bitmap".into()))?;
            let data = bitmap::read_entry(textures, info.offset, info.size)?;
            let faces = bitmap::decode_cube(info, &data)?;
            let stem = sanitize(tag.name());
            let mut names = Vec::new();
            for (k, face) in faces.iter().enumerate() {
                let name = format!("{stem}__face{k}.png");
                bitmap::write_png(&dir.join("textures").join(&name), face)?;
                names.push(name);
            }
            Ok(names)
        })();
        let out = match result {
            Ok(faces) => Some(faces),
            Err(e) => {
                notes.push(format!("cube map {}: {e}", tag.name()));
                None
            }
        };
        self.cubes.insert(key, out.clone());
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
    /// Drawn without a lightmap (Halo 2's glass takes none).
    unlit: bool,
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
            unlit: false,
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
    let mut tags: BTreeMap<&str, Tag<'_>> = BTreeMap::new();
    let mut cube_faces: Option<Vec<String>> = None;
    let mut constants: Vec<[f32; 4]> = Vec::new();
    // Pixel constants: D3DCOLOR (B, G, R, A) each, here as RGBA in 0..1.
    let mut pixel: Vec<[f32; 4]> = Vec::new();
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
            if role == "env" {
                cube_faces = tex.stage_cube(cache, &t, dir, notes);
                continue;
            }
            roles.insert(role, tex.stage(cache, &t, b.u32(4).max(0), dir, notes));
            tags.insert(role, t);
        }
        constants = p.block(0x14, 0x10).iter().map(|c| [c.f32(0), c.f32(4), c.f32(8), c.f32(12)]).collect();
        pixel = p
            .block(0x0C, 4)
            .iter()
            .map(|c| [c.u8(2) as f32 / 255.0, c.u8(1) as f32 / 255.0, c.u8(0) as f32 / 255.0, c.u8(3) as f32 / 255.0])
            .collect();
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
    let rgb = |c: Option<&[f32; 4]>| -> [f32; 3] { c.map(|c| [c[0], c[1], c[2]]).unwrap_or([1.0; 3]) };
    let mul = |a: [f32; 3], b: [f32; 3]| [a[0] * b[0], a[1] * b[1], a[2] * b[2]];
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
    let mut unlit = false;
    let (class, alpha_mode, double_sided, base, summary) = if template_name.contains("one_alpha_env") && !template_name.starts_with("sky_") {
        // Glass (one_alpha_env, one_alpha_env_illum; the compiled MCC shader
        // read back): colour = base.rgb * albedo tint * base.a + cube(R) *
        // env tint * specular mask, both scaled by a tint between the facing
        // and glancing colours; unlit. As CE's shader_transparent_glass: the
        // diffuse pass draws the base copy tinted by the albedo and facing
        // tints (flag bit 3 makes the bump map the reflection's specular
        // mask), the reflection pass the cube, tinted by the environment and
        // facing/glancing tints. Pixel constants: 0 env tint, 1 albedo tint;
        // vertex constants: 0 facing tint, 1 glancing tint.
        unlit = true;
        let albedo = rgb(pixel.get(1));
        let facing = rgb(constants.get(0));
        let glancing = rgb(constants.get(1));
        let env = rgb(pixel.get(0));
        let tinted = tags.get("base").and_then(|t| tex.stage_with(cache, t, 0, dir, notes, mul(albedo, facing), &tint_suffix(mul(albedo, facing))));
        let reflects = cube_faces.is_some();
        let s = json!({
            "tag_path": shader.name(), "shader_class": "sgla", "h2_template": template_name,
            "shader_flags": 8, "base_map": tinted,
            "tag": {
                "flags": 8,
                "diffuse_map": {"file": tinted}, "diffuse_map_scale": 1.0,
                "bump_map": {"file": role("mask")}, "bump_map_scale": 1.0,
                "reflection_map": cube_faces.as_ref().map(|f| json!({"faces": f})),
                "reflection_type": 1,
                "perpendicular_brightness": if reflects { 1.0 } else { 0.0 },
                "parallel_brightness": if reflects { 1.0 } else { 0.0 },
                "perpendicular_tint_color": mul(env, facing),
                "parallel_tint_color": mul(env, glancing),
                "background_tint_color": [0.0, 0.0, 0.0],
            },
        });
        ("sgla", "BLEND", false, tinted, s)
    } else if tpl.transparent > 0 {
        let blend = (tpl.transparent - 1) as i64;
        let (maps, base, two_sided) = if template_name.contains("two_plus_two") {
            // mask * A * B, alpha the product of theirs (the compiled shader
            // multiplies all three, whatever the name says), two-sided.
            (two_plus_two_maps(&role, &constants, &slot_scroll(post)), base, true)
        } else if template_name == "plasma_alpha" {
            // noise A * noise B * the mask's alpha, added to the frame; the
            // "medium" colour (pixel constant 0) is baked into noise A.
            let medium = rgb(pixel.get(0));
            let a = tags.get("noise_a").and_then(|t| tex.stage_with(cache, t, 0, dir, notes, [medium[0] * 2.0, medium[1] * 2.0, medium[2] * 2.0], &tint_suffix([medium[0] * 2.0, medium[1] * 2.0, medium[2] * 2.0])));
            let scroll = slot_scroll(post);
            let rows = |k: usize| two_plus_two_rows(&constants, k);
            let (ra, rb, rm) = (rows(0), rows(1), rows(2));
            let mut maps = vec![
                json!({"map": {"file": a}, "color_function": 2, "alpha_function": 2, "map_u_scale": ra[0], "map_v_scale": ra[1], "map_u_offset": ra[2], "map_v_offset": ra[3]}),
                json!({"map": {"file": role("noise_b")}, "color_function": 2, "alpha_function": 2, "flags": 2, "map_u_scale": rb[0], "map_v_scale": rb[1], "map_u_offset": rb[2], "map_v_offset": rb[3]}),
                json!({"map": {"file": role("mask")}, "color_function": 0, "alpha_function": 0, "map_u_scale": rm[0], "map_v_scale": rm[1], "map_u_offset": rm[2], "map_v_offset": rm[3]}),
            ];
            for (k, m) in maps.iter_mut().enumerate() {
                scroll_json(m, scroll.get(&k));
            }
            (maps, a, true)
        } else {
            // The sky's layers: the base, tinted by the albedo tint (pixel
            // constant 1), blended by its alpha.
            let tinted = match (tags.get("base"), pixel.get(1)) {
                (Some(t), Some(c)) if [c[0], c[1], c[2]] != [1.0; 3] => tex.stage_with(cache, t, 0, dir, notes, [c[0], c[1], c[2]], &tint_suffix([c[0], c[1], c[2]])),
                _ => base,
            };
            (vec![json!({"map": {"file": tinted}, "color_function": 0, "alpha_function": 0,
                         "map_u_scale": base_scale[0], "map_v_scale": base_scale[1]})], tinted, true)
        };
        let flags = if two_sided { 4 } else { 0 };
        let s = json!({
            "tag_path": shader.name(), "shader_class": "schi", "h2_template": template_name,
            "shader_flags": flags, "framebuffer_blend_function": blend, "base_map": base,
            "tag": {"flags": flags, "framebuffer_blend_function": blend, "maps": maps},
        });
        ("schi", "BLEND", two_sided, base, s)
    } else {
        let detail2 = role("detail2");
        // A second detail blends over the first by the base map's alpha,
        // CE's "blended" environment type, which draws its primary detail
        // where the alpha is high. Halo 2 draws its second detail there
        // (Lockout's snow is where composite_block_snow's alpha is high), so
        // the second detail goes in as the primary.
        let (primary, secondary) = match detail2 {
            Some(d2) => (Some(d2), role("detail")),
            None => (role("detail"), None),
        };
        let (primary_scale, secondary_scale) = if secondary.is_some() {
            (rel("detail2"), rel("detail"))
        } else {
            (rel("detail"), 1.0)
        };
        let s = json!({
            "tag_path": shader.name(), "shader_class": "shad", "h2_template": template_name,
            "h2_material": root.sid(0x08),
            "shader_type": if secondary.is_some() { 1 } else { 0 },
            "shader_flags": 0,
            "base_map": base,
            "base_map_has_alpha": tpl.alpha_tested,
            "detail": {
                "function": 0,
                "primary": primary, "primary_scale": primary_scale,
                "secondary": secondary, "secondary_scale": secondary_scale,
                "micro": Value::Null, "micro_scale": 1.0, "micro_function": 0,
            },
            "bump": {"map": role("bump"), "scale": rel("bump")},
            "self_illum": {"map": role("self_illum"), "map_scale": 1.0, "on_color": [1.0, 1.0, 1.0]},
            "specular": {"flags": 0, "brightness": 0.0},
        });
        ("shad", if tpl.alpha_tested { "MASK" } else { "OPAQUE" }, false, base, s)
    };
    Shader { key, class, alpha_mode, double_sided, base, base_scale, unlit, summary }
}

/// A map's scrolling: per axis, (period in seconds, repeats per period).
type Scroll = [Option<(f32, f32)>; 2];

/// A transparent shader's animated texture translations, by bitmap slot,
/// from its postprocess definition: animated parameter refs (+0x54, 4
/// bytes: u16 descriptor, u8, i8 parameter; a descriptor below 0x100 is
/// the bitmap slot), animated parameters (+0x4C, u16: count in the top 7
/// bits, first in the low 9, a range of overlay refs), overlay refs (+0x44:
/// i16 overlay, i16 transform type; 4 translation u, 5 translation v) and
/// overlays (+0x3C, 0x14 bytes: f32 period at 8, the function at 0xC as
/// {size, address}: byte 0 type, 0 identity; the value at t = 0 at +4 and
/// at t = period at +8). Lockout's clouds drift 1 repeat in 200 and 500 s,
/// its lower clouds in 20 and 40 s, the containment gas in 20 to 50 s.
fn slot_scroll(post: Option<Struct<'_>>) -> BTreeMap<usize, Scroll> {
    let mut out: BTreeMap<usize, Scroll> = BTreeMap::new();
    let Some(p) = post else { return out };
    let overlays: Vec<Option<(f32, f32)>> = p
        .block(0x3C, 0x14)
        .iter()
        .map(|o| {
            let period = o.f32(8);
            let at = p.file.offset(o.u32(0x10))?;
            let f = p.file.data.get(at..at + 12)?;
            if f[0] != 0 || period <= 0.0 {
                return None;
            }
            let v = |k: usize| f32::from_le_bytes(f[k..k + 4].try_into().unwrap());
            Some((period, v(8) - v(4)))
        })
        .collect();
    let refs: Vec<(i16, i16)> = p.block(0x44, 4).iter().map(|r| (r.i16(0), r.i16(2))).collect();
    let params: Vec<(usize, usize)> = p.block(0x4C, 2).iter().map(|r| ((r.u16(0) & 0x1FF) as usize, (r.u16(0) >> 9) as usize)).collect();
    for r in p.block(0x54, 4).iter() {
        let (descriptor, param) = (r.u16(0), r.i16(3) as i8);
        if descriptor >= 0x100 || param < 0 {
            continue;
        }
        let Some(&(first, count)) = params.get(param as usize) else { continue };
        let slot = out.entry(descriptor as usize).or_default();
        for &(overlay, transform) in refs.iter().skip(first).take(count) {
            let Some(Some(motion)) = usize::try_from(overlay).ok().and_then(|i| overlays.get(i)) else { continue };
            match transform {
                4 => slot[0] = Some(*motion),
                5 => slot[1] = Some(*motion),
                _ => {}
            }
        }
    }
    out
}

/// CE's chicago map animation for a scroll: function 6 slides the map
/// `scale` repeats every `period` seconds.
fn scroll_json(map: &mut Value, scroll: Option<&Scroll>) {
    let Some(scroll) = scroll else { return };
    for (axis, motion) in ["u", "v"].iter().zip(scroll) {
        if let Some((period, repeats)) = motion {
            map[format!("{axis}_animation_function")] = json!(6);
            map[format!("{axis}_animation_period")] = json!(period);
            map[format!("{axis}_animation_scale")] = json!(repeats);
        }
    }
}

/// Map `k`'s texture transform from a transparent template's vertex
/// constants, which hold a 2 x 4 affine row pair per map (u row, v row:
/// scale in .x / .y, offset in .w): `[u scale, v scale, u offset, v offset]`.
fn two_plus_two_rows(constants: &[[f32; 4]], k: usize) -> [f32; 4] {
    let u = constants.get(2 * k).copied().unwrap_or([1.0, 0.0, 0.0, 0.0]);
    let v = constants.get(2 * k + 1).copied().unwrap_or([0.0, 1.0, 0.0, 0.0]);
    [if u[0] == 0.0 { 1.0 } else { u[0] }, if v[1] == 0.0 { 1.0 } else { v[1] }, u[3], v[3]]
}

/// A "two plus two" template's chicago maps: the mask, layer A and layer B
/// multiplied together, colour and alpha (the compiled MCC shader is a
/// plain product; the sky's cloud banks and the containment gas), each map
/// with its own tiling and offset from the vertex constants (the mask's
/// rows first, then A's, then B's).
fn two_plus_two_maps(role: &dyn Fn(&str) -> Option<String>, constants: &[[f32; 4]], scroll: &BTreeMap<usize, Scroll>) -> Vec<Value> {
    let map = |r: &str, k: usize, function: i64| {
        let x = two_plus_two_rows(constants, k);
        let mut m = json!({"map": {"file": role(r)}, "color_function": function, "alpha_function": function,
               "map_u_scale": x[0], "map_v_scale": x[1], "map_u_offset": x[2], "map_v_offset": x[3]});
        scroll_json(&mut m, scroll.get(&k));
        m
    };
    vec![map("mask", 0, 2), map("base", 1, 2), map("base2", 2, 0)]
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
    /// coordinate when given (a vertex-lit piece on its own texel), and
    /// `incident` gives each definition vertex's incident light direction in
    /// world space (an instance's, from its lightmap bucket) in place of the
    /// section's own.
    fn add(
        &mut self,
        section: &Section,
        part: &geometry::Part,
        frame: Frame,
        base_scale: [f32; 2],
        uv1: Option<[f32; 2]>,
        incident: Option<&[[f32; 3]]>,
    ) {
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
                    self.incident.push(match incident.and_then(|inc| inc.get(i as usize)) {
                        Some(&world) => to_gltf(world),
                        None if section.has_incident => to_gltf(frame.dir(v.incident)),
                        None => [0.0; 3],
                    });
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

/// A lightmap vertex bucket: per vertex, the incident light direction in
/// world space (type 0x2F, 12 bytes) and, for vertex-lit geometry, the
/// light's colour (type 0x2E: u8 R, G, B, 0, in the lightmap pages' units).
#[derive(Default)]
struct Bucket {
    incident: Vec<[f32; 3]>,
    colour: Vec<[u8; 3]>,
}

/// The scenario BSP's lightmap: its bitmap group, each cluster's and
/// instance's submap, and the vertex buckets every instance's light comes
/// from (ltmp group +0x40; the instance bucket refs at +0x50 give the
/// bucket and the instance's first vertex in it, and definition vertex k is
/// bucket vertex offset + k; checked on the 24 maps' 2,341 instances).
struct Lightmap<'a> {
    bitmap: Option<Tag<'a>>,
    clusters: Vec<i16>,
    instances: Vec<i16>,
    buckets: Vec<Bucket>,
    /// Per instance: (bucket, first vertex), or `None` for an empty one.
    refs: Vec<Option<(usize, usize)>>,
}

impl<'a> Lightmap<'a> {
    /// Instance `i`'s vertices in its bucket: the incident directions and,
    /// when the bucket carries colour, the colours, for its definition's
    /// `n` vertices.
    fn instance_vertices(&self, i: usize, n: usize) -> (Option<&[[f32; 3]]>, Option<&[[u8; 3]]>) {
        let Some(Some((b, o))) = self.refs.get(i) else { return (None, None) };
        let Some(bucket) = self.buckets.get(*b) else { return (None, None) };
        let incident = bucket.incident.get(*o..(*o + n).min(bucket.incident.len())).filter(|s| !s.is_empty());
        let colour = bucket.colour.get(*o..(*o + n).min(bucket.colour.len())).filter(|s| !s.is_empty());
        (incident, colour)
    }
}

fn lightmap<'a>(cache: &'a Cache, bsp_entry: Struct<'a>) -> Lightmap<'a> {
    let mut lm = Lightmap { bitmap: None, clusters: vec![], instances: vec![], buckets: vec![], refs: vec![] };
    let Some(tag) = bsp_entry.tagref(0x18).and_then(|r| cache.follow(r)) else { return lm };
    let Some(g) = tag.root.block(0x80, 0x68).get(0) else { return lm };
    lm.bitmap = g.tagref(0x18).and_then(|r| cache.follow(r));
    lm.clusters = g.block(0x28, 4).iter().map(|e| e.i16(0)).collect();
    lm.instances = g.block(0x48, 4).iter().map(|e| e.i16(0)).collect();
    for b in g.block(0x40, 0x38).iter() {
        lm.buckets.push(read_bucket(cache, tag.file, b).unwrap_or_default());
    }
    lm.refs = g
        .block(0x50, 12)
        .iter()
        .map(|r| {
            let offset = r.block(4, 2).get(0).map(|o| o.i16(0)).unwrap_or(-1);
            let bucket = r.i16(2);
            (offset >= 0 && bucket >= 0).then(|| (bucket as usize, offset as usize))
        })
        .collect();
    lm
}

/// A bucket's raw block: like a geometry section's (`blkh`, an 8-byte
/// section struct, `rsrc`, the resources), with the vertex buffer
/// descriptors (type 0 at locator 0, 32 bytes each: type, stride) and the
/// buffers (type 2, by index).
fn read_bucket(cache: &Cache, owner: &CacheFile, b: Struct<'_>) -> Result<Bucket, Error> {
    let raw = b.u32(0x0C);
    if raw == u32::MAX {
        return Ok(Bucket::default());
    }
    let (file, at) = geometry::block(cache, owner, raw)?;
    let d = &file.data;
    let rsrc = at + 8 + b.u32(0x14) as usize;
    if d.get(at..at + 4) != Some(b"hklb") || d.get(rsrc..rsrc + 4) != Some(b"crsr") {
        return Err(Error::Format(format!("no bucket block at {at:#x}")));
    }
    let mut types: Vec<(u8, usize)> = Vec::new();
    let mut buffers: Vec<(usize, &[u8])> = Vec::new();
    for r in b.block(0x1C, 16).iter() {
        let (kind, locator, index) = (r.u8(0), r.u16(2), r.i16(6));
        let (size, off) = (r.u32(8) as usize, rsrc + r.u32(12) as usize);
        let bytes = d.get(off..off + size).ok_or_else(|| Error::Format(format!("bucket resource at {off:#x} runs past the file")))?;
        match (kind, locator) {
            (0, 0) => types = bytes.chunks_exact(32).map(|c| (c[0], c[1] as usize)).collect(),
            (2, _) if index >= 0 => buffers.push((index as usize, bytes)),
            _ => {}
        }
    }
    let mut out = Bucket::default();
    for (index, bytes) in buffers {
        match types.get(index) {
            Some(&(0x2F, 12)) => out.incident = bytes.chunks_exact(12).map(|c| f32s(c, 0)).collect(),
            Some(&(0x2E, 4)) => out.colour = bytes.chunks_exact(4).map(|c| [c[0], c[1], c[2]]).collect(),
            _ => {}
        }
    }
    Ok(out)
}

fn f32s<const N: usize>(b: &[u8], at: usize) -> [f32; N] {
    std::array::from_fn(|i| f32::from_le_bytes(b[at + i * 4..at + i * 4 + 4].try_into().unwrap()))
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
                pages.push(self.tex.stage_with(cache, b, k, &self.dir, &mut self.notes, [LIGHTMAP_GAIN; 3], "").unwrap_or_default());
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
        // buckets) draw on a page of their own, the one after the last, one
        // 4 x 4 block per instance holding that instance's light
        // (`instance_light`, else the level's average), rather than
        // fullbright. Clusters always carry lightmap coordinates.
        let flat_page = pages.len() as i16;
        let mut texels: Vec<usize> = Vec::new();
        let texel_uv = |k: usize| -> [f32; 2] {
            let (col, row) = (k % TEXELS_PER_ROW, k / TEXELS_PER_ROW);
            [(col as f32 + 0.5) / TEXELS_PER_ROW as f32, (row as f32 + 0.5) / TEXEL_ROWS_MAX as f32]
        };
        // (shader, page) -> primitive, in first-seen order.
        let mut order: Vec<(usize, Option<i16>)> = Vec::new();
        let mut prims: BTreeMap<(usize, Option<i16>), Prim> = BTreeMap::new();
        let shaders = &self.shaders;
        let mut texel_light: Vec<Option<[u8; 3]>> = Vec::new();
        let mut add_section = |section: &Section, frame: Frame, page: Option<i16>, instance: Option<usize>| {
            let (incident, colour) = match instance {
                Some(i) => lm.instance_vertices(i, section.vertices.len()),
                None => (None, None),
            };
            let (page, uv1) = match page.filter(|&p| p >= 0 && section.has_lightmap_uv) {
                Some(p) => (p, None),
                None => {
                    let k = texels.len();
                    texels.push(instance.unwrap_or(usize::MAX));
                    // The instance's light: its vertices' mean, in the pages'
                    // units, doubled as the pages are.
                    texel_light.push(colour.map(|c| {
                        let n = c.len() as f32;
                        std::array::from_fn(|k| (c.iter().map(|v| v[k] as f32).sum::<f32>() / n * LIGHTMAP_GAIN).round().min(255.0) as u8)
                    }));
                    (flat_page, Some(texel_uv(k)))
                }
            };
            for part in section.parts.iter().filter(|p| p.is_drawn()) {
                let Some(&s) = materials.get(part.material.max(0) as usize) else { continue };
                let key = (s, Some(page));
                if !prims.contains_key(&key) {
                    order.push(key);
                }
                prims.entry(key).or_default().add(section, part, frame, shaders[s].base_scale, uv1, incident);
            }
        };
        for (i, c) in sbsp.root.block(0x9C, 0xB0).iter().enumerate() {
            let section = geometry::read(cache, sbsp.file, c.at(0x28), c.u16(0) as usize, section_compression(c))?;
            add_section(&section, Frame::IDENTITY, lm.clusters.get(i).copied(), None);
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
            add_section(def, frame, lm.instances.get(i).copied(), Some(i));
        }

        if !texels.is_empty() {
            // Named as the pages after page 0 are (`<page 0 stem>_<N>`):
            // lightmap_bake finds page N by that name, not by the manifest.
            let png = match pages.first().and_then(|p| p.strip_suffix(".png")) {
                Some(stem) if !stem.is_empty() => format!("{stem}_{flat_page}.png"),
                _ => "h2_vertex_lit.png".to_string(),
            };
            let mean = average_light(&self.dir.join("textures"), &pages).unwrap_or([128, 128, 128]);
            let (w, h) = (TEXELS_PER_ROW * TEXEL_BLOCK, TEXEL_ROWS_MAX * TEXEL_BLOCK);
            let mut rgba = vec![0u8; w * h * 4];
            let mut lit = 0;
            for k in 0..texels.len().min(TEXELS_PER_ROW * TEXEL_ROWS_MAX) {
                let c = texel_light.get(k).copied().flatten().inspect(|_| lit += 1).unwrap_or(mean);
                let (x0, y0) = ((k % TEXELS_PER_ROW) * TEXEL_BLOCK, (k / TEXELS_PER_ROW) * TEXEL_BLOCK);
                for y in y0..y0 + TEXEL_BLOCK {
                    for x in x0..x0 + TEXEL_BLOCK {
                        rgba[(y * w + x) * 4..(y * w + x) * 4 + 4].copy_from_slice(&[c[0], c[1], c[2], 255]);
                    }
                }
            }
            let img = bitmap::Image { width: w as u32, height: h as u32, rgba };
            bitmap::write_png(&self.dir.join("textures").join(&png), &img)?;
            self.notes.push(format!(
                "{} vertex-lit piece(s) on a page of their own: {lit} from Halo 2's vertex light, the rest at the level's average {mean:?}",
                texels.len()
            ));
            pages.push(png);
        }

        // The glTF: one buffer, one mesh, a primitive per (shader, page).
        let mut gltf = Gltf::default();
        let mut primitives = Vec::new();
        let (mut vertices, mut triangles) = (0usize, 0usize);
        for key in &order {
            let p = &prims[key];
            let sh = &self.shaders[key.0];
            let page = key.1.and_then(|k| pages.get(k as usize).filter(|s| !s.is_empty()).cloned()).filter(|_| !sh.unlit);
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

    /// Stage a render model (`mode`) as `models/<name>__<class>.gltf` (a
    /// scaled placement's copy as `<name>_x<scale>__<class>.gltf`), in
    /// object space (a section's vertices are stored posed, whatever node
    /// they belong to; the node transforms serve animation): every region's
    /// first permutation at its most detailed level, one primitive per
    /// shader, named for the shader (the scene merge adds the object
    /// lighting suffix). Returns the manifest's model
    /// record (`gltf` relative to the staging), or `None` when the model has
    /// no drawable geometry.
    pub fn model(&mut self, mode: &Tag<'c>, object: &str, class: &str, scale: f32) -> Result<Option<Value>, Error> {
        let rel = format!("models/{}{}__{class}.gltf", sanitize(object), crate::h2::stage::scale_suffix(scale));
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
                let frame = Frame { scale, ..Frame::IDENTITY };
                prims.entry(m).or_default().add(&section, part, frame, self.shaders[m].base_scale, Some([0.0, 0.0]), None);
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
        assert_eq!(template("one_add_two_plus_two").transparent, 1, "a product of its maps, alpha blended");
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

    /// A tinted copy is named by its tint in hundredths; a plain gain names
    /// nothing. The transparent templates' texture rows give scale and offset.
    #[test]
    fn tinted_copies_and_texture_rows_read_as_the_shaders_have_them() {
        assert_eq!(tint_suffix([1.0; 3]), "");
        assert_eq!(tint_suffix([0.47, 0.47, 0.6]), "__t2f2f3c");
        // Lockout's mountains_clouds layer 2: u x 6, v x 2 offset 1.
        let rows = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [8.0, 0.0, 0.0, 0.0], [0.0, 3.0, 0.0, 0.0], [6.0, 0.0, 0.0, 0.0], [0.0, 2.0, 0.0, 1.0]];
        assert_eq!(two_plus_two_rows(&rows, 2), [6.0, 2.0, 0.0, 1.0]);
        assert_eq!(two_plus_two_rows(&rows, 7), [1.0, 1.0, 0.0, 0.0]);
    }

    /// Halo (x, y, z) is glTF (x, z, -y): a rotation, so winding survives.
    #[test]
    fn the_axis_swap_is_a_rotation() {
        let (x, y, z) = (to_gltf([1.0, 0.0, 0.0]), to_gltf([0.0, 1.0, 0.0]), to_gltf([0.0, 0.0, 1.0]));
        assert_eq!(cross(x, y), z);
    }
}
