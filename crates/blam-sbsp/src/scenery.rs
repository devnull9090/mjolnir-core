//! Put standalone two-sided surfaces (CE scenery collision) into a BSP's
//! bsp3d tree, so line tests that walk the tree — projectiles — meet them.
//!
//! `tools/level/merge_ce_collision.py` appends each scenery triangle as a
//! surface no leaf references. The structure's Havok MOPP keys every surface,
//! so players and vehicles stop at them, but a bullet walks the tree and went
//! straight through the Covenant shields on Danger Canyon, Gephyrophobia and
//! Rat Race (playtest 2026-10-03, issue 5).
//!
//! The simulation's line test (`fn_2eb3d0`, CU4, `docs/re/collision_bsp`)
//! checks a surface on the plane it crosses between two OPEN leaves only when
//! both leaves carry flag bit 0 ("contains two-sided surfaces"). It then looks
//! for a 2D reference on that plane in the leaf the ray left, takes it only
//! when the reference's sign matches the direction of travel (no sign: moving
//! against the plane's normal, from its front), and tests the point against
//! the surface polygon. Classic CE data follows that: every node between two
//! flagged leaves that carries a two-sided surface has a positive reference
//! in its front leaf and a negated one in its back leaf (Blood Gulch 2,
//! Danger Canyon 26, Gephyrophobia 10; checked 2026-10-03).
//!
//! So every leaf a scenery polygon passes through is split on the polygon's
//! own plane. Both children are copies of the leaf — a leaf stays a leaf and
//! open space stays open; nothing becomes "none" (solid), which put the whole
//! of Danger Canyon inside solid scenery once (2026-10-01) — flagged, keeping
//! the leaf's own references, and with a reference straight to the surface
//! (no 2D nodes): positive in front, negated behind. A polygon lying on a
//! plane the tree already splits on gets references on that plane instead of
//! a second, coincident node. A later split passes each scenery reference on
//! only to the side(s) its part of the polygon reaches; the leaf's own
//! references always stay, since a ray that reaches solid from either copy
//! needs them. Leaves many polygons reach are cut up along the axes first
//! ([`kd`]), so one polygon's plane does not slice through all the others.
//!
//! The offline check is `examples/scenery_probe.rs` (rays through every
//! scenery triangle, and the BSP's own floors, before and after).

use crate::ce::{Bsp2dReference, Bsp3dNode, Collision, Plane};
use crate::{split, unpack16, Error};

const LEAF: u32 = 0x8000_0000;
const NEGATED: u32 = 0x8000_0000;
/// Leaf flag bit 0: the leaf contains two-sided surfaces.
pub const TWO_SIDED_LEAF: u16 = 1;
/// How far (world units) a vertex may sit off a plane and still count as on
/// it: 1 mm. Scenery triangles are placed in floats, and a polygon that
/// merely touches a plane must not be cut into slivers on its far side.
const EPS: f32 = 3.3e-4;

#[derive(Debug, Clone, Default)]
pub struct Report {
    /// Surfaces the tree now reaches.
    pub surfaces: usize,
    /// Leaves split on a scenery plane (one node and one leaf each).
    pub splits: usize,
    /// References added on a plane the tree already split on.
    pub coplanar: usize,
    /// Axis cuts made in leaves many polygons reach, before linking.
    pub cuts: usize,
    pub nodes: (usize, usize),
    pub leaves: (usize, usize),
    pub references: (usize, usize),
}

fn dot(a: [f32; 3], b: [f32; 3]) -> f32 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

/// Signed distances of `poly` from plane `plane` (flip bit applied).
fn distances(c: &Collision, plane: i32, poly: &[[f32; 3]]) -> Vec<f32> {
    let pl = c.planes[(plane as u32 & 0x7fff_ffff) as usize];
    let flip = (plane as u32) & NEGATED != 0;
    poly.iter()
        .map(|&p| {
            let d = dot(pl.n, p) - pl.d;
            if flip {
                -d
            } else {
                d
            }
        })
        .collect()
}

/// Which side(s) of a plane a polygon reaches: (front, back). Both false
/// means it lies on the plane.
fn reach(d: &[f32]) -> (bool, bool) {
    (d.iter().any(|&x| x > EPS), d.iter().any(|&x| x < -EPS))
}

/// Split a convex polygon by its vertices' distances; vertices on the plane
/// go to both halves.
fn clip(poly: &[[f32; 3]], d: &[f32]) -> (Vec<[f32; 3]>, Vec<[f32; 3]>) {
    let (mut front, mut back) = (Vec::new(), Vec::new());
    let n = poly.len();
    for i in 0..n {
        let (a, b) = (poly[i], poly[(i + 1) % n]);
        let (da, db) = (d[i], d[(i + 1) % n]);
        if da >= -EPS {
            front.push(a);
        }
        if da <= EPS {
            back.push(a);
        }
        if (da > EPS && db < -EPS) || (da < -EPS && db > EPS) {
            let t = da / (da - db);
            let p = [
                a[0] + (b[0] - a[0]) * t,
                a[1] + (b[1] - a[1]) * t,
                a[2] + (b[2] - a[2]) * t,
            ];
            front.push(p);
            back.push(p);
        }
    }
    (front, back)
}

/// A child pointer to (maybe) rewrite: the node and which of its children.
#[derive(Clone, Copy)]
struct Slot {
    node: usize,
    front: bool,
}

struct Work {
    slot: Slot,
    fragment: Vec<[f32; 3]>,
    /// Planes the fragment lies on that the path already split on, each with
    /// the reference sign for the side taken.
    on: Vec<i32>,
}

/// Make surfaces `first..` of `c` reachable by its bsp3d tree. They must be
/// two-sided standalone surfaces (scenery), and the tree's root must be node
/// 0. A leaf that gains scenery gets a fresh reference range at the end of
/// the table, holding its own references and the scenery's.
pub fn link(c: &mut Collision, first: usize) -> Report {
    let mut r = Report {
        nodes: (c.bsp3d_nodes.len(), 0),
        leaves: (c.leaves.len(), 0),
        references: (c.bsp2d_references.len(), 0),
        ..Default::default()
    };
    let polys: Vec<Vec<[f32; 3]>> = (first..c.surfaces.len())
        .map(|s| unpack16::polygon(c, s))
        .collect();
    if c.bsp3d_nodes.is_empty() {
        return r;
    }

    // A leaf many polygons reach is first cut up between them along the
    // axes, so one polygon's plane does not slice through every other one in
    // the leaf: Danger Canyon's 43,646 tree and rock triangles, linked into
    // pieces of one open leaf each, made 37 pieces of ~35 references per
    // triangle and trees 190 deep that way (2026-10-03).
    let mut crowds: std::collections::BTreeMap<usize, (Slot, Vec<Item>)> = Default::default();
    for poly in &polys {
        if poly.len() < 3 {
            continue;
        }
        for hit in walk(c, poly) {
            crowds
                .entry(hit.leaf)
                .or_insert_with(|| (hit.slot, Vec::new()))
                .1
                .push(Item::of(&hit.fragment));
        }
    }
    for (leaf, (slot, mut items)) in crowds {
        if items.len() > CROWD {
            let mut original = Some(leaf);
            let child = kd(c, leaf, &mut original, &mut items, 0, &mut r);
            set_child(c, slot, child);
        }
    }

    // Scenery each leaf has gained: the signed plane it is named on, the
    // surface, and the part of it on the leaf's boundary. A later split
    // passes each part on only to the side(s) it reaches.
    let mut extra: Vec<Vec<Named>> = vec![Vec::new(); c.leaves.len()];
    for s in first..c.surfaces.len() {
        let poly = &polys[s - first];
        if poly.len() < 3 {
            continue;
        }
        let plane = (c.surfaces[s].plane as u32 & 0x7fff_ffff) as i32;
        let hits = walk(c, poly);
        if !hits.is_empty() {
            r.surfaces += 1;
        }
        // Each leaf is reached once, so the leaves can be split in turn.
        for hit in hits {
            let l = hit.leaf;
            c.leaves[l].flags |= TWO_SIDED_LEAF;
            if !hit.on.is_empty() {
                // Not on a plane the leaf names a surface of its own on: there
                // the leaf borders solid, which stops a ray anyway, and the
                // simulation takes the first reference on the plane it finds.
                let own = c.leaves[l];
                let own = &c.bsp2d_references[own.first_reference.max(0) as usize..]
                    [..own.reference_count.max(0) as usize];
                for &p in &hit.on {
                    let raw = p as u32 & 0x7fff_ffff;
                    if own.iter().any(|o| o.plane as u32 & 0x7fff_ffff == raw) {
                        continue;
                    }
                    if !extra[l]
                        .iter()
                        .any(|e| e.plane == p && e.surface == s as i32)
                    {
                        extra[l].push(Named {
                            plane: p,
                            surface: s as i32,
                            part: hit.fragment.clone(),
                        });
                        r.coplanar += 1;
                    }
                }
                continue;
            }
            // Split the leaf on the surface's plane: the leaf stays behind,
            // its copy goes in front.
            let mut front = Vec::new();
            let mut back = Vec::new();
            for e in std::mem::take(&mut extra[l]) {
                let d = distances(c, plane, &e.part);
                match reach(&d) {
                    (true, false) => front.push(e),
                    (false, true) => back.push(e),
                    (false, false) => {
                        back.push(e.clone());
                        front.push(e);
                    }
                    (true, true) => {
                        let (f, b) = clip(&e.part, &d);
                        if f.len() >= 3 {
                            front.push(Named {
                                part: f,
                                ..e.clone()
                            });
                        }
                        if b.len() >= 3 {
                            back.push(Named { part: b, ..e });
                        }
                    }
                }
            }
            front.push(Named {
                plane,
                surface: s as i32,
                part: hit.fragment.clone(),
            });
            back.push(Named {
                plane: (plane as u32 | NEGATED) as i32,
                surface: s as i32,
                part: hit.fragment,
            });
            let copy = c.leaves.len();
            c.leaves.push(c.leaves[l]);
            extra[l] = back;
            extra.push(front);
            let node = c.bsp3d_nodes.len() as i32;
            c.bsp3d_nodes.push(Bsp3dNode {
                plane,
                back: (LEAF | l as u32) as i32,
                front: (LEAF | copy as u32) as i32,
            });
            set_child(c, hit.slot, node);
            r.splits += 1;
        }
    }

    // Lay the references out. Every leaf that names scenery keeps its own
    // references (the leaf it was cut from had them; a ray that leaves it
    // into solid needs them) in a fresh range with the scenery's. Leaves cut
    // from the same leaf go in pairs around one copy of those: [scenery of
    // A, own, scenery of B], A's range ending and B's starting at the copy.
    // One copy per leaf put Blood Gulch's 1,794 scenery triangles at 82,938
    // references, past the 16-bit table (2026-10-03).
    let mut groups: std::collections::BTreeMap<(i32, i16), Vec<usize>> = Default::default();
    for (l, refs) in extra.iter().enumerate() {
        if !refs.is_empty() {
            let leaf = c.leaves[l];
            groups
                .entry((leaf.first_reference, leaf.reference_count.max(0)))
                .or_default()
                .push(l);
        }
    }
    let named = |l: usize| {
        extra[l].iter().map(|e| Bsp2dReference {
            plane: e.plane,
            node: (LEAF | e.surface as u32) as i32,
        })
    };
    for ((own_first, own_count), leaves) in groups {
        let own = own_first.max(0) as usize..own_first.max(0) as usize + own_count as usize;
        for pair in leaves.chunks(2) {
            let a = pair[0];
            let at = c.bsp2d_references.len();
            c.bsp2d_references.extend(named(a));
            let shared = c.bsp2d_references.len();
            c.bsp2d_references.extend_from_within(own.clone());
            c.leaves[a].first_reference = at as i32;
            c.leaves[a].reference_count = (c.bsp2d_references.len() - at) as i16;
            if let Some(&b) = pair.get(1) {
                c.bsp2d_references.extend(named(b));
                c.leaves[b].first_reference = shared as i32;
                c.leaves[b].reference_count = (c.bsp2d_references.len() - shared) as i16;
            }
        }
    }
    r.nodes.1 = c.bsp3d_nodes.len();
    r.leaves.1 = c.leaves.len();
    r.references.1 = c.bsp2d_references.len();
    r
}

/// A scenery surface a leaf names: on which signed plane, and the part of
/// the surface on the leaf's boundary.
#[derive(Clone)]
struct Named {
    plane: i32,
    surface: i32,
    part: Vec<[f32; 3]>,
}

/// More polygons than this reaching one leaf get it cut up first ([`kd`]).
const CROWD: usize = 12;

/// A polygon fragment's centre and box, for [`kd`].
struct Item {
    centre: [f32; 3],
    min: [f32; 3],
    max: [f32; 3],
}

impl Item {
    fn of(fragment: &[[f32; 3]]) -> Item {
        let mut min = fragment[0];
        let mut max = fragment[0];
        for p in fragment {
            for a in 0..3 {
                min[a] = min[a].min(p[a]);
                max[a] = max[a].max(p[a]);
            }
        }
        let k = fragment.len() as f32;
        Item {
            centre: [0, 1, 2].map(|a| fragment.iter().map(|p| p[a]).sum::<f32>() / k),
            min,
            max,
        }
    }
}

/// Cut leaf `leaf` up along the axes until no cell holds more than
/// [`CROWD`] of `items`, each cut where it crosses the fewest fragments.
/// Every cell is a copy of the leaf, with its flags and its own references
/// (shared, not duplicated), so the space the leaf covered is as open as
/// before and names the same surfaces. Returns the subtree's root as a bsp3d
/// child; the first cell is the leaf itself.
fn kd(
    c: &mut Collision,
    leaf: usize,
    original: &mut Option<usize>,
    items: &mut [Item],
    depth: usize,
    r: &mut Report,
) -> i32 {
    let cell = |c: &mut Collision, original: &mut Option<usize>| -> i32 {
        let l = original.take().unwrap_or_else(|| {
            c.leaves.push(c.leaves[leaf]);
            c.leaves.len() - 1
        });
        (LEAF | l as u32) as i32
    };
    if items.len() <= CROWD || depth >= 24 {
        return cell(c, original);
    }
    let mut lo = items[0].centre;
    let mut hi = lo;
    for it in items.iter() {
        for a in 0..3 {
            lo[a] = lo[a].min(it.centre[a]);
            hi[a] = hi[a].max(it.centre[a]);
        }
    }
    let axis = (0..3)
        .max_by(|&a, &b| (hi[a] - lo[a]).total_cmp(&(hi[b] - lo[b])))
        .unwrap();
    items.sort_by(|a, b| a.centre[axis].total_cmp(&b.centre[axis]));
    let n = items.len();
    // Candidate cuts between neighbouring centres in the middle half: the
    // fewest fragments crossed, then the most even.
    let mut best: Option<(usize, usize, f32)> = None;
    let (from, to) = ((n / 4).max(1), (3 * n / 4).min(n - 1));
    let step = ((to - from) / 16).max(1);
    for i in (from..=to).step_by(step) {
        let (a, b) = (items[i - 1].centre[axis], items[i].centre[axis]);
        if b - a <= 2.0 * EPS {
            continue;
        }
        let at = 0.5 * (a + b);
        let crossed = items
            .iter()
            .filter(|it| it.min[axis] < at - EPS && it.max[axis] > at + EPS)
            .count();
        let better = match best {
            None => true,
            Some((bi, bc, _)) => {
                crossed < bc || (crossed == bc && (2 * i).abs_diff(n) < (2 * bi).abs_diff(n))
            }
        };
        if better {
            best = Some((i, crossed, at));
        }
    }
    let Some((i, _, at)) = best else {
        return cell(c, original);
    };
    let mut normal = [0.0; 3];
    normal[axis] = 1.0;
    let plane = c.planes.len() as i32;
    c.planes.push(Plane { n: normal, d: at });
    let node = c.bsp3d_nodes.len();
    c.bsp3d_nodes.push(Bsp3dNode {
        plane,
        back: -1,
        front: -1,
    });
    r.cuts += 1;
    let (back, front) = items.split_at_mut(i);
    let back = kd(c, leaf, original, back, depth + 1, r);
    let front = kd(c, leaf, original, front, depth + 1, r);
    c.bsp3d_nodes[node].back = back;
    c.bsp3d_nodes[node].front = front;
    node as i32
}

fn set_child(c: &mut Collision, slot: Slot, child: i32) {
    let parent = &mut c.bsp3d_nodes[slot.node];
    if slot.front {
        parent.front = child;
    } else {
        parent.back = child;
    }
}

/// A leaf a polygon reaches: where it hangs, the part of the polygon in it,
/// and the planes on the way that the polygon lies on (signed for the side).
struct Reached {
    slot: Slot,
    leaf: usize,
    fragment: Vec<[f32; 3]>,
    on: Vec<i32>,
}

/// Every leaf `poly` reaches, each once. Solid space takes nothing.
fn walk(c: &Collision, poly: &[[f32; 3]]) -> Vec<Reached> {
    let root = c.bsp3d_nodes[0];
    let d = distances(c, root.plane, poly);
    let mut work = Vec::new();
    push_children(&mut work, 0, root.plane, poly, &d, &[]);
    let mut out = Vec::new();
    while let Some(w) = work.pop() {
        let n = c.bsp3d_nodes[w.slot.node];
        let child = if w.slot.front { n.front } else { n.back };
        if child == -1 {
            continue;
        }
        if (child as u32) & LEAF == 0 {
            let k = child as usize;
            let q = c.bsp3d_nodes[k].plane;
            let d = distances(c, q, &w.fragment);
            push_children(&mut work, k, q, &w.fragment, &d, &w.on);
            continue;
        }
        out.push(Reached {
            slot: w.slot,
            leaf: (child as u32 & 0x7fff_ffff) as usize,
            fragment: w.fragment,
            on: w.on,
        });
    }
    out
}

/// Where [`place`] put the scenery.
#[derive(Debug, Clone)]
pub enum Placed {
    /// In the BSP's own tree.
    Tree(Report),
    /// In pieces of their own, each with its own tree, because the BSP's
    /// 16-bit tables could not hold them (why).
    Pieces(String),
}

/// Make the scenery tail `first..` of `c` reachable by a tree: linked into
/// the BSP's own when the result (fan split as the transplant will) still
/// fits the 16-bit tables, otherwise moved out into pieces of at most `max`
/// surfaces ([`split::split_standalone`]), which link their own.
pub fn place(
    mut c: Collision,
    first: usize,
    max: usize,
) -> Result<(Collision, Vec<Collision>, Placed), Error> {
    let why = match c.fits_16bit() {
        Ok(()) => {
            let mut linked = c.clone();
            let r = link(&mut linked, first);
            let mut check = linked.clone();
            split::fan_split(&mut check, 4);
            match check.fits_16bit() {
                Ok(()) => return Ok((linked, Vec::new(), Placed::Tree(r))),
                Err(e) => format!("{e} once the scenery is in the tree"),
            }
        }
        Err(e) => e.to_string(),
    };
    let pieces = split::split_standalone(&mut c, first, max)?;
    Ok((c, pieces, Placed::Pieces(why)))
}

/// Queue the children of node `node` (plane `q`) that `fragment` reaches.
fn push_children(
    work: &mut Vec<Work>,
    node: usize,
    q: i32,
    fragment: &[[f32; 3]],
    d: &[f32],
    on: &[i32],
) {
    let (f, b) = reach(d);
    let item = |front: bool, fragment: Vec<[f32; 3]>, on: Vec<i32>| Work {
        slot: Slot { node, front },
        fragment,
        on,
    };
    match (f, b) {
        (true, false) => work.push(item(true, fragment.to_vec(), on.to_vec())),
        (false, true) => work.push(item(false, fragment.to_vec(), on.to_vec())),
        (true, true) => {
            let (front, back) = clip(fragment, d);
            if front.len() >= 3 {
                work.push(item(true, front, on.to_vec()));
            }
            if back.len() >= 3 {
                work.push(item(false, back, on.to_vec()));
            }
        }
        (false, false) => {
            // On the node's plane: both sides see it across this plane. The
            // front leaf's reference is the plane as it is, the back's
            // negated (a node plane's own flip bit turns that round).
            let raw = (q as u32 & 0x7fff_ffff) as i32;
            let flip = (q as u32) & NEGATED != 0;
            for front in [true, false] {
                let negated = front == flip;
                let p = if negated {
                    (raw as u32 | NEGATED) as i32
                } else {
                    raw
                };
                let mut on = on.to_vec();
                if !on.contains(&p) {
                    on.push(p);
                }
                work.push(item(front, fragment.to_vec(), on));
            }
        }
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use crate::ce::{Edge, Leaf, Surface, Vertex};
    use crate::raytest;

    /// Append `poly` as a surface with its own plane and edge ring, the way
    /// the scenery merge writes one. Returns the surface index.
    pub(crate) fn add_polygon(c: &mut Collision, poly: &[[f32; 3]], flags: u8) -> usize {
        let (a, b, d) = (poly[0], poly[1], poly[2]);
        let u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
        let v = [d[0] - a[0], d[1] - a[1], d[2] - a[2]];
        let mut n = [
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        ];
        let len = dot(n, n).sqrt();
        n = n.map(|x| x / len);
        let plane = c.planes.len() as i32;
        c.planes.push(Plane { n, d: dot(n, a) });
        let s = c.surfaces.len() as i32;
        let (v0, e0, k) = (
            c.vertices.len() as i32,
            c.edges.len() as i32,
            poly.len() as i32,
        );
        for (j, &p) in poly.iter().enumerate() {
            c.vertices.push(Vertex {
                point: p,
                first_edge: e0 + j as i32,
            });
        }
        for j in 0..k {
            c.edges.push(Edge {
                start: v0 + j,
                end: v0 + (j + 1) % k,
                forward: e0 + (j + 1) % k,
                reverse: -1,
                left: s,
                right: -1,
            });
        }
        c.surfaces.push(Surface {
            plane,
            first_edge: e0,
            flags,
            breakable: -1,
            material: 0,
        });
        s as usize
    }

    /// A floor at z = 0 (solid below, one open leaf above) and, standing on
    /// it, a two-sided wall at x = 0 (y -1..1, z 0.5..2) as two standalone
    /// triangles, each on a plane of its own, as the scenery merge adds them.
    pub(crate) fn floor_and_wall() -> (Collision, usize) {
        let mut c = Collision::default();
        add_polygon(
            &mut c,
            &[
                [-10.0, -10.0, 0.0],
                [10.0, -10.0, 0.0],
                [10.0, 10.0, 0.0],
                [-10.0, 10.0, 0.0],
            ],
            0,
        );
        c.bsp3d_nodes.push(Bsp3dNode {
            plane: 0,
            back: -1,
            front: LEAF as i32,
        });
        c.leaves.push(Leaf {
            flags: 0,
            reference_count: 1,
            first_reference: 0,
        });
        c.bsp2d_references.push(Bsp2dReference {
            plane: 0,
            node: LEAF as i32,
        });
        let first = c.surfaces.len();
        let w = [
            [0.0, -1.0, 0.5],
            [0.0, 1.0, 0.5],
            [0.0, 1.0, 2.0],
            [0.0, -1.0, 2.0],
        ];
        add_polygon(&mut c, &[w[0], w[1], w[2]], 1);
        add_polygon(&mut c, &[w[0], w[2], w[3]], 1);
        (c, first)
    }

    pub(crate) fn ray(c: &Collision, o: [f32; 3], e: [f32; 3]) -> Option<raytest::Hit> {
        raytest::tree(c, o, [e[0] - o[0], e[1] - o[1], e[2] - o[2]])
    }

    #[test]
    fn a_ray_through_the_wall_hits_it_only_once_it_is_linked() {
        let (mut c, first) = floor_and_wall();
        let through = ([-1.0, 0.3, 1.0], [1.0, 0.3, 1.0]);
        assert!(
            ray(&c, through.0, through.1).is_none(),
            "standalone: missed"
        );

        let r = link(&mut c, first);
        assert_eq!(r.surfaces, 2);
        for (o, e) in [
            through,
            (through.1, through.0),
            ([-1.0, -0.8, 1.9], [1.0, -0.8, 1.9]),
        ] {
            let hit = ray(&c, o, e).expect("linked: hit");
            assert!((hit.t - 0.5).abs() < 1e-4, "{o:?} -> {e:?}: t {}", hit.t);
            assert!(
                hit.surface >= first,
                "{o:?} -> {e:?}: surface {}",
                hit.surface
            );
        }
        // Beside, above and under the wall: nothing in the way.
        for (o, e) in [
            ([-1.0, 1.5, 1.0], [1.0, 1.5, 1.0]),
            ([-1.0, 0.0, 2.5], [1.0, 0.0, 2.5]),
            ([-1.0, 0.0, 0.25], [1.0, 0.0, 0.25]),
        ] {
            assert!(ray(&c, o, e).is_none(), "{o:?} -> {e:?} hit");
        }
        // The floor still stops a ray, with its own surface, beside the
        // wall and in the space the wall's planes now split.
        for x in [5.0, 0.5, -0.5] {
            let down = ray(&c, [x, 0.0, 3.0], [x, 0.0, -1.0]).expect("floor");
            assert_eq!(down.surface, 0, "x {x}");
            assert!((down.t - 0.75).abs() < 1e-4);
        }
    }

    #[test]
    fn open_space_stays_open_and_solid_stays_solid() {
        let (before, first) = floor_and_wall();
        let mut c = before.clone();
        link(&mut c, first);
        assert!(c.bsp3d_nodes.len() > before.bsp3d_nodes.len());
        for i in 0..21 {
            for j in 0..21 {
                for k in 0..13 {
                    let p = [
                        -2.0 + 0.2 * i as f32 + 0.013,
                        -2.0 + 0.2 * j as f32 + 0.007,
                        -1.0 + 0.25 * k as f32 + 0.011,
                    ];
                    assert_eq!(
                        raytest::classify(&before, p).is_some(),
                        raytest::classify(&c, p).is_some(),
                        "{p:?}"
                    );
                }
            }
        }
        // No child is "none" that was not before, and every leaf hangs off
        // exactly one node.
        let nones = |c: &Collision| {
            c.bsp3d_nodes
                .iter()
                .flat_map(|n| [n.back, n.front])
                .filter(|&x| x == -1)
                .count()
        };
        assert_eq!(nones(&c), nones(&before));
        let mut refs = vec![0; c.leaves.len()];
        for n in &c.bsp3d_nodes {
            for x in [n.back, n.front] {
                if x != -1 && (x as u32) & LEAF != 0 {
                    refs[(x as u32 & 0x7fff_ffff) as usize] += 1;
                }
            }
        }
        assert!(refs.iter().all(|&r| r == 1), "{refs:?}");
        // Every leaf keeps the floor's reference, and is flagged.
        for l in &c.leaves {
            let refs =
                &c.bsp2d_references[l.first_reference as usize..][..l.reference_count as usize];
            assert_eq!(refs.iter().filter(|r| r.plane == 0).count(), 1);
            assert_eq!(l.flags & TWO_SIDED_LEAF, TWO_SIDED_LEAF);
        }
        assert!(c.fits_16bit().is_ok());
    }

    #[test]
    fn the_tree_agrees_with_the_polygons() {
        let (mut c, first) = floor_and_wall();
        link(&mut c, first);
        let mut rays = Vec::new();
        for i in 0..24 {
            for j in 0..12 {
                let y = -1.6 + 0.137 * i as f32;
                let z = 0.1 + 0.19 * j as f32;
                rays.push(([-1.3, y, z], [1.1, -y * 0.5, z + 0.3]));
                rays.push(([1.2, y, z], [-0.9, y + 0.2, z - 0.4]));
            }
        }
        let r = raytest::compare(&c, &rays, 1e-3);
        assert!(r.expected > 100, "{r:?}");
        assert_eq!((r.missed, r.displaced, r.phantom), (0, 0, 0), "{r:?}");
    }

    /// Forty small tilted walls in the floor's one open leaf: the leaf is cut
    /// up between them first, and every wall still stops a ray from either
    /// side, while the floor stays the floor.
    #[test]
    fn a_crowded_leaf_is_cut_up_and_every_polygon_still_hits() {
        let (mut c, first) = floor_and_wall();
        c.surfaces.truncate(first);
        let mut centres = Vec::new();
        for i in 0..8 {
            for j in 0..5 {
                let (x, y) = (-7.0 + 2.0 * i as f32, -5.0 + 2.5 * j as f32);
                let t = 0.3 * (i + j) as f32;
                let (dx, dy) = (0.6 * t.cos(), 0.6 * t.sin());
                add_polygon(
                    &mut c,
                    &[
                        [x - dx, y - dy, 0.4],
                        [x + dx, y + dy, 0.4],
                        [x + dx, y + dy, 1.6],
                    ],
                    1,
                );
                // Just inside the triangle, and its normal.
                let p = [x + 0.3 * dx, y + 0.3 * dy, 0.8];
                centres.push((p, [dy / 0.6, -dx / 0.6, 0.0]));
            }
        }
        let before = c.clone();
        let r = link(&mut c, first);
        assert!(r.cuts > 0, "{r:?}");
        assert_eq!(r.surfaces, 40);
        for (k, (p, n)) in centres.iter().enumerate() {
            let a = [0, 1, 2].map(|i| p[i] + 0.2 * n[i]);
            let b = [0, 1, 2].map(|i| p[i] - 0.2 * n[i]);
            for (o, e) in [(a, b), (b, a)] {
                let hit = ray(&c, o, e).unwrap_or_else(|| panic!("wall {k}: {o:?} -> {e:?}"));
                assert_eq!(hit.surface, first + k);
            }
        }
        for i in 0..40 {
            for j in 0..40 {
                let p = [-9.7 + 0.5 * i as f32, -9.6 + 0.5 * j as f32, 0.9];
                assert_eq!(
                    raytest::classify(&before, p).is_some(),
                    raytest::classify(&c, p).is_some()
                );
                let down = ray(&c, [p[0], p[1], 3.0], [p[0], p[1], -1.0]);
                if let Some(h) = down {
                    assert!(h.surface == 0 || h.surface >= first);
                } else {
                    panic!("no floor under {p:?}");
                }
            }
        }
    }

    #[test]
    fn a_polygon_on_a_plane_the_tree_splits_on_gets_references_there() {
        // A third triangle exactly on the wall's plane, beside it: no node on
        // a coincident plane, references on the existing one.
        let (mut c, first) = floor_and_wall();
        add_polygon(
            &mut c,
            &[[0.0, 1.0, 0.5], [0.0, 3.0, 0.5], [0.0, 3.0, 2.0]],
            1,
        );
        let r = link(&mut c, first);
        assert!(r.coplanar > 0, "{r:?}");
        for (o, e) in [
            ([-1.0, 2.5, 0.7], [1.0, 2.5, 0.7]),
            ([1.0, 2.5, 0.7], [-1.0, 2.5, 0.7]),
        ] {
            let hit = ray(&c, o, e).expect("hit");
            assert_eq!(hit.surface, first + 2);
        }
    }
}
