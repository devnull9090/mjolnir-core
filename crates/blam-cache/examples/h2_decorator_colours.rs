//! Compare a Halo 2 map's decal and sprite decorators' stored vertex
//! colours with their placements' tint and lightmap words and the colour
//! Halo 2 computes for model decorators (halo2.dll 0x7fa1d0).
//! Usage: h2_decorator_colours <map> [rows]
use blam_cache::h2::{decorator, Cache, Group};
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let rows: usize = a.get(2).and_then(|s| s.parse().ok()).unwrap_or(12);
    let file = &cache.map;
    for e in file.tags.iter().filter(|e| e.group == Group::new(b"sbsp")) {
        let Some(at) = e.address.and_then(|x| file.offset(x)) else { continue };
        let root = blam_cache::h2::Struct { file, at };
        let decals = decorator::decals(&cache, root).expect("decals");
        let step = (decals.len() / rows.max(1)).max(1);
        for d in decals.iter().step_by(step).take(rows) {
            let f = |c: [f32; 3]| format!("{:.2} {:.2} {:.2}", c[0], c[1], c[2]);
            let v = d.colors.first().copied().unwrap_or_default();
            println!(
                "g{} c{} p{}  vertex [{} a{:.2}]  tint [{}] blend {:.2}  lightmap [{}]",
                d.group, d.class, d.permutation, f([v[0], v[1], v[2]]), v[3], f(d.tint), d.tint_blend, f(d.lightmap)
            );
        }
        let n = decals.len().max(1) as f32;
        let same = decals.iter().filter(|d| d.colors.windows(2).all(|w| w[0] == w[1])).count();
        let mean = |g: &dyn Fn(&decorator::Decal) -> f32| decals.iter().map(g).sum::<f32>() / n;
        println!(
            "{} decal(s); {same} with one colour on every vertex; mean vertex {:.3}, tint {:.3}, lightmap {:.3}",
            decals.len(),
            mean(&|d| d.colors.first().map(|c| (c[0] + c[1] + c[2]) / 3.0).unwrap_or(0.0)),
            mean(&|d| (d.tint[0] + d.tint[1] + d.tint[2]) / 3.0),
            mean(&|d| (d.lightmap[0] + d.lightmap[1] + d.lightmap[2]) / 3.0),
        );
    }
}
