//! The level's collision BSP (halo2ue's `bsp/collision_0.json` + `.bin`),
//! for one question: is a point inside the solid? tool.exe walks this tree
//! for its shadow rays, and a ray whose start or end lies in solid space is
//! blocked; the rendered mesh alone cannot tell (a structure's panels drawn
//! a little inside its simpler collision hull are dark in CE's lightmaps).

use crate::math::V3;
use std::path::Path;

/// CE world units per glTF metre.
const WU_TO_M: f32 = 3.048;

pub struct Collision {
    /// (plane, back child, front child); a child is a node index, a leaf
    /// (high bit set) or -1 for solid.
    nodes: Vec<[i32; 3]>,
    /// (i, j, k, d): `i x + j y + k z = d`.
    planes: Vec<[f32; 4]>,
}

impl Collision {
    pub fn load(staging: &Path) -> Option<Collision> {
        let json: serde_json::Value = serde_json::from_slice(&std::fs::read(staging.join("bsp").join("collision_0.json")).ok()?).ok()?;
        let bin = std::fs::read(staging.join(json["bin"].as_str()?)).ok()?;
        let order: Vec<&str> = json["array_order"].as_array()?.iter().filter_map(|v| v.as_str()).collect();
        let sizes = &json["element_sizes"];
        let mut at = 0usize;
        let mut nodes = Vec::new();
        let mut planes = Vec::new();
        for name in order {
            let count = u32::from_le_bytes(bin.get(at..at + 4)?.try_into().ok()?) as usize;
            at += 4;
            let size = sizes[name].as_u64()? as usize;
            let bytes = bin.get(at..at + count * size)?;
            match name {
                "bsp3d_nodes" => {
                    nodes = bytes
                        .chunks_exact(12)
                        .map(|c| {
                            let i = |k: usize| i32::from_le_bytes(c[k..k + 4].try_into().unwrap());
                            [i(0), i(4), i(8)]
                        })
                        .collect();
                }
                "planes" => {
                    planes = bytes
                        .chunks_exact(16)
                        .map(|c| {
                            let f = |k: usize| f32::from_le_bytes(c[k..k + 4].try_into().unwrap());
                            [f(0), f(4), f(8), f(12)]
                        })
                        .collect();
                }
                _ => {}
            }
            at += count * size;
        }
        (!nodes.is_empty() && !planes.is_empty()).then_some(Collision { nodes, planes })
    }

    /// Whether a glTF-space point (metres) lies in the solid.
    pub fn in_solid(&self, p: V3) -> bool {
        // glTF (x, y, z) is CE (x, -z, y) in world units.
        let q = [p[0] / WU_TO_M, -p[2] / WU_TO_M, p[1] / WU_TO_M];
        let mut node = 0i32;
        for _ in 0..256 {
            if node == -1 {
                return true;
            }
            if node as u32 & 0x8000_0000 != 0 {
                return false;
            }
            let Some(n) = self.nodes.get(node as usize) else { return false };
            let Some(pl) = self.planes.get(n[0] as usize) else { return false };
            let d = pl[0] * q[0] + pl[1] * q[1] + pl[2] * q[2] - pl[3];
            node = if d >= 0.0 { n[2] } else { n[1] };
        }
        false
    }
}
