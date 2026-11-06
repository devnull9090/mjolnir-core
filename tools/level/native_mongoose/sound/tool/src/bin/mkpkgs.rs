// Clone the shipped horn's Stop event and HaloAudioSound into new packages.
//   mkpkgs <ev_stop.uasset> <hs_veh.uasset> <out dir> <bank id> <id once> <id loop> <id stop> <seconds>
use ue_asset::package::{name_hash, public_export_hash, ZenPackage};
const ROOT: &str = "/Game/MJOLNIR/Audio/CEHorn";
const OLD_BANK: u32 = 833622567;
const OLD_EVENT: u32 = 3182413213;

fn set_name(z: &mut ZenPackage, old: &str, new: &str) {
    let i = z.names.names.iter().position(|n| n == old).unwrap_or_else(|| panic!("no name {old}"));
    z.names.names[i] = new.to_string();
    z.names.hashes[i] = name_hash(new);
}
fn replace_u32(b: &mut [u8], old: u32, new: u32, want: usize) {
    let (o, n) = (old.to_le_bytes(), new.to_le_bytes());
    let mut c = 0;
    let mut i = 0;
    while i + 4 <= b.len() {
        if b[i..i + 4] == o { b[i..i + 4].copy_from_slice(&n); c += 1; i += 4 } else { i += 1 }
    }
    assert_eq!(c, want, "{old:#x} occurrences");
}
fn event(tpl: &[u8], leaf: &str, bank: u32, id: u32, tail: (f32, f32, u32, f32)) -> (String, Vec<u8>) {
    event_at(tpl, &format!("{ROOT}/{leaf}"), bank, id, tail)
}
fn event_at(tpl: &[u8], path: &str, bank: u32, id: u32, tail: (f32, f32, u32, f32)) -> (String, Vec<u8>) {
    let mut z = ZenPackage::parse(tpl).unwrap();
    assert_eq!(z.write(), tpl, "template round trip");
    let leaf = path.rsplit('/').next().unwrap();
    let path = path.to_string();
    let old_path = z.name();
    let old_leaf = old_path.rsplit('/').next().unwrap().to_string();
    if old_path != path { set_name(&mut z, &old_path, &path); }
    if old_leaf != leaf { set_name(&mut z, &old_leaf, leaf); }
    set_name(&mut z, &format!("{OLD_BANK}.bnk"), &format!("{bank}.bnk"));
    set_name(&mut z, "VE_Warthog", "MJ_CE_Horn");
    z.export_map[0].public_export_hash = public_export_hash(leaf);
    let mut e = z.export_bytes(0).unwrap().to_vec();
    replace_u32(&mut e, OLD_EVENT, id, 2);
    replace_u32(&mut e, OLD_BANK, bank, 1);
    let n = e.len();
    e[n - 16..n - 12].copy_from_slice(&tail.0.to_le_bytes());
    e[n - 12..n - 8].copy_from_slice(&tail.1.to_le_bytes());
    e[n - 8..n - 4].copy_from_slice(&tail.2.to_le_bytes());
    e[n - 4..].copy_from_slice(&tail.3.to_le_bytes());
    z.set_export_bytes(0, e).unwrap();
    (path, z.write())
}
// HaloAudioSound: import 0 is PlayEvent, import 1 StopEvent. keep_path: leave the package's own path (an override).
fn sound(tpl: &[u8], leaf: Option<&str>, play: &str, stop: &str) -> (String, Vec<u8>, Vec<String>) {
    let mut z = ZenPackage::parse(tpl).unwrap();
    assert_eq!(z.write(), tpl, "template round trip");
    let path = match leaf {
        Some(l) => {
            let p = format!("{ROOT}/{l}");
            let old_path = z.name();
            let old_leaf = old_path.rsplit('/').next().unwrap().to_string();
            set_name(&mut z, &old_path, &p);
            set_name(&mut z, &old_leaf, l);
            z.export_map[0].public_export_hash = public_export_hash(l);
            p
        }
        None => z.name(),
    };
    // Shipped order: imported package 0 = Stop, 1 = Play; hash 0 = Play, 1 = Stop.
    assert!(z.imported_package_names.names[0].contains("Stop_") && z.imported_package_names.names[1].contains("Play_"));
    assert_eq!(z.import_map[0], 0x8000_0001_0000_0000);
    assert_eq!(z.import_map[1], 0x8000_0000_0000_0001);
    z.imported_package_names.names[0] = stop.to_string();
    z.imported_package_names.hashes[0] = name_hash(stop);
    z.imported_package_names.names[1] = play.to_string();
    z.imported_package_names.hashes[1] = name_hash(play);
    z.imported_public_export_hashes[0] = public_export_hash(play.rsplit('/').next().unwrap());
    z.imported_public_export_hashes[1] = public_export_hash(stop.rsplit('/').next().unwrap());
    let imports = z.imported_package_names.names.clone();
    (path, z.write(), imports)
}
// BlamAudioSound, what a snd! tag binds to: import 0 is PlayEvent.
fn blam_sound(tpl: &[u8], leaf: &str, play: &str) -> (String, Vec<u8>) {
    let mut z = ZenPackage::parse(tpl).unwrap();
    assert_eq!(z.write(), tpl, "template round trip");
    let p = format!("{ROOT}/{leaf}");
    let old_path = z.name();
    let old_leaf = old_path.rsplit('/').next().unwrap().to_string();
    set_name(&mut z, &old_path, &p);
    set_name(&mut z, &old_leaf, leaf);
    z.export_map[0].public_export_hash = public_export_hash(leaf);
    assert_eq!(z.imported_package_names.names.len(), 1);
    z.imported_package_names.names[0] = play.to_string();
    z.imported_package_names.hashes[0] = name_hash(play);
    z.imported_public_export_hashes[0] = public_export_hash(play.rsplit('/').next().unwrap());
    (p, z.write())
}
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let ev = std::fs::read(&a[0]).unwrap();
    let hs = std::fs::read(&a[1]).unwrap();
    let out = &a[2];
    let n = |i: usize| a[i].parse::<u32>().unwrap();
    let (bank, once, lp, st) = (n(3), n(4), n(5), n(6));
    let secs: f32 = a[7].parse().unwrap();
    let list = [
        event(&ev, "Play_MJ_CE_Horn_Once", bank, once, (secs, secs, 0, 8000.0)),
        event(&ev, "Play_MJ_CE_Horn_Loop", bank, lp, (0.0, 0.0, 1, 8000.0)),
        event(&ev, "Stop_MJ_CE_Horn_Loop", bank, st, (0.0, 0.0, 0, 0.0)),
    ];
    let mut args = Vec::new();
    for (p, b) in &list {
        let f = format!("{out}/{}.uasset", p.rsplit('/').next().unwrap());
        std::fs::write(&f, b).unwrap();
        ZenPackage::parse(b).unwrap();
        args.push(format!("{p}={f}"));
    }
    let (once_p, loop_p, stop_p) = (&list[0].0, &list[1].0, &list[2].0);
    for (leaf, play) in [("HS_MJ_CE_Horn_Once", once_p), ("HS_MJ_CE_Horn_Loop", loop_p)] {
        let (p, b, imports) = sound(&hs, Some(leaf), play, stop_p);
        let f = format!("{out}/{leaf}.uasset");
        std::fs::write(&f, &b).unwrap();
        args.push(format!("{p}={f}"));
        println!("# {p} imports {imports:?}");
    }
    {
        let bs = std::fs::read(&a[8]).unwrap();
        let (p, b) = blam_sound(&bs, "BS_MJ_CE_Horn_Once", once_p);
        let f = format!("{out}/BS_MJ_CE_Horn_Once.uasset");
        std::fs::write(&f, &b).unwrap();
        ZenPackage::parse(&b).unwrap();
        args.push(format!("{p}={f}"));
    }
    // Stage B: the stock horn's two events, same package paths, our bank and ids. An
    // event imports no package, so an override needs no store entry.
    let stock = "/Game/WwiseAudio/Events/Meteorite/Vehicle/Warthog/VEH_Warthog_Horn";
    let (_, b) = event_at(&ev, &format!("{stock}/Play_VEH_Warthog_Horn_Loop"), bank, lp, (0.0, 0.0, 1, 8000.0));
    std::fs::write(format!("{out}/override_Play_VEH_Warthog_Horn_Loop.uasset"), &b).unwrap();
    let (_, b) = event_at(&ev, &format!("{stock}/Stop_VEH_Warthog_Horn_Loop"), bank, st, (0.0, 0.0, 0, 0.0));
    std::fs::write(format!("{out}/override_Stop_VEH_Warthog_Horn_Loop.uasset"), &b).unwrap();
    for x in args { println!("{x}"); }
}
