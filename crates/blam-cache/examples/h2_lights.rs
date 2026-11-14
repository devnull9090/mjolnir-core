//! A Halo 2 map's placed lights as scene_lights.json (merge_ce_scene.py
//! write_lights' format, which upgrade_ce_map.py ce_lights reads).
//! Usage: h2_lights <map> <out.json>
//!
//! scnr +0xE8 lights (0x6C each: the 0x34-byte placement header, palette
//! index 0x00, position 0x08, the light itself; 0x4C is a point about 2.2
//! world units over it (above the bases' roofs: not the light); its radius
//! in world units 0x68), palette
//! +0xF0 (0x28 each, a `ligh` reference at 0x00). A `ligh`: colour 0x64
//! (rgb), intensity 0x70. Read off Coagulation (2026-11-14): its bases'
//! sphere lights in the team colours, three a base. Positions go out as
//! glTF metres ((x, z, -y) x 3.048), as halo2ue's conversions write them.
use blam_cache::h2::Cache;
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let scnr = cache.scenario().expect("scenario");
    let palette: Vec<_> = scnr.root.block(0xF0, 0x28).iter().map(|e| e.tagref(0).and_then(|r| cache.follow(r))).collect();
    let mut out = Vec::new();
    for (i, el) in scnr.root.block(0xE8, 0x6C).iter().enumerate() {
        let index = el.u16(0) as usize;
        let Some(Some(tag)) = palette.get(index) else { continue };
        let colour = tag.root.vec3(0x64);
        let intensity = tag.root.f32(0x70);
        let o = el.vec3(0x08);
        let radius = el.f32(0x68);
        let m = 3.048_f32;
        let pos = [o[0] * m, o[2] * m, -o[1] * m];
        let name = tag.name().rsplit('\\').next().unwrap_or("").to_string();
        out.push(serde_json::json!({
            "name": format!("{name}:{i}"), "tag": tag.name(), "pos": pos,
            "dir": [0.0, -1.0, 0.0], "colour": colour, "intensity": intensity,
            "radius": radius, "source": "halo2 scenario light",
        }));
    }
    let n = out.len();
    std::fs::write(&a[2], serde_json::to_string_pretty(&serde_json::json!({ "lights": out })).unwrap()).expect("write");
    println!("{n} light(s) -> {}", a[2]);
}
