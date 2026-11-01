//! Original open-sky Forge canvas, with no converted-map geometry.
//!
//! cargo run -p blam-sbsp --example forge_canvas -- <BSP_03_1_Chasm_old.scenario_structure_bsp> <out.sbsp>
//! Optional: --width-m 64 --depth-m 64 --thickness-m 1 --extent-m 64 --below-m 8 --height-m 64
//!
//! The slab is centred on X/Y, with its top at Z=0; all parameters are metres.
//! Output uses Blam axes/world units (metres / 3.048), BSP index 0. A sibling
//! `<out>.canvas.json` records the exact scenario bounds and render dimensions.
//! Bake on B40 with active_bsps:[8], single_bsp:8, --bsp 8=<out.sbsp> and the
//! bare defs/level/empty_world.umap. The caller supplies rendering and spawns.

use std::{error::Error, fs, path::Path};

use blam_sbsp::ce::{Bounds, Bsp3dNode, Collision, Edge, Leaf, Plane, Surface, Vertex};
use blam_sbsp::{convert, pack16, raytest, scenery, transplant, unpack16};
use blam_tag::{blockedit::find_block, patch, TagFile};

const METRES_PER_UNIT: f32 = 3.048;
type Result<T> = std::result::Result<T, Box<dyn Error>>;

#[derive(Clone, Copy, Debug)]
struct Canvas {
    width: f32,
    depth: f32,
    thickness: f32,
    extent: f32,
    below: f32,
    height: f32,
}

impl Default for Canvas {
    fn default() -> Self {
        Self {
            width: 64.0,
            depth: 64.0,
            thickness: 1.0,
            extent: 64.0,
            below: 8.0,
            height: 64.0,
        }
    }
}

impl Canvas {
    fn parse(args: &[String]) -> Result<Self> {
        let mut c = Self::default();
        if args.len() % 2 != 0 {
            return Err("each canvas option requires a value".into());
        }
        for pair in args.chunks_exact(2) {
            let value: f32 = pair[1].parse()?;
            match pair[0].as_str() {
                "--width-m" => c.width = value,
                "--depth-m" => c.depth = value,
                "--thickness-m" => c.thickness = value,
                "--extent-m" => c.extent = value,
                "--below-m" => c.below = value,
                "--height-m" => c.height = value,
                _ => return Err(format!("unknown canvas option {}", pair[0]).into()),
            }
        }
        c.validate()?;
        Ok(c)
    }

    fn validate(self) -> Result<()> {
        if [
            self.width,
            self.depth,
            self.thickness,
            self.extent,
            self.below,
            self.height,
        ]
        .iter()
        .any(|x| !x.is_finite() || *x < 0.01 || *x > 1024.0)
        {
            return Err("canvas dimensions must be finite, between 0.01 and 1024 metres".into());
        }
        if self.width > self.extent * 2.0
            || self.depth > self.extent * 2.0
            || self.thickness > self.below
        {
            return Err("playable bounds must contain the entire slab".into());
        }
        Ok(())
    }

    fn bounds(self) -> Bounds {
        Bounds {
            min: [-self.extent, -self.extent, -self.below].map(|x| x / METRES_PER_UNIT),
            max: [self.extent, self.extent, self.height].map(|x| x / METRES_PER_UNIT),
        }
    }
}

// The same linked two-sided surface construction as forge_collision, reduced
// to six original box faces. No donor geometry is used to construct this slab.
fn slab(c: Canvas) -> Collision {
    let leaf = Leaf {
        flags: 0,
        reference_count: 0,
        first_reference: 0,
    };
    let mut out = Collision {
        planes: vec![Plane {
            n: [1.0, 0.0, 0.0],
            d: 0.0,
        }],
        bsp3d_nodes: vec![Bsp3dNode {
            plane: 0,
            back: i32::MIN,
            front: i32::MIN + 1,
        }],
        leaves: vec![leaf, leaf],
        ..Default::default()
    };
    let x = c.width / (2.0 * METRES_PER_UNIT);
    let y = c.depth / (2.0 * METRES_PER_UNIT);
    let z = -c.thickness / METRES_PER_UNIT;
    let points = [
        [-x, -y, z],
        [x, -y, z],
        [x, y, z],
        [-x, y, z],
        [-x, -y, 0.0],
        [x, -y, 0.0],
        [x, y, 0.0],
        [-x, y, 0.0],
    ];
    for (indices, normal) in [
        ([0, 3, 2, 1], [0.0, 0.0, -1.0]),
        ([4, 5, 6, 7], [0.0, 0.0, 1.0]),
        ([0, 4, 7, 3], [-1.0, 0.0, 0.0]),
        ([1, 2, 6, 5], [1.0, 0.0, 0.0]),
        ([0, 1, 5, 4], [0.0, -1.0, 0.0]),
        ([3, 7, 6, 2], [0.0, 1.0, 0.0]),
    ] {
        let surface = out.surfaces.len() as i32;
        let edge = out.edges.len() as i32;
        let vertex = out.vertices.len() as i32;
        let plane = out.planes.len() as i32;
        out.planes.push(Plane {
            n: normal,
            d: (0..3).map(|i| normal[i] * points[indices[0]][i]).sum(),
        });
        for (i, &index) in indices.iter().enumerate() {
            out.vertices.push(Vertex {
                point: points[index],
                first_edge: edge + i as i32,
            });
            out.edges.push(Edge {
                start: vertex + i as i32,
                end: vertex + ((i + 1) % 4) as i32,
                forward: edge + ((i + 1) % 4) as i32,
                reverse: -1,
                left: surface,
                right: -1,
            });
        }
        out.surfaces.push(Surface {
            plane,
            first_edge: edge,
            flags: 1,
            breakable: -1,
            material: 0,
        });
    }
    scenery::link(&mut out, 0);
    out
}

fn read_collision(file: &[u8], base: &str) -> Result<Collision> {
    let tag = TagFile::parse(file, None)?;
    let layout = tag.layout()?;
    let root = tag.read_data(&layout)?;
    let get = |name: &str| -> Result<&[u8]> {
        Ok(find_block(&layout, file, &root, &format!("{base}.{name}"))?
            .block
            .elements)
    };
    Ok(unpack16::unpack(&unpack16::Tables {
        bsp3d_nodes: get("bsp3d nodes")?,
        planes: get("planes")?,
        leaves: get("leaves")?,
        bsp2d_references: get("bsp2d references")?,
        bsp2d_nodes: get("bsp2d nodes")?,
        surfaces: get("surfaces")?,
        edges: get("edges")?,
        vertices: get("vertices")?,
    })?
    .0)
}

// The game rebuilds its broadphase bounds from ALL shell vertices, then
// unions instance bounds and adds 0.1 wu (CU4 0x2c1aa1..0x2c1e20). Authored
// world/cluster bounds alone cannot expand that box: the slab-only result
// ended at Z=0.1 wu, culling every horizontal Forge ray above the floor.
// Unreferenced vertices expand that query volume without adding polygons.
// Apply this only to the world shell, after the actual Havok floor is built.
fn extend_query_bounds(collision: &mut Collision, bounds: Bounds) {
    for point in [bounds.min, bounds.max] {
        collision.vertices.push(Vertex {
            point,
            first_edge: -1,
        });
    }
}

// Test the actual game-winding walk, including the space outside the slab and
// the upper build volume. Comparing only two ray implementations could allow
// both to agree on the same incorrect floor height or a phantom ceiling.
fn verify_collision(c: &Collision, canvas: Canvas) -> Result<usize> {
    let mut checks = 0;
    for i in 0..33 {
        for j in 0..33 {
            let x = canvas.extent * (-0.98 + 1.96 * (i as f32 + 0.23) / 33.0);
            let y = canvas.extent * (-0.98 + 1.96 * (j as f32 + 0.61) / 33.0);
            let top = canvas.height * 0.75;
            let bottom = -canvas.below * 0.9;
            let p = [x, y, top].map(|v| v / METRES_PER_UNIT);
            let hit = raytest::tree_game(c, p, [0.0, 0.0, (bottom - top) / METRES_PER_UNIT]);
            let expected = x.abs() < canvas.width * 0.5 && y.abs() < canvas.depth * 0.5;
            if hit.is_some() != expected
                || hit.is_some_and(|h| (top + (bottom - top) * h.t).abs() > 0.002)
            {
                return Err(format!("canvas floor mismatch at ({x}, {y}): {hit:?}").into());
            }
            for z in [0.1, canvas.height * 0.5, canvas.height * 0.99] {
                let start = [x, y, z].map(|v| v / METRES_PER_UNIT);
                if raytest::classify(c, start).is_none()
                    || raytest::tree_game(c, start, [0.0, 0.0, 0.001]).is_some()
                {
                    return Err(format!("canvas has solid/ceiling at ({x}, {y}, {z})").into());
                }
                checks += 1;
            }
            checks += 1;
        }
    }
    Ok(checks)
}

fn verify_bounds(file: &[u8], wanted: Bounds) -> Result<()> {
    let tag = TagFile::parse(file, None)?;
    let layout = tag.layout()?;
    let root = tag.read_data(&layout)?;
    for (path, values) in [
        ("world bounds x", vec![wanted.min[0], wanted.max[0]]),
        ("world bounds y", vec![wanted.min[1], wanted.max[1]]),
        ("world bounds z", vec![wanted.min[2], wanted.max[2]]),
        ("clusters[0].bounds x", vec![wanted.min[0], wanted.max[0]]),
        ("clusters[0].bounds y", vec![wanted.min[1], wanted.max[1]]),
        ("clusters[0].bounds z", vec![wanted.min[2], wanted.max[2]]),
        ("structure_physics.mopp bounds min", wanted.min.to_vec()),
        ("structure_physics.mopp bounds max", wanted.max.to_vec()),
    ] {
        let target = patch::resolve(&layout, file, &root, path)?;
        for (index, expected) in values.iter().enumerate() {
            let offset = target.file_offset + index * 4;
            let value = f32::from_le_bytes(file[offset..offset + 4].try_into()?);
            if (value - expected).abs() > 0.00001 {
                return Err(format!("{path}: {value} != {expected}").into());
            }
        }
    }
    let aabbs = find_block(&layout, file, &root, "super aabbs")?;
    if aabbs.block.count == 0 {
        return Err("canvas has no super AABBs".into());
    }
    for element in aabbs.block.elements.chunks_exact(24) {
        for axis in 0..3 {
            let min = f32::from_le_bytes(element[axis * 8..axis * 8 + 4].try_into()?);
            let max = f32::from_le_bytes(element[axis * 8 + 4..axis * 8 + 8].try_into()?);
            if min != wanted.min[axis] || max != wanted.max[axis] {
                return Err("super AABB clips the build volume".into());
            }
        }
    }
    Ok(())
}

fn build(donor: &[u8], canvas: Canvas) -> Result<(Vec<u8>, usize)> {
    canvas.validate()?;
    let tag = TagFile::parse(donor, None)?;
    let layout = tag.layout()?;
    let root = tag.read_data(&layout)?;
    for path in [
        "clusters",
        "instanced geometry instances",
        &format!("{}.bsp3d supernodes", transplant::SHELL),
    ] {
        if find_block(&layout, donor, &root, path)?.block.count != 1 {
            return Err(format!(
                "expected the single-cluster/supernode/instance BSP_03_1_Chasm_old donor: {path}"
            )
            .into());
        }
    }
    let c = slab(canvas);
    let floor_bounds = c.bounds().ok_or("canvas floor has no vertices")?;
    let mut checks = verify_collision(&c, canvas)?;
    // The donor's static tree names 62 old shell surfaces. A six-face slab
    // cannot retain those keys: seed the shell and its static tree together
    // before convert_own rebuilds the walkable instance and its surface keys.
    let seed = transplant::apply(
        donor,
        &pack16::pack(&c, &|_| 0)?,
        &transplant::Options {
            bounds: Some(canvas.bounds()),
            kd_template: Some(donor.to_vec()),
            ..Default::default()
        },
    )?;
    let (seed, _) = convert::shell_structure_mopp(&seed)?;
    // The original map is centred at the origin, so keep definition 0 local
    // there too instead of inheriting the mission donor's translated frame.
    let seed = transplant::set_scalar(
        &seed,
        "instanced geometry instances[0].position",
        "(0, 0, 0)",
    )?;
    let (file, _) = convert::convert_own(&seed, c, vec![], [0.0; 3], 0, false)?;
    let mut shell = read_collision(&file, transplant::SHELL)?;
    extend_query_bounds(&mut shell, canvas.bounds());
    let packed = pack16::pack(&shell, &|_| 0)?;
    // Keep the slab and its compiled Havok bodies exactly as converted. Only
    // the world shell's unreferenced bound vertices and world/cluster/kd
    // envelopes extend upwards; no collision geometry is added there.
    let file = transplant::apply(
        &file,
        &packed,
        &transplant::Options {
            bounds: Some(canvas.bounds()),
            kd_template: Some(donor.to_vec()),
            ..Default::default()
        },
    )?;
    verify_bounds(&file, canvas.bounds())?;
    let shell = read_collision(&file, transplant::SHELL)?;
    let floor = read_collision(&file, &transplant::definition(0))?;
    let actual_query = shell.bounds().ok_or("canvas shell has no vertices")?;
    let actual_floor = floor.bounds().ok_or("canvas definition has no vertices")?;
    if actual_query.min != canvas.bounds().min
        || actual_query.max != canvas.bounds().max
        || actual_floor.min != floor_bounds.min
        || actual_floor.max != floor_bounds.max
    {
        return Err("canvas query volume or compact floor bounds changed unexpectedly".into());
    }
    checks += verify_collision(&shell, canvas)?;
    checks += verify_collision(&floor, canvas)?;
    Ok((file, checks))
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() < 2 {
        return Err("usage: forge_canvas <BSP_03_1_Chasm_old.scenario_structure_bsp> <out.sbsp> [--width-m 64 --depth-m 64 --thickness-m 1 --extent-m 64 --below-m 8 --height-m 64]".into());
    }
    if Path::new(&args[0]) == Path::new(&args[1]) {
        return Err("output must differ from the donor".into());
    }
    let canvas = Canvas::parse(&args[2..])?;
    let (file, checks) = build(&fs::read(&args[0])?, canvas)?;
    let bounds = canvas.bounds();
    let report = serde_json::json!({
        "schema_version": 1, "bsp_index": 0, "verified_checks": checks,
        "slab_m": { "width": canvas.width, "depth": canvas.depth, "thickness": canvas.thickness, "top_z": 0 },
        "render_cm": { "center": [0.0, 0.0, -canvas.thickness * 50.0], "dimensions": [canvas.width * 100.0, canvas.depth * 100.0, canvas.thickness * 100.0] },
        "world_bounds_wu": { "min": bounds.min, "max": bounds.max },
        "bytes": file.len()
    });
    fs::write(&args[1], &file)?;
    fs::write(
        format!("{}.canvas.json", args[1]),
        serde_json::to_vec_pretty(&report)?,
    )?;
    println!(
        "{}: {} bytes, {} verified checks; {} x {} m slab, {} m build height",
        args[1],
        file.len(),
        checks,
        canvas.width,
        canvas.depth,
        canvas.height
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn floor_hits_open_edges_and_high_build_space_survive_packing() {
        for canvas in [
            Canvas::default(),
            Canvas {
                width: 24.0,
                depth: 40.0,
                ..Canvas::default()
            },
        ] {
            let c = slab(canvas);
            assert_eq!(verify_collision(&c, canvas).unwrap(), 4356);
            let p = pack16::pack(&c, &|_| 0).unwrap();
            let (decoded, _) = unpack16::unpack(&unpack16::Tables {
                bsp3d_nodes: &p.bsp3d_nodes,
                planes: &p.planes,
                leaves: &p.leaves,
                bsp2d_references: &p.bsp2d_references,
                bsp2d_nodes: &p.bsp2d_nodes,
                surfaces: &p.surfaces,
                edges: &p.edges,
                vertices: &p.vertices,
            })
            .unwrap();
            assert_eq!(verify_collision(&decoded, canvas).unwrap(), 4356);
            let b = decoded.bounds().unwrap();
            assert!((b.min[2] + canvas.thickness / METRES_PER_UNIT).abs() < 0.00001);
            assert_eq!(b.max[2], 0.0);
        }
    }

    #[test]
    fn dimensions_reject_nonfinite_and_clipped_playable_space() {
        for (flag, value) in [
            ("--width-m", "NaN"),
            ("--height-m", "inf"),
            ("--depth-m", "-2"),
            ("--width-m", "129"),
            ("--thickness-m", "9"),
        ] {
            assert!(Canvas::parse(&[flag.into(), value.into()]).is_err());
        }
        assert!(Canvas::parse(&["--depth-m".into()]).is_err());
        assert!(Canvas::parse(&["--typo".into(), "1".into()]).is_err());
    }

    #[test]
    fn query_bounds_cover_air_without_new_collision_surfaces() {
        for canvas in [
            Canvas::default(),
            Canvas {
                width: 24.0,
                depth: 40.0,
                ..Canvas::default()
            },
        ] {
            let mut shell = slab(canvas);
            let before = pack16::pack(&shell, &|_| 0).unwrap();
            let floor_bounds = shell.bounds().unwrap();
            assert_eq!(floor_bounds.max[2], 0.0);
            extend_query_bounds(&mut shell, canvas.bounds());
            let after = pack16::pack(&shell, &|_| 0).unwrap();
            // These are the only changed bytes/tables: two orphan vertices.
            assert_eq!(after.vertices.len(), before.vertices.len() + 32);
            assert_eq!(&after.vertices[..before.vertices.len()], before.vertices);
            assert_eq!(after.bsp3d_nodes, before.bsp3d_nodes);
            assert_eq!(after.planes, before.planes);
            assert_eq!(after.leaves, before.leaves);
            assert_eq!(after.bsp2d_references, before.bsp2d_references);
            assert_eq!(after.bsp2d_nodes, before.bsp2d_nodes);
            assert_eq!(after.surfaces, before.surfaces);
            assert_eq!(after.edges, before.edges);
            let (decoded, _) = unpack16::unpack(&unpack16::Tables {
                bsp3d_nodes: &after.bsp3d_nodes,
                planes: &after.planes,
                leaves: &after.leaves,
                bsp2d_references: &after.bsp2d_references,
                bsp2d_nodes: &after.bsp2d_nodes,
                surfaces: &after.surfaces,
                edges: &after.edges,
                vertices: &after.vertices,
            })
            .unwrap();
            let query_bounds = decoded.bounds().unwrap();
            assert_eq!(query_bounds.min, canvas.bounds().min);
            assert_eq!(query_bounds.max, canvas.bounds().max);
            assert!(decoded
                .vertices
                .iter()
                .rev()
                .take(2)
                .all(|v| v.first_edge == -1));
            assert_eq!(verify_collision(&decoded, canvas).unwrap(), 4356);
            // Reproduce the live miss: this ray lies entirely above the old
            // floor+0.1 bbox, but is wholly inside the widened query volume.
            let origin = [-2.09326243, -0.23752071, 0.71773672];
            let vector = [0.00191387, -4.98987103, 0.31808609];
            assert!(origin[2] > floor_bounds.max[2] + 0.1);
            for t in [0.0, 0.62583995, 1.0] {
                let point = [0, 1, 2].map(|axis| origin[axis] + vector[axis] * t);
                assert!((0..3).all(|axis| point[axis] >= query_bounds.min[axis]
                    && point[axis] <= query_bounds.max[axis]));
                assert!(raytest::classify(&decoded, point).is_some());
            }
            assert!(raytest::tree_game(&decoded, origin, vector).is_none());
        }
    }
}
