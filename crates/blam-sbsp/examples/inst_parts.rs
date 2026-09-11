//! Block counts an instanced-geometry instance carries (physics etc.).
//!   cargo run -p blam-sbsp --example inst_parts -- <payload> <instance index>...
use blam_tag::blockedit::find_block;
const INST: &str = "instanced geometry instances";
fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let block = tag.read_data(&layout).expect("data");
    let payload = tag.data().expect("bdat");
    let bytes = payload.content;
    for a in &args[1..] {
        let i: usize = a.parse().unwrap();
        println!("-- instance {i}");
        // The world box the tag stores at 76..100, min/max interleaved per
        // axis; the definition's local frame is world minus the position.
        if let Ok(b) = find_block(&layout, bytes, &block, INST) {
            if let Some(e) = b.block.element(i) {
                let f = |o: usize| f32::from_le_bytes(e[o..o + 4].try_into().unwrap());
                println!(
                    "   world box x[{:.2},{:.2}] y[{:.2},{:.2}] z[{:.2},{:.2}]",
                    f(76),
                    f(80),
                    f(84),
                    f(88),
                    f(92),
                    f(96)
                );
            }
        }
        for sub in [
            "physics",
            "physics[0].collision geometry shape",
            "physics[0].mopp codes",
        ] {
            let path = format!("{INST}[{i}].{sub}");
            match find_block(&layout, bytes, &block, &path) {
                Ok(b) => println!("   {sub:<40} {} element(s)", b.block.count),
                Err(e) => println!("   {sub:<40} ({e:?})"),
            }
        }
    }
}
