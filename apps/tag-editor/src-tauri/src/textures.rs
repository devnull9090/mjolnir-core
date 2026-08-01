//! Cooked Texture2D (virtual texture) reading.
//!
//! Format documented in `docs/ue_texture_format.md`. Every shipped Texture2D
//! in this build is a virtual texture: the `.uasset` export carries the tile
//! metadata and the `.ubulk` holds fixed-size border-padded tiles addressed
//! by Morton code through an RLE offset table.

use serde::Serialize;

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

/// Parse the export blob of a cooked Texture2D `.uasset`.
///
/// `data` is everything after the zen package header (`header_size`).
pub fn parse_vt(data: &[u8]) -> Result<VtData, String> {
    // Anchor: the first FString starting with "PF_".
    let mut anchor = None;
    for i in 12..data.len().saturating_sub(8) {
        let len = i32::from_le_bytes(data[i..i + 4].try_into().unwrap());
        if (4..24).contains(&len)
            && &data[i + 4..i + 6] == b"PF"
            && data[i + 3 + len as usize] == 0
        {
            anchor = Some((i, len as usize));
            break;
        }
    }
    let (fs, len) = anchor.ok_or("no PF_ pixel format string; not a cooked texture")?;
    let format = String::from_utf8_lossy(&data[fs + 4..fs + 3 + len]).into_owned();

    let mut pre = Reader {
        buf: data,
        pos: fs - 12,
    };
    let width0 = pre.u32()?;
    let height0 = pre.u32()?;
    let layers = pre.u32()?;
    if layers != 1 {
        return Err(format!("{layers} layers; only single-layer textures are supported"));
    }

    let mut r = Reader {
        buf: data,
        pos: fs + 4 + len,
    };
    r.skip(20); // five constant u32s
    let _width_in_blocks = r.u32()?;
    let _height_in_blocks = r.u32()?;
    let tile_size = r.u32()?;
    let tile_border = r.u32()?;
    let _layers2 = r.u32()?;
    let tile_bytes = r.u32()?;
    let num_mips = r.u32()?;
    let width = r.u32()?;
    let height = r.u32()?;
    if width != width0 || height != height0 {
        return Err(format!(
            "size fields disagree ({width0}x{height0} vs {width}x{height})"
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
    let mut t = None;
    for i in 0..tail.len().saturating_sub(8) {
        let len2 = i32::from_le_bytes(tail[i..i + 4].try_into().unwrap());
        if (4..24).contains(&len2)
            && tail.len() > i + 4 + len2 as usize
            && &tail[i + 4..i + 6] == b"PF"
            && tail[i + 3 + len2 as usize] == 0
        {
            t = Some(i + 4 + len2 as usize);
            break;
        }
    }
    if let Some(mut p) = t {
        p += 16; // fallback colour, 4 floats
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

/// Decode one tile's blocks to RGBA8, `pixels_per_side` square.
fn decode_tile(format: &str, data: &[u8], px: usize) -> Result<Vec<u32>, String> {
    let mut out = vec![0u32; px * px];
    let res = match format {
        "PF_DXT1" => texture2ddecoder::decode_bc1(data, px, px, &mut out),
        "PF_DXT3" => texture2ddecoder::decode_bc2(data, px, px, &mut out),
        "PF_DXT5" => texture2ddecoder::decode_bc3(data, px, px, &mut out),
        "PF_BC4" => texture2ddecoder::decode_bc4(data, px, px, &mut out),
        "PF_BC5" => texture2ddecoder::decode_bc5(data, px, px, &mut out),
        "PF_BC7" => texture2ddecoder::decode_bc7(data, px, px, &mut out),
        "PF_B8G8R8A8" => {
            for (i, o) in out.iter_mut().enumerate() {
                let p = &data[i * 4..i * 4 + 4];
                *o = u32::from_le_bytes([p[0], p[1], p[2], p[3]]);
            }
            Ok(())
        }
        "PF_G8" => {
            for (i, o) in out.iter_mut().enumerate() {
                let g = data[i] as u32;
                *o = 0xFF00_0000 | g << 16 | g << 8 | g;
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

/// Assemble one mip from the ubulk payload. Missing tiles stay transparent.
pub fn assemble_mip(vt: &VtData, ubulk: &[u8], mip: u32) -> Result<TextureImage, String> {
    let mip = mip.min(vt.num_mips - 1);
    let table = &vt.tables[mip as usize];
    let chunk = *vt
        .chunk_index_per_mip
        .get(mip as usize)
        .ok_or("mip out of range")? as usize;
    let chunk_start: u64 = vt.chunk_sizes[..chunk].iter().map(|s| *s as u64).sum();
    let mip_base = chunk_start + vt.mip_offset_in_chunk[mip as usize] as u64;

    let mip_w = (vt.width >> mip).max(1);
    let mip_h = (vt.height >> mip).max(1);
    let ts = vt.tile_size as usize;
    let border = vt.tile_border as usize;
    let padded = ts + 2 * border;
    let tile_bytes = vt.tile_bytes as usize;

    let w = mip_w as usize;
    let h = mip_h as usize;
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
            let pixels = decode_tile(&vt.format, tile, padded)?;
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
                    // texture2ddecoder emits BGRA words; unpack to RGBA bytes.
                    let p = pixels[(y + border) * padded + (x + border)];
                    let d = (dy * w + dx) * 4;
                    rgba[d] = (p >> 16) as u8;
                    rgba[d + 1] = (p >> 8) as u8;
                    rgba[d + 2] = p as u8;
                    rgba[d + 3] = (p >> 24) as u8;
                }
            }
        }
    }

    Ok(TextureImage {
        width: mip_w,
        height: mip_h,
        format: vt.format.clone(),
        mip,
        rgba,
    })
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

/// Zen package: offset of the export blob and a quick check that the name
/// map mentions a `PF_` pixel format (true for every cooked Texture2D).
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
}
