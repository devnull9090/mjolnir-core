//! Print how an sbsp payload carries breakable surfaces: the root's sets,
//! each geometry material's breakable surface index, the structure physics'
//! key table and breakable MOPP, and for every instance the key table names,
//! its definition's sets and the definition surfaces naming a set.
//!
//!   cargo run -p blam-sbsp --example breakable_probe -- <sbsp payload>
use blam_tag::blockedit::find_block;
use std::collections::BTreeSet;

const DEFS: &str = "resource interface.raw_resources[0].raw_items.instanced geometries definitions";

fn i16_at(b: &[u8], o: usize) -> i16 {
    i16::from_le_bytes([b[o], b[o + 1]])
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let block = |path: &str| find_block(&layout, &file, &root, path).ok();
    let count = |path: &str| block(path).map(|f| f.block.count).unwrap_or(0);

    if std::env::var("MOPP").is_ok() {
        mopp_keys(&file);
        return;
    }
    println!("root breakable surface sets: {}", count("breakable surface sets"));
    if let Some(m) = block("materials") {
        let n = m.block.count as usize;
        let size = if n > 0 { m.block.elements.len() / n } else { 0 };
        for i in 0..n {
            let e = &m.block.elements[i * size..(i + 1) * size];
            // breakable surface index: char at +16.
            let b = e[16] as i8;
            if b >= 0 {
                println!("  material {i}: breakable surface index {b} (element {size} bytes)");
            }
        }
    }
    let keys = block("structure_physics.breakable surfaace key table");
    let mut instances = BTreeSet::new();
    if let Some(k) = &keys {
        let n = k.block.count as usize;
        println!("key table: {n} entries");
        for i in 0..n {
            let e = &k.block.elements[i * 32..(i + 1) * 32];
            instances.insert(i16_at(e, 0));
            if i < 4 || i + 2 > n {
                let seed = i32::from_le_bytes(e[4..8].try_into().unwrap());
                println!("  [{i}] instance {} set {} index {} seed {seed}", i16_at(e, 0), e[2], e[3]);
            }
        }
    }
    println!("breakable mopp blocks: {}", count("structure_physics.breakable surfaces mopp code block"));
    if let Some(m) = block("structure_physics.breakable surfaces mopp code block[0].mopp data block") {
        println!("  mopp bytes: {}", m.block.count);
    }
    let inst = block("instanced geometry instances").expect("instances");
    let isize = inst.block.elements.len() / inst.block.count.max(1) as usize;
    for i in instances {
        let e = &inst.block.elements[i as usize * isize..(i as usize + 1) * isize];
        // instance definition: short at +0x30 in the shipped layout? Print the
        // candidates around it so the field can be pinned.
        println!("instance {i}: element {isize} bytes, head {:02x?}", &e[..0x40.min(isize)]);
        let def = block(&format!("instanced geometry instances[{i}].instance definition"));
        let _ = def;
    }
    let defs = block(DEFS).expect("definitions");
    for d in 0..defs.block.count as usize {
        let sets = count(&format!("{DEFS}[{d}].breakable surface sets"));
        let surfs = block(&format!("{DEFS}[{d}].collision info.surfaces"));
        let mut named = 0;
        let mut sample = Vec::new();
        if let Some(s) = &surfs {
            let n = s.block.count as usize;
            let size = if n > 0 { s.block.elements.len() / n } else { 0 };
            for j in 0..n {
                let e = &s.block.elements[j * size..(j + 1) * size];
                let (set, idx) = (i16_at(e, 6), i16_at(e, 8));
                if set >= 0 || idx >= 0 {
                    named += 1;
                    if sample.len() < 4 || std::env::var("ALL").is_ok() {
                        sample.push((j, set, idx, u16::from_le_bytes([e[10], e[11]])));
                    }
                }
            }
        }
        if sets > 0 || named > 0 {
            println!("definition {d}: {sets} set(s), {named} surface(s) naming one, e.g. (surface, set, index, flags) {sample:?}");
            if let Some(b) = block(&format!("{DEFS}[{d}].breakable surface sets")) {
                for k in 0..b.block.count as usize {
                    println!("  set {k}: {:02x?}", &b.block.elements[k * 32..(k + 1) * 32]);
                }
            }
        }
    }
}

/// The breakable MOPP's terminal keys, for `MOPP=1`.
#[allow(dead_code)]
fn mopp_keys(file: &[u8]) {
    let tag = blam_tag::TagFile::parse(file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let m = find_block(&layout, file, &root, "structure_physics.breakable surfaces mopp code block").expect("mopp");
    let mut code: Vec<u8> = Vec::new();
    for v in &m.block.children[0] {
        bytecode(v, &mut code);
    }
    let t = blam_sbsp::mopp::terminals(&code).expect("terminals");
    let keys: Vec<u32> = t.iter().map(|(k, _)| *k).collect();
    println!("breakable mopp: {} terminal(s), first {:x?}, last {:x?}", keys.len(), &keys[..keys.len().min(8)], &keys[keys.len().saturating_sub(4)..]);
    let hdr = find_block(&layout, file, &root, "structure_physics.breakable surfaces mopp code block").expect("hdr");
    println!("  header element ({} bytes): {:02x?}", hdr.block.elements.len(), &hdr.block.elements[..hdr.block.elements.len().min(64)]);
}

fn bytecode(v: &blam_tag::data::Value<'_>, out: &mut Vec<u8>) {
    match v {
        blam_tag::data::Value::Block(b) => {
            if b.elements.len() > out.len() {
                *out = b.elements.to_vec();
            }
            for kids in &b.children {
                for k in kids {
                    bytecode(k, out);
                }
            }
        }
        blam_tag::data::Value::Struct { children } | blam_tag::data::Value::Array { children } => {
            for k in children {
                bytecode(k, out);
            }
        }
        _ => {}
    }
}
