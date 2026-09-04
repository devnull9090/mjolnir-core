//! Read a world shell back out of an `sbsp` payload and check it hangs
//! together: every reference in range, every surface an edge loop that closes,
//! every leaf reachable from the tree. The mirror of `pack16`, run on the
//! bytes that will ship rather than on the structs that produced them.

use blam_tag::blockedit::find_block;

use crate::pack16::{LEAF24, NONE24};
use crate::transplant::SHELL;
use crate::Error;

#[derive(Debug, Clone, Default)]
pub struct Report {
    pub nodes: usize,
    pub supernodes: usize,
    pub planes: usize,
    pub leaves: usize,
    pub bsp2d_references: usize,
    pub bsp2d_nodes: usize,
    pub surfaces: usize,
    pub edges: usize,
    pub vertices: usize,
    /// Closed edge loops with at least three vertices.
    pub polygons: usize,
    pub triangles: usize,
    /// Node indices no other node references (subtree roots).
    pub roots: Vec<usize>,
    pub leaves_referenced: usize,
    pub bounds: Option<([f32; 3], [f32; 3])>,
    pub problems: Vec<String>,
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

/// Validate the world shell of `file`.
pub fn shell(file: &[u8]) -> Result<Report, Error> {
    at(file, SHELL)
}

/// Validate the collision tables under `base` — the world shell, or an
/// instanced-geometry definition's `collision info`, which has the same shape.
pub fn at(file: &[u8], base: &str) -> Result<Report, Error> {
    let tag = blam_tag::TagFile::parse(file, None).map_err(|e| Error::Other(e.to_string()))?;
    let layout = tag.layout().map_err(|e| Error::Other(e.to_string()))?;
    let root = tag
        .read_data(&layout)
        .map_err(|e| Error::Other(e.to_string()))?;
    let get = |name: &str| -> Result<(&[u8], usize, usize), Error> {
        let f = find_block(&layout, file, &root, &format!("{base}.{name}"))?;
        Ok((
            f.block.elements,
            f.block.count as usize,
            f.block.element_size as usize,
        ))
    };
    let (nodes, n_nodes, _) = get("bsp3d nodes")?;
    let (_supers, n_supers, _) = get("bsp3d supernodes")?;
    let (_planes, n_planes, _) = get("planes")?;
    let (leaves, n_leaves, _) = get("leaves")?;
    let (refs, n_refs, _) = get("bsp2d references")?;
    let (n2d, n_2d, _) = get("bsp2d nodes")?;
    let (surfaces, n_surfaces, ss) = get("surfaces")?;
    let (edges, n_edges, es) = get("edges")?;
    let (vertices, n_vertices, vs) = get("vertices")?;

    let mut r = Report {
        nodes: n_nodes,
        supernodes: n_supers,
        planes: n_planes,
        leaves: n_leaves,
        bsp2d_references: n_refs,
        bsp2d_nodes: n_2d,
        surfaces: n_surfaces,
        edges: n_edges,
        vertices: n_vertices,
        ..Default::default()
    };
    let mut problem = |s: String| r.problems.push(s);

    // Tree: every child in range; count references.
    let mut node_refs = vec![0u32; n_nodes];
    let mut leaf_refs = vec![0u32; n_leaves];
    for i in 0..n_nodes {
        let w = u64::from_le_bytes(nodes[i * 8..i * 8 + 8].try_into().unwrap());
        let plane = (w & 0xffff) as usize;
        if plane >= n_planes {
            problem(format!("node {i}: plane {plane} out of range"));
        }
        for child in [
            ((w >> 16) & 0xff_ffff) as u32,
            ((w >> 40) & 0xff_ffff) as u32,
        ] {
            if child == NONE24 {
                continue;
            }
            if child & LEAF24 != 0 {
                let l = (child & 0x7f_ffff) as usize;
                if l >= n_leaves {
                    problem(format!("node {i}: leaf {l} out of range"));
                } else {
                    leaf_refs[l] += 1;
                }
            } else if (child as usize) >= n_nodes {
                problem(format!("node {i}: child node {child} out of range"));
            } else {
                node_refs[child as usize] += 1;
            }
        }
    }
    r.roots = (0..n_nodes).filter(|&i| node_refs[i] == 0).collect();
    r.leaves_referenced = leaf_refs.iter().filter(|&&c| c > 0).count();
    if let Some(i) = (0..n_nodes).find(|&i| node_refs[i] > 1) {
        problem(format!("node {i} referenced {} times", node_refs[i]));
    }
    if let Some(l) = (0..n_leaves).find(|&l| leaf_refs[l] != 1) {
        problem(format!("leaf {l} referenced {} times", leaf_refs[l]));
    }

    // Leaves → references → 2D nodes / surfaces.
    for l in 0..n_leaves {
        let b = &leaves[l * 8..l * 8 + 8];
        let count = u16_at(b, 2) as usize;
        let first = u32_at(b, 4) as usize;
        // An empty leaf carries `first = -1`, in shipped and CE data alike.
        if count > 0 && first + count > n_refs {
            problem(format!(
                "leaf {l}: references {first}+{count} exceed {n_refs}"
            ));
        }
    }
    let check_2d = |v: i16, what: &str, problem: &mut dyn FnMut(String)| {
        if v < 0 {
            let s = (v as u16 & 0x7fff) as usize;
            if s >= n_surfaces {
                problem(format!("{what}: surface {s} out of range"));
            }
        } else if v as usize >= n_2d {
            problem(format!("{what}: bsp2d node {v} out of range"));
        }
    };
    for i in 0..n_refs {
        let b = &refs[i * 4..i * 4 + 4];
        let plane = (i16_at(b, 0) as u16 & 0x7fff) as usize;
        if plane >= n_planes {
            problem(format!("bsp2d reference {i}: plane {plane} out of range"));
        }
        check_2d(i16_at(b, 2), &format!("bsp2d reference {i}"), &mut problem);
    }
    for i in 0..n_2d {
        let b = &n2d[i * 16..i * 16 + 16];
        check_2d(i16_at(b, 12), &format!("bsp2d node {i} left"), &mut problem);
        check_2d(
            i16_at(b, 14),
            &format!("bsp2d node {i} right"),
            &mut problem,
        );
    }

    // Surfaces: walk the edge loop.
    let none = u16::MAX;
    for s in 0..n_surfaces {
        let b = &surfaces[s * ss..s * ss + ss];
        let plane = u16_at(b, 0) as usize;
        if plane >= n_planes {
            problem(format!("surface {s}: plane {plane} out of range"));
        }
        let first = u16_at(b, 2);
        if first == none {
            continue;
        }
        let mut cursor = first;
        let mut verts = 0usize;
        for _ in 0..256 {
            if cursor as usize >= n_edges {
                problem(format!("surface {s}: edge {cursor} out of range"));
                break;
            }
            let e = &edges[cursor as usize * es..cursor as usize * es + es];
            let (start, end, fwd, rev, left, _right) = (
                u16_at(e, 0),
                u16_at(e, 2),
                u16_at(e, 4),
                u16_at(e, 6),
                u16_at(e, 8),
                u16_at(e, 10),
            );
            let v = if left as usize == s { start } else { end };
            if v as usize >= n_vertices {
                problem(format!("surface {s}: vertex {v} out of range"));
                break;
            }
            verts += 1;
            cursor = if left as usize == s { fwd } else { rev };
            if cursor == first || cursor == none {
                break;
            }
        }
        if cursor != first {
            problem(format!("surface {s}: edge loop does not close"));
        } else if verts >= 3 {
            r.polygons += 1;
            r.triangles += verts - 2;
        }
    }

    // Vertex bounds.
    if n_vertices > 0 {
        let p = |i: usize| {
            let b = &vertices[i * vs..i * vs + vs];
            [f32_at(b, 0), f32_at(b, 4), f32_at(b, 8)]
        };
        let mut min = p(0);
        let mut max = p(0);
        for i in 1..n_vertices {
            let q = p(i);
            for a in 0..3 {
                min[a] = min[a].min(q[a]);
                max[a] = max[a].max(q[a]);
            }
        }
        r.bounds = Some((min, max));
    }
    Ok(r)
}
