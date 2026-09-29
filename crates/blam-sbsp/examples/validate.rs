//! `cargo run -p blam-sbsp --example validate -- <sbsp payload>` — check the
//! world shell of a payload and print what it holds. `-- <payload> <base>`
//! checks another collision container (e.g. a definition's `collision info`);
//! `-- <collision_N.json>` runs the table-level checks on staged CE data.
fn main() {
    let path = std::env::args().nth(1).expect("payload path");
    if path.ends_with(".json") {
        let staged = blam_sbsp::ce::load(std::path::Path::new(&path)).expect("staged collision");
        let c = &staged.collision;
        let bad = blam_sbsp::validate::two_sided_leaves_unflagged(c);
        let two_sided = c.surfaces.iter().filter(|s| s.flags & 1 != 0).count();
        println!(
            "leaves {} surfaces {} (two-sided {two_sided}); leaves reaching a two-sided surface without flag bit 0: {}",
            c.leaves.len(),
            c.surfaces.len(),
            bad.len()
        );
        if !bad.is_empty() {
            std::process::exit(1);
        }
        return;
    }
    let file = std::fs::read(&path).expect("read");
    let base = std::env::args().nth(2);
    let r = match base {
        Some(b) => blam_sbsp::validate::at(&file, &b).expect("validate"),
        None => blam_sbsp::validate::shell(&file).expect("validate"),
    };
    println!(
        "nodes {} (roots {:?}) supernodes {} planes {} leaves {} (referenced {}) 2d refs {} 2d nodes {} surfaces {} edges {} vertices {}",
        r.nodes, r.roots, r.supernodes, r.planes, r.leaves, r.leaves_referenced,
        r.bsp2d_references, r.bsp2d_nodes, r.surfaces, r.edges, r.vertices
    );
    println!(
        "polygons {} triangles {} bounds {:?}",
        r.polygons, r.triangles, r.bounds
    );
    println!(
        "leaves reaching a two-sided surface without flag bit 0: {}",
        r.two_sided_leaves_unflagged.len()
    );
    for p in r.problems.iter().take(20) {
        println!("  problem: {p}");
    }
    println!("{} problem(s)", r.problems.len());
    if !r.problems.is_empty() {
        std::process::exit(1);
    }
}
