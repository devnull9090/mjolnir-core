//! A cloned vehicle Blueprint with its engine loop back, playing our own sound.
//!
//!   vehicle_engine <muted Blueprint .uasset> <donor Blueprint .uasset> <sound package> <out.uasset>
//!
//! `vehicle_mute` jumps over the engine's `PlaySound` and over the stop's guard,
//! and over the gear shift's. This puts the donor's bytes back for the first two
//! only, so the gear shift stays silent, and repoints the `Engine_Main` import,
//! which is what `SoundVariant_EngineLoop` holds.
//!
//! The Blueprint is the whole of the engine's pitch: its `Audio_EngineTick` sets
//! `RTPC_VEH_Speed` on the sound it started, from
//! `GetEngineAngularVelocityFraction`, every 33 ms. An `lsnd` attachment can't do
//! that. It only starts and stops its loop (docs/ce_native_support.md, result 12).
use ue_asset::{
    kismet::{self, Names, Stmt},
    package::{name_hash, public_export_hash, ZenPackage},
};

struct Text<'a>(&'a ZenPackage);

impl Names for Text<'_> {
    fn name(&self, index: u32, number: u32) -> String {
        self.0.mapped_name(index, number)
    }
    fn object(&self, index: i32) -> String {
        format!("object{index}")
    }
}

fn ubergraph(z: &ZenPackage) -> usize {
    (0..z.export_map.len())
        .find(|&i| {
            let e = &z.export_map[i];
            z.mapped_name(e.name_index, e.name_number)
                .starts_with("ExecuteUbergraph")
        })
        .expect("no ubergraph")
}

fn restores(s: &Stmt) -> bool {
    s.text.contains("SoundVariant_EngineLoop") || s.text.contains("IsTrackedSoundIdValid")
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    if a.len() != 4 {
        eprintln!("usage: vehicle_engine <muted> <donor> <sound package> <out.uasset>");
        std::process::exit(2);
    }
    let mut muted = ZenPackage::parse(&std::fs::read(&a[0]).unwrap()).unwrap();
    let donor = ZenPackage::parse(&std::fs::read(&a[1]).unwrap()).unwrap();
    let sound = &a[2];

    let (mi, di) = (ubergraph(&muted), ubergraph(&donor));
    let mut mb = muted.export_bytes(mi).unwrap().to_vec();
    let db = donor.export_bytes(di).unwrap().to_vec();
    let ms = kismet::script(&mb, &Text(&muted)).unwrap();
    let ds = kismet::script(&db, &Text(&donor)).unwrap();
    assert_eq!(mb.len(), db.len(), "ubergraph sizes");
    assert_eq!(ms.start, ds.start, "script starts");

    // Every donor statement the mute changed, then the two that come back.
    let code = ms.start;
    let changed: Vec<&Stmt> = ds
        .stmts
        .iter()
        .filter(|s| {
            let r = code + s.range.start..code + s.range.end;
            mb[r.clone()] != db[r]
        })
        .collect();
    let back: Vec<&&Stmt> = changed.iter().filter(|s| restores(s)).collect();
    assert_eq!(back.len(), 2, "engine PlaySound and its stop's guard");
    for s in back {
        let r = code + s.range.start..code + s.range.end;
        mb[r.clone()].copy_from_slice(&db[r]);
    }
    let after = kismet::script(&mb, &Text(&muted)).unwrap();
    assert_eq!(after.memory_size, ms.memory_size, "script memory size");
    muted.set_export_bytes(mi, mb).unwrap();

    // The sound.
    let p = muted
        .imported_package_names
        .names
        .iter()
        .position(|n| n.ends_with("/VEH_Warthog_Engine_Main"))
        .expect("no Engine_Main import");
    muted.imported_package_names.names[p] = sound.clone();
    muted.imported_package_names.hashes[p] = name_hash(sound);
    let hits: Vec<u32> = muted
        .import_map
        .iter()
        .filter(|&&v| v >> 62 == 2 && ((v >> 32) & 0x3fff_ffff) as usize == p)
        .map(|&v| v as u32)
        .collect();
    assert_eq!(hits.len(), 1, "imports of Engine_Main");
    muted.imported_public_export_hashes[hits[0] as usize] =
        public_export_hash(sound.rsplit('/').next().unwrap());

    let out = muted.write();
    ZenPackage::parse(&out).unwrap();
    std::fs::write(&a[3], out).unwrap();
    println!("{}: engine back, playing {sound}", a[3]);
}
