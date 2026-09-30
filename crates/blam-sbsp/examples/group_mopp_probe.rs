//! Decode an instance-group MOPP: what its terminals mean and what box it
//! covers, so the group broadphase can be recompiled after a transplant.
//!   cargo run -p blam-sbsp --example group_mopp_probe -- <payload> <group>...
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
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let path = match a.iter().position(|x| x == "--path") {
        Some(i) => a[i + 1].clone(),
        None => "instance group to instance mopps".to_string(),
    };
    for g in a[1..].iter().filter(|x| x.parse::<usize>().is_ok()) {
        let g: usize = g.parse().unwrap();
        let m = find_block(&layout, &file, &root, &path).expect("mopps");
        let mut code = Vec::new();
        for v in &m.block.children[g] { bytecode(v, &mut code); }
        let e = m.block.element(g).expect("element");
        let f = |o: usize| f32::from_le_bytes(e[o..o + 4].try_into().unwrap());
        let member_path = if path.starts_with("cluster") {
            format!("cluster to instance group spheres[{g}].instance group indices")
        } else {
            format!("instance group to instance spheres[{g}].instance indices")
        };
        let ids: Vec<u16> = match find_block(&layout, &file, &root, &member_path) {
            Ok(members) => (0..members.block.count as usize)
                .map(|k| { let b = members.block.element(k).unwrap(); u16::from_le_bytes([b[0], b[1]]) })
                .collect(),
            Err(_) => Vec::new(),
        };
        println!("{path}[{g}]: {} code byte(s), {} member(s) {:?}", code.len(), ids.len(),
            &ids[..ids.len().min(16)]);
        println!("  code info ({:.3}, {:.3}, {:.3}) w {:.1}, size word {}",
            f(32), f(36), f(40), f(44), i32::from_le_bytes(e[56..60].try_into().unwrap()));
        let mut kinds: std::collections::BTreeMap<String, usize> = Default::default();
        let mut first = Vec::new();
        mopp::walk(&code, 0, &mut |d, depth| {
            let k = match &d.node {
                mopp::Node::Split { .. } => "split",
                mopp::Node::Terminal(_) => "terminal",
                mopp::Node::Rescale { .. } => "rescale",
                mopp::Node::Reindex(_) => "reindex",
                mopp::Node::Jump(_) => "jump",
                mopp::Node::Clip { .. } => "clip",
                mopp::Node::Diagonal { .. } => "diagonal",
                mopp::Node::Property { .. } => "property",
                mopp::Node::Chunk(_) => "chunk",
                mopp::Node::Return => "return",
            };
            *kinds.entry(k.to_string()).or_default() += 1;
            if first.len() < 14 { first.push(format!("{:?}@{}", d.node, depth)); }
        }).ok();
        println!("  node kinds {kinds:?}");
        for n in &first { println!("    {n}"); }
        match mopp::terminals(&code) {
            Ok(t) => {
                let mut v: Vec<u32> = t.iter().map(|(i, _)| *i).collect();
                v.sort_unstable();
                println!("  terminals {v:?}");
            }
            Err(err) => println!("  decode failed: {err}"),
        }
    }
}
