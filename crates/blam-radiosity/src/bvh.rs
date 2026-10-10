//! A bounding-volume hierarchy over triangles, for the visibility rays the
//! form factors need. tool.exe walks the structure's collision BSP for the
//! same test; against the rendered triangles the result is the same set of
//! occluders, and a BVH takes any mesh (a converted map's scenery too).

use crate::math::{cross, dot, sub, V3};

struct Node {
    min: V3,
    max: V3,
    /// Leaf: first triangle; inner: right child (left is the next node).
    index: u32,
    /// Leaf: triangle count; inner: 0.
    count: u32,
}

/// A hit along a ray: its distance and the triangle it met, as the index
/// the triangles were given to [`Bvh::build`].
#[derive(Clone, Copy, Debug)]
pub struct Hit {
    pub t: f32,
    pub tri: u32,
    /// The ray met the triangle's back face (its winding seen clockwise).
    pub back: bool,
}

pub struct Bvh {
    nodes: Vec<Node>,
    tris: Vec<[V3; 3]>,
    /// The caller's index of each triangle, in the sorted order.
    ids: Vec<u32>,
}

impl Bvh {
    pub fn build(tris: Vec<[V3; 3]>) -> Bvh {
        let mut nodes = Vec::new();
        let n = tris.len();
        let mut items: Vec<([V3; 3], u32)> = tris.into_iter().zip(0..n as u32).collect();
        Self::split(&mut items, 0, n, &mut nodes);
        let (tris, ids): (Vec<_>, Vec<_>) = items.into_iter().unzip();
        Bvh { nodes, tris, ids }
    }

    pub fn len(&self) -> usize {
        self.tris.len()
    }

    pub fn is_empty(&self) -> bool {
        self.tris.is_empty()
    }

    /// The triangles in tree order, and per triangle the caller's index.
    pub fn triangles(&self) -> (&[[V3; 3]], &[u32]) {
        (&self.tris, &self.ids)
    }

    /// The tree for the GPU (`gpu.wgsl`): per node eight 32-bit words (min,
    /// index, max, count; the floats as bits), per triangle in tree order
    /// its first corner and two edges as three vec4s, and per triangle in
    /// tree order the caller's index.
    pub fn flat(&self) -> (Vec<u32>, Vec<[f32; 4]>, &[u32]) {
        let mut nodes = Vec::with_capacity(self.nodes.len() * 8);
        for n in &self.nodes {
            nodes.extend([n.min[0].to_bits(), n.min[1].to_bits(), n.min[2].to_bits(), n.index]);
            nodes.extend([n.max[0].to_bits(), n.max[1].to_bits(), n.max[2].to_bits(), n.count]);
        }
        let mut tris = Vec::with_capacity(self.tris.len() * 3);
        for t in &self.tris {
            let (e1, e2) = (sub(t[1], t[0]), sub(t[2], t[0]));
            tris.extend([[t[0][0], t[0][1], t[0][2], 0.0], [e1[0], e1[1], e1[2], 0.0], [e2[0], e2[1], e2[2], 0.0]]);
        }
        (nodes, tris, &self.ids)
    }

    fn split(tris: &mut [([V3; 3], u32)], first: usize, end: usize, nodes: &mut Vec<Node>) -> usize {
        let mut min = [f32::MAX; 3];
        let mut max = [f32::MIN; 3];
        for (t, _) in &tris[first..end] {
            for v in t {
                for k in 0..3 {
                    min[k] = min[k].min(v[k]);
                    max[k] = max[k].max(v[k]);
                }
            }
        }
        let me = nodes.len();
        nodes.push(Node { min, max, index: first as u32, count: (end - first) as u32 });
        if end - first <= 4 {
            return me;
        }
        let ext = sub(max, min);
        let axis = if ext[0] >= ext[1] && ext[0] >= ext[2] { 0 } else if ext[1] >= ext[2] { 1 } else { 2 };
        let centre = |t: &[V3; 3]| t[0][axis] + t[1][axis] + t[2][axis];
        tris[first..end].sort_by(|a, b| centre(&a.0).partial_cmp(&centre(&b.0)).unwrap());
        let mid = (first + end) / 2;
        Self::split(tris, first, mid, nodes);
        let right = Self::split(tris, mid, end, nodes);
        nodes[me].index = right as u32;
        nodes[me].count = 0;
        me
    }

    /// The nearest triangle along `o + t d` for `t` in (0, `tmax`), or with
    /// `any`, the first one found (for a shadow ray, which only asks
    /// whether something is in the way).
    pub fn trace(&self, o: V3, d: V3, tmax: f32, any: bool) -> Option<Hit> {
        if self.tris.is_empty() {
            return None;
        }
        let inv = [1.0 / d[0], 1.0 / d[1], 1.0 / d[2]];
        let mut best = tmax;
        let mut found: Option<Hit> = None;
        let mut stack = [0u32; 64];
        let mut sp = 1;
        while sp > 0 {
            sp -= 1;
            let node = &self.nodes[stack[sp] as usize];
            let mut t0 = 0.0f32;
            let mut t1 = best;
            for k in 0..3 {
                let a = (node.min[k] - o[k]) * inv[k];
                let b = (node.max[k] - o[k]) * inv[k];
                t0 = t0.max(a.min(b));
                t1 = t1.min(a.max(b));
            }
            if t0 > t1 {
                continue;
            }
            if node.count > 0 {
                for i in node.index as usize..(node.index + node.count) as usize {
                    let tri = &self.tris[i];
                    // Moller-Trumbore, both faces.
                    let e1 = sub(tri[1], tri[0]);
                    let e2 = sub(tri[2], tri[0]);
                    let p = cross(d, e2);
                    let det = dot(e1, p);
                    if det.abs() < 1e-12 {
                        continue;
                    }
                    let inv_det = 1.0 / det;
                    let s = sub(o, tri[0]);
                    let u = dot(s, p) * inv_det;
                    if !(0.0..=1.0).contains(&u) {
                        continue;
                    }
                    let q = cross(s, e1);
                    let v = dot(d, q) * inv_det;
                    if v < 0.0 || u + v > 1.0 {
                        continue;
                    }
                    let t = dot(e2, q) * inv_det;
                    if t > 1e-5 && t < best {
                        let hit = Hit { t, tri: self.ids[i], back: det < 0.0 };
                        if any {
                            return Some(hit);
                        }
                        best = t;
                        found = Some(hit);
                    }
                }
            } else {
                let me = stack[sp] as usize;
                stack[sp] = (me + 1) as u32;
                stack[sp + 1] = node.index;
                sp += 2;
            }
        }
        found
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hits_the_nearest_of_two_quads() {
        let quad = |z: f32, id_base: usize| -> Vec<[V3; 3]> {
            let _ = id_base;
            vec![
                [[-1.0, -1.0, z], [1.0, -1.0, z], [1.0, 1.0, z]],
                [[-1.0, -1.0, z], [1.0, 1.0, z], [-1.0, 1.0, z]],
            ]
        };
        let mut tris = quad(2.0, 0);
        tris.extend(quad(5.0, 2));
        let bvh = Bvh::build(tris);
        let hit = bvh.trace([0.0, 0.0, 0.0], [0.0, 0.0, 1.0], 100.0, false).unwrap();
        assert!((hit.t - 2.0).abs() < 1e-5);
        assert!(hit.tri < 2);
        assert!(bvh.trace([0.0, 0.0, 0.0], [0.0, 0.0, -1.0], 100.0, true).is_none());
        assert!(bvh.trace([0.0, 0.0, 0.0], [0.0, 0.0, 1.0], 1.5, true).is_none());
    }
}
