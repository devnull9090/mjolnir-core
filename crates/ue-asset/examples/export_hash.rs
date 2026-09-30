//! Print the public export hash a leaf object name derives to, so an import
//! written by hand can be checked against the shipped package's export.
//!
//!   cargo run -p ue-asset --example export_hash -- <leaf name>...
fn main() {
    for name in std::env::args().skip(1) {
        println!(
            "{name} -> {:#018x}",
            ue_asset::package::public_export_hash(&name)
        );
    }
}
