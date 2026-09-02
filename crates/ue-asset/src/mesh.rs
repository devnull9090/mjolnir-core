//! Cooked `UStaticMesh` render data: LODs, sections, vertex and index
//! buffers — the visual geometry the Blam tags deliberately do not carry.
//!
//! Layout verified byte-by-byte against this game's cook (UE 5.5; meshes
//! cooked under `Nanite/` folders serialize the same stream): after the
//! unversioned properties and the object guard come strip flags, `bCooked`,
//! BodySetup and NavCollision references and the lighting guid, a socket
//! count, then `FStaticMeshRenderData` as a plain LOD array. A LOD is either
//! inlined (buffers follow directly) or streamed, with a bulk-data header
//! pointing into the package's `.ubulk`. The buffer block does not stop at
//! the main index buffer: reversed, depth-only and wireframe index buffers,
//! a ray-tracing blob and area-weighted triangle samplers follow, gated by
//! the block's strip flags, and every LOD closes with the three
//! `FStaticMeshBuffersSize` words — a multi-LOD mesh misparses without them.
//! Cross-checked against CUE4Parse's `FStaticMeshLODResources`.

use crate::unversioned::{Ctx, Error as PropError, Keep, Walker};

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error(transparent)]
    Props(#[from] PropError),
    #[error("mesh data ends early at {0:#x}")]
    Eof(usize),
    #[error("{0}")]
    Format(String),
}

#[derive(Debug, Clone)]
pub struct Section {
    pub material_index: i32,
    pub first_index: u32,
    pub num_triangles: u32,
}

#[derive(Debug, Default)]
pub struct Lod {
    pub sections: Vec<Section>,
    /// xyz per vertex.
    pub positions: Vec<f32>,
    /// Unpacked tangent-frame normals, xyz per vertex.
    pub normals: Vec<f32>,
    /// First UV channel, uv per vertex.
    pub uvs: Vec<f32>,
    pub indices: Vec<u32>,
    /// False when the LOD's buffers live in the `.ubulk`.
    pub inlined: bool,
}

#[derive(Debug, Default)]
pub struct StaticMeshData {
    /// Material slot names paired with their import-map object reference
    /// (`FPackageIndex`: negative is an import).
    pub materials: Vec<(String, i32)>,
    pub lods: Vec<Lod>,
}

/// Parse a `StaticMesh` export. `ubulk` carries the streamed LOD buffers when
/// the package has one.
pub fn parse_static_mesh(
    ctx: &Ctx<'_>,
    data: &[u8],
    ubulk: Option<&[u8]>,
) -> Result<StaticMeshData, Error> {
    let mut w = Walker::new(ctx, data);
    let props = w.read_object("StaticMesh", Keep::Names(&["StaticMaterials"]))?;

    let mut out = StaticMeshData::default();
    if let Some(crate::unversioned::Value::Array(list)) = props.get("StaticMaterials") {
        for entry in list {
            if let crate::unversioned::Value::Struct(fields) = entry {
                let slot = fields
                    .get("MaterialSlotName")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();
                let object = fields
                    .get("MaterialInterface")
                    .and_then(|v| v.as_object())
                    .unwrap_or(0);
                out.materials.push((slot, object));
            }
        }
    }

    // UStaticMesh native tail.
    let _strip = w.u16()?;
    let cooked = w.u32()?;
    if cooked == 0 {
        return Err(Error::Format("mesh is not cooked".into()));
    }
    let _body_setup = w.u32()?;
    let _nav_collision = w.u32()?;
    w.skip(16)?; // lighting guid
    let sockets = w.u32()?;
    if sockets > 64 {
        return Err(Error::Format(format!("{sockets} sockets is implausible")));
    }
    // Sockets are object references, four bytes each.
    w.skip(sockets as usize * 4)?;

    // FStaticMeshRenderData: LOD array.
    let lod_count = w.u32()?;
    if lod_count > 16 {
        return Err(Error::Format(format!("{lod_count} LODs is implausible")));
    }
    let trace = std::env::var_os("UE_ASSET_TRACE").is_some();
    for lod_index in 0..lod_count {
        let mut lod = Lod::default();
        let _strip = w.u16()?;
        let section_count = w.u32()?;
        if section_count > 256 {
            return Err(Error::Format(format!("{section_count} sections is implausible")));
        }
        for _ in 0..section_count {
            let material_index = w.u32()? as i32;
            let first_index = w.u32()?;
            let num_triangles = w.u32()?;
            let _min_vertex = w.u32()?;
            let _max_vertex = w.u32()?;
            let _enable_collision = w.u32()?;
            let _cast_shadow = w.u32()?;
            let _force_opaque = w.u32()?;
            let _visible_in_ray_tracing = w.u32()?;
            let _affect_distance_field_lighting = w.u32()?;
            lod.sections.push(Section {
                material_index,
                first_index,
                num_triangles,
            });
        }
        let _max_deviation = w.f32()?;
        let lod_cooked_out = w.u32()?;
        let inlined = w.u32()?;
        if trace {
            eprintln!(
                "lod {lod_index}: {} section(s), cooked-out {lod_cooked_out}, inlined {inlined}, at {:#x}",
                lod.sections.len(),
                w.pos
            );
        }
        if lod_cooked_out != 0 {
            out.lods.push(lod);
            continue;
        }
        if inlined != 0 {
            lod.inlined = true;
            // One as-yet-unnamed u32 (always 0 in this cook) precedes the
            // buffer block.
            let extra = w.u32()?;
            if extra != 0 {
                return Err(Error::Format(format!("pre-buffer word is {extra}, expected 0")));
            }
            read_buffers(&mut w, &mut lod, trace)?;
        } else {
            // FByteBulkData header, payload in the .ubulk.
            let flags = w.u32()?;
            let size64 = flags & 0x2000 != 0; // BULKDATA_Size64Bit
            let (count, size_on_disk) = if size64 {
                (w.u64()? as usize, w.u64()? as usize)
            } else {
                (w.u32()? as usize, w.u32()? as usize)
            };
            let offset = w.u64()? as usize;
            if trace {
                eprintln!(
                    "  bulk: flags {flags:#x} count {count} size {size_on_disk} offset {offset:#x}"
                );
            }
            let _ = count;
            // Availability metadata after the bulk header: depth-only
            // triangle count, packed flags, then per-buffer metadata the
            // engine needs before streaming (fixed 72 bytes in this layout:
            // 4 index-buffer entries, position, color, and five vertex-buffer
            // words, each two u32s wide).
            let _depth_only_triangles = w.u32()?;
            let _packed = w.u32()?;
            w.skip(4 * 4 + 2 * 4 + 2 * 4 + 5 * 2 * 4)?;

            if let Some(bulk) = ubulk {
                let slice = bulk
                    .get(offset..offset + size_on_disk)
                    .ok_or(Error::Eof(offset))?;
                let mut bw = Walker::new(ctx, slice);
                read_buffers(&mut bw, &mut lod, trace)?;
            }
        }
        // FStaticMeshBuffersSize: serialized size, depth-only size, reversed
        // size — trails both the inlined and the streamed form.
        let (_serialized, _depth_only, _reversed) = (w.u32()?, w.u32()?, w.u32()?);
        out.lods.push(lod);
    }
    Ok(out)
}

/// `FStaticMeshLODResources::SerializeBuffers` — the whole block, whether it
/// sits inline in the export or fills a streamed LOD's `.ubulk` payload.
fn read_buffers(w: &mut Walker<'_>, lod: &mut Lod, trace: bool) -> Result<(), Error> {
    // The buffer block opens with its own strip flags: global byte first,
    // class byte second. The class flags gate the optional blocks at the end.
    let strip = w.u16()?;
    // FPositionVertexBuffer: stride, count, then bulk-serialized data.
    let stride = w.u32()?;
    let vertices = w.u32()?;
    let (elem, num) = (w.u32()?, w.u32()?);
    if trace {
        eprintln!("  positions: stride {stride} x{vertices}, bulk {elem}x{num} at {:#x}", w.pos);
    }
    if stride != 12 || elem != 12 || num != vertices {
        return Err(Error::Format(format!(
            "unexpected position buffer: stride {stride}, {vertices} vertices, bulk {elem}x{num}"
        )));
    }
    let raw = w.bytes(vertices as usize * 12)?;
    lod.positions = raw
        .chunks_exact(4)
        .map(|c| f32::from_le_bytes(c.try_into().unwrap()))
        .collect();

    // FStaticMeshVertexBuffer: strip flags, texcoord count, vertex count,
    // precision flags, tangents, texcoords.
    let _strip = w.u16()?;
    let num_texcoords = w.u32()?;
    let verts2 = w.u32()?;
    let full_precision_uvs = w.u32()? != 0;
    let high_precision_tangents = w.u32()? != 0;
    if trace {
        eprintln!(
            "  vertex buffer: {num_texcoords} uv ch, {verts2} verts, fullUV {full_precision_uvs}, hqTangent {high_precision_tangents} at {:#x}",
            w.pos
        );
    }
    if num_texcoords > 8 || verts2 != vertices {
        return Err(Error::Format(format!(
            "unexpected vertex buffer: {num_texcoords} texcoords, {verts2} vs {vertices} vertices"
        )));
    }
    // Tangents: packed 4+4 bytes (or 8+8 high-precision) per vertex.
    let (t_elem, t_num) = (w.u32()?, w.u32()?);
    let tangent_size = if high_precision_tangents { 16 } else { 8 };
    if t_elem as usize * t_num as usize != tangent_size * vertices as usize {
        return Err(Error::Format(format!(
            "unexpected tangents: {t_elem}x{t_num} for {vertices} vertices"
        )));
    }
    let tangents = w.bytes(t_elem as usize * t_num as usize)?;
    lod.normals = Vec::with_capacity(vertices as usize * 3);
    for v in 0..vertices as usize {
        // The normal is the second packed vector (Z of the tangent basis).
        let n = if high_precision_tangents {
            let at = v * 16 + 8;
            let x = i16::from_le_bytes([tangents[at], tangents[at + 1]]) as f32 / 32767.0;
            let y = i16::from_le_bytes([tangents[at + 2], tangents[at + 3]]) as f32 / 32767.0;
            let z = i16::from_le_bytes([tangents[at + 4], tangents[at + 5]]) as f32 / 32767.0;
            [x, y, z]
        } else {
            let at = v * 8 + 4;
            let x = tangents[at] as i8 as f32 / 127.0;
            let y = tangents[at + 1] as i8 as f32 / 127.0;
            let z = tangents[at + 2] as i8 as f32 / 127.0;
            [x, y, z]
        };
        lod.normals.extend_from_slice(&n);
    }
    // Texcoords: half2 or float2 per channel per vertex.
    let (u_elem, u_num) = (w.u32()?, w.u32()?);
    let uv_size = if full_precision_uvs { 8 } else { 4 };
    if u_elem as usize * u_num as usize != uv_size * num_texcoords as usize * vertices as usize {
        return Err(Error::Format(format!(
            "unexpected texcoords: {u_elem}x{u_num} for {vertices} vertices x{num_texcoords}"
        )));
    }
    let uv_raw = w.bytes(u_elem as usize * u_num as usize)?;
    lod.uvs = Vec::with_capacity(vertices as usize * 2);
    for v in 0..vertices as usize {
        let at = v * num_texcoords as usize * uv_size;
        if full_precision_uvs {
            let u = f32::from_le_bytes(uv_raw[at..at + 4].try_into().unwrap());
            let vv = f32::from_le_bytes(uv_raw[at + 4..at + 8].try_into().unwrap());
            lod.uvs.extend_from_slice(&[u, vv]);
        } else {
            let u = half(u16::from_le_bytes([uv_raw[at], uv_raw[at + 1]]));
            let vv = half(u16::from_le_bytes([uv_raw[at + 2], uv_raw[at + 3]]));
            lod.uvs.extend_from_slice(&[u, vv]);
        }
    }

    // FColorVertexBuffer: strip flags, stride, count, data when non-empty.
    let _strip = w.u16()?;
    let color_stride = w.u32()?;
    let color_count = w.u32()?;
    if color_count > 0 {
        let (c_elem, c_num) = (w.u32()?, w.u32()?);
        w.skip(c_elem as usize * c_num as usize)?;
    }
    let _ = color_stride;

    // FRawStaticIndexBuffer: wide flag, bulk-serialized bytes, and one
    // trailing bool (bShouldExpandTo32Bit).
    let b32 = w.u32()? != 0;
    let (i_elem, i_num) = (w.u32()?, w.u32()?);
    let index_bytes = w.bytes(i_elem as usize * i_num as usize)?;
    if trace {
        eprintln!("  indices: 32-bit {b32}, {i_elem}x{i_num} at {:#x}", w.pos);
    }
    lod.indices = if b32 {
        index_bytes
            .chunks_exact(4)
            .map(|c| u32::from_le_bytes(c.try_into().unwrap()))
            .collect()
    } else {
        index_bytes
            .chunks_exact(2)
            .map(|c| u16::from_le_bytes([c[0], c[1]]) as u32)
            .collect()
    };
    let expand = w.u32()?;
    if expand > 1 {
        return Err(Error::Format(format!("index-buffer tail bool is {expand}")));
    }

    // The optional index buffers, gated by the strip flags. Editor data
    // (wireframe) carries global bit 1; the class byte strips the reversed
    // buffers (0x4) and the ray-tracing geometry (0x8).
    let editor_stripped = strip & 0x01 != 0;
    let reversed_stripped = strip & 0x0400 != 0;
    let raytracing_stripped = strip & 0x0800 != 0;
    if !reversed_stripped {
        skip_raw_index_buffer(w, "reversed", trace)?;
    }
    skip_raw_index_buffer(w, "depth-only", trace)?;
    if !reversed_stripped {
        skip_raw_index_buffer(w, "reversed depth-only", trace)?;
    }
    if !editor_stripped {
        skip_raw_index_buffer(w, "wireframe", trace)?;
    }
    if !raytracing_stripped {
        // Ray-tracing geometry, a bulk-serialized byte array.
        let (elem, num) = (w.u32()?, w.u32()?);
        if elem != 1 {
            return Err(Error::Format(format!(
                "unexpected ray-tracing blob: bulk {elem}x{num}"
            )));
        }
        w.skip(num as usize)?;
        if trace && num > 0 {
            eprintln!("  ray-tracing blob: {num} bytes, at {:#x}", w.pos);
        }
    }

    // One area-weighted triangle sampler per section, then one for the whole
    // mesh: probability floats, alias table, total weight.
    for _ in 0..=lod.sections.len() {
        let prob = w.u32()? as usize;
        if prob > 4_000_000 {
            return Err(Error::Format(format!("{prob} sampler probabilities is implausible")));
        }
        w.skip(prob * 4)?;
        let alias = w.u32()? as usize;
        if alias != prob {
            return Err(Error::Format(format!("sampler has {prob} probs but {alias} aliases")));
        }
        w.skip(alias * 4)?;
        let _total_weight = w.f32()?;
    }
    Ok(())
}

/// One `FRawStaticIndexBuffer` whose contents the viewer does not need:
/// wide flag, bulk bytes, trailing bool.
fn skip_raw_index_buffer(w: &mut Walker<'_>, which: &str, trace: bool) -> Result<(), Error> {
    let b32 = w.u32()?;
    let (elem, num) = (w.u32()?, w.u32()?);
    if b32 > 1 || elem != 1 {
        return Err(Error::Format(format!(
            "unexpected {which} index buffer: b32 {b32}, bulk {elem}x{num}"
        )));
    }
    w.skip(num as usize)?;
    let expand = w.u32()?;
    if expand > 1 {
        return Err(Error::Format(format!("{which} index-buffer tail bool is {expand}")));
    }
    if trace && num > 0 {
        eprintln!("  {which} indices: {num} bytes, at {:#x}", w.pos);
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// SkeletalMesh

#[derive(Debug, Clone)]
pub struct Bone {
    pub name: String,
    /// Parent bone index, or -1 at the root.
    pub parent: i32,
    /// Rest pose relative to the parent.
    pub translation: [f32; 3],
    /// i j k w.
    pub rotation: [f32; 4],
}

#[derive(Debug, Default)]
pub struct SkeletalMeshData {
    pub materials: Vec<(String, i32)>,
    pub bones: Vec<Bone>,
    pub lods: Vec<Lod>,
}

/// Parse a `SkeletalMesh` export. Skeletal vertices are stored in component
/// space, so a rest-pose preview needs no skinning.
pub fn parse_skeletal_mesh(
    ctx: &Ctx<'_>,
    data: &[u8],
    ubulk: Option<&[u8]>,
) -> Result<SkeletalMeshData, Error> {
    let trace = std::env::var_os("UE_ASSET_TRACE").is_some();
    let mut w = Walker::new(ctx, data);
    w.read_object("SkeletalMesh", Keep::None)?;

    let mut out = SkeletalMeshData::default();
    let _strip = w.u16()?;
    w.skip(56)?; // FBoxSphereBounds, doubles

    // Materials: interface ref, slot name, UV channel info, and one trailing
    // word whose meaning is still unnamed (entry stride 40, verified against
    // the reference skeleton landing where it must).
    let material_count = w.u32()?;
    if material_count > 256 {
        return Err(Error::Format(format!("{material_count} materials is implausible")));
    }
    for _ in 0..material_count {
        let object = w.u32()? as i32;
        let slot = w.fname()?;
        w.skip(24 + 4)?;
        out.materials.push((slot, object));
    }

    // FReferenceSkeleton: bone info, rest pose, name-to-index map.
    let bone_count = w.u32()? as usize;
    if bone_count > 4096 {
        return Err(Error::Format(format!("{bone_count} bones is implausible")));
    }
    for _ in 0..bone_count {
        let name = w.fname()?;
        let parent = w.u32()? as i32;
        out.bones.push(Bone {
            name,
            parent,
            translation: [0.0; 3],
            rotation: [0.0, 0.0, 0.0, 1.0],
        });
    }
    let pose_count = w.u32()? as usize;
    if pose_count != bone_count {
        return Err(Error::Format(format!(
            "rest pose has {pose_count} transforms for {bone_count} bones"
        )));
    }
    for i in 0..pose_count {
        let mut quat = [0.0f32; 4];
        for q in &mut quat {
            *q = f64::from_bits(w.u64()?) as f32;
        }
        let mut t = [0.0f32; 3];
        for v in &mut t {
            *v = f64::from_bits(w.u64()?) as f32;
        }
        w.skip(24)?; // scale
        out.bones[i].rotation = quat;
        out.bones[i].translation = t;
    }
    let map_count = w.u32()? as usize;
    if map_count != bone_count {
        return Err(Error::Format(format!(
            "name map has {map_count} entries for {bone_count} bones"
        )));
    }
    w.skip(map_count * 12)?;
    if trace {
        eprintln!(
            "skeletal: {} materials, {} bones; render data at {:#x}",
            out.materials.len(),
            bone_count,
            w.pos
        );
    }

    // FSkeletalMeshRenderData: one leading word (always 1 so far), then the
    // LOD array.
    let leading = w.u32()?;
    if leading > 16 {
        return Err(Error::Format(format!("render-data lead word is {leading}")));
    }
    let lod_count = w.u32()?;
    if trace {
        eprintln!("  lead {leading}, {lod_count} LOD(s)");
    }
    if lod_count > 16 {
        return Err(Error::Format(format!("{lod_count} LODs is implausible")));
    }
    for lod_index in 0..lod_count {
        let mut lod = Lod::default();
        let _strip = w.u16()?;
        let cooked_out = w.u32()?;
        let inlined = w.u32()?;
        if trace {
            eprintln!(
                "  lod {lod_index}: cooked-out {cooked_out}, inlined {inlined}, at {:#x}",
                w.pos
            );
        }
        if cooked_out > 1 || inlined > 1 {
            return Err(Error::Format(format!(
                "lod {lod_index} flags {cooked_out}/{inlined} are not booleans"
            )));
        }
        if cooked_out != 0 {
            out.lods.push(lod);
            continue;
        }
        read_skeletal_lod(&mut w, &mut lod, inlined != 0, ubulk, ctx, trace)?;
        out.lods.push(lod);
    }
    Ok(out)
}

/// One `FSkeletalMeshLODRenderData`, past its cooked flags.
fn read_skeletal_lod(
    w: &mut Walker<'_>,
    lod: &mut Lod,
    inlined: bool,
    ubulk: Option<&[u8]>,
    ctx: &Ctx<'_>,
    trace: bool,
) -> Result<(), Error> {
    // RequiredBones, then the render sections.
    let required = w.u32()? as usize;
    if required > 4096 {
        return Err(Error::Format(format!("{required} required bones is implausible")));
    }
    w.skip(required * 2)?;

    let section_count = w.u32()?;
    if section_count > 256 {
        return Err(Error::Format(format!("{section_count} sections is implausible")));
    }
    for _ in 0..section_count {
        read_skeletal_section(w, lod, trace)?;
    }

    // A second bone-index array follows the sections (the LOD keeps both
    // ActiveBoneIndices and RequiredBones), then the total streamed-block
    // size — which is what lets the reader skip the skin-weight, colour and
    // profile tails it does not need: the next LOD starts exactly
    // `buffers_size` bytes after this word.
    let second = w.u32()? as usize;
    if second > 4096 {
        return Err(Error::Format(format!("{second} post-section bones is implausible")));
    }
    w.skip(second * 2)?;
    let buffers_size = w.u32()? as usize;

    if inlined {
        lod.inlined = true;
        let start = w.pos;
        read_skeletal_buffers(w, lod, trace)?;
        w.pos = start + buffers_size;
    } else {
        // Streamed: bulk header into the ubulk, then availability metadata.
        let flags = w.u32()?;
        let size64 = flags & 0x2000 != 0;
        let (_count, size_on_disk) = if size64 {
            (w.u64()? as usize, w.u64()? as usize)
        } else {
            (w.u32()? as usize, w.u32()? as usize)
        };
        let offset = w.u64()? as usize;
        if trace {
            eprintln!("    bulk: flags {flags:#x} size {size_on_disk} offset {offset:#x}");
        }
        if let Some(bulk) = ubulk {
            let slice = bulk
                .get(offset..offset + size_on_disk)
                .ok_or(Error::Eof(offset))?;
            let mut bw = Walker::new(ctx, slice);
            read_skeletal_buffers(&mut bw, lod, trace)?;
        }
    }
    Ok(())
}

/// One `FSkelMeshRenderSection`, empirically decoded for this cook.
fn read_skeletal_section(w: &mut Walker<'_>, lod: &mut Lod, trace: bool) -> Result<(), Error> {
    if trace {
        let peek = w.peek(192);
        eprint!("    section head at {:#x}:", w.pos);
        for (n, b) in peek.iter().enumerate() {
            if n % 16 == 0 {
                eprint!("\n      ");
            }
            eprint!("{b:02x} ");
        }
        eprintln!();
    }
    let _strip = w.u16()?;
    let material_index = w.u16()? as i16 as i32;
    let base_index = w.u32()?;
    let num_triangles = w.u32()?;
    let _recompute_tangent = w.u32()?;
    let _recompute_tangent_channel = w.u8()?;
    let _cast_shadow = w.u32()?;
    let _visible_in_ray_tracing = w.u32()?;
    let _base_vertex_index = w.u32()?;
    // Cloth mapping data, one array per cloth LOD bias.
    let cloth_lods = w.u32()? as usize;
    if cloth_lods > 8 {
        return Err(Error::Format(format!("{cloth_lods} cloth LODs is implausible")));
    }
    for _ in 0..cloth_lods {
        let n = w.u32()? as usize;
        w.skip(n * 96)?; // FMeshToMeshVertData
    }
    let bone_map = w.u32()? as usize;
    if bone_map > 4096 {
        return Err(Error::Format(format!("{bone_map} bone-map entries is implausible")));
    }
    w.skip(bone_map * 2)?;
    let _num_vertices = w.u32()?;
    let _max_bone_influences = w.u32()?;
    let _cloth_asset_index = w.u16()?;
    w.skip(20)?; // FClothingSectionData: guid + asset lod index
    read_duplicated_vertices(w)?;
    let _disabled = w.u32()?;
    if trace {
        eprintln!(
            "    section: mat {material_index}, first {base_index}, tris {num_triangles}, at {:#x}",
            w.pos
        );
    }
    lod.sections.push(Section {
        material_index,
        first_index: base_index,
        num_triangles,
    });
    Ok(())
}

/// FDuplicatedVerticesBuffer: duplicated-vertex indices, then per-vertex
/// (index, length) pairs — plain arrays in this cook.
fn read_duplicated_vertices(w: &mut Walker<'_>) -> Result<(), Error> {
    let dup = w.u32()? as usize;
    if dup > 4_000_000 {
        return Err(Error::Format(format!("{dup} duplicated vertices is implausible")));
    }
    w.skip(dup * 4)?;
    let pairs = w.u32()? as usize;
    if pairs > 4_000_000 {
        return Err(Error::Format(format!("{pairs} dup-index pairs is implausible")));
    }
    w.skip(pairs * 8)?;
    Ok(())
}

/// `FSkeletalMeshLODRenderData::SerializeStreamedData`.
fn read_skeletal_buffers(w: &mut Walker<'_>, lod: &mut Lod, trace: bool) -> Result<(), Error> {
    let _strip = w.u16()?;

    // FMultiSizeIndexContainer: index width byte, then bulk-serialized
    // indices.
    let index_size = w.u8()? as u32;
    let (i_elem, i_num) = (w.u32()?, w.u32()?);
    if trace {
        eprintln!(
            "    indices: width {index_size}, bulk {i_elem}x{i_num} at {:#x}",
            w.pos
        );
    }
    if index_size != 2 && index_size != 4 {
        return Err(Error::Format(format!("index width {index_size}")));
    }
    let index_bytes = w.bytes(i_elem as usize * i_num as usize)?;
    lod.indices = if index_size == 4 {
        index_bytes
            .chunks_exact(4)
            .map(|c| u32::from_le_bytes(c.try_into().unwrap()))
            .collect()
    } else {
        index_bytes
            .chunks_exact(2)
            .map(|c| u16::from_le_bytes([c[0], c[1]]) as u32)
            .collect()
    };

    // The static-mesh vertex buffers, same shapes as the static path. The
    // skin-weight, colour and profile buffers that follow are not read: the
    // caller jumps over them with the block size, and a rest-pose preview
    // needs none of them (skeletal vertices are stored in component space).
    read_buffers_positions_tangents(w, lod, trace)?;
    Ok(())
}

/// The position + tangent/uv buffers shared with the static path, minus the
/// colour/index tail (the skeletal layout continues differently after them).
fn read_buffers_positions_tangents(
    w: &mut Walker<'_>,
    lod: &mut Lod,
    trace: bool,
) -> Result<(), Error> {
    let stride = w.u32()?;
    let vertices = w.u32()?;
    let (elem, num) = (w.u32()?, w.u32()?);
    if trace {
        eprintln!(
            "    positions: stride {stride} x{vertices}, bulk {elem}x{num} at {:#x}",
            w.pos
        );
    }
    if stride != 12 || elem != 12 || num != vertices {
        return Err(Error::Format(format!(
            "unexpected position buffer: stride {stride}, {vertices} vertices, bulk {elem}x{num}"
        )));
    }
    let raw = w.bytes(vertices as usize * 12)?;
    lod.positions = raw
        .chunks_exact(4)
        .map(|c| f32::from_le_bytes(c.try_into().unwrap()))
        .collect();

    let _strip = w.u16()?;
    let num_texcoords = w.u32()?;
    let verts2 = w.u32()?;
    let full_precision_uvs = w.u32()? != 0;
    let high_precision_tangents = w.u32()? != 0;
    if num_texcoords > 8 || verts2 != vertices {
        return Err(Error::Format(format!(
            "unexpected vertex buffer: {num_texcoords} texcoords, {verts2} vs {vertices} vertices"
        )));
    }
    let (t_elem, t_num) = (w.u32()?, w.u32()?);
    let tangent_size = if high_precision_tangents { 16 } else { 8 };
    if t_elem as usize * t_num as usize != tangent_size * vertices as usize {
        return Err(Error::Format(format!(
            "unexpected tangents: {t_elem}x{t_num} for {vertices} vertices"
        )));
    }
    let tangents = w.bytes(t_elem as usize * t_num as usize)?;
    lod.normals = Vec::with_capacity(vertices as usize * 3);
    for v in 0..vertices as usize {
        let n = if high_precision_tangents {
            let at = v * 16 + 8;
            let x = i16::from_le_bytes([tangents[at], tangents[at + 1]]) as f32 / 32767.0;
            let y = i16::from_le_bytes([tangents[at + 2], tangents[at + 3]]) as f32 / 32767.0;
            let z = i16::from_le_bytes([tangents[at + 4], tangents[at + 5]]) as f32 / 32767.0;
            [x, y, z]
        } else {
            let at = v * 8 + 4;
            let x = tangents[at] as i8 as f32 / 127.0;
            let y = tangents[at + 1] as i8 as f32 / 127.0;
            let z = tangents[at + 2] as i8 as f32 / 127.0;
            [x, y, z]
        };
        lod.normals.extend_from_slice(&n);
    }
    let (u_elem, u_num) = (w.u32()?, w.u32()?);
    let uv_size = if full_precision_uvs { 8 } else { 4 };
    if u_elem as usize * u_num as usize != uv_size * num_texcoords as usize * vertices as usize {
        return Err(Error::Format(format!(
            "unexpected texcoords: {u_elem}x{u_num} for {vertices} vertices x{num_texcoords}"
        )));
    }
    let uv_raw = w.bytes(u_elem as usize * u_num as usize)?;
    lod.uvs = Vec::with_capacity(vertices as usize * 2);
    for v in 0..vertices as usize {
        let at = v * num_texcoords as usize * uv_size;
        if full_precision_uvs {
            let u = f32::from_le_bytes(uv_raw[at..at + 4].try_into().unwrap());
            let vv = f32::from_le_bytes(uv_raw[at + 4..at + 8].try_into().unwrap());
            lod.uvs.extend_from_slice(&[u, vv]);
        } else {
            let u = half(u16::from_le_bytes([uv_raw[at], uv_raw[at + 1]]));
            let vv = half(u16::from_le_bytes([uv_raw[at + 2], uv_raw[at + 3]]));
            lod.uvs.extend_from_slice(&[u, vv]);
        }
    }
    Ok(())
}

/// IEEE half to f32.
fn half(bits: u16) -> f32 {
    let sign = ((bits >> 15) & 1) as u32;
    let exp = ((bits >> 10) & 0x1F) as u32;
    let frac = (bits & 0x3FF) as u32;
    let f = match (exp, frac) {
        (0, 0) => sign << 31,
        (0, _) => {
            // Subnormal: normalize.
            let mut e = 127 - 15 + 1;
            let mut f = frac;
            while f & 0x400 == 0 {
                f <<= 1;
                e -= 1;
            }
            (sign << 31) | ((e as u32) << 23) | ((f & 0x3FF) << 13)
        }
        (0x1F, 0) => (sign << 31) | 0x7F80_0000,
        (0x1F, _) => (sign << 31) | 0x7FC0_0000,
        _ => (sign << 31) | ((exp + 127 - 15) << 23) | (frac << 13),
    };
    f32::from_bits(f)
}
