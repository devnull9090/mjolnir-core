// The vehicle Blueprint with its engine loop back and pointed at our sound.
//   engactor <muted BP.uasset> <shipped donor BP.uasset> <new sound package> <out.uasset>
//
// vehicle_mute wrote jumps over the engine's PlaySound and over the stop's guard, and
// left the gear shift's. This puts the donor's bytes back for those two only, and
// retargets the Engine_Main import, which is what SoundVariant_EngineLoop holds.
use ue_asset::{kismet::{self, Names}, package::{name_hash, public_export_hash, ZenPackage}};
struct Text<'a>(&'a ZenPackage);
impl Names for Text<'_> {
    fn name(&self, i: u32, n: u32) -> String { self.0.mapped_name(i, n) }
    fn object(&self, i: i32) -> String { format!("object{i}") }
}
fn uber(z: &ZenPackage) -> usize {
    (0..z.export_map.len()).find(|&i| { let e = &z.export_map[i]; z.mapped_name(e.name_index, e.name_number).starts_with("ExecuteUbergraph_") }).unwrap()
}
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let mut m = ZenPackage::parse(&std::fs::read(&a[0]).unwrap()).unwrap();
    let d = ZenPackage::parse(&std::fs::read(&a[1]).unwrap()).unwrap();
    let new = &a[2];
    let (mi, di) = (uber(&m), uber(&d));
    let mut mb = m.export_bytes(mi).unwrap().to_vec();
    let db = d.export_bytes(di).unwrap().to_vec();
    let ms = kismet::script(&mb, &Text(&m)).unwrap();
    let ds = kismet::script(&db, &Text(&d)).unwrap();
    println!("ubergraph {} / {} bytes, statements {} / {}", mb.len(), db.len(), ms.stmts.len(), ds.stmts.len());
    assert_eq!(mb.len(), db.len());
    assert_eq!(ms.start, ds.start);
    // Every byte that differs, by statement of the donor.
    let (mut diff, code) = (Vec::new(), ms.start);
    for s in &ds.stmts {
        let r = code + s.range.start..code + s.range.end;
        if mb[r.clone()] != db[r.clone()] { diff.push(s); }
    }
    for s in &diff { println!("differs at {}: {}", s.offset, &s.text[..s.text.len().min(110)]); }
    let restore: Vec<&kismet::Stmt> = diff.iter().copied().filter(|s| s.text.contains("SoundVariant_EngineLoop") || s.text.contains("CallFunc_IsTrackedSoundIdValid_ReturnValue = ")).collect();
    assert_eq!(restore.len(), 2, "engine PlaySound and the guard");
    for s in &restore {
        let r = code + s.range.start..code + s.range.end;
        let (from, to) = (r.clone(), r);
        mb[to].copy_from_slice(&db[from]);
    }
    // The stop after the guard was skipped by jumping, not changed: nothing else to do.
    let after = kismet::script(&mb, &Text(&m)).unwrap();
    assert_eq!(after.memory_size, ms.memory_size);
    let left: Vec<_> = after.stmts.iter().filter(|s| s.text.contains("SoundVariant_") || s.text.contains("IsTrackedSoundIdValid_ReturnValue =")).map(|s| format!("{}: {}", s.offset, &s.text[..s.text.len().min(100)])).collect();
    println!("{left:#?}");
    m.set_export_bytes(mi, mb).unwrap();
    // The sound.
    let p = m.imported_package_names.names.iter().position(|n| n.ends_with("/VEH_Warthog_Engine_Main")).expect("Engine_Main import");
    m.imported_package_names.names[p] = new.clone();
    m.imported_package_names.hashes[p] = name_hash(new);
    let hits: Vec<u32> = m.import_map.iter().filter(|&&v| v >> 62 == 2 && ((v >> 32) & 0x3fff_ffff) as usize == p).map(|&v| v as u32).collect();
    println!("imports of Engine_Main: {hits:?}");
    assert_eq!(hits.len(), 1);
    m.imported_public_export_hashes[hits[0] as usize] = public_export_hash(new.rsplit('/').next().unwrap());
    let out = m.write();
    ZenPackage::parse(&out).unwrap();
    std::fs::write(&a[3], out).unwrap();
}
