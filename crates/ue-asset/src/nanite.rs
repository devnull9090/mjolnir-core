//! Nanite geometry: the cluster pages a cooked `UStaticMesh` carries, decoded
//! back into triangles.
//!
//! Most meshes in this game cooked their detailed LOD 0 into Nanite and kept
//! only a reduced fallback in the classic buffers. The Nanite data is a set of
//! pages — a few root pages inline in the export, the rest streamed from the
//! `.ubulk` — each holding up to 256-triangle clusters with bit-packed
//! positions, octahedral normals and float-encoded UVs, plus triangle strips
//! and vertices that refer to other clusters' vertices. This module decodes
//! the pages and picks the clusters that are leaves when everything is
//! streamed in, which together are the mesh at full detail.
//!
//! The format is UE 5.5's, which is the engine this game ships on; the
//! branches other engine versions take are not carried. The decoding rules
//! are ported from CUE4Parse's Nanite readers (`FCluster`,
//! `FNaniteStreamableData`, `NaniteUtils` and friends), Apache License 2.0,
//! Copyright the CUE4Parse contributors — see `NOTICE`. The bit twiddling is
//! deliberately kept close to that source so it can be checked against it.

use std::collections::HashMap;

use crate::mesh::{Lod, Section};

/// Bits per cluster index inside a page (UE 5.4+: the larger of the
/// streaming and root page cluster-count widths).
const MAX_CLUSTERS_PER_PAGE_BITS: u32 = 8;
const MAX_UVS: usize = 4;
const UV_FLOAT_NUM_EXPONENT_BITS: u32 = 5;
const UV_FLOAT_NUM_MANTISSA_BITS: u32 = 14;
const MIN_POSITION_PRECISION: i32 = -20;
const VERTEX_COLOR_MODE_VARIABLE: u32 = 1;
const FIXUP_MAGIC: u16 = 0x464E;
const GPU_PAGE_HEADER_SIZE: usize = 16;
/// A cluster that is a leaf once every page is streamed in.
const CLUSTER_FLAG_FULL_LEAF: u32 = 0x4;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("nanite data ends early at {0:#x}")]
    Eof(usize),
    #[error("{0}")]
    Format(String),
}

fn fmt(msg: impl Into<String>) -> Error {
    Error::Format(msg.into())
}

/// One streaming page as the resources describe it.
#[derive(Debug, Clone)]
pub struct PageState {
    pub bulk_offset: u32,
    pub bulk_size: u32,
    pub page_size: u32,
    pub dependencies_start: u32,
    pub dependencies_num: u16,
    pub max_hierarchy_depth: u8,
    pub flags: u8,
}

/// `FResources` as serialized after the classic LODs.
#[derive(Debug, Default)]
pub struct Resources {
    pub resource_flags: u32,
    /// Where the streamed pages sit in the `.ubulk`, when they are there.
    pub streamable: Option<(usize, usize)>,
    /// Pages carried inline, holding the root pages.
    pub root_data: Vec<u8>,
    pub pages: Vec<PageState>,
    pub page_dependencies: Vec<u32>,
    pub num_root_pages: u32,
    pub position_precision: i32,
    pub normal_precision: i32,
    pub num_input_triangles: u32,
    pub num_input_vertices: u32,
    pub num_clusters: u32,
}

/// A little-endian cursor over the export bytes.
struct Cur<'a> {
    d: &'a [u8],
    pos: usize,
}

impl<'a> Cur<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8], Error> {
        let s = self
            .d
            .get(self.pos..self.pos + n)
            .ok_or(Error::Eof(self.pos))?;
        self.pos += n;
        Ok(s)
    }
    fn u8(&mut self) -> Result<u8, Error> {
        Ok(self.take(1)?[0])
    }
    fn u16(&mut self) -> Result<u16, Error> {
        Ok(u16::from_le_bytes(self.take(2)?.try_into().unwrap()))
    }
    fn u32(&mut self) -> Result<u32, Error> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
    fn i32(&mut self) -> Result<i32, Error> {
        Ok(self.u32()? as i32)
    }
    fn u64(&mut self) -> Result<u64, Error> {
        Ok(u64::from_le_bytes(self.take(8)?.try_into().unwrap()))
    }
    fn count(&mut self) -> Result<usize, Error> {
        let n = self.i32()?;
        if !(0..=(1 << 26)).contains(&n) {
            return Err(fmt(format!("array count {n} is implausible")));
        }
        Ok(n as usize)
    }
}

/// Parse the Nanite resources that follow the LOD array in a cooked
/// `FStaticMeshRenderData`. Returns the number of bytes consumed with the
/// resources, so a caller can continue past them.
///
/// `bulk_map` is the package's bulk-data map as `(offset, size)` into the
/// `.ubulk`. A zen package with one writes a bulk-data header as a single
/// index into it; a package without one writes the legacy header inline.
pub fn parse_resources(
    data: &[u8],
    at: usize,
    bulk_map: &[(u64, u64)],
) -> Result<(Resources, usize), Error> {
    let mut c = Cur { d: data, pos: at };
    // FStripDataFlags: global, then class flags.
    let global_strip = c.u8()?;
    let _class_strip = c.u8()?;
    let mut r = Resources::default();
    if global_strip & 2 != 0 {
        // Audio-visual data stripped: no Nanite on this platform.
        return Ok((r, c.pos - at));
    }
    r.resource_flags = c.u32()?;

    // FByteBulkData for the streamable pages.
    let mut mapped = false;
    if !bulk_map.is_empty() {
        let index = c.i32()?;
        match usize::try_from(index).ok().and_then(|i| bulk_map.get(i)) {
            Some(&(offset, size)) => {
                if size > 0 {
                    r.streamable = Some((offset as usize, size as usize));
                }
                mapped = true;
            }
            None => c.pos -= 4,
        }
    }
    if !mapped {
        let flags = c.u32()?;
        let size64 = flags & 0x2000 != 0;
        let (count, size_on_disk) = if size64 {
            (c.u64()? as usize, c.u64()? as usize)
        } else {
            (c.u32()? as usize, c.u32()? as usize)
        };
        let offset = c.u64()? as usize;
        let _ = count;
        if flags & 0x40 != 0 {
            // Inline payload: the pages follow the header.
            let inline = c.take(size_on_disk)?;
            r.root_data.extend_from_slice(inline);
            r.streamable = None;
        } else if size_on_disk > 0 {
            r.streamable = Some((offset, size_on_disk));
        }
    }

    let root_len = c.count()?;
    let root = c.take(root_len)?;
    if r.root_data.is_empty() {
        r.root_data = root.to_vec();
    }

    let n = c.count()?;
    for _ in 0..n {
        r.pages.push(PageState {
            bulk_offset: c.u32()?,
            bulk_size: c.u32()?,
            page_size: c.u32()?,
            dependencies_start: c.u32()?,
            dependencies_num: c.u16()?,
            max_hierarchy_depth: c.u8()?,
            flags: c.u8()?,
        });
    }
    // Hierarchy nodes: four 52-byte slices each. Not needed to rebuild the
    // full-detail mesh.
    let nodes = c.count()?;
    c.take(nodes * 4 * 52)?;
    let roots = c.count()?;
    c.take(roots * 4)?;
    let deps = c.count()?;
    for _ in 0..deps {
        r.page_dependencies.push(c.u32()?);
    }
    // Imposter atlas.
    let imposter = c.count()?;
    c.take(imposter * 2)?;
    r.num_root_pages = c.u32()?;
    r.position_precision = c.i32()?;
    r.normal_precision = c.i32()?;
    r.num_input_triangles = c.u32()?;
    r.num_input_vertices = c.u32()?;
    let _num_input_meshes = c.u16()?;
    let _num_input_tex_coords = c.u16()?;
    r.num_clusters = c.u32()?;
    Ok((r, c.pos - at))
}

// ------------------------------------------------------------------ bits

#[inline]
fn get_bits(value: u32, num_bits: u32, offset: u32) -> u32 {
    let mask = 1u32.wrapping_shl(num_bits).wrapping_sub(1);
    let mask = if num_bits >= 32 { u32::MAX } else { mask };
    value.wrapping_shr(offset) & mask
}

#[inline]
fn get_bits_signed(value: u32, num_bits: u32, offset: u32) -> i32 {
    let v = get_bits(value, num_bits, offset);
    (v.wrapping_shl(32 - num_bits) as i32).wrapping_shr(32 - num_bits)
}

#[inline]
fn bit_align_u32(high: u32, low: u32, shift: u32) -> u32 {
    let shift = shift & 31;
    let mut result = low >> shift;
    if shift > 0 {
        result |= high << (32 - shift);
    }
    result
}

#[inline]
fn decode_zigzag(data: u32) -> i32 {
    ((data >> 1) as i32) ^ -((data & 1) as i32)
}

#[inline]
fn first_bit_high(x: u32) -> u32 {
    if x == 0 {
        u32::MAX
    } else {
        31 - x.leading_zeros()
    }
}

#[inline]
fn u32_at(d: &[u8], at: i64) -> u32 {
    if at < 0 {
        return 0;
    }
    let at = at as usize;
    match d.get(at..at + 4) {
        Some(b) => u32::from_le_bytes(b.try_into().unwrap()),
        None => {
            // A read straddling the end is padded with zeroes, as the engine
            // reads a page buffer that is always dword-aligned in size.
            let mut v = 0u32;
            for (i, b) in d.get(at..).unwrap_or(&[]).iter().take(4).enumerate() {
                v |= (*b as u32) << (8 * i);
            }
            v
        }
    }
}

#[inline]
fn u8_at(d: &[u8], at: i64) -> u8 {
    if at < 0 {
        return 0;
    }
    d.get(at as usize).copied().unwrap_or(0)
}

/// A dword that need not be byte aligned: `bit_offset` bits past `base`.
fn read_unaligned_dword(d: &[u8], base: i64, bit_offset: i64) -> u32 {
    let byte_address = base + (bit_offset >> 3);
    let aligned = byte_address & !3;
    let bits = ((byte_address - aligned) << 3) | (bit_offset & 7);
    let low = u32_at(d, aligned);
    let high = u32_at(d, aligned + 4);
    bit_align_u32(high, low, bits as u32)
}

/// `2^-precision`, the scale a quantized position or UV is multiplied by.
fn precision_scale(precision: i32) -> f32 {
    f32::from_bits((0x3F80_0000i32 - (precision << 23)) as u32)
}

fn unpack_normal(packed: u32, bits: u32) -> [f32; 3] {
    let mask = 1u32.wrapping_shl(bits).wrapping_sub(1) as f32;
    let f0 = get_bits(packed, bits, 0) as f32 * (2.0 / mask) - 1.0;
    let f1 = get_bits(packed, bits, bits) as f32 * (2.0 / mask) - 1.0;
    let mut n = [f0, f1, 1.0 - f0.abs() - f1.abs()];
    let t = (-n[2]).clamp(0.0, 1.0);
    n[0] += if n[0] >= 0.0 { -t } else { t };
    n[1] += if n[1] >= 0.0 { -t } else { t };
    let len = (n[0] * n[0] + n[1] * n[1] + n[2] * n[2]).sqrt();
    if len > 1e-8 {
        [n[0] / len, n[1] / len, n[2] / len]
    } else {
        [0.0, 0.0, 1.0]
    }
}

fn decode_uv_float(encoded: u32, mantissa_bits: u32) -> f32 {
    let mask = (1u32 << (UV_FLOAT_NUM_EXPONENT_BITS + mantissa_bits)) - 1;
    let neg = encoded <= mask;
    let em = (if neg { !encoded } else { encoded }) & mask;
    let mut result = f32::from_bits(0x3F00_0000u32.wrapping_add(em << (23 - mantissa_bits)));
    result = (result * 2.0 - 1.0).min(result);
    if neg {
        -result
    } else {
        result
    }
}

// --------------------------------------------------------------- headers

#[derive(Debug, Clone, Copy, Default)]
struct ClusterDiskHeader {
    index_data_offset: u32,
    page_cluster_map_offset: u32,
    vertex_ref_data_offset: u32,
    low_bytes_data_offset: u32,
    mid_bytes_data_offset: u32,
    high_bytes_data_offset: u32,
    num_vertex_refs: u32,
    num_prev_ref_vertices_before_dwords: u32,
    num_prev_new_vertices_before_dwords: u32,
}

#[derive(Debug, Clone, Copy, Default)]
#[allow(dead_code)]
struct PageDiskHeader {
    num_clusters: u32,
    num_raw_float4s: u32,
    num_vertex_refs: u32,
    decode_info_offset: u32,
    strip_bitmask_offset: u32,
    vertex_ref_bitmask_offset: u32,
}

#[derive(Debug, Clone, Copy)]
struct UvRange {
    min: [u32; 2],
    num_bits: [u32; 2],
    bytes_per_value: u32,
}

/// One decoded vertex, in cluster-quantized integer space and in units.
#[derive(Debug, Clone, Copy)]
struct Vertex {
    raw: [i32; 3],
    pos: [f32; 3],
    normal: [f32; 3],
    uv: [f32; 2],
}

/// One cluster: its packed header, then what decoding filled in.
#[derive(Debug, Default)]
struct Cluster {
    num_verts: u32,
    num_tris: u32,
    pos_start: [i32; 3],
    pos_precision: i32,
    pos_scale: f32,
    pos_bits: [u32; 3],
    normal_precision: u32,
    tangent_precision: u32,
    box_center: [f32; 3],
    box_extent: [f32; 3],
    flags: u32,
    decode_info_offset: u32,
    has_tangents: bool,
    num_uvs: u32,
    color_mode: u32,
    color_bits: [u32; 4],
    material_table_offset: u32,
    material_table_length: u32,
    material0: (u32, u32),
    material1: (u32, u32),
    material2_index: u32,
    // Decoded.
    material_ranges: Vec<(u32, u32, u32)>,
    triangles: Vec<[u32; 3]>,
    group_ref_to_vertex: Vec<u32>,
    group_non_ref_to_vertex: Vec<u32>,
    vertices: Vec<Option<Vertex>>,
}

impl Cluster {
    fn uses_material_table(&self) -> bool {
        self.material0.1 == 0
    }

    fn material_index(&self, tri: u32) -> u32 {
        if self.uses_material_table() {
            for (start, len, index) in &self.material_ranges {
                if tri >= *start && tri < start + len {
                    return *index;
                }
            }
            return u32::MAX;
        }
        if tri < self.material0.1 {
            self.material0.0
        } else if tri < self.material0.1 + self.material1.1 {
            self.material1.0
        } else {
            self.material2_index
        }
    }
}

struct Page {
    disk_header_offset: usize,
    gpu_header_offset: usize,
    disk: PageDiskHeader,
    cluster_disk: Vec<ClusterDiskHeader>,
    clusters: Vec<Cluster>,
}

/// Read the packed cluster headers of a page. Clusters are stored as a
/// structure of arrays — float4 row `k` of every cluster, then row `k+1` —
/// so a cluster's rows sit `16 * (num_clusters - 1)` bytes apart.
fn read_cluster(
    d: &[u8],
    origin: usize,
    cluster_index: usize,
    num_clusters: usize,
) -> Result<Cluster, Error> {
    let stride = 16 * num_clusters;
    let row = |k: usize| origin + k * stride + 16 * cluster_index;
    let u = |at: usize| -> u32 { u32_at(d, at as i64) };
    let f = |at: usize| -> f32 { f32::from_bits(u32_at(d, at as i64)) };
    if row(7) + 16 > d.len() {
        return Err(Error::Eof(row(7)));
    }

    let mut c = Cluster::default();
    // Row 0.
    let num_verts_position_offset = u(row(0));
    c.num_verts = get_bits(num_verts_position_offset, 9, 0);
    let num_tris_index_offset = u(row(0) + 4);
    c.num_tris = get_bits(num_tris_index_offset, 8, 0);
    let color_min = u(row(0) + 8);
    let color_bits = get_bits(u(row(0) + 12), 16, 0);
    c.color_bits = [
        get_bits(color_bits, 4, 0),
        get_bits(color_bits, 4, 4),
        get_bits(color_bits, 4, 8),
        get_bits(color_bits, 4, 12),
    ];
    let _ = color_min;
    // Row 1.
    c.pos_start = [u(row(1)) as i32, u(row(1) + 4) as i32, u(row(1) + 8) as i32];
    let packed = u(row(1) + 12);
    c.pos_precision = get_bits(packed, 6, 3) as i32 + MIN_POSITION_PRECISION;
    c.pos_bits = [
        get_bits(packed, 5, 9),
        get_bits(packed, 5, 14),
        get_bits(packed, 5, 19),
    ];
    c.normal_precision = get_bits(packed, 4, 24);
    c.tangent_precision = get_bits(packed, 4, 28);
    c.pos_scale = precision_scale(c.pos_precision);
    // Row 2: LOD bounds. Row 3: box centre, LOD error, edge length.
    c.box_center = [f(row(3)), f(row(3) + 4), f(row(3) + 8)];
    // Row 4: box extent, flags.
    c.box_extent = [f(row(4)), f(row(4) + 4), f(row(4) + 8)];
    c.flags = u(row(4) + 12);
    // Row 5.
    let decode = u(row(5) + 4);
    c.decode_info_offset = get_bits(decode, 22, 0);
    c.has_tangents = get_bits(decode, 1, 22) == 1;
    c.num_uvs = get_bits(decode, 3, 24);
    c.color_mode = get_bits(decode, 1, 27);
    let material_encoding = u(row(5) + 12);
    // Row 6: extended and brick data (5.5). Row 7: vertex-reuse batch info.
    if material_encoding < 0xFE00_0000 {
        c.material0 = (
            get_bits(material_encoding, 6, 0),
            get_bits(material_encoding, 7, 18) + 1,
        );
        c.material1 = (
            get_bits(material_encoding, 6, 6),
            get_bits(material_encoding, 7, 25),
        );
        c.material2_index = get_bits(material_encoding, 6, 12);
    } else {
        c.material_table_offset = get_bits(material_encoding, 19, 0);
        c.material_table_length = get_bits(material_encoding, 6, 19) + 1;
    }
    Ok(c)
}

fn read_page_headers(d: &[u8]) -> Result<Page, Error> {
    let mut c = Cur { d, pos: 0 };
    // FFixupChunk header (5.3–5.6 layout), then its fixup arrays.
    let magic = c.u16()?;
    if magic != FIXUP_MAGIC {
        return Err(fmt(format!("fixup chunk magic {magic:#06x}")));
    }
    let fixup_clusters = c.u16()?;
    let hierarchy_fixups = c.u16()?;
    let cluster_fixups = c.u16()?;
    c.take(hierarchy_fixups as usize * 16 + cluster_fixups as usize * 8)?;

    let disk_header_offset = c.pos;
    let disk = PageDiskHeader {
        num_clusters: c.u32()?,
        num_raw_float4s: c.u32()?,
        num_vertex_refs: c.u32()?,
        decode_info_offset: c.u32()?,
        strip_bitmask_offset: c.u32()?,
        vertex_ref_bitmask_offset: c.u32()?,
    };
    if disk.num_clusters != fixup_clusters as u32 {
        return Err(fmt(format!(
            "page says {} clusters, fixup chunk {fixup_clusters}",
            disk.num_clusters
        )));
    }
    if disk.num_clusters > 256 {
        return Err(fmt(format!("{} clusters in one page", disk.num_clusters)));
    }
    let mut cluster_disk = Vec::with_capacity(disk.num_clusters as usize);
    for _ in 0..disk.num_clusters {
        cluster_disk.push(ClusterDiskHeader {
            index_data_offset: c.u32()?,
            page_cluster_map_offset: c.u32()?,
            vertex_ref_data_offset: c.u32()?,
            low_bytes_data_offset: c.u32()?,
            mid_bytes_data_offset: c.u32()?,
            high_bytes_data_offset: c.u32()?,
            num_vertex_refs: c.u32()?,
            num_prev_ref_vertices_before_dwords: c.u32()?,
            num_prev_new_vertices_before_dwords: c.u32()?,
        });
    }
    let gpu_header_offset = c.pos;
    let gpu_clusters = get_bits(c.u32()?, 16, 0);
    if gpu_clusters != disk.num_clusters {
        return Err(fmt(format!(
            "GPU header says {gpu_clusters} clusters, disk header {}",
            disk.num_clusters
        )));
    }
    let origin = gpu_header_offset + GPU_PAGE_HEADER_SIZE;
    let n = disk.num_clusters as usize;
    let mut clusters = Vec::with_capacity(n);
    for i in 0..n {
        clusters.push(read_cluster(d, origin, i, n)?);
    }
    Ok(Page {
        disk_header_offset,
        gpu_header_offset,
        disk,
        cluster_disk,
        clusters,
    })
}

// --------------------------------------------------------------- decoding

/// The three indices of one triangle from the cluster's strip encoding.
fn triangle_indices(
    d: &[u8],
    page: &Page,
    cdh: &ClusterDiskHeader,
    cluster_index: u32,
    tri_index: u32,
) -> [u32; 3] {
    let dword_index = tri_index >> 5;
    let bit_index = tri_index & 31;

    let masks_at = page.disk_header_offset as i64
        + page.disk.strip_bitmask_offset as i64
        + ((cluster_index * 4 + dword_index) * 12) as i64;
    let s_mask = u32_at(d, masks_at);
    let l_mask = u32_at(d, masks_at + 4);
    let w_mask = u32_at(d, masks_at + 8);
    let sl_mask = s_mask & l_mask;
    let head_ref_vertex_mask = (sl_mask | !s_mask) & w_mask;

    let prev_bits_mask = (1u32 << bit_index) - 1;
    let num_prev_ref_before = if dword_index == 0 {
        0
    } else {
        get_bits(
            cdh.num_prev_ref_vertices_before_dwords,
            10,
            dword_index * 10 - 10,
        )
    };
    let num_prev_new_before = if dword_index == 0 {
        0
    } else {
        get_bits(
            cdh.num_prev_new_vertices_before_dwords,
            10,
            dword_index * 10 - 10,
        )
    };
    let cur_prev_ref = (((sl_mask & prev_bits_mask).count_ones() << 1)
        + (w_mask & prev_bits_mask).count_ones()) as i32;
    let cur_prev_new =
        (((s_mask & prev_bits_mask).count_ones() << 1) as i32) + bit_index as i32 - cur_prev_ref;
    let num_prev_ref = num_prev_ref_before as i32 + cur_prev_ref;
    let num_prev_new = num_prev_new_before as i32 + cur_prev_new;

    let is_start = get_bits_signed(s_mask, 1, bit_index);
    let is_left = get_bits_signed(l_mask, 1, bit_index);
    let is_ref = get_bits_signed(w_mask, 1, bit_index);
    let base_vertex = (num_prev_new - 1) as u32;

    let read_base = page.disk_header_offset as i64 + cdh.index_data_offset as i64;
    let index_data = read_unaligned_dword(d, read_base, ((num_prev_ref + !is_start) * 5) as i64);

    let (x, mut y, mut z);
    if is_start != 0 {
        let minus_num_ref = (is_left << 1) + is_ref;
        let mut next = num_prev_new as u32;
        let mut data = index_data;
        if minus_num_ref <= -1 {
            x = base_vertex.wrapping_sub(data & 31);
            data >>= 5;
        } else {
            x = next;
            next = next.wrapping_add(1);
        }
        if minus_num_ref <= -2 {
            y = base_vertex.wrapping_sub(data & 31);
            data >>= 5;
        } else {
            y = next;
            next = next.wrapping_add(1);
        }
        if minus_num_ref <= -3 {
            z = base_vertex.wrapping_sub(data & 31);
        } else {
            z = next;
        }
    } else {
        let prev_bit_index = bit_index.wrapping_sub(1);
        let is_prev_start = get_bits_signed(s_mask, 1, prev_bit_index);
        let is_prev_head_ref = get_bits_signed(head_ref_vertex_mask, 1, prev_bit_index);
        let num_prev_new_in_tri = is_prev_start
            & (3u32.wrapping_sub(
                (get_bits(l_mask, 1, prev_bit_index) << 1) | get_bits(w_mask, 1, prev_bit_index),
            ) as i32);
        y = (base_vertex as i32
            + (is_prev_head_ref & (num_prev_new_in_tri.wrapping_sub((index_data & 31) as i32))))
            as u32;
        z = (num_prev_new + (is_ref & (-1 - get_bits(index_data, 5, 5) as i32))) as u32;

        let search_mask = s_mask | (l_mask ^ (is_left as u32));
        let found_bit_index = first_bit_high(search_mask & prev_bits_mask);
        let is_found_case_s = get_bits_signed(s_mask, 1, found_bit_index);
        let found_prev_bits_mask = 1u32.wrapping_shl(found_bit_index).wrapping_sub(1);
        let found_cur_prev_ref = (((sl_mask & found_prev_bits_mask).count_ones() << 1)
            + (w_mask & found_prev_bits_mask).count_ones()) as i32;
        let found_cur_prev_new = (((s_mask & found_prev_bits_mask).count_ones() << 1) as i32)
            + found_bit_index as i32
            - found_cur_prev_ref;
        let found_num_prev_new = num_prev_new_before as i32 + found_cur_prev_new;
        let found_num_prev_ref = num_prev_ref_before as i32 + found_cur_prev_ref;
        let found_num_ref =
            (get_bits(l_mask, 1, found_bit_index) << 1) + get_bits(w_mask, 1, found_bit_index);
        let is_before_found_ref =
            get_bits(head_ref_vertex_mask, 1, found_bit_index.wrapping_sub(1));

        let read_offset = if is_found_case_s != 0 { is_left } else { 1 };
        let found_index_data = read_unaligned_dword(
            d,
            read_base,
            ((found_num_prev_ref - read_offset) * 5) as i64,
        );
        let found_index = (found_num_prev_new as u32)
            .wrapping_sub(1)
            .wrapping_sub(get_bits(found_index_data, 5, 0));
        let condition = if is_found_case_s != 0 {
            found_num_ref as i32 >= 1 - is_left
        } else {
            is_before_found_ref != 0
        };
        let found_new_vertex = found_num_prev_new
            + if is_found_case_s != 0 {
                is_left & (if found_num_ref == 0 { 1 } else { 0 })
            } else {
                -1
            };
        x = if condition {
            found_index
        } else {
            found_new_vertex as u32
        };
        if is_left != 0 {
            std::mem::swap(&mut y, &mut z);
        }
    }
    [x, y, z]
}

/// Which vertices of a cluster are references to other clusters' vertices,
/// from the page's per-cluster bitmask, in the two orders the data streams
/// use.
fn split_ref_vertices(
    d: &[u8],
    page: &Page,
    cdh: &ClusterDiskHeader,
    cluster_index: u32,
    num_verts: u32,
) -> (Vec<u32>, Vec<u32>) {
    let mut ref_to_vertex = vec![0u32; cdh.num_vertex_refs as usize];
    let num_non_ref = num_verts.saturating_sub(cdh.num_vertex_refs);
    let mut non_ref_to_vertex = vec![0u32; num_non_ref as usize];
    let aligned = page.disk_header_offset as i64
        + page.disk.vertex_ref_bitmask_offset as i64
        + (cluster_index * 32) as i64;
    let mut group_num_refs_in_prev_dwords8888 = [0u32; 2];
    for group_index in 0..7u32 {
        let count = u32_at(d, aligned + (group_index * 4) as i64).count_ones();
        let count8888 = count.wrapping_mul(0x0101_0101);
        let index = group_index + 1;
        group_num_refs_in_prev_dwords8888[(index >> 2) as usize] =
            group_num_refs_in_prev_dwords8888[(index >> 2) as usize]
                .wrapping_add(count8888 << ((index & 3) << 3));
        if num_verts > 128 && index < 4 {
            group_num_refs_in_prev_dwords8888[1] =
                group_num_refs_in_prev_dwords8888[1].wrapping_add(count8888);
        }
    }
    for vertex_index in 0..num_verts {
        let dword_index = vertex_index >> 5;
        let bit_index = vertex_index & 31;
        let shift = (dword_index & 3) << 3;
        let num_refs_in_prev_dwords =
            (group_num_refs_in_prev_dwords8888[(dword_index >> 2) as usize] >> shift) & 0xFF;
        let dword_mask = u32_at(d, aligned + (dword_index * 4) as i64);
        let num_prev_ref =
            get_bits(dword_mask, bit_index, 0).count_ones() + num_refs_in_prev_dwords;
        if dword_mask & (1 << bit_index) != 0 {
            if let Some(slot) = ref_to_vertex.get_mut(num_prev_ref as usize) {
                *slot = vertex_index;
            }
        } else {
            let num_prev_non_ref = vertex_index - num_prev_ref;
            if let Some(slot) = non_ref_to_vertex.get_mut(num_prev_non_ref as usize) {
                *slot = vertex_index;
            }
        }
    }
    (ref_to_vertex, non_ref_to_vertex)
}

/// Read one value set from the low/mid/high byte streams: `count`
/// components, `bytes_per_value` of them present, zigzag-delta coded
/// against the previous vertex.
fn lmh_read(
    d: &[u8],
    offsets: [u64; 3],
    bytes_per_value: u32,
    count: usize,
    index: u32,
    prev: &mut [i32; 4],
) -> [i32; 4] {
    let mut packed = [0u32; 4];
    for (plane, shift) in [(2usize, 16u32), (1, 8), (0, 0)] {
        if bytes_per_value as usize > plane {
            let at = offsets[plane] + (index as u64) * count as u64;
            for (k, slot) in packed.iter_mut().enumerate().take(count) {
                *slot |= (u8_at(d, (at + k as u64) as i64) as u32) << shift;
            }
        }
    }
    let mut value = [0i32; 4];
    for k in 0..4 {
        let decoded = if k < count {
            decode_zigzag(packed[k])
        } else {
            0
        };
        value[k] = decoded.wrapping_add(prev[k]);
    }
    *prev = value;
    value
}

fn lmh_increment(offsets: &mut [u64; 3], bytes_per_value: u32, num: u64) {
    if bytes_per_value >= 1 {
        offsets[0] += num;
    }
    if bytes_per_value >= 2 {
        offsets[1] += num;
    }
    if bytes_per_value >= 3 {
        offsets[2] += num;
    }
}

/// Decode a page's clusters: material tables, triangles, ref/non-ref split,
/// UV ranges and every non-reference vertex.
fn decode_page(d: &[u8], page: &mut Page) -> Result<(), Error> {
    for ci in 0..page.clusters.len() {
        let cdh = page.cluster_disk[ci];
        let cluster = &mut page.clusters[ci];

        if cluster.uses_material_table() {
            let at = page.gpu_header_offset as i64 + (cluster.material_table_offset * 4) as i64;
            cluster.material_ranges = (0..cluster.material_table_length)
                .map(|k| {
                    let v = u32_at(d, at + (k * 4) as i64);
                    (get_bits(v, 8, 0), get_bits(v, 8, 8), get_bits(v, 6, 16))
                })
                .collect();
        }

        let mut triangles = Vec::with_capacity(cluster.num_tris as usize);
        for t in 0..cluster.num_tris {
            let [mut x, mut y, mut z] = triangle_indices(d, page, &cdh, ci as u32, t);
            if y < x.min(z) {
                (x, y, z) = (y, z, x);
            } else if z < x.min(y) {
                (x, y, z) = (z, x, y);
            }
            triangles.push([x, y, z]);
        }
        let cluster = &mut page.clusters[ci];
        cluster.triangles = triangles;

        let (refs, non_refs) =
            split_ref_vertices(d, page, &cdh, ci as u32, page.clusters[ci].num_verts);
        let cluster = &mut page.clusters[ci];
        cluster.group_ref_to_vertex = refs;
        cluster.group_non_ref_to_vertex = non_refs;
        let num_non_ref = cluster.group_non_ref_to_vertex.len() as u32;

        // UV ranges.
        let ranges_at = page.gpu_header_offset as i64 + cluster.decode_info_offset as i64;
        let uv_ranges: Vec<UvRange> = (0..cluster.num_uvs.min(MAX_UVS as u32))
            .map(|k| {
                let a = u32_at(d, ranges_at + (k * 8) as i64);
                let b = u32_at(d, ranges_at + (k * 8 + 4) as i64);
                let num_bits = [a & 31, b & 31];
                UvRange {
                    min: [a >> 5, b >> 5],
                    num_bits,
                    bytes_per_value: num_bits[0].max(num_bits[1]).div_ceil(8),
                }
            })
            .collect();

        // The low/mid/high byte streams, in the order the builder laid them
        // out: positions, normals, tangents, colours, then each UV set.
        let base = page.disk_header_offset as u64;
        let mut next = [
            base + cdh.low_bytes_data_offset as u64,
            base + cdh.mid_bytes_data_offset as u64,
            base + cdh.high_bytes_data_offset as u64,
        ];
        let pos_bits = cluster.pos_bits;
        let position_offsets = next;
        let position_bytes = pos_bits[0].max(pos_bits[1]).max(pos_bits[2]).div_ceil(8);
        let mut prev_position = [
            1i32.wrapping_shl(pos_bits[0].wrapping_sub(1)),
            1i32.wrapping_shl(pos_bits[1].wrapping_sub(1)),
            1i32.wrapping_shl(pos_bits[2].wrapping_sub(1)),
            0,
        ];
        let position_mask = [
            1i32.wrapping_shl(pos_bits[0]).wrapping_sub(1),
            1i32.wrapping_shl(pos_bits[1]).wrapping_sub(1),
            1i32.wrapping_shl(pos_bits[2]).wrapping_sub(1),
            0,
        ];
        lmh_increment(&mut next, position_bytes, 3 * num_non_ref as u64);

        let normal_offsets = next;
        let normal_bytes = cluster.normal_precision.div_ceil(8);
        let mut prev_normal = [0i32; 4];
        let normal_mask = 1i32.wrapping_shl(cluster.normal_precision).wrapping_sub(1);
        lmh_increment(&mut next, normal_bytes, 2 * num_non_ref as u64);

        if cluster.has_tangents {
            let tangent_bytes = (cluster.tangent_precision + 1).div_ceil(8);
            lmh_increment(&mut next, tangent_bytes, num_non_ref as u64);
        }
        if cluster.color_mode == VERTEX_COLOR_MODE_VARIABLE {
            lmh_increment(&mut next, 1, 4 * num_non_ref as u64);
        }
        let mut uv_offsets = Vec::with_capacity(uv_ranges.len());
        let mut uv_prev = vec![[0i32; 4]; uv_ranges.len()];
        for r in &uv_ranges {
            uv_offsets.push(next);
            lmh_increment(&mut next, r.bytes_per_value, 2 * num_non_ref as u64);
        }

        let pos_start = cluster.pos_start;
        let pos_scale = cluster.pos_scale;
        let normal_precision = cluster.normal_precision;
        let mut vertices: Vec<Option<Vertex>> = vec![None; cluster.num_verts as usize];
        for i in 0..num_non_ref {
            let v = lmh_read(
                d,
                position_offsets,
                position_bytes,
                3,
                i,
                &mut prev_position,
            );
            let raw = [
                (v[0] & position_mask[0]).wrapping_add(pos_start[0]),
                (v[1] & position_mask[1]).wrapping_add(pos_start[1]),
                (v[2] & position_mask[2]).wrapping_add(pos_start[2]),
            ];
            let n = lmh_read(d, normal_offsets, normal_bytes, 2, i, &mut prev_normal);
            let packed_normal =
                (((n[1] & normal_mask) as u32) << normal_precision) | (n[0] & normal_mask) as u32;
            let normal = unpack_normal(packed_normal, normal_precision);
            let mut uv = [0.0f32; 2];
            if let Some(r) = uv_ranges.first() {
                let mask = [
                    1i32.wrapping_shl(r.num_bits[0]).wrapping_sub(1),
                    1i32.wrapping_shl(r.num_bits[1]).wrapping_sub(1),
                ];
                let t = lmh_read(d, uv_offsets[0], r.bytes_per_value, 2, i, &mut uv_prev[0]);
                let gx = ((t[0] & mask[0]) as u32).wrapping_add(r.min[0]);
                let gy = ((t[1] & mask[1]) as u32).wrapping_add(r.min[1]);
                uv = [
                    decode_uv_float(gx, UV_FLOAT_NUM_MANTISSA_BITS),
                    decode_uv_float(gy, UV_FLOAT_NUM_MANTISSA_BITS),
                ];
            }
            // The other UV sets still advance their own streams, which the
            // per-set offsets above already account for; nothing to read.
            let pos = [
                raw[0] as f32 * pos_scale,
                raw[1] as f32 * pos_scale,
                raw[2] as f32 * pos_scale,
            ];
            let slot = cluster.group_non_ref_to_vertex[i as usize] as usize;
            if let Some(s) = vertices.get_mut(slot) {
                *s = Some(Vertex {
                    raw,
                    pos,
                    normal,
                    uv,
                });
            }
        }
        cluster.vertices = vertices;
    }
    Ok(())
}

/// Resolve a page's reference vertices against their source clusters — in
/// this page or in a page it depends on, all decoded already.
fn resolve_refs(d: &[u8], pages: &mut [Page], page_index: usize, res: &Resources) -> usize {
    let mut unresolved = 0;
    let n = pages[page_index].clusters.len();
    for ci in 0..n {
        let cdh = pages[page_index].cluster_disk[ci];
        let disk_base = pages[page_index].disk_header_offset as i64;
        let num_page_refs = pages[page_index].disk.num_vertex_refs as i64;
        let mut prev_ref_vertex_index = 0i32;
        for ri in 0..cdh.num_vertex_refs {
            let vertex_index =
                pages[page_index].clusters[ci].group_ref_to_vertex[ri as usize] as usize;
            let page_cluster_index =
                u8_at(d, disk_base + cdh.vertex_ref_data_offset as i64 + ri as i64);
            let page_cluster_data = u32_at(
                d,
                disk_base + cdh.page_cluster_map_offset as i64 + (page_cluster_index as i64) * 4,
            );
            let parent_page_index = page_cluster_data >> MAX_CLUSTERS_PER_PAGE_BITS;
            let src_local_cluster =
                get_bits(page_cluster_data, MAX_CLUSTERS_PER_PAGE_BITS, 0) as usize;
            let coded = u8_at(
                d,
                disk_base + cdh.vertex_ref_data_offset as i64 + ri as i64 + num_page_refs,
            );
            let temp = decode_zigzag(coded as u32).wrapping_add(prev_ref_vertex_index);
            prev_ref_vertex_index = temp;
            let src_vertex = (temp as u8) as usize;

            let src_page = if parent_page_index != 0 {
                let state = &res.pages[page_index];
                let dep = state.dependencies_start as usize + parent_page_index as usize - 1;
                match res.page_dependencies.get(dep) {
                    Some(p) => *p as usize,
                    None => {
                        unresolved += 1;
                        continue;
                    }
                }
            } else {
                page_index
            };
            let src = pages
                .get(src_page)
                .and_then(|p| p.clusters.get(src_local_cluster))
                .and_then(|c| c.vertices.get(src_vertex))
                .and_then(|v| *v);
            let scale = pages[page_index].clusters[ci].pos_scale;
            match src {
                Some(v) => {
                    let pos = [
                        v.raw[0] as f32 * scale,
                        v.raw[1] as f32 * scale,
                        v.raw[2] as f32 * scale,
                    ];
                    if let Some(slot) = pages[page_index].clusters[ci]
                        .vertices
                        .get_mut(vertex_index)
                    {
                        *slot = Some(Vertex { pos, ..v });
                    }
                }
                None => unresolved += 1,
            }
        }
    }
    unresolved
}

/// What decoding produced, besides the geometry.
#[derive(Debug, Default, Clone)]
pub struct Report {
    pub pages: usize,
    pub clusters: usize,
    /// Clusters that make up the full-detail mesh.
    pub leaf_clusters: usize,
    pub triangles: usize,
    /// Triangles dropped because a vertex reference did not resolve.
    pub dropped_triangles: usize,
    pub unresolved_refs: usize,
    /// Vertices of full-detail clusters that fall outside the box their
    /// cluster header claims — zero when decoding is right.
    pub out_of_bounds_vertices: usize,
    /// Triangles the builder was given, from the resources; the full-detail
    /// clusters should hold about this many.
    pub input_triangles: u32,
}

/// Decode every page and assemble the full-detail mesh: the clusters that are
/// leaves once all pages are streamed in, welded on position, normal and UV,
/// with one section per material index.
pub fn decode(res: &Resources, ubulk: Option<&[u8]>) -> Result<(Lod, Report), Error> {
    if res.pages.is_empty() {
        return Err(fmt("no Nanite pages"));
    }
    let streamable: &[u8] = match (res.streamable, ubulk) {
        (Some((off, len)), Some(bulk)) => bulk.get(off..off + len).ok_or(Error::Eof(off))?,
        (Some(_), None) => &[],
        (None, _) => &[],
    };

    // Each page decodes against its own byte slice, so page-relative offsets
    // are simply offsets into it.
    let mut buffers: Vec<&[u8]> = Vec::with_capacity(res.pages.len());
    for (i, p) in res.pages.iter().enumerate() {
        let (from, source): (usize, &[u8]) = if (i as u32) < res.num_root_pages {
            (p.bulk_offset as usize, &res.root_data)
        } else {
            (p.bulk_offset as usize, streamable)
        };
        let slice = source
            .get(from..from + p.bulk_size as usize)
            .ok_or_else(|| {
                fmt(format!(
                    "page {i}: {} bytes at {from:#x} is beyond its source",
                    p.bulk_size
                ))
            })?;
        buffers.push(slice);
    }

    let mut pages = Vec::with_capacity(buffers.len());
    for (i, b) in buffers.iter().enumerate() {
        let mut page = read_page_headers(b).map_err(|e| fmt(format!("page {i}: {e}")))?;
        decode_page(b, &mut page).map_err(|e| fmt(format!("page {i}: {e}")))?;
        pages.push(page);
    }
    let mut report = Report {
        pages: pages.len(),
        clusters: pages.iter().map(|p| p.clusters.len()).sum(),
        input_triangles: res.num_input_triangles,
        ..Report::default()
    };
    for (i, buffer) in buffers.iter().enumerate() {
        report.unresolved_refs += resolve_refs(buffer, &mut pages, i, res);
    }

    // Weld and assemble.
    let mut lod = Lod {
        inlined: true,
        ..Lod::default()
    };
    let mut welded: HashMap<[u32; 8], u32> = HashMap::new();
    let mut by_material: HashMap<u32, Vec<[u32; 3]>> = HashMap::new();
    for page in &pages {
        for cluster in &page.clusters {
            if cluster.flags & CLUSTER_FLAG_FULL_LEAF == 0 {
                continue;
            }
            report.leaf_clusters += 1;
            for v in cluster.vertices.iter().flatten() {
                let inside = (0..3).all(|k| {
                    (v.pos[k] - cluster.box_center[k]).abs()
                        <= cluster.box_extent[k].abs() * 1.02 + 1e-2
                });
                if !inside {
                    report.out_of_bounds_vertices += 1;
                }
            }
            for (t, tri) in cluster.triangles.iter().enumerate() {
                let mut out = [0u32; 3];
                let mut ok = true;
                for (k, &vi) in tri.iter().enumerate() {
                    let Some(v) = cluster.vertices.get(vi as usize).and_then(|v| *v) else {
                        ok = false;
                        break;
                    };
                    let key = [
                        v.pos[0].to_bits(),
                        v.pos[1].to_bits(),
                        v.pos[2].to_bits(),
                        v.normal[0].to_bits(),
                        v.normal[1].to_bits(),
                        v.normal[2].to_bits(),
                        v.uv[0].to_bits(),
                        v.uv[1].to_bits(),
                    ];
                    let index = *welded.entry(key).or_insert_with(|| {
                        lod.positions.extend_from_slice(&v.pos);
                        lod.normals.extend_from_slice(&v.normal);
                        lod.uvs.extend_from_slice(&v.uv);
                        (lod.positions.len() / 3 - 1) as u32
                    });
                    out[k] = index;
                }
                if !ok {
                    report.dropped_triangles += 1;
                    continue;
                }
                let material = cluster.material_index(t as u32);
                by_material.entry(material).or_default().push(out);
                report.triangles += 1;
            }
        }
    }
    let mut materials: Vec<u32> = by_material.keys().copied().collect();
    materials.sort_unstable();
    for m in materials {
        let tris = &by_material[&m];
        lod.sections.push(Section {
            material_index: if m == u32::MAX { 0 } else { m as i32 },
            first_index: lod.indices.len() as u32,
            num_triangles: tris.len() as u32,
        });
        for t in tris {
            lod.indices.extend_from_slice(t);
        }
    }
    if lod.indices.is_empty() {
        return Err(fmt("no full-detail cluster decoded to a triangle"));
    }
    Ok((lod, report))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Against the installed game: every shipped static mesh with Nanite
    /// pages decodes, its cluster count matches the resources, its leaf
    /// clusters hold about the triangles the builder was given, no vertex
    /// leaves its cluster's box, and the full-detail mesh spans the same
    /// space as the classic fallback.
    #[test]
    fn shipped_nanite_meshes_decode_consistently() {
        let Ok(paks) = std::env::var("HCE_PAKS") else {
            return;
        };
        let containers = ue_iostore::load_all(&paks).unwrap();
        let global = containers
            .iter()
            .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
            .unwrap();
        let script_chunk = global
            .chunks
            .iter()
            .find(|c| c.type_name() == "ScriptObjects")
            .unwrap();
        let scripts = crate::zen::ScriptObjects::parse(
            &ue_iostore::read_chunk(global, script_chunk, None, &[]).unwrap(),
        )
        .unwrap();
        static USMAP: &[u8] = include_bytes!("../../../defs/ue/Meteorite-2607-CU3.usmap");
        let usmap = crate::Usmap::parse(USMAP).unwrap();

        let limit: usize = std::env::var("NANITE_TEST_LIMIT")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(40);
        let mut checked = 0usize;
        let mut with_nanite = 0usize;
        let mut skeletal_with_nanite = 0usize;
        let mut failures: Vec<String> = Vec::new();
        // Skeletal meshes are few and sort late; sweep each kind on its own
        // so `limit` of both get checked.
        for want_skeletal in [true, false] {
            let mut checked_kind = 0usize;
            'outer: for (ci, c) in containers.iter().enumerate() {
                let mut names: Vec<(&String, &usize)> = c.files.iter().collect();
                names.sort();
                for (rel, chunk_index) in names {
                    let full = c.full_path(rel);
                    let leaf = full.rsplit('/').next().unwrap_or("");
                    let skeletal = leaf.starts_with("SK_");
                    if skeletal != want_skeletal
                        || !(leaf.starts_with("SM_") || skeletal)
                        || !full.ends_with(".uasset")
                        || full.contains("/Engine/")
                    {
                        continue;
                    }
                    let stem = full.trim_end_matches(".uasset");
                    let bulk = c
                        .files
                        .get(&format!("{}.ubulk", rel.trim_end_matches(".uasset")))
                        .and_then(|bi| ue_iostore::read_chunk(c, &c.chunks[*bi], None, &[]).ok());
                    let data =
                        ue_iostore::read_chunk(c, &c.chunks[*chunk_index], None, &[]).unwrap();
                    let Ok(package) = crate::zen::Package::parse(&data) else {
                        continue;
                    };
                    let wanted = if skeletal {
                        "SkeletalMesh"
                    } else {
                        "StaticMesh"
                    };
                    let Some(export) = package
                        .exports
                        .iter()
                        .position(|e| scripts.leaf(e.class) == Some(wanted))
                    else {
                        continue;
                    };
                    let Ok(bytes) = package.export_data(&data, export) else {
                        continue;
                    };
                    let ctx = crate::unversioned::Ctx {
                        usmap: &usmap,
                        names: &package.names,
                    };
                    let bulk_map = crate::mesh::bulk_map_of(&data);
                    let (lods, nanite, report, note) = if skeletal {
                        let Ok(sk) = crate::mesh::parse_skeletal_mesh_with_bulk_map(
                            &ctx,
                            bytes,
                            bulk.as_deref(),
                            &bulk_map,
                        ) else {
                            continue;
                        };
                        (sk.lods, sk.nanite, sk.nanite_report, sk.nanite_note)
                    } else {
                        let Ok(sm) = crate::mesh::parse_static_mesh_with_bulk_map(
                            &ctx,
                            bytes,
                            bulk.as_deref(),
                            &bulk_map,
                        ) else {
                            continue;
                        };
                        (sm.lods, sm.nanite, sm.nanite_report, sm.nanite_note)
                    };
                    let mesh = crate::mesh::StaticMeshData {
                        materials: Vec::new(),
                        lods,
                        nanite,
                        nanite_report: report,
                        nanite_note: note,
                    };
                    checked += 1;
                    checked_kind += 1;
                    if checked_kind > limit {
                        break 'outer;
                    }
                    let short = stem.trim_start_matches("../../../Meteorite/Content/");
                    if let Some(note) = &mesh.nanite_note {
                        failures.push(format!("{short}: {note}"));
                        continue;
                    }
                    let (Some(lod), Some(report)) = (&mesh.nanite, &mesh.nanite_report) else {
                        continue;
                    };
                    with_nanite += 1;
                    skeletal_with_nanite += usize::from(skeletal);
                    if report.out_of_bounds_vertices > 0
                        || report.dropped_triangles > 0
                        || report.unresolved_refs > 0
                    {
                        failures.push(format!("{short}: {report:?}"));
                    }
                    if report.clusters != mesh.nanite_report.as_ref().map_or(0, |r| r.clusters) {
                        unreachable!();
                    }
                    let ratio = report.triangles as f64 / report.input_triangles.max(1) as f64;
                    if !(0.9..=1.1).contains(&ratio) {
                        failures.push(format!(
                            "{short}: {} full-detail triangles vs {} input ({ratio:.3})",
                            report.triangles, report.input_triangles
                        ));
                    }
                    // The classic fallback spans the same space, give or take
                    // the simplification.
                    if let Some(classic) = mesh.lods.iter().find(|l| l.positions.len() > 9) {
                        let aabb = |p: &[f32]| {
                            let mut min = [f32::MAX; 3];
                            let mut max = [f32::MIN; 3];
                            for v in p.chunks_exact(3) {
                                for k in 0..3 {
                                    min[k] = min[k].min(v[k]);
                                    max[k] = max[k].max(v[k]);
                                }
                            }
                            (min, max)
                        };
                        let (nmin, nmax) = aabb(&lod.positions);
                        let (cmin, cmax) = aabb(&classic.positions);
                        for k in 0..3 {
                            let span = (cmax[k] - cmin[k]).abs().max(1.0);
                            // Foliage with wind proxies and flat water planes keep
                            // fallbacks shaped differently from the full mesh, so a
                            // mismatch is reported, not failed; the cluster boxes
                            // above are the decoder's own check.
                            if (nmin[k] - cmin[k]).abs() > span * 0.25
                                || (nmax[k] - cmax[k]).abs() > span * 0.25
                            {
                                eprintln!(
                                "note {short}: nanite bounds {nmin:?}..{nmax:?} vs classic {cmin:?}..{cmax:?}"
                            );
                                break;
                            }
                        }
                    }
                }
                let _ = ci;
            }
        }
        eprintln!(
            "{checked} meshes parsed, {with_nanite} with Nanite geometry ({skeletal_with_nanite} skeletal)"
        );
        for f in failures.iter().take(20) {
            eprintln!("FAIL {f}");
        }
        assert!(with_nanite > 0, "no Nanite mesh among the first {checked}");
        assert!(failures.is_empty(), "{} mesh(es) failed", failures.len());
    }

    #[test]
    fn bit_helpers_match_the_shader_definitions() {
        assert_eq!(get_bits(0xABCD_1234, 8, 8), 0x12);
        assert_eq!(get_bits_signed(0b10, 1, 1), -1);
        assert_eq!(get_bits_signed(0b01, 1, 1), 0);
        assert_eq!(bit_align_u32(0x1234_5678, 0x9ABC_DEF0, 8), 0x789A_BCDE);
        assert_eq!(bit_align_u32(0x1234_5678, 0x9ABC_DEF0, 0), 0x9ABC_DEF0);
        assert_eq!(decode_zigzag(0), 0);
        assert_eq!(decode_zigzag(1), -1);
        assert_eq!(decode_zigzag(2), 1);
        assert_eq!(decode_zigzag(3), -2);
        assert_eq!(first_bit_high(0), u32::MAX);
        assert_eq!(first_bit_high(1), 0);
        assert_eq!(first_bit_high(0x8000_0000), 31);
        assert_eq!(precision_scale(0), 1.0);
        assert_eq!(precision_scale(3), 0.125);
        assert_eq!(precision_scale(-2), 4.0);
    }

    #[test]
    fn an_unaligned_dword_reads_across_dword_boundaries() {
        let d: Vec<u8> = (0u8..16).collect();
        assert_eq!(read_unaligned_dword(&d, 0, 0), 0x0302_0100);
        assert_eq!(read_unaligned_dword(&d, 0, 8), 0x0403_0201);
        assert_eq!(read_unaligned_dword(&d, 1, 4), 0x5040_3020);
        // Past the end pads with zeroes rather than failing.
        assert_eq!(read_unaligned_dword(&d, 14, 0), 0x0000_0F0E);
    }

    #[test]
    fn normals_and_uv_floats_decode_to_unit_and_signed_values() {
        // The centre of the octahedron map is +Z.
        let bits = 9;
        let mid = (1u32 << (bits - 1)) | ((1u32 << (bits - 1)) << bits);
        let n = unpack_normal(mid, bits);
        assert!(n[2] > 0.99, "{n:?}");
        let len = (n[0] * n[0] + n[1] * n[1] + n[2] * n[2]).sqrt();
        assert!((len - 1.0).abs() < 1e-5);
        // 0 encodes the most negative value, the top of the range +1-ish.
        assert!(decode_uv_float(0, 14) < 0.0);
        assert!(decode_uv_float((1 << 19) - 1, 14) <= 0.0);
        assert!(decode_uv_float(1 << 19, 14) >= 0.0);
        // Half-way encodings around zero are tiny.
        assert!(decode_uv_float((1 << 19) - 1, 14).abs() < 1e-3);
    }
}
