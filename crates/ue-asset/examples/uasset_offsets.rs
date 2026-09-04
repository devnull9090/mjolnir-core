//! Scan a tag package's .uasset chunk for integers that look like offsets into
//! its .ubulk payload, and dump its export/property names.
//!
//!   cargo run -p ue-asset --example uasset_offsets -- <paks> <path substring> <payload size>
use ue_asset::zen::Package;
fn main() {
    let mut a = std::env::args().skip(1);
    let paks = a.next().unwrap(); let want = a.next().unwrap(); let size: u64 = a.next().unwrap().parse().unwrap();
    for c in ue_iostore::load_all(&paks).expect("load") {
        for (path, idx) in &c.files {
            if !(path.contains(&want) && path.ends_with(".uasset")) { continue; }
            let data = ue_iostore::read_chunk(&c, &c.chunks[*idx], None, &[]).expect("read");
            println!("{path}: {} bytes", data.len());
            if let Ok(pkg) = Package::parse(&data) {
                println!("  names: {}", pkg.names.iter().filter(|n| !n.starts_with('/')).cloned().collect::<Vec<_>>().join(" "));
                for e in &pkg.exports { println!("  export {} class {:?}", e.name, e.class); }
            }
            let mut hits = Vec::new();
            for o in (0..data.len().saturating_sub(4)).step_by(4) {
                let v = u32::from_le_bytes(data[o..o + 4].try_into().unwrap()) as u64;
                if v > 4096 && v < size { hits.push((o, v)); }
            }
            println!("  {} u32 values between 4096 and the payload size:", hits.len());
            for (o, v) in hits.iter().take(60) { print!("{o}:{v} "); }
            println!();
        }
    }
}
