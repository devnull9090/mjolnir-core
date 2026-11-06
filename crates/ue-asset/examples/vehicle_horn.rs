//! A cloned horn weapon's Blueprint, playing our own sound.
//!
//!   vehicle_horn <Blueprint .uasset> <sound package> <out.uasset>
//!
//! The horn is the Warthog's driver weapon, and its `lsnd` attachment names events
//! with no bank behind them: `BP_WarthogHornWeaponActor` is what plays it, from
//! `Audio_Horn_Start` and `Audio_Horn_End`. So a vehicle's own horn is a clone of
//! that Blueprint (`vehicle_actor`) with this one import repointed.
use ue_asset::package::{name_hash, public_export_hash, ZenPackage};

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    if a.len() != 3 {
        eprintln!("usage: vehicle_horn <Blueprint> <sound package> <out.uasset>");
        std::process::exit(2);
    }
    let mut z = ZenPackage::parse(&std::fs::read(&a[0]).unwrap()).unwrap();
    let sound = &a[1];
    let p = z
        .imported_package_names
        .names
        .iter()
        .position(|n| n.ends_with("/VEH_Warthog_Horn_Loop"))
        .expect("no VEH_Warthog_Horn_Loop import");
    z.imported_package_names.names[p] = sound.clone();
    z.imported_package_names.hashes[p] = name_hash(sound);
    let hits: Vec<u32> = z
        .import_map
        .iter()
        .filter(|&&v| v >> 62 == 2 && ((v >> 32) & 0x3fff_ffff) as usize == p)
        .map(|&v| v as u32)
        .collect();
    assert_eq!(hits.len(), 1, "imports of the horn");
    z.imported_public_export_hashes[hits[0] as usize] =
        public_export_hash(sound.rsplit('/').next().unwrap());
    let out = z.write();
    ZenPackage::parse(&out).unwrap();
    std::fs::write(&a[2], out).unwrap();
    println!("{}: horn plays {sound}", a[2]);
}
