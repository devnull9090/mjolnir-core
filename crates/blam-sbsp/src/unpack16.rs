//! Read the Meteorite 16-bit collision tables back into CE-shaped structs: the
//! inverse of [`crate::pack16`], so a shipped definition can be decoded,
//! re-packed and compared byte for byte — the one test of the encoder that
//! needs no running game.

use crate::ce::{
    Bsp2dNode, Bsp2dReference, Bsp3dNode, Collision, Edge, Leaf, Plane, Surface, Vertex,
};
use crate::pack16::{LEAF24, NONE24};
use crate::Error;

/// Per-surface fields the CE structs have no home for, kept so a round trip
/// can put them back.
#[derive(Debug, Clone, Default)]
pub struct SurfaceExtras {
    pub breakable_set: Vec<i16>,
    pub breakable: Vec<i16>,
    pub best_plane_vertex: Vec<u8>,
    pub high_flags: Vec<u16>,
}

/// The raw bytes of the eight tables, as read from a tag.
#[derive(Debug, Clone, Default)]
pub struct Tables<'a> {
    pub bsp3d_nodes: &'a [u8],
    pub planes: &'a [u8],
    pub leaves: &'a [u8],
    pub bsp2d_references: &'a [u8],
    pub bsp2d_nodes: &'a [u8],
    pub surfaces: &'a [u8],
    pub edges: &'a [u8],
    pub vertices: &'a [u8],
}

fn u16_at(b: &[u8], o: usize) -> u16 {
    u16::from_le_bytes([b[o], b[o + 1]])
}
fn i16_at(b: &[u8], o: usize) -> i16 {
    i16::from_le_bytes([b[o], b[o + 1]])
}
fn u32_at(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}
fn f32_at(b: &[u8], o: usize) -> f32 {
    f32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

fn child_from24(v: u32) -> i32 {
    if v == NONE24 {
        -1
    } else if v & LEAF24 != 0 {
        (0x8000_0000u32 | (v & 0x7f_ffff)) as i32
    } else {
        v as i32
    }
}

fn child_from16(v: i16) -> i32 {
    if v == -1 {
        -1
    } else if v < 0 {
        (0x8000_0000u32 | ((v as u16) & 0x7fff) as u32) as i32
    } else {
        v as i32
    }
}

fn plane_from16(v: i16) -> i32 {
    if v < 0 {
        (0x8000_0000u32 | ((v as u16) & 0x7fff) as u32) as i32
    } else {
        v as i32
    }
}

fn index_from16(v: u16) -> i32 {
    if v == u16::MAX {
        -1
    } else {
        v as i32
    }
}

/// Decode the tables. Surfaces come back with their CE-representable fields;
/// the rest are in the extras.
pub fn unpack(t: &Tables<'_>) -> Result<(Collision, SurfaceExtras), Error> {
    let mut c = Collision::default();
    let mut x = SurfaceExtras::default();

    for chunk in t.bsp3d_nodes.chunks_exact(8) {
        let w = u64::from_le_bytes(chunk.try_into().unwrap());
        c.bsp3d_nodes.push(Bsp3dNode {
            plane: (w & 0xffff) as i32,
            back: child_from24(((w >> 16) & 0xff_ffff) as u32),
            front: child_from24(((w >> 40) & 0xff_ffff) as u32),
        });
    }
    for chunk in t.planes.chunks_exact(16) {
        c.planes.push(Plane {
            n: [f32_at(chunk, 0), f32_at(chunk, 4), f32_at(chunk, 8)],
            d: f32_at(chunk, 12),
        });
    }
    for chunk in t.leaves.chunks_exact(8) {
        c.leaves.push(Leaf {
            flags: chunk[0] as u16,
            reference_count: u16_at(chunk, 2) as i16,
            first_reference: u32_at(chunk, 4) as i32,
        });
    }
    for chunk in t.bsp2d_references.chunks_exact(4) {
        c.bsp2d_references.push(Bsp2dReference {
            plane: plane_from16(i16_at(chunk, 0)),
            node: child_from16(i16_at(chunk, 2)),
        });
    }
    for chunk in t.bsp2d_nodes.chunks_exact(16) {
        c.bsp2d_nodes.push(Bsp2dNode {
            plane: [f32_at(chunk, 0), f32_at(chunk, 4), f32_at(chunk, 8)],
            left: child_from16(i16_at(chunk, 12)),
            right: child_from16(i16_at(chunk, 14)),
        });
    }
    for chunk in t.surfaces.chunks_exact(14) {
        let flags = u16_at(chunk, 10);
        let negated = flags & 0x80 != 0;
        let plane = u16_at(chunk, 0) as u32 | if negated { 0x8000_0000 } else { 0 };
        c.surfaces.push(Surface {
            plane: plane as i32,
            first_edge: index_from16(u16_at(chunk, 2)),
            flags: (flags & 0x0f) as u8,
            breakable: 0,
            material: i16_at(chunk, 4),
        });
        x.breakable_set.push(i16_at(chunk, 6));
        x.breakable.push(i16_at(chunk, 8));
        x.high_flags.push(flags & !0x8f);
        x.best_plane_vertex.push(chunk[12]);
    }
    for chunk in t.edges.chunks_exact(12) {
        c.edges.push(Edge {
            start: index_from16(u16_at(chunk, 0)),
            end: index_from16(u16_at(chunk, 2)),
            forward: index_from16(u16_at(chunk, 4)),
            reverse: index_from16(u16_at(chunk, 6)),
            left: index_from16(u16_at(chunk, 8)),
            right: index_from16(u16_at(chunk, 10)),
        });
    }
    for chunk in t.vertices.chunks_exact(16) {
        c.vertices.push(Vertex {
            point: [f32_at(chunk, 0), f32_at(chunk, 4), f32_at(chunk, 8)],
            first_edge: index_from16(u16_at(chunk, 12)),
        });
    }
    Ok((c, x))
}

/// The vertices of one surface, walking its edge loop the CE way.
pub fn polygon(c: &Collision, surface: usize) -> Vec<[f32; 3]> {
    let mut pts = Vec::new();
    let Some(s) = c.surfaces.get(surface) else {
        return pts;
    };
    if s.first_edge < 0 {
        return pts;
    }
    let first = s.first_edge as usize;
    let mut e = first;
    for _ in 0..256 {
        let Some(edge) = c.edges.get(e) else { break };
        let (v, next) = if edge.left == surface as i32 {
            (edge.start, edge.forward)
        } else {
            (edge.end, edge.reverse)
        };
        if let Some(vx) = c.vertices.get(v.max(0) as usize) {
            pts.push(vx.point);
        }
        if next < 0 {
            break;
        }
        e = next as usize;
        if e == first {
            break;
        }
    }
    pts
}
