//! Print an instanced-geometry definition's collision tables.
//!
//!   cargo run -p blam-sbsp --example def_probe -- <sbsp payload> <def index>...
use blam_tag::blockedit::find_block;

const DEFS: &str = "resource interface.raw_resources[0].raw_items.instanced geometries definitions";

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");

    let defs = find_block(&layout, &file, &root, DEFS).expect("definitions");
    println!("{} definition(s)", defs.block.count);

    if args.len() == 1 {
        // No indices: one line per definition, so the shapes of the whole set
        // are visible at once.
        let mut zero_supernodes = 0;
        for idx in 0..defs.block.count as usize {
            let count = |t: &str| {
                find_block(&layout, &file, &root, &format!("{DEFS}[{idx}].collision info.{t}"))
                    .map(|f| f.block.count)
                    .unwrap_or(0)
            };
            let (n, sn, sf) = (count("bsp3d nodes"), count("bsp3d supernodes"), count("surfaces"));
            if sn == 0 {
                zero_supernodes += 1;
            }
            println!("  def {idx:<4} nodes {n:<6} supernodes {sn:<4} surfaces {sf}");
        }
        println!("{zero_supernodes} definition(s) have no supernode");
        return;
    }

    for a in &args[1..] {
        let idx: usize = a.parse().expect("index");
        println!("-- definition {idx}");
        for table in [
            "bsp3d nodes",
            "bsp3d supernodes",
            "planes",
            "leaves",
            "bsp2d references",
            "bsp2d nodes",
            "surfaces",
            "edges",
            "vertices",
        ] {
            let path = format!("{DEFS}[{idx}].collision info.{table}");
            match find_block(&layout, &file, &root, &path) {
                Ok(f) => println!(
                    "   {table:<18} {:>6} element(s) of {} bytes",
                    f.block.count,
                    if f.block.count > 0 {
                        f.block.elements.len() / f.block.count as usize
                    } else {
                        0
                    }
                ),
                Err(e) => println!("   {table:<18} unavailable: {e}"),
            }
        }
    }
}
