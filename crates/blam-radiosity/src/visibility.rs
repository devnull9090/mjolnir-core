//! Which shooter lights which vertex: tool.exe shoots an element at every
//! vertex of every element in the clusters its own cluster sees (the
//! structure's PVS), one shooter at a time. A batch gathers from many
//! shooters at once, so each shooter-vertex pair is tested here; without
//! it a shooter lit whatever any of its batch-mates' clusters saw, and the
//! result moved with the batch size (Coldsnap's interiors at 256 came out
//! 10-40/255 brighter, 2026-10-10).
//!
//! A vertex can sit on several clusters' elements (their shared edges), so
//! it carries the set of clusters its elements are in, as a group shared
//! by every vertex with the same set: it gathers from a shooter whose
//! visibility row holds any of them.

use crate::elements::Elements;
use std::collections::HashMap;

pub struct ClusterVis {
    /// 32-bit words per row of `bits`.
    pub words: usize,
    /// Per cluster, the clusters it sees, one bit each.
    pub bits: Vec<u32>,
    /// Every cluster sees every cluster: no pair needs the test.
    pub all: bool,
    /// Per pool vertex, its group (0: in no element yet).
    pub group: Vec<u32>,
    /// Per group, its clusters, ascending; group 0 is the empty set.
    pub groups: Vec<Vec<u32>>,
    index: HashMap<Vec<u32>, u32>,
    /// What changed since the GPU last took it: the vertices from here on,
    /// and the group list.
    pub dirty_from: usize,
    pub groups_dirty: bool,
}

impl ClusterVis {
    /// `visible`: per cluster, the clusters it sees (itself included);
    /// `cluster`: each element's cluster, as the solver files it.
    pub fn new(visible: &[Vec<u32>], elements: &Elements, cluster: impl Fn(usize) -> usize) -> ClusterVis {
        let n = visible.len().max(1);
        let words = n.div_ceil(32);
        let mut bits = vec![0u32; n * words];
        let mut all = true;
        for (g, row) in visible.iter().enumerate() {
            for &h in row {
                bits[g * words + h as usize / 32] |= 1 << (h % 32);
            }
            all &= (0..n).all(|h| bits[g * words + h / 32] & (1 << (h % 32)) != 0);
        }
        let mut v = ClusterVis {
            words,
            bits,
            all,
            group: vec![0; elements.pool.vertices.len()],
            groups: vec![Vec::new()],
            index: HashMap::from([(Vec::new(), 0)]),
            dirty_from: 0,
            groups_dirty: true,
        };
        for (i, e) in elements.elements.iter().enumerate() {
            let leaves = if e.children.is_empty() { std::slice::from_ref(&e.patch) } else { &e.children[..] };
            for leaf in leaves {
                for &vi in &leaf.v {
                    v.add(vi, cluster(i) as u32);
                }
            }
        }
        v
    }

    /// Vertex `v` is on an element of `cluster`.
    pub fn add(&mut self, v: u32, cluster: u32) {
        let vi = v as usize;
        if vi >= self.group.len() {
            self.group.resize(vi + 1, 0);
        }
        let current = &self.groups[self.group[vi] as usize];
        let Err(at) = current.binary_search(&cluster) else { return };
        let mut set = current.clone();
        set.insert(at, cluster);
        let id = match self.index.get(&set) {
            Some(&id) => id,
            None => {
                let id = self.groups.len() as u32;
                self.groups.push(set.clone());
                self.index.insert(set, id);
                self.groups_dirty = true;
                id
            }
        };
        self.group[vi] = id;
        self.dirty_from = self.dirty_from.min(vi);
    }

    /// Whether a shooter in `cluster` lights vertex `v`.
    pub fn sees(&self, cluster: usize, v: u32) -> bool {
        if self.all {
            return true;
        }
        let row = &self.bits[cluster * self.words..(cluster + 1) * self.words];
        let g = self.group.get(v as usize).copied().unwrap_or(0) as usize;
        self.groups[g].iter().any(|&c| row[c as usize / 32] & (1 << (c % 32)) != 0)
    }

    /// The test as one array for the GPU (`gpu.wgsl` `sees`): the rows,
    /// then per group (first, count) into the cluster lists that follow;
    /// with where the group table and the lists start.
    pub fn flat(&self) -> (Vec<u32>, u32, u32) {
        let mut out = self.bits.clone();
        let table = out.len() as u32;
        let lists = table + 2 * self.groups.len() as u32;
        let mut first = 0u32;
        for g in &self.groups {
            out.extend([first, g.len() as u32]);
            first += g.len() as u32;
        }
        for g in &self.groups {
            out.extend_from_slice(g);
        }
        (out, table, lists)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::elements::{Element, MaterialInfo, Patch, Pool, Vertex};

    fn element(v: [u32; 3], cluster: i32) -> Element {
        Element {
            patch: Patch { v, uv0: [[0.0; 2]; 3], uv1: [[0.0; 2]; 3], area: 1.0, segment: 1.0 },
            normal: [0.0, 1.0, 0.0],
            d: 0.0,
            delta: [0.0; 3],
            reflectance: [0.5; 3],
            material: 0,
            cluster,
            tri: 0,
            children: Vec::new(),
        }
    }

    #[test]
    fn a_shooter_lights_only_its_clusters_vertices() {
        // Three clusters: 0 sees 1, 2 sees only itself. Vertex 2 is on an
        // element of cluster 1 and one of cluster 2.
        let mut pool = Pool::default();
        for i in 0..5 {
            pool.vertices.push(Vertex { p: [i as f32, 0.0, 0.0], n: [0.0, 1.0, 0.0], total: [0.0; 3], dir: [0.0; 3], sun: [0.0; 3], ambient: [0.0; 3], placed: [0.0; 3], faces: Vec::new() });
        }
        let elements = Elements {
            pool,
            elements: vec![element([0, 1, 2], 1), element([2, 3, 4], 2)],
            materials: vec![MaterialInfo { shader: String::new(), page: 0, fixed: None, detail_level: 0, ignore_normals: false, emission: [0.0; 3], area: 0.0 }],
            total_area: 2.0,
        };
        let visible = vec![vec![0, 1], vec![1, 0], vec![2]];
        let vis = ClusterVis::new(&visible, &elements, |i| elements.elements[i].cluster as usize);
        assert!(!vis.all);
        assert!(vis.sees(0, 0) && vis.sees(0, 2) && !vis.sees(0, 3));
        assert!(vis.sees(2, 2) && vis.sees(2, 4) && !vis.sees(2, 0));
        let (flat, table, lists) = vis.flat();
        assert_eq!(table as usize, 3);
        assert_eq!(lists as usize, 3 + 2 * vis.groups.len());
        assert_eq!(flat.len(), lists as usize + vis.groups.iter().map(|g| g.len()).sum::<usize>());
    }
}
