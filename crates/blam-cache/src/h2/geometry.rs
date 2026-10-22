//! Halo 2 render geometry sections: BSP clusters, instanced geometry
//! definitions and render models (`mode`) share one "global geometry
//! section" layout.
//!
//! A section's data is raw, outside the tag: its geometry block info gives
//! the block's offset, size, header size and resource size, and a block of
//! 16-byte resource entries (at +0x28 in a cluster or an instanced geometry
//! definition, +0x38 in a render model section). The offset's top two bits
//! pick the file (0 the tag's own, 1 `mainmenu.map`, 2 `shared.map`, 3
//! `single_player_shared.map`). The block is `blkh`, u32 resource size, the
//! section struct (header size bytes: 0x48 for BSP sections, 0x78 for render
//! models), `rsrc`, then the resources, each at its entry's offset from the
//! `rsrc` marker, then `blkf`.
//!
//! A resource entry is u8 type (0 a tag block, 1 tag data, 2 a vertex
//! buffer), u8, u16 locator (the section struct field it fills: 0x00 parts,
//! 0x20 indices, 0x38 vertex buffer descriptors), u16, i16 element size or
//! vertex buffer index, u32 size, u32 offset. Parts are 72 bytes: i16 type,
//! u16 flags, i16 material, i16 first index, i16 index count, ... A vertex
//! buffer descriptor is 32 bytes whose first two are the vertex type and
//! stride; MCC's types are the Vista ones, all plain floats:
//!
//! | type | stride | contents |
//! |---|---|---|
//! | 0x01 | 12 | position |
//! | 0x02, 0x04, 0x06 | 16, 20, 20 | position (rigid boned, skinned), then node indices and weights |
//! | 0x17 | 8 | texture coordinate |
//! | 0x19 | 36 | normal, binormal, tangent |
//! | 0x1D | 8 | lightmap coordinate |
//! | 0x2F | 12 | incident light direction |
//!
//! BSP sections are triangle lists that wind counter-clockwise about their
//! vertex normals (Lockout, 7,048 of 7,049 triangles; the opposite of CE's
//! BSP); render model parts are strips unless flag bit 3 says list.
//! Layouts from docs/h2_cache_format.md, checked on Lockout and shared.map.

use crate::h2::{Cache, CacheFile, Struct};
use crate::Error;

#[derive(Debug, Clone, Copy, Default)]
pub struct Vertex {
    pub position: [f32; 3],
    pub uv: [f32; 2],
    pub normal: [f32; 3],
    pub binormal: [f32; 3],
    pub tangent: [f32; 3],
    pub lightmap_uv: [f32; 2],
    pub incident: [f32; 3],
}

#[derive(Debug, Clone, Copy)]
pub struct Part {
    /// 0 not drawn, 1 opaque shadow only, 2 opaque shadow casting, 3 opaque
    /// non-shadowing, 4 transparent, 5 lightmap only.
    pub kind: i16,
    pub flags: u16,
    pub material: i16,
    pub first: usize,
    pub count: usize,
}

impl Part {
    /// Bit 3, "override triangle list": the indices are a list, not a strip.
    pub fn is_list(&self) -> bool {
        self.flags & 8 != 0
    }
    /// Whether the part draws in the render pass: opaque shadow casting
    /// (2), opaque (3) or transparent (4); not the shadow-only (1) or
    /// lightmap-only (5) parts.
    pub fn is_drawn(&self) -> bool {
        matches!(self.kind, 2..=4)
    }
}

#[derive(Debug, Clone, Default)]
pub struct Section {
    pub vertices: Vec<Vertex>,
    pub parts: Vec<Part>,
    pub indices: Vec<u16>,
    /// Whether the section has a lightmap coordinate per vertex.
    pub has_lightmap_uv: bool,
    pub has_incident: bool,
}

impl Section {
    /// A part's triangles as vertex index triples, front faces
    /// counter-clockwise.
    pub fn triangles(&self, part: &Part) -> Vec<[u32; 3]> {
        let end = (part.first + part.count).min(self.indices.len());
        let idx = &self.indices[part.first.min(end)..end];
        let mut out = Vec::new();
        if part.is_list() {
            for t in idx.chunks_exact(3) {
                out.push([t[0] as u32, t[1] as u32, t[2] as u32]);
            }
        } else {
            // A strip: every other triangle flips; a repeated index is a
            // degenerate join, dropped.
            for k in 0..idx.len().saturating_sub(2) {
                let (a, b, c) = (idx[k], idx[k + 1], idx[k + 2]);
                if a == b || b == c || a == c {
                    continue;
                }
                out.push(if k % 2 == 0 { [a as u32, b as u32, c as u32] } else { [a as u32, c as u32, b as u32] });
            }
        }
        out.retain(|t| t.iter().all(|&i| (i as usize) < self.vertices.len()));
        out
    }
}

/// How a section's positions and texture coordinates are packed: each
/// compressed one is stored in -1..1 across its bounds. BSP sections are
/// plain world positions; render models (the sky's included) store both
/// compressed, against the model's compression info (7 ranges: position x,
/// y, z, texture u, v, secondary u, v). Lockout's sky spans hundreds of world
/// units from vertices that all lie within -1..1.
#[derive(Debug, Clone, Copy)]
pub struct Compression {
    pub position: Option<[[f32; 2]; 3]>,
    pub texcoord: Option<[[f32; 2]; 2]>,
}

impl Compression {
    pub const NONE: Compression = Compression { position: None, texcoord: None };

    /// From a section's compression flags (bit 0 position, bit 1 texture
    /// coordinate) and a compression info element (0x38 bytes of ranges).
    pub fn from(flags: u16, info: Option<Struct<'_>>) -> Compression {
        let Some(c) = info else { return Compression::NONE };
        let range = |k: usize| [c.f32(k * 8), c.f32(k * 8 + 4)];
        Compression {
            position: (flags & 1 != 0).then(|| [range(0), range(1), range(2)]),
            texcoord: (flags & 2 != 0).then(|| [range(3), range(4)]),
        }
    }
}

fn expand(v: f32, r: [f32; 2]) -> f32 {
    r[0] + (v + 1.0) * 0.5 * (r[1] - r[0])
}

fn f32s<const N: usize>(b: &[u8], at: usize) -> [f32; N] {
    let mut v = [0f32; N];
    for (i, x) in v.iter_mut().enumerate() {
        *x = f32::from_le_bytes(b[at + i * 4..at + i * 4 + 4].try_into().unwrap());
    }
    v
}

/// The raw block a geometry block info points at, in whichever file holds it.
fn block<'a>(cache: &'a Cache, owner: &'a CacheFile, raw: u32) -> Result<(&'a CacheFile, usize), Error> {
    let file = match raw >> 30 {
        0 => owner,
        2 => cache.shared.as_ref().ok_or_else(|| Error::Unsupported("section data in shared.map, which is not open".into()))?,
        loc => return Err(Error::Unsupported(format!("section data in shared file {loc} (mainmenu or single-player shared)"))),
    };
    Ok((file, (raw & 0x3FFF_FFFF) as usize))
}

/// Read the section whose geometry block info is `info` (a struct in
/// `owner`: u32 offset, u32 size, u32 header size, u32 resource size, the
/// resources block), with `vertex_count` vertices.
pub fn read(
    cache: &Cache,
    owner: &CacheFile,
    info: Struct<'_>,
    vertex_count: usize,
    compression: Compression,
) -> Result<Section, Error> {
    let raw = info.u32(0);
    if raw == u32::MAX {
        return Ok(Section::default());
    }
    let header_size = info.u32(8) as usize;
    let resources = info.block(16, 16);
    let (file, at) = block(cache, owner, raw)?;
    let d = &file.data;
    if d.get(at..at + 4) != Some(b"hklb") {
        return Err(Error::Format(format!("no 'blkh' section block at {at:#x} in {}", file.path.display())));
    }
    let rsrc = at + 8 + header_size;
    if d.get(rsrc..rsrc + 4) != Some(b"crsr") {
        return Err(Error::Format(format!("no 'rsrc' marker at {rsrc:#x}")));
    }
    let mut s = Section { vertices: vec![Vertex::default(); vertex_count], ..Default::default() };
    let mut types: Vec<(u8, usize)> = Vec::new();
    let mut buffers: Vec<(usize, &[u8])> = Vec::new();
    for r in resources.iter() {
        let kind = r.u8(0);
        let locator = r.u16(2);
        let index = r.i16(6);
        let size = r.u32(8) as usize;
        let off = rsrc + r.u32(12) as usize;
        let bytes = d.get(off..off + size).ok_or_else(|| Error::Format(format!("resource at {off:#x} runs past the file")))?;
        match (kind, locator) {
            (0, 0x00) => {
                for p in bytes.chunks_exact(72) {
                    let i16_at = |o: usize| i16::from_le_bytes([p[o], p[o + 1]]);
                    s.parts.push(Part {
                        kind: i16_at(0),
                        flags: u16::from_le_bytes([p[2], p[3]]),
                        material: i16_at(4),
                        first: i16_at(6) as u16 as usize,
                        count: i16_at(8) as u16 as usize,
                    });
                }
            }
            (0, 0x20) => s.indices = bytes.chunks_exact(2).map(|c| u16::from_le_bytes([c[0], c[1]])).collect(),
            (0, 0x38) => types = bytes.chunks_exact(32).map(|c| (c[0], c[1] as usize)).collect(),
            (2, _) if index >= 0 => buffers.push((index as usize, bytes)),
            _ => {}
        }
    }
    let mut has_position = false;
    for (index, bytes) in buffers {
        let Some(&(ty, stride)) = types.get(index) else { continue };
        if stride == 0 {
            continue;
        }
        let n = vertex_count.min(bytes.len() / stride);
        for (i, v) in s.vertices.iter_mut().enumerate().take(n) {
            let o = i * stride;
            match (ty, stride) {
                // Plain (0x01), rigid boned (0x02) and skinned (0x04, 0x06)
                // positions: the node indices and weights after the first 12
                // bytes are not needed for a model staged in its rest pose.
                (0x01, 12) | (0x02, 16) | (0x04 | 0x06, 20) => {
                    let p: [f32; 3] = f32s(bytes, o);
                    v.position = match compression.position {
                        Some(r) => [expand(p[0], r[0]), expand(p[1], r[1]), expand(p[2], r[2])],
                        None => p,
                    };
                }
                (0x17, 8) => {
                    let t: [f32; 2] = f32s(bytes, o);
                    v.uv = match compression.texcoord {
                        Some(r) => [expand(t[0], r[0]), expand(t[1], r[1])],
                        None => t,
                    };
                }
                (0x19, 36) => {
                    v.normal = f32s(bytes, o);
                    v.binormal = f32s(bytes, o + 12);
                    v.tangent = f32s(bytes, o + 24);
                }
                (0x1D, 8) => v.lightmap_uv = f32s(bytes, o),
                (0x2F, 12) => v.incident = f32s(bytes, o),
                _ => {}
            }
        }
        match (ty, stride) {
            (0x01, 12) | (0x02, 16) | (0x04 | 0x06, 20) => has_position = true,
            (0x1D, _) => s.has_lightmap_uv = true,
            (0x2F, _) => s.has_incident = true,
            _ => {}
        }
    }
    if vertex_count > 0 && !has_position {
        let kinds: Vec<String> = types.iter().map(|(t, w)| format!("{t:#04x}/{w}")).collect();
        return Err(Error::Unsupported(format!("no position buffer read here (vertex types {})", kinds.join(", "))));
    }
    Ok(s)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn section(indices: Vec<u16>, vertices: usize) -> Section {
        Section { vertices: vec![Vertex::default(); vertices], indices, ..Default::default() }
    }

    /// A compressed value spans its bounds from -1 to 1.
    #[test]
    fn compressed_values_span_their_bounds() {
        assert_eq!(expand(-1.0, [-322.0, 408.0]), -322.0);
        assert_eq!(expand(1.0, [-322.0, 408.0]), 408.0);
        assert_eq!(expand(0.0, [0.0, 1.0]), 0.5);
    }

    /// A list is read three at a time; a strip alternates and drops joins.
    #[test]
    fn lists_and_strips_give_the_same_winding() {
        let s = section(vec![0, 1, 2, 2, 1, 3], 4);
        let list = Part { kind: 2, flags: 8, material: 0, first: 0, count: 6 };
        assert_eq!(s.triangles(&list), vec![[0, 1, 2], [2, 1, 3]]);
        let s = section(vec![0, 1, 2, 3, 3, 4], 5);
        let strip = Part { kind: 2, flags: 0, material: 0, first: 0, count: 6 };
        assert_eq!(s.triangles(&strip), vec![[0, 1, 2], [1, 3, 2]]);
    }
}
