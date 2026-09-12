//! Writing a texture as DDS in its cooked pixel format, every mip included.
//!
//! A PNG export decodes to RGBA and keeps one mip; a DDS keeps the bytes the
//! game ships — BC1, BC3, BC5, BC7, BC6H, or the uncompressed layouts — so
//! nothing is re-encoded and the whole mip chain travels. Tools that speak
//! DDS (texconv, the GIMP and Paint.NET plugins, Blender's importers) open it
//! directly.
//!
//! Layout follows `DDS_HEADER` (124 bytes after the magic) and, for formats
//! with no legacy FourCC, the `DDS_HEADER_DXT10` extension with the DXGI
//! format. The classic BC1/BC2/BC3 names are written as `DXT1`/`DXT3`/`DXT5`,
//! which every reader handles; BC4, BC5, BC6H, BC7 and the float formats go
//! through the DX10 header.
//!
//! A virtual texture's mips are stored as tiles, Morton-addressed, with a
//! border around each; here the payload blocks of every tile are copied back
//! into a linear block image per mip — no decode, just block moves. Tiles the
//! cook left out come out as zero blocks.

use crate::{block_layout, morton, MipSource, Payload, Texture, VtData};

const DDSD_CAPS: u32 = 0x1;
const DDSD_HEIGHT: u32 = 0x2;
const DDSD_WIDTH: u32 = 0x4;
const DDSD_PIXELFORMAT: u32 = 0x1000;
const DDSD_MIPMAPCOUNT: u32 = 0x2_0000;
const DDSD_LINEARSIZE: u32 = 0x8_0000;
const DDSD_PITCH: u32 = 0x8;

const DDPF_ALPHAPIXELS: u32 = 0x1;
const DDPF_FOURCC: u32 = 0x4;
const DDPF_RGB: u32 = 0x40;
const DDPF_LUMINANCE: u32 = 0x2_0000;

const DDSCAPS_COMPLEX: u32 = 0x8;
const DDSCAPS_TEXTURE: u32 = 0x1000;
const DDSCAPS_MIPMAP: u32 = 0x40_0000;

/// How the pixel format is spelled in the header.
enum Spelling {
    /// A legacy FourCC every reader knows.
    FourCc([u8; 4]),
    /// The DX10 extension header with a DXGI format.
    Dxgi(u32),
    /// Uncompressed, described by bit masks: (bit count, r, g, b, a, flags).
    Masks(u32, u32, u32, u32, u32, u32),
}

fn spelling(format: &str) -> Result<Spelling, String> {
    Ok(match format {
        "PF_DXT1" => Spelling::FourCc(*b"DXT1"),
        "PF_DXT3" => Spelling::FourCc(*b"DXT3"),
        "PF_DXT5" => Spelling::FourCc(*b"DXT5"),
        "PF_BC4" => Spelling::Dxgi(80),
        "PF_BC5" => Spelling::Dxgi(83),
        "PF_BC6H" => Spelling::Dxgi(95),
        "PF_BC7" => Spelling::Dxgi(98),
        "PF_B8G8R8A8" => Spelling::Masks(
            32,
            0x00FF_0000,
            0x0000_FF00,
            0x0000_00FF,
            0xFF00_0000,
            DDPF_RGB | DDPF_ALPHAPIXELS,
        ),
        "PF_G8" => Spelling::Masks(8, 0xFF, 0, 0, 0, DDPF_LUMINANCE),
        "PF_A8" => Spelling::Masks(8, 0, 0, 0, 0xFF, DDPF_ALPHAPIXELS),
        "PF_R16F" => Spelling::Dxgi(54),
        "PF_FloatRGBA" => Spelling::Dxgi(10),
        "PF_A32B32G32R32F" => Spelling::Dxgi(2),
        other => return Err(format!("{other} has no DDS spelling here")),
    })
}

/// Byte size of one mip of `w` x `h` in `format`.
fn mip_bytes(format: &str, w: u32, h: u32) -> Result<u64, String> {
    let (block_bytes, edge) =
        block_layout(format).ok_or_else(|| format!("{format}: unknown layout"))?;
    let bw = (w as u64).div_ceil(edge);
    let bh = (h as u64).div_ceil(edge);
    Ok(bw * bh * block_bytes)
}

/// One mip's cooked bytes, linear, top-left first.
fn mip_data(tex: &Texture, ubulk: &[u8], mip: u32) -> Result<Vec<u8>, String> {
    match &tex.payload {
        Payload::Classic(mips) => {
            let m = mips.get(mip as usize).ok_or("mip out of range")?;
            Ok(match &m.source {
                MipSource::Inline { bytes, .. } => bytes.clone(),
                MipSource::Bulk { offset, len } => ubulk
                    .get(*offset as usize..(*offset + *len) as usize)
                    .ok_or_else(|| format!("mip {mip} is beyond the bulk payload"))?
                    .to_vec(),
            })
        }
        Payload::Virtual(vt) => vt_mip_linear(vt, ubulk, mip),
    }
}

/// Copy a virtual texture mip's payload blocks out of its tiles into a linear
/// block image.
fn vt_mip_linear(vt: &VtData, ubulk: &[u8], mip: u32) -> Result<Vec<u8>, String> {
    let (block_bytes, edge) =
        block_layout(&vt.format).ok_or_else(|| format!("{}: unknown layout", vt.format))?;
    let (block_bytes, edge) = (block_bytes as usize, edge as usize);
    let table = vt.tables.get(mip as usize).ok_or("mip out of range")?;
    let chunk = *vt
        .chunk_index_per_mip
        .get(mip as usize)
        .ok_or("mip out of range")? as usize;
    let chunk_start: u64 = vt.chunk_sizes[..chunk].iter().map(|s| *s as u64).sum();
    let mip_base = chunk_start as usize + vt.mip_offset_in_chunk[mip as usize] as usize;

    let ts = vt.tile_size as usize;
    let border = vt.tile_border as usize;
    let padded = ts + 2 * border;
    if ts % edge != 0 || border % edge != 0 {
        return Err(format!(
            "tile {ts}+{border} is not a whole number of {edge}-pixel blocks"
        ));
    }
    let tile_bytes = vt.tile_bytes as usize;
    let padded_blocks = padded / edge;
    let tile_blocks = ts / edge;
    let border_blocks = border / edge;

    let w = (vt.width >> mip).max(1) as usize;
    let h = (vt.height >> mip).max(1) as usize;
    let bw = w.div_ceil(edge);
    let bh = h.div_ceil(edge);
    let mut out = vec![0u8; bw * bh * block_bytes];

    for ty in 0..table.height {
        for tx in 0..table.width {
            let Some(off) = table.offset_of(morton(tx, ty)) else {
                continue;
            };
            let start = mip_base + off as usize * tile_bytes;
            let Some(tile) = ubulk.get(start..start + tile_bytes) else {
                return Err(format!("tile at ({tx},{ty}) is beyond the payload"));
            };
            for by in 0..tile_blocks {
                let dy = ty as usize * tile_blocks + by;
                if dy >= bh {
                    break;
                }
                let src_row = (by + border_blocks) * padded_blocks;
                for bx in 0..tile_blocks {
                    let dx = tx as usize * tile_blocks + bx;
                    if dx >= bw {
                        break;
                    }
                    let src = (src_row + bx + border_blocks) * block_bytes;
                    let dst = (dy * bw + dx) * block_bytes;
                    if let Some(block) = tile.get(src..src + block_bytes) {
                        out[dst..dst + block_bytes].copy_from_slice(block);
                    }
                }
            }
        }
    }
    Ok(out)
}

/// The texture as a DDS file: header, then every mip's cooked bytes, largest
/// first.
pub fn write_dds(tex: &Texture, ubulk: &[u8]) -> Result<Vec<u8>, String> {
    let spelling = spelling(&tex.format)?;
    let (block_bytes, edge) =
        block_layout(&tex.format).ok_or_else(|| format!("{}: unknown layout", tex.format))?;
    let compressed = edge > 1;

    let mut mips = Vec::with_capacity(tex.num_mips as usize);
    for i in 0..tex.num_mips {
        let (w, h) = tex.mip_dims(i);
        let data = mip_data(tex, ubulk, i)?;
        let want = mip_bytes(&tex.format, w, h)?;
        if data.len() as u64 != want {
            return Err(format!(
                "mip {i} is {} bytes; {w}x{h} {} needs {want}",
                data.len(),
                tex.format
            ));
        }
        mips.push(data);
    }

    let mut out = Vec::new();
    let put = |out: &mut Vec<u8>, v: u32| out.extend_from_slice(&v.to_le_bytes());
    out.extend_from_slice(b"DDS ");
    put(&mut out, 124);
    let mut flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT;
    if tex.num_mips > 1 {
        flags |= DDSD_MIPMAPCOUNT;
    }
    flags |= if compressed {
        DDSD_LINEARSIZE
    } else {
        DDSD_PITCH
    };
    put(&mut out, flags);
    put(&mut out, tex.height);
    put(&mut out, tex.width);
    let pitch_or_size = if compressed {
        mips[0].len() as u32
    } else {
        tex.width * block_bytes as u32
    };
    put(&mut out, pitch_or_size);
    put(&mut out, 0); // depth
    put(&mut out, tex.num_mips);
    for _ in 0..11 {
        put(&mut out, 0); // reserved
    }
    // DDS_PIXELFORMAT
    put(&mut out, 32);
    match &spelling {
        Spelling::FourCc(cc) => {
            put(&mut out, DDPF_FOURCC);
            out.extend_from_slice(cc);
            for _ in 0..5 {
                put(&mut out, 0);
            }
        }
        Spelling::Dxgi(_) => {
            put(&mut out, DDPF_FOURCC);
            out.extend_from_slice(b"DX10");
            for _ in 0..5 {
                put(&mut out, 0);
            }
        }
        Spelling::Masks(bits, r, g, b, a, pf_flags) => {
            put(&mut out, *pf_flags);
            put(&mut out, 0);
            put(&mut out, *bits);
            put(&mut out, *r);
            put(&mut out, *g);
            put(&mut out, *b);
            put(&mut out, *a);
        }
    }
    let mut caps = DDSCAPS_TEXTURE;
    if tex.num_mips > 1 {
        caps |= DDSCAPS_COMPLEX | DDSCAPS_MIPMAP;
    }
    put(&mut out, caps);
    put(&mut out, 0); // caps2
    put(&mut out, 0); // caps3
    put(&mut out, 0); // caps4
    put(&mut out, 0); // reserved2
    debug_assert_eq!(out.len(), 128);

    if let Spelling::Dxgi(dxgi) = spelling {
        put(&mut out, dxgi);
        put(&mut out, 3); // D3D10_RESOURCE_DIMENSION_TEXTURE2D
        put(&mut out, 0); // misc flags
        put(&mut out, 1); // array size
        put(&mut out, 0); // misc flags 2: alpha mode unknown
    }

    for m in &mips {
        out.extend_from_slice(m);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Mip;

    fn classic(format: &str, w: u32, h: u32, mips: u32) -> (Texture, Vec<u8>) {
        let mut ubulk = Vec::new();
        let mut chain = Vec::new();
        for i in 0..mips {
            let (mw, mh) = ((w >> i).max(1), (h >> i).max(1));
            let len = mip_bytes(format, mw, mh).unwrap();
            let offset = ubulk.len() as u64;
            ubulk.extend((0..len).map(|k| (k + i as u64) as u8));
            chain.push(Mip {
                width: mw,
                height: mh,
                source: MipSource::Bulk { offset, len },
            });
        }
        (
            Texture {
                width: w,
                height: h,
                format: format.into(),
                num_mips: mips,
                payload: Payload::Classic(chain),
            },
            ubulk,
        )
    }

    #[test]
    fn a_bc1_chain_writes_a_legacy_header_and_every_mip() {
        let (tex, ubulk) = classic("PF_DXT1", 8, 4, 3);
        let dds = write_dds(&tex, &ubulk).unwrap();
        assert_eq!(&dds[..4], b"DDS ");
        assert_eq!(u32::from_le_bytes(dds[12..16].try_into().unwrap()), 4); // height
        assert_eq!(u32::from_le_bytes(dds[16..20].try_into().unwrap()), 8); // width
        assert_eq!(u32::from_le_bytes(dds[20..24].try_into().unwrap()), 16); // mip 0 bytes
        assert_eq!(u32::from_le_bytes(dds[28..32].try_into().unwrap()), 3); // mips
        assert_eq!(&dds[84..88], b"DXT1");
        // 8x4 = 2 blocks, 4x2 = 1 block, 2x1 = 1 block: 32 bytes of mips.
        assert_eq!(dds.len(), 128 + 16 + 8 + 8);
        assert_eq!(&dds[128..144], &ubulk[..16]);
    }

    #[test]
    fn bc7_goes_through_the_dx10_header() {
        let (tex, ubulk) = classic("PF_BC7", 4, 4, 1);
        let dds = write_dds(&tex, &ubulk).unwrap();
        assert_eq!(&dds[84..88], b"DX10");
        assert_eq!(u32::from_le_bytes(dds[128..132].try_into().unwrap()), 98);
        assert_eq!(dds.len(), 148 + 16);
    }

    #[test]
    fn an_uncompressed_bgra_texture_writes_masks_and_a_pitch() {
        let (tex, ubulk) = classic("PF_B8G8R8A8", 2, 2, 1);
        let dds = write_dds(&tex, &ubulk).unwrap();
        assert_eq!(u32::from_le_bytes(dds[20..24].try_into().unwrap()), 8); // pitch
        assert_eq!(u32::from_le_bytes(dds[88..92].try_into().unwrap()), 32); // bits
        assert_eq!(
            u32::from_le_bytes(dds[92..96].try_into().unwrap()),
            0x00FF_0000
        );
        assert_eq!(dds.len(), 128 + 16);
    }

    #[test]
    fn a_short_mip_is_refused() {
        let (tex, mut ubulk) = classic("PF_DXT5", 4, 4, 1);
        ubulk.truncate(8);
        assert!(write_dds(&tex, &ubulk).is_err());
    }
}
