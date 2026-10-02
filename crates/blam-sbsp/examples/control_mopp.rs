//! Bisection control: recompile definitions' MOPPs from their own shipped
//! surfaces (and sync their instances' copies of the header), park some
//! instances, and change nothing else. If a pawn still stands on the
//! recompiled definition, the MOPP compiler is not what drops converted
//! terrain.
//!
//!   cargo run -p blam-sbsp --example control_mopp -- <payload> <out> --defs 159 [--park 545,593,779]
use blam_sbsp::convert;

fn list(v: Option<&String>) -> Vec<usize> {
    v.map(|s| s.split(',').map(|x| x.parse().unwrap()).collect())
        .unwrap_or_default()
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let at = |flag: &str| a.iter().position(|x| x == flag).and_then(|i| a.get(i + 1));
    let defs = list(at("--defs"));
    let park = list(at("--park"));
    let (file, lens) = convert::compile_definition_mopps(&file, &defs).expect("mopp");
    println!("  recompiled {defs:?}: {lens:?} code byte(s)");
    let file = convert::park_instances(&file, &park, -500.0).expect("park");
    println!("  parked {park:?}");
    std::fs::write(&a[1], &file).expect("write");
    println!("  wrote {} ({} bytes)", a[1], file.len());
}
