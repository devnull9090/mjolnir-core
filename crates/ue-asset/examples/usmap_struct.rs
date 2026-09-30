//! Print one or more reflected classes/structs from a usmap, supers included.
//!
//!   cargo run -p ue-asset --example usmap_struct -- <usmap> <Name>...
use ue_asset::Usmap;

fn main() {
    let mut args = std::env::args().skip(1);
    let path = args.next().expect("usage: usmap_struct <usmap> <Name>...");
    let data = std::fs::read(&path).expect("read usmap");
    let map = Usmap::parse(&data).expect("parse usmap");
    for name in args {
        let mut cur = Some(name.clone());
        let mut depth = 0;
        while let Some(n) = cur {
            match map.structs.get(&n) {
                Some(s) => {
                    println!("{}{} (props {}, super {:?})", "  ".repeat(depth), s.name, s.prop_count, s.super_name);
                    for p in &s.props {
                        println!("{}    {:?}", "  ".repeat(depth), p);
                    }
                    cur = s.super_name.clone();
                    depth += 1;
                    if depth > 6 {
                        break;
                    }
                }
                None => {
                    println!("{n}: not in usmap");
                    break;
                }
            }
        }
    }
}
