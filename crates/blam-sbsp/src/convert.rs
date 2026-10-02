//! One step from a staged CE collision BSP to a canvas `sbsp` payload the
//! simulation walks on.
//!
//! This is the recipe that made the pawn stand on Blood Gulch (see
//! `docs/ce_terrain_collision.md`, "It stands"), with the numbers that were
//! typed by hand derived from the map instead:
//!
//! 1. [`transplant_definition`] — the terrain goes into one instanced-geometry
//!    definition behind an instance that keeps its place, with a pass-through
//!    kd supernode.
//! 2. [`set_group_sphere`] — the host instance's group sphere grows to the
//!    terrain's bounding sphere.
//! 3. [`compile_definition_mopps`] — the definition's Havok MOPP is rebuilt
//!    over the surfaces that are actually there.
//! 4. [`compile_group_mopps`] — the host group's tree and the cluster tree
//!    above it are rebuilt, so the broadphase reaches the new extent.
//! 5. [`park_instances`] — every other canvas instance whose footprint
//!    overlaps the terrain drops to `park_z`. Blocks the engine dereferences
//!    are never emptied (an empty block is an unrelocated reference and a
//!    crash); moving an instance is safe.
//!
//! [`convert`] runs all five. Each step is public so the probe examples keep
//! their one-step-per-launch shape.

use blam_tag::blockedit::{find_block, replace_nested, NestedReplace};

use crate::ce::{Bounds, Collision};
use crate::transplant::{self, passthrough_from, set_scalar};
use crate::unpack16::{self, Tables};
use crate::{mopp, pack16, split, Error};

pub const INSTANCES: &str = "instanced geometry instances";
pub const GROUP_MOPPS: &str = "instance group to instance mopps";
pub const GROUP_SPHERES: &str = "instance group to instance spheres";
pub const CLUSTER_MOPPS: &str = "cluster to instance group mopps";

/// The definition, instance and group that carry the terrain.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Host {
    pub definition: usize,
    pub instance: usize,
    pub group: usize,
}

impl Host {
    /// B40 `BSP_01_1_Start`: definition 159 behind instance 763 in group 58.
    /// The only host proven in game (2026-09-09).
    pub const B40_START: Host = Host {
        definition: 159,
        instance: 763,
        group: 58,
    };
}

/// Where the terrain lands in the canvas: B40's own start, which sits inside
/// BSP 8's world box. The terrain's footprint centre goes here in x and y, and
/// its lowest point to `z`.
pub const B40_START_ANCHOR: [f32; 3] = [33.5, 33.5, 43.65];

/// Which other canvas instances to move out of the way.
#[derive(Debug, Clone)]
pub enum Park {
    None,
    /// These instances, by index.
    Listed(Vec<usize>),
    /// Every instance whose stored box overlaps the terrain's footprint in x
    /// and y (at any height), grown by `margin` world units.
    Footprint {
        margin: f32,
    },
}

#[derive(Debug, Clone)]
pub struct Options {
    pub host: Host,
    /// Added to every CE coordinate: CE world → canvas world.
    pub delta: [f32; 3],
    pub park: Park,
    /// Where parked instances go.
    pub park_z: f32,
    /// Also put the terrain into the world shell, so the simulation's
    /// inside-the-world test follows the CE map (see [`transplant_shell`]).
    /// `None` leaves the canvas shell, which only works where the terrain
    /// happens to overlap the canvas's own playable space.
    pub shell: Option<ShellOptions>,
    /// The canvas BSP's index in its scenario: what the collision kd
    /// hierarchy's headers name.
    pub bsp_index: u8,
    /// Keep each surface's material index (the caller has remapped them onto
    /// the `collision materials` block it writes). Otherwise every surface
    /// lands on the donor's material 0, as a canvas host's must.
    pub keep_materials: bool,
}

/// The world shell rewrite: a pass-through kd supernode, with the root kd
/// companion tables copied from a shipped shell that has exactly one
/// supernode (`BSP_03_1_Chasm_old`).
#[derive(Debug, Clone)]
pub struct ShellOptions {
    pub kd_template: Vec<u8>,
}

impl Options {
    /// The B40 start host, the terrain centred on [`B40_START_ANCHOR`], and
    /// everything under its footprint parked.
    pub fn for_terrain(ce_bounds: Bounds) -> Options {
        Options {
            host: Host::B40_START,
            delta: delta_to_anchor(ce_bounds, B40_START_ANCHOR),
            park: Park::Footprint { margin: 2.0 },
            park_z: -500.0,
            shell: None,
            bsp_index: 8,
            keep_materials: false,
        }
    }
}

/// The translation that puts the centre of `b`'s footprint at `anchor`'s x
/// and y, and `b`'s lowest point at `anchor`'s z.
pub fn delta_to_anchor(b: Bounds, anchor: [f32; 3]) -> [f32; 3] {
    [
        anchor[0] - (b.min[0] + b.max[0]) * 0.5,
        anchor[1] - (b.min[1] + b.max[1]) * 0.5,
        anchor[2] - b.min[2],
    ]
}

#[derive(Debug, Clone)]
pub struct Report {
    /// The terrain's bounds in canvas world space, after the move.
    pub bounds: Bounds,
    pub surfaces: usize,
    pub vertices: usize,
    /// Polygons past four vertices that were fan-split, and the 2D references
    /// that were rewired to follow them.
    pub split: usize,
    pub rewired: usize,
    pub sphere_center: [f32; 3],
    pub sphere_radius: f32,
    pub definition_code: usize,
    pub group_code: usize,
    pub cluster_code: usize,
    pub parked: Vec<usize>,
    /// Collision kd hierarchy root nodes the host was added to.
    pub kd_roots: Vec<usize>,
    pub structure: StructureMopp,
    /// Scenery collision behind instances of its own ([`convert_own`]).
    pub scenery: Scenery,
}

/// Run the whole recipe. `collision` is the CE BSP in CE world coordinates.
pub fn convert(
    donor: &[u8],
    collision: Collision,
    opts: &Options,
) -> Result<(Vec<u8>, Report), Error> {
    check_host(donor, opts.host)?;
    let shelled;
    let donor = match &opts.shell {
        Some(shell) => {
            shelled = transplant_shell(
                donor,
                collision.clone(),
                opts.delta,
                shell,
                opts.keep_materials,
            )?;
            &shelled[..]
        }
        None => donor,
    };
    let (file, t) =
        transplant_definition(donor, collision, opts.host, opts.delta, opts.keep_materials)?;
    let (center, radius) = bounding_sphere(t.bounds);
    let file = set_group_sphere(&file, opts.host.group, center, radius)?;
    let (file, def_codes) = compile_definition_mopps(&file, &[opts.host.definition])?;
    let (file, group) = compile_group_mopps(&file, &[opts.host.group], true)?;
    let mut parked = match &opts.park {
        Park::None => Vec::new(),
        Park::Listed(ids) => ids.clone(),
        Park::Footprint { margin } => {
            footprint_overlaps(&file, t.bounds, *margin, opts.host.instance)?
        }
    };
    // Every other instance of the host definition now carries the terrain at
    // its own frame (B40's definition 159 is also instance 764's): park them
    // too, or the map appears twice.
    if !matches!(opts.park, Park::None) {
        for i in instances_of(&file, opts.host.definition)? {
            if i != opts.host.instance && !parked.contains(&i) {
                parked.push(i);
            }
        }
    }
    let file = park_instances(&file, &parked, opts.park_z)?;
    // With the canvas's shell kept, its collision kd hierarchy decides which
    // instances a query tests, and lists the host only around its old box.
    // The collision kd hierarchy decides which instances a Blam query tests;
    // a canvas lists the host only around its old box, and a donor BSP names
    // it under the donor's own BSP index.
    let (file, kd_roots) = add_to_kd_roots(&file, opts.host.instance, opts.bsp_index)?;
    // What Havok movement actually stands on: the BSP's one static body.
    let (file, structure) = rebuild_structure_mopp(&file, &[opts.host.instance], &parked)?;
    check_walks(&file)?;
    Ok((
        file,
        Report {
            bounds: t.bounds,
            surfaces: t.surfaces,
            vertices: t.vertices,
            split: t.split,
            rewired: t.rewired,
            sphere_center: center,
            sphere_radius: radius,
            definition_code: def_codes.first().copied().unwrap_or(0),
            group_code: group.groups.first().copied().unwrap_or(0),
            cluster_code: group.cluster.unwrap_or(0),
            parked,
            kd_roots,
            structure,
            scenery: Scenery::default(),
        },
    ))
}

/// Put the terrain, moved by `delta`, into the world shell
/// (`raw_items.collision bsp[0]`).
///
/// The shell is not what the pawn walks on — a shipped shell is an
/// inside/outside classifier (B40's start BSP: 19 surfaces over 17,567
/// leaves), and `structure_physics` carries its own Havok mesh — but it is
/// what `object_get_bsp` and the rest of the simulation's "which BSP is this
/// point in" answer from. With the canvas's shell left in place, a terrain
/// placed anywhere the canvas calls solid or void puts every object outside
/// the world (`object_get_bsp` = -1): nothing is simulated, the player cannot
/// be killed or pushed, and pickups never settle. Hang 'Em High on B40,
/// 2026-09-30. The walkable collision stays in the definition.
pub fn transplant_shell(
    donor: &[u8],
    mut collision: Collision,
    delta: [f32; 3],
    shell: &ShellOptions,
    keep_materials: bool,
) -> Result<Vec<u8>, Error> {
    if delta != [0.0; 3] {
        pack16::translate(&mut collision, delta);
    }
    split::fan_split(&mut collision, 4);
    collision.fits_16bit()?;
    let bounds = collision
        .bounds()
        .ok_or_else(|| Error::Staging("the collision BSP has no vertices".into()))?;
    let packed = pack16::pack(&collision, &material_map(keep_materials))?;
    let opts = transplant::Options {
        supernodes: transplant::Supernodes::PassThrough,
        bounds: Some(bounds),
        kd_template: Some(shell.kd_template.clone()),
        ..Default::default()
    };
    let file = transplant::apply(donor, &packed, &opts)?;
    check_walks(&file)?;
    Ok(file)
}

/// Surface material indices as packed: kept (a surface with none, -1, takes
/// material 0), or all on material 0.
fn material_map(keep: bool) -> impl Fn(i16) -> i16 {
    move |m: i16| if keep { m.max(0) } else { 0 }
}

/// The smallest sphere around a box's corners.
pub fn bounding_sphere(b: Bounds) -> ([f32; 3], f32) {
    let c = [
        (b.min[0] + b.max[0]) / 2.0,
        (b.min[1] + b.max[1]) / 2.0,
        (b.min[2] + b.max[2]) / 2.0,
    ];
    let r =
        ((b.max[0] - c[0]).powi(2) + (b.max[1] - c[1]).powi(2) + (b.max[2] - c[2]).powi(2)).sqrt();
    (c, r)
}

fn f32_at(b: &[u8], o: usize) -> f32 {
    f32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

fn other(e: impl std::fmt::Display) -> Error {
    Error::Other(e.to_string())
}

/// Parse `file` and hand its layout and root to `f`.
fn with_tag<'a, T>(
    file: &'a [u8],
    f: impl FnOnce(&blam_tag::Layout<'a>, &blam_tag::data::Block<'a>) -> Result<T, Error>,
) -> Result<T, Error> {
    let tag = blam_tag::TagFile::parse(file, None).map_err(other)?;
    let layout = tag.layout().map_err(other)?;
    let root = tag.read_data(&layout).map_err(other)?;
    f(&layout, &root)
}

/// It must still walk exactly, or the game will not read it.
pub fn check_walks(file: &[u8]) -> Result<(), Error> {
    let tag = blam_tag::TagFile::parse(file, None).map_err(other)?;
    let l = tag.layout().map_err(other)?;
    let block = tag.read_data(&l).map_err(other)?;
    let payload = tag
        .data()
        .ok_or_else(|| Error::Other("the tag has no data section".into()))?;
    if block.consumed != payload.size as usize {
        return Err(Error::Other(format!(
            "the rewritten payload does not walk exactly ({} of {} bytes)",
            block.consumed, payload.size
        )));
    }
    Ok(())
}

/// An instance's position and its stored world box `(min, max)`.
#[derive(Debug, Clone, Copy)]
pub struct InstanceBox {
    pub position: [f32; 3],
    pub min: [f32; 3],
    pub max: [f32; 3],
}

/// An instance's world-space box, as the tag stores it at offsets 76..100.
fn instance_box(elem: &[u8]) -> InstanceBox {
    InstanceBox {
        position: [f32_at(elem, 40), f32_at(elem, 44), f32_at(elem, 48)],
        min: [f32_at(elem, 76), f32_at(elem, 84), f32_at(elem, 92)],
        max: [f32_at(elem, 80), f32_at(elem, 88), f32_at(elem, 96)],
    }
}

/// Every instance's box, in index order.
pub fn instance_boxes(file: &[u8]) -> Result<Vec<InstanceBox>, Error> {
    with_tag(file, |layout, root| {
        let inst = find_block(layout, file, root, INSTANCES)?;
        Ok((0..inst.block.count as usize)
            .filter_map(|i| inst.block.element(i).map(instance_box))
            .collect())
    })
}

/// The host has to have what the recipe reuses: a definition with a supernode
/// to build the pass-through from and a mopp element to patch, an instance
/// with a physics block (one without is never tested), and that instance a
/// member of the group.
pub fn check_host(file: &[u8], host: Host) -> Result<(), Error> {
    with_tag(file, |layout, root| {
        let count = |path: &str| -> usize {
            find_block(layout, file, root, path)
                .map(|f| f.block.count as usize)
                .unwrap_or(0)
        };
        let base = transplant::definition(host.definition);
        let def = base.trim_end_matches(".collision info");
        let problems: Vec<String> = [
            (
                count(&format!("{base}.bsp3d supernodes")) > 0,
                "its definition has no bsp3d supernode",
            ),
            (
                count(&format!("{def}.mopp codes")) > 0,
                "its definition has no mopp",
            ),
            (
                count(&format!("{INSTANCES}[{}].physics", host.instance)) > 0,
                "its instance has no physics block",
            ),
        ]
        .into_iter()
        .filter(|(ok, _)| !ok)
        .map(|(_, why)| why.to_string())
        .collect();
        if !problems.is_empty() {
            return Err(Error::Other(format!(
                "host {host:?}: {}",
                problems.join("; ")
            )));
        }
        let members = find_block(
            layout,
            file,
            root,
            &format!("{GROUP_SPHERES}[{}].instance indices", host.group),
        )?;
        let member = (0..members.block.count as usize).any(|k| {
            let b = members.block.element(k).unwrap();
            u16::from_le_bytes([b[0], b[1]]) as usize == host.instance
        });
        if !member {
            return Err(Error::Other(format!(
                "host {host:?}: instance {} is not a member of group {}",
                host.instance, host.group
            )));
        }
        Ok(())
    })
}

#[derive(Debug, Clone, Copy)]
pub struct Transplanted {
    /// World-space bounds of the terrain.
    pub bounds: Bounds,
    pub surfaces: usize,
    pub vertices: usize,
    pub split: usize,
    pub rewired: usize,
}

/// Put `collision` (CE world coordinates) into the host definition, moved by
/// `delta`, behind the host instance. The instance keeps its position (so it
/// stays inside the volumes the broadphase walks) and is reset to an identity
/// frame; its position is pre-subtracted from the geometry.
pub fn transplant_definition(
    donor: &[u8],
    mut collision: Collision,
    host: Host,
    delta: [f32; 3],
    keep_materials: bool,
) -> Result<(Vec<u8>, Transplanted), Error> {
    let p = format!("{INSTANCES}[{}]", host.instance);
    let inst_pos = with_tag(donor, |layout, root| {
        let inst = find_block(layout, donor, root, INSTANCES)?;
        let e = inst
            .block
            .element(host.instance)
            .ok_or_else(|| Error::Other(format!("no instance {}", host.instance)))?;
        Ok(instance_box(e).position)
    })?;

    let local_delta = [
        delta[0] - inst_pos[0],
        delta[1] - inst_pos[1],
        delta[2] - inst_pos[2],
    ];
    if local_delta != [0.0; 3] {
        pack16::translate(&mut collision, local_delta);
    }
    // Shipped definitions are triangles and quads only; larger CE polygons
    // took the simulation down once lookups reached them.
    let (split, rewired) = split::fan_split(&mut collision, 4);
    collision.fits_16bit()?;
    let local = collision
        .bounds()
        .ok_or_else(|| Error::Staging("the collision BSP has no vertices".into()))?;
    let bounds = Bounds {
        min: [
            local.min[0] + inst_pos[0],
            local.min[1] + inst_pos[1],
            local.min[2] + inst_pos[2],
        ],
        max: [
            local.max[0] + inst_pos[0],
            local.max[1] + inst_pos[1],
            local.max[2] + inst_pos[2],
        ],
    };

    let packed = pack16::pack(&collision, &material_map(keep_materials))?;
    let base = transplant::definition(host.definition);
    let mut edits = transplant::tables_at(&base, &packed);

    // One pass-through supernode built on the definition's own first one:
    // every cell names the root, so the whole tree is searched. Zero
    // supernodes leaves the kd walk nothing to traverse (no collision at all).
    let supernode = transplant::donor_element(donor, &format!("{base}.bsp3d supernodes"), 0)
        .map(|(e, _)| passthrough_from(&e))
        .map_err(|e| {
            Error::Other(format!(
                "definition {} has no supernode: {e}",
                host.definition
            ))
        })?;
    edits.push(NestedReplace {
        path: format!("{base}.bsp3d supernodes"),
        count: 1,
        elements: supernode,
        wrappers: None,
    });
    let mut file = replace_nested(donor, &edits)?;

    let (centre, radius) = bounding_sphere(bounds);
    let v3 = |v: [f32; 3]| format!("({}, {}, {})", v[0], v[1], v[2]);
    let sets: Vec<(String, String)> = vec![
        (format!("{p}.scale"), "1.0".into()),
        (format!("{p}.forward"), "(1.0, 0.0, 0.0)".into()),
        (format!("{p}.left"), "(0.0, 1.0, 0.0)".into()),
        (format!("{p}.up"), "(0.0, 0.0, 1.0)".into()),
        (format!("{p}.position"), v3(inst_pos)),
        (format!("{p}.bounds x0"), format!("{}", bounds.min[0])),
        (format!("{p}.bounds x1"), format!("{}", bounds.max[0])),
        (format!("{p}.bounds y0"), format!("{}", bounds.min[1])),
        (format!("{p}.bounds y1"), format!("{}", bounds.max[1])),
        (format!("{p}.bounds z0"), format!("{}", bounds.min[2])),
        (format!("{p}.bounds z1"), format!("{}", bounds.max[2])),
        (format!("{p}.world bounding sphere center"), v3(centre)),
        (
            format!("{p}.world bounding sphere radius"),
            format!("{radius}"),
        ),
        // The Havok shape's own box is the definition's LOCAL vertex bounds
        // scaled by the instance scale, with no rotation or position applied
        // (shipped instances 763, 105 and 545 match to the last digit). A box
        // in world space, or one that no longer matched the tables, stalled
        // the load while the shape was built.
        (
            format!("{p}.physics[0].collision geometry shape[0].center"),
            v3([
                (local.min[0] + local.max[0]) / 2.0,
                (local.min[1] + local.max[1]) / 2.0,
                (local.min[2] + local.max[2]) / 2.0,
            ]),
        ),
        (
            format!("{p}.physics[0].collision geometry shape[0].half extent"),
            v3([
                (local.max[0] - local.min[0]) / 2.0,
                (local.max[1] - local.min[1]) / 2.0,
                (local.max[2] - local.min[2]) / 2.0,
            ]),
        ),
        (
            format!("{p}.physics[0].collision geometry shape[0].scale"),
            "1.0".into(),
        ),
        // The Havok mopp shape keeps its own copy of the instance scale. Left
        // at a shipped instance's (definition 159's instances ship at
        // 0.328084), Havok builds the terrain at a third of its size around
        // the instance origin while Blam's own tests use scale 1: everything
        // that moves through Havok falls through the real terrain.
        (
            format!("{p}.physics[0].mopp bv tree shape.mopp scale"),
            "1.0".into(),
        ),
    ];
    for (path, value) in &sets {
        file = set_scalar(&file, path, value)?;
    }
    check_walks(&file)?;
    Ok((
        file,
        Transplanted {
            bounds,
            surfaces: collision.surfaces.len(),
            vertices: collision.vertices.len(),
            split,
            rewired,
        },
    ))
}

/// Set one instance group's broadphase sphere.
pub fn set_group_sphere(
    file: &[u8],
    group: usize,
    center: [f32; 3],
    radius: f32,
) -> Result<Vec<u8>, Error> {
    let p = format!("{GROUP_SPHERES}[{group}]");
    let file = set_scalar(
        file,
        &format!("{p}.center"),
        &format!("({}, {}, {})", center[0], center[1], center[2]),
    )?;
    set_scalar(&file, &format!("{p}.radius"), &format!("{radius}"))
}

/// Recompile each definition's Havok MOPP from its own collision surfaces,
/// and rewrite the element's `code info` so the quantisation matches. Returns
/// the code length per definition (0 when a definition has no surfaces and
/// was skipped).
pub fn compile_definition_mopps(
    file: &[u8],
    defs: &[usize],
) -> Result<(Vec<u8>, Vec<usize>), Error> {
    let mut edits = Vec::new();
    let mut lens = Vec::new();
    with_tag(file, |layout, root| {
        for &d in defs {
            let coll = transplant::definition(d);
            let base = coll.trim_end_matches(".collision info").to_string();
            let get = |name: &str| -> &[u8] {
                find_block(layout, file, root, &format!("{coll}.{name}"))
                    .map(|f| f.block.elements)
                    .unwrap_or(&[])
            };
            let t = Tables {
                bsp3d_nodes: get("bsp3d nodes"),
                planes: get("planes"),
                leaves: get("leaves"),
                bsp2d_references: get("bsp2d references"),
                bsp2d_nodes: get("bsp2d nodes"),
                surfaces: get("surfaces"),
                edges: get("edges"),
                vertices: get("vertices"),
            };
            let (c, _) = unpack16::unpack(&t)?;
            if c.surfaces.is_empty() {
                lens.push(0);
                continue;
            }
            let polys: Vec<Vec<[f32; 3]>> = (0..c.surfaces.len())
                .map(|s| unpack16::polygon(&c, s))
                .collect();
            let mut lo = [f32::MAX; 3];
            let mut hi = [f32::MIN; 3];
            for p in polys.iter().flatten() {
                for k in 0..3 {
                    lo[k] = lo[k].min(p[k]);
                    hi[k] = hi[k].max(p[k]);
                }
            }
            let q = mopp::Quant::fit(lo, hi);
            let prims: Vec<(u32, mopp::Aabb)> = polys
                .iter()
                .enumerate()
                .map(|(i, p)| (i as u32, q.box_of(p)))
                .collect();
            let code = build_checked(&prims, &format!("definition {d}"))?;
            let (mut element, _) =
                transplant::donor_element(file, &format!("{base}.mopp codes"), 0).map_err(|e| {
                    Error::Other(format!("definition {d} has no mopp to reuse: {e}"))
                })?;
            mopp::patch_element(&mut element, q, code.len());
            lens.push(code.len());
            edits.push(NestedReplace {
                path: format!("{base}.mopp codes"),
                count: 1,
                elements: element,
                wrappers: Some(vec![mopp::wrapper(&code)]),
            });
        }
        Ok(())
    })?;
    let mut out = replace_nested(file, &edits)?;
    for &d in defs {
        sync_instance_mopp_copies(&mut out, d)?;
    }
    check_walks(&out)?;
    Ok((out, lens))
}

/// Offsets inside an instance's `physics[0]` element (its Havok `mopp bv
/// tree shape`) of the copies it keeps of its definition's mopp header.
const SHAPE_CODE_SIZE: usize = 56;
const SHAPE_CODE_INFO: usize = 64;
/// Offsets inside a definition's `mopp codes[0]` element.
const MOPP_CODE_INFO: usize = 32;
const MOPP_CODE_SIZE: usize = 56;
/// `instance definition` inside an instance element.
const INSTANCE_DEFINITION: usize = 52;

/// Copy definition `d`'s mopp header — its code info (offset and scale) and
/// code length — into the Havok shape of every instance of it.
///
/// Each instance's `mopp bv tree shape` carries its own copy of both, and the
/// Havok query runs through that copy: with a recompiled definition and the
/// donor's copy left in place, the query quantises points into the donor's
/// frame and stops reading the tree at the donor's length. Blam's own point
/// test reads the collision tables directly, so a pawn at rest still stood
/// while anything moving through Havok fell through the terrain (Hang 'Em
/// High, 2026-09-30: instance 763 kept length 5187 and offset (-109.05,
/// 12.74, -11.59) against a 14,151-byte tree). Returns the instances patched.
pub fn sync_instance_mopp_copies(file: &mut Vec<u8>, d: usize) -> Result<Vec<usize>, Error> {
    let base = transplant::definition(d);
    let base = base.trim_end_matches(".collision info").to_string();
    let (header, targets) = {
        let bytes: &[u8] = file;
        with_tag(bytes, |layout, root| {
            let mopp = find_block(layout, bytes, root, &format!("{base}.mopp codes"))?;
            let e = mopp
                .block
                .element(0)
                .ok_or_else(|| Error::Other(format!("definition {d} has no mopp")))?;
            let mut header = [0u8; 20];
            header[..16].copy_from_slice(&e[MOPP_CODE_INFO..MOPP_CODE_INFO + 16]);
            header[16..].copy_from_slice(&e[MOPP_CODE_SIZE..MOPP_CODE_SIZE + 4]);
            let inst = find_block(layout, bytes, root, INSTANCES)?;
            let mut targets = Vec::new();
            for i in 0..inst.block.count as usize {
                let el = inst.block.element(i).unwrap();
                if i16::from_le_bytes([el[INSTANCE_DEFINITION], el[INSTANCE_DEFINITION + 1]])
                    as usize
                    != d
                {
                    continue;
                }
                let Ok(phys) =
                    find_block(layout, bytes, root, &format!("{INSTANCES}[{i}].physics"))
                else {
                    continue;
                };
                if phys.block.count == 0 {
                    continue;
                }
                let at = phys.block.elements.as_ptr() as usize - bytes.as_ptr() as usize;
                targets.push((i, at));
            }
            Ok((header, targets))
        })?
    };
    for &(_, at) in &targets {
        file[at + SHAPE_CODE_INFO..at + SHAPE_CODE_INFO + 16].copy_from_slice(&header[..16]);
        file[at + SHAPE_CODE_SIZE..at + SHAPE_CODE_SIZE + 4].copy_from_slice(&header[16..]);
    }
    Ok(targets.into_iter().map(|(i, _)| i).collect())
}

/// Every instance that names definition `d`.
pub fn instances_of(file: &[u8], d: usize) -> Result<Vec<usize>, Error> {
    with_tag(file, |layout, root| {
        let inst = find_block(layout, file, root, INSTANCES)?;
        Ok((0..inst.block.count as usize)
            .filter(|&i| {
                let el = inst.block.element(i).unwrap();
                i16::from_le_bytes([el[INSTANCE_DEFINITION], el[INSTANCE_DEFINITION + 1]]) as usize
                    == d
            })
            .collect())
    })
}

/// Build a MOPP and require every primitive to answer a query of its own box,
/// or the floor has holes in it. Checked here so a bad tree never reaches a
/// container.
fn build_checked(prims: &[(u32, mopp::Aabb)], label: &str) -> Result<Vec<u8>, Error> {
    let code =
        mopp::build(prims).map_err(|e| Error::Other(format!("{label}: build mopp: {e:?}")))?;
    let mut miss = 0;
    for (id, b) in prims {
        let ql = [b.lo[0] as i32 - 1, b.lo[1] as i32 - 1, b.lo[2] as i32 - 1];
        let qh = [b.hi[0] as i32 + 1, b.hi[1] as i32 + 1, b.hi[2] as i32 + 1];
        if !mopp::query_bytes(&code, ql, qh)
            .map_err(other)?
            .contains(id)
        {
            miss += 1;
        }
    }
    if miss > 0 {
        return Err(Error::Other(format!(
            "{label}: {miss} member(s) do not answer their own box"
        )));
    }
    Ok(code)
}

fn fit_and_build(
    prims: &[(u32, [f32; 3], [f32; 3])],
    label: &str,
) -> Result<(Vec<u8>, mopp::Quant), Error> {
    let mut lo = [f32::MAX; 3];
    let mut hi = [f32::MIN; 3];
    for (_, l, h) in prims {
        for k in 0..3 {
            lo[k] = lo[k].min(l[k]);
            hi[k] = hi[k].max(h[k]);
        }
    }
    let q = mopp::Quant::fit(lo, hi);
    let boxes: Vec<(u32, mopp::Aabb)> = prims
        .iter()
        .map(|(id, l, h)| (*id, q.box_of(&[*l, *h])))
        .collect();
    Ok((build_checked(&boxes, label)?, q))
}

#[derive(Debug, Clone, Default)]
pub struct Broadphase {
    /// Code length per recompiled group, in argument order.
    pub groups: Vec<usize>,
    pub cluster: Option<usize>,
}

/// Recompile the instanced-geometry broadphase above the definitions: each
/// listed instance group's MOPP, and optionally the cluster MOPP above them.
///
/// Collision reaches an instance through two bounding-volume trees before its
/// own MOPP is consulted (cluster → instance group → instance → definition).
/// Moving or growing an instance leaves both upper trees describing where it
/// used to be; widening the group's *sphere* does not substitute for this.
///
/// Terminal convention, read off the shipped trees: an instance-group tree
/// names **absolute instance indices**, and the cluster tree names **absolute
/// group indices**.
pub fn compile_group_mopps(
    file: &[u8],
    groups: &[usize],
    cluster: bool,
) -> Result<(Vec<u8>, Broadphase), Error> {
    let mut report = Broadphase::default();
    let edits = with_tag(file, |layout, root| {
        let instances = find_block(layout, file, root, INSTANCES)?;
        let spheres = find_block(layout, file, root, GROUP_SPHERES)?;
        let group_count = spheres.block.count as usize;
        let members_of = |g: usize| -> Vec<u16> {
            match find_block(
                layout,
                file,
                root,
                &format!("{GROUP_SPHERES}[{g}].instance indices"),
            ) {
                Ok(m) => (0..m.block.count as usize)
                    .map(|k| {
                        let b = m.block.element(k).unwrap();
                        u16::from_le_bytes([b[0], b[1]])
                    })
                    .collect(),
                Err(_) => Vec::new(),
            }
        };
        let member_boxes = |g: usize| -> Vec<(u32, [f32; 3], [f32; 3])> {
            members_of(g)
                .iter()
                .filter_map(|i| {
                    instances.block.element(*i as usize).map(|e| {
                        let b = instance_box(e);
                        (*i as u32, b.min, b.max)
                    })
                })
                .collect()
        };
        // A NestedReplace rewrites a whole block, so gather every element of
        // the mopp blocks and patch only the ones being recompiled.
        let gather = |path: &str| -> Result<(Vec<Vec<u8>>, Vec<Vec<u8>>), Error> {
            let count = find_block(layout, file, root, path)?.block.count as usize;
            let mut els = Vec::with_capacity(count);
            let mut wraps = Vec::with_capacity(count);
            for i in 0..count {
                let (e, w) = transplant::donor_element(file, path, i)?;
                els.push(e);
                wraps.push(w);
            }
            Ok((els, wraps))
        };

        let mut edits = Vec::new();
        if !groups.is_empty() {
            let (mut els, mut wraps) = gather(GROUP_MOPPS)?;
            let mut touched = false;
            for &g in groups {
                let prims = member_boxes(g);
                if prims.is_empty() {
                    report.groups.push(0);
                    continue;
                }
                let (code, q) = fit_and_build(&prims, &format!("group {g}"))?;
                let el = els
                    .get_mut(g)
                    .ok_or_else(|| Error::Other(format!("no group mopp {g}")))?;
                mopp::patch_element(el, q, code.len());
                wraps[g] = mopp::wrapper(&code);
                report.groups.push(code.len());
                touched = true;
            }
            if touched {
                edits.push(NestedReplace {
                    path: GROUP_MOPPS.to_string(),
                    count: els.len() as u32,
                    elements: els.concat(),
                    wrappers: Some(wraps),
                });
            }
        }
        if cluster {
            let prims: Vec<(u32, [f32; 3], [f32; 3])> = (0..group_count)
                .filter_map(|g| {
                    let boxes = member_boxes(g);
                    if boxes.is_empty() {
                        return None;
                    }
                    let mut lo = [f32::MAX; 3];
                    let mut hi = [f32::MIN; 3];
                    for (_, l, h) in &boxes {
                        for k in 0..3 {
                            lo[k] = lo[k].min(l[k]);
                            hi[k] = hi[k].max(h[k]);
                        }
                    }
                    Some((g as u32, lo, hi))
                })
                .collect();
            let (code, q) = fit_and_build(&prims, "cluster")?;
            let (mut els, mut wraps) = gather(CLUSTER_MOPPS)?;
            mopp::patch_element(&mut els[0], q, code.len());
            wraps[0] = mopp::wrapper(&code);
            report.cluster = Some(code.len());
            edits.push(NestedReplace {
                path: CLUSTER_MOPPS.to_string(),
                count: els.len() as u32,
                elements: els.concat(),
                wrappers: Some(wraps),
            });
        }
        Ok(edits)
    })?;
    let out = replace_nested(file, &edits)?;
    check_walks(&out)?;
    Ok((out, report))
}

/// Every instance but `except` whose stored box overlaps `b` in x and y,
/// grown by `margin`.
pub fn footprint_overlaps(
    file: &[u8],
    b: Bounds,
    margin: f32,
    except: usize,
) -> Result<Vec<usize>, Error> {
    Ok(instance_boxes(file)?
        .iter()
        .enumerate()
        .filter(|(i, ib)| {
            *i != except
                && ib.max[0] >= b.min[0] - margin
                && ib.min[0] <= b.max[0] + margin
                && ib.max[1] >= b.min[1] - margin
                && ib.min[1] <= b.max[1] + margin
        })
        .map(|(i, _)| i)
        .collect())
}

/// Drop instances to `z` by their position alone. Their stored boxes are left
/// where they were, so the broadphase still reaches them and tests a shape
/// that is no longer there.
pub fn park_instances(file: &[u8], ids: &[usize], z: f32) -> Result<Vec<u8>, Error> {
    if ids.is_empty() {
        return Ok(file.to_vec());
    }
    // Position is a fixed-width field inside a fixed-size element, so the z
    // is written in place rather than through a re-parse per instance.
    let (start, size, count) = with_tag(file, |layout, root| {
        let inst = find_block(layout, file, root, INSTANCES)?;
        let count = inst.block.count as usize;
        let start = inst.block.elements.as_ptr() as usize - file.as_ptr() as usize;
        Ok((start, inst.block.elements.len() / count.max(1), count))
    })?;
    let mut out = file.to_vec();
    for &i in ids {
        if i >= count {
            return Err(Error::Other(format!("no instance {i} to park")));
        }
        let at = start + i * size + 48;
        out[at..at + 4].copy_from_slice(&z.to_le_bytes());
    }
    check_walks(&out)?;
    Ok(out)
}

/// Make `instance` a collision candidate everywhere in the canvas: append a
/// collidable header for it to every cluster's root node of the `instance kd
/// hierarchy`.
///
/// The hierarchy is how a collision query finds instances to test: a
/// position's cluster and the world shell's supernode walk key a spatial hash
/// (`(cluster, supernode, plane)`, root = `(cluster, 0, 0)`) into kd nodes,
/// and box, sphere and point queries test the headers of the root and every
/// node on the way down; rays climb the parent links back to the root
/// (HaloSimulation CU4 `0x3cad30`, `0x3e2ab0`, `0x3e27e0`). A host moved away
/// from its shipped box is listed only in the nodes around the old box, so
/// the moved terrain was never tested and everything fell through it. A
/// header at the roots is tested by every query. Duplicate headers are
/// harmless: a query marks each instance visited once. Returns the roots.
pub fn add_to_kd_roots(
    file: &[u8],
    instance: usize,
    bsp_index: u8,
) -> Result<(Vec<u8>, Vec<usize>), Error> {
    const KD: &str = "instance kd hierarchy";
    let mut roots: Vec<usize> = with_tag(file, |layout, root| {
        let hash = find_block(layout, file, root, &format!("{KD}.hash data"))?;
        Ok((0..hash.block.count as usize)
            .filter_map(|i| {
                let e = hash.block.element(i)?;
                let w = |o: usize| i32::from_le_bytes(e[o..o + 4].try_into().unwrap());
                (w(8) == 0 && w(12) == 0).then_some(w(0) as usize)
            })
            .collect())
    })?;
    roots.sort_unstable();
    roots.dedup();
    let mut header = Vec::with_capacity(12);
    header.push(0u8); // cull flags: none, so every query tests it
    header.push(bsp_index);
    header.extend_from_slice(&(instance as u16).to_le_bytes());
    header.extend_from_slice(&(1u32 << (instance % 32)).to_le_bytes());
    header.extend_from_slice(&(1u32 << bsp_index).to_le_bytes());
    let mut edits = Vec::new();
    with_tag(file, |layout, root| {
        for &r in &roots {
            let path = format!("{KD}.nodes[{r}].collidable headers");
            let found = find_block(layout, file, root, &path)?;
            let mut elements = found.block.elements.to_vec();
            elements.extend_from_slice(&header);
            edits.push(NestedReplace {
                path,
                count: found.block.count + 1,
                elements,
                wrappers: None,
            });
        }
        Ok(())
    })?;
    let out = replace_nested(file, &edits)?;
    check_walks(&out)?;
    Ok((out, roots))
}

/// Give the BSP a new index in its scenario: every kd hierarchy header (its
/// `bsp index` and `bsp mask`) and every instance's collision shape
/// (`structure_bsp_index`) names `bsp_index`. A BSP built from a donor
/// carries the donor's index in its own headers. Returns how many headers
/// and shapes changed.
pub fn retarget_bsp(file: &[u8], bsp_index: u8) -> Result<(Vec<u8>, usize), Error> {
    const NODES: &str = "instance kd hierarchy.nodes";
    let mut changed = 0;
    let mut edits = Vec::new();
    with_tag(file, |layout, root| {
        let nodes = find_block(layout, file, root, NODES)?.block.count as usize;
        for n in 0..nodes {
            for list in ["collidable headers", "render only headers"] {
                let path = format!("{NODES}[{n}].{list}");
                let found = find_block(layout, file, root, &path)?;
                let size = found.block.element_size as usize;
                let mut elements = found.block.elements.to_vec();
                let mut dirty = false;
                // [cull flags, bsp index, instance (u16), instance mask (u32), bsp mask (u32)]
                for h in elements.chunks_mut(size) {
                    let mask = (1u32 << bsp_index).to_le_bytes();
                    if h[1] != bsp_index || h[8..12] != mask {
                        h[1] = bsp_index;
                        h[8..12].copy_from_slice(&mask);
                        changed += 1;
                        dirty = true;
                    }
                }
                if dirty {
                    edits.push(NestedReplace {
                        path,
                        count: found.block.count,
                        elements,
                        wrappers: None,
                    });
                }
            }
        }
        Ok(())
    })?;
    let mut out = replace_nested(file, &edits)?;
    // Every instance's physics and its shapes (an instance with no physics
    // has none).
    let shapes: Vec<String> = with_tag(&out, |layout, root| {
        let mut shapes = Vec::new();
        let instances = find_block(layout, &out, root, INSTANCES)?.block.count as usize;
        for i in 0..instances {
            let physics = format!("{INSTANCES}[{i}].physics");
            for p in 0..find_block(layout, &out, root, &physics)?.block.count as usize {
                let shape = format!("{physics}[{p}].collision geometry shape");
                for s in 0..find_block(layout, &out, root, &shape)?.block.count as usize {
                    shapes.push(format!("{shape}[{s}].structure_bsp_index"));
                }
            }
        }
        Ok(shapes)
    })?;
    for path in shapes {
        out = set_scalar(&out, &path, &bsp_index.to_string())?;
        changed += 1;
    }
    check_walks(&out)?;
    Ok((out, changed))
}

/// What [`rebuild_structure_mopp`] kept, dropped and added.
#[derive(Debug, Clone, Default)]
pub struct StructureMopp {
    pub shell: usize,
    pub kept: usize,
    pub dropped: usize,
    pub added: usize,
    pub code: usize,
}

/// Type bits of a `structure_physics` MOPP key (`key >> 29`), as the
/// simulation's `getChildShape` (`0x3cf720`) decodes them.
const KEY_SHELL: u32 = 1;
const KEY_INSTANCE: u32 = 2;
const KEY_SURFACE: u32 = 3;
/// The most surfaces a type-3 key can index (13 bits).
pub const MAX_SURFACE_KEYS: usize = 0x2000;

/// One world-shell surface; `sink` (3 bits) indexes the scenario's shell
/// sink table.
pub fn shell_key(sink: u32, surface: u32) -> u32 {
    (KEY_SHELL << 29) | ((sink & 7) << 26) | (surface & 0x3ff_ffff)
}

/// A whole instance, under its frame.
pub fn instance_key(instance: u32) -> u32 {
    (KEY_INSTANCE << 29) | (instance & 0xffff)
}

/// One surface of an instance's definition, under the instance's frame.
pub fn surface_key(surface: u32, instance: u32) -> u32 {
    (KEY_SURFACE << 29) | ((surface & 0x1fff) << 16) | (instance & 0xffff)
}

/// The bytecode of a mopp element sits in a nested block of its `tgst`
/// wrapper; take the largest byte block under it.
fn bytecode(v: &blam_tag::data::Value<'_>, out: &mut Vec<u8>) {
    match v {
        blam_tag::data::Value::Block(b) => {
            if b.elements.len() > out.len() {
                *out = b.elements.to_vec();
            }
            for kids in &b.children {
                for k in kids {
                    bytecode(k, out);
                }
            }
        }
        blam_tag::data::Value::Struct { children } | blam_tag::data::Value::Array { children } => {
            for k in children {
                bytecode(k, out);
            }
        }
        _ => {}
    }
}

/// A collision table set at `base` (the world shell, or a definition's
/// `collision info`), decoded.
fn collision_at(
    layout: &blam_tag::Layout<'_>,
    file: &[u8],
    root: &blam_tag::data::Block<'_>,
    base: &str,
) -> Result<Collision, Error> {
    let get = |name: &str| -> &[u8] {
        find_block(layout, file, root, &format!("{base}.{name}"))
            .map(|f| f.block.elements)
            .unwrap_or(&[])
    };
    let t = Tables {
        bsp3d_nodes: get("bsp3d nodes"),
        planes: get("planes"),
        leaves: get("leaves"),
        bsp2d_references: get("bsp2d references"),
        bsp2d_nodes: get("bsp2d nodes"),
        surfaces: get("surfaces"),
        edges: get("edges"),
        vertices: get("vertices"),
    };
    Ok(unpack16::unpack(&t)?.0)
}

fn grow(lo: &mut [f32; 3], hi: &mut [f32; 3], p: [f32; 3]) {
    for k in 0..3 {
        lo[k] = lo[k].min(p[k]);
        hi[k] = hi[k].max(p[k]);
    }
}

/// An instance's frame: scale, axes (forward, left, up), position, definition.
type Frame = (f32, [[f32; 3]; 3], [f32; 3], usize);

fn frame_of(e: &[u8]) -> Option<Frame> {
    let f = |o: usize| f32_at(e, o);
    let d = i16::from_le_bytes([e[52], e[53]]);
    (d >= 0).then(|| {
        (
            f(0),
            [
                [f(4), f(8), f(12)],
                [f(16), f(20), f(24)],
                [f(28), f(32), f(36)],
            ],
            [f(40), f(44), f(48)],
            d as usize,
        )
    })
}

fn to_world(fr: &Frame, p: [f32; 3]) -> [f32; 3] {
    let (s, ax, pos, _) = fr;
    let mut w = *pos;
    for (k, axis) in ax.iter().enumerate() {
        for j in 0..3 {
            w[j] += s * p[k] * axis[j];
        }
    }
    w
}

fn surface_box(c: &Collision, s: usize, fr: Option<&Frame>) -> Option<([f32; 3], [f32; 3])> {
    let mut lo = [f32::MAX; 3];
    let mut hi = [f32::MIN; 3];
    for p in unpack16::polygon(c, s) {
        grow(&mut lo, &mut hi, fr.map_or(p, |fr| to_world(fr, p)));
    }
    (lo[0] <= hi[0]).then_some((lo, hi))
}

/// Recompile the BSP's static Havok body, `structure_physics.mopp code
/// block`, so movement can stand on the host's new geometry.
///
/// This, not a definition's collision BSP or its instance's own shape, is
/// what Havok moves pawns, vehicles and items against: a control with the
/// host instance parked away still held the pawn. Each terminal is a key
/// (HaloSimulation CU4 `getChildShape`, `0x3cf720`): `key >> 29` = 1 is one
/// world-shell surface (`0x20000000 | k << 26 | surface`), 2 is a whole
/// instance under its frame (`0x40000000 | instance`), 3 is one surface of an
/// instance's definition under its frame (`0x60000000 | surface << 16 |
/// instance`, surface < 8192). B40's start BSP ships 19, 776 and 34,095 of
/// them. The tree is never rebuilt at load, so geometry moved or replaced has
/// no terminals where it now is.
///
/// Kept: every shell key and every key of an instance that is neither the
/// host nor parked, each boxed from its geometry as it is now. Dropped: keys
/// of parked instances and the host's old keys. Added: one surface key per
/// host surface (one instance key past 8,191 surfaces).
pub fn rebuild_structure_mopp(
    file: &[u8],
    hosts: &[usize],
    parked: &[usize],
) -> Result<(Vec<u8>, StructureMopp), Error> {
    const BLOCK: &str = "structure_physics.mopp code block";
    let mut report = StructureMopp::default();
    let prims = with_tag(file, |layout, root| {
        let m = find_block(layout, file, root, BLOCK)?;
        if m.block.count == 0 {
            return Err(Error::Other("the BSP has no structure_physics mopp".into()));
        }
        let mut code = Vec::new();
        for v in &m.block.children[0] {
            bytecode(v, &mut code);
        }
        let keys: Vec<u32> = mopp::terminals(&code)
            .map_err(other)?
            .into_iter()
            .map(|(k, _)| k)
            .collect();

        let shell = collision_at(layout, file, root, transplant::SHELL)?;
        let inst = find_block(layout, file, root, INSTANCES)?;
        let mut defs: std::collections::HashMap<usize, Collision> =
            std::collections::HashMap::new();
        let mut prims: Vec<(u32, [f32; 3], [f32; 3])> = Vec::with_capacity(keys.len() + 4096);
        for key in keys {
            let ty = key >> 29;
            let instance = (key & 0xffff) as usize;
            let b = match ty {
                KEY_SHELL => {
                    report.shell += 1;
                    // The engine sinks shell polygons' z by up to a table
                    // value plus 0.0164; widen the box down to cover it.
                    surface_box(&shell, (key & 0x3ff_ffff) as usize, None).map(|(mut lo, hi)| {
                        lo[2] -= 0.25;
                        (lo, hi)
                    })
                }
                KEY_INSTANCE | KEY_SURFACE
                    if hosts.contains(&instance) || parked.contains(&instance) =>
                {
                    report.dropped += 1;
                    continue;
                }
                KEY_INSTANCE => inst.block.element(instance).map(|e| {
                    let b = instance_box(e);
                    (b.min, b.max)
                }),
                KEY_SURFACE => match inst.block.element(instance).and_then(frame_of) {
                    Some(fr) => {
                        if !defs.contains_key(&fr.3) {
                            let c =
                                collision_at(layout, file, root, &transplant::definition(fr.3))?;
                            defs.insert(fr.3, c);
                        }
                        surface_box(&defs[&fr.3], ((key >> 16) & 0x1fff) as usize, Some(&fr))
                    }
                    None => None,
                },
                _ => None,
            };
            let (lo, hi) =
                b.ok_or_else(|| Error::Other(format!("structure key {key:#010x} names nothing")))?;
            if ty != KEY_SHELL {
                report.kept += 1;
            }
            prims.push((key, lo, hi));
        }
        // Each host's own geometry, surface by surface as the cook does it.
        for &host in hosts {
            let e = inst
                .block
                .element(host)
                .ok_or_else(|| Error::Other(format!("no instance {host}")))?;
            let fr = frame_of(e)
                .ok_or_else(|| Error::Other(format!("host instance {host} has no definition")))?;
            let c = collision_at(layout, file, root, &transplant::definition(fr.3))?;
            if c.surfaces.len() <= MAX_SURFACE_KEYS {
                for s in 0..c.surfaces.len() {
                    if let Some((lo, hi)) = surface_box(&c, s, Some(&fr)) {
                        prims.push((surface_key(s as u32, host as u32), lo, hi));
                        report.added += 1;
                    }
                }
            } else {
                // Past 13 bits of surface index: the whole instance, whose own
                // shape (the definition MOPP under the instance frame) Havok
                // descends into (Sidewinder, 2026-09-30).
                let b = instance_box(e);
                prims.push((instance_key(host as u32), b.min, b.max));
                report.added += 1;
            }
        }
        Ok(prims)
    })?;
    let (code, q) = fit_and_build(&prims, "structure_physics")?;
    report.code = code.len();
    let (mut element, _) = transplant::donor_element(file, BLOCK, 0)?;
    mopp::patch_element(&mut element, q, code.len());
    let out = replace_nested(
        file,
        &[NestedReplace {
            path: BLOCK.to_string(),
            count: 1,
            elements: element,
            wrappers: Some(vec![mopp::wrapper(&code)]),
        }],
    )?;
    check_walks(&out)?;
    Ok((out, report))
}

/// What [`convert_own`] built.
#[derive(Debug, Clone)]
pub struct OwnReport {
    /// The terrain's bounds in canvas world space.
    pub bounds: Bounds,
    pub surfaces: usize,
    pub parked: Vec<usize>,
    pub structure: StructureMopp,
}

/// A structure BSP that is only the CE map, built on a small shipped donor
/// with ONE kd supernode, one cluster and one instance — `BSP_03_1_Chasm_old`
/// (62 shell surfaces; definition 0 behind instance 0 in group 0).
///
/// The CE tree goes into the world shell (the inside-the-world test and
/// Blam's own queries) and into definition 0 behind instance 0, which the
/// rebuilt `structure_physics` body lists surface by surface — the path proven
/// on Hang 'Em High. A body of shell keys alone did not hold a pawn. Nothing
/// of the canvas mission's geometry is used. Definition 0 ships without a
/// MOPP element, so it gets one first, cloned from the static body's (the
/// same struct), for the recompile to patch.
///
/// `scenery` is standalone collision too large to share definition 0's 16-bit
/// tables ([`crate::split::split_standalone`]): each piece gets a definition
/// and an instance of its own ([`add_scenery_instances`]), and the group,
/// cluster and structure trees are rebuilt over all of them.
pub fn convert_own(
    donor: &[u8],
    collision: Collision,
    scenery: Vec<Collision>,
    delta: [f32; 3],
    bsp_index: u8,
    keep_materials: bool,
) -> Result<(Vec<u8>, Report), Error> {
    const HOST: Host = Host {
        definition: 0,
        instance: 0,
        group: 0,
    };
    let base = transplant::definition(HOST.definition);
    let mopps = format!("{}.mopp codes", base.trim_end_matches(".collision info"));
    let has_mopp = with_tag(donor, |layout, root| {
        Ok(find_block(layout, donor, root, &mopps)
            .map(|f| f.block.count > 0)
            .unwrap_or(false))
    })?;
    let seeded;
    let donor = if has_mopp {
        donor
    } else {
        let (element, wrapper) =
            transplant::donor_element(donor, "structure_physics.mopp code block", 0)?;
        seeded = replace_nested(
            donor,
            &[NestedReplace {
                path: mopps,
                count: 1,
                elements: element,
                wrappers: Some(vec![wrapper]),
            }],
        )?;
        check_walks(&seeded)?;
        &seeded[..]
    };
    let opts = Options {
        host: HOST,
        delta,
        park: Park::None,
        park_z: -500.0,
        shell: Some(ShellOptions {
            kd_template: donor.to_vec(),
        }),
        bsp_index,
        keep_materials,
    };
    let (file, mut report) = convert(donor, collision, &opts)?;
    if scenery.is_empty() {
        return Ok((file, report));
    }
    let (file, added) =
        add_scenery_instances(&file, scenery, HOST, delta, bsp_index, keep_materials)?;
    if let Some(b) = added.bounds {
        let t = report.bounds;
        report.bounds = Bounds {
            min: [0, 1, 2].map(|k| t.min[k].min(b.min[k])),
            max: [0, 1, 2].map(|k| t.max[k].max(b.max[k])),
        };
    }
    let (center, radius) = bounding_sphere(report.bounds);
    let file = set_group_sphere(&file, HOST.group, center, radius)?;
    let (file, group) = compile_group_mopps(&file, &[HOST.group], true)?;
    let mut hosts = vec![HOST.instance];
    hosts.extend(&added.instances);
    let (file, structure) = rebuild_structure_mopp(&file, &hosts, &[])?;
    report.sphere_center = center;
    report.sphere_radius = radius;
    report.group_code = group.groups.first().copied().unwrap_or(0);
    report.cluster_code = group.cluster.unwrap_or(0);
    report.structure = structure;
    report.scenery = added;
    Ok((file, report))
}

/// Append a copy of the last element of the block at `path`, nested blocks
/// and all. Returns the new file and the new element's index.
fn duplicate_last(file: &[u8], path: &str) -> Result<(Vec<u8>, usize), Error> {
    let count = with_tag(file, |layout, root| {
        Ok(find_block(layout, file, root, path)?.block.count as usize)
    })?;
    if count == 0 {
        return Err(Error::Other(format!("{path} has no element to copy")));
    }
    let (out, _) = with_tag(file, |layout, root| {
        blam_tag::patch::edit_elements(
            layout,
            file,
            root,
            path,
            blam_tag::patch::ElementOp::Duplicate(count - 1),
        )
        .map_err(other)
    })?;
    Ok((out, count))
}

/// Add `index` to an `index_list_block` (a group's `instance indices`).
fn append_index(file: &[u8], path: &str, index: usize) -> Result<Vec<u8>, Error> {
    let edit = with_tag(file, |layout, root| {
        let found = find_block(layout, file, root, path)?;
        let count = found.block.count as usize;
        let size = if count > 0 {
            found.block.elements.len() / count
        } else {
            2
        };
        let mut elements = found.block.elements.to_vec();
        let mut element = vec![0u8; size];
        element[..2].copy_from_slice(&(index as u16).to_le_bytes());
        elements.extend_from_slice(&element);
        Ok(NestedReplace {
            path: path.to_string(),
            count: count as u32 + 1,
            elements,
            wrappers: None,
        })
    })?;
    Ok(replace_nested(file, &[edit])?)
}

/// What [`add_scenery_instances`] added.
#[derive(Debug, Clone, Default)]
pub struct Scenery {
    /// One instance per piece, each behind a definition of its own.
    pub instances: Vec<usize>,
    pub surfaces: usize,
    /// The union of the pieces' bounds, in canvas world space.
    pub bounds: Option<Bounds>,
}

/// Give each piece of standalone collision (scenery, from
/// [`crate::split::split_standalone`]) a definition and an instance of its
/// own, copied from the host's, in the host's group.
///
/// One definition's tables are 16-bit, which a forested map's scenery
/// overflows on its own (Timberland: 31,950 scenery triangles over 5,759
/// terrain surfaces). Each piece goes through the same steps as the host:
/// its tables and an identity frame at the host's position
/// ([`transplant_definition`]), its MOPP and the instance's copies of it, a
/// collidable header at every kd root, and a place in the host's group. The
/// caller then recompiles the group and cluster trees and the structure body
/// over all of them.
pub fn add_scenery_instances(
    file: &[u8],
    pieces: Vec<Collision>,
    host: Host,
    delta: [f32; 3],
    bsp_index: u8,
    keep_materials: bool,
) -> Result<(Vec<u8>, Scenery), Error> {
    const DEFINITIONS: &str =
        "resource interface.raw_resources[0].raw_items.instanced geometries definitions";
    let mut file = file.to_vec();
    let mut report = Scenery::default();
    for piece in pieces {
        let (f, d) = duplicate_last(&file, DEFINITIONS)?;
        let (f, i) = duplicate_last(&f, INSTANCES)?;
        let p = format!("{INSTANCES}[{i}]");
        let f = set_scalar(&f, &format!("{p}.instance definition"), &d.to_string())?;
        let f = set_scalar(
            &f,
            &format!("{p}.physics[0].collision geometry shape[0].instance index"),
            &i.to_string(),
        )?;
        let at = Host {
            definition: d,
            instance: i,
            group: host.group,
        };
        let (f, t) = transplant_definition(&f, piece, at, delta, keep_materials)?;
        let (f, _) = compile_definition_mopps(&f, &[d])?;
        let f = append_index(
            &f,
            &format!("{GROUP_SPHERES}[{}].instance indices", host.group),
            i,
        )?;
        let (f, _) = add_to_kd_roots(&f, i, bsp_index)?;
        file = f;
        report.instances.push(i);
        report.surfaces += t.surfaces;
        report.bounds = Some(match report.bounds {
            None => t.bounds,
            Some(b) => Bounds {
                min: [0, 1, 2].map(|k| b.min[k].min(t.bounds.min[k])),
                max: [0, 1, 2].map(|k| b.max[k].max(t.bounds.max[k])),
            },
        });
    }
    check_walks(&file)?;
    Ok((file, report))
}

/// The shell key sink index the shipped shell keys carry (`key >> 26 & 7`).
const SHELL_SINK: u32 = 5;

/// Recompile `structure_physics` with one shell key per world-shell surface
/// and nothing else.
pub fn shell_structure_mopp(file: &[u8]) -> Result<(Vec<u8>, StructureMopp), Error> {
    const BLOCK: &str = "structure_physics.mopp code block";
    let mut report = StructureMopp::default();
    let prims = with_tag(file, |layout, root| {
        let shell = collision_at(layout, file, root, transplant::SHELL)?;
        let mut prims = Vec::with_capacity(shell.surfaces.len());
        for s in 0..shell.surfaces.len() {
            if let Some((mut lo, hi)) = surface_box(&shell, s, None) {
                lo[2] -= 0.25;
                prims.push((shell_key(SHELL_SINK, s as u32), lo, hi));
                report.shell += 1;
            }
        }
        Ok(prims)
    })?;
    let (code, q) = fit_and_build(&prims, "structure_physics")?;
    report.code = code.len();
    let (mut element, _) = transplant::donor_element(file, BLOCK, 0)?;
    mopp::patch_element(&mut element, q, code.len());
    let out = replace_nested(
        file,
        &[NestedReplace {
            path: BLOCK.to_string(),
            count: 1,
            elements: element,
            wrappers: Some(vec![mopp::wrapper(&code)]),
        }],
    )?;
    check_walks(&out)?;
    Ok((out, report))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The keys B40's start BSP ships decode as the simulation reads them:
    /// its lowest key is shell surface 0 with sink index 5, and its highest
    /// is surface 3204 of instance 833 (definition 178 has 3,205 surfaces).
    #[test]
    fn structure_keys_match_the_shipped_ones() {
        assert_eq!(shell_key(5, 0), 0x3400_0000);
        assert_eq!(surface_key(3204, 833), 0x6C84_0341);
        assert_eq!(instance_key(763), 0x4000_02FB);
        assert_eq!(0x3400_0000 >> 29, KEY_SHELL);
        assert_eq!(surface_key(0x1fff, 0xffff) >> 29, KEY_SURFACE);
    }

    #[test]
    fn a_terrain_is_centred_on_the_anchor_with_its_floor_at_z() {
        let b = Bounds {
            min: [5.9, -190.2, -0.35],
            max: [131.9, -45.06, 50.0],
        };
        let d = delta_to_anchor(b, B40_START_ANCHOR);
        assert!((b.min[0] + d[0] + b.max[0] + d[0] - 2.0 * B40_START_ANCHOR[0]).abs() < 1e-3);
        assert!((b.min[1] + d[1] + b.max[1] + d[1] - 2.0 * B40_START_ANCHOR[1]).abs() < 1e-3);
        assert!((b.min[2] + d[2] - B40_START_ANCHOR[2]).abs() < 1e-4);
    }

    #[test]
    fn the_bounding_sphere_reaches_every_corner() {
        let b = Bounds {
            min: [-1.0, -2.0, -3.0],
            max: [1.0, 2.0, 3.0],
        };
        let (c, r) = bounding_sphere(b);
        assert_eq!(c, [0.0, 0.0, 0.0]);
        assert!((r - 14f32.sqrt()).abs() < 1e-5);
    }
}
