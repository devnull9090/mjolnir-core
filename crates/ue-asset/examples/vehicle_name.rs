//! Give a cloned vehicle Blueprint its own display name.
//!
//! The prompt "Drive {ItemName}" fills `{ItemName}` from the data asset in
//! `BlamVehicleComponent.VehicleUIDataAsset`, not from a tag. This clones the
//! stock `DA_VehicleHUD_*` the actor imports beside the actor, with `ItemName`
//! as culture-invariant text, and repoints the actor's import at the clone. No
//! string table is involved, so any name works, and stock assets stay stock.
//!
//! vehicle_name <paks> <actor .uasset, or a package leaf in paks> <label> <out dir>
//!
//! Prints `package <path>=<file>` for each package to hand to package_add.
use std::error::Error;
use ue_asset::package::{public_export_hash, NameBatch, ZenPackage};

const HUD_ASSETS: &str = "/Game/UI/Hud/Data/Vehicles/DA_VehicleHUD_";
const PACKAGE_IMPORT: u64 = 2;

fn fail(s: impl Into<String>) -> Box<dyn Error> {
    s.into().into()
}

fn read_leaf(containers: &[ue_iostore::Container], leaf: &str) -> Result<Vec<u8>, Box<dyn Error>> {
    let suffix = format!("/{leaf}.uasset");
    let (c, i) = containers
        .iter()
        .find_map(|c| {
            c.files
                .iter()
                .find(|(p, _)| p.ends_with(&suffix))
                .map(|(_, i)| (c, *i))
        })
        .ok_or_else(|| fail(format!("{leaf} is in no container")))?;
    Ok(ue_iostore::read_chunk(c, &c.chunks[i], None, &[])?)
}

fn u32_at(b: &[u8], at: usize) -> usize {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap()) as usize
}

/// The span of the one string-table `FText` (flags, history 11, table, key).
fn table_text(b: &[u8], names: &[String]) -> Result<(usize, usize), Box<dyn Error>> {
    let hits: Vec<(usize, usize)> = (4..b.len().saturating_sub(13))
        .filter_map(|p| {
            if b[p] != 0x0b
                || u32_at(b, p - 4) != 0
                || u32_at(b, p + 1) >= names.len()
                || u32_at(b, p + 5) != 0
            {
                return None;
            }
            let len = u32_at(b, p + 9);
            let (s, e) = (p + 13, (p + 13).saturating_add(len));
            ((1..=256).contains(&len)
                && e <= b.len()
                && b[e - 1] == 0
                && b[s..e - 1].iter().all(u8::is_ascii_graphic))
            .then_some((p - 4, e))
        })
        .collect();
    match hits.as_slice() {
        [hit] => Ok(*hit),
        _ => Err(fail(format!(
            "expected one string-table text in the data asset, found {}",
            hits.len()
        ))),
    }
}

/// `FText` flags, history -1, "has a string", then the `FString`: ANSI with a
/// positive length, UTF-16 with a negative one, both counting the terminator.
fn invariant_text(label: &str) -> Vec<u8> {
    let mut t = vec![0, 0, 0, 0, 0xff];
    t.extend(1u32.to_le_bytes());
    if label.is_ascii() {
        t.extend((label.len() as i32 + 1).to_le_bytes());
        t.extend(label.as_bytes());
        t.push(0);
    } else {
        let wide: Vec<u16> = label.encode_utf16().chain([0]).collect();
        t.extend((-(wide.len() as i32)).to_le_bytes());
        t.extend(wide.iter().flat_map(|c| c.to_le_bytes()));
    }
    t
}

/// New names change the Zen header's length; keep its distance from
/// CookedHeaderSize, which `ZenPackage::write` preserves verbatim.
fn finish(pkg: &mut ZenPackage, old_header: u32) -> Result<Vec<u8>, Box<dyn Error>> {
    let once = pkg.write();
    let new_header = header_of(&once)?;
    pkg.cooked_header_size = u32::try_from(
        i64::from(pkg.cooked_header_size) + i64::from(new_header) - i64::from(old_header),
    )?;
    Ok(pkg.write())
}

fn header_of(data: &[u8]) -> Result<u32, Box<dyn Error>> {
    Ok(u32::from_le_bytes(data[4..8].try_into()?))
}

fn swap_name(batch: &NameBatch, from: &str, to: &str) -> NameBatch {
    NameBatch::from_names(
        batch
            .names
            .iter()
            .map(|n| if n == from { to.to_string() } else { n.clone() })
            .collect(),
    )
}

fn main() -> Result<(), Box<dyn Error>> {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let [paks, actor, label, out] = a.as_slice() else {
        return Err(fail(
            "vehicle_name <paks> <actor .uasset or leaf> <label> <out dir>",
        ));
    };
    if label.trim().is_empty() || label.contains('\0') {
        return Err(fail("the label needs text"));
    }
    let containers = ue_iostore::load_all(paks)?;
    let actor_data = if std::path::Path::new(actor).is_file() {
        std::fs::read(actor)?
    } else {
        read_leaf(&containers, actor)?
    };
    let actor_header = header_of(&actor_data)?;
    let mut bp = ZenPackage::parse(&actor_data)?;
    let before = ZenPackage::parse(&actor_data)?;
    let actor_path = bp.name();
    let (folder, actor_leaf) = actor_path.rsplit_once('/').ok_or("actor path")?;
    let stem = actor_leaf
        .strip_prefix("BP_")
        .filter(|_| actor_path.starts_with("/Game/MJOLNIR/Vehicles/"))
        .ok_or_else(|| fail(format!("{actor_path} is not a cloned vehicle actor")))?;
    let new_leaf = format!("DA_{stem}_HUD");
    let new_path = format!("{folder}/{new_leaf}");

    // The stock asset this actor shows, and the one import that reaches it.
    let stock: Vec<(usize, String)> = bp
        .imported_package_names
        .names
        .iter()
        .enumerate()
        .filter(|(_, n)| n.starts_with(HUD_ASSETS))
        .map(|(i, n)| (i, n.clone()))
        .collect();
    let [(package, stock_path)] = stock.as_slice() else {
        return Err(fail(format!(
            "{actor_path} imports {} stock vehicle HUD asset(s), not 1: start from an unnamed clone",
            stock.len()
        )));
    };
    let stock_leaf = stock_path.rsplit('/').next().ok_or("stock leaf")?;
    let uses: Vec<usize> = bp
        .import_map
        .iter()
        .filter(|i| **i >> 62 == PACKAGE_IMPORT && (**i >> 32) & 0x3fff_ffff == *package as u64)
        .map(|i| (*i & 0xffff_ffff) as usize)
        .collect();
    let [slot] = uses.as_slice() else {
        return Err(fail(format!("{stock_leaf}: {} imports, not 1", uses.len())));
    };
    if bp.imported_public_export_hashes[*slot] != public_export_hash(stock_leaf) {
        return Err(fail(format!("{stock_leaf}: import hash does not match")));
    }

    // The clone: same class and icons, its own identity and name.
    let data = read_leaf(&containers, stock_leaf)?;
    let data_header = header_of(&data)?;
    let mut da = ZenPackage::parse(&data)?;
    if da.export_map.len() != 1 {
        return Err(fail(format!("{stock_leaf}: expected one export")));
    }
    let mut block = da.export_bytes(0).ok_or("data asset export")?.to_vec();
    let (start, end) = table_text(&block, &da.names.names)?;
    let key = String::from_utf8_lossy(&block[start + 17..end - 1]).to_string();
    let text = invariant_text(label);
    block.splice(start..end, text.iter().copied());
    da.names = swap_name(
        &swap_name(&da.names, stock_path, &new_path),
        stock_leaf,
        &new_leaf,
    );
    da.export_map[0].public_export_hash = public_export_hash(&new_leaf);
    da.set_export_bytes(0, block)?;
    let da_out = finish(&mut da, data_header)?;

    // The actor: one imported package name, one hash; nothing else moves.
    bp.imported_public_export_hashes[*slot] = public_export_hash(&new_leaf);
    bp.imported_package_names = swap_name(&bp.imported_package_names, stock_path, &new_path);
    bp.names = swap_name(&bp.names, stock_path, &new_path);
    let bp_out = finish(&mut bp, actor_header)?;

    // Read both back before anything is written.
    let r = ZenPackage::parse(&da_out)?;
    let e = r.export_map[0];
    let body = r.export_bytes(0).ok_or("clone export")?;
    if r.name() != new_path
        || r.mapped_name(e.name_index, e.name_number) != new_leaf
        || e.public_export_hash != public_export_hash(&new_leaf)
        || body[start..start + text.len()] != text[..]
    {
        return Err(fail("the data asset did not read back"));
    }
    let r = ZenPackage::parse(&bp_out)?;
    let same_exports =
        (0..before.export_map.len()).all(|i| r.export_bytes(i) == before.export_bytes(i));
    let changed = (0..r.imported_public_export_hashes.len())
        .filter(|i| r.imported_public_export_hashes[*i] != before.imported_public_export_hashes[*i])
        .count();
    if r.name() != actor_path
        || !same_exports
        || r.import_map != before.import_map
        || changed != 1
        || r.imported_package_names.names[*package] != new_path
    {
        return Err(fail("the actor did not read back"));
    }

    std::fs::create_dir_all(out)?;
    let da_file = format!("{out}/{new_leaf}.uasset");
    let bp_file = format!("{out}/{actor_leaf}.uasset");
    std::fs::write(&da_file, da_out)?;
    std::fs::write(&bp_file, bp_out)?;
    println!("{actor_path}: {stock_leaf} ({key}) -> {new_leaf} = {label:?}");
    println!("package {new_path}={da_file}");
    println!("package {actor_path}={bp_file}");
    Ok(())
}
