//! Pair a tag's field definitions with its decoded values.
//!
//! [`crate::layout`] gives the fields, [`crate::data`] gives the value
//! structure, and [`crate::value`] turns packed bytes into typed values. This
//! joins the three into one tree, which is the shape a tag editor renders and
//! the shape a person reads.
//!
//! The join is order-sensitive: the reader emits one [`crate::data::Value`] per
//! field that writes, in declaration order, so walking the same field list with
//! the same [`crate::data::field_writes`] predicate lines them back up. Using a
//! different rule here would silently pair values with the wrong fields, so the
//! predicate has exactly one definition and both sides call it.

use std::collections::HashMap;

use crate::data::{field_writes, Block, Value};
use crate::layout::Layout;
use crate::value::{self, Scalar};

/// What a node is, which decides how it renders and whether it expands.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    /// A leaf holding a value.
    Field,
    /// An inlined struct; `children` are its fields.
    Struct,
    /// A block; `children` are its elements.
    Block,
    /// One element of a block or array; `children` are its fields.
    Element,
    /// A fixed-count array; `children` are its elements.
    Array,
}

/// One node of a tag's value tree.
#[derive(Debug, Clone)]
pub struct Node {
    pub kind: Kind,
    pub name: String,
    pub type_name: String,
    /// Byte offset within the enclosing element's packed data.
    pub offset: u32,
    pub size: u32,
    pub value: Scalar,
    /// Every option an enum or bitfield field can take, in declaration order.
    pub options: Vec<String>,
    /// For a block: the definition's name for it, and the limit Guerilla
    /// enforced.
    pub block_name: Option<String>,
    pub max_count: Option<u32>,
    /// Elements this block or array actually has. `children` may hold fewer,
    /// because a tag like `scenario_structure_bsp` has millions of them and
    /// materialising every one costs gigabytes.
    pub count: Option<u32>,
    /// For a block, the index of the element `children[0]` is. Zero unless a
    /// window asked for later elements; see [`root_windowed`].
    pub first: u32,
    pub children: Vec<Node>,
}

impl Node {
    fn leaf(name: String, type_name: String, offset: u32, size: u32, value: Scalar) -> Node {
        Node {
            kind: Kind::Field,
            name,
            type_name,
            offset,
            size,
            value,
            options: Vec::new(),
            block_name: None,
            max_count: None,
            count: None,
            first: 0,
            children: Vec::new(),
        }
    }

    /// Total nodes in this subtree, including itself.
    pub fn len(&self) -> usize {
        1 + self.children.iter().map(Node::len).sum::<usize>()
    }

    pub fn is_empty(&self) -> bool {
        false
    }
}

/// Types that exist to shape the layout rather than hold a value. They still
/// occupy bytes, so the offset walk counts them, but there is nothing to show.
fn structural(type_name: &str) -> bool {
    matches!(type_name, "pad" | "terminator X" | "custom")
}

/// How much of a tag's value tree to materialise, and what to do en route.
struct Walk<'v> {
    /// Called with every fixed-width field and the bytes it occupies.
    visit: &'v mut dyn FnMut(&crate::layout::FieldEntry, &[u8]),
    /// Whether to allocate `Node`s. A pure visit allocates nothing.
    build: bool,
    /// Elements to materialise per block or array when building.
    max_elements: usize,
    /// Nodes left in the build budget. A per-block cap alone still allows
    /// `max_elements` to the power of the nesting depth, so the total is
    /// bounded too.
    budget: usize,
    /// Build nodes for structural fields too — padding, custom markers, the
    /// terminator — as raw bytes at their offsets. What an expert view shows;
    /// nothing else wants them.
    structural: bool,
    /// An element to show, by block path (`vehicles`, `bsp[0].surfaces`): the
    /// block builds the `max_elements`-wide page holding it rather than the
    /// first page. Paths are only tracked when this is non-empty.
    windows: Option<&'v HashMap<String, usize>>,
}

impl Walk<'_> {
    fn tracks_paths(&self) -> bool {
        self.windows.is_some_and(|w| !w.is_empty())
    }

    /// The first element to build of the block at `path`, holding `count`.
    fn first_element(&self, path: &str, count: usize) -> usize {
        let Some(&wanted) = self.windows.and_then(|w| w.get(path)) else {
            return 0;
        };
        if count == 0 || self.max_elements == 0 {
            return 0;
        }
        // A window can outlive the elements it pointed at; land on the last.
        let wanted = wanted.min(count - 1);
        wanted / self.max_elements * self.max_elements
    }
}

/// `base.name`, the path the editor's edits name a field by. Names are
/// trimmed, as [`crate::patch::segments`] trims them.
fn join(base: &str, name: &str) -> String {
    let segment = crate::patch::escape_segment(name.trim());
    if base.is_empty() {
        segment
    } else {
        format!("{base}.{segment}")
    }
}

/// A field path rebuilt the way the walk spells paths, so a window key
/// matches however its writer spaced or escaped it.
pub fn window_key(path: &str) -> String {
    let mut out = String::new();
    for (name, index) in crate::patch::segments(path) {
        out = join(&out, &name);
        if let Some(i) = index {
            out = format!("{out}[{i}]");
        }
    }
    out
}

/// Windows that reach element `element` of the block at `path`, and every
/// block element `path` passes through on the way (`a[70].b` pages `a` to
/// 70 too).
pub fn windows_to(path: &str, element: usize) -> HashMap<String, usize> {
    let mut windows = HashMap::new();
    let mut base = String::new();
    for (name, index) in crate::patch::segments(path) {
        base = join(&base, &name);
        if let Some(i) = index {
            windows.insert(base.clone(), i);
            base = format!("{base}[{i}]");
        }
    }
    windows.insert(base, element);
    windows
}

/// Default cap on block elements built per node.
///
/// A `scenario_structure_bsp` holds millions of elements; building them all
/// costs tens of gigabytes and no interface can show them at once. Callers that
/// genuinely need every element should use [`visit_fields`], which walks all of
/// them without allocating.
pub const DEFAULT_MAX_ELEMENTS: usize = 64;

/// Default cap on total nodes built for one tag.
pub const DEFAULT_MAX_NODES: usize = 200_000;

/// Build the value tree for a tag: the fields of the root block's one element.
///
/// Blocks and arrays are capped at [`DEFAULT_MAX_ELEMENTS`] materialised
/// elements; `Node::count` carries how many there really are.
pub fn root(layout: &Layout<'_>, block: &Block<'_>) -> Vec<Node> {
    root_capped(layout, block, DEFAULT_MAX_ELEMENTS)
}

/// [`root`], with an explicit cap on elements built per block.
pub fn root_capped(layout: &Layout<'_>, block: &Block<'_>, max_elements: usize) -> Vec<Node> {
    root_windowed(layout, block, max_elements, false, &HashMap::new())
}

/// [`root_capped`], with the structural fields — padding, `custom` markers,
/// the `terminator X` — built as read-only leaves holding their raw bytes.
/// The layout's every byte becomes visible, which is what an expert wants
/// when a definition looks wrong.
pub fn root_expert(layout: &Layout<'_>, block: &Block<'_>, max_elements: usize) -> Vec<Node> {
    root_windowed(layout, block, max_elements, true, &HashMap::new())
}

/// The value tree, with chosen blocks paged past their first `max_elements`.
///
/// `windows` maps a block's path — as edits name it, `vehicles` or
/// `bsp[0].surfaces` — to an element the caller wants built. That block then
/// builds the page of `max_elements` holding the element, and its
/// [`Node::first`] says where the page starts. Every other block builds its
/// first page, as [`root_capped`] does. `structural` is [`root_expert`]'s
/// switch.
pub fn root_windowed(
    layout: &Layout<'_>,
    block: &Block<'_>,
    max_elements: usize,
    structural: bool,
    windows: &HashMap<String, usize>,
) -> Vec<Node> {
    let windows: HashMap<String, usize> = windows
        .iter()
        .map(|(path, &element)| (window_key(path), element))
        .collect();
    let mut walk = Walk {
        visit: &mut |_, _| {},
        build: true,
        max_elements,
        budget: DEFAULT_MAX_NODES,
        structural,
        windows: Some(&windows),
    };
    run(layout, block, &mut walk)
}

/// Visit every fixed-width field of every element, allocating nothing.
///
/// This is the whole-tag traversal: no cap, no `Node`s. Use it for checks over
/// the real data, where building the tree would exhaust memory.
pub fn visit_fields(
    layout: &Layout<'_>,
    block: &Block<'_>,
    visit: &mut dyn FnMut(&crate::layout::FieldEntry, &[u8]),
) {
    let mut walk = Walk {
        visit,
        build: false,
        max_elements: usize::MAX,
        budget: usize::MAX,
        structural: false,
        windows: None,
    };
    run(layout, block, &mut walk);
}

fn run(layout: &Layout<'_>, block: &Block<'_>, walk: &mut Walk<'_>) -> Vec<Node> {
    let Some(run) = layout.struct_run(block.struct_index) else {
        return Vec::new();
    };
    let bytes = block.element(0).unwrap_or(&[]);
    let values = block.children.first().map(Vec::as_slice).unwrap_or(&[]);
    fields(layout, run, bytes, values, 0, "", walk)
}

/// Build the nodes for one struct run against one element's bytes and values.
/// `base` is the element's path, kept only while the walk tracks paths.
fn fields(
    layout: &Layout<'_>,
    run: usize,
    bytes: &[u8],
    values: &[Value<'_>],
    depth: u32,
    base: &str,
    walk: &mut Walk<'_>,
) -> Vec<Node> {
    if depth > 64 {
        return Vec::new();
    }
    let Some(range) = layout.struct_ranges().get(run).cloned() else {
        return Vec::new();
    };

    let mut out = Vec::new();
    let mut offset = 0u32;
    // Values arrive in the order the writing fields are declared.
    let mut next_value = 0usize;

    for index in range {
        let field = layout.fields[index];
        let type_name = layout.type_name_of(&field).to_string();
        let size = layout.field_size(&field).unwrap_or(0);
        let name = layout.string_at(field.name_offset).unwrap_or("").to_string();

        let value = if field_writes(layout, &field) {
            // A phantom pairs with no field; step over it.
            while matches!(values.get(next_value), Some(Value::Phantom)) {
                next_value += 1;
            }
            let v = values.get(next_value);
            next_value += 1;
            v
        } else {
            None
        };

        if structural(&type_name) {
            if walk.build && walk.structural && walk.budget > 0 {
                let slice = bytes
                    .get(offset as usize..(offset + size) as usize)
                    .unwrap_or(&[]);
                let shown = if name.trim().is_empty() {
                    type_name.clone()
                } else {
                    name.clone()
                };
                walk.budget -= 1;
                out.push(Node::leaf(
                    shown,
                    type_name.clone(),
                    offset,
                    size,
                    Scalar::Raw(slice.to_vec()),
                ));
            }
            offset += size;
            continue;
        }

        let slice = bytes
            .get(offset as usize..(offset + size) as usize)
            .unwrap_or(&[]);

        let nests = matches!(type_name.as_str(), "block" | "struct" | "array");
        let path = if nests && walk.tracks_paths() {
            join(base, &name)
        } else {
            String::new()
        };
        let node = match type_name.as_str() {
            "block" => block_node(
                layout,
                &field,
                name,
                type_name.clone(),
                offset,
                size,
                value,
                depth,
                &path,
                walk,
            ),
            "struct" => {
                let children = layout
                    .struct_run(field.aux as usize)
                    .map(|target| {
                        let inner = match value {
                            Some(Value::Struct { children }) => children.as_slice(),
                            _ => &[][..],
                        };
                        fields(layout, target, slice, inner, depth + 1, &path, walk)
                    })
                    .unwrap_or_default();
                Node {
                    kind: Kind::Struct,
                    children,
                    ..Node::leaf(name, type_name.clone(), offset, size, Scalar::Empty)
                }
            }
            "array" => array_node(
                layout,
                &field,
                name,
                type_name.clone(),
                offset,
                size,
                value,
                slice,
                depth,
                &path,
                walk,
            ),
            _ => {
                (walk.visit)(&field, slice);
                if !walk.build {
                    offset += size;
                    continue;
                }
                let mut node = Node::leaf(
                    name,
                    type_name.clone(),
                    offset,
                    size,
                    value::read(layout, &field, slice),
                );
                if layout.has_options(&field) {
                    node.options = layout
                        .field_options(&field)
                        .into_iter()
                        .map(String::from)
                        .collect();
                }
                // A `string id`, `data` or `tag reference` keeps its text in a
                // trailing section rather than inline; prefer that over the
                // handle bytes.
                if let Some(text) = section_text(value) {
                    node.value = text;
                }
                node
            }
        };

        if walk.build {
            walk.budget = walk.budget.saturating_sub(1);
            out.push(node);
        }
        offset += size;
    }
    out
}

/// The readable payload of a section-backed field, if it has one.
fn section_text(value: Option<&Value<'_>>) -> Option<Scalar> {
    match value? {
        Value::StringId(b) => {
            let end = b.iter().position(|c| *c == 0).unwrap_or(b.len());
            Some(Scalar::Text(String::from_utf8_lossy(&b[..end]).into_owned()))
        }
        Value::TagRef(b) => Some(value::reference(b)),
        Value::Data(b) => Some(Scalar::Raw(b.to_vec())),
        _ => None,
    }
}

#[allow(clippy::too_many_arguments)]
fn block_node(
    layout: &Layout<'_>,
    field: &crate::layout::FieldEntry,
    name: String,
    type_name: String,
    offset: u32,
    size: u32,
    value: Option<&Value<'_>>,
    depth: u32,
    path: &str,
    walk: &mut Walk<'_>,
) -> Node {
    let entry = layout.blocks.get(field.aux as usize).copied();
    let mut node = Node {
        kind: Kind::Block,
        block_name: entry.and_then(|b| layout.string_at(b.name_offset)).map(String::from),
        max_count: entry.map(|b| b.max_count),
        ..Node::leaf(name, type_name, offset, size, Scalar::Empty)
    };

    let Some(Value::Block(inner)) = value else {
        return node;
    };
    let Some(run) = layout.struct_run(inner.struct_index) else {
        return node;
    };

    node.count = Some(inner.count);
    // A pure visit walks every element; building one stops at the cap, on
    // the page a window asked for.
    let count = inner.count as usize;
    let (first, end) = if walk.build {
        let first = walk.first_element(path, count);
        (first, count.min(first.saturating_add(walk.max_elements)))
    } else {
        (0, count)
    };
    node.first = first as u32;
    for i in first..end {
        if walk.build && walk.budget == 0 {
            break;
        }
        let bytes = inner.element(i).unwrap_or(&[]);
        let values = inner.children.get(i).map(Vec::as_slice).unwrap_or(&[]);
        let element_path = if walk.tracks_paths() {
            format!("{path}[{i}]")
        } else {
            String::new()
        };
        let children = fields(layout, run, bytes, values, depth + 1, &element_path, walk);
        if !walk.build {
            continue;
        }
        node.children.push(Node {
            kind: Kind::Element,
            children,
            ..Node::leaf(
                format!("[{i}]"),
                String::new(),
                (i as u32) * inner.element_size,
                inner.element_size,
                Scalar::Empty,
            )
        });
    }
    node
}

#[allow(clippy::too_many_arguments)]
fn array_node(
    layout: &Layout<'_>,
    field: &crate::layout::FieldEntry,
    name: String,
    type_name: String,
    offset: u32,
    size: u32,
    value: Option<&Value<'_>>,
    slice: &[u8],
    depth: u32,
    path: &str,
    walk: &mut Walk<'_>,
) -> Node {
    let mut node = Node {
        kind: Kind::Array,
        ..Node::leaf(name, type_name, offset, size, Scalar::Empty)
    };

    let Some(entry) = layout.arrays.get(field.aux as usize).copied() else {
        return node;
    };
    let Some(run) = layout.struct_run(entry.struct_index as usize) else {
        return node;
    };
    let element_size = size.checked_div(entry.count).unwrap_or(0);

    node.count = Some(entry.count);
    for i in 0..entry.count {
        if walk.build && walk.budget == 0 {
            break;
        }
        // An array repeats its element struct inline, so element `i` starts
        // `i * element_size` into the array field's own bytes.
        let start = (i * element_size) as usize;
        let bytes = slice
            .get(start..start + element_size as usize)
            .unwrap_or(&[]);
        let values = match value {
            Some(Value::Array { children }) => match children.get(i as usize) {
                Some(Value::Struct { children }) => children.as_slice(),
                _ => &[][..],
            },
            _ => &[][..],
        };
        let element_path = if walk.tracks_paths() {
            format!("{path}[{i}]")
        } else {
            String::new()
        };
        let children = fields(layout, run, bytes, values, depth + 1, &element_path, walk);
        if !walk.build {
            continue;
        }
        node.children.push(Node {
            kind: Kind::Element,
            children,
            ..Node::leaf(
                format!("[{i}]"),
                String::new(),
                offset + i * element_size,
                element_size,
                Scalar::Empty,
            )
        });
    }
    node
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::layout::tests::{section_bytes, synth_camera_track, words};

    /// A camera_track payload whose control-points block holds `n` elements.
    ///
    /// The root block carries one element wrapper; the inner block is flagged
    /// `1`, so its fixed-width elements follow the header with no wrappers.
    fn camera_track_payload(n: u32) -> Vec<u8> {
        let mut inner = words(&[n, 1]);
        inner.extend(std::iter::repeat_n(0u8, n as usize * 28));
        let wrapper = section_bytes(b"lbgt", 0, &inner);

        let mut out = words(&[1, 0]);
        out.extend_from_slice(&[0u8; 12]);
        out.extend_from_slice(&section_bytes(b"tsgt", wrapper.len() as u32, &wrapper));
        out
    }

    fn control_points(n: u32, cap: usize) -> Node {
        let body = synth_camera_track();
        let layout = Layout::parse(&body).expect("layout");
        let payload = camera_track_payload(n);
        let block = crate::data::read_block(&layout, &payload, 0).expect("walk");
        let mut nodes = root_capped(&layout, &block, cap);
        assert_eq!(nodes.len(), 1, "the root declares one block field");
        nodes.remove(0)
    }

    /// A block's `count` is what the tag holds, whatever the element cap
    /// materialised. Conflating the two is what made `mjolnir values` report
    /// exactly 64 string references for every `unic` tag carrying more.
    #[test]
    fn a_block_counts_every_element_past_the_build_cap() {
        let node = control_points(318, DEFAULT_MAX_ELEMENTS);

        assert_eq!(node.kind, Kind::Block);
        assert_eq!(node.count, Some(318));
        assert_eq!(
            node.children.len(),
            DEFAULT_MAX_ELEMENTS,
            "the cap bounds what is built, not what is counted"
        );
    }

    /// Raising the cap materialises the rest, so a caller asking for every
    /// element gets every element rather than the first 64.
    #[test]
    fn a_raised_cap_materialises_every_element() {
        let node = control_points(318, 4000);

        assert_eq!(node.count, Some(318));
        assert_eq!(node.children.len(), 318);
    }

    /// The cap is per block, so a count under it is materialised whole and the
    /// two numbers agree — the case that hid the defect (`team_names` reports 9
    /// correctly).
    #[test]
    fn a_block_under_the_cap_is_built_whole() {
        let node = control_points(9, DEFAULT_MAX_ELEMENTS);

        assert_eq!(node.count, Some(9));
        assert_eq!(node.children.len(), 9);
    }

    /// A window pages a block past its first 64, so an element added after
    /// the 64th can be built, shown and edited. Asking past the end lands on
    /// the last page; a block nobody asked about keeps its first page.
    #[test]
    fn a_window_builds_the_page_holding_the_wanted_element() {
        let body = synth_camera_track();
        let layout = Layout::parse(&body).expect("layout");
        let payload = camera_track_payload(318);
        let block = crate::data::read_block(&layout, &payload, 0).expect("walk");
        let name = root_capped(&layout, &block, DEFAULT_MAX_ELEMENTS).remove(0).name;
        let page = |wanted: usize, path: &str| {
            let windows = HashMap::from([(path.to_string(), wanted)]);
            root_windowed(&layout, &block, DEFAULT_MAX_ELEMENTS, false, &windows).remove(0)
        };

        let node = page(70, &escape(&name));
        assert_eq!(node.first, 64);
        assert_eq!(node.count, Some(318));
        assert_eq!(node.children.len(), 64);
        assert_eq!(node.children[0].name, "[64]");

        let node = page(10_000, &escape(&name));
        assert_eq!(node.first, 256, "past the end lands on the last page");
        assert_eq!(node.children.len(), 62);
        assert_eq!(node.children.last().unwrap().name, "[317]");

        let node = page(70, "some other block");
        assert_eq!(node.first, 0);
        assert_eq!(node.children[0].name, "[0]");
    }

    fn escape(name: &str) -> String {
        crate::patch::escape_segment(name)
    }

    #[test]
    fn a_window_reaches_through_every_block_on_its_path() {
        assert_eq!(
            windows_to("bsp[70].surfaces", 3),
            HashMap::from([("bsp".to_string(), 70), ("bsp[70].surfaces".to_string(), 3)])
        );
        assert_eq!(windows_to("vehicles", 64), HashMap::from([("vehicles".to_string(), 64)]));
        assert_eq!(window_key("hud[2].message anchor v\\[0,1\\]"), "hud[2].message anchor v\\[0,1\\]");
        assert_eq!(window_key(" vehicles "), "vehicles");
    }

    #[test]
    fn structural_types_are_not_shown() {
        assert!(structural("pad"));
        assert!(structural("terminator X"));
        assert!(structural("custom"));
        assert!(!structural("real"));
        assert!(!structural("block"));
    }

    #[test]
    fn the_expert_root_shows_structural_fields_as_raw_bytes() {
        let file = crate::patch::tests::synth_block_file();
        let tag = crate::TagFile::parse(&file, Some(file.len())).unwrap();
        let layout = tag.layout().unwrap();
        let block = tag.read_data(&layout).unwrap();
        let plain = root(&layout, &block);
        let expert = root_expert(&layout, &block, DEFAULT_MAX_ELEMENTS);
        let count = |nodes: &[Node]| -> usize {
            fn walk(n: &Node, f: &mut dyn FnMut(&Node)) {
                f(n);
                for c in &n.children {
                    walk(c, f);
                }
            }
            let mut structural = 0;
            for n in nodes {
                walk(n, &mut |n| {
                    if matches!(n.type_name.as_str(), "pad" | "custom" | "terminator X") {
                        structural += 1;
                    }
                });
            }
            structural
        };
        assert_eq!(count(&plain), 0, "the plain view hides structural fields");
        // The synthetic fixture may or may not carry padding; when it does,
        // the expert view shows it as bytes with a size.
        for n in &expert {
            if matches!(n.type_name.as_str(), "pad" | "custom" | "terminator X") {
                assert!(matches!(n.value, Scalar::Raw(_)));
                assert!(n.size > 0 || n.type_name == "terminator X");
            }
        }
        assert!(expert.len() >= plain.len());
    }

    #[test]
    fn a_node_counts_its_whole_subtree() {
        let leaf = Node::leaf("a".into(), "real".into(), 0, 4, Scalar::Real(1.0));
        let parent = Node {
            kind: Kind::Struct,
            children: vec![leaf.clone(), leaf.clone()],
            ..Node::leaf("s".into(), "struct".into(), 0, 8, Scalar::Empty)
        };
        assert_eq!(parent.len(), 3);
    }
}

/// Which bytes of `file` hold fixed-width scalar values — numbers, angles,
/// flags, enums: everything that is a *value* rather than a reference.
///
/// A runtime that resolves a tag in place rewrites its references — string
/// ids become handles, tag references become pointers, block indices are
/// re-based — and leaves the numbers where the file put them. So the scalar
/// bytes are what survives to be matched against memory. One flag per byte
/// of `file`; everything outside a scalar field — block headers, section
/// wrappers, the header and layout sections — is `false`.
pub fn scalar_mask(layout: &Layout<'_>, block: &Block<'_>, file: &[u8]) -> Vec<bool> {
    let mut mask = vec![false; file.len()];
    let lo = file.as_ptr() as usize;
    visit_fields(layout, block, &mut |field, bytes| {
        if bytes.is_empty() || !scalar(layout.type_name_of(field)) {
            return;
        }
        let at = bytes.as_ptr() as usize;
        if at < lo || at + bytes.len() > lo + file.len() {
            return;
        }
        let off = at - lo;
        mask[off..off + bytes.len()].iter_mut().for_each(|b| *b = true);
    });
    mask
}

/// Types whose bytes are a value, not a reference the runtime resolves.
fn scalar(type_name: &str) -> bool {
    matches!(
        type_name,
        "real"
            | "real fraction"
            | "angle"
            | "real bounds"
            | "angle bounds"
            | "fraction bounds"
            | "real point 2d"
            | "real vector 2d"
            | "real euler angles 2d"
            | "real point 3d"
            | "real vector 3d"
            | "real euler angles 3d"
            | "real rgb color"
            | "real plane 2d"
            | "real argb color"
            | "real plane 3d"
            | "real quaternion"
            | "char integer"
            | "byte integer"
            | "short integer"
            | "word integer"
            | "long integer"
            | "int64 integer"
            | "short integer bounds"
            | "rectangle 2d"
            | "byte flags"
            | "word flags"
            | "long flags"
            | "char enum"
            | "short enum"
            | "long enum"
            | "rgb color"
            | "argb color"
    )
}
