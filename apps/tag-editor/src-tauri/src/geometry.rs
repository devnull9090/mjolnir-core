//! Renderable geometry from Blam tags.
//!
//! The shipped game carries no render meshes in its tag data — visuals are
//! Unreal packages — but the simulation geometry is complete: `collision_model`
//! holds a winged-edge collision BSP per region/permutation, attached to a
//! skeleton node, and `skeleton_model` holds the node hierarchy, rest pose and
//! marker groups. Together they draw a faithful, posable shell of any object.
//!
//! Everything here reads field offsets from the tag's own `blay` layout — the
//! same rule the rest of the editor follows — so a game update that moves a
//! field moves the reader with it.

use blam_tag::data::{Block, Value};
use blam_tag::Layout;
use serde::Serialize;

/// Combined geometry for one object, ready for the viewer.
#[derive(Serialize, Default)]
pub struct ModelGeometry {
    /// Short path of the collision_model the meshes came from.
    pub collision: Option<String>,
    /// Short path of the skeleton_model the nodes came from.
    pub skeleton: Option<String>,
    pub meshes: Vec<CollisionMesh>,
    pub nodes: Vec<SkeletonNode>,
    pub marker_groups: Vec<MarkerGroup>,
}

/// One collision BSP, triangulated. Vertices are in the local space of the
/// skeleton node the BSP is attached to.
#[derive(Serialize)]
pub struct CollisionMesh {
    pub region: String,
    pub permutation: String,
    /// Skeleton node this piece attaches to, or -1.
    pub node: i32,
    /// xyz triplets.
    pub positions: Vec<f32>,
    /// Triangle list into `positions`.
    pub indices: Vec<u32>,
    /// One surface-flag word per triangle (bit 0 two sided, bit 1 invisible,
    /// bit 2 climbable, bit 3 breakable).
    pub flags: Vec<u16>,
}

#[derive(Serialize)]
pub struct SkeletonNode {
    pub name: String,
    /// Parent node index, or -1 at the root.
    pub parent: i32,
    /// Rest-pose translation relative to the parent.
    pub translation: [f32; 3],
    /// Rest-pose rotation relative to the parent, as i j k w.
    pub rotation: [f32; 4],
}

#[derive(Serialize)]
pub struct MarkerGroup {
    pub name: String,
    pub markers: Vec<Marker>,
}

#[derive(Serialize)]
pub struct Marker {
    /// Skeleton node the marker hangs off, or -1.
    pub node: i32,
    pub translation: [f32; 3],
    pub rotation: [f32; 4],
}

/// A tag reference another tag must be resolved through.
pub struct GeometryRef {
    /// Target group's long name, known from the field that held the reference.
    pub group: &'static str,
    /// Tag path as written, backslash-separated.
    pub path: String,
}

// ---------------------------------------------------------------------------
// Layout-driven element access

/// One block element: its packed bytes plus its variable-length values, with
/// the struct run that describes both.
struct Elem<'a, 'b> {
    layout: &'b Layout<'a>,
    run: usize,
    bytes: &'b [u8],
    values: &'b [Value<'a>],
}

impl<'a, 'b> Elem<'a, 'b> {
    fn of(layout: &'b Layout<'a>, block: &'b Block<'a>, index: usize) -> Option<Self> {
        Some(Elem {
            layout,
            run: layout.struct_run(block.struct_index)?,
            bytes: block.element(index)?,
            values: block.children.get(index).map(Vec::as_slice).unwrap_or(&[]),
        })
    }

    /// Byte offset and size of a named field, accumulated the way `view.rs`
    /// walks a struct run.
    fn offset(&self, name: &str) -> Option<(usize, usize)> {
        let range = self.layout.struct_ranges().get(self.run)?.clone();
        let mut offset = 0usize;
        for i in range {
            let f = self.layout.fields[i];
            let size = self.layout.field_size(&f).unwrap_or(0) as usize;
            if self.layout.string_at(f.name_offset) == Some(name) {
                return Some((offset, size));
            }
            offset += size;
        }
        None
    }

    /// The variable-length value paired with a named field, honouring the
    /// phantom-skipping rule the view walk uses.
    fn value(&self, name: &str) -> Option<&'b Value<'a>> {
        let range = self.layout.struct_ranges().get(self.run)?.clone();
        let mut next = 0usize;
        for i in range {
            let f = self.layout.fields[i];
            if !blam_tag::data::field_writes(self.layout, &f) {
                continue;
            }
            while matches!(self.values.get(next), Some(Value::Phantom)) {
                next += 1;
            }
            let v = self.values.get(next);
            next += 1;
            if self.layout.string_at(f.name_offset) == Some(name) {
                return v;
            }
        }
        None
    }

    fn block(&self, name: &str) -> Option<&'b Block<'a>> {
        match self.value(name)? {
            Value::Block(b) => Some(b),
            _ => None,
        }
    }

    /// A nested `struct` field as an element view over its slice of bytes.
    fn nested(&self, name: &str) -> Option<Elem<'a, 'b>> {
        let (offset, size) = self.offset(name)?;
        let range = self.layout.struct_ranges().get(self.run)?.clone();
        // Find the field again for its aux (struct-table index).
        let field = range
            .map(|i| self.layout.fields[i])
            .find(|f| self.layout.string_at(f.name_offset) == Some(name))?;
        let children = match self.value(name) {
            Some(Value::Struct { children }) => children.as_slice(),
            _ => &[],
        };
        Some(Elem {
            layout: self.layout,
            run: self.layout.struct_run(field.aux as usize)?,
            bytes: self.bytes.get(offset..offset + size)?,
            values: children,
        })
    }

    fn string_id(&self, name: &str) -> String {
        match self.value(name) {
            Some(Value::StringId(b)) => String::from_utf8_lossy(b).into_owned(),
            _ => String::new(),
        }
    }

    fn f32(&self, name: &str, at: usize) -> f32 {
        let Some((offset, _)) = self.offset(name) else {
            return 0.0;
        };
        read_f32(self.bytes, offset + at * 4)
    }

    fn vec3(&self, name: &str) -> [f32; 3] {
        [self.f32(name, 0), self.f32(name, 1), self.f32(name, 2)]
    }

    fn quat(&self, name: &str) -> [f32; 4] {
        [
            self.f32(name, 0),
            self.f32(name, 1),
            self.f32(name, 2),
            self.f32(name, 3),
        ]
    }

    fn i16(&self, name: &str) -> i16 {
        let Some((offset, _)) = self.offset(name) else {
            return -1;
        };
        read_i16(self.bytes, offset)
    }
}

fn read_f32(bytes: &[u8], offset: usize) -> f32 {
    bytes
        .get(offset..offset + 4)
        .map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]]))
        .unwrap_or(0.0)
}

fn read_i16(bytes: &[u8], offset: usize) -> i16 {
    bytes
        .get(offset..offset + 2)
        .map(|b| i16::from_le_bytes([b[0], b[1]]))
        .unwrap_or(-1)
}

fn read_u16(bytes: &[u8], offset: usize) -> u16 {
    bytes
        .get(offset..offset + 2)
        .map(|b| u16::from_le_bytes([b[0], b[1]]))
        .unwrap_or(u16::MAX)
}

/// Parse a tag file down to its root element.
fn root<'a>(
    file: &'a [u8],
) -> Result<(blam_tag::TagFile<'a>, Layout<'a>, Block<'a>), String> {
    let tag = blam_tag::TagFile::parse(file, None).map_err(|e| e.to_string())?;
    let layout = tag.layout().map_err(|e| e.to_string())?;
    let block = tag.read_data(&layout).map_err(|e| e.to_string())?;
    Ok((tag, layout, block))
}

// ---------------------------------------------------------------------------
// collision_model

/// Sentinel for "no edge / no vertex" in the 16-bit winged-edge tables.
const NONE16: u16 = u16::MAX;

/// Triangulate every collision BSP of a `collision_model` tag.
pub fn collision_meshes(file: &[u8]) -> Result<Vec<CollisionMesh>, String> {
    let (_tag, layout, block) = root(file)?;
    let root = Elem::of(&layout, &block, 0).ok_or("empty tag")?;
    let mut out = Vec::new();

    let Some(regions) = root.block("regions") else {
        return Ok(out);
    };
    for r in 0..regions.count as usize {
        let Some(region) = Elem::of(&layout, regions, r) else {
            continue;
        };
        let region_name = region.string_id("name");
        let Some(permutations) = region.block("permutations") else {
            continue;
        };
        for p in 0..permutations.count as usize {
            let Some(permutation) = Elem::of(&layout, permutations, p) else {
                continue;
            };
            let permutation_name = permutation.string_id("name");
            let Some(bsps) = permutation.block("bsps") else {
                continue;
            };
            for b in 0..bsps.count as usize {
                let Some(holder) = Elem::of(&layout, bsps, b) else {
                    continue;
                };
                let node = holder.i16("node index") as i32;
                let Some(bsp) = holder.nested("bsp") else {
                    continue;
                };
                if let Some(mesh) = triangulate_bsp(&layout, &bsp) {
                    out.push(CollisionMesh {
                        region: region_name.clone(),
                        permutation: permutation_name.clone(),
                        node,
                        positions: mesh.0,
                        indices: mesh.1,
                        flags: mesh.2,
                    });
                }
            }
        }
    }
    Ok(out)
}

/// Walk one winged-edge BSP into a triangle list.
///
/// Each surface's boundary is an edge loop: follow `forward edge` when the
/// surface is the edge's left face, `reverse edge` when it is the right, then
/// fan-triangulate the polygon from its first vertex.
fn triangulate_bsp(
    layout: &Layout<'_>,
    bsp: &Elem<'_, '_>,
) -> Option<(Vec<f32>, Vec<u32>, Vec<u16>)> {
    let vertices = bsp.block("vertices")?;
    let edges = bsp.block("edges")?;
    let surfaces = bsp.block("surfaces")?;

    // Field offsets are per-block constants; resolve them once from element 0.
    let v0 = Elem::of(layout, vertices, 0)?;
    let (point_off, _) = v0.offset("point")?;
    let e0 = Elem::of(layout, edges, 0)?;
    let (start_off, _) = e0.offset("start vertex")?;
    let (end_off, _) = e0.offset("end vertex")?;
    let (fwd_off, _) = e0.offset("forward edge")?;
    let (rev_off, _) = e0.offset("reverse edge")?;
    let (left_off, _) = e0.offset("left surface")?;
    let s0 = Elem::of(layout, surfaces, 0)?;
    let (first_edge_off, _) = s0.offset("first edge")?;
    let (flags_off, _) = s0.offset("flags")?;

    let mut positions = Vec::with_capacity(vertices.count as usize * 3);
    for i in 0..vertices.count as usize {
        let bytes = vertices.element(i)?;
        positions.push(read_f32(bytes, point_off));
        positions.push(read_f32(bytes, point_off + 4));
        positions.push(read_f32(bytes, point_off + 8));
    }

    let mut indices = Vec::new();
    let mut flags = Vec::new();
    for s in 0..surfaces.count as usize {
        let surface = surfaces.element(s)?;
        let first_edge = read_u16(surface, first_edge_off);
        if first_edge == NONE16 {
            continue;
        }
        let flag_word = read_u16(surface, flags_off);

        // Collect the polygon's vertex loop.
        let mut polygon: Vec<u32> = Vec::new();
        let mut cursor = first_edge;
        for _ in 0..64 {
            let Some(edge) = edges.element(cursor as usize) else {
                break;
            };
            if read_u16(edge, left_off) == s as u16 {
                polygon.push(read_u16(edge, start_off) as u32);
                cursor = read_u16(edge, fwd_off);
            } else {
                polygon.push(read_u16(edge, end_off) as u32);
                cursor = read_u16(edge, rev_off);
            }
            if cursor == first_edge || cursor == NONE16 {
                break;
            }
        }
        if polygon.len() < 3 {
            continue;
        }
        for i in 1..polygon.len() - 1 {
            indices.push(polygon[0]);
            indices.push(polygon[i]);
            indices.push(polygon[i + 1]);
            flags.push(flag_word);
        }
    }

    Some((positions, indices, flags))
}

// ---------------------------------------------------------------------------
// skeleton_model

/// Node hierarchy and marker groups of a `skeleton_model` tag.
pub fn skeleton(file: &[u8]) -> Result<(Vec<SkeletonNode>, Vec<MarkerGroup>), String> {
    let (_tag, layout, block) = root(file)?;
    let root = Elem::of(&layout, &block, 0).ok_or("empty tag")?;

    let mut nodes = Vec::new();
    if let Some(list) = root.block("nodes") {
        for i in 0..list.count as usize {
            let Some(node) = Elem::of(&layout, list, i) else {
                continue;
            };
            nodes.push(SkeletonNode {
                name: node.string_id("name"),
                parent: node.i16("parent node") as i32,
                translation: node.vec3("default translation"),
                rotation: node.quat("default rotation"),
            });
        }
    }

    let mut marker_groups = Vec::new();
    if let Some(groups) = root.block("marker groups") {
        for g in 0..groups.count as usize {
            let Some(group) = Elem::of(&layout, groups, g) else {
                continue;
            };
            let mut markers = Vec::new();
            if let Some(list) = group.block("markers") {
                for m in 0..list.count as usize {
                    let Some(marker) = Elem::of(&layout, list, m) else {
                        continue;
                    };
                    markers.push(Marker {
                        node: marker.i16("node index") as i32,
                        translation: marker.vec3("translation"),
                        rotation: marker.quat("rotation"),
                    });
                }
            }
            marker_groups.push(MarkerGroup {
                name: group.string_id("name"),
                markers,
            });
        }
    }

    Ok((nodes, marker_groups))
}

// ---------------------------------------------------------------------------
// model (hlmt)

/// The geometry-bearing references of a `model` (hlmt) tag.
pub fn model_refs(file: &[u8]) -> Result<Vec<GeometryRef>, String> {
    let (_tag, layout, block) = root(file)?;
    let root = Elem::of(&layout, &block, 0).ok_or("empty tag")?;
    let mut out = Vec::new();
    for (field, group) in [
        ("collision model", "collision_model"),
        ("skeleton model", "skeleton_model"),
    ] {
        if let Some(Value::TagRef(content)) = root.value(field) {
            if let blam_tag::Scalar::Reference { path, .. } =
                blam_tag::value::reference(content)
            {
                if !path.is_empty() {
                    out.push(GeometryRef {
                        group,
                        path,
                    });
                }
            }
        }
    }
    Ok(out)
}
