//! Cooked Texture2D reading.
//!
//! Format documented in `docs/ue_texture_format.md`. A cooked texture is
//! serialized as `FTexturePlatformData`: `SizeX`, `SizeY`, `PackedData`, the
//! pixel-format name, then `FirstMipToSerialize` and `NumMips`. When `NumMips`
//! is zero the payload is a *virtual* texture — border-padded tiles in the
//! `.ubulk`, addressed by Morton code through an RLE offset table. Otherwise it
//! is a classic mip chain: each mip is either inline in the export or appended
//! to the `.ubulk` in order.

use serde::Serialize;

/// A cooked texture, ready to have a mip assembled.
#[derive(Debug)]
pub struct Texture {
    /// Dimensions of the largest mip actually present, which is not the
    /// authored size when the cook dropped the top mips.
    pub width: u32,
    pub height: u32,
    pub format: String,
    /// How many mips can be assembled.
    pub num_mips: u32,
    pub payload: Payload,
}

#[derive(Debug)]
pub enum Payload {
    Virtual(VtData),
    /// Classic mip chain, largest first.
    Classic(Vec<Mip>),
}

/// One mip of a classic chain.
#[derive(Debug)]
pub struct Mip {
    pub width: u32,
    pub height: u32,
    pub source: MipSource,
}

#[derive(Debug)]
pub enum MipSource {
    /// Byte range in the `.ubulk`, which holds the external mips in order.
    Bulk { offset: u64, len: u64 },
    /// Payload carried inline in the export.
    Inline(Vec<u8>),
}

impl Texture {
    /// Dimensions of mip `i`.
    pub fn mip_dims(&self, i: u32) -> (u32, u32) {
        match &self.payload {
            Payload::Virtual(_) => ((self.width >> i).max(1), (self.height >> i).max(1)),
            Payload::Classic(mips) => mips
                .get(i as usize)
                .map(|m| (m.width, m.height))
                .unwrap_or((self.width, self.height)),
        }
    }
}

/// Parsed virtual-texture metadata for one texture asset.
#[derive(Debug)]
pub struct VtData {
    pub width: u32,
    pub height: u32,
    pub format: String,
    pub tile_size: u32,
    pub tile_border: u32,
    pub tile_bytes: u32,
    pub num_mips: u32,
    pub chunk_index_per_mip: Vec<u32>,
    pub mip_offset_in_chunk: Vec<u32>,
    pub tables: Vec<TileOffsets>,
    /// Byte size of each chunk; chunks are concatenated in the ubulk.
    pub chunk_sizes: Vec<u32>,
}

/// `FVirtualTextureTileOffsetData`: RLE map of Morton address to tile offset.
#[derive(Debug)]
pub struct TileOffsets {
    pub width: u32,
    pub height: u32,
    pub addresses: Vec<u32>,
    pub offsets: Vec<u32>,
}

const EMPTY: u32 = 0xFFFF_FFFF;

impl TileOffsets {
    /// Tile offset for a Morton address, or `None` where no tile exists.
    fn offset_of(&self, address: u32) -> Option<u32> {
        let i = match self.addresses.binary_search(&address) {
            Ok(i) => i,
            Err(0) => return None,
            Err(i) => i - 1,
        };
        let base = *self.offsets.get(i)?;
        if base == EMPTY {
            return None;
        }
        Some(base + (address - self.addresses[i]))
    }
}

fn morton(x: u32, y: u32) -> u32 {
    let mut out = 0u32;
    for b in 0..12 {
        out |= ((x >> b) & 1) << (2 * b) | ((y >> b) & 1) << (2 * b + 1);
    }
    out
}

/// Bytes per block and block edge in pixels.
///
/// Only formats this build actually ships are listed, plus `PF_DXT3` for the
/// sake of the BC family. Guessing at the rest risks sizing a mip wrongly and
/// desynchronising the chain walk, so an unlisted format is refused instead.
///
/// Uncompressed formats are described as 1x1 "blocks" so one rule sizes both.
fn block_layout(format: &str) -> Option<(u64, u64)> {
    Some(match format {
        "PF_DXT1" | "PF_BC4" => (8, 4),
        "PF_DXT3" | "PF_DXT5" | "PF_BC5" | "PF_BC6H" | "PF_BC7" => (16, 4),
        "PF_G8" | "PF_A8" => (1, 1),
        "PF_R16F" => (2, 1),
        "PF_B8G8R8A8" => (4, 1),
        "PF_FloatRGBA" => (8, 1),
        "PF_A32B32G32R32F" => (16, 1),
        _ => return None,
    })
}

/// Byte size of one `width`x`height` surface in `format`.
fn surface_bytes(format: &str, width: u32, height: u32) -> Option<u64> {
    let (bytes, dim) = block_layout(format)?;
    let bw = (width as u64).div_ceil(dim).max(1);
    let bh = (height as u64).div_ceil(dim).max(1);
    Some(bw * bh * bytes)
}

fn half_to_f32(h: u16) -> f32 {
    let sign = ((h >> 15) & 1) as u32;
    let exp = ((h >> 10) & 0x1f) as u32;
    let man = (h & 0x3ff) as u32;
    let bits = match exp {
        0 if man == 0 => sign << 31,
        // Subnormal: shift the leading one up into place, paying for each
        // shift out of the exponent. `k` shifts leave a value of 2^(-14-k).
        0 => {
            let mut k = 0u32;
            let mut m = man;
            while m & 0x400 == 0 {
                m <<= 1;
                k += 1;
            }
            (sign << 31) | ((127 - 14 - k) << 23) | ((m & 0x3ff) << 13)
        }
        0x1f => (sign << 31) | (0xff << 23) | (man << 13),
        _ => (sign << 31) | ((exp + 127 - 15) << 23) | (man << 13),
    };
    f32::from_bits(bits)
}

/// Clamp a linear float channel into an 8-bit sRGB-ish value.
fn float_channel(v: f32) -> u32 {
    let v = if v.is_finite() { v.clamp(0.0, 1.0) } else { 0.0 };
    (v * 255.0 + 0.5) as u32
}

struct Reader<'a> {
    buf: &'a [u8],
    pos: usize,
}

impl<'a> Reader<'a> {
    fn u32(&mut self) -> Result<u32, String> {
        let b = self
            .buf
            .get(self.pos..self.pos + 4)
            .ok_or("texture metadata ends early")?;
        self.pos += 4;
        Ok(u32::from_le_bytes(b.try_into().unwrap()))
    }
    fn u32s(&mut self, n: usize) -> Result<Vec<u32>, String> {
        (0..n).map(|_| self.u32()).collect()
    }
    fn skip(&mut self, n: usize) {
        self.pos += n;
    }
}

/// Read a `u32` at `pos`, if it is in bounds.
fn peek(data: &[u8], pos: usize) -> Option<u32> {
    data.get(pos..pos + 4)
        .map(|b| u32::from_le_bytes(b.try_into().unwrap()))
}

/// `SizeZ` when `pos` holds the `SizeX, SizeY, SizeZ` triple closing this mip.
fn closes_mip(data: &[u8], pos: usize, width: u32, height: u32) -> Option<u32> {
    if peek(data, pos) != Some(width) || peek(data, pos + 4) != Some(height) {
        return None;
    }
    peek(data, pos + 8).filter(|z| (1..=4096).contains(z))
}

/// How many slices a mip's payload holds.
///
/// A volume texture reports its depth in the mip's own `SizeZ`, halving down
/// the chain. A cubemap or array reports `SizeZ` of 1 and instead keeps its
/// slice count in `PackedData`, constant across mips.
fn payload_slices(mip_size_z: u32, packed_slices: u32) -> u32 {
    if mip_size_z > 1 {
        mip_size_z
    } else {
        packed_slices.max(1)
    }
}

/// Locate the first `FString` whose text starts with `PF_`, which is the
/// pixel-format name of `FTexturePlatformData`.
fn find_format(data: &[u8]) -> Option<(usize, usize)> {
    for i in 12..data.len().saturating_sub(8) {
        let len = i32::from_le_bytes(data[i..i + 4].try_into().unwrap());
        if (4..24).contains(&len)
            && data.len() > i + 4 + len as usize
            && &data[i + 4..i + 6] == b"PF"
            && data[i + 3 + len as usize] == 0
        {
            return Some((i, len as usize));
        }
    }
    None
}

/// Parse the export blob of a cooked Texture2D `.uasset`.
///
/// `data` is everything after the zen package header (`header_size`).
pub fn parse_texture(data: &[u8]) -> Result<Texture, String> {
    // A render target or other runtime-generated texture cooks no pixel data,
    // so it carries no pixel-format name at all.
    let (fs, len) = find_format(data)
        .ok_or("no cooked pixel data; a render target or runtime-generated texture")?;
    let format = String::from_utf8_lossy(&data[fs + 4..fs + 3 + len]).into_owned();

    let mut pre = Reader {
        buf: data,
        pos: fs - 12,
    };
    let size_x = pre.u32()?;
    let size_y = pre.u32()?;
    // The low bits hold NumSlices; the high bits are cook flags.
    let packed = pre.u32()?;
    let slices = (packed & 0x0FFF_FFFF).max(1);

    let mut r = Reader {
        buf: data,
        pos: fs + 4 + len,
    };
    let first_mip = r.u32()?;
    let num_mips = r.u32()?;

    if num_mips == 0 {
        // Virtual texture: the mip chain is replaced by FVirtualTextureBuiltData.
        let vt = parse_vt_body(data, r.pos, format, size_x, size_y)?;
        return Ok(Texture {
            width: vt.width,
            height: vt.height,
            format: vt.format.clone(),
            num_mips: vt.num_mips,
            payload: Payload::Virtual(vt),
        });
    }

    if num_mips > 20 || first_mip > 20 {
        return Err(format!(
            "implausible mip chain (first {first_mip}, count {num_mips})"
        ));
    }
    if block_layout(&format).is_none() {
        return Err(format!("{format} is not supported yet"));
    }

    // Walk the chain. Each mip serializes its bulk-data reference, then the
    // payload if it is inline, then its own SizeX/SizeY/SizeZ — which is what
    // tells the two cases apart and validates the walk as it goes.
    let mut mips = Vec::with_capacity(num_mips as usize);
    let mut bulk_offset = 0u64;
    for m in 0..num_mips {
        let shift = first_mip + m;
        let width = (size_x >> shift).max(1);
        let height = (size_y >> shift).max(1);
        // One slice; a cubemap, array or volume repeats it SizeZ times.
        let slice = surface_bytes(&format, width, height).unwrap();
        let _bulk_ref = r.u32()?;
        let source = if let Some(z) = closes_mip(data, r.pos, width, height) {
            // External: the trailer sits right here, so this mip is in the bulk.
            let len = slice * payload_slices(z, slices) as u64;
            let source = MipSource::Bulk {
                offset: bulk_offset,
                len,
            };
            bulk_offset += len;
            source
        } else {
            // Inline: the payload sits between here and the trailer, so its
            // length has to be guessed from the slice counts the header allows.
            // Landing exactly on the trailer is what confirms the guess.
            let mut depths = vec![1, slices, (slices >> shift).max(1)];
            depths.dedup();
            let hit = depths.iter().find_map(|&d| {
                let end = r.pos + (slice * d as u64) as usize;
                closes_mip(data, end, width, height).map(|_| end)
            });
            let Some(end) = hit else {
                return Err(format!(
                    "mip {m} ({width}x{height}) does not close where the chain predicts"
                ));
            };
            let start = r.pos;
            r.pos = end;
            MipSource::Inline(data[start..end].to_vec())
        };
        r.skip(12);
        mips.push(Mip {
            width,
            height,
            source,
        });
    }

    Ok(Texture {
        width: mips[0].width,
        height: mips[0].height,
        format,
        num_mips,
        payload: Payload::Classic(mips),
    })
}

/// Parse `FVirtualTextureBuiltData`, positioned just past `NumMips == 0`.
///
/// `size_x`/`size_y` are the authored size, which is larger than the cooked
/// virtual texture whenever the cook applied an LOD bias.
fn parse_vt_body(
    data: &[u8],
    pos: usize,
    format: String,
    size_x: u32,
    size_y: u32,
) -> Result<VtData, String> {
    let mut r = Reader { buf: data, pos };
    r.skip(12); // three constant u32s
    let _width_in_blocks = r.u32()?;
    let _height_in_blocks = r.u32()?;
    let tile_size = r.u32()?;
    let tile_border = r.u32()?;
    let _layers = r.u32()?;
    let tile_bytes = r.u32()?;
    let num_mips = r.u32()?;
    let width = r.u32()?;
    let height = r.u32()?;
    // The cooked size must be the authored size shrunk by a whole number of
    // mip levels; anything else means the anchor landed in the wrong place.
    let shift_ok = (0..=16).any(|k| width << k == size_x && height << k == size_y);
    if !shift_ok || width == 0 || height == 0 {
        return Err(format!(
            "size fields disagree ({size_x}x{size_y} vs {width}x{height})"
        ));
    }
    if tile_size == 0 || tile_size > 1024 || tile_bytes == 0 || num_mips == 0 || num_mips > 16 {
        return Err("implausible virtual-texture header".to_string());
    }

    // The per-mip arrays are TArrays and carry their own count prefix.
    let n1 = r.u32()?;
    if n1 != num_mips {
        return Err(format!("chunk-index array has {n1} entries for {num_mips} mips"));
    }
    let chunk_index_per_mip = r.u32s(num_mips as usize)?;
    let n2 = r.u32()?;
    if n2 != num_mips {
        return Err(format!("mip-offset array has {n2} entries for {num_mips} mips"));
    }
    let mip_offset_in_chunk = r.u32s(num_mips as usize)?;
    let num_tables = r.u32()?;
    if num_tables != num_mips {
        return Err(format!("{num_tables} tile tables for {num_mips} mips"));
    }
    let mut tables = Vec::with_capacity(num_mips as usize);
    for _ in 0..num_mips {
        let w = r.u32()?;
        let h = r.u32()?;
        let _max_address = r.u32()?;
        let na = r.u32()? as usize;
        if na > 4096 {
            return Err("implausible tile table".to_string());
        }
        let addresses = r.u32s(na)?;
        let no = r.u32()? as usize;
        let offsets = r.u32s(no)?;
        tables.push(TileOffsets {
            width: w,
            height: h,
            addresses,
            offsets,
        });
    }

    // Chunk records follow the second PF_ string and the fallback colour:
    // NumChunks, then per chunk a 20-byte hash, the size, and constants.
    let tail = &data[r.pos..];
    let mut chunk_sizes = Vec::new();
    if let Some((i, len2)) = find_format(tail) {
        let mut p = i + 4 + len2 + 16; // past the string and the fallback colour
        if p + 4 <= tail.len() {
            let n = u32::from_le_bytes(tail[p..p + 4].try_into().unwrap()) as usize;
            p += 4;
            if n <= 16 {
                for _ in 0..n {
                    // 20-byte FIoHash, then the chunk byte size.
                    if p + 24 > tail.len() {
                        break;
                    }
                    let size = u32::from_le_bytes(tail[p + 20..p + 24].try_into().unwrap());
                    chunk_sizes.push(size);
                    // size, u32 = 4, five constant bytes, chunk index.
                    p += 20 + 4 + 4 + 5 + 4;
                }
            }
        }
    }
    if chunk_sizes.is_empty() {
        return Err("no chunk records found".to_string());
    }

    Ok(VtData {
        width,
        height,
        format,
        tile_size,
        tile_border,
        tile_bytes,
        num_mips,
        chunk_index_per_mip,
        mip_offset_in_chunk,
        tables,
        chunk_sizes,
    })
}

/// Decode a `width`x`height` surface to BGRA words.
fn decode_surface(format: &str, data: &[u8], width: usize, height: usize) -> Result<Vec<u32>, String> {
    let mut out = vec![0u32; width * height];
    let need = surface_bytes(format, width as u32, height as u32)
        .ok_or_else(|| format!("{format} is not supported yet"))? as usize;
    if data.len() < need {
        return Err(format!(
            "{format} {width}x{height} needs {need} bytes, {} available",
            data.len()
        ));
    }
    let res = match format {
        "PF_DXT1" => texture2ddecoder::decode_bc1(data, width, height, &mut out),
        "PF_DXT3" => texture2ddecoder::decode_bc2(data, width, height, &mut out),
        "PF_DXT5" => texture2ddecoder::decode_bc3(data, width, height, &mut out),
        "PF_BC4" => texture2ddecoder::decode_bc4(data, width, height, &mut out),
        "PF_BC5" => texture2ddecoder::decode_bc5(data, width, height, &mut out),
        "PF_BC6H" => texture2ddecoder::decode_bc6_unsigned(data, width, height, &mut out),
        "PF_BC7" => texture2ddecoder::decode_bc7(data, width, height, &mut out),
        "PF_B8G8R8A8" => {
            for (i, o) in out.iter_mut().enumerate() {
                let p = &data[i * 4..i * 4 + 4];
                *o = u32::from_le_bytes([p[0], p[1], p[2], p[3]]);
            }
            Ok(())
        }
        "PF_G8" | "PF_A8" => {
            for (i, o) in out.iter_mut().enumerate() {
                let g = data[i] as u32;
                *o = 0xFF00_0000 | g << 16 | g << 8 | g;
            }
            Ok(())
        }
        "PF_R16F" => {
            for (i, o) in out.iter_mut().enumerate() {
                let v = float_channel(half_to_f32(u16::from_le_bytes([
                    data[i * 2],
                    data[i * 2 + 1],
                ])));
                *o = 0xFF00_0000 | v << 16 | v << 8 | v;
            }
            Ok(())
        }
        "PF_FloatRGBA" => {
            for (i, o) in out.iter_mut().enumerate() {
                let p = &data[i * 8..i * 8 + 8];
                let c = |k: usize| {
                    float_channel(half_to_f32(u16::from_le_bytes([p[k * 2], p[k * 2 + 1]])))
                };
                *o = c(3) << 24 | c(0) << 16 | c(1) << 8 | c(2);
            }
            Ok(())
        }
        "PF_A32B32G32R32F" => {
            for (i, o) in out.iter_mut().enumerate() {
                let p = &data[i * 16..i * 16 + 16];
                let c = |k: usize| {
                    float_channel(f32::from_le_bytes(
                        p[k * 4..k * 4 + 4].try_into().unwrap(),
                    ))
                };
                *o = c(3) << 24 | c(0) << 16 | c(1) << 8 | c(2);
            }
            Ok(())
        }
        other => return Err(format!("{other} is not supported yet")),
    };
    res.map_err(|e| format!("decode failed: {e}"))?;
    Ok(out)
}

/// Assembled RGBA image of one mip.
#[derive(Serialize)]
pub struct TextureImage {
    pub width: u32,
    pub height: u32,
    pub format: String,
    /// Which mip was assembled (0 unless the top mip was too large).
    pub mip: u32,
    #[serde(skip)]
    pub rgba: Vec<u8>,
}

/// texture2ddecoder emits BGRA words; write one out as RGBA bytes.
fn put_rgba(rgba: &mut [u8], at: usize, bgra: u32) {
    rgba[at] = (bgra >> 16) as u8;
    rgba[at + 1] = (bgra >> 8) as u8;
    rgba[at + 2] = bgra as u8;
    rgba[at + 3] = (bgra >> 24) as u8;
}

/// Assemble one mip. `ubulk` may be empty for a texture with only inline mips.
pub fn assemble_mip(tex: &Texture, ubulk: &[u8], mip: u32) -> Result<TextureImage, String> {
    let mip = mip.min(tex.num_mips - 1);
    let (width, height) = tex.mip_dims(mip);
    let mut rgba = match &tex.payload {
        Payload::Virtual(vt) => {
            if ubulk.is_empty() {
                return Err("virtual texture has no bulk payload".to_string());
            }
            assemble_vt_mip(vt, ubulk, mip)?
        }
        Payload::Classic(mips) => {
            let m = &mips[mip as usize];
            let data: &[u8] = match &m.source {
                MipSource::Inline(bytes) => bytes,
                MipSource::Bulk { offset, len } => {
                    let (start, end) = (*offset as usize, (*offset + *len) as usize);
                    ubulk
                        .get(start..end)
                        .ok_or_else(|| format!("mip {mip} is beyond the bulk payload"))?
                }
            };
            let pixels = decode_surface(&tex.format, data, width as usize, height as usize)?;
            let mut rgba = vec![0u8; width as usize * height as usize * 4];
            for (i, p) in pixels.iter().enumerate() {
                put_rgba(&mut rgba, i * 4, *p);
            }
            rgba
        }
    };

    // Packed maps (an ORME mask, say) leave the alpha channel unused, so it
    // reads as zero everywhere and would hide the image behind full
    // transparency. Alpha that uniform carries nothing; show the colour.
    if rgba.chunks(4).all(|p| p[3] == 0) {
        for p in rgba.chunks_mut(4) {
            p[3] = 0xFF;
        }
    }

    Ok(TextureImage {
        width,
        height,
        format: tex.format.clone(),
        mip,
        rgba,
    })
}

/// Reassemble a virtual-texture mip from its tiles. Missing tiles stay clear.
fn assemble_vt_mip(vt: &VtData, ubulk: &[u8], mip: u32) -> Result<Vec<u8>, String> {
    let table = &vt.tables[mip as usize];
    let chunk = *vt
        .chunk_index_per_mip
        .get(mip as usize)
        .ok_or("mip out of range")? as usize;
    let chunk_start: u64 = vt.chunk_sizes[..chunk].iter().map(|s| *s as u64).sum();
    let mip_base = chunk_start + vt.mip_offset_in_chunk[mip as usize] as u64;

    let ts = vt.tile_size as usize;
    let border = vt.tile_border as usize;
    let padded = ts + 2 * border;
    let tile_bytes = vt.tile_bytes as usize;

    let w = (vt.width >> mip).max(1) as usize;
    let h = (vt.height >> mip).max(1) as usize;
    let mut rgba = vec![0u8; w * h * 4];

    for ty in 0..table.height {
        for tx in 0..table.width {
            let Some(off) = table.offset_of(morton(tx, ty)) else {
                continue;
            };
            let start = mip_base as usize + off as usize * tile_bytes;
            let Some(tile) = ubulk.get(start..start + tile_bytes) else {
                return Err(format!("tile at ({tx},{ty}) is beyond the payload"));
            };
            let pixels = decode_surface(&vt.format, tile, padded, padded)?;
            // Copy the payload region, cropping the border.
            for y in 0..ts {
                let dy = ty as usize * ts + y;
                if dy >= h {
                    break;
                }
                for x in 0..ts {
                    let dx = tx as usize * ts + x;
                    if dx >= w {
                        break;
                    }
                    put_rgba(
                        &mut rgba,
                        (dy * w + dx) * 4,
                        pixels[(y + border) * padded + (x + border)],
                    );
                }
            }
        }
    }
    Ok(rgba)
}

/// Encode RGBA to a PNG blob.
pub fn to_png(img: &TextureImage) -> Result<Vec<u8>, String> {
    let mut out = Vec::new();
    {
        let mut enc = png::Encoder::new(&mut out, img.width, img.height);
        enc.set_color(png::ColorType::Rgba);
        enc.set_depth(png::BitDepth::Eight);
        let mut writer = enc.write_header().map_err(|e| e.to_string())?;
        writer
            .write_image_data(&img.rgba)
            .map_err(|e| e.to_string())?;
    }
    Ok(out)
}

/// Zen package: offset of the export blob.
pub fn zen_header_size(uasset: &[u8]) -> Option<usize> {
    if uasset.len() < 64 {
        return None;
    }
    let header_size = u32::from_le_bytes(uasset[4..8].try_into().unwrap()) as usize;
    if header_size == 0 || header_size >= uasset.len() {
        return None;
    }
    Some(header_size)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn morton_interleaves_bits() {
        assert_eq!(morton(0, 0), 0);
        assert_eq!(morton(1, 0), 1);
        assert_eq!(morton(0, 1), 2);
        assert_eq!(morton(1, 1), 3);
        assert_eq!(morton(2, 0), 4);
        assert_eq!(morton(47, 7), 1109 | 42);
    }

    #[test]
    fn tile_offsets_resolve_ranges_and_gaps() {
        let t = TileOffsets {
            width: 48,
            height: 8,
            addresses: vec![0, 128, 256, 384, 1024, 1152],
            offsets: vec![0, EMPTY, 128, EMPTY, 256, EMPTY],
        };
        assert_eq!(t.offset_of(0), Some(0));
        assert_eq!(t.offset_of(127), Some(127));
        assert_eq!(t.offset_of(128), None);
        assert_eq!(t.offset_of(256), Some(128));
        assert_eq!(t.offset_of(300), Some(172));
        assert_eq!(t.offset_of(1151), Some(383));
        assert_eq!(t.offset_of(1152), None);
    }

    #[test]
    fn surface_bytes_rounds_up_to_whole_blocks() {
        assert_eq!(surface_bytes("PF_DXT1", 4096, 2048), Some(4096 * 2048 / 2));
        assert_eq!(surface_bytes("PF_DXT5", 2048, 2048), Some(4 * 1024 * 1024));
        // A mip smaller than one block still costs a whole block.
        assert_eq!(surface_bytes("PF_DXT1", 1, 1), Some(8));
        assert_eq!(surface_bytes("PF_DXT5", 2, 2), Some(16));
        assert_eq!(surface_bytes("PF_B8G8R8A8", 32, 2), Some(256));
        assert_eq!(surface_bytes("PF_A32B32G32R32F", 32, 2), Some(1024));
        assert_eq!(surface_bytes("PF_Nonesuch", 4, 4), None);
    }

    #[test]
    fn half_floats_round_trip_known_values() {
        assert_eq!(half_to_f32(0x0000), 0.0);
        assert_eq!(half_to_f32(0x3C00), 1.0);
        assert_eq!(half_to_f32(0x4000), 2.0);
        assert_eq!(half_to_f32(0xBC00), -1.0);
        assert_eq!(half_to_f32(0x3800), 0.5);
        // Subnormals renormalise rather than flushing to zero: the largest is
        // just under 2^-14 and the smallest is 2^-24.
        assert_eq!(half_to_f32(0x0200), 2f32.powi(-15));
        assert_eq!(half_to_f32(0x03ff), (1023.0 / 1024.0) * 2f32.powi(-14));
        assert_eq!(half_to_f32(0x0001), 2f32.powi(-24));
        assert_eq!(half_to_f32(0x8001), -2f32.powi(-24));
    }

    #[test]
    fn float_channels_clamp_and_reject_nan() {
        assert_eq!(float_channel(0.0), 0);
        assert_eq!(float_channel(1.0), 255);
        assert_eq!(float_channel(2.5), 255);
        assert_eq!(float_channel(-1.0), 0);
        assert_eq!(float_channel(f32::NAN), 0);
    }

    /// A classic chain closes each mip with its own dimensions, which is how
    /// the walk tells an inline payload from one that lives in the ubulk.
    #[test]
    fn closes_mip_matches_only_the_exact_dimensions() {
        let mut data = Vec::new();
        for v in [64u32, 32, 1] {
            data.extend_from_slice(&v.to_le_bytes());
        }
        assert_eq!(closes_mip(&data, 0, 64, 32), Some(1));
        assert_eq!(closes_mip(&data, 0, 32, 64), None);
        assert_eq!(closes_mip(&data, 4, 32, 1), None);
        // Out of bounds is not a match rather than a panic.
        assert_eq!(closes_mip(&data, 8, 1, 0), None);
    }

    #[test]
    fn slice_counts_come_from_the_right_field() {
        // Plain 2D.
        assert_eq!(payload_slices(1, 1), 1);
        // Cubemap: six faces, but the mip still calls itself one deep.
        assert_eq!(payload_slices(1, 6), 6);
        // Volume: the mip's own depth wins, and it halves down the chain.
        assert_eq!(payload_slices(32, 32), 32);
        assert_eq!(payload_slices(16, 32), 16);
    }
}
