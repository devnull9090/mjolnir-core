//! Scan definition and instance elements for baked pointers: int64 values
//! whose (value - base) lands exactly on a nested block's bytes.
//!
//!   cargo run -p blam-sbsp --example baked_scan -- <payload> <base> [def index] [instance index]
use blam_tag::blockedit::find_block;
use blam_tag::Value;
use std::collections::BTreeMap;

fn walk(v: &Value<'_>, fp: usize, path: &str, out: &mut BTreeMap<usize, (usize, String)>) {
    match v {
        Value::Block(b) => {
            if !b.elements.is_empty() {
                out.insert(b.elements.as_ptr() as usize - fp, (b.elements.len(), path.to_string()));
            }
            for (i, kids) in b.children.iter().enumerate() {
                for k in kids { walk(k, fp, &format!("{path}[{i}]"), out); }
            }
        }
        Value::Struct { children } | Value::Array { children } => { for k in children { walk(k, fp, path, out); } }
        Value::Data(d) => { out.insert(d.as_ptr() as usize - fp, (d.len(), format!("{path}<data>"))); }
        _ => {}
    }
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let base: i128 = args[1].parse().expect("base");
    let want_def: Option<usize> = args.get(2).map(|s| s.parse().unwrap());
    let want_inst: Option<usize> = args.get(3).map(|s| s.parse().unwrap());
    let fp = file.as_ptr() as usize;
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let mut regions = BTreeMap::new();
    for kids in &root.children { for k in kids { walk(k, fp, "root", &mut regions); } }
    // Also every element start of every block, so pointers to elements resolve.
    let mut elements: BTreeMap<usize, String> = BTreeMap::new();
    fn walk_elems(v: &Value<'_>, fp: usize, path: &str, out: &mut BTreeMap<usize, String>) {
        match v {
            Value::Block(b) => {
                let sz = if b.count > 0 { b.elements.len() / b.count as usize } else { 0 };
                for i in 0..b.count as usize {
                    out.insert(b.elements.as_ptr() as usize - fp + i * sz, format!("{path}[{i}]"));
                }
                for (i, kids) in b.children.iter().enumerate() { for k in kids { walk_elems(k, fp, &format!("{path}[{i}]"), out); } }
            }
            Value::Struct { children } | Value::Array { children } => { for k in children { walk_elems(k, fp, path, out); } }
            _ => {}
        }
    }
    for kids in &root.children { for k in kids { walk_elems(k, fp, "root", &mut elements); } }

    let scan = |label: &str, bytes: &[u8]| {
        for o in (0..bytes.len().saturating_sub(8)).step_by(4) {
            let v = i64::from_le_bytes(bytes[o..o + 8].try_into().unwrap()) as i128;
            let off = v - base;
            if off <= 0 || off >= file.len() as i128 { continue; }
            let off = off as usize;
            if let Some((n, p)) = regions.get(&off) {
                println!("  {label} +{o}: -> region {p} ({n} B) @ {off}");
            } else if let Some(p) = elements.get(&off) {
                println!("  {label} +{o}: -> element {p} @ {off}");
            }
        }
    };
    let defs = find_block(&layout, &file, &root, "resource interface.raw_resources[0].raw_items.instanced geometries definitions").expect("defs");
    let inst = find_block(&layout, &file, &root, "instanced geometry instances").expect("inst");
    let d = want_def.unwrap_or(159);
    println!("== definition {d} element ({} B)", defs.block.elements.len() / defs.block.count as usize);
    scan(&format!("def[{d}]"), defs.block.element(d).unwrap());
    let i = want_inst.unwrap_or(763);
    println!("== instance {i} element");
    scan(&format!("inst[{i}]"), inst.block.element(i).unwrap());
    if let Ok(sh) = find_block(&layout, &file, &root, &format!("instanced geometry instances[{i}].physics[0].collision geometry shape")) {
        println!("== instance {i} shape");
        scan(&format!("shape[{i}]"), sh.block.element(0).unwrap());
    }
    if let Ok(ph) = find_block(&layout, &file, &root, &format!("instanced geometry instances[{i}].physics")) {
        println!("== instance {i} physics element");
        scan(&format!("physics[{i}]"), ph.block.element(0).unwrap());
    }
}
