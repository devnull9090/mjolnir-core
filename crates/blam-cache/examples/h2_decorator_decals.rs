//! Print a Halo 2 map's decal decorators: set, class, permutation, the quad's
//! corners, texture coordinates, colours and triangles (first few), and
//! the count. Usage: h2_decorator_decals <map> [how many to show]
use blam_cache::h2::{decorator, Cache, Group};
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let show: usize = a.get(2).and_then(|s| s.parse().ok()).unwrap_or(4);
    let file = &cache.map;
    for e in file.tags.iter().filter(|e| e.group == Group::new(b"sbsp")) {
        let Some(at) = e.address.and_then(|x| file.offset(x)) else { continue };
        let root = blam_cache::h2::Struct { file, at };
        let ds = decorator::decals(&cache, root).expect("decals");
        println!("{}: {} decal(s)", e.name, ds.len());
        for d in ds.iter().take(show) {
            println!(" set {} class {} perm {} tris {:?}", d.set, d.class, d.permutation, d.triangles);
            for k in 0..d.positions.len() {
                println!("   {:?} uv {:?} col {:?}", d.positions[k], d.uvs[k], d.colors[k]);
            }
        }
    }
}
