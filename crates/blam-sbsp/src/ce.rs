//! The classic Halo CE collision BSP, as the halo2ue exporter stages it.
//!
//! `collision_<i>.json` describes the arrays and `collision_<i>.bin` carries
//! them as verbatim little-endian CE element bytes, each array prefixed by a
//! `u32` count, in the fixed order bsp3d nodes, planes, leaves, bsp2d
//! references, bsp2d nodes, surfaces, edges, vertices. Coordinates are Halo
//! world units on Blam axes — the same units and axes the Meteorite `sbsp`
//! uses, so no geometry is transformed on the way through.

use std::path::Path;

use serde::Deserialize;

use crate::Error;

/// CE element sizes, in bytes, in `.bin` order.
pub const CE_SIZES: [usize; 8] = [12, 16, 8, 8, 20, 12, 24, 16];

#[derive(Debug, Clone, Deserialize)]
pub struct Manifest {
    pub layout: String,
    #[serde(default)]
    pub coordinate_space: String,
    pub world_bounds: Bounds,
    #[serde(default)]
    pub materials: Vec<Material>,
}

#[derive(Debug, Clone, Copy, Deserialize)]
pub struct Bounds {
    pub min: [f32; 3],
    pub max: [f32; 3],
}

#[derive(Debug, Clone, Deserialize)]
pub struct Material {
    pub index: usize,
    #[serde(default)]
    pub shader_class: String,
    #[serde(default)]
    pub shader_path: String,
}

/// One bsp3d node: children are `-1` for none, or `0x8000_0000 | leaf`.
#[derive(Debug, Clone, Copy)]
pub struct Bsp3dNode {
    pub plane: i32,
    pub back: i32,
    pub front: i32,
}

#[derive(Debug, Clone, Copy)]
pub struct Plane {
    pub n: [f32; 3],
    pub d: f32,
}

#[derive(Debug, Clone, Copy)]
pub struct Leaf {
    pub flags: u16,
    pub reference_count: i16,
    pub first_reference: i32,
}

/// `node` is `0x8000_0000 | surface` when it names a surface directly.
#[derive(Debug, Clone, Copy)]
pub struct Bsp2dReference {
    pub plane: i32,
    pub node: i32,
}

#[derive(Debug, Clone, Copy)]
pub struct Bsp2dNode {
    pub plane: [f32; 3],
    pub left: i32,
    pub right: i32,
}

#[derive(Debug, Clone, Copy)]
pub struct Surface {
    pub plane: i32,
    pub first_edge: i32,
    /// bit 0 two sided, 1 invisible, 2 climbable, 3 breakable.
    pub flags: u8,
    pub breakable: i8,
    pub material: i16,
}

#[derive(Debug, Clone, Copy)]
pub struct Edge {
    pub start: i32,
    pub end: i32,
    pub forward: i32,
    pub reverse: i32,
    pub left: i32,
    pub right: i32,
}

#[derive(Debug, Clone, Copy)]
pub struct Vertex {
    pub point: [f32; 3],
    pub first_edge: i32,
}

#[derive(Debug, Clone, Default)]
pub struct Collision {
    pub bsp3d_nodes: Vec<Bsp3dNode>,
    pub planes: Vec<Plane>,
    pub leaves: Vec<Leaf>,
    pub bsp2d_references: Vec<Bsp2dReference>,
    pub bsp2d_nodes: Vec<Bsp2dNode>,
    pub surfaces: Vec<Surface>,
    pub edges: Vec<Edge>,
    pub vertices: Vec<Vertex>,
}

/// A staged BSP: the manifest plus its decoded arrays.
#[derive(Debug, Clone)]
pub struct Staged {
    pub manifest: Manifest,
    pub collision: Collision,
}

struct Cursor<'a> {
    b: &'a [u8],
    at: usize,
}

impl<'a> Cursor<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8], Error> {
        let s = self
            .b
            .get(self.at..self.at + n)
            .ok_or_else(|| Error::Staging(format!("collision.bin truncated at {}", self.at)))?;
        self.at += n;
        Ok(s)
    }
    fn u32(&mut self) -> Result<u32, Error> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
}

fn i32_at(b: &[u8], o: usize) -> i32 {
    i32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}
fn i16_at(b: &[u8], o: usize) -> i16 {
    i16::from_le_bytes(b[o..o + 2].try_into().unwrap())
}
fn u16_at(b: &[u8], o: usize) -> u16 {
    u16::from_le_bytes(b[o..o + 2].try_into().unwrap())
}
fn f32_at(b: &[u8], o: usize) -> f32 {
    f32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

/// Read `collision_<i>.json` and its `.bin` sibling.
pub fn load(json_path: &Path) -> Result<Staged, Error> {
    let text = std::fs::read_to_string(json_path)
        .map_err(|e| Error::Staging(format!("{}: {e}", json_path.display())))?;
    let manifest: Manifest = serde_json::from_str(&text)
        .map_err(|e| Error::Staging(format!("{}: {e}", json_path.display())))?;
    if manifest.layout != "ce_pc_v7" {
        return Err(Error::Staging(format!(
            "unsupported collision layout {:?}",
            manifest.layout
        )));
    }
    let bin_path = json_path.with_extension("bin");
    let bin = std::fs::read(&bin_path)
        .map_err(|e| Error::Staging(format!("{}: {e}", bin_path.display())))?;
    let collision = parse_bin(&bin)?;
    Ok(Staged {
        manifest,
        collision,
    })
}

/// Decode the eight count-prefixed arrays.
pub fn parse_bin(bin: &[u8]) -> Result<Collision, Error> {
    let mut c = Cursor { b: bin, at: 0 };
    let mut arrays: Vec<&[u8]> = Vec::with_capacity(8);
    for size in CE_SIZES {
        let n = c.u32()? as usize;
        arrays.push(c.take(n * size)?);
    }
    if c.at != bin.len() {
        return Err(Error::Staging(format!(
            "collision.bin has {} trailing byte(s)",
            bin.len() - c.at
        )));
    }
    let mut out = Collision::default();
    for b in arrays[0].chunks_exact(12) {
        out.bsp3d_nodes.push(Bsp3dNode {
            plane: i32_at(b, 0),
            back: i32_at(b, 4),
            front: i32_at(b, 8),
        });
    }
    for b in arrays[1].chunks_exact(16) {
        out.planes.push(Plane {
            n: [f32_at(b, 0), f32_at(b, 4), f32_at(b, 8)],
            d: f32_at(b, 12),
        });
    }
    for b in arrays[2].chunks_exact(8) {
        out.leaves.push(Leaf {
            flags: u16_at(b, 0),
            reference_count: i16_at(b, 2),
            first_reference: i32_at(b, 4),
        });
    }
    for b in arrays[3].chunks_exact(8) {
        out.bsp2d_references.push(Bsp2dReference {
            plane: i32_at(b, 0),
            node: i32_at(b, 4),
        });
    }
    for b in arrays[4].chunks_exact(20) {
        out.bsp2d_nodes.push(Bsp2dNode {
            plane: [f32_at(b, 0), f32_at(b, 4), f32_at(b, 8)],
            left: i32_at(b, 12),
            right: i32_at(b, 16),
        });
    }
    for b in arrays[5].chunks_exact(12) {
        out.surfaces.push(Surface {
            plane: i32_at(b, 0),
            first_edge: i32_at(b, 4),
            flags: b[8],
            breakable: b[9] as i8,
            material: i16_at(b, 10),
        });
    }
    for b in arrays[6].chunks_exact(24) {
        out.edges.push(Edge {
            start: i32_at(b, 0),
            end: i32_at(b, 4),
            forward: i32_at(b, 8),
            reverse: i32_at(b, 12),
            left: i32_at(b, 16),
            right: i32_at(b, 20),
        });
    }
    for b in arrays[7].chunks_exact(16) {
        out.vertices.push(Vertex {
            point: [f32_at(b, 0), f32_at(b, 4), f32_at(b, 8)],
            first_edge: i32_at(b, 12),
        });
    }
    Ok(out)
}

impl Collision {
    /// Axis-aligned bounds of the vertices.
    pub fn bounds(&self) -> Option<Bounds> {
        let first = self.vertices.first()?;
        let mut min = first.point;
        let mut max = first.point;
        for v in &self.vertices {
            for a in 0..3 {
                min[a] = min[a].min(v.point[a]);
                max[a] = max[a].max(v.point[a]);
            }
        }
        Some(Bounds { min, max })
    }

    /// Every index must fit the 16-bit Meteorite tables: nodes and leaves in
    /// 24 bits, everything else in 15 (the sign bit flags surfaces).
    pub fn fits_16bit(&self) -> Result<(), Error> {
        let check = |name: &str, n: usize, max: usize| {
            if n > max {
                Err(Error::Staging(format!(
                    "{name}: {n} elements exceed the 16-bit table limit {max}"
                )))
            } else {
                Ok(())
            }
        };
        check("bsp3d nodes", self.bsp3d_nodes.len(), 0x7f_ffff)?;
        check("leaves", self.leaves.len(), 0x7f_ffff)?;
        check("planes", self.planes.len(), 0xffff)?;
        check("bsp2d references", self.bsp2d_references.len(), 0xffff)?;
        check("bsp2d nodes", self.bsp2d_nodes.len(), 0x7fff)?;
        check("surfaces", self.surfaces.len(), 0x7fff)?;
        check("edges", self.edges.len(), 0xfffe)?;
        check("vertices", self.vertices.len(), 0xfffe)?;
        Ok(())
    }
}
