//! Comparing two tags field by field.
//!
//! Both payloads are decoded into `path -> rendered value` maps over every
//! materialised field, and the maps are compared. The result is narrative,
//! not ground truth: block elements past the materialisation cap are compared
//! only by count, and a payload that does not decode yields no map at all.
//! The byte comparison is the truth; this is what makes it readable. Shared
//! by `mjolnir tagdiff` (two builds) and the tag editor (two tags, or a tag
//! against its own edits).

use std::collections::BTreeMap;

use crate::view::{Kind, Node};
use crate::TagFile;

/// One field-level difference.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FieldDiff {
    /// `unit/object/bounding radius`, `control points[3]/position`, or a
    /// block's `.../#count`.
    pub path: String,
    /// The value on the first side; `None` when only the second has it.
    pub before: Option<String>,
    /// The value on the second side; `None` when only the first has it.
    pub after: Option<String>,
}

/// Decode a payload into `path -> rendered value` for every materialised
/// field, up to `elements` per block. `None` when it does not decode.
pub fn flatten(buf: &[u8], chunk_len: usize, elements: usize) -> Option<BTreeMap<String, String>> {
    let tag = TagFile::parse(buf, Some(chunk_len)).ok()?;
    let layout = tag.layout().ok()?;
    let block = tag.read_data(&layout).ok()?;
    let nodes = crate::view::root_capped(&layout, &block, elements);
    let mut out = BTreeMap::new();
    for n in &nodes {
        flatten_node(n, "", &mut out);
    }
    Some(out)
}

/// Flatten one node and everything under it into `out`.
pub fn flatten_node(node: &Node, prefix: &str, out: &mut BTreeMap<String, String>) {
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
pub fn diff_maps(a: &BTreeMap<String, String>, b: &BTreeMap<String, String>) -> Vec<FieldDiff> {
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
    fn changed_added_and_removed_fields_are_reported_in_path_order() {
        let a = map(&[("z", "1"), ("a", "same"), ("m", "old")]);
        let b = map(&[("a", "same"), ("m", "new"), ("q", "added")]);
        let d = diff_maps(&a, &b);
        let paths: Vec<&str> = d.iter().map(|f| f.path.as_str()).collect();
        assert_eq!(paths, vec!["m", "q", "z"]);
        assert_eq!(d[0].before.as_deref(), Some("old"));
        assert_eq!(d[0].after.as_deref(), Some("new"));
        assert_eq!(d[1].before, None);
        assert_eq!(d[2].after, None);
        assert!(diff_maps(&a, &a).is_empty());
    }

    #[test]
    fn the_synthetic_block_flattens_with_counts_and_element_paths() {
        let file = crate::patch::tests::synth_block_file();
        let flat = flatten(&file, file.len(), 64).expect("decodes");
        assert_eq!(flat.get("items/#count").map(String::as_str), Some("2"));
        assert!(flat.keys().any(|k| k.starts_with("items[0]/")));
        assert!(flat.keys().any(|k| k.starts_with("items[1]/")));
    }
}
