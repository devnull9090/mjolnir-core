//! Hexdump one definition element and name any float that matches a known
//! mopp-header value, to locate the definition-level copy of the header.
//!   cargo run -p blam-sbsp --example def_elem_hex -- <payload> <def>
use blam_sbsp::transplant;
const DEFS: &str = "resource interface.raw_resources[0].raw_items.instanced geometries definitions";
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let d: usize = a[1].parse().unwrap();
    let (e, _) = transplant::donor_element(&file, DEFS, d).expect("element");
    for (i, row) in e.chunks(16).enumerate() {
        let hex: Vec<String> = row.iter().map(|b| format!("{b:02x}")).collect();
        println!("{:04x}: {}", i * 16, hex.join(" "));
    }
    println!("floats that look like coordinates or scales:");
    for o in (0..e.len() - 3).step_by(4) {
        let v = f32::from_le_bytes(e[o..o + 4].try_into().unwrap());
        let u = u32::from_le_bytes(e[o..o + 4].try_into().unwrap());
        if v.is_finite() && (v.abs() > 0.5 && v.abs() < 1.0e7) && u != 0 {
            println!("  +{o:#05x} f32 {v:>14.4}   u32 {u}");
        }
    }
}
