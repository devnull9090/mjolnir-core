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
    /// Page size multiple (2: 512 -> 1024).
    #[arg(long, default_value_t = 2)]
    pub scale: usize,
    /// Divide tool.exe's element segment lengths by this: denser patches
    /// for the bounce light (the sun and fill are per texel regardless).
    #[arg(long, default_value_t = 2.0)]
    pub finer: f32,
    /// tool.exe's `draft` quality table instead of `final`.
    #[arg(long)]
    pub draft: bool,
    /// Stop shooting when the unshot energy falls to this fraction.
    #[arg(long, default_value_t = 0.01)]
    pub stop: f32,
    /// Shooters per parallel batch.
    #[arg(long, default_value_t = 64)]
    pub batch: usize,
    /// Draw at this multiple and box-filter down (tool.exe: 3).
    #[arg(long, default_value_t = 3)]
    pub supersample: usize,
    /// Leave the placed scenery out of the shadow rays.
    #[arg(long)]
    pub no_objects: bool,
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
    /// Print each shooting step's residual.
    #[arg(long)]
    pub verbose: bool,
    /// At `--scale 1`: per page, the mean and 95th-percentile difference
    /// from the shipped page over the texels both cover (0..255).
    #[arg(long)]
    pub compare: bool,
}

fn read_png(path: &Path) -> Option<(usize, usize, Vec<[f32; 3]>)> {
    let img = blam_radiosity::staging::Image::load(path).ok()?;
    Some((img.width, img.height, img.rgb))
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
    let verbose = a.verbose;
    let job = Job {
        staging_dir: &a.staging,
        scene: &a.scene,
        translucent: translucent.as_deref(),
        occluders: occluders.as_deref(),
        options: Options {
            quality,
            stop: a.stop,
            batch: a.batch,
            texel_direct: !a.no_texel_direct,
            progress: verbose.then(|| Box::new(|step: usize, residual: f32| println!("step {step}: residual {residual:.6}")) as Box<dyn Fn(usize, f32) + Sync>),
            ..Options::default()
        },
        scale: a.scale.max(1),
        objects_occlude: !a.no_objects,
        supersample: a.supersample.max(1),
        flat_reflectance: a.flat_reflectance,
        bsp_solid: !a.no_bsp_solid,
    };

    let staging = Staging::load(&a.staging).map_err(|e| anyhow!("{e}"))?;
    if staging.pages.is_empty() {
        return Err(anyhow!("{}: the staging lists no lightmap pages", a.staging.display()));
    }
    let shipped: Vec<Option<(usize, usize, Vec<[f32; 3]>)>> =
        staging.pages.iter().map(|p| read_png(&a.staging.join("textures").join(p))).collect();
    let sizes: Vec<(usize, usize)> = shipped.iter().map(|p| p.as_ref().map(|(w, h, _)| (*w, *h)).unwrap_or((1, 1))).collect();

    let started = std::time::Instant::now();
    let solved = blam_radiosity::solve(&job, &sizes).map_err(|e| anyhow!("solve: {e}"))?;
    println!(
        "{} element(s), {} vertices, {} shot(s), {} split(s), residual {:.5}, {:.1}s on {} thread(s)",
        solved.elements,
        solved.vertices,
        solved.steps,
        solved.splits,
        solved.residual,
        started.elapsed().as_secs_f32(),
        blam_radiosity::threads()
    );
    println!(
        "{} emitting element(s) ({} without a cluster); vertices exterior {} interior {}",
        solved.emitters, solved.emitters_unplaced, solved.set_vertices.0, solved.set_vertices.1
    );
    for (i, page) in solved.pages.iter().enumerate() {
        let name = staging.pages.get(i).cloned().unwrap_or_else(|| format!("page_{i}.png"));
        page.write_png(&a.out.join(&name)).map_err(|e| anyhow!("{e}"))?;
    }
    println!("{} page(s) at {}x -> {}", solved.pages.len(), a.scale.max(1), a.out.display());

    if a.compare && a.scale <= 1 {
        let mut all: Vec<f32> = Vec::new();
        for (i, page) in solved.pages.iter().enumerate() {
            let Some((w, h, rgb)) = &shipped[i] else { continue };
            if *w != page.width || *h != page.height {
                continue;
            }
            let mut d: Vec<f32> = Vec::new();
            for (k, c) in page.rgb.iter().enumerate() {
                if !page.covered[k] {
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
