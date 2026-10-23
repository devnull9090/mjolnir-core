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

use crate::h2::bitmap::{self, Image};
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
    /// The role whose alpha an alpha-tested template cuts out on.
    pub alpha_from: &'static str,
}

/// A shader template's slot layout, by its name (`tex_bump`, ...).
pub fn template(name: &str) -> Template {
    let t = |slots, tiling, transparent, alpha_tested| Template { slots, tiling, transparent, alpha_tested, alpha_from: "base" };
    const BUMP_FIRST: &[(&str, usize)] = &[("bump", 0), ("base", 1), ("detail", 2), ("detail2", 3)];
    // tex_bump_detail_blend alone keeps its details' constants first (25
    // shaders on the 24 maps, base always constant 2 at (1, 1)); its
    // siblings (_keep, _overlay, _blend_detail, two and three detail) are
    // bump-first like tex_bump, base at constant 1 (Coagulation's ground
    // tiled 60 times when read the other way).
    const DETAIL_FIRST: &[(&str, usize)] = &[("detail", 0), ("detail2", 1), ("base", 2), ("bump", 3)];
    let mut tpl = match name {
        // The single-pass variants' compiled lightmap pass discards where
        // the bump map's alpha rounds to 0 (Zanzibar's palm fronds and
        // beach bushes: solid colour maps, the leaves' outline in the bump
        // map's alpha).
        n if n.starts_with("tex_bump_alpha_test") && n.contains("single_pass") => {
            Template { alpha_from: "bump", ..t(&["bump", "", "base", "detail"], BUMP_FIRST, 0, true) }
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
        // Lit base x detail, plus a glow the plasma pass draws from bitmap
        // 3's channels (`plasma_band`); Zanzibar's fusion coil cores.
        "tex_bump_plasma_one_channel_illum" => t(&["bump", "base", "detail", "plasma"], BUMP_FIRST, 0, false),
        // A neutral grey detail before the base, and a glow map whose three
        // channels its multichannel self-illumination pass tints by pixel
        // constants 4, 6 and 7 (Backwash's blue rectangle lights).
        "tex_bump_illum_3_channel" => t(&["bump", "detail", "base", "self_illum"], BUMP_FIRST, 0, false),
        // Water (Beaver Creek's creek, Coagulation's cave pool): the frame
        // behind (copied and rippled) and the reflection map mixed by a
        // fresnel term, drawn as the reflection blended over the scene,
        // more opaque towards grazing; `water_pool` has a 2D reflection map,
        // `water_pool_cube` a cube.
        n if n.starts_with("water_pool") => t(&["ripple", "env", "", "fresnel"], &[], 1, false),
        // Waterfalls (Sanctuary's): min(1, mask x A + mask x B) x C, alpha
        // (A.a + B.a) x mask.a, each map scrolling, alpha blended.
        "waves" => t(&["mask", "base", "base2", "base3"], &[], 1, false),
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
        // A base, a detail and a glow map (Backwash's fungus: the weeds
        // detail tiled 6 x, vertex constant 2).
        "tex_illum" => t(&["base", "detail", "self_illum"], &[("base", 0), ("self_illum", 1), ("detail", 2)], 0, false),
        "tex_illum_bloom" => t(&["base", "detail", "self_illum"], &[], 0, false),
        // A base and two details blended by its alpha, the details' scales
        // in constants 2 and 3 (Sanctuary's ground: pebbles 24 x 36, weeds
        // 16 x 24).
        "tex_detail_blend" => t(&["base", "detail", "detail2"], &[("base", 0), ("detail", 2), ("detail2", 3)], 0, false),
        // Street Sweeper's road stripes, Headlong's signs: the map alpha
        // blended over the road.
        "decal_simple" => t(&["base"], &[], 1, false),
        // Glass: an environment cube through a specular mask, the base map
        // blended by its alpha, a self-illumination map (the sky dome's
        // layers use the same slots with a black cube).
        n if n.ends_with("one_alpha_env") || n.ends_with("one_alpha_env_clamped") => {
            t(&["env", "mask", "base", "", "self_illum"], &[], 1, false)
        }
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
        // Cloud layers (the sky's cloud cover, Ascension's cloud plane under
        // the island): two maps multiplied, colour and alpha, alpha blended
        // (`clouds_simple_transparent`), each tiled and scrolled as its
        // slot's rows and overlays say.
        n if n.ends_with("two_alpha_clouds") => t(&["base", "mask"], &[], 1, false),
        // The sky's sun shafts: a mask (rgb x its alpha) times a tiled,
        // scrolling detail, tinted, added.
        // The same outside the sky: Gemini's hologram halo (a ring map
        // through scanlines), the light volumes (`one_add_illum_detail`).
        "sky_one_add_illum_detail" | "one_add_illum_detail" | "add_illum_detail" => t(&["mask", "base"], &[], 4, false),
        // A self-illuminated map tinted by pixel constant 0 (the
        // teleporters' glow), added.
        "one_add_illum" => t(&["base"], &[], 4, false),
        // Compiled (`add_clouds_simple_transparent`): min(1, 2 x bitmap 0 x
        // bitmap 1) x the vertex colour x pixel constant 0's alpha, added;
        // bitmap 1 is often default_multiplicative, 50% grey (Tombstone's
        // sky dome, Gemini's sky, the recharge stations' glow).
        n if n.ends_with("two_add_clouds") || n.ends_with("two_add_clouds_clamped") => t(&["base", "mask"], &[], 4, false),
        // Covenant holo panels (Midship, Desolation, Gemini): compiled
        // (`add_detail_masked`) min(1, 2 x the panel map (bitmap 0) x the
        // static (bitmap 1)) + a readout (bitmap 2, 4 x) x the panel's
        // alpha, faded and added as the clouds are. The first term goes in
        // as the clouds' double multiply; the readout is left out.
        "two_add_detail_masked" => t(&["base", "mask"], &[], 4, false),
        // Compiled (`default_transparent_add`): cube(R) x pixel constant 1 x
        // bitmap 1 + bitmap 3 x pixel constant 3 + bitmap 2's, added; the
        // fusion coils' bloom (bitmap 3, a black cube).
        "two_add_env_illum" => t(&["env", "mask", "", "base"], &[], 4, false),
        n if n.contains("add") => t(&["", "base"], &[], 4, false),
        // Compiled: 2 x base x detail x tint (pixel constant 0), drawn
        // dest x src + src x dest (a double multiply, alpha unused) with a
        // depth bias; Zanzibar's Camp Froman sign, the military crates'
        // stencils. On Zanzibar the multiply master draws nothing (it does
        // on Chill Out), so it goes in alpha blended, the multiply baked
        // into the map (`overlay_texel`).
        "overlay" => t(&["base", "detail"], &[("base", 0), ("detail", 1)], 1, false),
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

/// Placeholder bitmaps a template binds when a slot is unused. The default
/// cloud noises are content: the teleporters' plasma bands its offset map
/// against `clouds_256`.
fn is_placeholder(path: &str) -> bool {
    let p = path.to_ascii_lowercase();
    if p.contains(r"default_bitmaps\bitmaps\clouds_") {
        return false;
    }
    p.contains("default_bitmaps") || p.starts_with("rasterizer\\") || p.ends_with("gray_50_percent") || p.ends_with("color_white")
}

/// Staged bitmaps: PNG (and DDS) per (bitm datum in its file, submap,
/// tint), cube maps as six face PNGs.
#[derive(Default)]
struct Textures {
    done: BTreeMap<(usize, u32, u32, String), Option<String>>,
    cubes: BTreeMap<(usize, u32, String), Option<Vec<String>>>,
    names: BTreeMap<String, usize>,
}

/// One submap of a bitmap tag decoded, its mips largest first.
fn decode_bitmap(cache: &Cache, tag: &Tag<'_>, index: u32) -> Result<Vec<Image>, Error> {
    let textures = cache.textures.as_ref().ok_or_else(|| Error::Unsupported("no textures.dat".into()))?;
    let infos = bitmap::infos(tag);
    let info = infos.get(index as usize).ok_or_else(|| Error::Format(format!("no bitmap {index}")))?;
    let data = bitmap::read_entry(textures, info.offset, info.size)?;
    bitmap::decode(info, &data)
}

/// An image's alpha at (u, v) in 0..1, bilinear, wrapping.
fn sample_alpha(img: &Image, u: f32, v: f32) -> u8 {
    let (w, h) = (img.width as i64, img.height as i64);
    let fx = u * w as f32 - 0.5;
    let fy = v * h as f32 - 0.5;
    let (x0, y0) = (fx.floor() as i64, fy.floor() as i64);
    let (tx, ty) = (fx - x0 as f32, fy - y0 as f32);
    let at = |x: i64, y: i64| img.rgba[((y.rem_euclid(h) * w + x.rem_euclid(w)) * 4 + 3) as usize] as f32;
    let top = at(x0, y0) * (1.0 - tx) + at(x0 + 1, y0) * tx;
    let bottom = at(x0, y0 + 1) * (1.0 - tx) + at(x0 + 1, y0 + 1) * tx;
    (top * (1.0 - ty) + bottom * ty).round().clamp(0.0, 255.0) as u8
}

/// The plasma_one_channel_self_illumination pass's band, as compiled: 1
/// where the map's alpha is at `level` (pixel constant 2's alpha), falling
/// to 0 a quarter away, sharpened twice by (2x - 1)^2. The pass adds red x
/// band x pixel constant 5 + green x 3 + blue x 4.
fn plasma_band(a: f32, level: f32) -> f32 {
    let above = a - level + 0.501961;
    let below = -a + level + 0.501961;
    let mut x = if below.round_ties_even() >= 1.0 { above * above } else { below * below } * 4.0;
    for _ in 0..2 {
        let s = x.clamp(0.0, 1.0);
        x = x.round_ties_even() * (2.0 * s - 1.0) * (2.0 * s - 1.0);
    }
    x.clamp(0.0, 1.0)
}

/// How many times to repeat a map across and down so a uniform scale tiles
/// it as (u, v) does: `None` when u and v agree. The smaller scale is the
/// one kept, the ratio rounded and held to 16 a side.
fn repeats(u: f32, v: f32) -> Option<(u32, u32)> {
    if u <= 0.0 || v <= 0.0 || (u - v).abs() <= 1e-3 * u.max(v) {
        return None;
    }
    let s = u.min(v);
    let (nu, nv) = ((u / s).round().clamp(1.0, 16.0) as u32, (v / s).round().clamp(1.0, 16.0) as u32);
    (nu * nv > 1).then_some((nu, nv))
}

/// An image repeated `nu` times across and `nv` times down.
fn tile_image(img: &Image, nu: u32, nv: u32) -> Image {
    let (w, h) = (img.width as usize, img.height as usize);
    let (tw, th) = (w * nu as usize, h * nv as usize);
    let mut rgba = vec![0u8; tw * th * 4];
    for y in 0..th {
        let src = &img.rgba[(y % h) * w * 4..(y % h + 1) * w * 4];
        for k in 0..nu as usize {
            let at = (y * tw + k * w) * 4;
            rgba[at..at + w * 4].copy_from_slice(src);
        }
    }
    Image { width: tw as u32, height: th as u32, rgba }
}

/// A chicago map's transform and slide as M_H2_PlasmaAlpha takes them: (u
/// scale, v scale, u offset, v offset) and (u, v) per second. A slide moves
/// `scale` repeats a `period` from `phase`; `chicago_map` gave the phase's
/// share back to the offset, which is added again here.
fn plasma_map(m: &Value) -> ([f32; 4], [f32; 2]) {
    let f = |k: &str| m.get(k).and_then(Value::as_f64).unwrap_or(0.0) as f32;
    let mut xform = [f("map_u_scale"), f("map_v_scale"), f("map_u_offset"), f("map_v_offset")];
    let mut scroll = [0.0; 2];
    for (k, axis) in ["u", "v"].iter().enumerate() {
        let period = f(&format!("{axis}_animation_period"));
        if m.get(format!("{axis}_animation_function")).and_then(Value::as_i64) == Some(6) && period > 0.0 {
            let repeats = f(&format!("{axis}_animation_scale"));
            scroll[k] = repeats / period;
            xform[2 + k] += repeats * (f(&format!("{axis}_animation_phase")) / period).rem_euclid(1.0);
        }
    }
    (xform, scroll)
}

/// An overlay texel (its colour, 0..1), whose double multiply scales the
/// frame by m = 2 x its luminance, as a colour and alpha to blend over it:
/// black at 1 - m where it darkens (exactly the frame x m), its own hue at
/// full brightness and (m - 1) / 2 where it brightens (the frame's grey
/// unknown); 0.5 grey, which leaves the frame as it is, is clear.
fn overlay_texel(c: [f32; 3]) -> ([f32; 3], f32) {
    multiply_texel(c, 2.0)
}

/// A texel of a map that multiplies the frame by `gain` x its luminance
/// (a multiply decal 1, a double multiply 2), as a colour and alpha to
/// blend over it (`overlay_texel`).
fn multiply_texel(c: [f32; 3], gain: f32) -> ([f32; 3], f32) {
    let m = gain * (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]);
    if m <= 1.0 {
        ([0.0; 3], 1.0 - m)
    } else {
        let top = c[0].max(c[1]).max(c[2]).max(1e-6);
        (c.map(|v| v / top), ((m - 1.0) / 2.0).min(1.0))
    }
}

/// Whether a role was staged.
fn role_is_set(roles: &BTreeMap<&str, Option<String>>, role: &str) -> bool {
    roles.get(role).is_some_and(|r| r.is_some())
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
    /// doubled, keep their plain names, which the bake finds page N by). A
    /// suffix starting `__pm` also multiplies the colour by the map's own
    /// alpha (a shader that draws rgb x a, additive).
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
        let premultiply = suffix.starts_with("__pm");
        self.stage_mapped(cache, tag, index, dir, notes, suffix, suffix, &mut |mips| {
            if gain != [1.0; 3] || premultiply {
                for m in mips {
                    for p in m.rgba.chunks_exact_mut(4) {
                        let a = if premultiply { p[3] as f32 / 255.0 } else { 1.0 };
                        for (c, g) in p[..3].iter_mut().zip(gain) {
                            *c = (*c as f32 * g * a).round().min(255.0) as u8;
                        }
                    }
                }
            }
            Ok(())
        })
    }

    /// As [`Textures::stage`], the decoded mips (largest first) rewritten by
    /// `edit` and the file named with `suffix`; `key` tells apart copies
    /// whose edits differ under one name.
    #[allow(clippy::too_many_arguments)]
    fn stage_mapped(
        &mut self,
        cache: &Cache,
        tag: &Tag<'_>,
        index: u32,
        dir: &Path,
        notes: &mut Vec<String>,
        suffix: &str,
        key: &str,
        edit: &mut dyn FnMut(&mut Vec<Image>) -> Result<(), Error>,
    ) -> Option<String> {
        let key = (tag.file as *const CacheFile as usize, tag.entry.datum, index, key.to_string());
        if let Some(done) = self.done.get(&key) {
            return done.clone();
        }
        let result = (|| -> Result<String, Error> {
            let mut mips = decode_bitmap(cache, tag, index)?;
            edit(&mut mips)?;
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

    /// Stage `base` with its alpha replaced by `alpha`'s (resampled to each
    /// mip), as `<stem>__cut.png`: the cut-out an alpha-tested template
    /// reads from another map.
    fn stage_cutout(&mut self, cache: &Cache, base: &Tag<'_>, alpha: &Tag<'_>, dir: &Path, notes: &mut Vec<String>) -> Option<String> {
        let key = format!("__cut{:x}_{:x}", alpha.file as *const CacheFile as usize, alpha.entry.datum);
        self.stage_mapped(cache, base, 0, dir, notes, "__cut", &key, &mut |mips| {
            let a = decode_bitmap(cache, alpha, 0)?.into_iter().next().ok_or_else(|| Error::Format("no image".into()))?;
            // A base smaller than the cut-out (a placeholder colour) is
            // taken to the cut-out's size first, as one level.
            if let Some(m0) = mips.first() {
                if (m0.width as u64) * (m0.height as u64) < (a.width as u64) * (a.height as u64) {
                    let mut rgba = Vec::with_capacity((a.width * a.height * 4) as usize);
                    for y in 0..a.height {
                        for x in 0..a.width {
                            let (sx, sy) = (x * m0.width / a.width, y * m0.height / a.height);
                            let at = ((sy * m0.width + sx) * 4) as usize;
                            rgba.extend_from_slice(&m0.rgba[at..at + 4]);
                        }
                    }
                    *mips = vec![Image { width: a.width, height: a.height, rgba }];
                }
            }
            for m in mips.iter_mut() {
                for y in 0..m.height {
                    for x in 0..m.width {
                        let u = (x as f32 + 0.5) / m.width as f32;
                        let v = (y as f32 + 0.5) / m.height as f32;
                        m.rgba[((y * m.width + x) * 4 + 3) as usize] = sample_alpha(&a, u, v);
                    }
                }
            }
            Ok(())
        })
    }

    /// Stage a plasma map as a CE self-illumination map, `<stem>__glow.png`:
    /// the three channels CE tints by its primary, secondary and plasma
    /// colours hold Halo 2's green, blue and red x `plasma_band` at `level`.
    fn stage_glow(&mut self, cache: &Cache, tag: &Tag<'_>, dir: &Path, notes: &mut Vec<String>, level: f32) -> Option<String> {
        let key = format!("__glow{level}");
        self.stage_mapped(cache, tag, 0, dir, notes, "__glow", &key, &mut |mips| {
            for m in mips.iter_mut() {
                for p in m.rgba.chunks_exact_mut(4) {
                    let band = plasma_band(p[3] as f32 / 255.0, level);
                    p.copy_from_slice(&[p[1], p[2], (p[0] as f32 * band).round() as u8, 255]);
                }
            }
            Ok(())
        })
    }

    /// Stage a cube map's six faces as `<stem>__face<k>.png` in D3D order
    /// (what tools/level/ce_material_spec.py's `cube()` assembles into a
    /// TextureCube), each channel scaled by `gain` (a tinted copy is
    /// `<stem>__t<rrggbb>__face<k>.png`); the six names, or `None` with a
    /// note.
    fn stage_cube(&mut self, cache: &Cache, tag: &Tag<'_>, dir: &Path, notes: &mut Vec<String>, gain: [f32; 3]) -> Option<Vec<String>> {
        let suffix = tint_suffix(gain);
        let key = (tag.file as *const CacheFile as usize, tag.entry.datum, suffix.clone());
        if let Some(done) = self.cubes.get(&key) {
            return done.clone();
        }
        let result = (|| -> Result<Vec<String>, Error> {
            let textures = cache.textures.as_ref().ok_or_else(|| Error::Unsupported("no textures.dat".into()))?;
            let infos = bitmap::infos(tag);
            let info = infos.first().ok_or_else(|| Error::Format("no bitmap".into()))?;
            let data = bitmap::read_entry(textures, info.offset, info.size)?;
            let mut faces = bitmap::decode_cube(info, &data)?;
            for face in &mut faces {
                for px in face.rgba.chunks_exact_mut(4) {
                    for (c, g) in px[..3].iter_mut().zip(gain) {
                        *c = (*c as f32 * g).round().min(255.0) as u8;
                    }
                }
            }
            let stem = format!("{}{suffix}", sanitize(tag.name()));
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
    /// False for a template that draws no colour (`water_edge_blend`
    /// writes only the frame's alpha, a mask the water fades by): its
    /// geometry is left out.
    drawn: bool,
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
            drawn: true,
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
            // A placeholder is left out, except the base of a template that
            // cuts out on another map's alpha: Backwash's canopy is
            // color_black with the leaves' outline in its bump map.
            if is_placeholder(t.name()) && !(role == "base" && tpl.alpha_tested && tpl.alpha_from != "base") {
                continue;
            }
            if role == "env" {
                // A 2D reflection map (water_pool's) stands in on every face.
                cube_faces = if bitmap::infos(&t).first().map(|i| i.kind) == Some(2) {
                    tex.stage_cube(cache, &t, dir, notes, [1.0; 3])
                } else {
                    tex.stage(cache, &t, b.u32(4).max(0), dir, notes).map(|png| vec![png; 6])
                };
                continue;
            }
            if role == "plasma" {
                tags.insert(role, t);
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
    if tpl.alpha_tested && tpl.alpha_from != "base" {
        if let (Some(b), Some(a)) = (tags.get("base"), tags.get(tpl.alpha_from)) {
            let cut = tex.stage_cutout(cache, b, a, dir, notes);
            roles.insert("base", cut);
        }
    }
    // The plasma pass's colours as CE's three self-illumination channels
    // (`Textures::stage_glow`): pixel constants 3 and 4 always on, 5 the
    // band's, baked into the map, so CE's plasma ridge is left dark.
    let mut glow_channels = Value::Null;
    if template_name == "tex_bump_illum_3_channel" && role_is_set(&roles, "self_illum") {
        let c = |i: usize| pixel.get(i).map(|c| vec![c[0], c[1], c[2]]).unwrap_or(vec![0.0; 3]);
        glow_channels = json!([{"on": c(4)}, {"on": c(6)}, {"on": [0.0, 0.0, 0.0], "off": c(7)}]);
    }
    if let Some(t) = tags.get("plasma") {
        let c = |i: usize| pixel.get(i).map(|c| vec![c[0], c[1], c[2]]).unwrap_or(vec![0.0; 3]);
        let glow = tex.stage_glow(cache, t, dir, notes, pixel.get(2).map(|c| c[3]).unwrap_or(0.0));
        roles.insert("self_illum", glow);
        glow_channels = json!([{"on": c(3)}, {"on": c(4)}, {"on": [0.0, 0.0, 0.0], "off": c(5)}]);
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
        let stem = root.tagref(0x00).and_then(|r| cache.follow(r));
        let slots = template_slots(stem.as_ref());
        let transforms = bitmap_transforms(&slots, &constants);
        let scroll = slot_scroll(post, &slots);
        // A map by the shader bitmap its role is (the template's slot order).
        let bitmap_of = |r: &str| tpl.slots.iter().position(|s| *s == r).unwrap_or(0);
        let map = |file: Option<String>, b: usize, function: i64| chicago_map(file, b, function, &transforms, &scroll);
        // plasma_alpha's own drawing (M_H2_PlasmaAlpha), beside the chicago
        // approximation the CE masters can draw.
        let mut plasma: Option<Value> = None;
        // The vertex colour's alpha runs from a glancing alpha to a facing
        // one by N.V (the sun shafts' constants 7.w and 6.w, the holo
        // template's 11.w and 10.w): where the facing one is higher, a
        // volume seen edge-on vanishes. CE's chicago fades the same way
        // (`framebuffer_fade_mode` 2, |N.V|). Desolation's light shafts
        // were solid white slabs without it.
        let fades = |facing: usize, glancing: usize| {
            let a = |i: usize| constants.get(i).map(|c| c[3]).unwrap_or(0.0);
            constants.len() > facing.max(glancing) && a(facing) > a(glancing)
        };
        let mut fade_mode = 0;
        let (maps, base, two_sided) = if template_name.contains("two_plus_two") {
            // mask * A * B, alpha the product of theirs (the compiled shader
            // multiplies all three, whatever the name says), two-sided.
            let maps = vec![map(role("mask"), bitmap_of("mask"), 2), map(role("base"), bitmap_of("base"), 2),
                            map(role("base2"), bitmap_of("base2"), 0)];
            (maps, base, true)
        } else if template_name.ends_with("two_alpha_clouds") {
            // Compiled: bitmap 0 x bitmap 1, rgba; source alpha blend,
            // two-sided.
            let maps = vec![map(role("mask"), bitmap_of("mask"), 2), map(role("base"), bitmap_of("base"), 0)];
            (maps, role("base"), true)
        } else if template_name.ends_with("two_add_clouds")
            || template_name.ends_with("two_add_clouds_clamped")
            || template_name == "two_add_detail_masked"
        {
            // 2 x base x mask as CE's double multiply, or the base alone
            // where the mask is default_multiplicative (2 x 50% grey). Pixel
            // constant 0's alpha fades it: 0 (Colossus's and Triplicate's
            // lightning, which flashes by an animation the conversion doesn't
            // carry) draws nothing.
            let fade = pixel.get(0).map(|c| c[3]).unwrap_or(1.0);
            let maps = match (role("base"), role("mask")) {
                (_, _) if fade == 0.0 => vec![],
                (Some(b), Some(m)) => vec![map(Some(b), bitmap_of("base"), 3), map(Some(m), bitmap_of("mask"), 0)],
                (b, _) => vec![map(b, bitmap_of("base"), 0)],
            };
            let base = if fade == 0.0 { None } else { role("base") };
            if template_name == "two_add_detail_masked" && fades(10, 11) {
                fade_mode = 2;
            }
            (maps, base, true)
        } else if ["sky_one_add_illum_detail", "one_add_illum_detail", "add_illum_detail"].contains(&template_name.as_str()) {
            // Compiled: 2 x tint (pixel constant 0) x vertex colour x mask.rgb
            // x mask.a x detail.rgb, added. The vertex colour fades from the
            // facing colour (vertex constant 4, alpha 6.w) to the glancing
            // one (5, 7.w) as (N.V)^2 when the glancing alpha is 0: the
            // facing colour goes in, its alpha as the chicago fade (`fades`).
            // Mask: bitmap 0, rows 0-1; detail: bitmap 1, rows 2-3.
            let tint = rgb(pixel.get(0));
            // `add_illum_detail` has no view-dependent colour: its five
            // constants are the two maps' transforms.
            // The facing colour's alpha (6.w) scales it too: 1 on the sun
            // shafts, 0.15 on Gemini's white volumes.
            let (facing, alpha) = if constants.len() >= 8 {
                (rgb(constants.get(4)), constants.get(6).map(|c| c[3]).unwrap_or(1.0))
            } else {
                ([1.0; 3], 1.0)
            };
            let gain: [f32; 3] = std::array::from_fn(|k| 2.0 * tint[k] * facing[k] * alpha);
            let mask = tags
                .get("mask")
                .and_then(|t| tex.stage_with(cache, t, 0, dir, notes, gain, &format!("__pm{}", tint_suffix(gain))));
            let maps = vec![map(mask.clone(), bitmap_of("mask"), 2), map(role("base"), bitmap_of("base"), 0)];
            if fades(6, 7) {
                fade_mode = 2;
            }
            (maps, mask, true)
        } else if template_name == "waves" {
            // (A + B) x mask x C as CE's chain: each map's function folds
            // in the next; the last keeps the alpha.
            let mut mask = map(role("mask"), bitmap_of("mask"), 2);
            mask["alpha_function"] = json!(0);
            let maps = vec![map(role("base"), bitmap_of("base"), 4), map(role("base2"), bitmap_of("base2"), 2), mask,
                            map(role("base3"), bitmap_of("base3"), 0)];
            (maps, role("base"), true)
        } else if template_name.starts_with("water_pool") {
            // The reflection as CE's first-map cube along the reflected eye
            // vector, alpha blended and faded towards the normal
            // (`framebuffer_fade_mode` 1) as the fresnel term does.
            let maps = vec![json!({"map": {"file": Value::Null, "faces": cube_faces.clone()},
                                   "color_function": 0, "alpha_function": 0,
                                   "map_u_scale": 1.0, "map_v_scale": 1.0})];
            (maps, None, true)
        } else if template_name == "plasma_alpha" {
            // noise A * noise B * the mask's alpha, added to the frame, in
            // the colour the compiled shader's bands average to
            // (`plasma_tint`), baked into noise A.
            // The shader samples noise A's blue and noise B's red.
            let hist = |r: &str, channel: usize| tags.get(r).and_then(|t| histogram(cache, t, channel));
            let tint = plasma_tint(&pixel, hist("noise_a", 2).as_ref(), hist("noise_b", 0).as_ref());
            let a = tags.get("noise_a").and_then(|t| tex.stage_with(cache, t, 0, dir, notes, tint, &tint_suffix(tint)));
            let mut noise_b = map(role("noise_b"), bitmap_of("noise_b"), 2);
            noise_b["flags"] = json!(2);
            let maps = vec![map(a.clone(), bitmap_of("noise_a"), 2), noise_b, map(role("mask"), bitmap_of("mask"), 0)];
            // The compiled shader as it is (docs/h2_cache_format.md): the
            // raw maps with their transforms and scrolls, pixel constants 0,
            // 1 and 3 and 2's alpha.
            let pm = |r: &str| {
                let (xform, scroll) = plasma_map(&map(role(r), bitmap_of(r), 0));
                json!({"file": role(r), "xform": xform, "scroll": scroll})
            };
            let c = |i: usize| pixel.get(i).map(|c| [c[0], c[1], c[2]]).unwrap_or([0.0; 3]);
            plasma = Some(json!({
                "noise_a": pm("noise_a"), "noise_b": pm("noise_b"), "mask": pm("mask"),
                "color0": c(0), "color1": c(1), "color3": c(3), "fade": pixel.get(2).map(|c| c[3]).unwrap_or(0.0),
            }));
            (maps, a, true)
        } else {
            // The sky's layers: the base, tinted by the albedo tint (pixel
            // constant 1), blended by its alpha. one_add_illum's compiled
            // shader: base.rgb x pixel constant 0 x the vertex colour, added;
            // overlay's: the base x its tint (pixel constant 0), double
            // multiplied.
            let tint_at = match template_name.as_str() {
                "one_add_illum" | "overlay" => 0,
                "two_add_env_illum" => 3,
                _ => 1,
            };
            let tinted = match (tags.get("base"), pixel.get(tint_at)) {
                (Some(t), c) if template_name == "overlay" => {
                    let tint = c.map(|c| [c[0], c[1], c[2]]).unwrap_or([1.0; 3]);
                    let key = format!("__overlay{}", tint_suffix(tint));
                    tex.stage_mapped(cache, t, 0, dir, notes, "__overlay", &key, &mut |mips| {
                        for m in mips.iter_mut() {
                            for p in m.rgba.chunks_exact_mut(4) {
                                let texel = std::array::from_fn(|k| p[k] as f32 / 255.0 * tint[k]);
                                let (c, a) = overlay_texel(texel);
                                p.copy_from_slice(&[(c[0] * 255.0).round() as u8, (c[1] * 255.0).round() as u8,
                                                    (c[2] * 255.0).round() as u8, (a * 255.0).round() as u8]);
                            }
                        }
                        Ok(())
                    })
                }
                (Some(t), Some(c)) if [c[0], c[1], c[2]] != [1.0; 3] => tex.stage_with(cache, t, 0, dir, notes, [c[0], c[1], c[2]], &tint_suffix([c[0], c[1], c[2]])),
                _ => base,
            };
            (vec![json!({"map": {"file": tinted}, "color_function": 0, "alpha_function": 0,
                         "map_u_scale": base_scale[0], "map_v_scale": base_scale[1]})], tinted, true)
        };
        let flags = if two_sided { 4 } else { 0 };
        // Unfogged: these templates' compiled shaders have no fog term and
        // their stems no fog pass (Ascension's cloud plane draws over the
        // planar fog, not in it); tools/level/ce_material_spec.py leaves
        // their fog out.
        let mut s = json!({
            "tag_path": shader.name(), "shader_class": "schi", "h2_template": template_name,
            "shader_flags": flags, "framebuffer_blend_function": blend, "base_map": base, "fogged": false,
            "tag": {"flags": flags, "framebuffer_blend_function": blend, "maps": maps},
        });
        if let Some(p) = plasma {
            s["h2_plasma"] = p;
        }
        if fade_mode > 0 {
            s["tag"]["framebuffer_fade_mode"] = json!(fade_mode);
        }
        if template_name.starts_with("water_pool") {
            s["tag"]["first_map_type"] = json!(1);
            s["tag"]["framebuffer_fade_mode"] = json!(1);
            s["fogged"] = json!(true);
        }
        ("schi", "BLEND", two_sided, base, s)
    } else {
        let detail2 = role("detail2");
        // A second detail blends over the first by the base map's alpha,
        // CE's "blended" environment type, which draws its primary detail
        // where the alpha is high. Halo 2 draws its second detail there
        // (Lockout's snow is where composite_block_snow's alpha is high), so
        // the second detail goes in as the primary.
        // Each map at its tiling relative to the base, which is in UV0. CE
        // takes one scale per map, Halo 2 a u and a v scale (the palm bark's
        // detail and bump 2 x 12, the beach's detail 128 x 64): a map tiled
        // unevenly goes in as a copy repeated to the ratio (`repeats`), at
        // the smaller scale. Read as u alone, the palm's detail was
        // stretched six times along the trunk.
        let mut tiled = |r: &str| -> (Option<String>, f32) {
            let s = scale(r);
            let (ru, rv) = (s[0] / base_scale[0], s[1] / base_scale[1]);
            match (tags.get(r), repeats(ru, rv)) {
                (Some(t), Some((nu, nv))) => {
                    let suffix = format!("__x{nu}y{nv}");
                    let file = tex.stage_mapped(cache, t, 0, dir, notes, &suffix, &suffix, &mut |mips| {
                        for m in mips.iter_mut() {
                            *m = tile_image(m, nu, nv);
                        }
                        Ok(())
                    });
                    (file, ru / nu as f32)
                }
                _ => (role(r), ru),
            }
        };
        let (detail, detail_scale) = tiled("detail");
        let (bump, bump_scale) = tiled("bump");
        let ((primary, primary_scale), (secondary, secondary_scale)) = match detail2 {
            Some(_) => (tiled("detail2"), (detail, detail_scale)),
            None => ((detail, detail_scale), (None, 1.0)),
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
            "bump": {"map": bump, "scale": bump_scale},
            "self_illum": {"map": role("self_illum"), "map_scale": 1.0, "on_color": [1.0, 1.0, 1.0], "channels": glow_channels},
            "specular": {"flags": 0, "brightness": 0.0},
        });
        let mut s = s;
        if template_name.contains("env") {
            if let Some(r) = env_reflection(cache, &shader, post, &pixel, dir, tex, notes) {
                s["reflection"] = r;
            }
        }
        ("shad", if tpl.alpha_tested { "MASK" } else { "OPAQUE" }, false, base, s)
    };
    // water_edge_blend's compiled pass writes its map's alpha with colour
    // writes masked to alpha (D3DRS_COLORWRITEENABLE 0x8): Zanzibar's flat
    // plane at sea level fading the infinite water, drawn white without it.
    let drawn = template_name != "water_edge_blend";
    Shader { key, class, alpha_mode, double_sided, base, base_scale, unlit, drawn, summary }
}

/// A bitmap's first image's values in one channel, as a histogram of 64
/// bins (each the share of its texels), or `None` when it cannot be read.
fn histogram(cache: &Cache, tag: &Tag<'_>, channel: usize) -> Option<[f32; 64]> {
    let info = bitmap::infos(tag).into_iter().next()?;
    let data = bitmap::read_entry(cache.textures.as_ref()?, info.offset, info.size).ok()?;
    let image = bitmap::decode(&info, &data).ok()?.into_iter().next()?;
    let mut h = [0f32; 64];
    for p in image.rgba.chunks_exact(4) {
        h[p[channel] as usize / 4] += 1.0;
    }
    let n: f32 = h.iter().sum();
    (n > 0.0).then(|| h.map(|x| x / n))
}

/// The colour plasma_alpha's compiled shader averages to, over the product
/// of its two noise samples that stands in for it here (CE's chicago masters
/// cannot band). The shader takes noise A's blue and noise B's red, and
/// from v = 4 (0.502 - |a - b|)^2 three nested bands: p1 = round(v)
/// (2v - 1)^2, p2 the same of p1, p3 of p2; colour = sat(lerp(pixel 1,
/// pixel 0, p1) x v + p3 x pixel 3) (pixel constants 0-3 sit in registers
/// 2-5 by the template's remapping table; pixel 2 holds only the facing
/// fade in its alpha). Averaged over the two maps' own values (`a`, `b`:
/// histograms; uniform without them), each sampled apart, and divided by
/// the product's mean: the teleporters' beam is green at its edges and cyan
/// where the noises meet, green on the whole, as MCC draws it.
fn plasma_tint(pixel: &[[f32; 4]], a: Option<&[f32; 64]>, b: Option<&[f32; 64]>) -> [f32; 3] {
    let colour = |k: usize| pixel.get(k).map(|c| [c[0], c[1], c[2]]).unwrap_or([0.0; 3]);
    let (hot, mid, outer) = (colour(3), colour(0), colour(1));
    let band = |x: f32| x.round() * (2.0 * x.clamp(0.0, 1.0) - 1.0).powi(2);
    const UNIFORM: [f32; 64] = [1.0 / 64.0; 64];
    let (a, b) = (a.unwrap_or(&UNIFORM), b.unwrap_or(&UNIFORM));
    let value = |i: usize| (i as f32 + 0.5) / 64.0;
    let (mut sum, mut product) = ([0.0f32; 3], 0.0f32);
    for (i, &wa) in a.iter().enumerate() {
        for (j, &wb) in b.iter().enumerate() {
            let w = wa * wb;
            if w == 0.0 {
                continue;
            }
            let d = 0.501_961 - (value(i) - value(j)).abs();
            let v = 4.0 * d * d;
            let p1 = band(v);
            let p3 = band(band(p1)).clamp(0.0, 1.0);
            let p1 = p1.clamp(0.0, 1.0);
            for c in 0..3 {
                let m = (outer[c] + (mid[c] - outer[c]) * p1).clamp(0.0, 1.0);
                sum[c] += w * (m * v.min(1.0) + p3 * hot[c]).clamp(0.0, 1.0);
            }
            product += w * value(i) * value(j);
        }
    }
    sum.map(|s| s / product.max(1e-3))
}

/// An opaque `env` template's reflection (the tex_bump_env family's
/// lightmap pass, read back from its compiled shader): the cube map along
/// the reflected eye vector, times a colour and a brightness each between
/// the glancing and the facing value by N.V, masked by the albedo's alpha
/// (base x detail) and the light level, added to the lit albedo. The cube is
/// whichever of the shader's bitmaps is one (its slot differs by template);
/// the colours and brightnesses are the two pixel constants before the
/// first pair holding only alpha (facing then glancing colour; facing then
/// glancing brightness in that pair's alpha), which every env template has.
///
/// As CE's environment reflection (tools/level/ce_material_spec.py): its
/// tint mixes the cube toward its own eighth power, so the colour goes into
/// a tinted copy of the cube (the mean of the two colours over its
/// luminance) and the brightnesses carry the luminance; the reflection
/// dims with the lightmap as Halo 2's does. `None` without a cube, or when
/// it is the template's black placeholder or both brightnesses are 0.
fn env_reflection(
    cache: &Cache,
    shader: &Tag<'_>,
    post: Option<Struct<'_>>,
    pixel: &[[f32; 4]],
    dir: &Path,
    tex: &mut Textures,
    notes: &mut Vec<String>,
) -> Option<Value> {
    let p = post?;
    let cube = p.block(0x04, 0x0C).iter().find_map(|b| {
        let t = cache.tag(shader.file, b.u32(0))?;
        let cube = bitmap::infos(&t).first().is_some_and(|i| i.kind == 2);
        (cube && !is_placeholder(t.name())).then_some(t)
    })?;
    let (facing, glancing, b_facing, b_glancing) = env_constants(pixel)?;
    let lum = |c: [f32; 4]| 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    let mean = [(facing[0] + glancing[0]) / 2.0, (facing[1] + glancing[1]) / 2.0, (facing[2] + glancing[2]) / 2.0, 0.0];
    let hue = match lum(mean) {
        l if l > 1e-3 => [mean[0] / l, mean[1] / l, mean[2] / l],
        _ => return None,
    };
    let peak = hue.iter().fold(1.0f32, |a, &b| a.max(b));
    let gain = [hue[0] / peak, hue[1] / peak, hue[2] / peak];
    let faces = tex.stage_cube(cache, &cube, dir, notes, gain)?;
    let (perp, para) = (b_facing * lum(facing) * peak, b_glancing * lum(glancing) * peak);
    (perp > 0.0 || para > 0.0).then(|| {
        json!({
            "cube_map": faces, "type": 1,
            "perp_brightness": perp, "para_brightness": para,
            "lightmap_brightness_scale": 0.0,
        })
    })
}

/// An env template's reflection constants among its pixel constants:
/// (facing colour, glancing colour, facing brightness, glancing
/// brightness), the two colours before the first pair holding only alpha.
fn env_constants(pixel: &[[f32; 4]]) -> Option<([f32; 4], [f32; 4], f32, f32)> {
    let alpha_only = |c: &[f32; 4]| c[0] == 0.0 && c[1] == 0.0 && c[2] == 0.0 && c[3] > 0.0;
    let k = (2..pixel.len().saturating_sub(1)).find(|&k| alpha_only(&pixel[k]) && alpha_only(&pixel[k + 1]))?;
    Some((pixel[k - 2], pixel[k - 1], pixel[k][3], pixel[k + 1][3]))
}

/// A map's scrolling, per axis: (period in seconds, repeats per period,
/// phase in seconds).
type Scroll = [Option<(f32, f32, f32)>; 2];

/// A shader overlay's motion as a slide: (period, repeats per period,
/// phase), or `None` for one that does not slide. The engine's evaluator
/// (halo2.dll 0x959cd0, 0x7774c0, 0x7787a0) takes x = time / period,
/// wrapped to 0..1 for every type but periodic, and a value lo + (hi - lo)
/// x clamp01(f), lo and hi the floats at +4 and +8, with f by the type at
/// byte 0: 0 identity, f = x; 1 constant, f = 0; 2 transition, f =
/// lerp(+0x14, +0x18, g(x)) with g the curve at byte 2 (0: g = x; the rest
/// tables); 3 periodic, f = lerp(+0x1C, +0x20, P(x +0x14 + +0x18)) with P
/// the wave at byte 2 (6, slide: frac; the rest tables); 4 linear, f = x
/// +0x24 + +0x28 (Ascension's sun shafts and grav beam run at slope -1).
fn overlay_motion(period: f32, f: &[u8]) -> Option<(f32, f32, f32)> {
    let v = |k: usize| f.get(k..k + 4).map(|b| f32::from_le_bytes(b.try_into().unwrap()));
    if period <= 0.0 {
        return None;
    }
    let span = v(8)? - v(4)?;
    let (period, f0, f1, phase) = match (f.first()?, f.get(2).copied().unwrap_or(0)) {
        (0, _) => (period, 0.0, 1.0, 0.0),
        (2, 0) => (period, v(0x14)?, v(0x18)?, 0.0),
        (3, 6) => {
            let (freq, phase) = (v(0x14)?, v(0x18)?);
            if freq <= 0.0 {
                return None;
            }
            (period / freq, v(0x1C)?, v(0x20)?, phase * period / freq)
        }
        (4, _) => {
            let (slope, at0) = (v(0x24)?, v(0x28)?);
            (period, at0, at0 + slope, 0.0)
        }
        _ => return None,
    };
    // The evaluator clamps f to 0..1: a ramp that leaves it stops sliding.
    if !(0.0..=1.0).contains(&f0) || !(0.0..=1.0).contains(&f1) {
        return None;
    }
    let repeats = span * (f1 - f0);
    (repeats != 0.0).then_some((period, repeats, phase))
}

/// A template's texture slots: which shader bitmap each takes, and which
/// vertex constants hold its two affine rows. From its remapping table
/// (stem +0x58, +0x20; 4 bytes: u16 destination, u8, u8 source): a
/// destination below 8 is a texture slot taking source bitmap; any other is
/// a constant descriptor, whose bits 5-9 are its mask (14 the 2D affine row
/// 1, 15 row 2) and bits 10-12 its texture slot (halo2.dll's constant
/// writer, 0x959380). The first entry per slot and row is taken (the
/// table repeats them per implementation).
struct Slots {
    bitmap: BTreeMap<usize, usize>,
    rows: BTreeMap<(usize, u16), usize>,
}

fn template_slots(stem: Option<&Tag<'_>>) -> Slots {
    let mut out = Slots { bitmap: BTreeMap::new(), rows: BTreeMap::new() };
    let Some(table) = stem.and_then(|t| t.root.block(0x58, 0x28).get(0)).map(|d| d.block(0x20, 4)) else { return out };
    for e in table.iter() {
        let (d, source) = (e.u16(0), e.u8(3) as usize);
        if d < 8 {
            out.bitmap.entry(d as usize).or_insert(source);
        } else if matches!((d >> 5) & 0x1F, 14 | 15) {
            out.rows.entry((((d >> 10) & 7) as usize, (d >> 5) & 0x1F)).or_insert(source);
        }
    }
    out
}

/// Each shader bitmap's texture transform, `[u scale, v scale, u offset,
/// v offset]`, from its slot's rows (u' = a u + b v + d, row 1 for u,
/// row 2 for v; the engine writes the scale, rotation about (0.5, 0.5) and
/// translation there). The rows' cross terms (a rotation) are left out.
fn bitmap_transforms(slots: &Slots, constants: &[[f32; 4]]) -> BTreeMap<usize, [f32; 4]> {
    let mut out = BTreeMap::new();
    for (&slot, &bitmap) in &slots.bitmap {
        let row = |mask: u16, default: [f32; 4]| {
            slots.rows.get(&(slot, mask)).and_then(|&k| constants.get(k)).copied().unwrap_or(default)
        };
        let (u, v) = (row(14, [1.0, 0.0, 0.0, 0.0]), row(15, [0.0, 1.0, 0.0, 0.0]));
        out.insert(bitmap, [if u[0] == 0.0 { 1.0 } else { u[0] }, if v[1] == 0.0 { 1.0 } else { v[1] }, u[3], v[3]]);
    }
    out
}

/// A transparent shader's animated texture translations, by shader bitmap,
/// from its postprocess definition: animated parameter refs (+0x54, 4
/// bytes: u16 descriptor, u8, i8 parameter; a descriptor below 8 is a
/// texture slot), animated parameters (+0x4C, u16: count in the top 7
/// bits, first in the low 9, a range of overlay refs), overlay refs (+0x44:
/// i16 overlay, i16 transform type; 4 translation u, 5 translation v) and
/// overlays (+0x3C, 0x14 bytes: f32 period at 8, the function at 0xC as
/// {size, address}; `overlay_motion`). The slot names its bitmap through
/// the template's remapping table (`template_slots`). The engine adds the
/// translation (d = +value: halo2.dll 0x959380), as CE's masters add their
/// animation.
fn slot_scroll(post: Option<Struct<'_>>, slots: &Slots) -> BTreeMap<usize, Scroll> {
    let mut out: BTreeMap<usize, Scroll> = BTreeMap::new();
    let Some(p) = post else { return out };
    let overlays: Vec<Option<(f32, f32, f32)>> = p
        .block(0x3C, 0x14)
        .iter()
        .map(|o| {
            let at = p.file.offset(o.u32(0x10))?;
            let f = p.file.data.get(at..at + (o.u32(0x0C) as usize).min(64))?;
            overlay_motion(o.f32(8), f)
        })
        .collect();
    let refs: Vec<(i16, i16)> = p.block(0x44, 4).iter().map(|r| (r.i16(0), r.i16(2))).collect();
    let params: Vec<(usize, usize)> = p.block(0x4C, 2).iter().map(|r| ((r.u16(0) & 0x1FF) as usize, (r.u16(0) >> 9) as usize)).collect();
    for r in p.block(0x54, 4).iter() {
        let (descriptor, param) = (r.u16(0), r.i16(3) as i8);
        if descriptor >= 8 || param < 0 {
            continue;
        }
        let Some(&(first, count)) = params.get(param as usize) else { continue };
        let bitmap = slots.bitmap.get(&(descriptor as usize)).copied().unwrap_or(descriptor as usize);
        let slot = out.entry(bitmap).or_default();
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

/// A chicago map for shader bitmap `bitmap`: its file, its transform
/// (`bitmap_transforms`) and scroll as CE's slide (function 6: `scale`
/// repeats every `period` seconds from `phase`), with the colour and alpha
/// function. The tag's rows hold the translation at t = 0, which a phased
/// slide also adds at t = 0: the offset gives that share back.
fn chicago_map(
    file: Option<String>,
    bitmap: usize,
    function: i64,
    transforms: &BTreeMap<usize, [f32; 4]>,
    scroll: &BTreeMap<usize, Scroll>,
) -> Value {
    let mut x = transforms.get(&bitmap).copied().unwrap_or([1.0, 1.0, 0.0, 0.0]);
    let mut m = json!({"map": {"file": file}, "color_function": function, "alpha_function": function});
    if let Some(sc) = scroll.get(&bitmap) {
        for (k, (axis, motion)) in ["u", "v"].iter().zip(sc).enumerate() {
            if let Some((period, repeats, phase)) = motion {
                m[format!("{axis}_animation_function")] = json!(6);
                m[format!("{axis}_animation_period")] = json!(period);
                m[format!("{axis}_animation_phase")] = json!(phase);
                m[format!("{axis}_animation_scale")] = json!(repeats);
                x[2 + k] -= repeats * (phase / period).rem_euclid(1.0);
            }
        }
    }
    m["map_u_scale"] = json!(x[0]);
    m["map_v_scale"] = json!(x[1]);
    m["map_u_offset"] = json!(x[2]);
    m["map_v_offset"] = json!(x[3]);
    m
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
                if !shaders[s].drawn {
                    continue;
                }
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
                if !self.shaders[m].drawn {
                    continue;
                }
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
    /// Stage a bitmap tag's first image for the placement (a decal's): its
    /// PNG's file name and size.
    pub fn stage_bitmap(&mut self, tag: &Tag<'c>) -> Option<(String, u32, u32)> {
        self.stage_decal(tag, 1)
    }

    /// Stage a decal's bitmap for its layer (`deca` +0x04): a multiply (3)
    /// or double multiply (2) decal with the multiply baked for alpha
    /// blending (`multiply_texel`, times the bitmap's own alpha), as
    /// `<stem>__mul<gain>.png`, since multiply blends draw nothing on
    /// these maps; the rest as they are. Its PNG's name and size.
    pub fn stage_decal(&mut self, tag: &Tag<'c>, layer: u16) -> Option<(String, u32, u32)> {
        let info = bitmap::infos(tag).into_iter().next()?;
        let gain = match layer {
            2 => 2.0,
            3 => 1.0,
            _ => 0.0,
        };
        let png = if gain > 0.0 {
            let suffix = format!("__mul{gain:.0}");
            self.tex.stage_mapped(self.cache, tag, 0, &self.dir, &mut self.notes, &suffix, &suffix, &mut |mips| {
                for m in mips.iter_mut() {
                    for p in m.rgba.chunks_exact_mut(4) {
                        let (c, a) = multiply_texel([p[0] as f32 / 255.0, p[1] as f32 / 255.0, p[2] as f32 / 255.0], gain);
                        let a = a * p[3] as f32 / 255.0;
                        p.copy_from_slice(&[(c[0] * 255.0).round() as u8, (c[1] * 255.0).round() as u8,
                                            (c[2] * 255.0).round() as u8, (a * 255.0).round() as u8]);
                    }
                }
                Ok(())
            })?
        } else {
            self.tex.stage(self.cache, tag, 0, &self.dir, &mut self.notes)?
        };
        Some((png, info.width, info.height))
    }

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
        // Ascension's sky: the cloud cover's cloud map is bitmap 0 and its
        // mask bitmap 1; the sun shafts' mask is bitmap 0, added.
        assert_eq!(template("sky_two_alpha_clouds").slots, &["base", "mask"]);
        assert_eq!(template("sky_one_add_illum_detail").slots, &["mask", "base"]);
        assert_eq!(template("sky_one_add_illum_detail").transparent, 4);
        assert_eq!(template("add_illum_detail").slots, &["mask", "base"]);
        assert_eq!(template("sky_two_add_clouds").slots, &["base", "mask"]);
        assert_eq!(template("two_add_clouds").transparent, 4);
        assert_eq!(template("two_add_detail_masked").slots, &["base", "mask"]);
        assert_eq!(template("two_add_env_illum").slots[3], "base");
        assert_eq!(template("sky_one_alpha_env_clamped").slots[2], "base");
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
        assert_eq!(template("tex_bump_alpha_test_single_pass").alpha_from, "bump");
        assert_eq!(template("tex_bump_alpha_test_clamped_single_pass").alpha_from, "bump");
        assert_eq!(template("tex_bump_alpha_test").alpha_from, "base");
        assert_eq!(template("tex_bump_plasma_one_channel_illum").slots, &["bump", "base", "detail", "plasma"]);
        assert_eq!(template("overlay").transparent, 1, "a double multiply, baked for alpha blending");
    }

    /// The fusion coil core's band is dark at its level (alphas 0.43 to
    /// 0.5 against 0.302) and lit at it.
    #[test]
    fn the_plasma_band_reads_as_compiled() {
        assert_eq!(plasma_band(0.47, 0.302), 0.0);
        assert!((plasma_band(0.302, 0.302) - 1.0).abs() < 1e-3);
        assert!((plasma_band(0.31, 0.302) - 0.66).abs() < 0.01);
    }

    /// An overlay's neutral grey is clear, darker texels black over the
    /// frame by how much they darken it.
    #[test]
    fn overlays_bake_their_multiply_into_alpha() {
        assert!(overlay_texel([0.5; 3]).1.abs() < 1e-6);
        let (c, a) = overlay_texel([0.25; 3]);
        assert_eq!(c, [0.0; 3]);
        assert!((a - 0.5).abs() < 1e-6);
        let (c, a) = overlay_texel([1.0, 0.5, 0.5]);
        assert_eq!(c, [1.0, 0.5, 0.5]);
        assert!(a > 0.0 && a < 0.5);
    }

    /// Uneven tiling becomes a repeated copy: the palm bark's 2 x 12 is six
    /// copies down at scale 2; the beach's 128 x 64 two across at 64.
    #[test]
    fn uneven_tiling_repeats_the_map() {
        assert_eq!(repeats(2.0, 12.0), Some((1, 6)));
        assert_eq!(repeats(128.0, 64.0), Some((2, 1)));
        assert_eq!(repeats(16.0, 16.0), None);
        let img = Image { width: 2, height: 1, rgba: vec![1, 1, 1, 1, 2, 2, 2, 2] };
        let t = tile_image(&img, 2, 3);
        assert_eq!((t.width, t.height), (4, 3));
        assert_eq!(&t.rgba[8 * 2..8 * 2 + 8], &[1, 1, 1, 1, 2, 2, 2, 2]);
        assert_eq!(&t.rgba[16 * 2 + 8..16 * 2 + 16], &[1, 1, 1, 1, 2, 2, 2, 2]);
    }

    /// A slide's repeats per period become a scroll speed, and its phase
    /// goes back into the offset `chicago_map` took it from.
    #[test]
    fn plasma_maps_scroll_per_second() {
        let m = json!({"map_u_scale": 2.0, "map_v_scale": 3.0, "map_u_offset": -0.25, "map_v_offset": 0.5,
                       "u_animation_function": 6, "u_animation_period": 4.0, "u_animation_scale": 1.0,
                       "u_animation_phase": 1.0});
        let (x, s) = plasma_map(&m);
        assert_eq!(x, [2.0, 3.0, 0.0, 0.5]);
        assert_eq!(s, [0.25, 0.0]);
    }

    /// The cut-out's alpha resamples a smaller map bilinearly.
    #[test]
    fn alpha_resamples_bilinearly() {
        let img = Image { width: 2, height: 1, rgba: vec![0, 0, 0, 0, 0, 0, 0, 255] };
        assert_eq!(sample_alpha(&img, 0.25, 0.5), 0);
        assert_eq!(sample_alpha(&img, 0.75, 0.5), 255);
        assert_eq!(sample_alpha(&img, 0.5, 0.5), 128);
    }

    /// A tinted copy is named by its tint in hundredths; a plain gain names
    /// nothing. The transparent templates' texture rows give scale and offset.
    #[test]
    fn tinted_copies_and_texture_rows_read_as_the_shaders_have_them() {
        assert_eq!(tint_suffix([1.0; 3]), "");
        assert_eq!(tint_suffix([0.47, 0.47, 0.6]), "__t2f2f3c");
        // A slot's rows by its descriptors: Ascension's cloud plane binds
        // bitmap 1 to slot 0 and puts slot 1's rows (descriptors 0x5d4,
        // 0x5f5: mask 14 and 15, slot 1) in constants 0 and 1.
        let slots = Slots {
            bitmap: [(0, 1), (1, 0)].into_iter().collect(),
            rows: [((1, 14), 0), ((1, 15), 1), ((0, 14), 2), ((0, 15), 3)].into_iter().collect(),
        };
        let consts = [[3.0, 0.0, 0.0, 0.0], [0.0, 3.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.5]];
        let x = bitmap_transforms(&slots, &consts);
        assert_eq!(x[&0], [3.0, 3.0, 0.0, 0.0], "bitmap 0 takes slot 1's rows");
        assert_eq!(x[&1], [1.0, 1.0, 0.0, 0.5]);
    }

    /// The env templates' constants: tex_bump_env (the Chief's visor) has an
    /// albedo tint first, the _combined ones (Lockout's generic_grey) do not;
    /// the colours always sit before the alpha-only brightness pair.
    #[test]
    fn env_constants_find_the_colours_before_the_brightnesses() {
        let c = |r: u8, g: u8, b: u8, a: u8| [r as f32 / 255.0, g as f32 / 255.0, b as f32 / 255.0, a as f32 / 255.0];
        let visor = [c(255, 255, 255, 0), c(255, 186, 89, 0), c(219, 219, 166, 0), c(0, 0, 0, 229), c(0, 0, 0, 255), c(255, 232, 186, 0)];
        let (f, g, bf, bg) = env_constants(&visor).unwrap();
        assert_eq!((f, g), (visor[1], visor[2]));
        assert_eq!((bf, bg), (229.0 / 255.0, 1.0));
        let grey = [c(255, 255, 255, 0), c(139, 139, 139, 0), c(0, 0, 0, 255), c(0, 0, 0, 255), c(255, 255, 255, 0)];
        assert_eq!(env_constants(&grey).unwrap().1, grey[1]);
        assert!(env_constants(&[c(255, 255, 255, 0), c(180, 179, 189, 0)]).is_none());
    }

    #[test]
    fn the_teleporter_plasma_averages_to_green() {
        // teleporter_plasma's pixel constants: cyan, green, -, yellow.
        let c = |r: u8, g: u8, b: u8| [r as f32 / 255.0, g as f32 / 255.0, b as f32 / 255.0, 0.0];
        let t = plasma_tint(&[c(100, 227, 255), c(109, 217, 104), c(0, 0, 0), c(249, 255, 15)], None, None);
        assert!(t[1] > t[0] && t[1] > t[2], "{t:?}");
        assert!((t[1] - 1.165).abs() < 0.03, "{t:?}");
        assert!(template("one_add_illum").slots == ["base"]);
        assert!(!is_placeholder(r"shaders\default_bitmaps\bitmaps\clouds_256"));
        assert!(is_placeholder(r"shaders\default_bitmaps\bitmaps\gray_50_percent"));
    }

    /// The engine's overlay functions as slides: identity runs lo to hi
    /// over the period, linear at slope -1 runs back, a periodic slide at
    /// frequency 2 repeats twice per period, a constant does not move.
    #[test]
    fn overlays_slide_as_the_engine_evaluates_them() {
        let blob = |kind: u8, sub: u8, floats: &[(usize, f32)]| {
            let mut b = vec![0u8; 0x2C];
            b[0] = kind;
            b[2] = sub;
            b[4..8].copy_from_slice(&0.0f32.to_le_bytes());
            b[8..12].copy_from_slice(&1.0f32.to_le_bytes());
            for &(at, v) in floats {
                b[at..at + 4].copy_from_slice(&v.to_le_bytes());
            }
            b
        };
        assert_eq!(overlay_motion(120.0, &blob(0, 0, &[])), Some((120.0, 1.0, 0.0)));
        assert_eq!(overlay_motion(45.0, &blob(4, 0, &[(0x24, -1.0), (0x28, 1.0)])), Some((45.0, -1.0, 0.0)));
        assert_eq!(overlay_motion(50.0, &blob(3, 6, &[(0x14, 2.0), (0x18, 0.0), (0x1C, 0.0), (0x20, 1.0)])), Some((25.0, 1.0, 0.0)));
        assert_eq!(overlay_motion(1.0, &blob(1, 0, &[])), None);
    }

    /// Halo (x, y, z) is glTF (x, z, -y): a rotation, so winding survives.
    #[test]
    fn the_axis_swap_is_a_rotation() {
        let (x, y, z) = (to_gltf([1.0, 0.0, 0.0]), to_gltf([0.0, 1.0, 0.0]), to_gltf([0.0, 0.0, 1.0]));
        assert_eq!(cross(x, y), z);
    }
}
