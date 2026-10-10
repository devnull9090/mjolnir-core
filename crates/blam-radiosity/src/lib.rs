//! Classic Halo CE lightmap radiosity, re-solved from a converted map's
//! staging at any resolution. README.md holds the algorithm, recovered from
//! the HEK's `tool.exe lightmaps`, and the acceptance test: at tool.exe's own
//! element density the result must match its lightmaps.

pub mod bvh;
pub mod collision;
pub mod elements;
pub mod gltf;
#[cfg(feature = "gpu")]
pub mod gpu;
#[cfg(not(feature = "gpu"))]
#[path = "gpu_none.rs"]
pub mod gpu;
pub mod math;
pub mod raster;
pub mod staging;
pub mod transport;
pub mod visibility;

use std::path::Path;

/// A whole solve: the staging's scene and lights in, lightmap pages out.
/// How many threads the CPU path uses.
pub fn threads() -> usize {
    rayon::current_num_threads()
}

pub struct Job<'a> {
    pub staging_dir: &'a Path,
    /// The merged scene (`scene.gltf` of the conversion), whose BSP
    /// primitives come first and in the staging's order.
    pub scene: &'a Path,
    /// The merged scene's transparent pieces, which tint the light.
    pub translucent: Option<&'a Path>,
    /// Extra opaque occluders: the placed objects' collision models
    /// (`merge_ce_scene.py --occluders`).
    pub occluders: Option<&'a Path>,
    /// The placed lights (`merge_ce_scene.py --lights`): CE's light
    /// fixtures and the lamps its scenery carries.
    pub lights: Option<&'a Path>,
    pub options: transport::Options,
    /// Page size multiple over the shipped lightmap pages.
    pub scale: usize,
    /// Placed objects occlude.
    pub objects_occlude: bool,
    /// Pages are drawn at this multiple and box-filtered down (tool.exe: 3).
    pub supersample: usize,
    /// Reflect each shader's base map's mean colour instead of three
    /// texels under the patch's corners.
    pub flat_reflectance: bool,
    /// Block rays that start or end inside the collision BSP's solid, as
    /// tool.exe's BSP walk does.
    pub bsp_solid: bool,
    /// Cast the gather's and the per-texel pass's rays on the GPU (the
    /// `gpu` feature); the CPU when there is no adapter.
    pub gpu: bool,
    /// No element edge shorter than this many of its own texels at the
    /// drawn page size (`elements::TexelFloor`); 0: tool.exe's rows only.
    pub texel_elements: f32,
}

pub struct Solved {
    pub pages: Vec<raster::Page>,
    /// Per page, the sun's visibility (grey, same size and coverage), from
    /// the per-texel pass; empty without it.
    pub sun_pages: Vec<raster::Page>,
    /// Per page, the texel's light without the sun (CE's ambient, fill and
    /// bounce), a lightmap page of its own; from the per-texel pass.
    pub ambient_pages: Vec<raster::Page>,
    /// Per page, the sun's potential (grey): its share of the light the
    /// texel would hold with the sun unblocked; from the per-texel pass.
    pub potential_pages: Vec<raster::Page>,
    /// The solved elements and vertices themselves.
    pub detail: elements::Elements,
    /// Emitting elements, and how many of them have no cluster.
    pub emitters: usize,
    pub emitters_unplaced: usize,
    /// How many placed lights lit the scene.
    pub placed_lights: usize,
    /// Per cluster set, the vertex count (exterior, interior).
    pub set_vertices: (usize, usize),
    pub elements: usize,
    pub vertices: usize,
    pub steps: usize,
    pub splits: usize,
    pub residual: f32,
    pub timings: transport::Timings,
    /// Where the rays were cast: the GPU adapter, or "CPU" (and why).
    pub backend: String,
}

pub fn solve(job: &Job, page_sizes: &[(usize, usize)]) -> Result<Solved, String> {
    let staging = staging::Staging::load(job.staging_dir)?;
    let scene = gltf::Scene::load(job.scene)?;
    let translucent = match job.translucent {
        Some(p) if p.exists() => Some(gltf::Scene::load(p)?),
        _ => None,
    };
    let extra = match job.occluders {
        Some(p) if p.exists() => Some(gltf::Scene::load(p)?),
        _ => None,
    };
    let mut occluders = transport::Occluders::build(&scene, translucent.as_ref(), extra.as_ref(), &staging, job.objects_occlude);
    if job.bsp_solid {
        occluders.solid = collision::Collision::load(job.staging_dir);
    }
    let sizes: Vec<(usize, usize)> = page_sizes.iter().map(|&(w, h)| (w * job.scale, h * job.scale)).collect();
    let floor = (job.texel_elements > 0.0).then(|| elements::TexelFloor { texels: job.texel_elements, sizes: sizes.clone() });
    let elements = elements::Elements::build(&scene, translucent.as_ref(), &staging, &job.options.quality, job.flat_reflectance, floor.as_ref());
    let mut solver = transport::Solver::new(&staging, &occluders, elements);
    let mut backend = "CPU".to_string();
    if job.gpu {
        match gpu::Gpu::new(&occluders) {
            Ok(g) => {
                backend = g.name.clone();
                solver.gpu = Some(g);
            }
            Err(e) => backend = format!("CPU (no GPU: {e})"),
        }
    }
    let placed_lights = match job.lights {
        Some(p) if p.exists() => solver.load_placed(p)?,
        _ => 0,
    };
    solver.run(&job.options);
    let lights = (
        transport::sky_lights(&staging, transport::Set::Exterior, job.options.quality.sun_grid, job.options.fill_spread),
        transport::sky_lights(&staging, transport::Set::Interior, job.options.quality.sun_grid, job.options.fill_spread),
    );
    let cluster_sets: Vec<transport::Set> = (0..staging.clusters.as_ref().map(|c| c.clusters.len()).unwrap_or(0))
        .map(|c| transport::cluster_set(&staging, c as i32))
        .collect();
    let mut gpu = solver.gpu.take();
    if job.gpu && gpu.is_none() && !backend.starts_with("CPU") {
        backend = format!("CPU (the GPU failed: {})", solver.gpu_error.as_deref().unwrap_or("?"));
    }
    let drawing = std::time::Instant::now();
    let mut texel_direct = 0.0f64;
    let (pages, sun_pages, ambient_pages, potential_pages) = raster::pages(&mut raster::Draw {
        elements: &solver.elements,
        sizes: &sizes,
        supersample: job.supersample,
        dilate: 8 * job.scale.max(1),
        occluders: Some(&occluders),
        lights: Some(&lights),
        placed: Some(&solver.placed),
        cluster_sets: Some(&cluster_sets),
        options: &job.options,
        texel_direct_seconds: Some(&mut texel_direct),
        gpu: gpu.as_mut(),
    });
    solver.timings.draw = drawing.elapsed().as_secs_f64();
    solver.timings.texel_direct = texel_direct;
    let emitters = solver.elements.elements.iter().filter(|e| e.material < u32::MAX && solver.elements.materials[e.material as usize].emission.iter().any(|c| *c > 0.0)).count();
    let emitters_unplaced = solver.elements.elements.iter().filter(|e| solver.elements.materials[e.material as usize].emission.iter().any(|c| *c > 0.0) && e.cluster < 0).count();
    let set_vertices = solver.set_vertex_counts();
    let residual = solver.residual();
    let (steps, splits, timings) = (solver.steps, solver.splits, solver.timings);
    let detail = solver.elements;
    let (n_elements, n_vertices) = (detail.elements.len(), detail.pool.vertices.len());
    Ok(Solved {
        pages,
        sun_pages,
        ambient_pages,
        potential_pages,
        detail,
        emitters,
        emitters_unplaced,
        placed_lights,
        set_vertices,
        elements: n_elements,
        vertices: n_vertices,
        steps,
        splits,
        residual,
        timings,
        backend,
    })
}
