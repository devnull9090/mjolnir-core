//! Fan-split collision polygons with more than `max` vertices.
//!
//! Every shipped Meteorite definition is triangles and quads (surveyed on
//! `BSP_01_1_Start`: 3,152 + 53, 398 + 26, 46 + 6); classic CE collision
//! carries convex polygons of up to eight. With correct 2D data the simulation
//! reaches those surfaces and dies, so they are split before packing. The
//! winged-edge tables are rewired for the pieces, and each 2D leaf that named
//! the polygon becomes a chain of 2D nodes along the fan's diagonals so a
//! point in the old polygon still resolves to exactly one piece.

use crate::ce::{Bsp2dNode, Collision, Edge, Surface};
use crate::pack16::{node_frames, reference_axes};

const SURFACE_FLAG: u32 = 0x8000_0000;

/// One polygon as the walker sees it: vertex indices and the edge index that
/// carries each step, in loop order.
struct Loop {
    verts: Vec<i32>,
    edges: Vec<usize>,
}

fn walk(c: &Collision, s: usize) -> Option<Loop> {
    let surface = c.surfaces.get(s)?;
    if surface.first_edge < 0 {
        return None;
    }
    let first = surface.first_edge as usize;
    let mut e = first;
    let mut verts = Vec::new();
    let mut edges = Vec::new();
    for _ in 0..256 {
        let edge = c.edges.get(e)?;
        let (v, next) = if edge.left == s as i32 {
            (edge.start, edge.forward)
        } else {
            (edge.end, edge.reverse)
        };
        verts.push(v);
        edges.push(e);
        if next < 0 {
            return None;
        }
        e = next as usize;
        if e == first {
            break;
        }
    }
    Some(Loop { verts, edges })
}

/// Set the next-edge pointer on the side of `edge` that `owner` traverses.
fn set_next(edge: &mut Edge, owner: i32, next: i32, old_owner: i32) {
    if edge.left == old_owner {
        edge.left = owner;
        edge.forward = next;
    } else {
        edge.right = owner;
        edge.reverse = next;
    }
}

/// Append the chain of 2D nodes that splits a fan's pieces along its
/// diagonals, in the projection `(u, w)`, and return its root.
fn fan_chain(c: &mut Collision, v: &[i32], piece: &[i32], (u, w): (usize, usize)) -> i32 {
    let n = v.len();
    let proj = |c: &Collision, vi: i32| -> [f32; 2] {
        let p = c.vertices[vi as usize].point;
        [p[u], p[w]]
    };
    let p0 = proj(c, v[0]);
    // Build from the far end so each node's "rest" child already exists.
    let mut rest: i32 = (SURFACE_FLAG | piece[n - 3] as u32) as i32; // last piece
    for k in (2..=(n - 2)).rev() {
        let pk = proj(c, v[k]);
        let dir = [pk[0] - p0[0], pk[1] - p0[1]];
        let len = (dir[0] * dir[0] + dir[1] * dir[1]).sqrt().max(1e-9);
        let nrm = [dir[1] / len, -dir[0] / len];
        let d = nrm[0] * p0[0] + nrm[1] * p0[1];
        let near = (SURFACE_FLAG | piece[k - 2] as u32) as i32; // piece k-1
        let far_vertex = proj(c, v[k - 1]);
        let side = nrm[0] * far_vertex[0] + nrm[1] * far_vertex[1] - d;
        // Right child is the positive side of the line.
        let (left, right) = if side > 0.0 { (rest, near) } else { (near, rest) };
        let node = c.bsp2d_nodes.len() as i32;
        c.bsp2d_nodes.push(Bsp2dNode {
            plane: [nrm[0], nrm[1], d],
            left,
            right,
        });
        rest = node;
    }
    rest
}

/// Split every polygon with more than `max` vertices. Returns how many were
/// split and how many 2D references/leaves were rewritten.
pub fn fan_split(c: &mut Collision, max: usize) -> (usize, usize) {
    let mut split_count = 0;
    let mut rewired = 0;
    let original_surfaces = c.surfaces.len();

    for s in 0..original_surfaces {
        let Some(lp) = walk(c, s) else { continue };
        let n = lp.verts.len();
        if n <= max {
            continue;
        }
        split_count += 1;
        let template: Surface = c.surfaces[s];
        let v = &lp.verts;
        let e = &lp.edges;

        // Piece k (k = 1..=n-2) is (v0, v_k, v_{k+1}); piece 1 keeps index s.
        let mut piece: Vec<i32> = vec![s as i32];
        for _ in 2..=(n - 2) {
            piece.push(c.surfaces.len() as i32);
            c.surfaces.push(template);
        }
        // Diagonal k (k = 2..=n-2) runs v0 -> v_k; piece k has it on the left,
        // piece k-1 on the right.
        let mut diag: Vec<i32> = vec![-1, -1]; // index by k
        for k in 2..=(n - 2) {
            diag.push(c.edges.len() as i32);
            c.edges.push(Edge {
                start: v[0],
                end: v[k],
                forward: -1,
                reverse: -1,
                left: piece[k - 1],
                right: piece[k - 2],
            });
        }
        let first_edge_of = |k: usize| -> i32 { if k == 1 { e[0] as i32 } else { diag[k] } };
        let closing_edge_of = |k: usize| -> i32 { if k == n - 2 { e[n - 1] as i32 } else { diag[k + 1] } };

        for k in 1..=(n - 2) {
            let p = piece[k - 1];
            let (a, b, cl) = (first_edge_of(k), e[k] as i32, closing_edge_of(k));
            // a -> b -> cl -> a around piece k.
            if k == 1 {
                let old = s as i32;
                set_next(&mut c.edges[a as usize], p, b, old);
            } else {
                // Diagonal a is traversed start->end by piece k: its left side.
                c.edges[a as usize].forward = b;
            }
            set_next(&mut c.edges[b as usize], p, cl, s as i32);
            if k == n - 2 {
                set_next(&mut c.edges[cl as usize], p, a, s as i32);
            } else {
                // Diagonal cl is traversed end->start by piece k: its right side.
                c.edges[cl as usize].reverse = a;
            }
            c.surfaces[p as usize].first_edge = a;
        }

        // The 2D side: a chain of split lines along the diagonals. A 2D tree
        // is read in the frame of the reference that reaches it, and a
        // negated reference swaps the projected axes, so the chain is built
        // once per sign the polygon is reached under, and each reacher is
        // pointed at the chain in its own frame.
        let plane_index = (template.plane as u32 & 0x7fff) as usize;
        let normal = c.planes[plane_index].n;
        let target = (SURFACE_FLAG | s as u32) as i32;
        let frames = node_frames(c);
        let old_nodes = c.bsp2d_nodes.len();
        let mut signs: Vec<bool> = Vec::new();
        for r in &c.bsp2d_references {
            if r.node == target {
                signs.push((r.plane as u32) & SURFACE_FLAG != 0);
            }
        }
        for (i, node) in c.bsp2d_nodes.iter().enumerate() {
            if node.left == target || node.right == target {
                signs.push(frames[i].is_some_and(|f| f.negated));
            }
        }
        signs.sort_unstable();
        signs.dedup();
        if signs.is_empty() {
            signs.push(false);
        }
        let mut roots = [None, None];
        for &negated in &signs {
            roots[negated as usize] = Some(fan_chain(c, v, &piece, reference_axes(normal, negated)));
        }
        let root_for = |negated: bool| roots[negated as usize].or(roots[!negated as usize]).unwrap();
        for r in &mut c.bsp2d_references {
            if r.node == target {
                r.node = root_for((r.plane as u32) & SURFACE_FLAG != 0);
                rewired += 1;
            }
        }
        // 2D nodes that pointed at the old surface (only the nodes that
        // existed before this split can).
        for (i, node) in c.bsp2d_nodes[..old_nodes].iter_mut().enumerate() {
            let negated = frames[i].is_some_and(|f| f.negated);
            if node.left == target {
                node.left = root_for(negated);
                rewired += 1;
            }
            if node.right == target {
                node.right = root_for(negated);
                rewired += 1;
            }
        }
    }
    (split_count, rewired)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ce::{Bsp2dReference, Plane, Vertex};

    /// A pentagon in the z = 0 plane, wound counter-clockwise seen from +z,
    /// as one surface with a closed edge loop.
    fn pentagon() -> Collision {
        let pts = [(1.0, 0.0), (0.31, 0.95), (-0.81, 0.59), (-0.81, -0.59), (0.31, -0.95)];
        let mut c = Collision::default();
        c.planes.push(Plane { n: [0.0, 0.0, 1.0], d: 0.0 });
        for (i, (x, y)) in pts.iter().enumerate() {
            c.vertices.push(Vertex { point: [*x, *y, 0.0], first_edge: i as i32 });
            c.edges.push(Edge {
                start: i as i32,
                end: ((i + 1) % 5) as i32,
                forward: ((i + 1) % 5) as i32,
                reverse: -1,
                left: 0,
                right: -1,
            });
        }
        c.surfaces.push(Surface { plane: 0, first_edge: 0, flags: 0, breakable: -1, material: 0 });
        c
    }

    /// Walk a 2D tree from `node` in the frame of a reference with this sign:
    /// the right child is the positive side of a line.
    fn resolve(c: &Collision, mut node: i32, negated: bool, p: [f32; 3]) -> usize {
        let (u, w) = reference_axes(c.planes[0].n, negated);
        while (node as u32) & SURFACE_FLAG == 0 {
            let n = &c.bsp2d_nodes[node as usize];
            let side = n.plane[0] * p[u] + n.plane[1] * p[w] - n.plane[2];
            node = if side > 0.0 { n.right } else { n.left };
        }
        (node as u32 & !SURFACE_FLAG) as usize
    }

    /// Each piece's centroid, and the surface index the split gave that piece.
    fn centroids(c: &Collision) -> Vec<([f32; 3], usize)> {
        let v = |i: usize| c.vertices[i].point;
        // Piece k (1..=3) is (v0, v_k, v_{k+1}); piece 1 keeps index 0, the
        // others are appended in order.
        (1..=3)
            .map(|k| {
                let (a, b, d) = (v(0), v(k), v(k + 1));
                let m = [(a[0] + b[0] + d[0]) / 3.0, (a[1] + b[1] + d[1]) / 3.0, 0.0];
                (m, if k == 1 { 0 } else { k - 1 })
            })
            .collect()
    }

    #[test]
    fn a_negated_reference_gets_a_chain_in_its_own_frame() {
        let mut c = pentagon();
        c.bsp2d_references.push(Bsp2dReference {
            plane: SURFACE_FLAG as i32,
            node: SURFACE_FLAG as i32,
        });
        assert_eq!(fan_split(&mut c, 4), (1, 1));
        let root = c.bsp2d_references[0].node;
        for (p, piece) in centroids(&c) {
            assert_eq!(resolve(&c, root, true, p), piece, "centroid {p:?}");
        }
    }

    #[test]
    fn a_polygon_reached_under_both_signs_gets_a_chain_for_each() {
        let mut c = pentagon();
        c.bsp2d_references.push(Bsp2dReference { plane: 0, node: SURFACE_FLAG as i32 });
        c.bsp2d_references.push(Bsp2dReference {
            plane: SURFACE_FLAG as i32,
            node: SURFACE_FLAG as i32,
        });
        assert_eq!(fan_split(&mut c, 4), (1, 2));
        assert_eq!(c.bsp2d_nodes.len(), 4, "two diagonals, once per frame");
        let (plain, negated) = (c.bsp2d_references[0].node, c.bsp2d_references[1].node);
        assert_ne!(plain, negated);
        for (p, piece) in centroids(&c) {
            assert_eq!(resolve(&c, plain, false, p), piece, "plain, centroid {p:?}");
            assert_eq!(resolve(&c, negated, true, p), piece, "negated, centroid {p:?}");
        }
    }
}
