//! Dump an instance's `physics[0]` element (the Havok `mopp bv tree shape`
//! and what follows) beside its definition's mopp element, as dwords read
//! both as floats and integers, to spot the copies the instance keeps.
//!
//!   cargo run -p blam-sbsp --example inst_shape_dump -- <payload> <instance> <definition>
use blam_sbsp::transplant;

fn dump(label: &str, b: &[u8]) {
    println!("{label} ({} bytes)", b.len());
    for (i, w) in b.chunks(4).enumerate() {
        if w.len() < 4 {
            break;
        }
        let u = u32::from_le_bytes(w.try_into().unwrap());
        let f = f32::from_le_bytes(w.try_into().unwrap());
        println!("  +{:<4} {:#010x} {:>14} {:>16.6}", i * 4, u, u as i32, f);
    }
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let (e, _) = transplant::donor_element(
        &file,
        &format!("instanced geometry instances[{}].physics", a[1]),
        0,
    )
    .expect("physics");
    dump(&format!("instance {} physics[0]", a[1]), &e);
    let base = transplant::definition(a[2].parse().unwrap());
    let base = base.trim_end_matches(".collision info");
    let (m, _) = transplant::donor_element(&file, &format!("{base}.mopp codes"), 0).expect("mopp");
    dump(&format!("definition {} mopp codes[0]", a[2]), &m);
}
