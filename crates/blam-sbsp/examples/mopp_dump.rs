//! Hex-dump one instance-group mopp: header scalars and bytecode.
//!
//!   cargo run -p blam-sbsp --example mopp_dump -- <payload> <group>
use blam_tag::blockedit::find_block;

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let g: usize = a[1].parse().expect("group");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let m = find_block(&layout, &file, &root, "instance group to instance mopps").expect("mopps");
    let e = m.block.element(g).expect("element");
    let f = |o: usize| f32::from_le_bytes(e[o..o + 4].try_into().unwrap());
    let i32_at = |o: usize| i32::from_le_bytes(e[o..o + 4].try_into().unwrap());
    println!("group {g}: size {} count {} v=({:.3}, {:.3}, {:.3}, w {:.6}) m_size {} buildType {}",
        u16::from_le_bytes([e[8], e[9]]), u16::from_le_bytes([e[10], e[11]]),
        f(32), f(36), f(40), f(44), i32_at(56), e[64] as i8);
    // The bytecode is a nested block whose layout name carries a trailing
    // space, which the path parser trims away; walk the element's children
    // instead and dump every block found there.
    fn dump_blocks(v: &blam_tag::Value<'_>, depth: usize) {
        match v {
            blam_tag::Value::Block(b) => {
                println!("{}block: {} element(s), {} byte(s)", "  ".repeat(depth), b.count, b.elements.len());
                for (i, chunk) in b.elements.chunks(16).enumerate() {
                    let hex: Vec<String> = chunk.iter().map(|x| format!("{x:02x}")).collect();
                    println!("{}  {:04x}: {}", "  ".repeat(depth), i * 16, hex.join(" "));
                }
                for kids in &b.children {
                    for k in kids {
                        dump_blocks(k, depth + 1);
                    }
                }
            }
            blam_tag::Value::Struct { children } | blam_tag::Value::Array { children } => {
                for k in children {
                    dump_blocks(k, depth + 1);
                }
            }
            _ => {}
        }
    }
    for v in &m.block.children[g] {
        dump_blocks(v, 1);
    }
    let members = find_block(&layout, &file, &root, &format!("instance group to instance spheres[{g}].instance indices")).expect("members");
    let ids: Vec<u16> = (0..members.block.count as usize).map(|k| { let b = members.block.element(k).unwrap(); u16::from_le_bytes([b[0], b[1]]) }).collect();
    println!("members: {ids:?}");
}
