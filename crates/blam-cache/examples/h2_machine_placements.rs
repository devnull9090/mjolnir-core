//! Print a Halo 2 map's machine and control placements: their device
//! groups and the device and machine placement flags.
use blam_cache::h2::Cache;
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let root = cache.scenario().expect("scnr").root;
    for (kind, pal, size, group) in [(0xA8usize, 0xB0usize, 0x48usize, "mach"), (0xB8, 0xC0, 0x44, "ctrl")] {
        let palette = root.block(pal, 0x28);
        for e in root.block(kind, size).iter() {
            let i = e.i16(0);
            let Some(obj) = (i >= 0).then(|| palette.get(i as usize)).flatten().and_then(|p| p.tagref(0)).and_then(|r| cache.follow(r)) else { continue };
            let tail: Vec<String> = (0x34..size).step_by(4).map(|o| format!("{:08x}", e.u32(o))).collect();
            let t = if group == "mach" { format!(" type {} flags {:#x} radius {}", obj.root.u16(0x11C), obj.root.u16(0x11E), obj.root.f32(0x118)) } else { String::new() };
            println!("{group} {} pos {:?}{t} tail {}", obj.name(), e.vec3(0x08), tail.join(" "));
        }
    }
}
