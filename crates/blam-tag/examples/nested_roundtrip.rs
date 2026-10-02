//! Prove `blockedit::replace_nested` is the identity when handed a block's own
//! elements back, on a real `scenario_structure_bsp` payload.
//!
//! ```text
//! cargo run -p blam-tag --example nested_roundtrip -- <sbsp.ubulk payload>
//! ```
//!
//! Replaces every block of the world shell's collision BSP with its current
//! content (wrappers cloned per element) and requires the rebuilt file to be
//! byte-identical. Also exercises a real resize: truncating `vertices` to one
//! element must shrink the file by exactly `(count - 1) * element_size` bytes
//! and leave the inline count reading `1`.

use blam_tag::blockedit::{element_with_wrapper, find_block, replace_nested, NestedReplace};

const SHELL: &str = "resource interface.raw_resources[0].raw_items.collision bsp[0]";
const BLOCKS: [&str; 9] = [
    "bsp3d nodes",
    "bsp3d supernodes",
    "planes",
    "leaves",
    "bsp2d references",
    "bsp2d nodes",
    "surfaces",
    "edges",
    "vertices",
];

fn main() {
    let path = std::env::args().nth(1).expect("payload path");
    let file = std::fs::read(&path).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");

    let mut replacements = Vec::new();
    let mut root_paths = vec![
        "leaves".to_string(),
        "edge to seam edge".to_string(),
        "collision materials".to_string(),
        "materials".to_string(),
        "instanced geometry instances".to_string(),
    ];
    for b in BLOCKS {
        root_paths.push(format!("{SHELL}.{b}"));
    }
    for p in &root_paths {
        let found = find_block(&layout, &file, &root, p).unwrap_or_else(|e| panic!("{p}: {e}"));
        let block = found.block;
        let mut wrappers = Vec::new();
        for i in 0..block.count as usize {
            let (_, w) = element_with_wrapper(&file, p, i).expect("element");
            wrappers.push(w);
        }
        println!(
            "{p}: {} element(s) x {} B, flags {}, count inline at 0x{:x}",
            block.count, block.element_size, block.flags, found.count_at
        );
        replacements.push(NestedReplace {
            path: p.clone(),
            count: block.count,
            elements: block.elements.to_vec(),
            wrappers: if block.flags == 0 {
                Some(wrappers)
            } else {
                None
            },
        });
    }
    let out = replace_nested(&file, &replacements).expect("replace");
    assert_eq!(out.len(), file.len(), "identity replace changed the length");
    assert!(out == file, "identity replace changed bytes");
    println!(
        "identity: {} blocks re-emitted, byte-exact",
        replacements.len()
    );

    // A real resize: keep one vertex.
    let vp = format!("{SHELL}.vertices");
    let found = find_block(&layout, &file, &root, &vp).unwrap();
    let count = found.block.count;
    let size = found.block.element_size as usize;
    let one = NestedReplace {
        path: vp.clone(),
        count: 1,
        elements: found.block.element(0).unwrap().to_vec(),
        wrappers: None,
    };
    let shrunk = replace_nested(&file, &[one]).expect("shrink");
    let expect = file.len() - (count as usize - 1) * size;
    assert_eq!(shrunk.len(), expect, "shrink size");
    let tag2 = blam_tag::TagFile::parse(&shrunk, None).expect("parse shrunk");
    let layout2 = tag2.layout().unwrap();
    let root2 = tag2.read_data(&layout2).expect("walk shrunk");
    let payload = tag2.data().expect("bdat");
    assert_eq!(
        root2.consumed, payload.size as usize,
        "shrunk tag walks exactly"
    );
    let f2 = find_block(&layout2, &shrunk, &root2, &vp).unwrap();
    assert_eq!(f2.block.count, 1);
    let inline = u32::from_le_bytes(shrunk[f2.count_at..f2.count_at + 4].try_into().unwrap());
    assert_eq!(inline, 1, "inline count fixed");
    println!(
        "resize: vertices {count} -> 1, file {} -> {} B, walks exactly",
        file.len(),
        shrunk.len()
    );
}
