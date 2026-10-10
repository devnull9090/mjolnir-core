//! Solve a converted map's lightmaps and write them as PNG pages.
//!
//! ```text
//! cargo run --release -p blam-radiosity --example radiosity_bake -- \
//!     <staging dir> <scene.gltf> <out dir> [--scale 1] [--quality final|draft]
//!     [--finer K] [--stop 0.01] [--batch 64] [--no-sun-cosine] [--no-objects]
//!     [--no-adaptive] [--gpu] [--compare]
//! ```
//!
//! The staging is halo2ue's (its `textures/` holds the shipped lightmap
//! pages, which set the page sizes and, with `--compare`, the reference:
//! per page the mean and 95th-percentile absolute difference over the
//! texels both cover, in 0..255). `--finer K` divides tool.exe's segment
//! lengths by K for denser elements; `--scale` multiplies the page sizes.

use blam_radiosity::{elements::Quality, transport::Options, Job};
use std::path::{Path, PathBuf};

fn arg<T: std::str::FromStr>(args: &[String], name: &str, default: T) -> T {
    args.iter()
        .position(|a| a == name)
        .and_then(|i| args.get(i + 1))
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
}

fn read_png(path: &Path) -> Option<(usize, usize, Vec<[f32; 3]>)> {
    let img = blam_radiosity::staging::Image::load(path).ok()?;
    Some((img.width, img.height, img.rgb))
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 4 {
        eprintln!("usage: radiosity_bake <staging dir> <scene.gltf> <out dir> [options]");
        std::process::exit(2);
    }
    let staging_dir = PathBuf::from(&args[1]);
    let scene = PathBuf::from(&args[2]);
    let out = PathBuf::from(&args[3]);
    std::fs::create_dir_all(&out).expect("out dir");
    let scale: usize = arg(&args, "--scale", 1);
    let finer: f32 = arg(&args, "--finer", 1.0);
    let quality = match arg(&args, "--quality", "final".to_string()).as_str() {
        "draft" => Quality::draft(),
        _ if finer != 1.0 => Quality::finer(finer),
        _ => Quality::final_(),
    };
    let translucent = scene.with_file_name("scene_translucent.gltf");
    let occluders = scene.with_file_name("scene_occluders.gltf");
    let job = Job {
        staging_dir: &staging_dir,
        scene: &scene,
        translucent: Some(&translucent),
        occluders: Some(&occluders),
        lights: None,
        options: Options {
            quality,
            stop: arg(&args, "--stop", 0.01),
            batch: arg(&args, "--batch", 64),
            sun_cosine: !args.iter().any(|a| a == "--no-sun-cosine"),
            adaptive: !args.iter().any(|a| a == "--no-adaptive"),
            sun_ray: arg(&args, "--sun-ray", 1.0e4),
            solid_test: args.iter().any(|a| a == "--solid-test"),
            fill_spread: arg(&args, "--fill-spread", 1.0),
            texel_direct: !args.iter().any(|a| a == "--no-texel-direct"),
            progress: Some(Box::new(|step, residual| println!("step {step}: residual {residual:.6}"))),
        },
        scale,
        objects_occlude: !args.iter().any(|a| a == "--no-objects"),
        supersample: arg(&args, "--supersample", 3),
        flat_reflectance: args.iter().any(|a| a == "--flat-reflectance"),
        bsp_solid: !args.iter().any(|a| a == "--no-bsp-solid"),
        gpu: args.iter().any(|a| a == "--gpu"),
        texel_elements: arg(&args, "--texel-elements", 0.0),
    };

    let staging = blam_radiosity::staging::Staging::load(&staging_dir).expect("staging");
    // `--dump <csv>`: every root patch corner's position, normal, page,
    // lightmap UV, cluster and solved irradiance, for analysis.
    let dump: Option<PathBuf> = args.iter().position(|a| a == "--dump").and_then(|i| args.get(i + 1)).map(PathBuf::from);
    let shipped: Vec<Option<(usize, usize, Vec<[f32; 3]>)>> =
        staging.pages.iter().map(|p| read_png(&staging_dir.join("textures").join(p))).collect();
    let sizes: Vec<(usize, usize)> = shipped.iter().map(|p| p.as_ref().map(|(w, h, _)| (*w, *h)).unwrap_or((1, 1))).collect();

    let started = std::time::Instant::now();
    let solved = blam_radiosity::solve(&job, &sizes).expect("solve");
    if let Some(path) = &dump {
        let mut out = String::from("px,py,pz,nx,ny,nz,page,u,v,cluster,shader,r,g,b,sun,ambient,bounce\n");
        for e in &solved.detail.elements {
            let m = &solved.detail.materials[e.material as usize];
            for (k, &vi) in e.patch.v.iter().enumerate() {
                let v = &solved.detail.pool.vertices[vi as usize];
                let c = blam_radiosity::raster::vertex_colour(v.total);
                let l = blam_radiosity::math::luma;
                out.push_str(&format!(
                    "{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n",
                    v.p[0], v.p[1], v.p[2], v.n[0], v.n[1], v.n[2], m.page, e.patch.uv1[k][0], e.patch.uv1[k][1], e.cluster, m.shader, c[0], c[1], c[2],
                    l(v.sun), l(v.ambient), l(v.total) - l(v.sun) - l(v.ambient)
                ));
            }
        }
        std::fs::write(path, out).expect("dump");
    }
    println!(
        "{} element(s), {} vertices, {} shot(s), {} split(s), residual {:.5}, {:.1}s",
        solved.elements,
        solved.vertices,
        solved.steps,
        solved.splits,
        solved.residual,
        started.elapsed().as_secs_f32()
    );
    println!(
        "{} emitting element(s) ({} without a cluster); vertices exterior {} interior {}",
        solved.emitters, solved.emitters_unplaced, solved.set_vertices.0, solved.set_vertices.1
    );
    for (i, page) in solved.pages.iter().enumerate() {
        let name = staging.pages.get(i).cloned().unwrap_or_else(|| format!("page_{i}.png"));
        page.write_png(&out.join(&name)).expect("write page");
    }
    if args.iter().any(|a| a == "--compare") && scale == 1 {
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
                let dl = ((c[0] - s[0]).abs() + (c[1] - s[1]).abs() + (c[2] - s[2]).abs()) / 3.0 * 255.0;
                d.push(dl);
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
            println!(
                "all pages: mean |d| {:.1}/255, 95th {:.1}",
                all.iter().sum::<f32>() / all.len() as f32,
                all[(all.len() as f32 * 0.95) as usize]
            );
        }
    }
}
