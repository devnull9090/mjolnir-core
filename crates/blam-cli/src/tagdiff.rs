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
use blam_tag::view::{Kind, Node};
use blam_tag::TagFile;
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

/// One field-level difference inside a changed tag.
struct FieldDiff {
    path: String,
    before: Option<String>,
    after: Option<String>,
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

    let by_path_a: BTreeMap<&str, &index::TagEntry> =
        idx_a.tags.iter().map(|t| (t.path.as_str(), t)).collect();
    let by_path_b: BTreeMap<&str, &index::TagEntry> =
        idx_b.tags.iter().map(|t| (t.path.as_str(), t)).collect();

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

/// Decode a payload into `path -> rendered value` for every materialised field.
fn flatten(buf: &[u8], chunk_len: usize, elements: usize) -> Option<BTreeMap<String, String>> {
    let tag = TagFile::parse(buf, Some(chunk_len)).ok()?;
    let layout = tag.layout().ok()?;
    let block = tag.read_data(&layout).ok()?;
    let nodes = blam_tag::view::root_capped(&layout, &block, elements);
    let mut out = BTreeMap::new();
    for n in &nodes {
        flatten_node(n, "", &mut out);
    }
    Some(out)
}

fn flatten_node(node: &Node, prefix: &str, out: &mut BTreeMap<String, String>) {
    let path = if prefix.is_empty() {
        node.name.clone()
    } else if node.kind == Kind::Element {
        // Element names are already `[i]`; gluing them without a separator
        // reads as indexing: `control points[3]/position`.
        format!("{prefix}{}", node.name)
    } else {
        format!("{prefix}/{}", node.name)
    };
    match node.kind {
        Kind::Field => {
            let shown = node.value.display();
            if !shown.is_empty() {
                out.insert(path, shown);
            }
        }
        Kind::Block | Kind::Array => {
            if let Some(count) = node.count {
                out.insert(format!("{path}/#count"), count.to_string());
            }
            for child in &node.children {
                flatten_node(child, &path, out);
            }
        }
        Kind::Struct | Kind::Element => {
            for child in &node.children {
                flatten_node(child, &path, out);
            }
        }
    }
}

/// Differences between two flattened payloads, in path order.
fn diff_maps(a: &BTreeMap<String, String>, b: &BTreeMap<String, String>) -> Vec<FieldDiff> {
    let mut out = Vec::new();
    for (path, va) in a {
        match b.get(path) {
            Some(vb) if va == vb => {}
            Some(vb) => out.push(FieldDiff {
                path: path.clone(),
                before: Some(va.clone()),
                after: Some(vb.clone()),
            }),
            None => out.push(FieldDiff {
                path: path.clone(),
                before: Some(va.clone()),
                after: None,
            }),
        }
    }
    for (path, vb) in b {
        if !a.contains_key(path) {
            out.push(FieldDiff {
                path: path.clone(),
                before: None,
                after: Some(vb.clone()),
            });
        }
    }
    out.sort_by(|x, y| x.path.cmp(&y.path));
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn map(pairs: &[(&str, &str)]) -> BTreeMap<String, String> {
        pairs
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect()
    }

    #[test]
    fn diff_reports_changed_added_and_removed_paths() {
        let a = map(&[("jump velocity", "0.14"), ("gone", "1"), ("same", "x")]);
        let b = map(&[("jump velocity", "0.2"), ("new", "2"), ("same", "x")]);
        let d = diff_maps(&a, &b);
        let rendered: Vec<String> = d
            .iter()
            .map(|f| {
                format!(
                    "{} {:?}->{:?}",
                    f.path,
                    f.before.as_deref(),
                    f.after.as_deref()
                )
            })
            .collect();
        assert_eq!(
            rendered,
            vec![
                "gone Some(\"1\")->None",
                "jump velocity Some(\"0.14\")->Some(\"0.2\")",
                "new None->Some(\"2\")",
            ]
        );
    }

    #[test]
    fn identical_maps_diff_empty() {
        let a = map(&[("x", "1")]);
        assert!(diff_maps(&a, &a).is_empty());
    }
}
