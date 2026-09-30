//! `cargo run -p blam-sbsp --example list_instances -- <sbsp payload> [x y]` —
//! every instanced-geometry instance with its definition, transform, bounds
//! and name; with `x y`, only those whose xy bounds contain the point, sorted
//! by top z.

use blam_tag::blockedit::find_block;

fn f32_at(b: &[u8], o: usize) -> f32 {
    f32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}
fn i16_at(b: &[u8], o: usize) -> i16 {
    i16::from_le_bytes([b[o], b[o + 1]])
}
fn u16_at(b: &[u8], o: usize) -> u16 {
    u16::from_le_bytes([b[o], b[o + 1]])
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let at: Option<(f32, f32)> = if args.len() >= 3 {
        Some((args[1].parse().unwrap(), args[2].parse().unwrap()))
    } else {
        None
    };
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let found =
        find_block(&layout, &file, &root, "instanced geometry instances").expect("instances");
    let block = found.block;
    let mut rows = Vec::new();
    for i in 0..block.count as usize {
        let b = block.element(i).unwrap();
        let scale = f32_at(b, 0);
        let fwd = [f32_at(b, 4), f32_at(b, 8), f32_at(b, 12)];
        let left = [f32_at(b, 16), f32_at(b, 20), f32_at(b, 24)];
        let up = [f32_at(b, 28), f32_at(b, 32), f32_at(b, 36)];
        let pos = [f32_at(b, 40), f32_at(b, 44), f32_at(b, 48)];
        let def = i16_at(b, 52);
        let flags = u16_at(b, 54);
        let bounds = [
            f32_at(b, 76),
            f32_at(b, 80),
            f32_at(b, 84),
            f32_at(b, 88),
            f32_at(b, 92),
            f32_at(b, 96),
        ];
        let name = block
            .children
            .get(i)
            .and_then(|c| c.iter().find_map(|v| v.as_str()))
            .unwrap_or("")
            .to_string();
        if let Some((x, y)) = at {
            if !(bounds[0] - 0.5 <= x
                && x <= bounds[1] + 0.5
                && bounds[2] - 0.5 <= y
                && y <= bounds[3] + 0.5)
            {
                continue;
            }
        }
        rows.push((
            bounds[5], i, def, scale, fwd, left, up, pos, flags, bounds, name,
        ));
    }
    rows.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap());
    for (_, i, def, scale, fwd, left, up, pos, flags, bounds, name) in rows {
        println!(
            "[{i}] def {def} flags {flags:#x} scale {scale:.4} pos ({:.2},{:.2},{:.2}) f({:.2},{:.2},{:.2}) l({:.2},{:.2},{:.2}) u({:.2},{:.2},{:.2}) bounds x[{:.2},{:.2}] y[{:.2},{:.2}] z[{:.2},{:.2}] {name}",
            pos[0], pos[1], pos[2], fwd[0], fwd[1], fwd[2], left[0], left[1], left[2], up[0], up[1], up[2],
            bounds[0], bounds[1], bounds[2], bounds[3], bounds[4], bounds[5]
        );
    }
}
