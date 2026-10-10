//! Check the GPU kernels against the CPU path on a real map: the sky's
//! direct light (`direct_terms_placed`) at every element vertex, and one
//! shooting batch's gather from the brightest elements after the light
//! phase. Prints the largest differences.
//!
//! ```text
//! cargo run --release -p blam-radiosity --features gpu --example gpu_check -- \
//!     <staging dir> <scene.gltf> [--samples N]
//! ```

use blam_radiosity::math::V3;
use blam_radiosity::transport::{self, Options, Set};
use blam_radiosity::{collision, elements, gltf, gpu, staging};
use std::path::PathBuf;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: gpu_check <staging dir> <scene.gltf> [--samples N]");
        std::process::exit(2);
    }
    let staging_dir = PathBuf::from(&args[1]);
    let scene_path = PathBuf::from(&args[2]);
    let limit: usize = args.iter().position(|a| a == "--samples").and_then(|i| args.get(i + 1)).and_then(|v| v.parse().ok()).unwrap_or(200_000);
    let staging = staging::Staging::load(&staging_dir).expect("staging");
    let scene = gltf::Scene::load(&scene_path).expect("scene");
    let tr = scene_path.with_file_name("scene_translucent.gltf");
    let oc = scene_path.with_file_name("scene_occluders.gltf");
    let translucent = tr.exists().then(|| gltf::Scene::load(&tr).expect("translucent"));
    let extra = oc.exists().then(|| gltf::Scene::load(&oc).expect("occluders"));
    let mut occ = transport::Occluders::build(&scene, translucent.as_ref(), extra.as_ref(), &staging, true);
    occ.solid = collision::Collision::load(&staging_dir);
    let opt = Options { quality: elements::Quality::finer(2.0), ..Options::default() };
    let el = elements::Elements::build(&scene, translucent.as_ref(), &staging, &opt.quality, false, None);
    println!("{} occluder triangles, solid {}, {} elements, {} vertices", occ.bvh.len(), occ.solid.is_some(), el.elements.len(), el.pool.vertices.len());
    // Where the elements are: per shader, on a page or not, how many and
    // over what area (the largest first).
    let mut by_shader: std::collections::HashMap<(String, bool), (usize, f32)> = std::collections::HashMap::new();
    // Per shader: texel area on its page at the shipped size, for texels/m.
    let shipped: Vec<(usize, usize)> = staging
        .pages
        .iter()
        .map(|p| staging::Image::load(&staging_dir.join("textures").join(p)).map(|i| (i.width, i.height)).unwrap_or((1, 1)))
        .collect();
    let mut texel_area: std::collections::HashMap<String, f64> = std::collections::HashMap::new();
    for e in &el.elements {
        let m = &el.materials[e.material as usize];
        let entry = by_shader.entry((m.shader.clone(), m.page != usize::MAX)).or_insert((0, 0.0));
        entry.0 += 1;
        entry.1 += e.patch.area;
        if let Some(&(w, h)) = shipped.get(m.page) {
            let uv = e.patch.uv1;
            let t = 0.5 * ((uv[1][0] - uv[0][0]) * (uv[2][1] - uv[0][1]) - (uv[2][0] - uv[0][0]) * (uv[1][1] - uv[0][1])).abs() as f64 * (w * h) as f64;
            *texel_area.entry(m.shader.clone()).or_insert(0.0) += t;
        }
    }
    // What a one-texel floor at 4x would do: per element, its root
    // triangle's floor against its current segment.
    let floor = elements::TexelFloor { texels: 1.0, sizes: shipped.iter().map(|&(w, h)| (w * 4, h * 4)).collect() };
    let (mut bites, mut kept, mut est) = (0usize, 0usize, 0.0f64);
    let mut hist = [0usize; 6];
    for e in &el.elements {
        let Some(t) = scene.tris.get(e.tri as usize) else { continue };
        let f = floor.of(t.p, t.uv1, t.page);
        let ratio = if e.patch.segment > 0.0 { f / e.patch.segment } else { 0.0 };
        let bucket = match ratio { r if r <= 0.0 => 0, r if r < 0.5 => 1, r if r < 1.0 => 2, r if r < 2.0 => 3, r if r < 4.0 => 4, _ => 5 };
        hist[bucket] += 1;
        if f > e.patch.segment {
            bites += 1;
            est += ((e.patch.segment / f) as f64).powi(2);
        } else {
            kept += 1;
        }
    }
    println!("one-texel floor at 4x vs each element's segment: floor 0 {}, <0.5x {}, 0.5-1x {}, 1-2x {}, 2-4x {}, >4x {}", hist[0], hist[1], hist[2], hist[3], hist[4], hist[5]);
    println!("  elements the floor exceeds {bites}, kept {kept}; those would become about {:.0}", est);
    let mut rows: Vec<_> = by_shader.into_iter().collect();
    rows.sort_by(|a, b| b.1 .0.cmp(&a.1 .0));
    let (on_page, off_page): (usize, usize) = rows.iter().fold((0, 0), |(a, b), ((_, page), (n, _))| if *page { (a + n, b) } else { (a, b + n) });
    println!("elements on a page {on_page}, on no page {off_page}");
    for ((shader, page), (n, area)) in rows.iter().take(8) {
        let ta = texel_area.get(shader).copied().unwrap_or(0.0);
        let per_m = (ta / (*area as f64).max(1e-9)).sqrt();
        println!("  {n:>9} elements, {:>9.0} m2, {} shipped texels/m ({:.2} m a texel; x4 {:.2} m): {shader}", area, format!("{per_m:.3}"), 1.0 / per_m.max(1e-9), 0.25 / per_m.max(1e-9));
    }

    let mut g = gpu::Gpu::new(&occ).expect("gpu");
    println!("GPU: {}", g.name);
    let ext = transport::sky_lights(&staging, Set::Exterior, opt.quality.sun_grid, opt.fill_spread);
    let int = transport::sky_lights(&staging, Set::Interior, opt.quality.sun_grid, opt.fill_spread);
    for (i, l) in ext.iter().enumerate() {
        println!("exterior light {i}: {l:?}");
    }

    // Direct light at the vertices (every k-th, up to `limit`).
    let mut samples: Vec<(V3, V3, u32, i32)> = Vec::new();
    let mut cluster_of = vec![-1i32; el.pool.vertices.len()];
    for e in &el.elements {
        for &v in &e.patch.v {
            cluster_of[v as usize] = e.cluster;
        }
    }
    let interior_points = args.iter().any(|a| a == "--interior");
    if interior_points {
        // Points inside the patches, as the per-texel pass samples them.
        use blam_radiosity::math::{add, mul, norm};
        let step = (el.elements.len() / limit).max(1);
        for e in el.elements.iter().step_by(step) {
            let v = |k: usize| &el.pool.vertices[e.patch.v[k] as usize];
            for w in [[0.6f32, 0.3, 0.1], [0.2, 0.2, 0.6], [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]] {
                let p = add(add(mul(v(0).p, w[0]), mul(v(1).p, w[1])), mul(v(2).p, w[2]));
                let n = norm(add(add(mul(v(0).n, w[0]), mul(v(1).n, w[1])), mul(v(2).n, w[2])));
                let set = transport::cluster_set(&staging, e.cluster);
                samples.push((p, n, if set == Set::Interior { 1 } else { 0 }, e.cluster));
            }
        }
    } else {
        let step = (el.pool.vertices.len() / limit).max(1);
        for (i, v) in el.pool.vertices.iter().enumerate().step_by(step) {
            let set = transport::cluster_set(&staging, cluster_of[i]);
            samples.push((v.p, v.n, if set == Set::Interior { 1 } else { 0 }, cluster_of[i]));
        }
    }
    let placed = transport::PlacedLights::default();
    let t = std::time::Instant::now();
    let on_gpu = g.direct(&samples, &ext, &int, &placed, &opt).expect("direct");
    let gpu_s = t.elapsed().as_secs_f64();
    let t = std::time::Instant::now();
    let on_cpu: Vec<(V3, V3, V3, f32)> = {
        use rayon::prelude::*;
        samples
            .par_iter()
            .map(|(p, n, set, cluster)| transport::direct_terms_placed(&occ, if *set == 1 { &int } else { &ext }, &placed, *cluster, *p, *n, &opt))
            .collect()
    };
    let cpu_s = t.elapsed().as_secs_f64();
    let mut worst: Vec<(f32, usize)> = Vec::new();
    let (mut vis_diff, mut gain_diff) = (0usize, 0usize);
    for i in 0..samples.len() {
        let (a, b) = (&on_cpu[i], &on_gpu[i]);
        let dv = (a.3 - b.3).abs();
        let dg = (0..3).map(|k| (a.0[k] - b.0[k]).abs()).fold(0.0, f32::max);
        if dv > 1e-3 {
            vis_diff += 1;
        }
        if dg > 1e-3 {
            gain_diff += 1;
        }
        worst.push((dv.max(dg), i));
    }
    worst.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap());
    println!("direct: {} samples, CPU {:.2}s, GPU {:.2}s; vis differs at {}, gain at {}", samples.len(), cpu_s, gpu_s, vis_diff, gain_diff);
    for &(d, i) in worst.iter().take(8) {
        let s = samples[i];
        println!("  d {d:.4} at p {:?} n {:?} set {}: cpu vis {:.3} gain {:?} | gpu vis {:.3} gain {:?}", s.0, s.1, s.2, on_cpu[i].3, on_cpu[i].0, on_gpu[i].3, on_gpu[i].0);
        if d > 1e-3 {
            // The first sun ray, taken apart: the solid test at its start,
            // and the triangle walk alone.
            if let Some(transport::Light::Directional { towards, .. }) = (if s.2 == 1 { &int } else { &ext }).first() {
                use blam_radiosity::math::{add, mul};
                let start = add(s.0, mul(*towards, 0.001));
                let solid = occ.solid.as_ref().map(|c| c.in_solid(start));
                let hit = occ.bvh.trace(start, *towards, opt.sun_ray - 0.002, false);
                println!("    first sun ray: start in solid {solid:?}, nearest hit {:?}", hit.map(|h| (h.t, h.tri, h.back, occ.tint[h.tri as usize])));
            }
            for l in if s.2 == 1 { &int } else { &ext } {
                if let transport::Light::Directional { towards, .. } = l {
                    let far = blam_radiosity::math::add(s.0, blam_radiosity::math::mul(*towards, opt.sun_ray));
                    let one = transport::direct_terms(&occ, std::slice::from_ref(l), s.0, s.1, &opt);
                    let gone = g.direct(&[s], std::slice::from_ref(l), &[], &placed, &opt).unwrap();
                    println!("    light {towards:?}: cpu t {:?} vis {:.2} | gpu vis {:.2} (far {far:?})", occ.transmission(s.0, far, false), one.3, gone[0].3);
                }
            }
        }
    }
}
