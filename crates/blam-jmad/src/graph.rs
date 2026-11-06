//! A whole animation graph: its skeleton, its animations and its resources,
//! and the rewrite that gives it a different skeleton.

use blam_tag::blockedit::{element_with_wrapper, find_block, replace_nested, NestedReplace};
use blam_tag::patch::rewrite as rebuild;
use blam_tag::write::{raw_section, Edits};
use blam_tag::{Block, TagFile, Value};

use crate::clip::{Clip, Pose, Skeleton, Track};
use crate::codec::{f32_at, i16_at};
use crate::member::{has_bit, set_bit, set_bits, Member, ObjectSpace, NODE_BOUND_OPAQUE};
use crate::resource::Group;
use crate::Error;

const NODES: &str = "definitions.skeleton nodes";
const EXTRA: &str = "additional node data";
const USAGE: &str = "definitions.node usage";
pub(crate) const ANIMATIONS: &str = "definitions.animations";
pub(crate) const GROUPS: &str = "tag resource groups";

/// Bytes of a `skeleton nodes` element, and where its links sit.
const NODE_SIZE: usize = 40;
const NEXT_SIBLING: usize = 4;
const FIRST_CHILD: usize = 6;
const PARENT: usize = 8;
const MODEL_FLAGS: usize = 10;
/// Bytes of an `additional node data` element.
const EXTRA_SIZE: usize = 60;
/// Where the root keeps its left and right arm bit vectors.
const ARM_BITS: [usize; 2] = [332, 364];
/// Offsets in a `shared animation data` element.
const SHARED_NODES: usize = 0;
const SHARED_FRAMES: usize = 2;
const SHARED_KIND: usize = 4;
const SHARED_MOVEMENT: usize = 5;
const SHARED_GROUP: usize = 32;
const SHARED_MEMBER: usize = 34;

/// One skeleton node.
#[derive(Debug, Clone, PartialEq)]
pub struct Node {
    pub name: String,
    pub parent: Option<usize>,
    pub first_child: Option<usize>,
    pub next_sibling: Option<usize>,
    pub default: Pose,
}

/// One entry of `definitions.animations`.
#[derive(Debug, Clone, PartialEq)]
pub struct Animation {
    pub name: String,
    /// The `shared animation data` element: what the entry's frames are.
    /// Absent on an entry that points into another graph.
    pub data: Option<AnimationData>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AnimationData {
    pub nodes: u8,
    pub frames: i16,
    /// 1 base, 2 overlay, 3 replacement.
    pub kind: u8,
    pub movement_kind: u8,
    pub group: usize,
    pub member: usize,
}

/// A graph read from a tag file.
#[derive(Debug, Clone, PartialEq)]
pub struct Graph {
    pub nodes: Vec<Node>,
    pub animations: Vec<Animation>,
    /// One per `tag resource groups` element; `None` where no resource is
    /// attached.
    pub groups: Vec<Option<Group>>,
}

pub(crate) fn tree_err<E: std::fmt::Display>(e: E) -> Error {
    Error::Tag(e.to_string())
}

fn index(v: i16) -> Option<usize> {
    usize::try_from(v).ok()
}

fn stored_index(v: Option<usize>) -> i16 {
    v.map_or(-1, |i| i as i16)
}

pub(crate) fn string_of(children: Option<&Vec<Value<'_>>>) -> String {
    let text = children.and_then(|c| {
        c.iter().find_map(|v| match v {
            Value::StringId(b) => Some(*b),
            _ => None,
        })
    });
    String::from_utf8_lossy(text.unwrap_or(&[])).into_owned()
}

fn floats<const N: usize>(b: &[u8], at: usize) -> [f32; N] {
    std::array::from_fn(|i| f32_at(b, at + 4 * i))
}

fn offset_in(file: &[u8], part: &[u8]) -> usize {
    part.as_ptr() as usize - file.as_ptr() as usize
}

pub(crate) fn expect_size(block: &Block<'_>, size: usize, what: &str) -> Result<(), Error> {
    if block.element_size as usize != size {
        return Err(Error::Format(format!(
            "{what} elements are {} bytes, not {size}",
            block.element_size
        )));
    }
    Ok(())
}

/// Read every `tag resource groups` body from a parsed tree.
fn resource_bodies<'a>(block: &Block<'a>) -> Vec<Option<&'a [u8]>> {
    block
        .children
        .iter()
        .map(|c| {
            c.iter().find_map(|v| match v {
                Value::Resource {
                    kind: b'r', body, ..
                } => Some(*body),
                _ => None,
            })
        })
        .collect()
}

impl Graph {
    /// Read a graph from a tag file's bytes.
    pub fn read(file: &[u8]) -> Result<Graph, Error> {
        let tag = TagFile::parse(file, None).map_err(tree_err)?;
        let layout = tag.layout().map_err(tree_err)?;
        let root = tag.read_data(&layout).map_err(tree_err)?;
        let find = |path: &str| {
            find_block(&layout, file, &root, path)
                .map(|f| f.block)
                .map_err(tree_err)
        };

        let skeleton = find(NODES)?;
        expect_size(skeleton, NODE_SIZE, "skeleton node")?;
        let extra = find(EXTRA)?;
        expect_size(extra, EXTRA_SIZE, "additional node data")?;
        let nodes = (0..skeleton.count as usize)
            .map(|i| {
                let e = skeleton.element(i).unwrap();
                let default = extra.element(i).map_or(Pose::IDENTITY, |x| Pose {
                    rotation: floats(x, 4),
                    translation: floats(x, 20),
                    scale: f32_at(x, 32),
                });
                Node {
                    name: string_of(skeleton.children.get(i)),
                    next_sibling: index(i16_at(e, NEXT_SIBLING)),
                    first_child: index(i16_at(e, FIRST_CHILD)),
                    parent: index(i16_at(e, PARENT)),
                    default,
                }
            })
            .collect();

        let list = find(ANIMATIONS)?;
        let mut animations = Vec::with_capacity(list.count as usize);
        for i in 0..list.count as usize {
            let shared = find(&format!("{ANIMATIONS}[{i}].shared animation data"))?;
            let data = shared.element(0).map(|e| AnimationData {
                nodes: e[SHARED_NODES],
                frames: i16_at(e, SHARED_FRAMES),
                kind: e[SHARED_KIND],
                movement_kind: e[SHARED_MOVEMENT],
                group: i16_at(e, SHARED_GROUP).max(0) as usize,
                member: i16_at(e, SHARED_MEMBER).max(0) as usize,
            });
            animations.push(Animation {
                name: string_of(list.children.get(i)),
                data,
            });
        }

        let mut groups = Vec::new();
        for body in resource_bodies(find(GROUPS)?) {
            groups.push(body.map(Group::read).transpose()?);
        }
        Ok(Graph {
            nodes,
            animations,
            groups,
        })
    }

    /// The tag file with its resource bodies replaced by this graph's. For a
    /// graph just read, the result is the file itself, byte for byte.
    pub fn write_resources(&self, file: &[u8]) -> Result<Vec<u8>, Error> {
        let tag = TagFile::parse(file, None).map_err(tree_err)?;
        let layout = tag.layout().map_err(tree_err)?;
        let root = tag.read_data(&layout).map_err(tree_err)?;
        let block = find_block(&layout, file, &root, GROUPS)
            .map_err(tree_err)?
            .block;
        let mut edits = Edits::new(file);
        for (body, group) in resource_bodies(block).iter().zip(&self.groups) {
            if let (Some(body), Some(group)) = (body, group) {
                edits.sections.insert(offset_in(file, body), group.write());
            }
        }
        rebuild(file, &edits).map_err(tree_err)
    }

    /// The member an animation's frames are in.
    pub fn member(&self, data: &AnimationData) -> Option<&Member> {
        self.groups
            .get(data.group)?
            .as_ref()?
            .members
            .get(data.member)
    }

    /// Each node's place among its siblings.
    pub fn sibling_ranks(&self) -> Vec<usize> {
        let mut ranks = vec![0; self.nodes.len()];
        let heads = self.nodes.iter().filter_map(|n| n.first_child);
        let roots = self.nodes.iter().position(|n| n.parent.is_none());
        for head in heads.chain(roots) {
            let (mut at, mut rank) = (Some(head), 0);
            while let Some(i) = at {
                ranks[i] = rank;
                rank += 1;
                at = self.nodes[i].next_sibling;
            }
        }
        ranks
    }

    /// The graph's parents and default poses, for object-space work.
    pub fn parents(&self) -> Vec<Option<usize>> {
        self.nodes.iter().map(|n| n.parent).collect()
    }

    pub fn defaults(&self) -> Vec<Pose> {
        self.nodes.iter().map(|n| n.default).collect()
    }
}

/// One node of the skeleton a rewrite gives the graph.
#[derive(Debug, Clone, PartialEq)]
pub struct NodeSpec {
    pub name: String,
    pub parent: Option<usize>,
    /// The old node this one continues, if any. It inherits that node's
    /// frames, default pose and record.
    pub source: Option<usize>,
    /// The default pose; required on a node with no source.
    pub default: Option<Pose>,
}

/// A change to one animation, on the new skeleton.
#[derive(Debug, Clone, PartialEq)]
pub struct AnimationEdit {
    pub name: String,
    /// The new frame count. If it differs from the donor's, nodes left alone
    /// hold their first frame, and the root movement, pill and blend screen
    /// data go. A member with chain data must keep its count.
    pub frames: usize,
    /// Channels to set, by new node index. An absent channel is left alone.
    pub tracks: Vec<(usize, Track)>,
}

/// What a rewrite does.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Rewrite {
    /// The new skeleton, in order.
    pub nodes: Vec<NodeSpec>,
    /// Animations to change. All others are carried across node by node.
    pub edits: Vec<AnimationEdit>,
    /// Encode every member afresh even if the skeleton stays as it is, so
    /// that nothing is left in a codec this crate only carries.
    pub reencode: bool,
}

/// Each node's first child and next sibling, each parent's children running
/// in order of `ranks`, then of index. Shipped graphs disagree on the order
/// (most run from the highest index down), and the load compares these links
/// with the skeleton's, so a rewrite keeps the donor's.
pub fn link(parents: &[Option<usize>], ranks: &[usize]) -> Vec<(Option<usize>, Option<usize>)> {
    let mut order: Vec<usize> = (0..parents.len()).collect();
    order.sort_by_key(|&i| std::cmp::Reverse((ranks[i], i)));
    let mut links = vec![(None, None); parents.len()];
    let mut roots = None;
    for i in order {
        let head = match parents[i] {
            Some(p) => &mut links[p].0,
            None => &mut roots,
        };
        links[i].1 = head.replace(i);
    }
    links
}

/// The old nodes new node `i` stands for, top first. See [`Clip::remap`].
fn chain_of(
    spec: &[NodeSpec],
    i: usize,
    old_parents: &[Option<usize>],
) -> Result<Vec<usize>, Error> {
    let Some(source) = spec[i].source else {
        return Ok(Vec::new());
    };
    let stop = spec[i].parent.map(|p| spec[p].source);
    // Under a node of its own, a node keeps its pose as it is.
    if let Some(None) = stop {
        return Ok(vec![source]);
    }
    let stop = stop.flatten();
    let mut chain = vec![source];
    let mut at = old_parents[source];
    while at != stop {
        let Some(node) = at else {
            return Err(Error::Unsupported(format!(
                "{} does not hang below its new parent in the donor",
                spec[i].name
            )));
        };
        chain.push(node);
        at = old_parents[node];
    }
    chain.reverse();
    Ok(chain)
}

/// The blocks that hold node indices this rewrite does not translate. They
/// must be empty for the node list to change.
fn check_translatable(graph: &Graph, file: &[u8]) -> Result<(), Error> {
    let tag = TagFile::parse(file, None).map_err(tree_err)?;
    let layout = tag.layout().map_err(tree_err)?;
    let root = tag.read_data(&layout).map_err(tree_err)?;
    let count = |path: &str| {
        find_block(&layout, file, &root, path)
            .map(|f| f.block.count)
            .map_err(tree_err)
    };
    let mut refused = Vec::new();
    for path in [
        "definitions.node masks",
        "definitions.ik chains",
        "run time data.inheritence list",
        "run time data.new inheritance list",
    ] {
        if count(path)? != 0 {
            refused.push(path.to_string());
        }
    }
    for (i, a) in graph.animations.iter().enumerate() {
        if a.data.is_none() {
            continue;
        }
        for block in [
            "foot tracking",
            "object space offset nodes",
            "forward-invert kinetic anchor nodes",
        ] {
            if count(&format!(
                "{ANIMATIONS}[{i}].shared animation data[0].{block}"
            ))? != 0
            {
                refused.push(format!("{}: {block}", a.name));
            }
        }
    }
    for g in graph.groups.iter().flatten() {
        for m in &g.members {
            for s in NODE_BOUND_OPAQUE {
                if !m.opaque[s].is_empty() {
                    refused.push(format!("member segment {s}"));
                }
            }
        }
    }
    refused.sort();
    refused.dedup();
    if refused.is_empty() {
        Ok(())
    } else {
        Err(Error::Unsupported(format!(
            "node-bound data this rewrite cannot translate: {}",
            refused.join(", ")
        )))
    }
}

/// Stored object-space frames of the nodes that carry over, in place of the
/// worked-out ones: overlays store something forward kinematics of their
/// frames does not give.
fn carry_object_space(old: &ObjectSpace, new: &mut ObjectSpace, sources: &[Option<usize>]) {
    if old.frames != new.frames {
        return;
    }
    let f = new.frames;
    let before = set_bits(&old.mask);
    for (k, node) in set_bits(&new.mask).into_iter().enumerate() {
        let Some(source) = sources.get(node).copied().flatten() else {
            continue;
        };
        if let Ok(at) = before.binary_search(&source) {
            new.poses[k * f..(k + 1) * f].copy_from_slice(&old.poses[at * f..(at + 1) * f]);
        }
    }
}

/// Where a stored old node index went. A stored -1 names no node, and must not
/// land on a new node, whose source is also empty.
fn carried_to(sources: &[Option<usize>], old: i16) -> Option<usize> {
    let old = index(old)?;
    sources.iter().position(|s| *s == Some(old))
}

/// Whether node `i` is one of `edited` or hangs below one.
fn moved_by(i: usize, edited: &[usize], parents: &[Option<usize>]) -> bool {
    let mut at = Some(i);
    while let Some(node) = at {
        if edited.contains(&node) {
            return true;
        }
        at = parents[node];
    }
    false
}

/// Rewrite a graph's tag file for a new skeleton: the skeleton blocks, every
/// reference to a node, and every resource member, so that no animation is
/// left at the old node count. The hlmt load drops a graph otherwise.
pub fn rewrite(file: &[u8], plan: &Rewrite) -> Result<Vec<u8>, Error> {
    let graph = Graph::read(file)?;
    let n = plan.nodes.len();
    if n == 0 || n > 255 {
        return Err(Error::Unsupported(format!(
            "{n} nodes (a graph holds 1 to 255)"
        )));
    }
    for (i, s) in plan.nodes.iter().enumerate() {
        if s.parent.is_some_and(|p| p >= n || p == i) {
            return Err(Error::Unsupported(format!("{}: bad parent", s.name)));
        }
        if s.source.is_some_and(|o| o >= graph.nodes.len()) {
            return Err(Error::Unsupported(format!("{}: bad source", s.name)));
        }
        if s.source.is_none() && s.default.is_none() {
            return Err(Error::Unsupported(format!(
                "{}: a new node needs a default pose",
                s.name
            )));
        }
    }
    for edit in &plan.edits {
        if let Some((node, _)) = edit.tracks.iter().find(|(node, _)| *node >= n) {
            return Err(Error::Unsupported(format!(
                "{}: node {node} in a skeleton of {n}",
                edit.name
            )));
        }
        if !graph
            .animations
            .iter()
            .any(|a| a.name == edit.name && a.data.is_some())
        {
            return Err(Error::Unsupported(format!(
                "no animation {} with frames of its own",
                edit.name
            )));
        }
    }

    let sources: Vec<Option<usize>> = plan.nodes.iter().map(|s| s.source).collect();
    let parents: Vec<Option<usize>> = plan.nodes.iter().map(|s| s.parent).collect();
    let old_parents = graph.parents();
    let old_defaults = graph.defaults();
    let same_nodes = n == graph.nodes.len()
        && sources.iter().enumerate().all(|(i, s)| *s == Some(i))
        && parents == old_parents
        && plan.nodes.iter().all(|s| s.default.is_none());
    if !same_nodes {
        check_translatable(&graph, file)?;
    }
    let chains = (0..n)
        .map(|i| chain_of(&plan.nodes, i, &old_parents))
        .collect::<Result<Vec<_>, _>>()?;
    let defaults: Vec<Pose> = plan
        .nodes
        .iter()
        .zip(&chains)
        .map(|(s, chain)| {
            s.default.unwrap_or_else(|| {
                chain
                    .iter()
                    .fold(None, |above: Option<Pose>, &o| {
                        let local = old_defaults[o];
                        Some(above.map_or(local, |p| local.under(p)))
                    })
                    .unwrap_or(Pose::IDENTITY)
            })
        })
        .collect();
    let skeleton = Skeleton {
        parents: &parents,
        defaults: &defaults,
    };

    // Pass one: the blocks whose element counts change.
    let tag = TagFile::parse(file, None).map_err(tree_err)?;
    let layout = tag.layout().map_err(tree_err)?;
    let root = tag.read_data(&layout).map_err(tree_err)?;
    let block = |path: &str| {
        find_block(&layout, file, &root, path)
            .map(|f| f.block)
            .map_err(tree_err)
    };
    let old_skeleton = block(NODES)?;
    let old_extra = block(EXTRA)?;
    let old_ranks = graph.sibling_ranks();
    let ranks: Vec<usize> = sources
        .iter()
        .map(|s| s.map_or(usize::MAX, |o| old_ranks[o]))
        .collect();
    let links = link(&parents, &ranks);
    let mut node_bytes = Vec::with_capacity(n * NODE_SIZE);
    let mut extra_bytes = Vec::with_capacity(n * EXTRA_SIZE);
    let mut names = Vec::with_capacity(n);
    for (i, s) in plan.nodes.iter().enumerate() {
        let mut e = match s.source {
            Some(o) => old_skeleton.element(o).unwrap().to_vec(),
            None => {
                let mut blank = vec![0u8; NODE_SIZE];
                blank[MODEL_FLAGS] = 1;
                blank
            }
        };
        for (at, v) in [
            (NEXT_SIBLING, links[i].1),
            (FIRST_CHILD, links[i].0),
            (PARENT, parents[i]),
        ] {
            e[at..at + 2].copy_from_slice(&stored_index(v).to_le_bytes());
        }
        node_bytes.extend_from_slice(&e);
        let mut x = s
            .source
            .and_then(|o| old_extra.element(o))
            .map_or(vec![0u8; EXTRA_SIZE], <[u8]>::to_vec);
        let d = defaults[i];
        let put = |x: &mut Vec<u8>, at: usize, v: &[f32]| {
            for (k, c) in v.iter().enumerate() {
                x[at + 4 * k..at + 4 * k + 4].copy_from_slice(&c.to_le_bytes());
            }
        };
        put(&mut x, 4, &d.rotation);
        put(&mut x, 20, &d.translation);
        put(&mut x, 32, &[d.scale]);
        extra_bytes.extend_from_slice(&x);
        names.push(raw_section("tgsi", 0, s.name.as_bytes()));
    }
    let new_index = |old: i16| carried_to(&sources, old);
    let usage = block(USAGE)?;
    let mut usage_bytes = Vec::new();
    let mut usage_count = 0;
    for i in 0..usage.count as usize {
        let e = usage.element(i).unwrap();
        if let Some(node) = new_index(i16_at(e, 2)) {
            usage_bytes.extend_from_slice(&e[..2]);
            usage_bytes.extend_from_slice(&(node as i16).to_le_bytes());
            usage_count += 1;
        }
    }
    let mut replacements = vec![
        NestedReplace {
            path: NODES.into(),
            count: n as u32,
            elements: node_bytes,
            wrappers: Some(names.clone()),
        },
        NestedReplace {
            path: EXTRA.into(),
            count: n as u32,
            elements: extra_bytes,
            wrappers: Some(names),
        },
        NestedReplace {
            path: USAGE.into(),
            count: usage_count,
            elements: usage_bytes,
            wrappers: None,
        },
    ];
    for (i, a) in graph.animations.iter().enumerate() {
        if a.data.is_none() {
            continue;
        }
        let path = format!("{ANIMATIONS}[{i}].shared animation data[0].object-space parent nodes");
        let list = block(&path)?;
        if list.count == 0 {
            continue;
        }
        let mut elements = Vec::new();
        let mut wrappers = Vec::new();
        for k in 0..list.count as usize {
            let (e, wrapper) = element_with_wrapper(file, &path, k).map_err(tree_err)?;
            if let Some(node) = new_index(i16_at(&e, 0)) {
                elements.extend_from_slice(&(node as i16).to_le_bytes());
                elements.extend_from_slice(&e[2..]);
                wrappers.push(wrapper);
            }
        }
        let count = wrappers.len() as u32;
        replacements.push(NestedReplace {
            path,
            count,
            elements,
            wrappers: Some(wrappers),
        });
    }
    let shaped = replace_nested(file, &replacements).map_err(tree_err)?;

    // Pass two: the members, and the counts and bit vectors that sit inline.
    let mut groups = graph.groups.clone();
    let tail_of = |m: &Member| m.data_tail;
    for (gi, group) in groups.iter_mut().enumerate() {
        let Some(group) = group else { continue };
        for (mi, m) in group.members.iter_mut().enumerate() {
            let named = graph
                .animations
                .iter()
                .find(|a| a.data.is_some_and(|d| d.group == gi && d.member == mi));
            let label = named.map_or("<no animation>", |a| a.name.as_str());
            let edit = named.and_then(|a| plan.edits.iter().find(|e| e.name == a.name));
            if edit.is_none() && same_nodes && !plan.reencode {
                continue;
            }
            let clip = Clip::read(m).map_err(|e| Error::Unsupported(format!("{label}: {e}")))?;
            let clip = clip.remap(&chains, &old_defaults, &defaults);
            let mut carried = sources.clone();
            let mut fresh = if let Some(edit) = edit {
                // The tag's rows go on naming these segments, and they hold
                // the frame count, so a new length has nothing true to carry.
                if edit.frames != clip.frames && clip.has_node_bound_data() {
                    return Err(Error::Unsupported(format!(
                        "{label}: chain data holds for {} frames, not {}",
                        clip.frames, edit.frames
                    )));
                }
                let edited: Vec<usize> = edit.tracks.iter().map(|(node, _)| *node).collect();
                for (i, source) in carried.iter_mut().enumerate() {
                    if moved_by(i, &edited, &parents) {
                        *source = None;
                    }
                }
                clip.edited(edit.frames, &edit.tracks)
                    .write(skeleton, true, tail_of(m))?
            } else {
                clip.write(skeleton, m.object_space.is_some(), tail_of(m))?
            };
            if let (Some(old), Some(new)) = (&m.object_space, &mut fresh.object_space) {
                carry_object_space(old, new, &carried);
            }
            *m = Member {
                animation_index: m.animation_index,
                checksum: m.checksum,
                ..fresh
            };
        }
    }

    let tag = TagFile::parse(&shaped, None).map_err(tree_err)?;
    let layout = tag.layout().map_err(tree_err)?;
    let root = tag.read_data(&layout).map_err(tree_err)?;
    let mut edits = Edits::new(&shaped);
    for (i, a) in graph.animations.iter().enumerate() {
        let Some(data) = &a.data else { continue };
        let path = format!("{ANIMATIONS}[{i}].shared animation data");
        let shared = find_block(&layout, &shaped, &root, &path)
            .map_err(tree_err)?
            .block;
        let at = offset_in(&shaped, shared.element(0).unwrap());
        let Some(m) = groups
            .get(data.group)
            .and_then(|g| g.as_ref())
            .and_then(|g| g.members.get(data.member))
        else {
            return Err(Error::Format(format!(
                "{}: no member {}.{}",
                a.name, data.group, data.member
            )));
        };
        edits.inline.insert(at + SHARED_NODES, vec![m.nodes]);
        edits
            .inline
            .insert(at + SHARED_FRAMES, m.frames.to_le_bytes().to_vec());
        edits
            .inline
            .insert(at + SHARED_MOVEMENT, vec![m.movement_kind]);
    }
    let packed = root
        .element(0)
        .ok_or_else(|| Error::Format("no root element".into()))?;
    for arm in ARM_BITS {
        let at = offset_in(&shaped, packed) + arm;
        let old: [u32; 8] = std::array::from_fn(|k| {
            u32::from_le_bytes(shaped[at + 4 * k..at + 4 * k + 4].try_into().unwrap())
        });
        let mut new = [0u32; 8];
        for (i, s) in sources.iter().enumerate() {
            if s.is_some_and(|o| has_bit(&old, o)) {
                set_bit(&mut new, i);
            }
        }
        edits
            .inline
            .insert(at, new.iter().flat_map(|w| w.to_le_bytes()).collect());
    }
    let block = find_block(&layout, &shaped, &root, GROUPS)
        .map_err(tree_err)?
        .block;
    for (body, group) in resource_bodies(block).iter().zip(&groups) {
        if let (Some(body), Some(group)) = (body, group) {
            edits
                .sections
                .insert(offset_in(&shaped, body), group.write());
        }
    }
    rebuild(&shaped, &edits).map_err(tree_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn no_node_stays_no_node() {
        let sources = [Some(4), None, Some(2)];
        assert_eq!(carried_to(&sources, 2), Some(2));
        assert_eq!(carried_to(&sources, 3), None);
        assert_eq!(carried_to(&sources, -1), None);
    }

    #[test]
    fn children_run_in_rank_order() {
        // 0 has children 1, 2 and 3; 3 has child 4.
        let parents = [None, Some(0), Some(0), Some(0), Some(3)];
        let links = link(&parents, &[0, 2, 1, 0, 0]);
        assert_eq!(links[0], (Some(3), None));
        assert_eq!(links[3], (Some(4), Some(2)));
        assert_eq!(links[2], (None, Some(1)));
        assert_eq!(links[1], (None, None));
        assert_eq!(links[4], (None, None));
    }

    #[test]
    fn equal_ranks_run_by_index() {
        let links = link(&[None, Some(0), Some(0)], &[0, 0, 0]);
        assert_eq!(links[0], (Some(1), None));
        assert_eq!(links[1], (None, Some(2)));
    }
}
