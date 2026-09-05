//! `mjolnir zen-roundtrip`: the gate behind writing tag wrappers.
//!
//! Every shipped tag `.uasset` is parsed with [`ue_asset::package::ZenPackage`]
//! and serialized again; the bytes must come back. Alongside, each of the
//! derivation rules a from-scratch wrapper builder relies on is counted over
//! the same corpus — name hashes, export hash, class and CDO import indices,
//! import slot order, flags, the cooked-header-size formula, the export body
//! frame, the name-map order, the bundle shapes, the package id — so a rule
//! that holds for 12,290 of 12,291 packages is reported as exactly that, not
//! assumed.

use std::collections::BTreeMap;

use anyhow::{Context, Result};
use clap::Args;
use ue_asset::package::{self, ZenPackage};

#[derive(Args)]
pub struct ZenRoundtripArgs {
    #[command(flatten)]
    src: crate::Source,
    /// Stop after this many packages (default: every tag wrapper).
    #[arg(long)]
    limit: Option<usize>,
    /// Only packages whose path contains this text.
    #[arg(long)]
    filter: Option<String>,
    /// Print the packages that fail the byte round trip or a rule (up to eight
    /// per rule).
    #[arg(long)]
    verbose: bool,
    /// Write one CSV row per package with the quantities the cooked-header-size
    /// formula is fitted from.
    #[arg(long)]
    fit: Option<std::path::PathBuf>,
}

#[derive(Default)]
struct Tally {
    seen: usize,
    parse_failed: usize,
    exact: usize,
    rules: BTreeMap<&'static str, (usize, usize)>,
    flags: BTreeMap<(u32, u32), usize>,
    failures: BTreeMap<&'static str, Vec<String>>,
}

const FAILURES_PER_RULE: usize = 8;

impl Tally {
    fn rule(&mut self, name: &'static str, ok: bool, what: &str, verbose: bool) {
        let e = self.rules.entry(name).or_default();
        e.1 += 1;
        if ok {
            e.0 += 1;
        } else if verbose {
            let list = self.failures.entry(name).or_default();
            if list.len() < FAILURES_PER_RULE {
                list.push(what.replace("../../../Meteorite/Content/Tags/", ""));
            }
        }
    }
}

pub use ue_asset::package::{wrapper_class, BLAM_MODULE};

pub fn run(a: ZenRoundtripArgs) -> Result<()> {
    let containers = ue_iostore::load_all(&a.src.paks)?;
    let oodle = a.src.oodle_roots();
    let mut t = Tally::default();
    let module_index = package::script_import_index(BLAM_MODULE);
    let mut fit_rows = String::from(
        "cooked_header_size,pkg_len,obj_len,class_len,imported_pkgs,imported_name_bytes,ipeh,import_slots,dep_entries,names,name_bytes,body_len,group,package\n",
    );

    'outer: for c in &containers {
        let mut files: Vec<(&String, &usize)> = c.files.iter().collect();
        files.sort();
        for (rel, chunk_index) in files {
            let full = c.full_path(rel);
            if !full.ends_with(".uasset") || !full.contains("/Tags/") {
                continue;
            }
            if let Some(f) = &a.filter {
                if !full.contains(f.as_str()) {
                    continue;
                }
            }
            if a.limit.is_some_and(|n| t.seen >= n) {
                break 'outer;
            }
            t.seen += 1;
            let chunk = c.chunks[*chunk_index];
            let data = ue_iostore::read_chunk(c, &chunk, None, &oodle)
                .with_context(|| format!("reading {full}"))?;
            let pkg = match ZenPackage::parse(&data) {
                Ok(p) => p,
                Err(e) => {
                    t.parse_failed += 1;
                    if a.verbose {
                        t.failures
                            .entry("parse")
                            .or_default()
                            .push(format!("{full}: {e}"));
                    }
                    continue;
                }
            };
            let again = pkg.write();
            if again == data {
                t.exact += 1;
            } else if a.verbose {
                let at = again
                    .iter()
                    .zip(&data)
                    .position(|(x, y)| x != y)
                    .unwrap_or(again.len().min(data.len()));
                t.failures.entry("bytes").or_default().push(format!(
                    "{full}: differs at {at:#x} ({} written vs {} shipped)",
                    again.len(),
                    data.len()
                ));
            }

            // --- the rules ---------------------------------------------------
            let v = a.verbose;
            let name = pkg.name();
            let leaf = name.rsplit('/').next().unwrap_or("").to_string();
            let group = leaf.rsplit_once('-').map(|(_, g)| g).unwrap_or("");
            let class = wrapper_class(group);
            let class_path = format!("{BLAM_MODULE}.{class}");
            let cdo_path = format!("{BLAM_MODULE}.Default__{class}");

            let names_ok = pkg
                .names
                .names
                .iter()
                .zip(&pkg.names.hashes)
                .all(|(n, h)| package::name_hash(n) == *h);
            t.rule("name hashes = city(lowercase)", names_ok, &full, v);

            t.rule("exactly one export", pkg.export_map.len() == 1, &full, v);
            let Some(e) = pkg.export_map.first().copied() else {
                continue;
            };
            let object = pkg.mapped_name(e.name_index, e.name_number);
            t.rule(
                "public export hash = city(utf16 lowercase leaf)",
                package::public_export_hash(&object) == e.public_export_hash,
                &full,
                v,
            );
            t.rule(
                "class = Blam<Pascal(group)>TagDataAsset",
                package::script_import_index(&class_path) == e.class,
                &format!("{full} ({class})"),
                v,
            );
            t.rule(
                "template = Default__ of the class",
                package::script_import_index(&cdo_path) == e.template,
                &full,
                v,
            );
            t.rule(
                "outer and super are null",
                e.outer == u64::MAX && e.super_ == u64::MAX,
                &full,
                v,
            );

            let scripts: Vec<u64> = pkg
                .import_map
                .iter()
                .copied()
                .filter(|i| *i >> 62 == 1)
                .collect();
            t.rule(
                "exactly three script imports",
                scripts.len() == 3,
                &format!("{full} ({})", scripts.len()),
                v,
            );
            t.rule(
                "script imports are {CDO, class, module}",
                scripts.contains(&e.template)
                    && scripts.contains(&e.class)
                    && scripts.contains(&module_index),
                &full,
                v,
            );
            // A package import is `(imported package index << 32) | index into
            // the imported public export hashes`, under the type-2 tag.
            let mut package_imports: Vec<(u64, u64)> = pkg
                .import_map
                .iter()
                .copied()
                .filter(|i| *i >> 62 == 2)
                .map(|i| ((i >> 32) & 0x3FFF_FFFF, i & 0xFFFF_FFFF))
                .collect();
            package_imports.sort_unstable_by_key(|(_, h)| *h);
            t.rule(
                "package imports = (package index << 32 | hash index), each hash once",
                package_imports.len() == pkg.imported_public_export_hashes.len()
                    && package_imports.iter().enumerate().all(|(i, (p, h))| {
                        *h == i as u64 && (*p as usize) < pkg.imported_package_names.names.len()
                    }),
                &format!(
                    "{full} ({:?} vs {} hashes)",
                    package_imports,
                    pkg.imported_public_export_hashes.len()
                ),
                v,
            );
            t.rule(
                "dependency entries name import slots",
                pkg.dependency_bundle_entries
                    .iter()
                    .all(|d| *d < 0 && ((-d - 1) as usize) < pkg.import_map.len()),
                &full,
                v,
            );
            t.rule(
                "imported name numbers are zero",
                pkg.imported_package_name_numbers.iter().all(|n| *n == 0),
                &full,
                v,
            );
            let nulls = pkg.import_map.iter().filter(|i| **i == u64::MAX).count();
            t.rule(
                "one null import slot per imported package",
                nulls == pkg.imported_package_names.names.len(),
                &format!(
                    "{full} ({nulls} nulls, {} packages)",
                    pkg.imported_package_names.names.len()
                ),
                v,
            );

            *t.flags
                .entry((e.object_flags, pkg.package_flags))
                .or_default() += 1;
            let generated = matches!(
                group,
                "scenario"
                    | "scenario_structure_bsp"
                    | "scenario_structure_lighting_info"
                    | "structure_design"
                    | "structure_seams"
            );
            let expect_flags = if generated {
                (0x1, 0x8800_2200)
            } else {
                (0xb, 0x8000_2200)
            };
            t.rule(
                "flags 0xb/0x80002200, generated groups 0x1/0x88002200 (sound may drop transactional)",
                (e.object_flags, pkg.package_flags) == expect_flags
                    || (group == "sound" || group == "ai_mission_dialogue") && (e.object_flags, pkg.package_flags) == (0x3, 0x8000_2200),
                &format!("{full} ({:#x}/{:#x})", e.object_flags, pkg.package_flags),
                v,
            );

            if a.fit.is_some() {
                fit_rows.push_str(&format!(
                    "{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n",
                    pkg.cooked_header_size,
                    name.len(),
                    object.len(),
                    class.len(),
                    pkg.imported_package_names.names.len(),
                    pkg.imported_package_names
                        .names
                        .iter()
                        .map(|n| n.len())
                        .sum::<usize>(),
                    pkg.imported_public_export_hashes.len(),
                    pkg.import_map.len(),
                    pkg.dependency_bundle_entries.len(),
                    pkg.names.names.len(),
                    pkg.names.names.iter().map(|n| n.len()).sum::<usize>(),
                    pkg.export_data.len(),
                    group,
                    name,
                ));
            }
            t.rule(
                "cooked header size = 617 + 2·pkg + obj + 2·class",
                pkg.cooked_header_size as usize
                    == 617 + 2 * name.len() + object.len() + 2 * class.len(),
                &format!(
                    "{full} ({} vs {})",
                    pkg.cooked_header_size,
                    617 + 2 * name.len() + object.len() + 2 * class.len()
                ),
                v,
            );

            let bulk_ok = pkg.bulk.len() == 1
                && pkg.bulk[0].serial_offset == 0
                && pkg.bulk[0].duplicate_serial_offset == -1
                && pkg.bulk[0].flags == 66_817
                && pkg.bulk[0].cooked_index == 0;
            t.rule("one bulk entry {0, -1, size, 66817, 0}", bulk_ok, &full, v);
            let ubulk_len = c
                .files
                .get(&rel.replace(".uasset", ".ubulk"))
                .map(|i| c.chunks[*i].length as i64);
            t.rule(
                "bulk serial size = .ubulk length",
                ubulk_len == pkg.bulk.first().map(|b| b.serial_size),
                &format!(
                    "{full} ({:?} vs {:?})",
                    pkg.bulk.first().map(|b| b.serial_size),
                    ubulk_len
                ),
                v,
            );

            let body = &pkg.export_data;
            t.rule(
                "export body = [0000][fragments][values][0000]",
                body.len() >= 8 && body[..4] == [0; 4] && body[body.len() - 4..] == [0; 4],
                &full,
                v,
            );
            t.rule(
                "export data length = cooked serial size",
                body.len() as u64 == e.cooked_serial_size,
                &full,
                v,
            );
            t.rule("package trailer present", pkg.trailer, &full, v);

            let n = pkg.names.names.len();
            let tail_ok =
                n >= 2 && pkg.names.names[n - 1] == name && pkg.names.names[n - 2] == object;
            let head_sorted = n >= 2
                && pkg.names.names[..n - 2]
                    .windows(2)
                    .all(|w| w[0].to_lowercase() <= w[1].to_lowercase());
            t.rule(
                "name map = sorted(property names) + [object, package]",
                tail_ok && head_sorted,
                &full,
                v,
            );

            t.rule(
                "export bundle = [Create 0, Serialize 0]",
                pkg.export_bundle_entries == [(0, 0), (0, 1)],
                &full,
                v,
            );
            let dep = pkg
                .dependency_bundle_headers
                .first()
                .copied()
                .unwrap_or_default();
            t.rule(
                "one dependency header (0; 0,0,N,0), N = entries",
                pkg.dependency_bundle_headers.len() == 1
                    && dep.first_entry_index == 0
                    && dep.counts[0] == 0
                    && dep.counts[1] == 0
                    && dep.counts[3] == 0
                    && dep.counts[2] as usize == pkg.dependency_bundle_entries.len(),
                &format!(
                    "{full} ({:?} / {} entries)",
                    dep,
                    pkg.dependency_bundle_entries.len()
                ),
                v,
            );
            t.rule(
                "pad is zero bytes",
                pkg.pad.iter().all(|b| *b == 0),
                &full,
                v,
            );
            t.rule(
                "pad aligns the bulk map to 8",
                pkg.pad.len() == (8 - (package::SUMMARY + pkg.names.serialized_len() + 8) % 8) % 8,
                &format!("{full} (pad {})", pkg.pad.len()),
                v,
            );
            if pkg.is_bare() {
                let rebuilt = ZenPackage::bare_tag(group, &name, pkg.bulk[0].serial_size as u64);
                t.rule(
                    "bare wrappers rebuild from (group, path, length) byte-exact",
                    rebuilt.write() == data,
                    &format!(
                        "{full} (cooked {} vs {})",
                        rebuilt.cooked_header_size, pkg.cooked_header_size
                    ),
                    v,
                );
            }
            t.rule(
                "package id = city(utf16 lowercase package name)",
                ue_iostore::city::package_id(&name) == chunk.chunk_id,
                &full,
                v,
            );
            t.rule(
                "imported packages sorted by id",
                pkg.imported_package_names.names.windows(2).all(|w| {
                    ue_iostore::city::package_id(&w[0]) <= ue_iostore::city::package_id(&w[1])
                }),
                &full,
                v,
            );
        }
    }

    if let Some(path) = &a.fit {
        std::fs::write(path, &fit_rows)?;
        println!("fit rows written to {}", path.display());
    }
    println!(
        "{} tag wrappers, {} parsed, {} byte-exact after re-serialization",
        t.seen,
        t.seen - t.parse_failed,
        t.exact
    );
    println!("\nrules (holds / checked):");
    for (name, (ok, all)) in &t.rules {
        println!("  {ok:>6} / {all:<6}  {name}");
    }
    println!("\nflag pairs (object flags, package flags):");
    for ((o, p), n) in &t.flags {
        println!("  {n:>6}  {o:#x} / {p:#010x}");
    }
    for (rule, list) in &t.failures {
        println!("\n{rule} — first {}:", list.len());
        for f in list {
            println!("  {f}");
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn group_names_become_wrapper_classes() {
        assert_eq!(wrapper_class("biped"), "BlamBipedTagDataAsset");
        assert_eq!(
            wrapper_class("frame_event_list"),
            "BlamFrameEventListTagDataAsset"
        );
        assert_eq!(
            wrapper_class("scenario_structure_bsp"),
            "BlamScenarioStructureBspTagDataAsset"
        );
    }
}
