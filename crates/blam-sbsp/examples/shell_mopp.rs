//! Decode the world shell's Havok MOPP (`structure_physics.mopp code block`)
//! and compare its leaves with the shell's surface table.
//!
//!   cargo run -p blam-sbsp --example shell_mopp -- <payload>
//!
//! A definition's tree names each of its surfaces once; if the shell's does
//! the same, the shell's tree can be compiled the way `def_mopp` compiles a
//! definition's.
use blam_sbsp::{mopp, transplant};
use blam_tag::blockedit::find_block;

/// The bytecode lives in a nested block inside the mopp element's `tgst`
/// wrapper; walk the decoded value tree for the byte block.
fn bytecode(v: &blam_tag::Value<'_>, out: &mut Vec<u8>) {
    match v {
        blam_tag::Value::Block(b) => {
            if b.elements.len() > out.len() {
                *out = b.elements.to_vec();
            }
            for kids in &b.children {
                for k in kids {
                    bytecode(k, out);
                }
            }
        }
        blam_tag::Value::Struct { children } | blam_tag::Value::Array { children } => {
            for k in children {
                bytecode(k, out);
            }
        }
        _ => {}
    }
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let count = |p: &str| {
        find_block(&layout, &file, &root, p)
            .map(|f| f.block.count)
            .unwrap_or(0)
    };
    let shell = transplant::SHELL;
    println!(
        "shell: {} surface(s), {} leaves; large structure surfaces {}; structure surface to triangle mapping {}",
        count(&format!("{shell}.surfaces")),
        count(&format!("{shell}.leaves")),
        count("large structure surfaces"),
        count("structure surface to triangle mapping"),
    );
    let m = find_block(&layout, &file, &root, "structure_physics.mopp code block").expect("mopp");
    if m.block.count == 0 {
        println!("structure_physics mopp: none");
        return;
    }
    let mut code = Vec::new();
    for v in &m.block.children[0] {
        bytecode(v, &mut code);
    }
    let t = mopp::terminals(&code).expect("terminals");
    // How the keys split: count distinct values of the top bits at several widths.
    for shift in [16u32, 18, 20, 21, 22, 24] {
        let mut hi: Vec<u32> = t.iter().map(|(i, _)| i >> shift).collect();
        hi.sort_unstable();
        hi.dedup();
        println!(
            "  key >> {shift}: {} distinct, {:?}..{:?}",
            hi.len(),
            hi.first(),
            hi.last()
        );
    }
    // Keys by type (key >> 29), with the agent's field layouts checked.
    let mut by_type = std::collections::BTreeMap::<u32, (usize, u32, u32, u32)>::new();
    for (k, _) in &t {
        let e = by_type.entry(k >> 29).or_insert((0, 0, 0, u32::MAX));
        e.0 += 1;
        let (lo16, mid) = (k & 0xffff, (k >> 16) & 0x1fff);
        e.1 = e.1.max(lo16);
        e.2 = e.2.max(mid);
        e.3 = e.3.min(k & 0x3ff_ffff);
    }
    for (ty, (n, max_lo16, max_mid13, min_low26)) in &by_type {
        println!("  type {ty}: {n} keys, max low16 {max_lo16}, max bits16..28 {max_mid13}, min low26 {min_low26}");
    }
    let mut sample: Vec<u32> = t.iter().map(|(i, _)| *i).collect();
    sample.sort_unstable();
    println!("  first keys {:x?}", &sample[..12]);
    let mut ids: Vec<u32> = t.iter().map(|(i, _)| *i).collect();
    ids.sort_unstable();
    let n = ids.len();
    ids.dedup();
    println!(
        "structure_physics mopp: {} code byte(s), {} terminal(s), {} unique, ids {:?}..{:?}",
        code.len(),
        n,
        ids.len(),
        ids.first(),
        ids.last()
    );
}
