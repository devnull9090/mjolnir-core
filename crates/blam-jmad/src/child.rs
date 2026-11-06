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
//!
//! A graph can also take a mode of its parent's under a new label, so a seat
//! gets a pose of its own and the mode it came from stays as the parent has it.
//! A row cannot point into the parent, and the game finds a row's overlay group
//! by its labels, so the new mode brings its animations and overlay groups with it.

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
const EMPTIED: [&str; 10] = [
    "definitions.blend screens",
    "definitions.NEW function overlays",
    "definitions.ik data",
    "definitions.ik sets",
    "definitions.ik chains",
    "content.vehicle suspension",
    "content.function overlays",
    "run time data.inheritence list",
    "run time data.new inheritance list",
    "run time data.weapon list",
];
/// What a row's overlay group holds, and what those hold. Without a renamed
/// mode these go too.
const OVERLAY_GROUPS: &str = "definitions.overlay groups";
const BLEND_SCREENS: &str = "definitions.NEW blend screens";
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

/// What the mode tree holds.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
struct Tree {
    /// Each mode's label.
    modes: Vec<String>,
    /// Every set, by index.
    sets: Vec<[usize; 4]>,
    /// Every row that plays one of the graph's own animations.
    rows: Vec<Row>,
}

/// Read the mode tree.
fn tree_of(file: &[u8]) -> Result<Tree, Error> {
    let tag = TagFile::parse(file, None).map_err(tree_err)?;
    let layout = tag.layout().map_err(tree_err)?;
    let root = tag.read_data(&layout).map_err(tree_err)?;
    let block = |path: &str| {
        find_block(&layout, file, &root, path)
            .map(|f| f.block)
            .map_err(tree_err)
    };
    let mut tree = Tree::default();
    let modes = block(&block_at(&[]))?;
    for m in 0..modes.count as usize {
        let mode = string_of(modes.children.get(m));
        tree.modes.push(mode.clone());
        let classes = block(&block_at(&[m]))?;
        for c in 0..classes.count as usize {
            let class = string_of(classes.children.get(c));
            let types = block(&block_at(&[m, c]))?;
            for t in 0..types.count as usize {
                let kind = string_of(types.children.get(t));
                let sets = block(&block_at(&[m, c, t]))?;
                for s in 0..sets.count as usize {
                    let at = [m, c, t, s];
                    tree.sets.push(at);
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
                            tree.rows.push(Row {
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
    Ok(tree)
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

/// The modes to rename, by index, from `DONOR`, `NEW` pairs.
fn renamed_modes(
    tree: &Tree,
    modes: &[(String, String)],
) -> Result<BTreeMap<usize, String>, Error> {
    let mut out = BTreeMap::new();
    for (i, (donor, label)) in modes.iter().enumerate() {
        let m = tree
            .modes
            .iter()
            .position(|l| l == donor)
            .ok_or_else(|| Error::Format(format!("no mode labelled {donor}")))?;
        if donor == label || modes[..i].iter().any(|(d, l)| d == donor || l == label) {
            return Err(Error::Format(format!(
                "{donor}={label} repeats a mode or a label"
            )));
        }
        if !tree.rows.iter().any(|r| r.at[0] == m) {
            return Err(Error::Unsupported(format!("{donor} plays nothing")));
        }
        out.insert(m, label.clone());
    }
    Ok(out)
}

/// The rows of a graph with renamed modes: every row of those modes, under its
/// new label, whatever `kept` and `left` said of it, and the rest as they were.
fn with_renamed(
    tree: &Tree,
    renamed: &BTreeMap<usize, String>,
    kept: Vec<Row>,
    left: Vec<Row>,
) -> Result<(Vec<Row>, Vec<Row>), Error> {
    let outside = |r: &Row| !renamed.contains_key(&r.at[0]);
    let mut rows: Vec<Row> = kept.into_iter().filter(outside).collect();
    for r in &rows {
        if renamed.values().any(|l| *l == tree.modes[r.at[0]]) {
            return Err(Error::Unsupported(format!(
                "{} would make a second mode of that label",
                r.name
            )));
        }
    }
    rows.extend(tree.rows.iter().filter(|r| !outside(r)).cloned());
    rows.sort_by_key(|r| (r.at, r.list, r.row));
    Ok((rows, left.into_iter().filter(outside).collect()))
}

/// A row's name once its mode has its new label.
fn renamed_row(tree: &Tree, renamed: &BTreeMap<usize, String>, row: &Row) -> Row {
    let mut out = row.clone();
    if let Some(label) = renamed.get(&row.at[0]) {
        let rest = row.name.strip_prefix(&tree.modes[row.at[0]]);
        out.name = match rest {
            Some(rest) => format!("{label}{rest}"),
            None => format!("{label}:{}", row.name),
        };
    }
    out
}

/// What the rows of a renamed mode need beyond their animations. The game finds
/// a row's overlay group by the labels it stands at, in the graph and then up
/// the parent chain, so under a new label the parent's group is out of reach.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
struct Overlays {
    /// The group each element or row names, by its path before the cut.
    named: BTreeMap<String, usize>,
    /// Each group's blend screens, in order.
    groups: BTreeMap<usize, Vec<usize>>,
    /// Each blend screen's animation.
    screens: BTreeMap<usize, Option<usize>>,
}

impl Overlays {
    fn read(file: &[u8], rows: &[&Row]) -> Result<Overlays, Error> {
        let tag = TagFile::parse(file, None).map_err(tree_err)?;
        let layout = tag.layout().map_err(tree_err)?;
        let root = tag.read_data(&layout).map_err(tree_err)?;
        let index = |path: &str| -> Result<i64, Error> {
            let target = resolve(&layout, file, &root, path).map_err(tree_err)?;
            as_index(&target.current, path)
        };
        let mut out = Overlays::default();
        for r in rows {
            let mut paths: Vec<String> = (1..=r.at.len()).map(|d| element_at(&r.at[..d])).collect();
            paths.push(row_path(&r.at, r.list, r.row));
            for path in paths {
                if index(&format!("{path}.ik set"))? >= 0 {
                    return Err(Error::Unsupported(format!(
                        "{path} has an ik set, which a renamed mode does not carry"
                    )));
                }
                if let Ok(group) = usize::try_from(index(&format!("{path}.overlay group"))?) {
                    out.named.insert(path, group);
                    out.groups.entry(group).or_default();
                }
            }
        }
        let block = |path: &str| {
            find_block(&layout, file, &root, path)
                .map(|f| f.block)
                .map_err(tree_err)
        };
        for (&group, screens) in &mut out.groups {
            let at = format!("{OVERLAY_GROUPS}[{group}]");
            if block(&format!("{at}.function overlays"))?.count != 0 {
                return Err(Error::Unsupported(format!(
                    "{at} has function overlays, which a renamed mode does not carry"
                )));
            }
            for i in 0..block(&format!("{at}.blend screens"))?.count as usize {
                let path = format!("{at}.blend screens[{i}].blend screen");
                let screen = usize::try_from(index(&path)?)
                    .map_err(|_| Error::Unsupported(format!("{path} names no blend screen")))?;
                screens.push(screen);
            }
        }
        let used: BTreeSet<usize> = out.groups.values().flatten().copied().collect();
        for screen in used {
            let at = format!("{BLEND_SCREENS}[{screen}].animation");
            let graph = resolve(&layout, file, &root, &format!("{at}.graph index"))
                .map_err(tree_err)?
                .current;
            if graph != Scalar::Int(-1) {
                return Err(Error::Unsupported(format!(
                    "{at} points into another graph"
                )));
            }
            let animation = usize::try_from(index(&format!("{at}.animation"))?).ok();
            out.screens.insert(screen, animation);
        }
        Ok(out)
    }

    fn group_set(&self) -> BTreeSet<usize> {
        self.groups.keys().copied().collect()
    }

    fn screen_set(&self) -> BTreeSet<usize> {
        self.screens.keys().copied().collect()
    }

    /// `path` before the cut, as an overlay group field after it.
    fn group_field(&self, path: &str) -> Scalar {
        let index = self
            .named
            .get(path)
            .map_or(-1, |g| rank(&self.group_set(), *g) as i64);
        Scalar::BlockIndex(index)
    }
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

/// The path of a row.
fn row_path(at: &[usize; 4], list: usize, row: usize) -> String {
    format!("{}.{}[{row}]", element_at(at), LISTS[list])
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
    /// Overlay groups and blend screens it has of its own, for renamed modes.
    pub overlay_groups: usize,
    pub blend_screens: usize,
}

fn described(rows: &[Row]) -> Vec<String> {
    rows.iter()
        .map(|r| format!("{} ({})", r.name, LISTS[r.list]))
        .collect()
}

/// Cut `file` down to a child of the graph at `parent` that holds only the
/// animations named, and the modes of `modes`, `(donor, new label)`, whole and
/// under their new labels.
///
/// An animation named that a renamed mode plays stays in that mode: the donor's
/// label goes from the child, and the parent's rows stand for it there.
///
/// Each kept resource group keeps only the members those animations use,
/// unless `whole_groups` is set, when it keeps them all.
pub fn child(
    file: &[u8],
    parent: &str,
    names: &[String],
    modes: &[(String, String)],
    whole_groups: bool,
) -> Result<Child, Error> {
    let graph = Graph::read(file)?;
    let tree = tree_of(file)?;
    let renamed = renamed_modes(&tree, modes)?;

    let mut pool = BTreeSet::new();
    for name in names {
        let i = graph
            .animations
            .iter()
            .position(|a| a.name == *name)
            .ok_or_else(|| Error::Format(format!("no animation named {name}")))?;
        pool.insert(i);
    }
    if pool.is_empty() && renamed.is_empty() {
        return Err(Error::Format("no animations named".into()));
    }
    let wanted: Vec<(usize, &str)> = pool
        .iter()
        .map(|&i| (i, graph.animations[i].name.as_str()))
        .collect();
    let (kept, left) = pick_rows(&tree.rows, &wanted)?;
    let (kept, left) = with_renamed(&tree, &renamed, kept, left)?;
    let levels = kept_levels(&kept);

    let carried: Vec<&Row> = kept
        .iter()
        .filter(|r| renamed.contains_key(&r.at[0]))
        .collect();
    let overlays = Overlays::read(file, &carried)?;
    let (kept_groups, kept_screens) = (overlays.group_set(), overlays.screen_set());
    pool.extend(carried.iter().map(|r| r.animation));
    pool.extend(overlays.screens.values().flatten());
    for &i in &pool {
        let animation = graph.animations.get(i).ok_or_else(|| {
            Error::Format(format!(
                "a row plays animation {i}, past the end of the pool"
            ))
        })?;
        if animation.data.is_none() {
            return Err(Error::Unsupported(format!(
                "{} points into another graph",
                animation.name
            )));
        }
    }

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
        // The merge goes by label, so these would not reach the new label.
        for at in tree.sets.iter().filter(|at| renamed.contains_key(&at[0])) {
            for list in INHERITED_LISTS {
                let path = format!("{}.{list}", element_at(at));
                let found = find_block(&layout, file, &root, &path).map_err(tree_err)?;
                if found.block.count != 0 {
                    return Err(Error::Unsupported(format!(
                        "{path} holds rows a renamed mode does not carry"
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
        (
            OVERLAY_GROUPS.to_string(),
            kept_groups.iter().copied().collect(),
        ),
        (
            BLEND_SCREENS.to_string(),
            kept_screens.iter().copied().collect(),
        ),
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
        let row = row_path(&at, r.list, in_list);
        edits.insert(
            format!("{row}.animation.animation"),
            Scalar::BlockIndex(new_pool),
        );
        for depth in 1..=at.len() {
            let path = element_at(&at[..depth]);
            edits.insert(
                format!("{path}.overlay group"),
                overlays.group_field(&element_at(&r.at[..depth])),
            );
            edits.insert(format!("{path}.ik set"), none.clone());
        }
        edits.insert(
            format!("{row}.overlay group"),
            overlays.group_field(&row_path(&r.at, r.list, r.row)),
        );
        edits.insert(format!("{row}.ik set"), none.clone());
    }
    for (new, screens) in overlays.groups.values().enumerate() {
        for (i, screen) in screens.iter().enumerate() {
            edits.insert(
                format!("{OVERLAY_GROUPS}[{new}].blend screens[{i}].blend screen"),
                Scalar::BlockIndex(rank(&kept_screens, *screen) as i64),
            );
        }
    }
    for (new, animation) in overlays.screens.values().enumerate() {
        if let Some(animation) = animation {
            edits.insert(
                format!("{BLEND_SCREENS}[{new}].animation.animation"),
                Scalar::BlockIndex(rank(&pool, *animation) as i64),
            );
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

    for (m, label) in &renamed {
        let path = format!("{}.label", element_at(&[rank(&levels[&Vec::new()], *m)]));
        let tag = TagFile::parse(&out, None).map_err(tree_err)?;
        let layout = tag.layout().map_err(tree_err)?;
        let root = tag.read_data(&layout).map_err(tree_err)?;
        let text = Scalar::Text(label.clone());
        let written = set_text(&layout, &out, &root, &path, &text)
            .map_err(tree_err)?
            .0;
        out = written;
        check_walk(&out, "renaming a mode")?;
    }

    let shown: Vec<Row> = kept
        .iter()
        .map(|r| renamed_row(&tree, &renamed, r))
        .collect();
    Ok(Child {
        file: out,
        rows: described(&shown),
        left_to_parent: described(&left),
        cleared,
        overlay_groups: kept_groups.len(),
        blend_screens: kept_screens.len(),
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

    fn seats() -> Tree {
        Tree {
            modes: ["ghost_d", "truck_p", "warthog_p"]
                .map(String::from)
                .to_vec(),
            sets: vec![[0, 0, 0, 0], [1, 0, 0, 0], [2, 0, 0, 0], [2, 1, 0, 0]],
            rows: vec![
                row([0, 0, 0, 0], 0, 0, 742, "ghost_d:enter"),
                row([0, 0, 0, 0], 0, 1, 747, "ghost_d:idle"),
                row([1, 0, 0, 0], 0, 0, 869, "truck_p:rifle:idle"),
                row([2, 0, 0, 0], 0, 0, 839, "warthog_p:enter"),
                row([2, 1, 0, 0], 0, 0, 869, "warthog_p:rifle:idle"),
            ],
        }
    }

    fn renames(pairs: &[(&str, &str)]) -> Vec<(String, String)> {
        pairs
            .iter()
            .map(|(a, b)| (a.to_string(), b.to_string()))
            .collect()
    }

    #[test]
    fn a_renamed_mode_comes_whole_and_its_named_row_with_it() {
        let tree = seats();
        let modes = renames(&[("warthog_p", "mongoose_p")]);
        let renamed = renamed_modes(&tree, &modes).unwrap();
        let (kept, left) = pick_rows(&tree.rows, &[(869, "warthog_p:rifle:idle")]).unwrap();
        let (kept, left) = with_renamed(&tree, &renamed, kept, left).unwrap();
        assert_eq!(kept, tree.rows[3..]);
        assert_eq!(left, [tree.rows[2].clone()]);
        let shown = renamed_row(&tree, &renamed, &kept[1]);
        assert_eq!(shown.name, "mongoose_p:rifle:idle");
    }

    #[test]
    fn an_animation_outside_a_renamed_mode_keeps_its_own_row() {
        let tree = seats();
        let renamed = renamed_modes(&tree, &renames(&[("ghost_d", "mongoose_d")])).unwrap();
        let (kept, left) = pick_rows(&tree.rows, &[(839, "warthog_p:enter")]).unwrap();
        let (kept, _) = with_renamed(&tree, &renamed, kept, left).unwrap();
        assert_eq!(kept.len(), 3);
        assert_eq!(kept[2], tree.rows[3]);
        let shown = renamed_row(&tree, &renamed, &kept[2]);
        assert_eq!(shown.name, "warthog_p:enter");
    }

    #[test]
    fn a_kept_row_cannot_stand_at_a_new_label() {
        let tree = seats();
        let renamed = renamed_modes(&tree, &renames(&[("ghost_d", "truck_p")])).unwrap();
        let (kept, left) = pick_rows(&tree.rows, &[(869, "truck_p:rifle:idle")]).unwrap();
        assert!(with_renamed(&tree, &renamed, kept, left).is_err());
    }

    #[test]
    fn a_rename_needs_a_mode_that_plays_and_one_label_each() {
        let mut tree = seats();
        for bad in [
            &[("alert", "x")][..],
            &[("ghost_d", "ghost_d")],
            &[("ghost_d", "x"), ("warthog_p", "x")],
            &[("ghost_d", "x"), ("ghost_d", "y")],
        ] {
            assert!(renamed_modes(&tree, &renames(bad)).is_err(), "{bad:?}");
        }
        tree.rows.retain(|r| r.at[0] != 0);
        assert!(renamed_modes(&tree, &renames(&[("ghost_d", "x")])).is_err());
    }

    #[test]
    fn an_overlay_group_field_follows_the_group() {
        let overlays = Overlays {
            named: BTreeMap::from([("a".to_string(), 164), ("b".to_string(), 108)]),
            groups: BTreeMap::from([(108, vec![263]), (164, vec![234])]),
            screens: BTreeMap::from([(234, Some(739)), (263, None)]),
        };
        assert_eq!(overlays.group_field("a"), Scalar::BlockIndex(1));
        assert_eq!(overlays.group_field("b"), Scalar::BlockIndex(0));
        assert_eq!(overlays.group_field("c"), Scalar::BlockIndex(-1));
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
