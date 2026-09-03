//! Raise (or lower) the collision geometry of the instance definitions behind
//! a set of instances, in the tag alone.
//!
//! ```text
//! cargo run -p blam-sbsp --example shift_defs -- <in.ubulk> <out.ubulk> <dz world units> <instance index>...
//! ```
//!
//! For every listed instance: its definition's `collision info` vertices and
//! planes move by `dz` along world up expressed in the instance's local frame
//! (`(f.z, l.z, u.z) * dz / scale`), and the instance's own bounds z and
//! bounding-sphere centre move by `dz`. A probe: if the pawn stands `dz`
//! higher afterwards, the simulation builds walkable collision from these
//! tables at load; if not, it comes from somewhere baked.

use std::collections::BTreeMap;

use blam_sbsp::transplant::set_scalar;
use blam_tag::blockedit::{find_block, replace_nested, NestedReplace};

const DEFS: &str = "resource interface.raw_resources[0].raw_items.instanced geometries definitions";

fn f32_at(b: &[u8], o: usize) -> f32 {
    f32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let dz: f32 = args[2].parse().unwrap();
    let instances: Vec<usize> = args[3..].iter().map(|s| s.parse().unwrap()).collect();

    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let inst =
        find_block(&layout, &file, &root, "instanced geometry instances").expect("instances");

    // definition index -> local delta (from the first instance that uses it).
    let mut local: BTreeMap<usize, [f32; 3]> = BTreeMap::new();
    let mut scalar_edits: Vec<(String, String)> = Vec::new();
    for &i in &instances {
        let b = inst.block.element(i).expect("instance");
        let scale = f32_at(b, 0);
        let fz = f32_at(b, 12);
        let lz = f32_at(b, 24);
        let uz = f32_at(b, 36);
        let def = i16::from_le_bytes([b[52], b[53]]) as usize;
        local
            .entry(def)
            .or_insert([fz * dz / scale, lz * dz / scale, uz * dz / scale]);
        let z0 = f32_at(b, 92) + dz;
        let z1 = f32_at(b, 96) + dz;
        let cz = f32_at(b, 108) + dz;
        let cx = f32_at(b, 100);
        let cy = f32_at(b, 104);
        let p = format!("instanced geometry instances[{i}]");
        scalar_edits.push((format!("{p}.bounds z0"), format!("{z0}")));
        scalar_edits.push((format!("{p}.bounds z1"), format!("{z1}")));
        scalar_edits.push((
            format!("{p}.world bounding sphere center"),
            format!("({cx}, {cy}, {cz})"),
        ));
        println!("instance {i}: def {def} scale {scale:.4} up.z {uz:.3}");
    }

    let mut edits = Vec::new();
    for (def, d) in &local {
        let vp = format!("{DEFS}[{def}].collision info.vertices");
        let pp = format!("{DEFS}[{def}].collision info.planes");
        let v = find_block(&layout, &file, &root, &vp).unwrap_or_else(|e| panic!("{vp}: {e}"));
        let mut vb = v.block.elements.to_vec();
        for e in vb.chunks_exact_mut(16) {
            for a in 0..3 {
                let x = f32_at(e, a * 4) + d[a];
                e[a * 4..a * 4 + 4].copy_from_slice(&x.to_le_bytes());
            }
        }
        let p = find_block(&layout, &file, &root, &pp).unwrap_or_else(|e| panic!("{pp}: {e}"));
        let mut pb = p.block.elements.to_vec();
        for e in pb.chunks_exact_mut(16) {
            let n = [f32_at(e, 0), f32_at(e, 4), f32_at(e, 8)];
            let dd = f32_at(e, 12) + n[0] * d[0] + n[1] * d[1] + n[2] * d[2];
            e[12..16].copy_from_slice(&dd.to_le_bytes());
        }
        println!(
            "definition {def}: {} vertices, {} planes moved by local ({:.3}, {:.3}, {:.3})",
            v.block.count, p.block.count, d[0], d[1], d[2]
        );
        edits.push(NestedReplace {
            path: vp,
            count: v.block.count,
            elements: vb,
            wrappers: None,
        });
        edits.push(NestedReplace {
            path: pp,
            count: p.block.count,
            elements: pb,
            wrappers: None,
        });
    }
    let mut out = replace_nested(&file, &edits).expect("replace");
    for (path, value) in &scalar_edits {
        out = set_scalar(&out, path, value).unwrap_or_else(|e| panic!("{path}: {e}"));
    }
    let tag2 = blam_tag::TagFile::parse(&out, None).expect("parse out");
    let l2 = tag2.layout().unwrap();
    let r2 = tag2.read_data(&l2).expect("walk");
    assert_eq!(r2.consumed, tag2.data().unwrap().size as usize);
    std::fs::write(&args[1], &out).expect("write");
    println!("wrote {} ({} -> {} bytes)", args[1], file.len(), out.len());
}
