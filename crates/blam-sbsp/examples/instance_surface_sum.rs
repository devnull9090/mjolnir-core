//! Sum the collision surfaces (and fan-split triangles) of every instance's
//! definition, to compare with the structure_physics MOPP's terminal count.
//!
//!   cargo run -p blam-sbsp --example instance_surface_sum -- <payload>
use blam_sbsp::convert;
use blam_sbsp::transplant;
use blam_tag::blockedit::find_block;

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let inst = find_block(&layout, &file, &root, convert::INSTANCES).expect("instances");
    let mut surf_by_def = std::collections::HashMap::new();
    let (mut all, mut phys, mut tris_all, mut n_phys) = (0usize, 0usize, 0usize, 0usize);
    for i in 0..inst.block.count as usize {
        let e = inst.block.element(i).unwrap();
        let d = i16::from_le_bytes([e[52], e[53]]);
        if d < 0 {
            continue;
        }
        let (s, t) = *surf_by_def.entry(d).or_insert_with(|| {
            let coll = transplant::definition(d as usize);
            let surfaces = find_block(&layout, &file, &root, &format!("{coll}.surfaces"))
                .map(|f| f.block.count as usize)
                .unwrap_or(0);
            let edges = find_block(&layout, &file, &root, &format!("{coll}.edges"))
                .map(|f| f.block.count as usize)
                .unwrap_or(0);
            (surfaces, edges)
        });
        all += s;
        tris_all += t;
        let has_phys = find_block(
            &layout,
            &file,
            &root,
            &format!("{}[{i}].physics", convert::INSTANCES),
        )
        .map(|f| f.block.count > 0)
        .unwrap_or(false);
        if has_phys {
            phys += s;
            n_phys += 1;
        }
    }
    println!(
        "{} instances: surfaces over all {all}, over the {n_phys} with physics {phys}; edges over all {tris_all}; {} distinct definitions, their own surfaces {}",
        inst.block.count,
        surf_by_def.len(),
        surf_by_def.values().map(|v| v.0).sum::<usize>()
    );
}
