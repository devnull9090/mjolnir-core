//! Print a Halo 2 map's decorators: per BSP the placements by set, type,
//! class and permutation, and each decorator set's classes and models.
//! Usage: h2_decorators <map>; JSON=<out> writes the placements.
use blam_cache::h2::{decorator, Cache, Group};
use std::collections::BTreeMap;
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let cache = Cache::open(Path::new(&a[1]), None).expect("open");
    let file = &cache.map;
    let mut all = Vec::new();
    for e in file.tags.iter().filter(|e| e.group == Group::new(b"sbsp")) {
        let Some(at) = e.address.and_then(|x| file.offset(x)) else { continue };
        let root = blam_cache::h2::Struct { file, at };
        let ps = decorator::placements(&cache, root).expect("decorators");
        let mut tally: BTreeMap<(usize, u8, usize, usize), usize> = BTreeMap::new();
        for p in &ps {
            *tally.entry((p.set, p.kind, p.class, p.permutation)).or_default() += 1;
        }
        println!("{}: {} placement(s)", e.name, ps.len());
        for ((set, kind, class, perm), n) in &tally {
            println!("  set {set} type {kind} class {class} permutation {perm}: {n}");
        }
        all.extend(ps.iter().map(|p| serde_json::json!({"set": p.set, "type": p.kind, "class": p.class, "perm": p.permutation,
            "pos": p.position, "yaw": p.yaw, "scale": p.scale, "tint_blend": p.tint_blend, "up": p.up, "tint": p.tint, "lightmap": p.lightmap})));
    }
    let scnr = cache.scenario().expect("scenario");
    for (i, r) in scnr.root.block(0x378, 8).iter().enumerate() {
        let Some(t) = r.tagref(0).and_then(|r| cache.follow(r)) else { continue };
        let s = decorator::set(&cache, t.root).expect("set");
        println!("set {i}: {} ({} shader(s), {} model(s), {} vertices, {} indices)", t.name(), s.shaders.len(), s.models.len(), s.vertices.len(), s.indices.len());
        println!("  models: {:?}", s.models.iter().map(|m| (m.name.as_str(), m.first, m.count)).collect::<Vec<_>>());
        for (k, c) in s.classes.iter().enumerate() {
            println!("  class {k} {} type {} scale {}: {:?}", c.name, c.kind, c.scale,
                c.permutations.iter().map(|p| (p.name.as_str(), p.index, p.flags, p.scale)).collect::<Vec<_>>());
        }
    }
    if let Some(out) = std::env::var_os("JSON") {
        std::fs::write(out, serde_json::to_string(&all).unwrap()).unwrap();
    }
}
