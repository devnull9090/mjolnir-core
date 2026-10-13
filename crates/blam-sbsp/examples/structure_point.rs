//! What `structure_physics` answers for a pawn-sized box at a point: how many
//! keys, of which types, and whether a given instance's whole-instance key is
//! among them (and where in the order).
//!   cargo run -p blam-sbsp --example structure_point -- <payload> <instance> <x> <y> <z> [...]
use blam_sbsp::mopp;
use blam_tag::blockedit::find_block;

fn bytecode(v: &blam_tag::Value<'_>, out: &mut Vec<u8>) {
    match v {
        blam_tag::Value::Block(b) => {
            if b.elements.len() > out.len() { *out = b.elements.to_vec(); }
            for kids in &b.children { for k in kids { bytecode(k, out); } }
        }
        blam_tag::Value::Struct { children } | blam_tag::Value::Array { children } => {
            for k in children { bytecode(k, out); }
        }
        _ => {}
    }
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let want: u32 = a[1].parse().unwrap();
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let m = find_block(&layout, &file, &root, "structure_physics.mopp code block").expect("mopp");
    let e = m.block.elements;
    let f = |at: usize| f32::from_le_bytes(e[at..at + 4].try_into().unwrap());
    let q = mopp::Quant { offset: [f(32), f(36), f(40)], scale: f(44) };
    let mut code = Vec::new();
    for v in &m.block.children[0] { bytecode(v, &mut code); }
    println!("code {} B, offset {:?}, one byte = {:.2} wu", code.len(), q.offset, 65536.0 / q.scale);
    let v: Vec<f32> = a[2..].iter().map(|s| s.parse().unwrap()).collect();
    for p in v.chunks(3) {
        let lo = [p[0] - 0.3, p[1] - 0.3, p[2] - 0.5];
        let hi = [p[0] + 0.3, p[1] + 0.3, p[2] + 2.0];
        let keys = mopp::query(&code, &q.query_box(lo, hi)).expect("query");
        let mut types = [0usize; 8];
        for k in &keys { types[(k >> 29) as usize] += 1; }
        let at = keys.iter().position(|&k| k >> 29 == 2 && (k & 0xffff) == want);
        println!("({:.2}, {:.2}, {:.2}): {} key(s), shell {} instance {} surface {}; instance {want} key at {:?}",
            p[0], p[1], p[2], keys.len(), types[1], types[2], types[3], at);
    }
}
