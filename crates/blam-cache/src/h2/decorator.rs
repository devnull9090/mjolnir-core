//! Halo 2 decorators: the grass, rocks, debris and decals a structure BSP
//! scatters from its scenario's decorator sets (`DECR`).
//!
//! The BSP's decorators block (sbsp +0x234, 0x30 each) holds the grid's
//! centre (point3) and cells per dimension (the root cube is 8 world units
//! a cell), cache blocks (+0x10, 0x34: a raw block like a geometry
//! section's, {offset, size, section data size, resource data size,
//! resources (0x10 each) at +0x10}; its locator-0 resource is the
//! placements, 0x18 each), groups (+0x18, 0x18: set index, type, shader
//! index, compressed radius, cluster, cache block, first placement,
//! placement count) and cells (+0x20, 0x18: eight children, cache block,
//! group count, first group): an octree whose leaves are 8-unit cubes,
//! child index bit 2 the upper x half, bit 1 y, bit 0 z.
//!
//! A placement is six words, as MCC's `halo2.dll` reads them (0x979eeb, the
//! colour at 0x7fa1d0):
//!
//! - internal: bits 0-2 the class, 3-8 the permutation, 9-12 the yaw
//!   (v/15 of a turn), 13-15 the tint blend (v/7, the permutation's tint 1
//!   to tint 2), 16-19 the scale (v/15 across the permutation's scale
//!   range), 20-31 an up vector (x, y, z four bits each, 2v/15 - 1,
//!   normalised) the permutation's "align to normal" flag turns it to;
//! - position: the leaf cell's corner + (bits 0-9 x 8/1023, bits 10-19 x
//!   8/1023, bits 20-31 x 8/4095);
//! - tint and lightmap colour (XRGB), two light directions.
//!
//! Layouts from Assembly's Halo 2 plugins (sbsp, DECR); the decode checked
//! on Zanzibar, Turf and Beaver Creek: the placements lie on the BSP's
//! surface (median 0.1 world units, the test's sampling).

use crate::h2::{geometry, Cache, CacheFile, Struct};
use crate::Error;

/// A decoded placement.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Placement {
    /// The BSP's decorator set index (into the scenario's palette).
    pub set: usize,
    /// 0 model, 1 floating decal, 2 projected decal, 3 screen facing quad,
    /// 4 axis rotating quad, 5 cross quad.
    pub kind: u8,
    pub class: usize,
    pub permutation: usize,
    /// World units.
    pub position: [f32; 3],
    /// Radians about z.
    pub yaw: f32,
    /// 0..1 across the permutation's scale range.
    pub scale: f32,
    /// 0..1 from the permutation's tint 1 to tint 2.
    pub tint_blend: f32,
    /// The up vector, for an "align to normal" permutation.
    pub up: [f32; 3],
    /// The placement's tint and lightmap colours, 0..1.
    pub tint: [f32; 3],
    pub lightmap: [f32; 3],
}

/// Decode the internal and position words of a placement in the leaf cell
/// whose low corner is `corner`.
pub fn decode(internal: u32, position: u32, corner: [f32; 3]) -> (usize, usize, [f32; 3], f32, f32, f32, [f32; 3]) {
    let f = |v: u32, bits: u32, shift: u32| ((v >> shift) & ((1 << bits) - 1)) as f32;
    let pos = [
        corner[0] + f(position, 10, 0) * 8.0 / 1023.0,
        corner[1] + f(position, 10, 10) * 8.0 / 1023.0,
        corner[2] + f(position, 12, 20) * 8.0 / 4095.0,
    ];
    let mut up = [f(internal, 4, 20), f(internal, 4, 24), f(internal, 4, 28)].map(|v| 2.0 * v / 15.0 - 1.0);
    let n = (up[0] * up[0] + up[1] * up[1] + up[2] * up[2]).sqrt();
    if n > 0.0 {
        up = up.map(|v| v / n);
    } else {
        up = [0.0, 0.0, 1.0];
    }
    (
        f(internal, 3, 0) as usize,
        f(internal, 6, 3) as usize,
        pos,
        f(internal, 4, 9) / 15.0 * std::f32::consts::TAU,
        f(internal, 4, 16) / 15.0,
        f(internal, 3, 13) / 7.0,
        up,
    )
}

fn rgb(v: u32) -> [f32; 3] {
    [((v >> 16) & 0xFF) as f32 / 255.0, ((v >> 8) & 0xFF) as f32 / 255.0, (v & 0xFF) as f32 / 255.0]
}

/// The tag-block resources of a raw block whose info (offset, size,
/// section data size, resource data size, resources (0x10) at +0x10)
/// starts at `info`: (locator, bytes) for each. The section data size is
/// not where the resources start (Zanzibar: 0x88 against a struct running
/// to +0x188), so the `rsrc` marker is searched for in the block.
pub(crate) fn raw_resources<'a>(cache: &'a Cache, owner: &'a CacheFile, info: Struct<'_>) -> Result<Vec<(u16, &'a [u8])>, Error> {
    let raw = info.u32(0);
    if raw == u32::MAX || info.u32(4) == 0 {
        return Ok(Vec::new());
    }
    let (file, at) = geometry::block(cache, owner, raw)?;
    let d = &file.data;
    if d.get(at..at + 4) != Some(b"hklb") {
        return Err(Error::Format(format!("no 'blkh' block at {at:#x}")));
    }
    let end = (at + info.u32(4) as usize).min(d.len());
    let Some(rsrc) = d.get(at..end).and_then(|b| b.windows(4).position(|w| w == b"crsr")).map(|p| at + p) else {
        return Ok(Vec::new());
    };
    let mut out = Vec::new();
    for r in info.block(0x10, 0x10).iter().filter(|r| r.u8(0) == 0) {
        let off = rsrc + r.u32(12) as usize;
        if let Some(bytes) = d.get(off..off + r.u32(8) as usize) {
            out.push((r.u16(4), bytes));
        }
    }
    Ok(out)
}

/// Every decorator placement of a structure BSP (its root).
pub fn placements(cache: &Cache, bsp: Struct<'_>) -> Result<Vec<Placement>, Error> {
    let mut out = Vec::new();
    for d in bsp.block(0x234, 0x30).iter() {
        let centre = d.vec3(0x00);
        let side = d.u32(0x0C) as f32 * 8.0;
        let mut blocks: Vec<Vec<[u32; 6]>> = Vec::new();
        for b in d.block(0x10, 0x34).iter() {
            let mut words = Vec::new();
            for (locator, bytes) in raw_resources(cache, bsp.file, b)? {
                if locator == 0x00 {
                    for p in bytes.chunks_exact(0x18) {
                        let w = |i: usize| u32::from_le_bytes(p[i * 4..i * 4 + 4].try_into().unwrap());
                        words.push([w(0), w(1), w(2), w(3), w(4), w(5)]);
                    }
                }
            }
            blocks.push(words);
        }
        let groups = d.block(0x18, 0x18);
        let cells = d.block(0x20, 0x18);
        // Walk the octree from the root (cell 0), each leaf's groups
        // placed from its corner.
        let mut stack = vec![(0usize, [centre[0] - side / 2.0, centre[1] - side / 2.0, centre[2] - side / 2.0], side)];
        let mut seen = 0usize;
        while let Some((i, lo, size)) = stack.pop() {
            seen += 1;
            if seen > cells.count * 2 + 8 {
                break;
            }
            let Some(c) = cells.get(i) else { continue };
            let (first, count) = (c.u32(0x14) as usize, c.u16(0x12) as usize);
            if count > 0 && first != u32::MAX as usize {
                for g in (first..first + count).filter_map(|g| groups.get(g)) {
                    let set = g.u8(0) as usize;
                    let kind = g.u8(1);
                    let Some(words) = blocks.get(g.i16(6).max(0) as usize) else { continue };
                    let (start, n) = (g.u16(8) as usize, g.u16(0x0A) as usize);
                    for w in words.iter().skip(start).take(n) {
                        let (class, permutation, position, yaw, scale, tint_blend, up) = decode(w[0], w[1], lo);
                        out.push(Placement {
                            set, kind, class, permutation, position, yaw, scale, tint_blend, up,
                            tint: rgb(w[2]),
                            lightmap: rgb(w[3]),
                        });
                    }
                }
            }
            for k in 0..8 {
                let child = c.i16(k * 2);
                if child < 0 {
                    continue;
                }
                let h = size / 2.0;
                let corner = [
                    lo[0] + if k & 4 != 0 { h } else { 0.0 },
                    lo[1] + if k & 2 != 0 { h } else { 0.0 },
                    lo[2] + if k & 1 != 0 { h } else { 0.0 },
                ];
                stack.push((child as usize, corner, h));
            }
        }
    }
    Ok(out)
}

/// A decal decorator as the map stores it: Halo 2 builds no decal
/// geometry at run time, it draws the cache block's decal vertices
/// (locator 0x08: 0x20 each, position, texture coordinate, a second
/// coordinate, colour) through its decal indices (locator 0x10, u16), each
/// group's run given by its vertex start and count (+0x0C, +0x0E) and index
/// start and count (+0x10, +0x12); 4 vertices and 6 indices a placement,
/// in placement order (`halo2.dll` 0x9795c0 draws them).
#[derive(Debug, Clone)]
pub struct Decal {
    /// The decorator group it was drawn with (its index in the BSP's).
    pub group: usize,
    pub set: usize,
    pub class: usize,
    pub permutation: usize,
    /// World units.
    pub positions: Vec<[f32; 3]>,
    pub uvs: Vec<[f32; 2]>,
    /// The vertex colour, 0..1 (alpha last).
    pub colors: Vec<[f32; 4]>,
    /// Triangles into this decal's own vertices.
    pub triangles: Vec<[u32; 3]>,
}

/// Every decal decorator of a structure BSP (its root): the groups whose
/// placements carry decal geometry.
pub fn decals(cache: &Cache, bsp: Struct<'_>) -> Result<Vec<Decal>, Error> {
    let mut out = Vec::new();
    for d in bsp.block(0x234, 0x30).iter() {
        let mut blocks = Vec::new();
        for b in d.block(0x10, 0x34).iter() {
            let (mut words, mut verts, mut idx) = (Vec::new(), Vec::new(), Vec::new());
            for (locator, bytes) in raw_resources(cache, bsp.file, b)? {
                match locator {
                    0x00 => words = bytes.chunks_exact(0x18).map(|p| u32::from_le_bytes(p[0..4].try_into().unwrap())).collect(),
                    0x08 => verts = bytes.chunks_exact(0x20).map(|v| v.to_vec()).collect(),
                    0x10 => idx = bytes.chunks_exact(2).map(|c| u16::from_le_bytes([c[0], c[1]])).collect(),
                    _ => {}
                }
            }
            blocks.push((words, verts, idx));
        }
        let f = |b: &[u8], o: usize| f32::from_le_bytes(b[o..o + 4].try_into().unwrap());
        for (gi, g) in d.block(0x18, 0x18).iter().enumerate() {
            let (vstart, vcount) = (g.u16(0x0C) as usize, g.u16(0x0E) as usize);
            let (istart, icount) = (g.u16(0x10) as usize, g.u16(0x12) as usize);
            if vcount == 0 || icount == 0 {
                continue;
            }
            let Some((words, verts, idx)) = blocks.get(g.i16(6).max(0) as usize) else { continue };
            let (first, count) = (g.u16(8) as usize, g.u16(0x0A) as usize);
            let per_v = vcount / count.max(1);
            let per_i = icount / count.max(1);
            for k in 0..count {
                let Some(&internal) = words.get(first + k) else { continue };
                let v0 = vstart + k * per_v;
                let Some(vs) = verts.get(v0..v0 + per_v) else { continue };
                let Some(is) = idx.get(istart + k * per_i..istart + (k + 1) * per_i) else { continue };
                // Indices count from the block's first decal vertex.
                let triangles: Vec<[u32; 3]> = is
                    .chunks_exact(3)
                    .filter_map(|t| {
                        let r = |i: u16| (i as usize).checked_sub(v0).filter(|&x| x < per_v).map(|x| x as u32);
                        Some([r(t[0])?, r(t[1])?, r(t[2])?])
                    })
                    .collect();
                out.push(Decal {
                    group: gi,
                    set: g.u8(0) as usize,
                    class: (internal & 7) as usize,
                    permutation: ((internal >> 3) & 0x3F) as usize,
                    positions: vs.iter().map(|v| [f(v, 0), f(v, 4), f(v, 8)]).collect(),
                    uvs: vs.iter().map(|v| [f(v, 0x0C), f(v, 0x10)]).collect(),
                    colors: vs
                        .iter()
                        .map(|v| {
                            let c = u32::from_le_bytes(v[0x1C..0x20].try_into().unwrap());
                            let [r, g, b] = rgb(c);
                            [r, g, b, ((c >> 24) & 0xFF) as f32 / 255.0]
                        })
                        .collect(),
                    triangles,
                });
            }
        }
    }
    Ok(out)
}

/// One permutation of a decorator class (`DECR` class +0x0C, 0x28).
#[derive(Debug, Clone)]
pub struct Permutation {
    pub name: String,
    pub shader: usize,
    /// Bit 0 align to normal, 1 only on ground, 2 upright.
    pub flags: u8,
    /// The model (for a model class) or sprite index.
    pub index: usize,
    pub scale: [f32; 2],
    pub tint: [[f32; 3]; 2],
    pub base_map_tint: f32,
    pub lightmap_tint: f32,
}

#[derive(Debug, Clone)]
pub struct Class {
    pub name: String,
    pub kind: u8,
    pub scale: f32,
    pub permutations: Vec<Permutation>,
}

/// A decorator set's model: a run of the set's indices (a triangle list).
#[derive(Debug, Clone)]
pub struct Model {
    pub name: String,
    pub first: usize,
    pub count: usize,
}

#[derive(Debug, Clone, Copy, Default)]
pub struct Vertex {
    pub position: [f32; 3],
    pub normal: [f32; 3],
    pub uv: [f32; 2],
}

/// A decorator set (`DECR`): its shaders (+0x00, tag references), classes
/// (+0x10, 0x14: name, type, scale, permutations), models (+0x18, 8: name,
/// first index, index count), vertices (+0x20, 0x38: position, normal,
/// tangent, binormal, texture coordinate) and indices (+0x28, u16); the
/// vertices and indices may be in its raw block instead (info at +0x38,
/// resources at +0x48; locators 0x20 and 0x28).
#[derive(Debug, Clone, Default)]
pub struct Set {
    pub shaders: Vec<u32>,
    pub classes: Vec<Class>,
    pub models: Vec<Model>,
    pub vertices: Vec<Vertex>,
    pub indices: Vec<u16>,
}

fn vertices(bytes: &[u8]) -> Vec<Vertex> {
    let f = |b: &[u8], o: usize| f32::from_le_bytes(b[o..o + 4].try_into().unwrap());
    bytes
        .chunks_exact(0x38)
        .map(|v| Vertex {
            position: [f(v, 0), f(v, 4), f(v, 8)],
            normal: [f(v, 12), f(v, 16), f(v, 20)],
            uv: [f(v, 0x30), f(v, 0x34)],
        })
        .collect()
}

pub fn set(cache: &Cache, tag: Struct<'_>) -> Result<Set, Error> {
    let mut s = Set { shaders: tag.block(0x00, 8).iter().map(|r| r.u32(4)).collect(), ..Default::default() };
    for c in tag.block(0x10, 0x14).iter() {
        let permutations = c
            .block(0x0C, 0x28)
            .iter()
            .map(|p| Permutation {
                name: p.sid(0).to_string(),
                shader: p.u8(4) as usize,
                flags: p.u8(8),
                index: p.u8(0x0A) as usize,
                scale: [p.f32(0x0C), p.f32(0x10)],
                tint: [rgb(p.u32(0x14)), rgb(p.u32(0x18))],
                base_map_tint: p.f32(0x1C),
                lightmap_tint: p.f32(0x20),
            })
            .collect();
        s.classes.push(Class { name: c.sid(0).to_string(), kind: c.u8(4), scale: c.f32(8), permutations });
    }
    s.models = tag
        .block(0x18, 8)
        .iter()
        .map(|m| Model { name: m.sid(0).to_string(), first: m.u16(4) as usize, count: m.u16(6) as usize })
        .collect();
    let inline = tag.block(0x20, 0x38);
    if let Some(first) = inline.get(0).filter(|_| inline.get(inline.count - 1).is_some()) {
        s.vertices = vertices(first.bytes(0, inline.count * 0x38));
        s.indices = tag.block(0x28, 2).iter().map(|i| i.u16(0)).collect();
    } else {
        for (locator, bytes) in raw_resources(cache, tag.file, tag.at(0x38))? {
            match locator {
                0x20 => s.vertices = vertices(bytes),
                0x28 => s.indices = bytes.chunks_exact(2).map(|c| u16::from_le_bytes([c[0], c[1]])).collect(),
                _ => {}
            }
        }
    }
    Ok(s)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Zanzibar's first group: its leaf corner and three placements land
    /// on the ground there (checked against the BSP's surface).
    #[test]
    fn decode_fields() {
        let (class, perm, pos, yaw, scale, tint, up) = decode(0x0000_0000, 0xFFFF_FFFF, [0.0, 0.0, 0.0]);
        assert_eq!((class, perm), (0, 0));
        assert_eq!(pos, [8.0, 8.0, 8.0]);
        assert_eq!((yaw, scale, tint), (0.0, 0.0, 0.0));
        let s = (1.0f32 / 3.0).sqrt();
        assert!((up[0] + s).abs() < 1e-5 && (up[2] + s).abs() < 1e-5);
        // Class 5, permutation 9, yaw 15/15, tint 7/7, scale 15/15, up +z.
        let internal = 5 | (9 << 3) | (15 << 9) | (7 << 13) | (15 << 16) | (0x7 << 20) | (0x7 << 24) | (0xF << 28);
        let (class, perm, pos, yaw, scale, tint, up) = decode(internal, 0, [1.0, 2.0, 3.0]);
        assert_eq!((class, perm), (5, 9));
        assert_eq!(pos, [1.0, 2.0, 3.0]);
        assert!((yaw - std::f32::consts::TAU).abs() < 1e-5);
        assert_eq!((scale, tint), (1.0, 1.0));
        assert!(up[2] > 0.99, "{up:?}");
    }
}
