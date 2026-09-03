//! Transplant a staged CE collision BSP into a shipped `sbsp` payload.
//!
//! ```text
//! cargo run -p blam-sbsp --example transplant -- <donor.ubulk> <collision.json> <out.ubulk> [dx dy dz] [--no-mopp] [--keep-supernodes] [--drop-structure-surfaces]
//! ```
//!
//! Every CE surface material maps to the donor's collision material 0 (the
//! probe does not care what the floor sounds like).

use blam_sbsp::ce;
use blam_sbsp::pack16;
use blam_sbsp::transplant::{self, Options, Supernodes};

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut positional = Vec::new();
    let mut opts = Options::default();
    let mut kd: Option<String> = None;
    let mut it = args.iter();
    while let Some(a) = it.next() {
        match a.as_str() {
            "--kd-template" => kd = it.next().cloned(),
            "--no-mopp" => opts.drop_mopp = true,
            "--keep-supernodes" => opts.supernodes = Supernodes::Keep,
            "--no-supernodes" => opts.supernodes = Supernodes::None,
            "--drop-structure-surfaces" => opts.drop_structure_surfaces = true,
            "--no-root-leaves" => opts.root_leaves = false,
            "--no-edge-to-seam" => opts.edge_to_seam = false,
            other => positional.push(other.to_string()),
        }
    }
    if positional.len() < 3 {
        eprintln!(
            "usage: transplant <donor.ubulk> <collision.json> <out.ubulk> [dx dy dz] [flags]"
        );
        std::process::exit(2);
    }
    let donor = std::fs::read(&positional[0]).expect("donor");
    if let Some(k) = kd {
        opts.kd_template = Some(std::fs::read(&k).expect("kd template"));
    }
    let staged = ce::load(std::path::Path::new(&positional[1])).expect("staged collision");
    let mut collision = staged.collision;
    let delta: [f32; 3] = if positional.len() >= 6 {
        [
            positional[3].parse().unwrap(),
            positional[4].parse().unwrap(),
            positional[5].parse().unwrap(),
        ]
    } else {
        [0.0, 0.0, 0.0]
    };
    pack16::translate(&mut collision, delta);
    let bounds = collision.bounds().expect("vertices");
    println!(
        "collision: {} nodes, {} planes, {} leaves, {} surfaces, {} edges, {} vertices",
        collision.bsp3d_nodes.len(),
        collision.planes.len(),
        collision.leaves.len(),
        collision.surfaces.len(),
        collision.edges.len(),
        collision.vertices.len()
    );
    println!(
        "bounds after translate: ({:.2}, {:.2}, {:.2}) .. ({:.2}, {:.2}, {:.2})",
        bounds.min[0], bounds.min[1], bounds.min[2], bounds.max[0], bounds.max[1], bounds.max[2]
    );
    let packed = pack16::pack(&collision, &|_m: i16| 0i16).expect("pack");
    opts.bounds = Some(bounds);
    let plan = transplant::plan(&donor, &packed, &opts).expect("plan");
    for r in &plan {
        println!(
            "  {} <- {} element(s), {} B",
            r.path,
            r.count,
            r.elements.len()
        );
    }
    let out = transplant::apply(&donor, &packed, &opts).expect("apply");

    // The result must walk exactly through the ordinary reader.
    let tag = blam_tag::TagFile::parse(&out, None).expect("parse out");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("walk");
    let payload = tag.data().expect("bdat");
    assert_eq!(root.consumed, payload.size as usize, "output walks exactly");
    std::fs::write(&positional[2], &out).expect("write");
    println!(
        "wrote {} ({} -> {} bytes)",
        positional[2],
        donor.len(),
        out.len()
    );
}
