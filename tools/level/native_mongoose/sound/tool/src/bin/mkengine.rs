// New packages for the engine bank.
//   mkengine <ev_stop.uasset> <hs_engine.uasset> <bl_engine.uasset> <out dir> <bank id> <id play> <id stop>
use ue_asset::package::{name_hash, public_export_hash, ZenPackage};
const ROOT: &str = "/Game/MJOLNIR/Audio/CEEngine";
const OLD_BANK: u32 = 833622567;
const OLD_EVENT: u32 = 3182413213;
const BANK_NAME: &str = "MJ_CE_Engine";

fn set_name(z: &mut ZenPackage, old: &str, new: &str) {
    let i = z.names.names.iter().position(|n| n == old).unwrap_or_else(|| panic!("no name {old}"));
    z.names.names[i] = new.to_string();
    z.names.hashes[i] = name_hash(new);
}
fn replace_u32(b: &mut [u8], old: u32, new: u32, want: usize) {
    let (o, n) = (old.to_le_bytes(), new.to_le_bytes());
    let (mut c, mut i) = (0, 0);
    while i + 4 <= b.len() {
        if b[i..i + 4] == o { b[i..i + 4].copy_from_slice(&n); c += 1; i += 4 } else { i += 1 }
    }
    assert_eq!(c, want, "{old:#x} occurrences");
}
fn rename(z: &mut ZenPackage, path: &str) {
    let leaf = path.rsplit('/').next().unwrap();
    let old_path = z.name();
    let old_leaf = old_path.rsplit('/').next().unwrap().to_string();
    set_name(z, &old_path, path);
    set_name(z, &old_leaf, leaf);
    z.export_map[0].public_export_hash = public_export_hash(leaf);
}
fn event(tpl: &[u8], leaf: &str, bank: u32, id: u32, tail: (f32, f32, u32, f32)) -> (String, Vec<u8>) {
    let mut z = ZenPackage::parse(tpl).unwrap();
    assert_eq!(z.write(), tpl, "template round trip");
    let path = format!("{ROOT}/{leaf}");
    rename(&mut z, &path);
    set_name(&mut z, &format!("{OLD_BANK}.bnk"), &format!("{bank}.bnk"));
    set_name(&mut z, "VE_Warthog", BANK_NAME);
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
// The imported package whose leaf starts `prefix` becomes `new`: its name, hash, and
// the public export hash of the one import that names it.
fn retarget(z: &mut ZenPackage, prefix: &str, new: &str) {
    let p = z.imported_package_names.names.iter()
        .position(|n| n.rsplit('/').next().unwrap().starts_with(prefix))
        .unwrap_or_else(|| panic!("no import {prefix}"));
    z.imported_package_names.names[p] = new.to_string();
    z.imported_package_names.hashes[p] = name_hash(new);
    let hits: Vec<u32> = z.import_map.iter()
        .filter(|&&v| v >> 62 == 2 && ((v >> 32) & 0x3fff_ffff) as usize == p)
        .map(|&v| v as u32).collect();
    assert_eq!(hits.len(), 1, "imports of {prefix}");
    z.imported_public_export_hashes[hits[0] as usize] = public_export_hash(new.rsplit('/').next().unwrap());
}
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let (ev, hs, bl) = (std::fs::read(&a[0]).unwrap(), std::fs::read(&a[1]).unwrap(), std::fs::read(&a[2]).unwrap());
    let out = &a[3];
    let n = |i: usize| a[i].parse::<u32>().unwrap();
    let (bank, play, stop) = (n(4), n(5), n(6));
    let mut list = vec![
        event(&ev, "Play_MJ_CE_Engine", bank, play, (0.0, 0.0, 1, 8000.0)),
        event(&ev, "Stop_MJ_CE_Engine", bank, stop, (0.0, 0.0, 0, 0.0)),
    ];
    let (pp, sp) = (list[0].0.clone(), list[1].0.clone());
    for (tpl, leaf, pre_play, pre_stop) in [(&hs, "HS_MJ_CE_Engine", "Play_", "Stop_"), (&bl, "BL_MJ_CE_Engine", "Play_", "Stop_")] {
        let mut z = ZenPackage::parse(tpl).unwrap();
        assert_eq!(z.write(), *tpl, "template round trip");
        let p = format!("{ROOT}/{leaf}");
        rename(&mut z, &p);
        retarget(&mut z, pre_play, &pp);
        retarget(&mut z, pre_stop, &sp);
        println!("# {p} imports {:?}", z.imported_package_names.names);
        list.push((p, z.write()));
    }
    for (p, b) in &list {
        let f = format!("{out}/{}.uasset", p.rsplit('/').next().unwrap());
        std::fs::write(&f, b).unwrap();
        ZenPackage::parse(b).unwrap();
        println!("{p}={f}");
    }
}
