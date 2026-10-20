//! Print a zen package file's bulk-data map and export layout.
//!
//!   cargo run -p ue-asset --example bulk_map -- <package file>
fn main() {
    let path = std::env::args()
        .nth(1)
        .expect("usage: bulk_map <package file>");
    let data = std::fs::read(&path).expect("read");
    let pkg = ue_asset::package::ZenPackage::parse(&data).expect("package");
    println!("{} bytes, {} export(s)", data.len(), pkg.export_map.len());
    for b in &pkg.bulk {
        println!("  bulk {b:?}");
    }
    let header = data.len() as u64
        - pkg
            .export_map
            .iter()
            .map(|e| e.cooked_serial_size)
            .sum::<u64>();
    println!("header {header} bytes; exports by offset:");
    let mut order: Vec<usize> = (0..pkg.export_map.len()).collect();
    order.sort_by_key(|&i| pkg.export_map[i].cooked_serial_offset);
    for i in order {
        let e = &pkg.export_map[i];
        println!(
            "  {:>8} {:>7}  export {i} {}",
            e.cooked_serial_offset,
            e.cooked_serial_size,
            pkg.mapped_name(e.name_index, e.name_number)
        );
    }
}
