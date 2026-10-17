//! Re-encode a stock-cooked zen package's properties in the game's layout
//! (ue_asset::retarget).
//!
//!   cargo run -p ue-asset --example retarget_package -- <global.utoc dir> <stock.usmap> <game.usmap> <in.umap> <out.umap>
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let containers = ue_iostore::load_all(&a[0]).expect("containers");
    let global = containers
        .iter()
        .find(|c| {
            c.utoc_path
                .file_name()
                .map(|n| n == "global.utoc")
                .unwrap_or(false)
        })
        .expect("no global.utoc");
    let chunk = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .expect("no ScriptObjects chunk");
    let data = ue_iostore::read_chunk(global, chunk, None, &[]).expect("read ScriptObjects");
    let scripts = ue_asset::zen::ScriptObjects::parse(&data).expect("ScriptObjects");
    let stock =
        ue_asset::Usmap::parse(&std::fs::read(&a[1]).expect("stock usmap")).expect("stock usmap");
    let game =
        ue_asset::Usmap::parse(&std::fs::read(&a[2]).expect("game usmap")).expect("game usmap");
    let mut pkg = ue_asset::package::ZenPackage::parse(&std::fs::read(&a[3]).expect("package"))
        .expect("package");
    for line in ue_asset::retarget::package(&mut pkg, &stock, &game, &scripts).expect("retarget") {
        println!("{line}");
    }
    std::fs::write(&a[4], pkg.write()).expect("write");
    println!("wrote {}", a[4]);
}
