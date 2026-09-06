//! `mjolnir tagdiff` — what changed in the tag data between two builds.
//!
//! The game updates in place, so "what did this patch change" is only
//! answerable while both builds exist somewhere — the previous one as a
//! snapshot (`tools/game_snapshot.py materialize`), the current one as the
//! install. Given the two `Paks` directories this walks every shipped tag,
//! sorts each into added, removed, changed or identical by payload bytes, and
//! for the changed ones decodes both payloads and reports the differences
//! field by field.
//!
//! The field diff is best-effort narrative, not ground truth: block elements
//! past the materialisation cap are compared only by count, and a tag whose
//! payload no longer decodes is still reported as changed by its bytes. The
//! byte comparison is the truth; the field list is what makes it readable.

use std::collections::BTreeMap;
use std::path::PathBuf;

use anyhow::{Context, Result};
use blam_tag::diff::{diff_maps, flatten, FieldDiff};
use clap::Args;

use crate::index;

#[derive(Args)]
pub struct TagDiffArgs {
    /// The older build's `Meteorite/Content/Paks` directory.
    #[arg(long)]
    paks_a: PathBuf,
    /// The newer build's `Meteorite/Content/Paks` directory.
    #[arg(long)]
    paks_b: PathBuf,
    /// Path to `oo2core_*_win64.dll`, or a directory containing one. Optional:
    /// without it the built-in decoder is used.
    #[arg(long, env = "OODLE")]
    oodle: Option<PathBuf>,
    /// Version label for the older build, recorded in the report.
    #[arg(long, default_value = "")]
    label_a: String,
    /// Version label for the newer build, recorded in the report.
    #[arg(long, default_value = "")]
    label_b: String,
    /// Write the full report as JSON here.
    #[arg(long)]
    json: Option<PathBuf>,
    /// Field differences shown per changed tag; the JSON always carries all of
    /// them.
    #[arg(long, default_value_t = 12)]
    show: usize,
    /// Block elements decoded per block. Elements past this compare by count
    /// only, which keeps a scenario_structure_bsp from costing gigabytes.
    #[arg(long, default_value_t = 256)]
    elements: usize,
}

struct ChangedTag {
    group: String,
    path: String,
    size_a: u64,
    size_b: u64,
    first_diff: Option<usize>,
    /// None when either payload failed to decode.
    fields: Option<Vec<FieldDiff>>,
}

pub fn run(a: TagDiffArgs) -> Result<()> {
    let oodle: Vec<PathBuf> = a.oodle.clone().into_iter().collect();
    let idx_a = index::build(&a.paks_a).context("older build")?;
    let idx_b = index::build(&a.paks_b).context("newer build")?;

    // Keyed case-insensitively: the CU4 re-cook changed the *casing* of whole
    // cinematic directories (`Cinematics/A10/` became `Cinematics/a10/`), and
    // an exact match reports every tag in a re-cased folder as removed plus
    // added. Windows resolves these to the same asset; so does this diff.
    let by_path_a: BTreeMap<String, &index::TagEntry> = idx_a
        .tags
        .iter()
        .map(|t| (t.path.to_ascii_lowercase(), t))
        .collect();
    let by_path_b: BTreeMap<String, &index::TagEntry> = idx_b
        .tags
        .iter()
        .map(|t| (t.path.to_ascii_lowercase(), t))
        .collect();

    let added: Vec<&index::TagEntry> = by_path_b
        .iter()
        .filter(|(p, _)| !by_path_a.contains_key(*p))
        .map(|(_, e)| *e)
        .collect();
    let removed: Vec<&index::TagEntry> = by_path_a
        .iter()
        .filter(|(p, _)| !by_path_b.contains_key(*p))
        .map(|(_, e)| *e)
        .collect();

    let mut identical = 0usize;
    let mut unreadable = 0usize;
    let mut changed: Vec<ChangedTag> = Vec::new();
    let common: Vec<(&index::TagEntry, &index::TagEntry)> = by_path_a
        .iter()
        .filter_map(|(p, ea)| by_path_b.get(p).map(|eb| (*ea, *eb)))
        .collect();

    for (i, (ea, eb)) in common.iter().enumerate() {
        if i % 1000 == 0 {
            eprintln!("  {i}/{} compared", common.len());
        }
        let (Ok(buf_a), Ok(buf_b)) = (
            idx_a.read(ea, None, &oodle),
            idx_b.read(eb, None, &oodle),
        ) else {
            unreadable += 1;
            continue;
        };
        if buf_a == buf_b {
            identical += 1;
            continue;
        }
        let first_diff = buf_a
            .iter()
            .zip(buf_b.iter())
            .position(|(x, y)| x != y)
            .or(Some(buf_a.len().min(buf_b.len())));
        let flat_a = flatten(&buf_a, ea.chunk.length as usize, a.elements);
        let flat_b = flatten(&buf_b, eb.chunk.length as usize, a.elements);
        let fields = match (flat_a, flat_b) {
            (Some(fa), Some(fb)) => Some(diff_maps(&fa, &fb)),
            _ => None,
        };
        changed.push(ChangedTag {
            group: ea.group.clone(),
            path: ea.path.clone(),
            size_a: buf_a.len() as u64,
            size_b: buf_b.len() as u64,
            first_diff,
            fields,
        });
    }

    for e in &added {
        println!("ADDED    {:<24} {}", e.group, e.path);
    }
    for e in &removed {
        println!("REMOVED  {:<24} {}", e.group, e.path);
    }
    for c in &changed {
        println!(
            "CHANGED  {:<24} {}  ({} -> {} bytes)",
            c.group, c.path, c.size_a, c.size_b
        );
        match &c.fields {
            Some(fields) => {
                for d in fields.iter().take(a.show) {
                    match (&d.before, &d.after) {
                        (Some(x), Some(y)) => println!("    {}: {} -> {}", d.path, x, y),
                        (None, Some(y)) => println!("    {} added: {}", d.path, y),
                        (Some(x), None) => println!("    {} removed: was {}", d.path, x),
                        (None, None) => {}
                    }
                }
                if fields.len() > a.show {
                    println!("    ... {} more field differences", fields.len() - a.show);
                }
                if fields.is_empty() {
                    // Bytes moved but no materialised field did: the change is
                    // past the element cap or in a section the view skips.
                    println!("    (no difference within the first {} elements per block)", a.elements);
                }
            }
            None => println!("    (payload differs but does not decode; byte-level only)"),
        }
    }
    println!(
        "# {} tags: {} added, {} removed, {} changed, {} identical, {} unreadable",
        common.len() + added.len() + removed.len(),
        added.len(),
        removed.len(),
        changed.len(),
        identical,
        unreadable
    );

    if let Some(out) = &a.json {
        let report = serde_json::json!({
            "generator": "mjolnir tagdiff",
            "from": a.label_a,
            "to": a.label_b,
            "tags": common.len() + added.len() + removed.len(),
            "identical": identical,
            "unreadable": unreadable,
            "added": added.iter().map(|e| serde_json::json!({
                "group": e.group, "path": e.path, "bytes": e.chunk.length,
            })).collect::<Vec<_>>(),
            "removed": removed.iter().map(|e| serde_json::json!({
                "group": e.group, "path": e.path,
            })).collect::<Vec<_>>(),
            "changed": changed.iter().map(|c| serde_json::json!({
                "group": c.group,
                "path": c.path,
                "bytes_before": c.size_a,
                "bytes_after": c.size_b,
                "first_diff_offset": c.first_diff,
                "decoded": c.fields.is_some(),
                "fields": c.fields.as_ref().map(|fields| fields.iter().map(|d| serde_json::json!({
                    "path": d.path, "before": d.before, "after": d.after,
                })).collect::<Vec<_>>()),
            })).collect::<Vec<_>>(),
        });
        std::fs::write(out, serde_json::to_string_pretty(&report)? + "\n")
            .with_context(|| format!("writing {}", out.display()))?;
        eprintln!("# wrote {}", out.display());
    }
    Ok(())
}
