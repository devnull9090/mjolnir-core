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
///
/// Index fields are 16-bit in `collision_model` and the per-instance BSPs but
/// 32-bit in the sbsp's `large collision bsp`, so their widths come from the
/// layout like everything else. `NONE` is the all-ones value of either width.
fn triangulate_bsp(
    layout: &Layout<'_>,
    bsp: &Elem<'_, '_>,
) -> Option<(Vec<f32>, Vec<u32>, Vec<u16>)> {
    let vertices = bsp.block("vertices")?;
    let edges = bsp.block("edges")?;
    let surfaces = bsp.block("surfaces")?;
    if vertices.count == 0 || surfaces.count == 0 {
        return None;
    }

    // Field offsets are per-block constants; resolve them once from element 0.
    let v0 = Elem::of(layout, vertices, 0)?;
    let (point_off, _) = v0.offset("point")?;
    let e0 = Elem::of(layout, edges, 0)?;
    let start = e0.offset("start vertex")?;
    let end = e0.offset("end vertex")?;
    let fwd = e0.offset("forward edge")?;
    let rev = e0.offset("reverse edge")?;
    let left = e0.offset("left surface")?;
    let s0 = Elem::of(layout, surfaces, 0)?;
    let first = s0.offset("first edge")?;
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
    let mut polygon: Vec<u32> = Vec::new();
    for s in 0..surfaces.count as usize {
        let surface = surfaces.element(s)?;
        let first_edge = read_index(surface, first);
        if first_edge == NONE {
            continue;
        }
        let flag_word = read_u16(surface, flags_off);

        // Collect the polygon's vertex loop.
        polygon.clear();
        let mut cursor = first_edge;
        for _ in 0..128 {
            let Some(edge) = edges.element(cursor as usize) else {
                break;
            };
            if read_index(edge, left) == s as u32 {
                polygon.push(read_index(edge, start));
                cursor = read_index(edge, fwd);
            } else {
                polygon.push(read_index(edge, end));
                cursor = read_index(edge, rev);
            }
            if cursor == first_edge || cursor == NONE {
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

/// An index field of whichever width the layout declares, widened to u32 with
/// the all-ones "none" preserved.
fn read_index(bytes: &[u8], (offset, size): (usize, usize)) -> u32 {
    if size == 4 {
        bytes
            .get(offset..offset + 4)
            .map(|b| u32::from_le_bytes([b[0], b[1], b[2], b[3]]))
            .unwrap_or(NONE)
    } else {
        match read_u16(bytes, offset) {
            NONE16 => NONE,
            v => v as u32,
        }
    }
}

const NONE: u32 = u32::MAX;

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
// scenario_structure_bsp

/// One triangulated collision mesh, before packing.
struct WorldMesh {
    positions: Vec<f32>,
    indices: Vec<u32>,
    flags: Vec<u16>,
}

/// The level's collision world, packed for the viewer:
///
/// ```text
/// u32 magic "SBSP"    u32 json length    json header    aligned payload
/// ```
///
/// The header carries counts; the payload is the buffers in a fixed order —
/// per definition `positions f32×3v / indices u32×3t / flags u32×t`, then the
/// world mesh the same way, then instances at 56 bytes each (`def u32,
/// scale f32, forward ×3, left ×3, up ×3, position ×3`). Everything the level
/// stands on is instanced geometry: 754 definitions placed 11,381 times on
/// a30, which is exactly the shape `InstancedMesh` wants.
pub fn sbsp_world(file: &[u8]) -> Result<Vec<u8>, String> {
    let (_tag, layout, block) = root(file)?;
    let root = Elem::of(&layout, &block, 0).ok_or("empty tag")?;

    // The definitions and the world BSP live behind the resource interface:
    // resource interface (struct) → raw_resources block [0] → raw_items
    // (a struct, despite the plural).
    let raw_items = root
        .nested("resource interface")
        .and_then(|ri| {
            let b = ri.block("raw_resources")?;
            Elem::of(&layout, b, 0)
        })
        .and_then(|rr| rr.nested("raw_items"))
        .ok_or("no resource interface raw items")?;

    let mut defs: Vec<WorldMesh> = Vec::new();
    if let Some(list) = raw_items.block("instanced geometries definitions") {
        for i in 0..list.count as usize {
            let mesh = Elem::of(&layout, list, i)
                .and_then(|def| def.nested("collision info"))
                .and_then(|bsp| triangulate_bsp(&layout, &bsp))
                .map(|(positions, indices, flags)| WorldMesh {
                    positions,
                    indices,
                    flags,
                })
                .unwrap_or(WorldMesh {
                    positions: Vec::new(),
                    indices: Vec::new(),
                    flags: Vec::new(),
                });
            // Empty definitions keep their slot: instances index this list.
            defs.push(mesh);
        }
    }

    // The world shell is either the 32-bit "large collision bsp" or the
    // 16-bit "collision bsp" — both fields always exist, one is empty. The
    // triangulator reads index widths from the layout either way.
    let world = [
        raw_items.block("large collision bsp"),
        raw_items.block("collision bsp"),
    ]
    .into_iter()
    .flatten()
    .find(|b| b.count > 0)
    .and_then(|b| Elem::of(&layout, b, 0))
        .and_then(|bsp| triangulate_bsp(&layout, &bsp))
        .map(|(positions, indices, flags)| WorldMesh {
            positions,
            indices,
            flags,
        });

    // Instances: transform + definition index.
    struct Instance {
        def: u32,
        scale: f32,
        forward: [f32; 3],
        left: [f32; 3],
        up: [f32; 3],
        position: [f32; 3],
    }
    let mut instances: Vec<Instance> = Vec::new();
    if let Some(list) = root.block("instanced geometry instances") {
        if list.count > 0 {
            let e0 = Elem::of(&layout, list, 0).ok_or("empty instance block")?;
            let (scale_off, _) = e0.offset("scale").ok_or("no instance scale")?;
            let (fwd_off, _) = e0.offset("forward").ok_or("no instance forward")?;
            let (left_off, _) = e0.offset("left").ok_or("no instance left")?;
            let (up_off, _) = e0.offset("up").ok_or("no instance up")?;
            let (pos_off, _) = e0.offset("position").ok_or("no instance position")?;
            let (def_off, _) = e0
                .offset("instance definition")
                .ok_or("no instance definition")?;
            let vec3_at = |bytes: &[u8], off: usize| {
                [
                    read_f32(bytes, off),
                    read_f32(bytes, off + 4),
                    read_f32(bytes, off + 8),
                ]
            };
            for i in 0..list.count as usize {
                let Some(bytes) = list.element(i) else {
                    continue;
                };
                let def = read_i16(bytes, def_off);
                if def < 0 || def as usize >= defs.len() {
                    continue;
                }
                instances.push(Instance {
                    def: def as u32,
                    scale: read_f32(bytes, scale_off),
                    forward: vec3_at(bytes, fwd_off),
                    left: vec3_at(bytes, left_off),
                    up: vec3_at(bytes, up_off),
                    position: vec3_at(bytes, pos_off),
                });
            }
        }
    }

    // Pack.
    let header = serde_json::json!({
        "defs": defs
            .iter()
            .map(|d| serde_json::json!({
                "verts": d.positions.len() / 3,
                "tris": d.indices.len() / 3,
            }))
            .collect::<Vec<_>>(),
        "world": world.as_ref().map(|w| serde_json::json!({
            "verts": w.positions.len() / 3,
            "tris": w.indices.len() / 3,
        })),
        "instances": instances.len(),
    });
    let json = serde_json::to_vec(&header).map_err(|e| e.to_string())?;

    let mesh_bytes = |m: &WorldMesh| m.positions.len() * 4 + m.indices.len() * 4 + m.flags.len() * 4;
    let payload_len: usize = defs.iter().map(mesh_bytes).sum::<usize>()
        + world.as_ref().map(mesh_bytes).unwrap_or(0)
        + instances.len() * 56;

    let mut out = Vec::with_capacity(8 + json.len() + payload_len + 4);
    out.extend_from_slice(b"SBSP");
    out.extend_from_slice(&(json.len() as u32).to_le_bytes());
    out.extend_from_slice(&json);
    while out.len() % 4 != 0 {
        out.push(0);
    }

    let mut write_mesh = |out: &mut Vec<u8>, m: &WorldMesh| {
        for v in &m.positions {
            out.extend_from_slice(&v.to_le_bytes());
        }
        for i in &m.indices {
            out.extend_from_slice(&i.to_le_bytes());
        }
        for f in &m.flags {
            out.extend_from_slice(&(*f as u32).to_le_bytes());
        }
    };
    for d in &defs {
        write_mesh(&mut out, d);
    }
    if let Some(w) = &world {
        write_mesh(&mut out, w);
    }
    for inst in &instances {
        out.extend_from_slice(&inst.def.to_le_bytes());
        out.extend_from_slice(&inst.scale.to_le_bytes());
        for v in inst.forward.iter().chain(&inst.left).chain(&inst.up).chain(&inst.position) {
            out.extend_from_slice(&v.to_le_bytes());
        }
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// scenario (scnr)

/// Everything the scenario viewer needs from a scnr tag. Tag references are
/// returned as authored paths; the command layer resolves them to catalog
/// indices, which keeps this module free of the catalog.
#[derive(Serialize, Default)]
pub struct ScenarioLayout {
    /// Structure BSP paths, in block order.
    pub bsps: Vec<String>,
    pub object_names: Vec<String>,
    pub categories: Vec<PlacementCategory>,
    pub trigger_volumes: Vec<TriggerVolume>,
    pub squads: Vec<Squad>,
    pub player_starts: Vec<PlayerStart>,
}

#[derive(Serialize)]
pub struct PlacementCategory {
    /// Block name, which is also the patch-path prefix: an edit to placement
    /// `i`'s position goes to `<block>[i].object data.position`.
    pub block: String,
    /// Catalog group the palette's tags belong to.
    pub group: &'static str,
    /// Palette tag paths, in palette order; empty entries stay as "".
    pub palette: Vec<String>,
    pub placements: Vec<Placement>,
}

#[derive(Serialize)]
pub struct Placement {
    /// Element index within the block — the `[i]` of the patch path.
    pub element: usize,
    /// Palette index ("type"), or -1.
    pub palette: i32,
    /// Object-name index, or -1.
    pub name: i32,
    pub position: [f32; 3],
    /// Euler angles as stored, radians.
    pub rotation: [f32; 3],
    pub scale: f32,
}

#[derive(Serialize)]
pub struct TriggerVolume {
    pub name: String,
    pub position: [f32; 3],
    pub forward: [f32; 3],
    pub up: [f32; 3],
    pub extents: [f32; 3],
}

#[derive(Serialize)]
pub struct Squad {
    pub name: String,
    pub spawn_points: Vec<SpawnPoint>,
}

#[derive(Serialize)]
pub struct SpawnPoint {
    pub name: String,
    pub position: [f32; 3],
    /// Yaw and pitch, radians.
    pub facing: [f32; 2],
}

#[derive(Serialize)]
pub struct PlayerStart {
    pub position: [f32; 3],
    pub facing: [f32; 2],
}

/// The placement blocks worth drawing, with their palette block and the
/// catalog group its tags live in.
const PLACEMENT_BLOCKS: &[(&str, &str, &str)] = &[
    ("scenery", "scenery palette", "scenery"),
    ("bipeds", "biped palette", "biped"),
    ("vehicles", "vehicle palette", "vehicle"),
    ("equipment", "equipment palette", "equipment"),
    ("weapons", "weapon palette", "weapon"),
    ("machines", "machine palette", "device_machine"),
    ("controls", "control palette", "device_control"),
    ("crates", "crate palette", "crate"),
    ("effect scenery", "effect scenery palette", "effect_scenery"),
];

pub fn scenario_layout(file: &[u8]) -> Result<ScenarioLayout, String> {
    let (_tag, layout, block) = root(file)?;
    let root = Elem::of(&layout, &block, 0).ok_or("empty tag")?;
    let mut out = ScenarioLayout::default();

    if let Some(bsps) = root.block("structure bsps") {
        for i in 0..bsps.count as usize {
            let Some(e) = Elem::of(&layout, bsps, i) else {
                continue;
            };
            let path = match e.value("structure bsp") {
                Some(Value::TagRef(content)) => match blam_tag::value::reference(content) {
                    blam_tag::Scalar::Reference { path, .. } => path,
                    _ => String::new(),
                },
                _ => String::new(),
            };
            out.bsps.push(path);
        }
    }

    if let Some(names) = root.block("object names") {
        for i in 0..names.count as usize {
            let name = Elem::of(&layout, names, i)
                .map(|e| e.string_id("name"))
                .unwrap_or_default();
            out.object_names.push(name);
        }
    }

    for &(block_name, palette_name, group) in PLACEMENT_BLOCKS {
        let mut category = PlacementCategory {
            block: block_name.to_string(),
            group,
            palette: Vec::new(),
            placements: Vec::new(),
        };
        if let Some(palette) = root.block(palette_name) {
            for i in 0..palette.count as usize {
                let path = Elem::of(&layout, palette, i)
                    .and_then(|e| match e.value("name") {
                        Some(Value::TagRef(content)) => {
                            match blam_tag::value::reference(content) {
                                blam_tag::Scalar::Reference { path, .. } => Some(path),
                                _ => None,
                            }
                        }
                        _ => None,
                    })
                    .unwrap_or_default();
                category.palette.push(path);
            }
        }
        if let Some(list) = root.block(block_name) {
            for i in 0..list.count as usize {
                let Some(e) = Elem::of(&layout, list, i) else {
                    continue;
                };
                let Some(data) = e.nested("object data") else {
                    continue;
                };
                category.placements.push(Placement {
                    element: i,
                    palette: e.i16("type") as i32,
                    name: e.i16("name") as i32,
                    position: data.vec3("position"),
                    rotation: data.vec3("rotation"),
                    scale: data.f32("scale", 0),
                });
            }
        }
        if !category.palette.is_empty() || !category.placements.is_empty() {
            out.categories.push(category);
        }
    }

    if let Some(volumes) = root.block("trigger volumes") {
        for i in 0..volumes.count as usize {
            let Some(e) = Elem::of(&layout, volumes, i) else {
                continue;
            };
            out.trigger_volumes.push(TriggerVolume {
                name: e.string_id("name"),
                position: e.vec3("position"),
                forward: e.vec3("forward"),
                up: e.vec3("up"),
                extents: e.vec3("extents"),
            });
        }
    }

    if let Some(squads) = root.block("squads") {
        for i in 0..squads.count as usize {
            let Some(squad) = Elem::of(&layout, squads, i) else {
                continue;
            };
            let mut points = Vec::new();
            if let Some(list) = squad.block("spawn points") {
                for j in 0..list.count as usize {
                    let Some(p) = Elem::of(&layout, list, j) else {
                        continue;
                    };
                    points.push(SpawnPoint {
                        name: p.string_id("name"),
                        position: p.vec3("position"),
                        facing: [p.f32("facing (yaw, pitch)", 0), p.f32("facing (yaw, pitch)", 1)],
                    });
                }
            }
            out.squads.push(Squad {
                name: squad.string_id("name"),
                spawn_points: points,
            });
        }
    }

    if let Some(starts) = root.block("player starting locations") {
        for i in 0..starts.count as usize {
            let Some(e) = Elem::of(&layout, starts, i) else {
                continue;
            };
            out.player_starts.push(PlayerStart {
                position: e.vec3("position"),
                facing: [e.f32("facing", 0), e.f32("facing", 1)],
            });
        }
    }

    Ok(out)
}

/// The `model` (hlmt) reference of an object-definition tag — how a palette
/// entry becomes drawable geometry.
pub fn object_model_ref(file: &[u8]) -> Option<String> {
    let (_tag, layout, block) = root(file).ok()?;
    let root = Elem::of(&layout, &block, 0)?;
    match root.value("model") {
        Some(Value::TagRef(content)) => match blam_tag::value::reference(content) {
            blam_tag::Scalar::Reference { path, .. } if !path.is_empty() => Some(path),
            _ => None,
        },
        _ => None,
    }
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
