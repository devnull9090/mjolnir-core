//! `mjolnir level lightmaps` — re-solve a classic map's lightmaps with
//! [`blam_radiosity`]: tool.exe's radiosity (the sky's sun and fill, the
//! shaders' emission and reflectance, the cluster sets) on every core,
//! drawn at any multiple of the shipped pages' size. The pages replace the
//! shipped ones in `ce_material_spec.py --lightmaps`, so a conversion keeps
//! CE's light with shadow edges the shipped 1x pages could not hold.

use std::path::{Path, PathBuf};

use anyhow::{anyhow, Context, Result};
use blam_radiosity::{elements::Quality, staging::Staging, transport::Options, Job};
use clap::Args;

#[derive(Args)]
pub struct LightmapsArgs {
    /// halo2ue's staging directory for the map (its `textures/` holds the
    /// shipped lightmap pages, which set the page sizes and chart layout).
    pub staging: PathBuf,
    /// The merged scene (`merge_ce_scene.py`): `scene_translucent.gltf` and
    /// `scene_occluders.gltf` beside it are used when present.
    pub scene: PathBuf,
    /// Where the pages are written, one PNG per shipped page, same names.
    pub out: PathBuf,
    /// Page size multiple (2: 512 -> 1024), or `auto`: the smallest power of
    /// two that brings the lit surfaces' median texel density to `--density`,
    /// within `--max-page` and `--max-texels`.
    #[arg(long, default_value = "auto")]
    pub scale: String,
    /// `--scale auto`: the texel density to reach, texels per metre along a
    /// surface (CE's own pages sit near 0.3 on an outdoor map, 1 on a base).
    #[arg(long, default_value_t = 4.0)]
    pub density: f32,
    /// `--scale auto`: no page larger than this on a side.
    #[arg(long, default_value_t = 2048)]
    pub max_page: usize,
    /// `--scale auto`: all pages together at most this many texels (millions).
    #[arg(long, default_value_t = 48.0)]
    pub max_texels: f32,
    /// Divide tool.exe's element segment lengths by this: denser patches
    /// for the bounce light (the sun and fill are per texel regardless).
    #[arg(long, default_value_t = 2.0)]
    pub finer: f32,
    /// tool.exe's `draft` quality table instead of `final`.
    #[arg(long)]
    pub draft: bool,
    /// Stop shooting when the area-weighted mean unshot energy falls to this
    /// (tool.exe prints 0.01; its pages match a solve taken further).
    #[arg(long, default_value_t = 0.001)]
    pub stop: f32,
    /// Shooters per parallel batch. Each batch costs a pass over every
    /// element whatever its size, so with `--gpu` (where the rays are cheap)
    /// 256 solves several times faster; the pages move (the brightest shoot
    /// together rather than in turn, and a batch's receivers are every
    /// cluster any of its shooters sees): single texels on most maps, whole
    /// interior pages 10-40/255 brighter on Coldsnap.
    #[arg(long, default_value_t = 64)]
    pub batch: usize,
    /// Draw at this multiple and box-filter down (tool.exe: 3).
    #[arg(long, default_value_t = 3)]
    pub supersample: usize,
    /// Leave the placed scenery out of the shadow rays.
    #[arg(long)]
    pub no_objects: bool,
    /// Light the pages with the placed lights too (`scene_lights.json`
    /// beside the scene: the `light` tags on light fixtures and scenery, as
    /// point or spot lights at intensity / d^2). Off by default: tool.exe's
    /// own pages show none of their light (Death Island's twenty fixtures
    /// leave no pool on the walls beside them), so a map's interior light is
    /// its emitting shaders'.
    #[arg(long)]
    pub placed_lights: bool,
    /// Evaluate the sun and fill at the patch corners only (Gouraud), not
    /// at every texel.
    #[arg(long)]
    pub no_texel_direct: bool,
    /// Do not block rays that start or end inside the collision BSP's solid.
    #[arg(long)]
    pub no_bsp_solid: bool,
    /// Reflect each shader's base map's mean colour rather than the texels
    /// under each patch.
    #[arg(long)]
    pub flat_reflectance: bool,
    /// Cast the rays on the GPU (wgpu: Vulkan, DX12 or Metal): the
    /// receivers' gather and the per-texel sun and fill. The CPU path stays
    /// the reference and runs when no adapter is found.
    #[arg(long)]
    pub gpu: bool,
    /// Print each shooting step's residual.
    #[arg(long)]
    pub verbose: bool,
    /// At `--scale 1`: per page, the mean and 95th-percentile difference
    /// from the shipped page over the texels our charts cover (0..255).
    #[arg(long)]
    pub compare: bool,
}

/// The lit surfaces' area-weighted median texel density at the shipped page
/// sizes, texels per metre along the surface.
fn texel_density(scene: &blam_radiosity::gltf::Scene, sizes: &[(usize, usize)]) -> Option<f32> {
    let mut v: Vec<(f32, f32)> = Vec::new();
    for t in &scene.tris {
        let (Some(uv), Some(page)) = (t.uv1, t.page) else { continue };
        let Some(&(w, h)) = sizes.get(page) else { continue };
        let e1 = blam_radiosity::math::sub(t.p[1], t.p[0]);
        let e2 = blam_radiosity::math::sub(t.p[2], t.p[0]);
        let c = blam_radiosity::math::cross(e1, e2);
        let wa = 0.5 * (c[0] * c[0] + c[1] * c[1] + c[2] * c[2]).sqrt();
        if wa < 1e-6 {
            continue;
        }
        let (w, h) = (w as f32, h as f32);
        let ua = 0.5 * ((uv[1][0] - uv[0][0]) * w * (uv[2][1] - uv[0][1]) * h - (uv[2][0] - uv[0][0]) * w * (uv[1][1] - uv[0][1]) * h).abs();
        v.push(((ua / wa).sqrt(), wa));
    }
    if v.is_empty() {
        return None;
    }
    v.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap());
    let total: f32 = v.iter().map(|x| x.1).sum();
    let mut acc = 0.0;
    for (d, a) in &v {
        acc += a;
        if acc >= total * 0.5 {
            return Some(*d);
        }
    }
    v.last().map(|x| x.0)
}

fn read_png(path: &Path) -> Option<(usize, usize, Vec<[f32; 3]>)> {
    let img = blam_radiosity::staging::Image::load(path).ok()?;
    Some((img.width, img.height, img.rgb))
}

/// `--verbose`: per emitting shader, its elements, the energy it started
/// with and what is left unshot, and how lit the surfaces within 1.5 m of
/// it ended up (the receivers its light should land on first).
fn emitter_report(d: &blam_radiosity::elements::Elements) {
    use blam_radiosity::math::{luma, sub, dot};
    let emitting: Vec<usize> = (0..d.materials.len()).filter(|&m| d.materials[m].emission.iter().any(|c| *c > 0.0)).collect();
    for m in emitting {
        let mat = &d.materials[m];
        let (mut count, mut energy, mut left, mut area) = (0usize, 0.0f32, 0.0f32, 0.0f32);
        let mut centroids: Vec<[f32; 3]> = Vec::new();
        for e in &d.elements {
            if e.material as usize != m {
                continue;
            }
            count += 1;
            area += e.patch.area;
            energy += mat.emission.iter().sum::<f32>() * e.patch.area;
            left += e.delta.iter().sum::<f32>() * e.patch.area;
            let v = &d.pool.vertices;
            let c = [
                (v[e.patch.v[0] as usize].p[0] + v[e.patch.v[1] as usize].p[0] + v[e.patch.v[2] as usize].p[0]) / 3.0,
                (v[e.patch.v[0] as usize].p[1] + v[e.patch.v[1] as usize].p[1] + v[e.patch.v[2] as usize].p[1]) / 3.0,
                (v[e.patch.v[0] as usize].p[2] + v[e.patch.v[1] as usize].p[2] + v[e.patch.v[2] as usize].p[2]) / 3.0,
            ];
            centroids.push(c);
        }
        // The vertices of other, non-emitting elements within 1.5 m.
        let mut near = Vec::new();
        let mut seen = vec![false; d.pool.vertices.len()];
        for e in &d.elements {
            if d.materials[e.material as usize].emission.iter().any(|c| *c > 0.0) {
                continue;
            }
            for &vi in &e.patch.v {
                if seen[vi as usize] {
                    continue;
                }
                seen[vi as usize] = true;
                let p = d.pool.vertices[vi as usize].p;
                if centroids.iter().any(|c| { let q = sub(*c, p); dot(q, q) < 2.25 }) {
                    near.push(vi);
                }
            }
        }
        let lit = if near.is_empty() { 0.0 } else { near.iter().map(|&vi| luma(d.pool.vertices[vi as usize].total)).sum::<f32>() / near.len() as f32 };
        let clusters: std::collections::BTreeSet<i32> = d.elements.iter().filter(|e| e.material as usize == m).map(|e| e.cluster).collect();
        println!(
            "emitter {}: {} element(s), {:.1} m2, energy {:.0} (unshot {:.1}), clusters {:?}, {} vertex(es) within 1.5 m at mean luma {:.3}",
            mat.shader, count, area, energy, left, clusters, near.len(), lit
        );
    }
}

pub fn run(a: LightmapsArgs) -> Result<()> {
    std::fs::create_dir_all(&a.out).with_context(|| format!("create {}", a.out.display()))?;
    let quality = if a.draft {
        Quality::draft()
    } else if a.finer != 1.0 {
        Quality::finer(a.finer)
    } else {
        Quality::final_()
    };
    let beside = |name: &str| -> Option<PathBuf> {
        let p = a.scene.with_file_name(name);
        p.exists().then_some(p)
    };
    let translucent = beside("scene_translucent.gltf");
    let occluders = beside("scene_occluders.gltf");
    let lights = if a.placed_lights { beside("scene_lights.json") } else { None };
    let verbose = a.verbose;
    let staging = Staging::load(&a.staging).map_err(|e| anyhow!("{e}"))?;
    if staging.pages.is_empty() {
        return Err(anyhow!("{}: the staging lists no lightmap pages", a.staging.display()));
    }
    let shipped: Vec<Option<(usize, usize, Vec<[f32; 3]>)>> =
        staging.pages.iter().map(|p| read_png(&a.staging.join("textures").join(p))).collect();
    let sizes: Vec<(usize, usize)> = shipped.iter().map(|p| p.as_ref().map(|(w, h, _)| (*w, *h)).unwrap_or((1, 1))).collect();
    let scale: usize = if a.scale.trim().eq_ignore_ascii_case("auto") {
        let scene = blam_radiosity::gltf::Scene::load(&a.scene).map_err(|e| anyhow!("{e}"))?;
        let density = texel_density(&scene, &sizes).unwrap_or(1.0);
        let longest = sizes.iter().map(|&(w, h)| w.max(h)).max().unwrap_or(1).max(1);
        let texels: f32 = sizes.iter().map(|&(w, h)| (w * h) as f32).sum();
        let mut s = 1usize;
        while (density * s as f32) < a.density
            && longest * s * 2 <= a.max_page.max(1)
            && texels * ((s * 2) * (s * 2)) as f32 <= a.max_texels * 1.0e6
        {
            s *= 2;
        }
        println!(
            "scale auto: {s}x (shipped pages {:.2} texels/m median, {} pages, longest side {}; at {s}x {:.2}/m and {:.1} M texels)",
            density,
            sizes.len(),
            longest,
            density * s as f32,
            texels * (s * s) as f32 / 1.0e6
        );
        s
    } else {
        a.scale.trim().parse::<usize>().map_err(|_| anyhow!("--scale takes a number or `auto`, not {:?}", a.scale))?.max(1)
    };
    let job = Job {
        staging_dir: &a.staging,
        scene: &a.scene,
        translucent: translucent.as_deref(),
        occluders: occluders.as_deref(),
        lights: lights.as_deref(),
        options: Options {
            quality,
            stop: a.stop,
            batch: a.batch,
            texel_direct: !a.no_texel_direct,
            progress: verbose.then(|| Box::new(|step: usize, residual: f32| println!("step {step}: residual {residual:.6}")) as Box<dyn Fn(usize, f32) + Sync>),
            ..Options::default()
        },
        scale,
        objects_occlude: !a.no_objects,
        supersample: a.supersample.max(1),
        flat_reflectance: a.flat_reflectance,
        bsp_solid: !a.no_bsp_solid,
        gpu: a.gpu,
    };

    let started = std::time::Instant::now();
    let solved = blam_radiosity::solve(&job, &sizes).map_err(|e| anyhow!("solve: {e}"))?;
    println!(
        "{} element(s), {} vertices, {} shot(s), {} split(s), residual {:.5}, {:.1}s on {} thread(s), rays on {}",
        solved.elements,
        solved.vertices,
        solved.steps,
        solved.splits,
        solved.residual,
        started.elapsed().as_secs_f32(),
        blam_radiosity::threads(),
        solved.backend
    );
    let t = &solved.timings;
    println!(
        "time: light {:.1}s, shooting {:.1}s (select {:.1}s, gather {:.1}s, settle {:.1}s), draw {:.1}s (per-texel direct {:.1}s)",
        t.light,
        t.select + t.gather + t.settle,
        t.select,
        t.gather,
        t.settle,
        t.draw,
        t.texel_direct
    );
    println!(
        "{} emitting element(s) ({} without a cluster), {} placed light(s); vertices exterior {} interior {}",
        solved.emitters, solved.emitters_unplaced, solved.placed_lights, solved.set_vertices.0, solved.set_vertices.1
    );
    if verbose {
        emitter_report(&solved.detail);
    }
    for (i, page) in solved.pages.iter().enumerate() {
        let name = staging.pages.get(i).cloned().unwrap_or_else(|| format!("page_{i}.png"));
        page.write_png(&a.out.join(&name)).map_err(|e| anyhow!("{e}"))?;
    }
    for (i, page) in solved.sun_pages.iter().enumerate() {
        let name = staging.pages.get(i).cloned().unwrap_or_else(|| format!("page_{i}.png"));
        let stem = name.strip_suffix(".png").unwrap_or(&name);
        page.write_png(&a.out.join(format!("{stem}_sunvis.png"))).map_err(|e| anyhow!("{e}"))?;
    }
    // <page>_sunshare.png: the texel's light without the sun
    // (ce_material_spec.py SunShare); the masters put the sun back per
    // channel from the sky's sun (environment.sun.ce_light) at the texel's
    // N.L, so no share rides along.
    for (i, page) in solved.ambient_pages.iter().enumerate() {
        let name = staging.pages.get(i).cloned().unwrap_or_else(|| format!("page_{i}.png"));
        let stem = name.strip_suffix(".png").unwrap_or(&name);
        page.write_png(&a.out.join(format!("{stem}_sunshare.png"))).map_err(|e| anyhow!("{e}"))?;
    }
    println!(
        "{} page(s) at {}x -> {}{}",
        solved.pages.len(),
        scale,
        a.out.display(),
        if solved.sun_pages.is_empty() { "" } else { " (+ <page>_sunvis.png: the sun's visibility; <page>_sunshare.png: the light without the sun)" }
    );

    if a.compare && scale <= 1 {
        let mut all: Vec<f32> = Vec::new();
        for (i, page) in solved.pages.iter().enumerate() {
            let Some((w, h, rgb)) = &shipped[i] else { continue };
            if *w != page.width || *h != page.height {
                continue;
            }
            let mut d: Vec<f32> = Vec::new();
            for (k, c) in page.rgb.iter().enumerate() {
                // Only where a chart was drawn: the dilation reaches into
                // charts of surfaces the export lacks (Hang 'Em High's page
                // 1 is a sixth such), which tool.exe filled light blue.
                if !page.drawn[k] {
                    continue;
                }
                let s = rgb[k];
                // tool.exe fills the space between charts with a red and
                // yellow checkerboard; our dilation reaches into it.
                let filler = s[0] > 0.99 && s[2] < 0.01 && (s[1] > 0.99 || s[1] < 0.01);
                if filler {
                    continue;
                }
                d.push(((c[0] - s[0]).abs() + (c[1] - s[1]).abs() + (c[2] - s[2]).abs()) / 3.0 * 255.0);
            }
            if d.is_empty() {
                continue;
            }
            d.sort_by(|a, b| a.partial_cmp(b).unwrap());
            let mean = d.iter().sum::<f32>() / d.len() as f32;
            let p95 = d[(d.len() as f32 * 0.95) as usize];
            println!("page {i:2} {w}x{h}: {} texel(s), mean |d| {mean:.1}/255, 95th {p95:.1}", d.len());
            all.extend(d);
        }
        if !all.is_empty() {
            all.sort_by(|a, b| a.partial_cmp(b).unwrap());
            println!("all pages: mean |d| {:.1}/255, 95th {:.1}", all.iter().sum::<f32>() / all.len() as f32, all[(all.len() as f32 * 0.95) as usize]);
        }
    }
    Ok(())
}
