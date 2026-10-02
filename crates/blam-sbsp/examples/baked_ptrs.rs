//! Find every int64 field named like a pointer, and test whether its value
//! minus a common base equals the file offset of some nested block's bytes.
//!
//!   cargo run -p blam-sbsp --example baked_ptrs -- <payload> <base>
use blam_tag::blockedit::find_block;
use blam_tag::Value;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let base: i64 = args[1].parse().expect("base");
    let fp = file.as_ptr() as usize;
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");

    // Every nested block's element bytes, by file offset.
    let mut block_offsets: Vec<(usize, usize, String)> = Vec::new();
    fn walk(v: &Value<'_>, fp: usize, path: &str, out: &mut Vec<(usize, usize, String)>) {
        match v {
            Value::Block(b) => {
                if !b.elements.is_empty() {
                    out.push((b.elements.as_ptr() as usize - fp, b.elements.len(), path.to_string()));
                }
                for (i, kids) in b.children.iter().enumerate() {
                    for k in kids { walk(k, fp, &format!("{path}[{i}]"), out); }
                }
            }
            Value::Struct { children } | Value::Array { children } => {
                for k in children { walk(k, fp, path, out); }
            }
            Value::Data(d) => out.push((d.as_ptr() as usize - fp, d.len(), format!("{path}<data>"))),
            _ => {}
        }
    }
    for kids in &root.children {
        for k in kids { walk(k, fp, "root", &mut block_offsets); }
    }
    block_offsets.sort();
    println!("{} nested byte regions", block_offsets.len());

    for name in ["structure_physics.mopp code block", "cluster to instance group mopps", "instance group to instance mopps"] {
        let Ok(f) = find_block(&layout, &file, &root, name) else { println!("{name}: n/a"); continue };
        for i in 0..f.block.count.min(3) as usize {
            let e = f.block.element(i).unwrap();
            // mopp_code_definition: m_data pointer at +48 in the mopp block; structure_physics wraps one
            let scan = e.len();
            let mut hits = Vec::new();
            let raw: Vec<String> = [0usize, 8, 48, 56, 60].iter().filter(|&&o| o + 8 <= e.len()).map(|&o| format!("+{o}={}", i64::from_le_bytes(e[o..o + 8].try_into().unwrap()))).collect();
            hits.push(format!("raw {}", raw.join(" ")));
            for o in (0..scan.saturating_sub(8)).step_by(8) {
                let v = i64::from_le_bytes(e[o..o + 8].try_into().unwrap());
                let off = (v as i128) - (base as i128);
                if off > 0 && off < file.len() as i128 {
                    let off = off as i64;
                    let near = block_offsets.iter().find(|(bo, _, _)| *bo == off as usize);
                    hits.push(format!("+{o}: {v} -> offset {off}{}", near.map(|(_, n, p)| format!(" = {p} ({n} B)")).unwrap_or_default()));
                }
            }
            // The element's own nested block bytes (the mopp bytecode), by walking its children.
            let mut mine: Vec<(usize, usize, String)> = Vec::new();
            for k in &f.block.children[i] { walk(k, fp, name, &mut mine); }
            let p48 = i64::from_le_bytes(e[48..56].try_into().unwrap());
            let mopp = mine.iter().max_by_key(|(_, n, _)| *n);
            match mopp {
                Some((off, n, _)) => println!("{name}[{i}]: m_data {p48}; bytecode at file offset {off} ({n} B); m_data - offset = {}", p48 as i128 - *off as i128),
                None => println!("{name}[{i}]: m_data {p48}; no nested bytes"),
            }
            let _ = hits;
        }
    }
}
