//! Put a collision BSP into a shipped `sbsp` payload.
//!
//! The donor keeps everything the engine might insist on — seam tables, kd
//! hierarchy, instance groups, Havok mopps — and only the world shell's nine
//! tables (plus the root-level per-leaf and per-edge companions, which the
//! shipped data keeps 1:1 with the shell) are replaced. What the engine
//! *requires* is settled by the ablation probes in
//! `docs/ce_map_conversion.md`; [`Options`] switches each companion so a probe
//! is a flag, not a fork.

use blam_tag::blockedit::{element_with_wrapper, find_block, replace_nested, NestedReplace};
use blam_tag::patch;

use crate::ce::Bounds;
use crate::pack16::Packed;
use crate::Error;

pub const SHELL: &str = "resource interface.raw_resources[0].raw_items.collision bsp[0]";

/// Which companion tables to rewrite alongside the shell.
#[derive(Debug, Clone)]
pub struct Options {
    /// Keep the donor's `bsp3d supernodes` (they index the donor's node
    /// forest, which no longer exists) or write one pass-through supernode
    /// whose every cell is the new root node 0.
    pub supernodes: Supernodes,
    /// Root `leaves` (one cluster byte per collision leaf) follow the shell.
    pub root_leaves: bool,
    /// Root `edge to seam edge` (one `(-1, -1)` per edge) follows the shell.
    pub edge_to_seam: bool,
    /// Drop `structure_physics.mopp code block` (the Havok mopp of the donor
    /// shell, which describes geometry that is no longer there).
    pub drop_mopp: bool,
    /// Set world bounds, the cluster's bounds and the mopp bounds.
    pub bounds: Option<Bounds>,
    /// Drop the render-side `large structure surfaces` and
    /// `structure surface to triangle mapping` (per-surface, donor-sized).
    pub drop_structure_surfaces: bool,
    /// A shipped payload whose world shell has exactly one kd supernode
    /// (`BSP_03_1_Chasm_old`): its four root companion tables — `super aabbs`,
    /// `super node parent mappings`, `super node recursable_masks`,
    /// `structure_super_node_traversal_geometry_block` — are copied in, with
    /// every aabb widened to the new bounds, so the donor's per-supernode
    /// tables (2,009 of them on `BSP_01_1_Start`) do not describe a forest
    /// that no longer exists.
    pub kd_template: Option<Vec<u8>>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Supernodes {
    Keep,
    None,
    /// One 128-byte supernode: 15 planes at `plane`, every child cell = root.
    PassThrough,
}

impl Default for Options {
    fn default() -> Self {
        Options {
            supernodes: Supernodes::PassThrough,
            root_leaves: true,
            edge_to_seam: true,
            drop_mopp: false,
            bounds: None,
            drop_structure_surfaces: false,
            kd_template: None,
        }
    }
}

/// A pass-through kd supernode built on a shipped one: cells 0..14 all name
/// bsp3d node 0 (`0x4000_0000 | 0`), so whichever cell a query lands in, the
/// whole tree is searched. The split planes, `plane dimensions` word and the
/// opaque slot 15 (never a child in any shipped supernode — it carries a
/// large packed value) are kept from `template`, which is one 128-byte
/// element.
pub fn passthrough_from(template: &[u8]) -> Vec<u8> {
    let mut b = template[..128].to_vec();
    for cell in 0..15 {
        let at = 64 + cell * 4;
        b[at..at + 4].copy_from_slice(&0x4000_0000u32.to_le_bytes());
    }
    b
}

/// A pass-through kd supernode from nothing: the engine descends it to find
/// which bsp3d subtree to search; with every cell naming node 0 the whole
/// tree is one subtree. Splits sit at the centre of the bounds so any point
/// resolves.
pub fn passthrough_supernode(bounds: Bounds) -> Vec<u8> {
    let mut b = Vec::with_capacity(128);
    let mid = [
        (bounds.min[0] + bounds.max[0]) * 0.5,
        (bounds.min[1] + bounds.max[1]) * 0.5,
        (bounds.min[2] + bounds.max[2]) * 0.5,
    ];
    // 15 split planes: a 4-deep binary tree cycling x, y, z, x.
    let axes = [0usize, 1, 1, 2, 2, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0];
    let mut dims: u32 = 0;
    for (i, axis) in axes.iter().enumerate() {
        b.extend_from_slice(&mid[*axis].to_le_bytes());
        dims |= (*axis as u32 & 3) << (30 - 2 * i as u32);
    }
    b.extend_from_slice(&dims.to_le_bytes());
    for _ in 0..16 {
        b.extend_from_slice(&0x4000_0000u32.to_le_bytes());
    }
    b
}

/// The rewrites that put `packed` into `donor`, as a list the caller can
/// inspect before applying.
/// The eight collision tables, as replacements under `base` — the world shell
/// (`SHELL`) or an instanced-geometry definition's `collision info`, which
/// carry the same block shapes.
pub fn tables_at(base: &str, packed: &Packed) -> Vec<NestedReplace> {
    let table = |name: &str, bytes: &[u8], size: usize| NestedReplace {
        path: format!("{base}.{name}"),
        count: (bytes.len() / size) as u32,
        elements: bytes.to_vec(),
        wrappers: None,
    };
    vec![
        table("bsp3d nodes", &packed.bsp3d_nodes, 8),
        table("planes", &packed.planes, 16),
        table("leaves", &packed.leaves, 8),
        table("bsp2d references", &packed.bsp2d_references, 4),
        table("bsp2d nodes", &packed.bsp2d_nodes, 16),
        table("surfaces", &packed.surfaces, 14),
        table("edges", &packed.edges, 12),
        table("vertices", &packed.vertices, 16),
    ]
}

/// The collision-info path of one instanced-geometry definition.
pub fn definition(index: usize) -> String {
    format!(
        "resource interface.raw_resources[0].raw_items.instanced geometries definitions[{index}].collision info"
    )
}

pub fn plan(donor: &[u8], packed: &Packed, opts: &Options) -> Result<Vec<NestedReplace>, Error> {
    let tag = blam_tag::TagFile::parse(donor, None).map_err(|e| Error::Other(e.to_string()))?;
    let layout = tag.layout().map_err(|e| Error::Other(e.to_string()))?;
    let root = tag
        .read_data(&layout)
        .map_err(|e| Error::Other(e.to_string()))?;

    let mut out = tables_at(SHELL, packed);
    let table = |name: &str, bytes: &[u8], size: usize| NestedReplace {
        path: format!("{SHELL}.{name}"),
        count: (bytes.len() / size) as u32,
        elements: bytes.to_vec(),
        wrappers: None,
    };

    let leaf_count = (packed.leaves.len() / 8) as u32;
    let edge_count = (packed.edges.len() / 12) as u32;

    match opts.supernodes {
        Supernodes::Keep => {}
        Supernodes::None => out.push(table("bsp3d supernodes", &[], 128)),
        Supernodes::PassThrough => {
            let path = format!("{SHELL}.bsp3d supernodes");
            let donor_super = find_block(&layout, donor, &root, &path)?;
            let bytes = match donor_super.block.element(0) {
                Some(e) => passthrough_from(e),
                None => {
                    let bounds = opts.bounds.ok_or_else(|| {
                        Error::Other("pass-through supernode needs bounds".into())
                    })?;
                    passthrough_supernode(bounds)
                }
            };
            out.push(table("bsp3d supernodes", &bytes, 128));
        }
    }
    if let Some(template) = &opts.kd_template {
        let bounds = opts
            .bounds
            .ok_or_else(|| Error::Other("kd template needs bounds".into()))?;
        // 15 aabbs, every one the whole world: no cell can cull the shell.
        let t =
            blam_tag::TagFile::parse(template, None).map_err(|e| Error::Other(e.to_string()))?;
        let tl = t.layout().map_err(|e| Error::Other(e.to_string()))?;
        let tr = t.read_data(&tl).map_err(|e| Error::Other(e.to_string()))?;
        let aabbs = find_block(&tl, template, &tr, "super aabbs")?;
        let mut a = Vec::with_capacity(aabbs.block.count as usize * 24);
        for _ in 0..aabbs.block.count {
            for axis in 0..3 {
                a.extend_from_slice(&bounds.min[axis].to_le_bytes());
                a.extend_from_slice(&bounds.max[axis].to_le_bytes());
            }
        }
        out.push(NestedReplace {
            path: "super aabbs".into(),
            count: aabbs.block.count,
            elements: a,
            wrappers: None,
        });
        for name in [
            "super node parent mappings",
            "super node recursable_masks",
            "structure_super_node_traversal_geometry_block",
        ] {
            let found = find_block(&tl, template, &tr, name)?;
            let mut wrappers = Vec::new();
            for i in 0..found.block.count as usize {
                let (_, w) = element_with_wrapper(template, name, i)?;
                wrappers.push(w);
            }
            out.push(NestedReplace {
                path: name.into(),
                count: found.block.count,
                elements: found.block.elements.to_vec(),
                wrappers: if found.block.flags == 0 {
                    Some(wrappers)
                } else {
                    None
                },
            });
        }
    }
    if opts.root_leaves {
        out.push(NestedReplace {
            path: "leaves".into(),
            count: leaf_count,
            elements: vec![0u8; leaf_count as usize],
            wrappers: None,
        });
    }
    if opts.edge_to_seam {
        let mut e = Vec::with_capacity(edge_count as usize * 4);
        for _ in 0..edge_count {
            e.extend_from_slice(&[0xff, 0xff, 0xff, 0xff]);
        }
        out.push(NestedReplace {
            path: "edge to seam edge".into(),
            count: edge_count,
            elements: e,
            wrappers: None,
        });
    }
    if opts.drop_mopp {
        let found = find_block(&layout, donor, &root, "structure_physics.mopp code block")?;
        let _ = found;
        out.push(NestedReplace {
            path: "structure_physics.mopp code block".into(),
            count: 0,
            elements: Vec::new(),
            wrappers: None,
        });
    }
    if opts.drop_structure_surfaces {
        out.push(NestedReplace {
            path: "large structure surfaces".into(),
            count: 0,
            elements: Vec::new(),
            wrappers: None,
        });
        out.push(NestedReplace {
            path: "structure surface to triangle mapping".into(),
            count: 0,
            elements: Vec::new(),
            wrappers: None,
        });
    }
    Ok(out)
}

/// Apply [`plan`] and then the scalar bounds edits, returning the new payload.
pub fn apply(donor: &[u8], packed: &Packed, opts: &Options) -> Result<Vec<u8>, Error> {
    let replacements = plan(donor, packed, opts)?;
    let mut file = replace_nested(donor, &replacements)?;
    if let Some(b) = opts.bounds {
        let pairs = [
            ("world bounds x", 0usize),
            ("world bounds y", 1),
            ("world bounds z", 2),
            ("clusters[0].bounds x", 0),
            ("clusters[0].bounds y", 1),
            ("clusters[0].bounds z", 2),
        ];
        for (path, axis) in pairs {
            file = set_scalar(&file, path, &format!("({}, {})", b.min[axis], b.max[axis]))?;
        }
        file = set_scalar(
            &file,
            "structure_physics.mopp bounds min",
            &format!("({}, {}, {})", b.min[0], b.min[1], b.min[2]),
        )?;
        file = set_scalar(
            &file,
            "structure_physics.mopp bounds max",
            &format!("({}, {}, {})", b.max[0], b.max[1], b.max[2]),
        )?;
    }
    Ok(file)
}

/// `mjolnir set` for one fixed-width field, by text value.
pub fn set_scalar(file: &[u8], path: &str, value: &str) -> Result<Vec<u8>, Error> {
    let tag = blam_tag::TagFile::parse(file, None).map_err(|e| Error::Other(e.to_string()))?;
    let layout = tag.layout().map_err(|e| Error::Other(e.to_string()))?;
    let root = tag
        .read_data(&layout)
        .map_err(|e| Error::Other(e.to_string()))?;
    let target = patch::resolve(&layout, file, &root, path)?;
    if target.section.is_some() {
        return Err(Error::Other(format!("{path}: not a fixed-width field")));
    }
    let parsed = blam_tag::value::parse(&layout, &target.field, value)
        .map_err(|e| Error::Other(format!("{path}: {e}")))?;
    let (out, _) = patch::set(&layout, file, &root, path, &parsed)?;
    Ok(out)
}

/// Clone one donor element (bytes + wrapper) for tables whose elements carry
/// tag references, such as `collision materials`.
pub fn donor_element(file: &[u8], path: &str, index: usize) -> Result<(Vec<u8>, Vec<u8>), Error> {
    Ok(element_with_wrapper(file, path, index)?)
}
