//! Instances whose xy bounds contain a point, with their frame and whether
//! they carry a Havok physics shape.
//!
//!   cargo run -p blam-sbsp --example inst_physics -- <payload> <x> <y>
use blam_tag::blockedit::find_block;

fn f32_at(b: &[u8], o: usize) -> f32 {
    f32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let (px, py): (f32, f32) = (args[1].parse().unwrap(), args[2].parse().unwrap());
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let inst = find_block(&layout, &file, &root, "instanced geometry instances").expect("instances");
    for i in 0..inst.block.count as usize {
        let b = inst.block.element(i).unwrap();
        let (x0, x1, y0, y1, z0, z1) = (
            f32_at(b, 76), f32_at(b, 80), f32_at(b, 84),
            f32_at(b, 88), f32_at(b, 92), f32_at(b, 96),
        );
        if !(x0 <= px && px <= x1 && y0 <= py && py <= y1) {
            continue;
        }
        let scale = f32_at(b, 0);
        let f = [f32_at(b, 4), f32_at(b, 8), f32_at(b, 12)];
        let l = [f32_at(b, 16), f32_at(b, 20), f32_at(b, 24)];
        let u = [f32_at(b, 28), f32_at(b, 32), f32_at(b, 36)];
        let identity = (f[0] - 1.0).abs() < 0.001
            && f[1].abs() < 0.001
            && l[1] - 1.0 < 0.001
            && l[0].abs() < 0.001
            && (u[2] - 1.0).abs() < 0.001;
        let def = i16::from_le_bytes([b[52], b[53]]);
        let phys = find_block(
            &layout,
            &file,
            &root,
            &format!("instanced geometry instances[{i}].physics"),
        )
        .map(|f| f.block.count)
        .unwrap_or(0);
        println!(
            "[{i:>4}] def {def:>4} scale {scale:.4} identity {identity:<5} physics {phys} z[{z0:.2},{z1:.2}] pos ({:.2},{:.2},{:.2})",
            f32_at(b, 40), f32_at(b, 44), f32_at(b, 48)
        );
    }
}
