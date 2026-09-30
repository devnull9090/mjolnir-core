//! Write cooked `UStaticMesh` geometry in the game's own serialisation, by
//! rewriting a shipped mesh's LOD array in place.
//!
//! # Why in place
//!
//! Content cooked by stock UE 5.5 does not load in this build: a cooked actor
//! dies with `StaticMeshComponent: Bad export index`, and a cooked
//! `UStaticMesh` dies on its own with a `TArray` resize to `0x80000002`
//! (see `unreal/MJOLNIRMapKit/README.md`). Both are serialisation disagreements
//! between stock UE and the game's `5.5.4 i343-Meteorite` fork.
//!
//! So nothing new is authored. A **shipped** mesh package is taken exactly as
//! the game ships it and only the bytes of its `FStaticMeshRenderData` LOD
//! array are replaced. Everything the fork is fussy about — the unversioned
//! property block, the native tail, the Nanite/bounds tail — is carried
//! through untouched, so the package still deserialises the way its own engine
//! wrote it. This is the same trick that made texture swapping work.
//!
//! # What the caller has to respect
//!
//! * **Pick a donor with no Nanite pages.** The engine renders the Nanite
//!   representation when a mesh has one and ignores the classic LOD this
//!   writes. `/Engine/BasicShapes/Cube` is the reference donor: 54 vertices,
//!   one material, one inlined LOD, no Nanite, and it ships.
//! * **Keep inside the donor's bounds.** The bounds live in the tail this
//!   preserves, and the engine culls against them, so geometry is expected
//!   pre-normalised into the donor's box; scale it back up on the component.
//! * **Sections may only name materials the donor has.** The material slots
//!   are properties, which are not rewritten.
//!
//! The gate is that [`parse_static_mesh`](crate::mesh::parse_static_mesh) —
//! which is verified against the game's own cooked meshes — reads back exactly
//! what was written.

use crate::mesh::Error;
use crate::unversioned::{Ctx, Walker};

/// The geometry to write. One section per material slot used.
#[derive(Debug, Default, Clone)]
pub struct Geometry {
    /// xyz per vertex, in the donor's local space.
    pub positions: Vec<f32>,
    /// xyz per vertex; normalised. Empty means "straight up".
    pub normals: Vec<f32>,
    /// uv per vertex. Empty means all zero.
    pub uvs: Vec<f32>,
    /// Triangle list.
    pub indices: Vec<u32>,
    /// `(material_index, first_index, triangle_count)`. Empty means one
    /// section over everything using material 0.
    pub sections: Vec<(i32, u32, u32)>,
}

impl Geometry {
    pub fn vertices(&self) -> usize {
        self.positions.len() / 3
    }

    fn sections_or_default(&self) -> Vec<(i32, u32, u32)> {
        if self.sections.is_empty() {
            vec![(0, 0, (self.indices.len() / 3) as u32)]
        } else {
            self.sections.clone()
        }
    }
}

/// The donor's own flag words, so the rewrite keeps its exact block shape.
#[derive(Debug, Clone, Copy)]
struct DonorFlags {
    lod_strip: u16,
    buffer_strip: u16,
    color_stride: u32,
}

fn u16le(out: &mut Vec<u8>, v: u16) {
    out.extend_from_slice(&v.to_le_bytes());
}
fn u32le(out: &mut Vec<u8>, v: u32) {
    out.extend_from_slice(&v.to_le_bytes());
}
fn f32le(out: &mut Vec<u8>, v: f32) {
    out.extend_from_slice(&v.to_le_bytes());
}

/// IEEE binary16, matching the `half` decoder the reader uses.
fn to_half(v: f32) -> u16 {
    let bits = v.to_bits();
    let sign = ((bits >> 16) & 0x8000) as u16;
    let mut exp = ((bits >> 23) & 0xff) as i32 - 127 + 15;
    let mant = bits & 0x007f_ffff;
    if exp <= 0 {
        // Subnormal or zero; flush to zero, which is right for UVs.
        return sign;
    }
    if exp >= 0x1f {
        return sign | 0x7c00;
    }
    // Round to nearest even on the 13 dropped mantissa bits.
    let mut m = (mant >> 13) as u16;
    if mant & 0x1000 != 0 && (mant & 0x0fff != 0 || m & 1 != 0) {
        m += 1;
        if m == 0x400 {
            m = 0;
            exp += 1;
            if exp >= 0x1f {
                return sign | 0x7c00;
            }
        }
    }
    sign | ((exp as u16) << 10) | m
}

fn pack_i8(v: f32) -> u8 {
    (v.clamp(-1.0, 1.0) * 127.0).round() as i8 as u8
}

/// Read the donor's flag words by walking its LOD array far enough to see
/// them, so the rewrite mirrors the shape the engine wrote rather than
/// inventing one.
fn donor_flags(ctx: &Ctx<'_>, export: &[u8], span_start: usize) -> Result<DonorFlags, Error> {
    let mut w = Walker::new(ctx, export);
    w.skip(span_start)?;
    let lod_count = w.u32()?;
    if lod_count == 0 {
        return Err(Error::Format("donor has no LODs".into()));
    }
    // Walk LODs until one carries buffers; a cooked-out LOD has none.
    for _ in 0..lod_count {
        let lod_strip = w.u16()?;
        let section_count = w.u32()?;
        w.skip(section_count as usize * 10 * 4)?;
        let _max_deviation = w.f32()?;
        let cooked_out = w.u32()?;
        let inlined = w.u32()?;
        if cooked_out != 0 {
            continue;
        }
        if inlined == 0 {
            return Err(Error::Format(
                "donor's LOD is streamed; pick one with inlined buffers".into(),
            ));
        }
        let _extra = w.u32()?;
        let buffer_strip = w.u16()?;
        // Positions, then the vertex buffer, to reach the colour stride.
        let _stride = w.u32()?;
        let vertices = w.u32()?;
        let (elem, num) = (w.u32()?, w.u32()?);
        w.skip(elem as usize * num as usize)?;
        let _ = vertices;
        let _vb_strip = w.u16()?;
        let _num_tex = w.u32()?;
        let _verts2 = w.u32()?;
        let _full_uv = w.u32()?;
        let _hq_tan = w.u32()?;
        let (te, tn) = (w.u32()?, w.u32()?);
        w.skip(te as usize * tn as usize)?;
        let (ue_, un) = (w.u32()?, w.u32()?);
        w.skip(ue_ as usize * un as usize)?;
        let _colour_strip = w.u16()?;
        let color_stride = w.u32()?;
        return Ok(DonorFlags {
            lod_strip,
            buffer_strip,
            color_stride,
        });
    }
    Err(Error::Format("donor has no LOD with buffers".into()))
}

/// One `FRawStaticIndexBuffer` holding nothing.
fn empty_index_buffer(out: &mut Vec<u8>) {
    u32le(out, 0); // bIs32Bit
    u32le(out, 1); // bulk element size
    u32le(out, 0); // bulk count
    u32le(out, 0); // bShouldExpandTo32Bit
}

/// Serialise the LOD array: a single inlined LOD carrying `geo`.
fn write_lod_array(geo: &Geometry, flags: DonorFlags) -> Vec<u8> {
    let verts = geo.vertices();
    let sections = geo.sections_or_default();
    let mut out = Vec::new();

    u32le(&mut out, 1); // one LOD
    u16le(&mut out, flags.lod_strip);
    u32le(&mut out, sections.len() as u32);
    for (material, first, tris) in &sections {
        u32le(&mut out, *material as u32);
        u32le(&mut out, *first);
        u32le(&mut out, *tris);
        u32le(&mut out, 0); // MinVertexIndex
        u32le(&mut out, verts.saturating_sub(1) as u32); // MaxVertexIndex
        u32le(&mut out, 1); // bEnableCollision
        u32le(&mut out, 1); // bCastShadow
        u32le(&mut out, 0); // bForceOpaque
        u32le(&mut out, 1); // bVisibleInRayTracing
        u32le(&mut out, 1); // bAffectDistanceFieldLighting
    }
    f32le(&mut out, 0.0); // MaxDeviation
    u32le(&mut out, 0); // not cooked out
    u32le(&mut out, 1); // inlined
    u32le(&mut out, 0); // the pre-buffer word, always zero in this cook

    let block_start = out.len();

    // --- FStaticMeshLODResources::SerializeBuffers -------------------------
    u16le(&mut out, flags.buffer_strip);

    // FPositionVertexBuffer
    u32le(&mut out, 12);
    u32le(&mut out, verts as u32);
    u32le(&mut out, 12);
    u32le(&mut out, verts as u32);
    for i in 0..verts {
        for k in 0..3 {
            f32le(&mut out, geo.positions[i * 3 + k]);
        }
    }

    // FStaticMeshVertexBuffer: one UV channel, half UVs, packed tangents.
    u16le(&mut out, 0);
    u32le(&mut out, 1); // NumTexCoords
    u32le(&mut out, verts as u32);
    u32le(&mut out, 0); // full-precision UVs off
    u32le(&mut out, 0); // high-precision tangents off
    u32le(&mut out, 8); // tangent element size
    u32le(&mut out, verts as u32);
    for i in 0..verts {
        let n = if geo.normals.len() >= (i + 1) * 3 {
            [
                geo.normals[i * 3],
                geo.normals[i * 3 + 1],
                geo.normals[i * 3 + 2],
            ]
        } else {
            [0.0, 0.0, 1.0]
        };
        // A tangent perpendicular to the normal; any consistent choice works
        // for flat-shaded terrain, and the reader only takes the normal back.
        let up = if n[2].abs() > 0.9 {
            [1.0f32, 0.0, 0.0]
        } else {
            [0.0f32, 0.0, 1.0]
        };
        let mut t = [
            up[1] * n[2] - up[2] * n[1],
            up[2] * n[0] - up[0] * n[2],
            up[0] * n[1] - up[1] * n[0],
        ];
        let len = (t[0] * t[0] + t[1] * t[1] + t[2] * t[2]).sqrt().max(1e-6);
        for c in t.iter_mut() {
            *c /= len;
        }
        out.extend_from_slice(&[pack_i8(t[0]), pack_i8(t[1]), pack_i8(t[2]), 127]);
        out.extend_from_slice(&[pack_i8(n[0]), pack_i8(n[1]), pack_i8(n[2]), 127]);
    }
    u32le(&mut out, 4); // texcoord element size (half2)
    u32le(&mut out, verts as u32);
    for i in 0..verts {
        let (u, v) = if geo.uvs.len() >= (i + 1) * 2 {
            (geo.uvs[i * 2], geo.uvs[i * 2 + 1])
        } else {
            (0.0, 0.0)
        };
        out.extend_from_slice(&to_half(u).to_le_bytes());
        out.extend_from_slice(&to_half(v).to_le_bytes());
    }

    // FColorVertexBuffer: empty.
    u16le(&mut out, 0);
    u32le(&mut out, flags.color_stride);
    u32le(&mut out, 0);

    // FRawStaticIndexBuffer: 16-bit when the vertex count allows.
    let wide = verts > u16::MAX as usize;
    let index_bytes: Vec<u8> = if wide {
        geo.indices.iter().flat_map(|i| i.to_le_bytes()).collect()
    } else {
        geo.indices
            .iter()
            .flat_map(|i| (*i as u16).to_le_bytes())
            .collect()
    };
    u32le(&mut out, wide as u32);
    u32le(&mut out, 1); // bulk element size is one byte
    u32le(&mut out, index_bytes.len() as u32);
    out.extend_from_slice(&index_bytes);
    u32le(&mut out, 0); // bShouldExpandTo32Bit

    // The optional buffers, in the order the reader expects, gated by the
    // donor's own strip flags. Each is emitted empty.
    let editor_stripped = flags.buffer_strip & 0x01 != 0;
    let reversed_stripped = flags.buffer_strip & 0x0400 != 0;
    let raytracing_stripped = flags.buffer_strip & 0x0800 != 0;
    if !reversed_stripped {
        empty_index_buffer(&mut out);
    }
    empty_index_buffer(&mut out); // depth-only is never stripped
    if !reversed_stripped {
        empty_index_buffer(&mut out);
    }
    if !editor_stripped {
        empty_index_buffer(&mut out);
    }
    if !raytracing_stripped {
        u32le(&mut out, 1); // bulk element size
        u32le(&mut out, 0); // no ray-tracing blob
    }

    // One area-weighted sampler per section plus one for the whole mesh.
    for _ in 0..=sections.len() {
        u32le(&mut out, 0); // probabilities
        u32le(&mut out, 0); // aliases
        f32le(&mut out, 0.0); // total weight
    }

    let block_len = (out.len() - block_start) as u32;
    // FStaticMeshBuffersSize: serialized, depth-only, reversed.
    u32le(&mut out, block_len);
    u32le(&mut out, 0);
    u32le(&mut out, 0);
    out
}

/// Replace a shipped mesh export's geometry, keeping every other byte.
///
/// Returns the new export bytes. The caller repacks them into the package.
pub fn rewrite_static_mesh(
    ctx: &Ctx<'_>,
    export: &[u8],
    geo: &Geometry,
) -> Result<Vec<u8>, Error> {
    if geo.positions.len() % 3 != 0 {
        return Err(Error::Format("positions are not a multiple of 3".into()));
    }
    if geo.indices.len() % 3 != 0 {
        return Err(Error::Format("indices are not a multiple of 3".into()));
    }
    if let Some(bad) = geo.indices.iter().find(|i| **i as usize >= geo.vertices()) {
        return Err(Error::Format(format!(
            "index {bad} is past the {} vertices",
            geo.vertices()
        )));
    }
    let parsed = crate::mesh::parse_static_mesh(ctx, export, None)?;
    if parsed.nanite_report.is_some() {
        return Err(Error::Format(
            "donor has Nanite pages; the engine would render those and ignore this LOD".into(),
        ));
    }
    let (start, end) = parsed
        .lod_span
        .ok_or_else(|| Error::Format("donor has no LOD array span".into()))?;
    let flags = donor_flags(ctx, export, start)?;

    let mut out = Vec::with_capacity(export.len() + geo.positions.len() * 4);
    out.extend_from_slice(&export[..start]);
    out.extend_from_slice(&write_lod_array(geo, flags));
    out.extend_from_slice(&export[end..]);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn half_round_trips_through_the_readers_decoder() {
        for v in [0.0f32, 1.0, 0.5, -0.25, 12.5, 0.125] {
            let h = to_half(v);
            // Mirror of the reader's `half`.
            let sign = if h & 0x8000 != 0 { -1.0f32 } else { 1.0 };
            let exp = ((h >> 10) & 0x1f) as i32;
            let mant = (h & 0x3ff) as f32;
            let got = if exp == 0 {
                sign * mant / 1024.0 * 2f32.powi(-14)
            } else {
                sign * (1.0 + mant / 1024.0) * 2f32.powi(exp - 15)
            };
            assert!((got - v).abs() < 0.01, "{v} came back as {got}");
        }
    }

    #[test]
    fn packing_a_normal_survives_the_readers_unpack() {
        for v in [-1.0f32, -0.5, 0.0, 0.5, 1.0] {
            let back = pack_i8(v) as i8 as f32 / 127.0;
            assert!((back - v).abs() < 0.01, "{v} came back as {back}");
        }
    }
}
