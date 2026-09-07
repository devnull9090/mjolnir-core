//! Print a class's whole unversioned schema chain, slot by slot, in the order
//! the walker resolves it (the class's own properties first, then each super).
//!
//!   cargo run -p ue-asset --example usmap_chain -- <usmap> <Class>...

use ue_asset::Usmap;

fn main() {
    let mut args = std::env::args().skip(1);
    let path = args.next().expect("usmap path");
    let map = Usmap::parse(&std::fs::read(&path).expect("read usmap")).expect("parse usmap");
    for class in args {
        let total = map.total_slots(&class);
        let mut chain = Vec::new();
        let mut cur = map.structs.get(&class);
        while let Some(s) = cur {
            chain.push(s.name.clone());
            cur = s.super_name.as_deref().and_then(|n| map.structs.get(n));
        }
        println!("\n{class}  ({total} slots)  chain: {}", chain.join(" -> "));
        for slot in 0..total {
            match map.resolve(&class, slot) {
                Some((owner, p)) => println!(
                    "  [{slot:3}] x{} {:<36} {:?}  ({})",
                    p.array_dim, p.name, p.ty, owner.name
                ),
                None => println!("  [{slot:3}] <gap>"),
            }
        }
    }
}
