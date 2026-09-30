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
use crate::pack16::projection_axes;

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

        // The 2D side: a chain of split lines along the diagonals, in the
        // parent plane's projection.
        let plane_index = (template.plane as u32 & 0x7fff) as usize;
        let (u, w) = projection_axes(c.planes[plane_index].n);
        let proj = |vi: i32| -> [f32; 2] {
            let p = c.vertices[vi as usize].point;
            [p[u], p[w]]
        };
        let p0 = proj(v[0]);
        // Build from the far end so each node's "rest" child already exists.
        let mut rest: i32 = (SURFACE_FLAG | piece[n - 3] as u32) as i32; // last piece
        for k in (2..=(n - 2)).rev() {
            let pk = proj(v[k]);
            let dir = [pk[0] - p0[0], pk[1] - p0[1]];
            let len = (dir[0] * dir[0] + dir[1] * dir[1]).sqrt().max(1e-9);
            let nrm = [dir[1] / len, -dir[0] / len];
            let d = nrm[0] * p0[0] + nrm[1] * p0[1];
            let near = (SURFACE_FLAG | piece[k - 2] as u32) as i32; // piece k-1
            let far_vertex = proj(v[k - 1]);
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
        let root = rest;
        let target = (SURFACE_FLAG | s as u32) as i32;
        for r in &mut c.bsp2d_references {
            if r.node == target {
                r.node = root;
                rewired += 1;
            }
        }
        // 2D nodes that pointed at the old surface (only the nodes that
        // existed before this split can).
        let new_from = c.bsp2d_nodes.len() - (n - 3);
        for node in c.bsp2d_nodes[..new_from].iter_mut() {
            if node.left == target {
                node.left = root;
                rewired += 1;
            }
            if node.right == target {
                node.right = root;
                rewired += 1;
            }
        }
    }
    (split_count, rewired)
}
