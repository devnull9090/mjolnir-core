//! The whole CE-collision-to-canvas recipe in one step ([`blam_sbsp::convert`]).
//!
//! ```text
//! cargo run -p blam-sbsp --example convert -- <donor sbsp> <collision_N.json> <out> \
//!     [--delta dx dy dz] [--park i,j,k | --park-footprint margin | --no-park]
//!     [--shell <BSP_03_1_Chasm_old payload>]
//! ```
//!
//! Without `--delta` the terrain is centred on B40's start; without a park
//! option every instance under its footprint is parked.
use blam_sbsp::ce;
use blam_sbsp::convert::{self, Options, Park};

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.len() < 3 {
        eprintln!(
            "usage: convert <donor sbsp> <collision_N.json> <out> [--delta dx dy dz] \
             [--park i,j,k | --park-footprint margin | --no-park]"
        );
        std::process::exit(2);
    }
    let donor = std::fs::read(&args[0]).expect("donor");
    let staged = ce::load(std::path::Path::new(&args[1])).expect("staging");
    let ce_bounds = staged.collision.bounds().expect("bounds");
    let mut opts = Options::for_terrain(ce_bounds);
    let mut i = 3;
    while i < args.len() {
        match args[i].as_str() {
            "--delta" => {
                opts.delta = [
                    args[i + 1].parse().expect("dx"),
                    args[i + 2].parse().expect("dy"),
                    args[i + 3].parse().expect("dz"),
                ];
                i += 4;
            }
            "--park" => {
                opts.park = Park::Listed(
                    args[i + 1]
                        .split(',')
                        .map(|s| s.parse().expect("instance"))
                        .collect(),
                );
                i += 2;
            }
            "--park-footprint" => {
                opts.park = Park::Footprint {
                    margin: args[i + 1].parse().expect("margin"),
                };
                i += 2;
            }
            "--shell" => {
                opts.shell = Some(convert::ShellOptions {
                    kd_template: std::fs::read(&args[i + 1]).expect("kd template"),
                });
                i += 2;
            }
            "--no-park" => {
                opts.park = Park::None;
                i += 1;
            }
            other => panic!("unknown argument {other}"),
        }
    }
    println!(
        "  delta ({:.3}, {:.3}, {:.3}); CE bounds x[{:.2},{:.2}] y[{:.2},{:.2}] z[{:.2},{:.2}]",
        opts.delta[0],
        opts.delta[1],
        opts.delta[2],
        ce_bounds.min[0],
        ce_bounds.max[0],
        ce_bounds.min[1],
        ce_bounds.max[1],
        ce_bounds.min[2],
        ce_bounds.max[2],
    );
    let t = std::time::Instant::now();
    let (out, r) = convert::convert(&donor, staged.collision, &opts).expect("convert");
    let b = r.bounds;
    println!(
        "  {} surface(s), {} vertices ({} split, {} 2D reference(s) rewired)\n  world bounds x[{:.2},{:.2}] y[{:.2},{:.2}] z[{:.2},{:.2}]\n  group sphere ({:.3}, {:.3}, {:.3}) r {:.2}\n  mopp bytes: definition {}, group {}, cluster {}\n  parked {} instance(s): {:?}",
        r.surfaces, r.vertices, r.split, r.rewired,
        b.min[0], b.max[0], b.min[1], b.max[1], b.min[2], b.max[2],
        r.sphere_center[0], r.sphere_center[1], r.sphere_center[2], r.sphere_radius,
        r.definition_code, r.group_code, r.cluster_code,
        r.parked.len(), &r.parked[..r.parked.len().min(12)],
    );
    std::fs::write(&args[2], &out).expect("write");
    println!(
        "  wrote {} ({} bytes, walks exactly) in {:.1}s",
        args[2],
        out.len(),
        t.elapsed().as_secs_f32()
    );
}
