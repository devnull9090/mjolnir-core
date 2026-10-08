//! Classic Halo CE lightmap radiosity, re-solved from a converted map's
//! staging at any resolution. README.md holds the algorithm, recovered from
//! the HEK's `tool.exe lightmaps`, and the acceptance test: at tool.exe's own
//! element density the result must match its lightmaps.

pub mod bvh;
pub mod collision;
pub mod elements;
pub mod gltf;
pub mod math;
pub mod raster;
pub mod staging;
pub mod transport;

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
}

pub struct Solved {
    pub pages: Vec<raster::Page>,
    /// The solved elements and vertices themselves.
    pub detail: elements::Elements,
    /// Emitting elements, and how many of them have no cluster.
    pub emitters: usize,
    pub emitters_unplaced: usize,
    /// Per cluster set, the vertex count (exterior, interior).
    pub set_vertices: (usize, usize),
    pub elements: usize,
    pub vertices: usize,
    pub steps: usize,
    pub splits: usize,
    pub residual: f32,
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
    let elements = elements::Elements::build(&scene, translucent.as_ref(), &staging, &job.options.quality, job.flat_reflectance);
    let mut solver = transport::Solver::new(&staging, &occluders, elements);
    solver.run(&job.options);
    let sizes: Vec<(usize, usize)> = page_sizes.iter().map(|&(w, h)| (w * job.scale, h * job.scale)).collect();
    let lights = (
        transport::sky_lights(&staging, transport::Set::Exterior, job.options.quality.sun_grid, job.options.fill_spread),
        transport::sky_lights(&staging, transport::Set::Interior, job.options.quality.sun_grid, job.options.fill_spread),
    );
    let cluster_sets: Vec<transport::Set> = (0..staging.clusters.as_ref().map(|c| c.clusters.len()).unwrap_or(0))
        .map(|c| transport::cluster_set(&staging, c as i32))
        .collect();
    let pages = raster::pages(&raster::Draw {
        elements: &solver.elements,
        sizes: &sizes,
        supersample: job.supersample,
        occluders: Some(&occluders),
        lights: Some(&lights),
        cluster_sets: Some(&cluster_sets),
        options: &job.options,
    });
    let emitters = solver.elements.elements.iter().filter(|e| e.material < u32::MAX && solver.elements.materials[e.material as usize].emission.iter().any(|c| *c > 0.0)).count();
    let emitters_unplaced = solver.elements.elements.iter().filter(|e| solver.elements.materials[e.material as usize].emission.iter().any(|c| *c > 0.0) && e.cluster < 0).count();
    let set_vertices = solver.set_vertex_counts();
    let residual = solver.residual();
    let (steps, splits) = (solver.steps, solver.splits);
    let detail = solver.elements;
    let (n_elements, n_vertices) = (detail.elements.len(), detail.pool.vertices.len());
    Ok(Solved {
        pages,
        detail,
        emitters,
        emitters_unplaced,
        set_vertices,
        elements: n_elements,
        vertices: n_vertices,
        steps,
        splits,
        residual,
    })
}
