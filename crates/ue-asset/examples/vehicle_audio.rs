//! New event and sound packages for a vehicle's own Wwise bank.
//!
//!   vehicle_audio <Stop event .uasset> <HaloAudioSound .uasset> <out dir>
//!       <package folder> <sound name> <bank name> <bank id> <play id> <stop id>
//!
//! Clones a shipped Stop event twice, as `Play_<sound>` and `Stop_<sound>`, and
//! a shipped HaloAudioSound as `HS_<sound>`, which names the two. Every name
//! comes from the caller, so two maps' packages and ids never meet
//! (tools/level/ce_vehicle_audio.py). Prints `<package>=<file>` for each, the
//! shape `package_add --package` takes.
//!
//! The event template is the Warthog horn's: its bank name, bank id and event id
//! are the constants below, and each is checked as it is replaced, so another
//! template fails here rather than making a package that names the wrong bank.
use ue_asset::package::{name_hash, public_export_hash, ZenPackage};

const TEMPLATE_BANK: u32 = 833622567;
const TEMPLATE_EVENT: u32 = 3182413213;
const TEMPLATE_BANK_NAME: &str = "VE_Warthog";

fn set_name(z: &mut ZenPackage, old: &str, new: &str) {
    let i = z
        .names
        .names
        .iter()
        .position(|n| n == old)
        .unwrap_or_else(|| panic!("no name {old}"));
    z.names.names[i] = new.to_string();
    z.names.hashes[i] = name_hash(new);
}

fn replace_u32(b: &mut [u8], old: u32, new: u32, want: usize) {
    let (o, n) = (old.to_le_bytes(), new.to_le_bytes());
    let (mut count, mut i) = (0, 0);
    while i + 4 <= b.len() {
        if b[i..i + 4] == o {
            b[i..i + 4].copy_from_slice(&n);
            count += 1;
            i += 4;
        } else {
            i += 1;
        }
    }
    assert_eq!(count, want, "{old:#x} occurrences");
}

fn rename(z: &mut ZenPackage, path: &str) {
    let leaf = path.rsplit('/').next().unwrap();
    let old_path = z.name();
    let old_leaf = old_path.rsplit('/').next().unwrap().to_string();
    set_name(z, &old_path, path);
    set_name(z, &old_leaf, leaf);
    z.export_map[0].public_export_hash = public_export_hash(leaf);
}

/// One event: the template's last four fields are the longest and shortest
/// duration, whether it loops, and the attenuation's maximum radius.
fn event(
    template: &[u8],
    path: &str,
    bank_name: &str,
    bank: u32,
    id: u32,
    tail: (f32, f32, u32, f32),
) -> Vec<u8> {
    let mut z = ZenPackage::parse(template).unwrap();
    assert_eq!(z.write(), template, "template round trip");
    rename(&mut z, path);
    set_name(&mut z, &format!("{TEMPLATE_BANK}.bnk"), &format!("{bank}.bnk"));
    set_name(&mut z, TEMPLATE_BANK_NAME, bank_name);
    let mut e = z.export_bytes(0).unwrap().to_vec();
    replace_u32(&mut e, TEMPLATE_EVENT, id, 2);
    replace_u32(&mut e, TEMPLATE_BANK, bank, 1);
    let n = e.len();
    e[n - 16..n - 12].copy_from_slice(&tail.0.to_le_bytes());
    e[n - 12..n - 8].copy_from_slice(&tail.1.to_le_bytes());
    e[n - 8..n - 4].copy_from_slice(&tail.2.to_le_bytes());
    e[n - 4..].copy_from_slice(&tail.3.to_le_bytes());
    z.set_export_bytes(0, e).unwrap();
    z.write()
}

/// The imported package whose leaf starts `prefix` becomes `new`: its name, its
/// hash, and the public export hash of the one import that names it.
fn retarget(z: &mut ZenPackage, prefix: &str, new: &str) {
    let p = z
        .imported_package_names
        .names
        .iter()
        .position(|n| n.rsplit('/').next().unwrap().starts_with(prefix))
        .unwrap_or_else(|| panic!("no import {prefix}"));
    z.imported_package_names.names[p] = new.to_string();
    z.imported_package_names.hashes[p] = name_hash(new);
    let hits: Vec<u32> = z
        .import_map
        .iter()
        .filter(|&&v| v >> 62 == 2 && ((v >> 32) & 0x3fff_ffff) as usize == p)
        .map(|&v| v as u32)
        .collect();
    assert_eq!(hits.len(), 1, "imports of {prefix}");
    z.imported_public_export_hashes[hits[0] as usize] =
        public_export_hash(new.rsplit('/').next().unwrap());
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    if a.len() != 9 {
        eprintln!(
            "usage: vehicle_audio <stop event> <sound> <out dir> <package folder> <sound name> \
             <bank name> <bank id> <play id> <stop id>"
        );
        std::process::exit(2);
    }
    let stop_event = std::fs::read(&a[0]).unwrap();
    let sound = std::fs::read(&a[1]).unwrap();
    let (out, folder, name, bank_name) = (&a[2], &a[3], &a[4], &a[5]);
    let id = |i: usize| a[i].parse::<u32>().unwrap();
    let (bank, play, stop) = (id(6), id(7), id(8));

    let play_path = format!("{folder}/Play_{name}");
    let stop_path = format!("{folder}/Stop_{name}");
    let sound_path = format!("{folder}/HS_{name}");
    let mut list = vec![
        (
            play_path.clone(),
            event(&stop_event, &play_path, bank_name, bank, play, (0.0, 0.0, 1, 8000.0)),
        ),
        (
            stop_path.clone(),
            event(&stop_event, &stop_path, bank_name, bank, stop, (0.0, 0.0, 0, 0.0)),
        ),
    ];
    let mut z = ZenPackage::parse(&sound).unwrap();
    assert_eq!(z.write(), sound, "template round trip");
    rename(&mut z, &sound_path);
    retarget(&mut z, "Play_", &play_path);
    retarget(&mut z, "Stop_", &stop_path);
    list.push((sound_path, z.write()));

    for (path, bytes) in &list {
        let file = format!("{out}/{}.uasset", path.rsplit('/').next().unwrap());
        std::fs::write(&file, bytes).unwrap();
        ZenPackage::parse(bytes).unwrap();
        println!("{path}={file}");
    }
}
