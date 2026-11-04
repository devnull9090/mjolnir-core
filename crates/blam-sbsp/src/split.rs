//! Fan-split collision polygons with more than `max` vertices.
//!
//! Every shipped Meteorite definition is triangles and quads (surveyed on
//! `BSP_01_1_Start`: 3,152 + 53, 398 + 26, 46 + 6); classic CE collision
//! carries convex polygons of up to eight. With correct 2D data the simulation
//! reaches those surfaces and dies, so they are split before packing. The
//! winged-edge tables are rewired for the pieces, and each 2D leaf that named
//! the polygon becomes a chain of 2D nodes along the fan's diagonals so a
//! point in the old polygon still resolves to exactly one piece.

use crate::ce::{Bsp2dNode, Bsp2dReference, Bsp3dNode, Collision, Edge, Leaf, Surface, Vertex};
use crate::pack16::projection_axes;
use crate::Error;

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

/// Split every polygon with more than `max` vertices into triangles. Returns
/// how many were split and how many 2D references/leaves were rewritten.
pub fn fan_split(c: &mut Collision, max: usize) -> (usize, usize) {
    fan_split_into(c, max, 3)
}

/// [`fan_split`] into triangles when the result fits the 16-bit tables, into
/// quads (shipped definitions carry those too) when it does not: Coldsnap's
/// BSP is 35,173 surfaces as triangles and 32,257 as quads, under the 32,767
/// limit. Maps that fit split exactly as before.
pub fn fan_split_fit(c: &mut Collision, max: usize) -> (usize, usize) {
    let mut tri = c.clone();
    let r = fan_split(&mut tri, max);
    if tri.fits_16bit().is_ok() || max < 4 {
        *c = tri;
        return r;
    }
    fan_split_into(c, max, 4)
}

/// Split every polygon with more than `max` vertices into a fan of convex
/// pieces of at most `piece` vertices (3 or more), all sharing the polygon's
/// first vertex. Returns how many were split and how many 2D
/// references/leaves were rewritten.
pub fn fan_split_into(c: &mut Collision, max: usize, piece: usize) -> (usize, usize) {
    let piece = piece.max(3);
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

        // Piece j is (v0, v_ks[j], ..., v_ks[j+1]): `piece - 2` fan steps
        // each, the last one whatever is left. Edge e[i] carries v_i -> v_i+1.
        let mut ks = vec![1usize];
        while *ks.last().unwrap() < n - 1 {
            let k = *ks.last().unwrap();
            ks.push((k + piece - 2).min(n - 1));
        }
        let m = ks.len() - 1;
        // Piece 0 keeps index s.
        let mut pieces: Vec<i32> = vec![s as i32];
        for _ in 1..m {
            pieces.push(c.surfaces.len() as i32);
            c.surfaces.push(template);
        }
        // Diagonal j (j = 1..m) runs v0 -> v_ks[j]; piece j has it on the
        // left, piece j-1 on the right.
        let mut diag: Vec<i32> = vec![-1]; // index by j
        for j in 1..m {
            diag.push(c.edges.len() as i32);
            c.edges.push(Edge {
                start: v[0],
                end: v[ks[j]],
                forward: -1,
                reverse: -1,
                left: pieces[j],
                right: pieces[j - 1],
            });
        }

        for j in 0..m {
            let p = pieces[j];
            let opening = if j == 0 { e[0] as i32 } else { diag[j] };
            let closing = if j == m - 1 {
                e[n - 1] as i32
            } else {
                diag[j + 1]
            };
            // opening -> e[ks[j]] .. e[ks[j+1]-1] -> closing -> opening.
            let mut seq = vec![opening];
            seq.extend((ks[j]..ks[j + 1]).map(|i| e[i] as i32));
            seq.push(closing);
            for (q, &edge) in seq.iter().enumerate() {
                let next = seq[(q + 1) % seq.len()];
                if j > 0 && q == 0 {
                    // Diagonal j, traversed start->end by piece j: its left side.
                    c.edges[edge as usize].forward = next;
                } else if j + 1 < m && q == seq.len() - 1 {
                    // Diagonal j+1, traversed end->start by piece j: its right side.
                    c.edges[edge as usize].reverse = next;
                } else {
                    set_next(&mut c.edges[edge as usize], p, next, s as i32);
                }
            }
            c.surfaces[p as usize].first_edge = opening;
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
        let mut rest: i32 = (SURFACE_FLAG | pieces[m - 1] as u32) as i32; // last piece
        for j in (1..m).rev() {
            let pk = proj(v[ks[j]]);
            let dir = [pk[0] - p0[0], pk[1] - p0[1]];
            let len = (dir[0] * dir[0] + dir[1] * dir[1]).sqrt().max(1e-9);
            let nrm = [dir[1] / len, -dir[0] / len];
            let d = nrm[0] * p0[0] + nrm[1] * p0[1];
            let near = (SURFACE_FLAG | pieces[j - 1] as u32) as i32;
            // A vertex of piece j-1 off the diagonal.
            let far_vertex = proj(v[ks[j] - 1]);
            let side = nrm[0] * far_vertex[0] + nrm[1] * far_vertex[1] - d;
            // Right child is the positive side of the line.
            let (left, right) = if side > 0.0 {
                (rest, near)
            } else {
                (near, rest)
            };
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
        let new_from = c.bsp2d_nodes.len() - (m - 1);
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

/// Move the standalone surfaces `first..` out of `c` into collisions of at
/// most `max` surfaces each.
///
/// They are the scenery `tools/level/merge_ce_collision.py` appends after a
/// staged BSP's own surfaces: polygons the BSP tree never reaches, each with
/// its own plane, edge ring and vertices, appended after the BSP's. Havok
/// reaches them through a MOPP over the surfaces; projectiles walk the tree,
/// so each piece gets one in which every point is open space and every
/// surface is reachable ([`crate::scenery::link`]). (A child of "none" is
/// solid: pieces built that way put the whole map inside solid scenery, and
/// every player who moved was killed by the guardians, Danger Canyon
/// 2026-10-01.) A piece whose tree would overflow the 16-bit tables takes
/// fewer surfaces. What stays in `c` is the BSP as staged, its tables cut back
/// to what its own tree and surfaces use. Fails if the surfaces are not such
/// a tail.
pub fn split_standalone(
    c: &mut Collision,
    first: usize,
    max: usize,
) -> Result<Vec<Collision>, Error> {
    let total = c.surfaces.len();
    if first > total || max == 0 {
        return Err(Error::Staging(format!(
            "no standalone surfaces from {first} of {total}"
        )));
    }
    let mut loops = Vec::with_capacity(total - first);
    for s in first..total {
        let l = walk(c, s).ok_or_else(|| {
            Error::Staging(format!("standalone surface {s} has no closed edge ring"))
        })?;
        loops.push(l);
    }

    // Where the tail starts in each table: the lowest index any standalone
    // surface uses.
    let plane_of = |p: i32| (p as u32 & 0x7fff_ffff) as usize;
    let cut_planes = c.surfaces[first..]
        .iter()
        .map(|s| plane_of(s.plane))
        .min()
        .unwrap_or(c.planes.len());
    let cut_edges = loops
        .iter()
        .flat_map(|l| l.edges.iter().copied())
        .min()
        .unwrap_or(c.edges.len());
    let cut_vertices = loops
        .iter()
        .flat_map(|l| l.verts.iter().map(|&v| v as usize))
        .min()
        .unwrap_or(c.vertices.len());

    // What the BSP itself uses must sit below the cuts.
    let max_plane = c
        .bsp3d_nodes
        .iter()
        .map(|n| plane_of(n.plane))
        .chain(c.bsp2d_references.iter().map(|r| plane_of(r.plane)))
        .chain(c.surfaces[..first].iter().map(|s| plane_of(s.plane)))
        .max();
    let max_edge = c.surfaces[..first]
        .iter()
        .map(|s| s.first_edge.max(0) as usize)
        .chain(
            c.edges[..cut_edges.min(c.edges.len())]
                .iter()
                .flat_map(|e| [e.forward, e.reverse])
                .filter(|&e| e >= 0)
                .map(|e| e as usize),
        )
        .max();
    let max_vertex = c.edges[..cut_edges.min(c.edges.len())]
        .iter()
        .flat_map(|e| [e.start, e.end])
        .filter(|&v| v >= 0)
        .map(|v| v as usize)
        .max();
    if max_plane.is_some_and(|p| p >= cut_planes)
        || max_edge.is_some_and(|e| e >= cut_edges)
        || max_vertex.is_some_and(|v| v >= cut_vertices)
    {
        return Err(Error::Staging(format!(
            "surfaces {first}..{total} are not a standalone tail (planes from {cut_planes}, edges from {cut_edges}, vertices from {cut_vertices})"
        )));
    }
    let items: Vec<(Surface, &Loop)> = c.surfaces[first..].iter().copied().zip(&loops).collect();
    let pieces = pieces_of(c, &items, max)?;
    c.surfaces.truncate(first);
    c.planes.truncate(cut_planes);
    c.edges.truncate(cut_edges);
    c.vertices.truncate(cut_vertices);
    Ok(pieces)
}

/// Every surface a tree child reaches, through its leaves' 2D references.
fn surfaces_under(c: &Collision, child: i32, out: &mut std::collections::BTreeSet<usize>) {
    fn in_2d(c: &Collision, node: i32, out: &mut std::collections::BTreeSet<usize>) {
        if node == -1 {
        } else if node < 0 {
            out.insert((node as u32 & !SURFACE_FLAG) as usize);
        } else if let Some(n) = c.bsp2d_nodes.get(node as usize) {
            in_2d(c, n.left, out);
            in_2d(c, n.right, out);
        }
    }
    let mut work = vec![child];
    while let Some(k) = work.pop() {
        if k == -1 {
        } else if k < 0 {
            let leaf = c.leaves[(k as u32 & !SURFACE_FLAG) as usize];
            let first = leaf.first_reference.max(0) as usize;
            for r in &c.bsp2d_references[first..first + leaf.reference_count.max(0) as usize] {
                in_2d(c, r.node, out);
            }
        } else {
            let n = c.bsp3d_nodes[k as usize];
            work.extend([n.front, n.back]);
        }
    }
}

/// `c` with only what its tree reaches from the root: the leaves' references,
/// the 2D nodes and surfaces under them and those surfaces' edges. Vertices
/// stay, so the BSP's bounds do, and the shell still calls the region a cut
/// took inside the world. An edge a dropped surface shared loses that side.
fn compact(c: &Collision) -> Collision {
    use std::collections::BTreeMap;
    fn copy_2d(
        c: &Collision,
        node: i32,
        surface: &BTreeMap<usize, i32>,
        out: &mut Vec<Bsp2dNode>,
    ) -> i32 {
        if node == -1 {
            -1
        } else if node < 0 {
            (SURFACE_FLAG | surface[&((node as u32 & !SURFACE_FLAG) as usize)] as u32) as i32
        } else {
            let n = c.bsp2d_nodes[node as usize];
            let at = out.len();
            out.push(n);
            let (left, right) = (
                copy_2d(c, n.left, surface, out),
                copy_2d(c, n.right, surface, out),
            );
            (out[at].left, out[at].right) = (left, right);
            at as i32
        }
    }
    let mut used = std::collections::BTreeSet::new();
    surfaces_under(c, 0, &mut used);
    let surface: BTreeMap<usize, i32> = used
        .iter()
        .enumerate()
        .map(|(i, &s)| (s, i as i32))
        .collect();
    let mut edge: BTreeMap<usize, i32> = BTreeMap::new();
    for &s in &used {
        if let Some(l) = walk(c, s) {
            for e in l.edges {
                let next = edge.len() as i32;
                edge.entry(e).or_insert(next);
            }
        }
    }
    let mut out = Collision {
        bsp3d_nodes: c.bsp3d_nodes.clone(),
        planes: c.planes.clone(),
        leaves: c.leaves.clone(),
        vertices: c.vertices.clone(),
        ..Default::default()
    };
    // The leaves the tree still reaches keep their references; the rest empty.
    let mut reached = vec![false; c.leaves.len()];
    let mut work = vec![0i32];
    while let Some(k) = work.pop() {
        if k == -1 {
        } else if k < 0 {
            reached[(k as u32 & !SURFACE_FLAG) as usize] = true;
        } else {
            let n = c.bsp3d_nodes[k as usize];
            work.extend([n.front, n.back]);
        }
    }
    for (l, leaf) in out.leaves.iter_mut().enumerate() {
        let (first, count) = (
            leaf.first_reference.max(0) as usize,
            leaf.reference_count.max(0) as usize,
        );
        leaf.first_reference = out.bsp2d_references.len() as i32;
        if !reached[l] {
            leaf.reference_count = 0;
            continue;
        }
        for r in &c.bsp2d_references[first..first + count] {
            let node = copy_2d(c, r.node, &surface, &mut out.bsp2d_nodes);
            out.bsp2d_references.push(Bsp2dReference {
                plane: r.plane,
                node,
            });
        }
    }
    let side = |s: i32| {
        surface
            .get(&(s.max(0) as usize))
            .copied()
            .filter(|_| s >= 0)
            .unwrap_or(-1)
    };
    let link = |e: i32| {
        edge.get(&(e.max(0) as usize))
            .copied()
            .filter(|_| e >= 0)
            .unwrap_or(-1)
    };
    out.edges = vec![c.edges[0]; edge.len()];
    for (&old, &new) in &edge {
        let e = c.edges[old];
        out.edges[new as usize] = Edge {
            forward: link(e.forward),
            reverse: link(e.reverse),
            left: side(e.left),
            right: side(e.right),
            ..e
        };
    }
    out.surfaces = used
        .iter()
        .map(|&s| Surface {
            first_edge: link(c.surfaces[s].first_edge),
            ..c.surfaces[s]
        })
        .collect();
    for v in &mut out.vertices {
        v.first_edge = link(v.first_edge).max(0);
    }
    out
}

/// Bring a BSP too big for the 16-bit tables under them: cut subtrees out of
/// `c` until `fits` holds, each cut region becoming open space, and return the
/// surfaces that left as standalone pieces of at most `max` surfaces, which
/// have trees of their own as scenery does. Precipice and Sanctuary Final are
/// 37,000 to 40,000 surfaces against a limit of 32,767.
///
/// A piece's surfaces are two-sided: nothing behind them is solid any more,
/// so a player meets them as a shell through the MOPP and a bullet through
/// the tree. A surface another leaf still reaches stays in the BSP as well.
pub fn shed(
    c: &mut Collision,
    max: usize,
    fits: impl Fn(&Collision) -> bool,
) -> Result<Vec<Collision>, Error> {
    let mut pieces = Vec::new();
    while !fits(c) {
        let total = c.surfaces.len();
        // A sixth of the BSP at a time: enough to clear an overflow of a few
        // thousand surfaces in one or two cuts, with room for the edges.
        let want = (total / 6).max(1);
        let (mut parent, mut front);
        parent = 0usize;
        loop {
            let n = c.bsp3d_nodes[parent];
            let count = |k: i32| {
                let mut s = std::collections::BTreeSet::new();
                surfaces_under(c, k, &mut s);
                s.len()
            };
            let (f, b) = (count(n.front), count(n.back));
            front = f >= b;
            let (bigger, child) = if front { (f, n.front) } else { (b, n.back) };
            if child < 0 || bigger / 2 < want {
                break;
            }
            parent = child as usize;
        }
        let open = c.leaves.len() as u32;
        c.leaves.push(Leaf {
            flags: 0,
            reference_count: 0,
            first_reference: 0,
        });
        let before = c.clone();
        let node = &mut c.bsp3d_nodes[parent];
        if front {
            node.front = leaf_child(open);
        } else {
            node.back = leaf_child(open);
        }
        let mut kept = std::collections::BTreeSet::new();
        surfaces_under(c, 0, &mut kept);
        let mut loops = Vec::new();
        for s in (0..total).filter(|s| !kept.contains(s)) {
            if let Some(l) = walk(&before, s) {
                loops.push((
                    Surface {
                        flags: before.surfaces[s].flags | 1,
                        ..before.surfaces[s]
                    },
                    l,
                ));
            }
        }
        if loops.is_empty() {
            return Err(Error::Staging("a cut freed no surfaces".into()));
        }
        let items: Vec<(Surface, &Loop)> = loops.iter().map(|(s, l)| (*s, l)).collect();
        pieces.extend(pieces_of(&before, &items, max)?);
        *c = compact(c);
    }
    Ok(pieces)
}

/// Leaf `l` as a bsp3d child (`0x8000_0000 | leaf`).
const fn leaf_child(l: u32) -> i32 {
    (0x8000_0000 | l) as i32
}

/// One piece holding `items` (surfaces of `c` and their edge loops), with a
/// tree that reaches every one: a root on the first surface's plane between
/// two open leaves, and each surface linked in from there.
fn piece_of(c: &Collision, items: &[(Surface, &Loop)]) -> Collision {
    let plane_of = |p: i32| (p as u32 & 0x7fff_ffff) as usize;
    let mut piece = Collision {
        bsp3d_nodes: vec![Bsp3dNode {
            plane: 0,
            back: leaf_child(0),
            front: leaf_child(1),
        }],
        leaves: vec![
            Leaf {
                flags: 0,
                reference_count: 0,
                first_reference: 0,
            };
            2
        ],
        ..Default::default()
    };
    for (s, l) in items {
        let surface = piece.surfaces.len() as i32;
        let plane = piece.planes.len() as i32;
        piece.planes.push(c.planes[plane_of(s.plane)]);
        let (v0, e0, n) = (
            piece.vertices.len() as i32,
            piece.edges.len() as i32,
            l.verts.len() as i32,
        );
        for (j, &v) in l.verts.iter().enumerate() {
            piece.vertices.push(Vertex {
                point: c.vertices[v as usize].point,
                first_edge: e0 + j as i32,
            });
        }
        for j in 0..n {
            // A ring walked from the surface's left, as the merge writes it.
            piece.edges.push(Edge {
                start: v0 + j,
                end: v0 + (j + 1) % n,
                forward: e0 + (j + 1) % n,
                reverse: -1,
                left: surface,
                right: -1,
            });
        }
        piece.surfaces.push(Surface {
            plane: plane | (s.plane & i32::MIN),
            first_edge: e0,
            ..*s
        });
    }
    crate::scenery::link(&mut piece, 0);
    piece
}

/// Build `items` into pieces of at most `max` surfaces, in order, each as
/// full as its tree lets it be: a piece whose tree overflows the 16-bit
/// tables takes the longest run that fits, found by bisection to within
/// 1/32. (Linked, Danger Canyon's trees take ~28 2D references a triangle,
/// so the reference table, not the surface count, sets a piece's size.)
fn pieces_of(
    c: &Collision,
    items: &[(Surface, &Loop)],
    max: usize,
) -> Result<Vec<Collision>, Error> {
    let mut out = Vec::new();
    let mut rest = items;
    while !rest.is_empty() {
        let n = rest.len().min(max);
        let piece = piece_of(c, &rest[..n]);
        let (piece, n) = match piece.fits_16bit() {
            Ok(()) => (piece, n),
            Err(why) => {
                // `lo` surfaces fit (its piece is `best`), `hi` do not.
                let (mut lo, mut hi, mut best) = (0, n, None);
                while hi - lo > (hi / 32).max(1) {
                    let mid = (lo + hi) / 2;
                    let p = piece_of(c, &rest[..mid]);
                    if p.fits_16bit().is_ok() {
                        (lo, best) = (mid, Some(p));
                    } else {
                        hi = mid;
                    }
                }
                match best {
                    Some(p) => (p, lo),
                    None if hi == 1 => return Err(why),
                    None => {
                        let p = piece_of(c, &rest[..1]);
                        p.fits_16bit()?;
                        (p, 1)
                    }
                }
            }
        };
        out.push(piece);
        rest = &rest[n..];
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ce::Plane;

    /// A one-triangle BSP with two standalone triangles after it.
    fn with_tail() -> Collision {
        let mut c = Collision::default();
        for k in 0..3 {
            let base = c.vertices.len() as i32;
            let e0 = c.edges.len() as i32;
            let s = c.surfaces.len() as i32;
            c.planes.push(Plane {
                n: [0.0, 0.0, 1.0],
                d: k as f32,
            });
            for j in 0..3 {
                c.vertices.push(Vertex {
                    point: [j as f32, (j % 2) as f32, k as f32],
                    first_edge: e0 + j,
                });
                c.edges.push(Edge {
                    start: base + j,
                    end: base + (j + 1) % 3,
                    forward: e0 + (j + 1) % 3,
                    reverse: -1,
                    left: s,
                    right: -1,
                });
            }
            c.surfaces.push(Surface {
                plane: k,
                first_edge: e0,
                flags: 1,
                breakable: -1,
                material: k as i16,
            });
        }
        c.bsp3d_nodes.push(Bsp3dNode {
            plane: 0,
            back: -1,
            front: -1,
        });
        c
    }

    #[test]
    fn the_tail_moves_out_in_pieces() {
        let mut c = with_tail();
        let pieces = split_standalone(&mut c, 1, 1).unwrap();
        assert_eq!(
            (
                c.surfaces.len(),
                c.planes.len(),
                c.edges.len(),
                c.vertices.len()
            ),
            (1, 1, 3, 3)
        );
        assert_eq!(pieces.len(), 2);
        let p = &pieces[1];
        assert_eq!(
            (
                p.surfaces.len(),
                p.planes.len(),
                p.edges.len(),
                p.vertices.len()
            ),
            (1, 1, 3, 3)
        );
        assert_eq!(p.surfaces[0].material, 2);
        assert_eq!(p.planes[0].d, 2.0);
        assert_eq!(p.vertices[0].point, [0.0, 0.0, 2.0]);
        // Open space on both sides of the root, on the surface's plane:
        // never solid, and the surface is named from both leaves, positive
        // in front and negated behind.
        assert_eq!(
            (p.bsp3d_nodes[0].back, p.bsp3d_nodes[0].front),
            (leaf_child(0), leaf_child(1))
        );
        assert_eq!(p.leaves.len(), 2);
        let names = |l: usize| {
            let lf = p.leaves[l];
            assert_eq!(lf.flags & 1, 1);
            p.bsp2d_references[lf.first_reference as usize..][..lf.reference_count as usize]
                .iter()
                .map(|r| (r.plane as u32, r.node as u32))
                .collect::<Vec<_>>()
        };
        assert_eq!(names(0), vec![(0x8000_0000, 0x8000_0000)]);
        assert_eq!(names(1), vec![(0, 0x8000_0000)]);
        assert!(p.fits_16bit().is_ok());
    }

    /// A ray through a piece's triangle hits it, from either side; beside
    /// it, nothing.
    #[test]
    fn a_ray_meets_scenery_in_its_piece() {
        use crate::scenery::tests::{add_polygon, ray};
        let mut c = with_tail();
        add_polygon(
            &mut c,
            &[[5.0, 0.0, 0.0], [5.0, 1.0, 0.0], [5.0, 0.0, 1.0]],
            1,
        );
        let pieces = split_standalone(&mut c, 1, 8).unwrap();
        assert_eq!(pieces.len(), 1);
        let p = &pieces[0];
        let hit = ray(p, [4.0, 0.2, 0.2], [6.0, 0.2, 0.2]).expect("hit");
        assert_eq!(hit.surface, 2);
        assert!((hit.t - 0.5).abs() < 1e-4);
        assert_eq!(
            ray(p, [6.0, 0.2, 0.2], [4.0, 0.2, 0.2]).map(|h| h.surface),
            Some(2)
        );
        assert!(ray(p, [4.0, 0.9, 0.9], [6.0, 0.9, 0.9]).is_none());
        // Down through the flat triangles at z 1 and 2.
        let hit = ray(p, [0.9, 0.5, 3.0], [0.9, 0.5, -1.0]).expect("down");
        assert_eq!(hit.surface, 1);
    }

    #[test]
    fn surfaces_the_tree_uses_are_not_a_tail() {
        let mut c = with_tail();
        c.bsp3d_nodes[0].plane = 2;
        assert!(split_standalone(&mut c, 1, 8).is_err());
    }

    /// One convex octagon on z = 0, as a leaf's only 2D reference.
    fn octagon() -> Collision {
        use crate::ce::Bsp2dReference;
        let mut c = Collision::default();
        c.planes.push(Plane {
            n: [0.0, 0.0, 1.0],
            d: 0.0,
        });
        for i in 0..8 {
            let a = i as f32 * std::f32::consts::TAU / 8.0;
            c.vertices.push(Vertex {
                point: [10.0 * a.cos(), 10.0 * a.sin(), 0.0],
                first_edge: i,
            });
            c.edges.push(Edge {
                start: i,
                end: (i + 1) % 8,
                forward: (i + 1) % 8,
                reverse: -1,
                left: 0,
                right: -1,
            });
        }
        c.surfaces.push(Surface {
            plane: 0,
            first_edge: 0,
            flags: 0,
            breakable: -1,
            material: 0,
        });
        c.bsp2d_references.push(Bsp2dReference {
            plane: 0,
            node: SURFACE_FLAG as i32,
        });
        c.leaves.push(Leaf {
            flags: 0,
            reference_count: 1,
            first_reference: 0,
        });
        c
    }

    /// Every piece is a closed loop of at most `piece` vertices, and the 2D
    /// chain sends each piece's centroid to that piece.
    fn check_fan(piece: usize, expect: usize) {
        let mut c = octagon();
        assert_eq!(fan_split_into(&mut c, 4, piece), (1, 1));
        assert_eq!(c.surfaces.len(), expect);
        let mut corners = 0;
        for s in 0..c.surfaces.len() {
            let lp = walk(&c, s).expect("closed loop");
            assert!(
                lp.verts.len() >= 3 && lp.verts.len() <= piece,
                "piece {s}: {:?}",
                lp.verts
            );
            corners += lp.verts.len();
            let mut m = [0.0f32; 3];
            for &v in &lp.verts {
                for k in 0..3 {
                    m[k] += c.vertices[v as usize].point[k] / lp.verts.len() as f32;
                }
            }
            assert_eq!(
                crate::raytest::leaf_surface(&c, 0, 0, m),
                Some(s),
                "centroid of piece {s}"
            );
        }
        // n + 2 * diagonals corners in all.
        assert_eq!(corners, 8 + 2 * (expect - 1));
    }

    #[test]
    fn an_octagon_fans_into_triangles() {
        check_fan(3, 6);
    }

    #[test]
    fn an_octagon_fans_into_quads() {
        check_fan(4, 3);
    }
}

#[cfg(test)]
mod shed_tests {
    use super::*;
    use crate::ce::Plane;

    /// Two triangles, one in each of a root's leaves.
    fn two_leaves() -> Collision {
        let mut c = Collision::default();
        c.planes.push(Plane {
            n: [1.0, 0.0, 0.0],
            d: 0.0,
        });
        for k in 0..2 {
            let (s, v0, e0) = (k as i32, c.vertices.len() as i32, c.edges.len() as i32);
            let x = if k == 0 { 1.0 } else { -1.0 };
            for j in 0..3 {
                c.vertices.push(Vertex {
                    point: [x, j as f32, (j % 2) as f32],
                    first_edge: e0 + j,
                });
                c.edges.push(Edge {
                    start: v0 + j,
                    end: v0 + (j + 1) % 3,
                    forward: e0 + (j + 1) % 3,
                    reverse: -1,
                    left: s,
                    right: -1,
                });
            }
            c.surfaces.push(Surface {
                plane: 0,
                first_edge: e0,
                flags: 0,
                breakable: -1,
                material: k as i16,
            });
            c.bsp2d_references.push(Bsp2dReference {
                plane: 0,
                node: (SURFACE_FLAG | k as u32) as i32,
            });
            c.leaves.push(Leaf {
                flags: 0,
                reference_count: 1,
                first_reference: k as i32,
            });
        }
        c.bsp3d_nodes.push(Bsp3dNode {
            plane: 0,
            front: leaf_child(0),
            back: leaf_child(1),
        });
        c
    }

    #[test]
    fn a_cut_leaves_open_space_and_a_two_sided_piece() {
        let mut c = two_leaves();
        let pieces = shed(&mut c, 8, |c| c.surfaces.len() < 2).unwrap();
        assert_eq!(c.surfaces.len(), 1);
        assert_eq!(c.edges.len(), 3);
        assert_eq!(c.bsp2d_references.len(), 1);
        assert_eq!(c.vertices.len(), 6, "the bounds stay");
        assert!(walk(&c, 0).is_some());
        assert_eq!(pieces.len(), 1);
        assert_eq!(pieces[0].surfaces.len(), 1);
        assert_eq!(pieces[0].surfaces[0].flags & 1, 1);
        let n = c.bsp3d_nodes[0];
        let leaf = |k: i32| c.leaves[(k as u32 & !SURFACE_FLAG) as usize];
        let (kept, open) = if leaf(n.front).reference_count == 1 {
            (n.front, n.back)
        } else {
            (n.back, n.front)
        };
        assert_eq!(leaf(kept).first_reference, 0);
        assert_eq!(leaf(open).reference_count, 0);
    }

    #[test]
    fn a_bsp_that_fits_is_untouched() {
        let mut c = two_leaves();
        assert!(shed(&mut c, 8, |_| true).unwrap().is_empty());
        assert_eq!(c.surfaces.len(), 2);
    }
}
