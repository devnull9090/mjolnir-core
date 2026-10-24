//! Summarise a Halo Reach map variant (`.mvar`) through the grammar codec:
//! its title, map, world bounds, labels, palette quotas and placed objects,
//! with each object's position decoded back to world units.
//!
//!   cargo run -p blam-megalo --example mvar_summary -- <file.mvar> [objects to list]
use blam_megalo::blf;
use blam_megalo::raw::{self, field, int, position_widths, Node, Value};

fn f32_of(fields: &[Node], name: &str) -> f32 {
    match field(fields, name).map(|n| &n.value) {
        Some(Value::F32(b)) => f32::from_bits(*b),
        _ => f32::NAN,
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let path = args.next().expect("usage: mvar_summary <file.mvar> [n]");
    let list: usize = args.next().and_then(|s| s.parse().ok()).unwrap_or(5);
    let bytes = std::fs::read(&path)?;
    let mv = blf::map_variant(&bytes)?;
    let tree = raw::decode_map_variant(mv.payload)?;
    let top = &tree.fields;
    let header = field(top, "header")
        .map(|n| n.value.fields())
        .unwrap_or(&[]);
    println!("{path}");
    println!(
        "  title {:?}  description {:?}",
        field(header, "title")
            .and_then(|n| n.value.text())
            .unwrap_or_default(),
        field(header, "description")
            .and_then(|n| n.value.text())
            .unwrap_or_default()
    );
    println!(
        "  content type {:?}  game mode {:?}  version {:?}  map id {:?}",
        int(header, "content_type"),
        int(header, "game_mode"),
        int(top, "encoding_version"),
        int(top, "map_id")
    );
    let names = ["x_min", "x_max", "y_min", "y_max", "z_min", "z_max"];
    let b: Vec<f32> = names.iter().map(|n| f32_of(top, n)).collect();
    let bounds = [b[0], b[1], b[2], b[3], b[4], b[5]];
    let widths = position_widths(21, bounds);
    println!(
        "  bounds x {:.2}..{:.2} y {:.2}..{:.2} z {:.2}..{:.2}  position bits {widths:?}",
        b[0], b[1], b[2], b[3], b[4], b[5]
    );
    println!(
        "  labels {:?}  label strings {:?} bytes  quotas {:?}",
        int(top, "label_count"),
        int(top, "strings_size"),
        int(top, "quota_count")
    );
    let objects = field(top, "objects")
        .map(|n| n.value.items())
        .unwrap_or(&[]);
    let placed: Vec<&Vec<Node>> = objects
        .iter()
        .filter(|o| int(o, "present") == Some(1))
        .collect();
    println!("  objects placed {} of {}", placed.len(), objects.len());
    let mut outside = 0;
    for (k, o) in placed.iter().enumerate() {
        let p = field(o, "position")
            .map(|n| n.value.fields())
            .unwrap_or(&[]);
        let axis = |i: usize, name: &str| {
            let raw = int(p, name).unwrap_or(0) as f32;
            let (lo, hi) = (bounds[2 * i], bounds[2 * i + 1]);
            (hi - lo) / (1u64 << widths[i]) as f32 * (raw + 0.5) + lo
        };
        let (x, y, z) = (axis(0, "x"), axis(1, "y"), axis(2, "z"));
        if !(b[0]..=b[1]).contains(&x) || !(b[2]..=b[3]).contains(&y) || !(b[4]..=b[5]).contains(&z)
        {
            outside += 1;
        }
        if k < list {
            let props = field(o, "properties")
                .map(|n| n.value.fields())
                .unwrap_or(&[]);
            println!(
                "    palette {:?} variant {:?} at ({x:.2}, {y:.2}, {z:.2}) yaw {:?} type {:?} team {:?} label {:?} respawn {:?}",
                int(o, "palette_entry"),
                int(o, "variant"),
                int(o, "yaw"),
                int(props, "object_type"),
                int(props, "team"),
                int(props, "label"),
                int(props, "respawn_time")
            );
        }
    }
    println!("  objects outside the bounds: {outside}");
    Ok(())
}
