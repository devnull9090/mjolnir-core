//! A graph that inherits: a few animations of its own, the rest from a parent.
//!
//! The game merges a parent's rows into a graph at load, by label, and a row
//! the graph has itself wins. So a graph that changes three animations of a
//! large one need only hold those three and the rows that play them, which
//! takes it from the size of the parent to the size of the three.
//!
//! The skeleton and everything the kept animations index stay as they are:
//! sound and effect references, node masks, functions, gaits. What the parent
//! supplies goes: overlay groups, blend screens, IK sets and chains, and every
//! other row. See `docs/jmad_format.md`.

use std::collections::{BTreeMap, BTreeSet};

use blam_tag::blockedit::{find_block, select};
use blam_tag::patch::{resolve, set_many, set_text};
use blam_tag::{Scalar, TagFile};

use crate::codec::i16_at;
use crate::graph::{expect_size, string_of, tree_err, Graph, ANIMATIONS, GROUPS};
use crate::Error;

/// The four levels above a row.
const LEVELS: [&str; 4] = ["content.modes", "weapon class", "weapon type", "sets"];
/// A set's two lists of rows that name an animation directly.
const LISTS: [&str; 2] = ["actions", "overlay animations"];
/// A set's other lists. The merge fills these in from the parent.
const INHERITED_LISTS: [&str; 2] = ["death and damage", "transitions"];
/// A weapon class's lists whose rows hold animation indices this does not
/// translate. A kept class must have them empty.
const UNTRANSLATED: [&str; 2] = ["ranged actions", "sync actions groups"];
/// Blocks the parent supplies, or the load rebuilds.
const EMPTIED: [&str; 12] = [
    "definitions.blend screens",
    "definitions.NEW blend screens",
    "definitions.NEW function overlays",
    "definitions.overlay groups",
    "definitions.ik data",
    "definitions.ik sets",
    "definitions.ik chains",
    "content.vehicle suspension",
    "content.function overlays",
    "run time data.inheritence list",
    "run time data.new inheritance list",
    "run time data.weapon list",
];
const PARENT_GRAPH: &str = "definitions.parent animation graph";
const INHERITANCE_FLAGS: &str = "definitions.inheritance flags";
const PRIVATE_FLAGS: &str = "definitions.private flags";
/// A graph with this private flag is not compiled at load, so it never gets
/// its parent's rows.
const PRIVATE_NOT_COMPILED: u64 = 0x40;
/// Bytes of an `animation_entry_block` element, and where it keeps its
/// animation's graph index and pool index.
const ENTRY_SIZE: usize = 12;
const ENTRY_GRAPH: usize = 8;
const ENTRY_ANIMATION: usize = 10;

/// A row that plays an animation of the graph's own.
#[derive(Debug, Clone, PartialEq, Eq)]
struct Row {
    /// Its mode, weapon class, weapon type and set, by index.
    at: [usize; 4],
    /// Which of [`LISTS`] it is in.
    list: usize,
    row: usize,
    animation: usize,
    /// Its labels, as an animation's name writes them.
    name: String,
}

/// The name an animation goes by at these labels: `any` levels are left out,
/// so `warthog_p`, `rifle`, `any`, `any`, `idle` is `warthog_p:rifle:idle`.
fn row_name(levels: &[String], label: &str) -> String {
    let mut parts: Vec<&str> = levels
        .iter()
        .map(String::as_str)
        .filter(|l| *l != "any")
        .collect();
    parts.push(label);
    parts.join(":")
}

/// The path of the block below the elements `at`.
fn block_at(at: &[usize]) -> String {
    let mut path = LEVELS[0].to_string();
    for (i, n) in at.iter().enumerate() {
        path.push_str(&format!("[{n}].{}", LEVELS[i + 1]));
    }
    path
}

/// The path of the element `at`, which must not be empty.
fn element_at(at: &[usize]) -> String {
    let (last, above) = at.split_last().expect("an element has an index");
    format!("{}[{last}]", block_at(above))
}

/// Every row of the graph that plays one of its own animations.
fn rows_of(file: &[u8]) -> Result<Vec<Row>, Error> {
    let tag = TagFile::parse(file, None).map_err(tree_err)?;
    let layout = tag.layout().map_err(tree_err)?;
    let root = tag.read_data(&layout).map_err(tree_err)?;
    let block = |path: &str| {
        find_block(&layout, file, &root, path)
            .map(|f| f.block)
            .map_err(tree_err)
    };
    let mut rows = Vec::new();
    let modes = block(&block_at(&[]))?;
    for m in 0..modes.count as usize {
        let mode = string_of(modes.children.get(m));
        let classes = block(&block_at(&[m]))?;
        for c in 0..classes.count as usize {
            let class = string_of(classes.children.get(c));
            let types = block(&block_at(&[m, c]))?;
            for t in 0..types.count as usize {
                let kind = string_of(types.children.get(t));
                let sets = block(&block_at(&[m, c, t]))?;
                for s in 0..sets.count as usize {
                    let at = [m, c, t, s];
                    let levels = [
                        mode.clone(),
                        class.clone(),
                        kind.clone(),
                        string_of(sets.children.get(s)),
                    ];
                    for (list, name) in LISTS.iter().enumerate() {
                        let entries = block(&format!("{}.{name}", element_at(&at)))?;
                        expect_size(entries, ENTRY_SIZE, name)?;
                        for row in 0..entries.count as usize {
                            let e = entries.element(row).unwrap();
                            let Ok(animation) = usize::try_from(i16_at(e, ENTRY_ANIMATION)) else {
                                continue;
                            };
                            if i16_at(e, ENTRY_GRAPH) != -1 {
                                continue;
                            }
                            rows.push(Row {
                                at,
                                list,
                                row,
                                animation,
                                name: row_name(&levels, &string_of(entries.children.get(row))),
                            });
                        }
                    }
                }
            }
        }
    }
    Ok(rows)
}

/// The rows to keep for these animations (pool index and name), and those
/// that play one of them under another name and are left to the parent.
///
/// An animation keeps the row it is named for: an animation can be shared, and
/// a row that only borrows it stays as the parent has it. One named for no row
/// keeps every row that plays it.
fn pick_rows(rows: &[Row], animations: &[(usize, &str)]) -> Result<(Vec<Row>, Vec<Row>), Error> {
    let (mut kept, mut left) = (Vec::new(), Vec::new());
    for &(animation, name) in animations {
        let playing: Vec<&Row> = rows.iter().filter(|r| r.animation == animation).collect();
        if playing.is_empty() {
            return Err(Error::Unsupported(format!(
                "no action or overlay row plays {name}"
            )));
        }
        let named = playing.iter().any(|r| r.name == name);
        for r in playing {
            if !named || r.name == name {
                kept.push(r.clone());
            } else {
                left.push(r.clone());
            }
        }
    }
    kept.sort_by_key(|r| (r.at, r.list, r.row));
    left.sort_by_key(|r| (r.at, r.list, r.row));
    Ok((kept, left))
}

/// The elements kept at each level: for every kept prefix of `at`, the indices
/// below it.
fn kept_levels(rows: &[Row]) -> BTreeMap<Vec<usize>, BTreeSet<usize>> {
    let mut levels: BTreeMap<Vec<usize>, BTreeSet<usize>> = BTreeMap::new();
    for r in rows {
        for depth in 0..r.at.len() {
            levels
                .entry(r.at[..depth].to_vec())
                .or_default()
                .insert(r.at[depth]);
        }
    }
    levels
}

/// Where `value` lands among the kept values.
fn rank(kept: &BTreeSet<usize>, value: usize) -> usize {
    kept.range(..value).count()
}

/// Where `at` lands once only the kept elements remain.
fn renumbered(levels: &BTreeMap<Vec<usize>, BTreeSet<usize>>, at: &[usize; 4]) -> [usize; 4] {
    std::array::from_fn(|depth| rank(&levels[&at[..depth]], at[depth]))
}

fn as_index(target: &Scalar, path: &str) -> Result<i64, Error> {
    match target {
        Scalar::BlockIndex(v) => Ok(*v),
        other => Err(Error::Format(format!(
            "{path} is {}, not a block index",
            other.display()
        ))),
    }
}

/// Stop at the step that broke the tree, not at the end.
fn check_walk(file: &[u8], step: &str) -> Result<(), Error> {
    let tag = TagFile::parse(file, None).map_err(tree_err)?;
    let layout = tag.layout().map_err(tree_err)?;
    let root = tag.read_data(&layout).map_err(tree_err)?;
    let payload = tag
        .data()
        .ok_or_else(|| Error::Format("the tag has no data section".into()))?;
    if root.consumed != payload.size as usize {
        return Err(Error::Format(format!(
            "the tag no longer walks exactly after {step}"
        )));
    }
    Ok(())
}

fn select_step(file: &[u8], keep: &[(String, Vec<usize>)], step: &str) -> Result<Vec<u8>, Error> {
    let out = select(file, keep).map_err(tree_err)?;
    check_walk(&out, step)?;
    Ok(out)
}

fn set_fields(file: &[u8], edits: &[(String, Scalar)]) -> Result<Vec<u8>, Error> {
    let tag = TagFile::parse(file, None).map_err(tree_err)?;
    let layout = tag.layout().map_err(tree_err)?;
    let root = tag.read_data(&layout).map_err(tree_err)?;
    let (out, _) = set_many(&layout, file, &root, edits).map_err(tree_err)?;
    Ok(out)
}

/// A child graph, and what building it decided.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Child {
    /// The tag file.
    pub file: Vec<u8>,
    /// The rows it has, by name, as `name (list)`.
    pub rows: Vec<String>,
    /// Rows that played a kept animation under another name. The parent's
    /// rows, and so the parent's frames, stand for these.
    pub left_to_parent: Vec<String>,
    /// References from a kept animation to something that did not stay.
    pub cleared: Vec<String>,
}

fn described(rows: &[Row]) -> Vec<String> {
    rows.iter()
        .map(|r| format!("{} ({})", r.name, LISTS[r.list]))
        .collect()
}

/// Cut `file` down to a child of the graph at `parent` that holds only the
/// animations named.
///
/// Each kept resource group keeps only the members those animations use,
/// unless `whole_groups` is set, when it keeps them all.
pub fn child(
    file: &[u8],
    parent: &str,
    names: &[String],
    whole_groups: bool,
) -> Result<Child, Error> {
    let graph = Graph::read(file)?;

    let mut pool = BTreeSet::new();
    for name in names {
        let i = graph
            .animations
            .iter()
            .position(|a| a.name == *name)
            .ok_or_else(|| Error::Format(format!("no animation named {name}")))?;
        if graph.animations[i].data.is_none() {
            return Err(Error::Unsupported(format!(
                "{name} points into another graph"
            )));
        }
        pool.insert(i);
    }
    if pool.is_empty() {
        return Err(Error::Format("no animations named".into()));
    }
    let wanted: Vec<(usize, &str)> = pool
        .iter()
        .map(|&i| (i, graph.animations[i].name.as_str()))
        .collect();
    let (kept, left) = pick_rows(&rows_of(file)?, &wanted)?;
    let levels = kept_levels(&kept);

    {
        let tag = TagFile::parse(file, None).map_err(tree_err)?;
        let layout = tag.layout().map_err(tree_err)?;
        let root = tag.read_data(&layout).map_err(tree_err)?;
        match resolve(&layout, file, &root, PRIVATE_FLAGS)
            .map_err(tree_err)?
            .current
        {
            Scalar::Flags { raw, .. } if raw & PRIVATE_NOT_COMPILED == 0 => {}
            Scalar::Flags { .. } => {
                return Err(Error::Unsupported(
                    "the graph's private flags stop the load compiling it".into(),
                ))
            }
            other => {
                return Err(Error::Format(format!(
                    "private flags read as {}",
                    other.display()
                )))
            }
        }
        for r in &kept {
            for list in UNTRANSLATED {
                let path = format!("{}.{list}", element_at(&r.at[..2]));
                let found = find_block(&layout, file, &root, &path).map_err(tree_err)?;
                if found.block.count != 0 {
                    return Err(Error::Unsupported(format!(
                        "{path} holds rows this cannot translate"
                    )));
                }
            }
        }
    }

    // The members each kept group holds on, by old group.
    let mut members: BTreeMap<usize, BTreeSet<usize>> = BTreeMap::new();
    for &i in &pool {
        let data = graph.animations[i].data.as_ref().unwrap();
        graph
            .member(data)
            .ok_or_else(|| Error::Format(format!("{} has no member", graph.animations[i].name)))?;
        let held = members.entry(data.group).or_default();
        held.insert(data.member);
        if whole_groups {
            let count = graph.groups[data.group].as_ref().unwrap().members.len();
            held.extend(0..count);
        }
    }

    // The big cut first, so that everything after it works on a small file.
    let mut cut = vec![
        (ANIMATIONS.to_string(), pool.iter().copied().collect()),
        (GROUPS.to_string(), members.keys().copied().collect()),
    ];
    cut.extend(EMPTIED.iter().map(|p| (p.to_string(), Vec::new())));
    let mut out = select_step(file, &cut, "cutting the pool")?;

    let mut groups = Graph::read(&out)?;
    for (group, held) in groups.groups.iter_mut().zip(members.values()) {
        group
            .as_mut()
            .ok_or_else(|| Error::Format("a kept group has no resource".into()))?
            .keep(held)?;
    }
    out = groups.write_resources(&out)?;
    check_walk(&out, "cutting the members")?;

    // Rows from the inside out: an element's own indices stay valid until the
    // level above it is cut.
    let mut sets: BTreeMap<[usize; 4], [BTreeSet<usize>; 2]> = BTreeMap::new();
    for r in &kept {
        sets.entry(r.at).or_default()[r.list].insert(r.row);
    }
    let mut lists = Vec::new();
    for (at, rows) in &sets {
        let set = element_at(at);
        for (name, rows) in LISTS.iter().zip(rows) {
            lists.push((format!("{set}.{name}"), rows.iter().copied().collect()));
        }
        for name in INHERITED_LISTS {
            lists.push((format!("{set}.{name}"), Vec::new()));
        }
    }
    out = select_step(&out, &lists, "cutting the rows")?;
    for depth in (0..LEVELS.len()).rev() {
        let level: Vec<(String, Vec<usize>)> = levels
            .iter()
            .filter(|(at, _)| at.len() == depth)
            .map(|(at, kept)| (block_at(at), kept.iter().copied().collect()))
            .collect();
        out = select_step(&out, &level, LEVELS[depth])?;
    }

    // Every field that held an index into something cut. A block index of none
    // on a row sends the game up the parent chain.
    let none = Scalar::BlockIndex(-1);
    let mut edits: BTreeMap<String, Scalar> = BTreeMap::new();
    for r in &kept {
        let at = renumbered(&levels, &r.at);
        let new_pool = rank(&pool, r.animation) as i64;
        let in_list = rank(&sets[&r.at][r.list], r.row);
        let row = format!("{}.{}[{in_list}]", element_at(&at), LISTS[r.list]);
        edits.insert(
            format!("{row}.animation.animation"),
            Scalar::BlockIndex(new_pool),
        );
        for depth in 1..=at.len() {
            for field in ["overlay group", "ik set"] {
                edits.insert(
                    format!("{}.{field}", element_at(&at[..depth])),
                    none.clone(),
                );
            }
        }
        for field in ["overlay group", "ik set"] {
            edits.insert(format!("{row}.{field}"), none.clone());
        }
    }

    let mut cleared = Vec::new();
    {
        let tag = TagFile::parse(&out, None).map_err(tree_err)?;
        let layout = tag.layout().map_err(tree_err)?;
        let root = tag.read_data(&layout).map_err(tree_err)?;
        for (new, &old) in pool.iter().enumerate() {
            let at = format!("{ANIMATIONS}[{new}]");
            let name = &graph.animations[old].name;
            for field in ["parent animation", "next animation", "blend screen"] {
                let path = format!("{at}.{field}");
                let target = resolve(&layout, &out, &root, &path).map_err(tree_err)?;
                let value = as_index(&target.current, &path)?;
                let Ok(value) = usize::try_from(value) else {
                    continue;
                };
                let moved = (field != "blend screen" && pool.contains(&value))
                    .then(|| rank(&pool, value) as i64);
                if moved.is_none() {
                    cleared.push(format!("{name}: {field}"));
                }
                edits.insert(path, Scalar::BlockIndex(moved.unwrap_or(-1)));
            }
            let data = graph.animations[old].data.as_ref().unwrap();
            let held = &members[&data.group];
            let group = members.keys().take_while(|g| **g != data.group).count();
            let shared = format!("{at}.shared animation data[0]");
            edits.insert(
                format!("{shared}.resource_group"),
                Scalar::Int(group as i64),
            );
            edits.insert(
                format!("{shared}.resource_group_member"),
                Scalar::Int(rank(held, data.member) as i64),
            );
        }
    }
    for (i, held) in members.values().enumerate() {
        edits.insert(
            format!("{GROUPS}[{i}].reference_count"),
            Scalar::Int(held.len() as i64),
        );
    }
    edits.insert(
        INHERITANCE_FLAGS.to_string(),
        Scalar::Flags {
            raw: 0,
            set: Vec::new(),
        },
    );
    let edits: Vec<(String, Scalar)> = edits.into_iter().collect();
    out = set_fields(&out, &edits)?;

    let reference = Scalar::Reference {
        group: "jmad".to_string(),
        path: parent.to_string(),
    };
    out = {
        let tag = TagFile::parse(&out, None).map_err(tree_err)?;
        let layout = tag.layout().map_err(tree_err)?;
        let root = tag.read_data(&layout).map_err(tree_err)?;
        set_text(&layout, &out, &root, PARENT_GRAPH, &reference)
            .map_err(tree_err)?
            .0
    };
    check_walk(&out, "setting the parent")?;

    Ok(Child {
        file: out,
        rows: described(&kept),
        left_to_parent: described(&left),
        cleared,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(at: [usize; 4], list: usize, row: usize, animation: usize, name: &str) -> Row {
        Row {
            at,
            list,
            row,
            animation,
            name: name.to_string(),
        }
    }

    #[test]
    fn a_row_name_leaves_out_any() {
        let levels = ["warthog_p", "rifle", "any", "any"].map(String::from);
        assert_eq!(row_name(&levels, "idle"), "warthog_p:rifle:idle");
        let levels = ["any", "any", "any", "any"].map(String::from);
        assert_eq!(row_name(&levels, "aim_spine"), "aim_spine");
    }

    #[test]
    fn paths_step_down_the_levels() {
        assert_eq!(block_at(&[]), "content.modes");
        assert_eq!(
            block_at(&[2, 1]),
            "content.modes[2].weapon class[1].weapon type"
        );
        assert_eq!(
            element_at(&[2, 1, 0, 3]),
            "content.modes[2].weapon class[1].weapon type[0].sets[3]"
        );
    }

    #[test]
    fn a_borrowed_row_stays_with_the_parent() {
        let rows = [
            row([36, 3, 0, 0], 0, 0, 869, "truck_p:rifle:idle"),
            row([43, 4, 0, 0], 0, 0, 869, "warthog_p:rifle:idle"),
            row([43, 4, 0, 0], 0, 1, 870, "warthog_p:rifle:exit"),
        ];
        let (kept, left) = pick_rows(&rows, &[(869, "warthog_p:rifle:idle")]).unwrap();
        assert_eq!(kept, [rows[1].clone()]);
        assert_eq!(left, [rows[0].clone()]);
    }

    #[test]
    fn an_animation_no_row_is_named_for_keeps_every_row() {
        let rows = [
            row([0, 0, 0, 0], 1, 0, 5, "ghost_d:aim_enter"),
            row([0, 0, 0, 0], 1, 1, 5, "ghost_d:aim_exit"),
        ];
        let (kept, left) = pick_rows(&rows, &[(5, "ghost_d:aim_still")]).unwrap();
        assert_eq!(kept.len(), 2);
        assert!(left.is_empty());
    }

    #[test]
    fn an_animation_no_row_plays_is_refused() {
        assert!(pick_rows(&[], &[(5, "ghost_d:idle")]).is_err());
    }

    #[test]
    fn kept_elements_close_up() {
        let rows = [
            row([16, 0, 0, 0], 0, 5, 747, "ghost_d:idle"),
            row([16, 0, 0, 0], 1, 2, 746, "ghost_d:grip"),
            row([43, 4, 0, 0], 0, 0, 869, "warthog_p:rifle:idle"),
        ];
        let levels = kept_levels(&rows);
        assert_eq!(levels[&vec![]], BTreeSet::from([16, 43]));
        assert_eq!(levels[&vec![43]], BTreeSet::from([4]));
        assert_eq!(renumbered(&levels, &[16, 0, 0, 0]), [0, 0, 0, 0]);
        assert_eq!(renumbered(&levels, &[43, 4, 0, 0]), [1, 0, 0, 0]);
    }

    #[test]
    fn a_rank_counts_what_stays_below() {
        let kept = BTreeSet::from([746, 747, 869]);
        assert_eq!(rank(&kept, 746), 0);
        assert_eq!(rank(&kept, 869), 2);
    }
}
