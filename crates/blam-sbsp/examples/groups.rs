//! Dump the instanced-geometry broadphase: cluster-to-group and
//! group-to-instance spheres, and which group holds a given instance.
//!
//!   cargo run -p blam-sbsp --example groups -- <payload> [instance index]
use blam_tag::blockedit::find_block;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let want: Option<usize> = args.get(1).map(|s| s.parse().expect("instance"));
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");

    for name in [
        "cluster to instance group spheres",
        "instance group to instance spheres",
        "cluster to instance group mopps",
        "instance group to instance mopps",
    ] {
        let f = find_block(&layout, &file, &root, name).expect(name);
        println!("== {name}: {} element(s)", f.block.count);
        let run = layout.struct_run(f.block.struct_index).expect("run");
        let range = layout.struct_ranges()[run].clone();
        let mut offset = 0u32;
        for i in range {
            let field = layout.fields[i];
            let fname = layout.string_at(field.name_offset).unwrap_or("?");
            let kind = layout.type_name_of(&field);
            let size = layout.field_size(&field).unwrap_or(0);
            println!("     +{offset:<4} {kind:<24} {fname}");
            offset += size;
        }
        if name == "instance group to instance spheres" {
            if let Some(w) = want {
                for i in 0..f.block.count as usize {
                    let members = find_block(&layout, &file, &root, &format!("{name}[{i}].instance indices"))
                        .expect("members");
                    let hit = (0..members.block.count as usize).any(|k| {
                        let e = members.block.element(k).unwrap();
                        u16::from_le_bytes([e[0], e[1]]) as usize == w
                    });
                    if hit {
                        let e = f.block.element(i).unwrap();
                        let fl = |o: usize| f32::from_le_bytes(e[o..o + 4].try_into().unwrap());
                        println!(
                            "     instance {w} is in group {i}: center ({:.2}, {:.2}, {:.2}) radius {:.2}, {} member(s)",
                            fl(0), fl(4), fl(8), fl(12), members.block.count
                        );
                    }
                }
            }
        }
        if name.ends_with("spheres") {
            for i in 0..f.block.count as usize {
                if i >= 3 {
                    break;
                }
                let e = f.block.element(i).unwrap();
                let words: Vec<String> = e
                    .chunks(4)
                    .take(8)
                    .map(|w| {
                        let v = u32::from_le_bytes(w.try_into().unwrap_or([0; 4]));
                        let fl = f32::from_le_bytes(w.try_into().unwrap_or([0; 4]));
                        if fl.is_finite() && fl.abs() > 1e-3 && fl.abs() < 1e6 {
                            format!("{fl:.2}")
                        } else {
                            format!("{v}")
                        }
                    })
                    .collect();
                println!("     [{i}] {}", words.join(" "));
            }
        }
    }
}
