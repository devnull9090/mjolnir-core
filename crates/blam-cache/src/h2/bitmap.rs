//! Halo 2 bitmaps: the `bitm` data elements and their pixels in MCC's
//! `textures.dat`.
//!
//! A `bitm` tag's bitmaps block (+0x44) has 168-byte elements on MCC (116 on
//! Xbox and Vista): `bitm` signature, i16 width, i16 height, u8 depth, u8
//! flags, i16 type (0 2D, 1 3D, 2 cube) at 0x0A, i16 format at 0x0C, i16
//! mipmap count at 0x14, the pixel entry's offset in `textures.dat` at 0x38
//! and its size at 0x50. An entry is i32 n, i32 sizes[n], then the n chunks
//! back to back: a positive size is a zlib stream, a negative one |size|
//! stored bytes. The chunks concatenate to every mip from the largest down,
//! linear (MCC never swizzles), as many levels as the mipmap count plus one.

use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;

use crate::h2::Tag;
use crate::Error;

/// One bitmap of a `bitm` tag.
#[derive(Debug, Clone, Copy)]
pub struct Info {
    pub width: u32,
    pub height: u32,
    pub depth: u32,
    /// 0 2D, 1 3D, 2 cube.
    pub kind: u16,
    pub format: u16,
    /// Levels below the first.
    pub mipmaps: u32,
    pub offset: u32,
    pub size: u32,
}

/// The bitmaps of a `bitm` tag.
pub fn infos(tag: &Tag<'_>) -> Vec<Info> {
    tag.root
        .block(0x44, 0xA8)
        .iter()
        .filter(|e| e.bytes(0, 4) == b"mtib")
        .map(|e| Info {
            width: e.i16(4).max(1) as u32,
            height: e.i16(6).max(1) as u32,
            depth: (e.u8(8) as u32).max(1),
            kind: e.u16(0x0A),
            format: e.u16(0x0C),
            mipmaps: e.i16(0x14).max(0) as u32,
            offset: e.u32(0x38) & 0x3FFF_FFFF,
            size: e.u32(0x50),
        })
        .collect()
}

/// A decoded image, RGBA8.
#[derive(Debug, Clone)]
pub struct Image {
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<u8>,
}

/// A format's name, for messages.
pub fn format_name(format: u16) -> &'static str {
    match format {
        0 => "A8",
        1 => "Y8",
        2 => "AY8",
        3 => "A8Y8",
        6 => "R5G6B5",
        8 => "A1R5G5B5",
        9 => "A4R4G4B4",
        10 => "X8R8G8B8",
        11 => "A8R8G8B8",
        14 => "DXT1",
        15 => "DXT3",
        16 => "DXT5",
        17 => "P8-bump",
        18 => "P8",
        19 => "ARGBFP32",
        20 => "RGBFP32",
        21 => "RGBFP16",
        22 => "V8U8",
        23 => "G8B8",
        _ => "unknown",
    }
}

/// Bytes one level of `format` takes at `w` x `h`, or `None` when the format
/// is not decoded here.
fn level_bytes(format: u16, w: u32, h: u32) -> Option<usize> {
    let (w, h) = (w as usize, h as usize);
    let blocks = w.div_ceil(4) * h.div_ceil(4);
    Some(match format {
        0 | 1 | 2 => w * h,
        3 | 6 | 8 | 9 | 22 | 23 => w * h * 2,
        10 | 11 => w * h * 4,
        14 => blocks * 8,
        15 | 16 => blocks * 16,
        _ => return None,
    })
}

/// Read a `textures.dat` entry's bytes.
pub fn read_entry(textures: &Path, offset: u32, size: u32) -> Result<Vec<u8>, Error> {
    let io = |e| Error::Io(textures.to_path_buf(), e);
    let mut f = File::open(textures).map_err(io)?;
    f.seek(SeekFrom::Start(offset as u64)).map_err(io)?;
    let len = f.metadata().map_err(io)?.len();
    if size < 8 || offset as u64 + size as u64 > len {
        return Err(Error::Format(format!("textures.dat entry at {offset:#x} ({size} bytes) is outside the file")));
    }
    let mut entry = vec![0u8; size as usize];
    f.read_exact(&mut entry).map_err(io)?;
    let n = i32::from_le_bytes(entry[0..4].try_into().unwrap());
    if !(1..=4096).contains(&n) || 4 + n as usize * 4 > entry.len() {
        return Err(Error::Format(format!("textures.dat entry at {offset:#x} claims {n} chunks")));
    }
    let mut at = 4 + n as usize * 4;
    let mut out = Vec::new();
    for i in 0..n as usize {
        let s = i32::from_le_bytes(entry[4 + i * 4..8 + i * 4].try_into().unwrap());
        let len = s.unsigned_abs() as usize;
        let chunk = entry
            .get(at..at + len)
            .ok_or_else(|| Error::Format(format!("textures.dat entry at {offset:#x}: chunk {i} runs past the entry")))?;
        if s < 0 {
            out.extend_from_slice(chunk);
        } else {
            flate2::read::ZlibDecoder::new(chunk)
                .read_to_end(&mut out)
                .map_err(|e| Error::Format(format!("textures.dat entry at {offset:#x}, chunk {i}: {e}")))?;
        }
        at += len;
    }
    Ok(out)
}

fn rgb565(v: u16) -> [u8; 3] {
    let r = ((v >> 11) & 31) as u32;
    let g = ((v >> 5) & 63) as u32;
    let b = (v & 31) as u32;
    [(r * 255 / 31) as u8, (g * 255 / 63) as u8, (b * 255 / 31) as u8]
}

/// Decode one level to RGBA8.
fn decode_level(format: u16, w: u32, h: u32, data: &[u8]) -> Result<Vec<u8>, Error> {
    let n = (w * h) as usize;
    let mut rgba = vec![0u8; n * 4];
    let px = |rgba: &mut Vec<u8>, i: usize, p: [u8; 4]| rgba[i * 4..i * 4 + 4].copy_from_slice(&p);
    match format {
        0 => (0..n).for_each(|i| px(&mut rgba, i, [255, 255, 255, data[i]])),
        1 => (0..n).for_each(|i| px(&mut rgba, i, [data[i], data[i], data[i], 255])),
        2 => (0..n).for_each(|i| px(&mut rgba, i, [data[i], data[i], data[i], data[i]])),
        3 => (0..n).for_each(|i| {
            let (y, a) = (data[i * 2], data[i * 2 + 1]);
            px(&mut rgba, i, [y, y, y, a])
        }),
        6 => (0..n).for_each(|i| {
            let c = rgb565(u16::from_le_bytes([data[i * 2], data[i * 2 + 1]]));
            px(&mut rgba, i, [c[0], c[1], c[2], 255])
        }),
        8 => (0..n).for_each(|i| {
            let v = u16::from_le_bytes([data[i * 2], data[i * 2 + 1]]) as u32;
            let c = |s: u32| (((v >> s) & 31) * 255 / 31) as u8;
            px(&mut rgba, i, [c(10), c(5), c(0), if v & 0x8000 != 0 { 255 } else { 0 }])
        }),
        9 => (0..n).for_each(|i| {
            let v = u16::from_le_bytes([data[i * 2], data[i * 2 + 1]]) as u32;
            let c = |s: u32| (((v >> s) & 15) * 17) as u8;
            px(&mut rgba, i, [c(8), c(4), c(0), c(12)])
        }),
        10 | 11 => (0..n).for_each(|i| {
            let p = &data[i * 4..i * 4 + 4];
            px(&mut rgba, i, [p[2], p[1], p[0], if format == 10 { 255 } else { p[3] }])
        }),
        // Signed two-channel normals: blue rebuilt from the unit length.
        22 | 23 => (0..n).for_each(|i| {
            let (u, v) = if format == 22 {
                (data[i * 2] as i8 as f32 / 127.0, data[i * 2 + 1] as i8 as f32 / 127.0)
            } else {
                (data[i * 2 + 1] as f32 / 127.5 - 1.0, data[i * 2] as f32 / 127.5 - 1.0)
            };
            let z = (1.0 - u * u - v * v).max(0.0).sqrt();
            let b = |x: f32| ((x * 0.5 + 0.5) * 255.0).round().clamp(0.0, 255.0) as u8;
            px(&mut rgba, i, [b(u), b(v), b(z), 255])
        }),
        14 | 15 | 16 => {
            // Decode on whole blocks, then crop to the level.
            let (bw, bh) = (w.div_ceil(4) * 4, h.div_ceil(4) * 4);
            let mut out = vec![0u32; (bw * bh) as usize];
            let r = match format {
                14 => texture2ddecoder::decode_bc1(data, bw as usize, bh as usize, &mut out),
                15 => texture2ddecoder::decode_bc2(data, bw as usize, bh as usize, &mut out),
                _ => texture2ddecoder::decode_bc3(data, bw as usize, bh as usize, &mut out),
            };
            r.map_err(|e| Error::Format(format!("{}: {e}", format_name(format))))?;
            for y in 0..h {
                for x in 0..w {
                    let c = out[(y * bw + x) as usize];
                    px(&mut rgba, (y * w + x) as usize, [(c >> 16) as u8, (c >> 8) as u8, c as u8, (c >> 24) as u8]);
                }
            }
        }
        f => return Err(Error::Unsupported(format!("bitmap format {} ({f})", format_name(f)))),
    }
    Ok(rgba)
}

/// A cube map's six faces at their largest level, in D3D order (+X, -X,
/// +Y, -Y, +Z, -Z) on Halo's axes. MCC stores a cube mip-major, the six
/// faces of each level together, in the order +X, +Y, -X, -Y, +Z, -Z
/// (checked on Lockout's and the Forerunner interiors' cubes by matching
/// every face's edge texels across each seam: this order scores 13 against
/// 65 for the next best and 110 for D3D's own). No face is flipped.
pub fn decode_cube(info: &Info, data: &[u8]) -> Result<Vec<Image>, Error> {
    if info.kind != 2 {
        return Err(Error::Format("not a cube map".into()));
    }
    let size = level_bytes(info.format, info.width, info.height)
        .ok_or_else(|| Error::Unsupported(format!("bitmap format {} ({})", format_name(info.format), info.format)))?;
    const STORED_FOR_D3D: [usize; 6] = [0, 2, 1, 3, 4, 5];
    STORED_FOR_D3D
        .iter()
        .map(|&f| {
            let bytes = data
                .get(f * size..(f + 1) * size)
                .ok_or_else(|| Error::Format(format!("{} bytes of pixels for a six-face cube of {size} each", data.len())))?;
            Ok(Image { width: info.width, height: info.height, rgba: decode_level(info.format, info.width, info.height, bytes)? })
        })
        .collect()
}

/// Decode a 2D bitmap's mip chain (or a cube map's or volume's first face
/// or slice, the largest level only).
pub fn decode(info: &Info, data: &[u8]) -> Result<Vec<Image>, Error> {
    let mut out = Vec::new();
    let mut at = 0usize;
    let (mut w, mut h) = (info.width, info.height);
    let levels = if info.kind == 0 { info.mipmaps + 1 } else { 1 };
    for _ in 0..levels {
        let size = level_bytes(info.format, w, h)
            .ok_or_else(|| Error::Unsupported(format!("bitmap format {} ({})", format_name(info.format), info.format)))?;
        let Some(bytes) = data.get(at..at + size) else { break };
        out.push(Image { width: w, height: h, rgba: decode_level(info.format, w, h, bytes)? });
        at += size;
        w = (w / 2).max(1);
        h = (h / 2).max(1);
    }
    if out.is_empty() {
        return Err(Error::Format(format!("{} bytes of pixels for a {}x{} {}", data.len(), info.width, info.height, format_name(info.format))));
    }
    Ok(out)
}

pub fn write_png(path: &Path, img: &Image) -> Result<(), Error> {
    let io = |e| Error::Io(path.to_path_buf(), e);
    let f = File::create(path).map_err(io)?;
    let mut enc = png::Encoder::new(std::io::BufWriter::new(f), img.width, img.height);
    enc.set_color(png::ColorType::Rgba);
    enc.set_depth(png::BitDepth::Eight);
    let mut w = enc.write_header().map_err(|e| Error::Format(format!("{}: {e}", path.display())))?;
    w.write_image_data(&img.rgba).map_err(|e| Error::Format(format!("{}: {e}", path.display())))?;
    Ok(())
}

/// An uncompressed BGRA8 DDS holding the bitmap's own mip chain, as halo2ue
/// writes beside each PNG (tools/level/ce_material_spec.py imports it in
/// preference, so a detail map's authored small mips survive).
pub fn write_dds(path: &Path, mips: &[Image]) -> Result<(), Error> {
    let top = &mips[0];
    let mut b = Vec::new();
    let u = |b: &mut Vec<u8>, v: u32| b.extend_from_slice(&v.to_le_bytes());
    b.extend_from_slice(b"DDS ");
    u(&mut b, 124);
    // caps | height | width | pitch | pixel format | mipmap count
    u(&mut b, 0x1 | 0x2 | 0x4 | 0x8 | 0x1000 | 0x20000);
    u(&mut b, top.height);
    u(&mut b, top.width);
    u(&mut b, top.width * 4);
    u(&mut b, 0);
    u(&mut b, mips.len() as u32);
    b.extend_from_slice(&[0u8; 44]);
    u(&mut b, 32);
    u(&mut b, 0x41); // RGB | alpha pixels
    u(&mut b, 0);
    u(&mut b, 32);
    u(&mut b, 0x00FF_0000);
    u(&mut b, 0x0000_FF00);
    u(&mut b, 0x0000_00FF);
    u(&mut b, 0xFF00_0000);
    u(&mut b, 0x1000 | 0x8 | 0x40_0000); // texture | complex | mipmap
    b.extend_from_slice(&[0u8; 16]);
    for m in mips {
        for p in m.rgba.chunks_exact(4) {
            b.extend_from_slice(&[p[2], p[1], p[0], p[3]]);
        }
    }
    std::fs::write(path, b).map_err(|e| Error::Io(path.to_path_buf(), e))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// MCC's A8R8G8B8 is stored B, G, R, A; X8R8G8B8 ignores the fourth byte.
    #[test]
    fn argb_formats_come_out_rgba() {
        assert_eq!(decode_level(11, 1, 1, &[1, 2, 3, 4]).unwrap(), vec![3, 2, 1, 4]);
        assert_eq!(decode_level(10, 1, 1, &[1, 2, 3, 4]).unwrap(), vec![3, 2, 1, 255]);
    }

    /// The sky's 512 x 256 X8R8G8B8 bitmap with nine mipmaps took 699,052
    /// bytes in textures.dat: the levels down to 1 x 1, not 2 x 1.
    #[test]
    fn a_chain_runs_to_one_pixel() {
        let total: usize = (0..10).map(|k| level_bytes(10, (512u32 >> k).max(1), (256u32 >> k).max(1)).unwrap()).sum();
        assert_eq!(total, 699_052);
    }
}
