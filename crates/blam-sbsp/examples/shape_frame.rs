//! Is an instance's Havok shape box in definition-local or world space?
//! Compare it against the definition's vertex bounds, raw and transformed.
//!
//!   cargo run -p blam-sbsp --example shape_frame -- <payload> <instance>...
use blam_sbsp::transplant;
use blam_tag::blockedit::find_block;

fn f32_at(b: &[u8], o: usize) -> f32 { f32::from_le_bytes(b[o..o + 4].try_into().unwrap()) }

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let inst = find_block(&layout, &file, &root, "instanced geometry instances").expect("instances");
    for a in &args[1..] {
        let i: usize = a.parse().unwrap();
        let b = inst.block.element(i).unwrap();
        let scale = f32_at(b, 0);
        let f = [f32_at(b, 4), f32_at(b, 8), f32_at(b, 12)];
        let l = [f32_at(b, 16), f32_at(b, 20), f32_at(b, 24)];
        let u = [f32_at(b, 28), f32_at(b, 32), f32_at(b, 36)];
        let pos = [f32_at(b, 40), f32_at(b, 44), f32_at(b, 48)];
        let def = i16::from_le_bytes([b[52], b[53]]) as usize;
        let wb = [f32_at(b, 76), f32_at(b, 80), f32_at(b, 84), f32_at(b, 88), f32_at(b, 92), f32_at(b, 96)];
        let verts = find_block(&layout, &file, &root, &format!("{}.vertices", transplant::definition(def))).expect("verts");
        let mut mn = [f32::MAX; 3]; let mut mx = [f32::MIN; 3];
        let mut wmn = [f32::MAX; 3]; let mut wmx = [f32::MIN; 3];
        for k in 0..verts.block.count as usize {
            let v = verts.block.element(k).unwrap();
            let p = [f32_at(v, 0), f32_at(v, 4), f32_at(v, 8)];
            for ax in 0..3 { mn[ax] = mn[ax].min(p[ax]); mx[ax] = mx[ax].max(p[ax]); }
            let w = [
                pos[0] + scale * (p[0] * f[0] + p[1] * l[0] + p[2] * u[0]),
                pos[1] + scale * (p[0] * f[1] + p[1] * l[1] + p[2] * u[1]),
                pos[2] + scale * (p[0] * f[2] + p[1] * l[2] + p[2] * u[2]),
            ];
            for ax in 0..3 { wmn[ax] = wmn[ax].min(w[ax]); wmx[ax] = wmx[ax].max(w[ax]); }
        }
        let shape = find_block(&layout, &file, &root, &format!("instanced geometry instances[{i}].physics[0].collision geometry shape")).ok();
        println!("instance {i} def {def} scale {scale:.4} pos ({:.2},{:.2},{:.2})", pos[0], pos[1], pos[2]);
        println!("   local vertex bounds  ({:.2},{:.2},{:.2})..({:.2},{:.2},{:.2})  centre ({:.2},{:.2},{:.2}) half ({:.2},{:.2},{:.2})",
            mn[0], mn[1], mn[2], mx[0], mx[1], mx[2],
            (mn[0]+mx[0])/2.0, (mn[1]+mx[1])/2.0, (mn[2]+mx[2])/2.0, (mx[0]-mn[0])/2.0, (mx[1]-mn[1])/2.0, (mx[2]-mn[2])/2.0);
        println!("   world vertex bounds  ({:.2},{:.2},{:.2})..({:.2},{:.2},{:.2})", wmn[0], wmn[1], wmn[2], wmx[0], wmx[1], wmx[2]);
        println!("   instance bounds field x[{:.2},{:.2}] y[{:.2},{:.2}] z[{:.2},{:.2}]", wb[0], wb[1], wb[2], wb[3], wb[4], wb[5]);
        if let Some(s) = shape {
            let e = s.block.element(0).unwrap();
            println!("   shape centre ({:.2},{:.2},{:.2}) w {:.2}  half extent ({:.2},{:.2},{:.2}) w {:.2}  bsp {} type {} inst {} scale {:.4}  runtime tag idx {}",
                f32_at(e, 48), f32_at(e, 52), f32_at(e, 56), f32_at(e, 60), f32_at(e, 64), f32_at(e, 68), f32_at(e, 72), f32_at(e, 76),
                e[104] as i8, e[105] as i8, i16::from_le_bytes([e[106], e[107]]), f32_at(e, 108), i32::from_le_bytes(e[80..84].try_into().unwrap()));
        } else {
            println!("   no physics shape");
        }
    }
}
