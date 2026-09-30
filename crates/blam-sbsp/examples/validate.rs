//! `cargo run -p blam-sbsp --example validate -- <sbsp payload>` — check the
//! world shell of a payload and print what it holds.
fn main() {
    let path = std::env::args().nth(1).expect("payload path");
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
    for p in r.problems.iter().take(20) {
        println!("  problem: {p}");
    }
    println!("{} problem(s)", r.problems.len());
    if !r.problems.is_empty() {
        std::process::exit(1);
    }
}
