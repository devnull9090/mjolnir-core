//! For each placed scenery / crate palette object of a Halo 2 map: whether its
//! model has a collision model (and how many surfaces), and its physics
//! model's solid shapes (pills, boxes, polyhedra, minus phantoms). Census aid.
use blam_cache::h2::{collision, Cache};
use std::path::Path;

fn main() {
    let map = std::env::args().nth(1).expect("map");
    let cache = Cache::open(Path::new(&map), None).expect("open");
    let root = cache.scenario().expect("scnr").root;
    for (kind_block, palette_block, size, group) in [(0x50usize, 0x58usize, 0x5Cusize, "scen"), (0x328, 0x330, 0x4C, "bloc")] {
        let palette = root.block(palette_block, 0x28);
        let mut placed = vec![0usize; palette.count];
        for e in root.block(kind_block, size).iter() {
            let i = e.i16(0);
            if i >= 0 && (i as usize) < placed.len() {
                placed[i as usize] += 1;
            }
        }
        for (i, p) in palette.iter().enumerate() {
            if placed[i] == 0 {
                continue;
            }
            let Some(obj) = p.tagref(0).and_then(|r| cache.follow(r)) else { continue };
            let model = obj.root.tagref(0x34).and_then(|r| cache.follow(r));
            let (mut coll_s, mut phmo_s, mut phantoms) = (None, None, 0);
            if let Some(m) = model {
                if let Some(c) = m.root.tagref(0x08).and_then(|r| cache.follow(r)) {
                    let mut n = 0;
                    for region in c.root.block(0x1C, 0x0C).iter() {
                        if let Some(perm) = region.block(0x04, 0x14).get(0) {
                            for b in perm.block(0x04, 0x44).iter() {
                                n += collision::read(b.at(0x04)).surfaces.len();
                            }
                        }
                    }
                    coll_s = Some(n);
                }
                if let Some(ph) = m.root.tagref(0x20).and_then(|r| cache.follow(r)) {
                    let r = ph.root;
                    phantoms = r.block(0x108, 0x40).count;
                    phmo_s = Some((r.block(0x58, 0x60).count, r.block(0x60, 0xB0).count, r.block(0x70, 0x120).count, r.block(0x50, 0x80).count));
                }
            }
            println!("{group} x{} coll {:?} phmo(pills,boxes,polys,spheres?) {:?} phantoms {} {}", placed[i], coll_s, phmo_s, phantoms, obj.name());
        }
    }
}
