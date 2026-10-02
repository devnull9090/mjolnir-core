//! Every pageable-resource section in a payload: kind, version, size, first
//! bytes, and any u32 inside the body that equals the file offset of a nested
//! block region (a fixup table would look like that).
//!
//!   cargo run -p blam-sbsp --example resource_sections -- <payload>
use blam_tag::Value;
use std::collections::BTreeMap;

fn regions(v: &Value<'_>, fp: usize, path: &str, out: &mut BTreeMap<usize, String>) {
    match v {
        Value::Block(b) => {
            if !b.elements.is_empty() { out.insert(b.elements.as_ptr() as usize - fp, path.to_string()); }
            for (i, kids) in b.children.iter().enumerate() { for k in kids { regions(k, fp, &format!("{path}[{i}]"), out); } }
        }
        Value::Struct { children } | Value::Array { children } => { for k in children { regions(k, fp, path, out); } }
        _ => {}
    }
}
fn find_res(v: &Value<'_>, fp: usize, path: &str, out: &mut Vec<(String, u8, u32, usize, usize)>) {
    match v {
        Value::Resource { kind, version, body } => out.push((path.to_string(), *kind, *version, body.as_ptr() as usize - fp, body.len())),
        Value::Block(b) => { for (i, kids) in b.children.iter().enumerate() { for k in kids { find_res(k, fp, &format!("{path}[{i}]"), out); } } }
        Value::Struct { children } | Value::Array { children } => { for k in children { find_res(k, fp, path, out); } }
        _ => {}
    }
}
fn main() {
    let path = std::env::args().nth(1).expect("payload");
    let file = std::fs::read(&path).expect("read");
    let fp = file.as_ptr() as usize;
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let mut regs = BTreeMap::new();
    let mut res = Vec::new();
    for kids in &root.children { for k in kids { regions(k, fp, "root", &mut regs); find_res(k, fp, "root", &mut res); } }
    println!("{} nested regions, {} resource section(s)", regs.len(), res.len());
    for (p, kind, version, off, len) in &res {
        let body = &file[*off..*off + *len];
        let head: Vec<String> = body.iter().take(48).map(|b| format!("{b:02x}")).collect();
        println!("== {p}: kind {:?} version {version} body @ {off} len {len}\n   {}", *kind as char, head.join(" "));
        let mut hits = 0;
        for o in (0..body.len().saturating_sub(4)).step_by(4) {
            let v = u32::from_le_bytes(body[o..o + 4].try_into().unwrap()) as usize;
            if let Some(r) = regs.get(&v) {
                if hits < 12 { println!("   body+{o}: {v} -> {r}"); }
                hits += 1;
            }
        }
        println!("   {hits} u32(s) equal to a nested-region file offset");
    }
}
