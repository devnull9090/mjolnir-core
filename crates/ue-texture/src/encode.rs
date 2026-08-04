//! Writing new pixels back into a cooked texture payload.
//!
//! The whole approach rests on one property: re-encoding a texture at its
//! shipped dimensions and pixel format produces a payload of *exactly* the
//! shipped byte size. Every offset the metadata holds — virtual-texture tile
//! offsets, classic mip offsets, chunk sizes — therefore stays valid, and a
//! swap becomes "replace the bytes of one chunk" rather than a re-cook. None
//! of the metadata in the `.uasset` is touched at all for a virtual texture.
//!
//! A tile or mip is rewritten in place inside a copy of the shipped payload,
//! so anything the reader does not model (chunk headers, alignment padding,
//! tiles no table points at) survives untouched.

use crate::{morton, surface_bytes, Mip, MipSource, Payload, Texture, VtData};

/// An 8-bit RGBA image, the common currency between PNG files and surfaces.
#[derive(Clone)]
pub struct Image {
    pub width: u32,
    pub height: u32,
    /// `width * height * 4` bytes.
    pub rgba: Vec<u8>,
}

impl Image {
    pub fn new(width: u32, height: u32, rgba: Vec<u8>) -> Result<Image, String> {
        let want = width as usize * height as usize * 4;
        if rgba.len() != want {
            return Err(format!(
                "{width}x{height} RGBA needs {want} bytes, got {}",
                rgba.len()
            ));
        }
        Ok(Image {
            width,
            height,
            rgba,
        })
    }

    fn texel(&self, x: i64, y: i64) -> [u8; 4] {
        let x = x.clamp(0, self.width as i64 - 1) as usize;
        let y = y.clamp(0, self.height as i64 - 1) as usize;
        let at = (y * self.width as usize + x) * 4;
        [
            self.rgba[at],
            self.rgba[at + 1],
            self.rgba[at + 2],
            self.rgba[at + 3],
        ]
    }

    /// Resample to `width`x`height` by averaging each destination pixel's
    /// source footprint. Downscaling is the case that matters — an authored
    /// skin is fitted to the shipped mip — and averaging avoids the aliasing a
    /// nearest-neighbour fit would bake in permanently.
    pub fn resized(&self, width: u32, height: u32) -> Image {
        if width == self.width && height == self.height {
            return self.clone();
        }
        let mut out = vec![0u8; width as usize * height as usize * 4];
        for y in 0..height as usize {
            // The half-open source row span this destination row covers.
            let y0 = y as u64 * self.height as u64 / height as u64;
            let y1 = (((y as u64 + 1) * self.height as u64).div_ceil(height as u64))
                .max(y0 + 1)
                .min(self.height as u64);
            for x in 0..width as usize {
                let x0 = x as u64 * self.width as u64 / width as u64;
                let x1 = (((x as u64 + 1) * self.width as u64).div_ceil(width as u64))
                    .max(x0 + 1)
                    .min(self.width as u64);
                let mut acc = [0u64; 4];
                let mut n = 0u64;
                for sy in y0..y1 {
                    for sx in x0..x1 {
                        let p = self.texel(sx as i64, sy as i64);
                        for c in 0..4 {
                            acc[c] += p[c] as u64;
                        }
                        n += 1;
                    }
                }
                let at = (y * width as usize + x) * 4;
                for c in 0..4 {
                    out[at + c] = (acc[c] / n.max(1)) as u8;
                }
            }
        }
        Image {
            width,
            height,
            rgba: out,
        }
    }

    /// Gather a `size`x`size` block whose top-left corner is at `(ox, oy)`,
    /// clamping at the edges. That clamp is what fills a virtual texture's
    /// tile border, and it is also why a mip smaller than one tile can still
    /// fill a whole padded tile.
    fn block(&self, ox: i64, oy: i64, size: usize) -> Vec<u8> {
        let mut out = vec![0u8; size * size * 4];
        for y in 0..size {
            for x in 0..size {
                let p = self.texel(ox + x as i64, oy + y as i64);
                out[(y * size + x) * 4..][..4].copy_from_slice(&p);
            }
        }
        out
    }

    /// Decode a PNG into RGBA8.
    pub fn from_png(bytes: &[u8]) -> Result<Image, String> {
        let mut decoder = png::Decoder::new(bytes);
        // Expand palettes and low bit depths, drop 16-bit down to 8, and give
        // everything an alpha channel, so only two colour types can arrive.
        decoder.set_transformations(
            png::Transformations::normalize_to_color8() | png::Transformations::ALPHA,
        );
        let mut reader = decoder.read_info().map_err(|e| format!("not a PNG: {e}"))?;
        let mut buf = vec![0u8; reader.output_buffer_size()];
        let info = reader
            .next_frame(&mut buf)
            .map_err(|e| format!("PNG decode failed: {e}"))?;
        buf.truncate(info.buffer_size());

        let rgba = match info.color_type {
            png::ColorType::Rgba => buf,
            png::ColorType::GrayscaleAlpha => buf
                .chunks_exact(2)
                .flat_map(|p| [p[0], p[0], p[0], p[1]])
                .collect(),
            other => return Err(format!("unsupported PNG colour type {other:?}")),
        };
        Image::new(info.width, info.height, rgba)
    }
}

/// What a rewrite produced.
pub struct Rewrite {
    /// The new bulk payload, byte-for-byte the same length as the shipped one.
    /// Empty when the texture keeps every mip inline.
    pub ubulk: Vec<u8>,
    /// A new export blob, present only when inline mips had to change. Virtual
    /// textures never need this.
    pub export: Option<Vec<u8>>,
    /// How many mips were rewritten.
    pub mips: u32,
}

/// Replace a texture's pixels with `img`, resampled to fit.
///
/// `export_body` is the export blob `parse_texture` was given — everything
/// after the zen package header. `ubulk` is the shipped bulk payload.
pub fn rewrite(
    tex: &Texture,
    export_body: &[u8],
    ubulk: &[u8],
    img: &Image,
) -> Result<Rewrite, String> {
    if img.width == 0 || img.height == 0 {
        return Err("the replacement image is empty".into());
    }
    encodable(&tex.format)?;
    match &tex.payload {
        Payload::Virtual(vt) => Ok(Rewrite {
            ubulk: rewrite_vt(vt, ubulk, img)?,
            export: None,
            mips: vt.num_mips,
        }),
        Payload::Classic(mips) => rewrite_classic(tex, mips, export_body, ubulk, img),
    }
}

/// Refuse a format this module cannot write, before anything is rewritten.
///
/// Refusing beats approximating: a texture written in a format we encode
/// wrongly is a corrupt asset in the player's install, and the failure would
/// show up as garbage pixels rather than an error.
fn encodable(format: &str) -> Result<(), String> {
    match format {
        "PF_DXT1" | "PF_DXT3" | "PF_DXT5" | "PF_BC4" | "PF_BC5" | "PF_B8G8R8A8" | "PF_G8"
        | "PF_A8" => Ok(()),
        "PF_BC7" | "PF_BC6H" => Err(format!(
            "{format} cannot be written yet — it needs a BPTC encoder. Textures in \
             DXT1, DXT5, BC4, BC5 and the uncompressed formats can be swapped."
        )),
        other => Err(format!("{other} cannot be written yet")),
    }
}

/// Rewrite every tile of every mip of a virtual texture, in place.
fn rewrite_vt(vt: &VtData, ubulk: &[u8], img: &Image) -> Result<Vec<u8>, String> {
    if ubulk.is_empty() {
        return Err("virtual texture has no bulk payload to rewrite".into());
    }
    let ts = vt.tile_size as usize;
    let border = vt.tile_border as usize;
    let padded = ts + 2 * border;
    let tile_bytes = vt.tile_bytes as usize;

    // The tile size the format implies must be the tile size the header
    // declares. If they disagree the metadata is not what we think it is, and
    // writing would scribble over neighbouring tiles.
    let implied = surface_bytes(&vt.format, padded as u32, padded as u32)
        .ok_or_else(|| format!("{} has no known block size", vt.format))?;
    if implied != tile_bytes as u64 {
        return Err(format!(
            "{} tiles of {padded}x{padded} are {implied} bytes, but the header says {tile_bytes}",
            vt.format
        ));
    }

    let mut out = ubulk.to_vec();
    let mut level = img.resized(vt.width, vt.height);
    for mip in 0..vt.num_mips as usize {
        if mip > 0 {
            let w = (vt.width >> mip).max(1);
            let h = (vt.height >> mip).max(1);
            level = level.resized(w, h);
        }
        let table = &vt.tables[mip];
        let chunk = *vt
            .chunk_index_per_mip
            .get(mip)
            .ok_or("mip has no chunk index")? as usize;
        let chunk_start: u64 = vt
            .chunk_sizes
            .get(..chunk)
            .ok_or("chunk index out of range")?
            .iter()
            .map(|s| *s as u64)
            .sum();
        let mip_base = chunk_start as usize + vt.mip_offset_in_chunk[mip] as usize;

        for ty in 0..table.height {
            for tx in 0..table.width {
                let Some(off) = table.offset_of(morton(tx, ty)) else {
                    continue;
                };
                let start = mip_base + off as usize * tile_bytes;
                let end = start + tile_bytes;
                if end > out.len() {
                    return Err(format!(
                        "mip {mip} tile ({tx},{ty}) would land beyond the {} byte payload",
                        out.len()
                    ));
                }
                // The tile carries `border` pixels of its neighbours on every
                // side; clamped sampling reproduces that.
                let block = level.block(
                    tx as i64 * ts as i64 - border as i64,
                    ty as i64 * ts as i64 - border as i64,
                    padded,
                );
                let bytes = encode_surface(&vt.format, &block, padded, padded)?;
                out[start..end].copy_from_slice(&bytes);
            }
        }
    }
    Ok(out)
}

/// Rewrite a classic mip chain, in the bulk payload and inline in the export.
fn rewrite_classic(
    tex: &Texture,
    mips: &[Mip],
    export_body: &[u8],
    ubulk: &[u8],
    img: &Image,
) -> Result<Rewrite, String> {
    let mut bulk = ubulk.to_vec();
    let mut body = export_body.to_vec();
    let mut touched_export = false;

    for (i, m) in mips.iter().enumerate() {
        let one = surface_bytes(&tex.format, m.width, m.height)
            .ok_or_else(|| format!("{} has no known block size", tex.format))?;
        let level = img.resized(m.width, m.height);
        let bytes = encode_surface(
            &tex.format,
            &level.rgba,
            m.width as usize,
            m.height as usize,
        )?;

        match &m.source {
            MipSource::Bulk { offset, len } => {
                // A cubemap, array or volume mip holds several slices. One 2D
                // image does not say what the other faces should become, so
                // rewriting it would silently discard them.
                if *len != one {
                    return Err(format!(
                        "mip {i} holds {} slices; cubemaps, arrays and volume textures \
                         cannot be replaced from a single image",
                        len / one.max(1)
                    ));
                }
                let (start, end) = (*offset as usize, (*offset + *len) as usize);
                if end > bulk.len() {
                    return Err(format!("mip {i} is beyond the bulk payload"));
                }
                bulk[start..end].copy_from_slice(&bytes);
            }
            MipSource::Inline { at, bytes: old } => {
                if old.len() as u64 != one {
                    return Err(format!(
                        "mip {i} holds {} slices; cubemaps, arrays and volume textures \
                         cannot be replaced from a single image",
                        old.len() as u64 / one.max(1)
                    ));
                }
                body[*at..*at + old.len()].copy_from_slice(&bytes);
                touched_export = true;
            }
        }
    }

    Ok(Rewrite {
        ubulk: bulk,
        export: touched_export.then_some(body),
        mips: mips.len() as u32,
    })
}

/// Encode a `width`x`height` RGBA surface into `format`.
///
/// The output is exactly `surface_bytes(format, width, height)` long.
fn encode_surface(
    format: &str,
    rgba: &[u8],
    width: usize,
    height: usize,
) -> Result<Vec<u8>, String> {
    let need = surface_bytes(format, width as u32, height as u32)
        .ok_or_else(|| format!("{format} has no known block size"))? as usize;
    if rgba.len() != width * height * 4 {
        return Err(format!(
            "{width}x{height} RGBA needs {} bytes, got {}",
            width * height * 4,
            rgba.len()
        ));
    }
    let mut out = vec![0u8; need];

    match format {
        "PF_DXT1" | "PF_DXT3" | "PF_DXT5" => {
            let f = match format {
                "PF_DXT1" => texpresso::Format::Bc1,
                "PF_DXT3" => texpresso::Format::Bc2,
                _ => texpresso::Format::Bc3,
            };
            f.compress(rgba, width, height, texpresso::Params::default(), &mut out);
        }
        "PF_BC4" => encode_bc4(rgba, width, height, 0, &mut out),
        "PF_BC5" => {
            // Two BC4 blocks per 4x4: red then green. They interleave block by
            // block, so each is written into its own half of every 16 bytes.
            let mut red = vec![0u8; need / 2];
            let mut green = vec![0u8; need / 2];
            encode_bc4(rgba, width, height, 0, &mut red);
            encode_bc4(rgba, width, height, 1, &mut green);
            for (i, pair) in out.chunks_exact_mut(16).enumerate() {
                pair[..8].copy_from_slice(&red[i * 8..i * 8 + 8]);
                pair[8..].copy_from_slice(&green[i * 8..i * 8 + 8]);
            }
        }
        "PF_B8G8R8A8" => {
            for (i, p) in rgba.chunks_exact(4).enumerate() {
                out[i * 4..i * 4 + 4].copy_from_slice(&[p[2], p[1], p[0], p[3]]);
            }
        }
        "PF_G8" => {
            for (i, p) in rgba.chunks_exact(4).enumerate() {
                // Rec. 601 luma, the conventional colour-to-grey weighting.
                out[i] = ((p[0] as u32 * 299 + p[1] as u32 * 587 + p[2] as u32 * 114) / 1000) as u8;
            }
        }
        "PF_A8" => {
            for (i, p) in rgba.chunks_exact(4).enumerate() {
                out[i] = p[3];
            }
        }
        other => return Err(format!("{other} cannot be written yet")),
    }
    Ok(out)
}

/// Encode one channel of an RGBA surface as BC4 blocks.
///
/// `channel` indexes into the RGBA quad, so BC5 reuses this for red and green.
fn encode_bc4(rgba: &[u8], width: usize, height: usize, channel: usize, out: &mut [u8]) {
    let bw = width.div_ceil(4);
    let bh = height.div_ceil(4);
    for by in 0..bh {
        for bx in 0..bw {
            let mut vals = [0u8; 16];
            for y in 0..4 {
                for x in 0..4 {
                    // Blocks past the edge repeat the last row or column, which
                    // is what keeps a partial block from encoding black.
                    let sx = (bx * 4 + x).min(width - 1);
                    let sy = (by * 4 + y).min(height - 1);
                    vals[y * 4 + x] = rgba[(sy * width + sx) * 4 + channel];
                }
            }
            let block = encode_bc4_block(&vals);
            let at = (by * bw + bx) * 8;
            out[at..at + 8].copy_from_slice(&block);
        }
    }
}

/// One 4x4 BC4 block: two endpoints then sixteen 3-bit indices.
///
/// Always uses the eight-value mode (`e0 > e1`), whose palette is the two
/// endpoints plus six evenly spaced steps. The six-value mode only pays off
/// for blocks that need a hard 0 or 255, and picking the wider palette costs
/// at most one step of precision.
fn encode_bc4_block(vals: &[u8; 16]) -> [u8; 8] {
    let lo = *vals.iter().min().unwrap();
    let hi = *vals.iter().max().unwrap();
    let mut out = [0u8; 8];
    out[0] = hi;
    out[1] = lo;
    if hi == lo {
        // A flat block: endpoint 0 everywhere, which is what all-zero indices
        // already say.
        return out;
    }

    // Palette for e0 > e1: index 0 is e0, index 1 is e1, then six steps down.
    let palette: [u8; 8] = std::array::from_fn(|i| match i {
        0 => hi,
        1 => lo,
        _ => (((8 - i as u32) * hi as u32 + (i as u32 - 1) * lo as u32) / 7) as u8,
    });

    let mut bits: u64 = 0;
    for (i, &v) in vals.iter().enumerate() {
        let best = (0..8)
            .min_by_key(|&p| (palette[p] as i32 - v as i32).abs())
            .unwrap() as u64;
        bits |= best << (3 * i);
    }
    out[2..].copy_from_slice(&bits.to_le_bytes()[..6]);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Round-tripping through the decoder is the real test: a block that
    /// encodes to something the game's own format rules cannot read would
    /// still "succeed" if we only checked lengths.
    fn roundtrip(format: &str, rgba: &[u8], w: usize, h: usize) -> Vec<u8> {
        let enc = encode_surface(format, rgba, w, h).unwrap();
        assert_eq!(enc.len(), surface_bytes(format, w as u32, h as u32).unwrap() as usize);
        let px = crate::decode_surface(format, &enc, w, h).unwrap();
        let mut out = vec![0u8; w * h * 4];
        for (i, p) in px.iter().enumerate() {
            crate::put_rgba(&mut out, i * 4, *p);
        }
        out
    }

    fn gradient(w: usize, h: usize) -> Vec<u8> {
        let mut v = vec![0u8; w * h * 4];
        for y in 0..h {
            for x in 0..w {
                let at = (y * w + x) * 4;
                v[at] = (x * 255 / w.max(1)) as u8;
                v[at + 1] = (y * 255 / h.max(1)) as u8;
                v[at + 2] = 128;
                v[at + 3] = 255;
            }
        }
        v
    }

    #[test]
    fn dxt1_survives_a_round_trip() {
        let src = gradient(64, 64);
        let back = roundtrip("PF_DXT1", &src, 64, 64);
        // DXT1 is lossy, so this checks the image is recognisably the same
        // rather than identical.
        let err: u32 = src
            .chunks(4)
            .zip(back.chunks(4))
            .map(|(a, b)| {
                (0..3)
                    .map(|c| (a[c] as i32 - b[c] as i32).unsigned_abs())
                    .sum::<u32>()
            })
            .sum();
        assert!(err / (64 * 64 * 3) < 8, "mean channel error too high");
    }

    #[test]
    fn flat_colours_encode_exactly() {
        // A single colour has no quantisation error to hide behind, so any
        // endpoint or index mistake shows up immediately.
        for format in ["PF_DXT1", "PF_DXT5", "PF_B8G8R8A8"] {
            let src: Vec<u8> = [40u8, 200, 80, 255].repeat(16 * 16);
            let back = roundtrip(format, &src, 16, 16);
            for (a, b) in src.chunks(4).zip(back.chunks(4)) {
                for c in 0..3 {
                    assert!(
                        (a[c] as i32 - b[c] as i32).abs() <= 4,
                        "{format} channel {c}: {} vs {}",
                        a[c],
                        b[c]
                    );
                }
            }
        }
    }

    #[test]
    fn bc4_endpoints_bracket_the_block() {
        let mut vals = [0u8; 16];
        for (i, v) in vals.iter_mut().enumerate() {
            *v = (i * 17) as u8;
        }
        let block = encode_bc4_block(&vals);
        assert_eq!(block[0], 255, "e0 is the maximum");
        assert_eq!(block[1], 0, "e1 is the minimum");
        // A flat block collapses to one endpoint and all-zero indices.
        let flat = encode_bc4_block(&[77u8; 16]);
        assert_eq!(flat, [77, 77, 0, 0, 0, 0, 0, 0]);
    }

    #[test]
    fn bc5_round_trips_two_channels() {
        let src = gradient(32, 32);
        let back = roundtrip("PF_BC5", &src, 32, 32);
        for (a, b) in src.chunks(4).zip(back.chunks(4)) {
            for c in 0..2 {
                assert!(
                    (a[c] as i32 - b[c] as i32).abs() <= 10,
                    "channel {c}: {} vs {}",
                    a[c],
                    b[c]
                );
            }
        }
    }

    #[test]
    fn uncompressed_formats_round_trip_exactly() {
        let src = gradient(8, 8);
        let back = roundtrip("PF_B8G8R8A8", &src, 8, 8);
        assert_eq!(src, back);
    }

    #[test]
    fn resize_preserves_a_flat_colour() {
        // Averaging must not drift the value, in either direction.
        let src = Image::new(64, 16, [10u8, 20, 30, 255].repeat(64 * 16)).unwrap();
        for (w, h) in [(16u32, 4u32), (128, 32), (7, 3)] {
            let out = src.resized(w, h);
            assert_eq!(out.rgba.len(), w as usize * h as usize * 4);
            assert!(
                out.rgba.chunks(4).all(|p| p == [10, 20, 30, 255]),
                "{w}x{h} drifted"
            );
        }
    }

    #[test]
    fn resize_to_the_same_size_is_a_copy() {
        let src = Image::new(4, 4, gradient(4, 4)).unwrap();
        assert_eq!(src.resized(4, 4).rgba, src.rgba);
    }

    /// A mip of one pixel is the end of every chain, and the block-gather has
    /// to keep working there.
    #[test]
    fn one_pixel_mips_still_encode() {
        let src = Image::new(1, 1, vec![9, 8, 7, 255]).unwrap();
        let block = src.block(-4, -4, 8);
        assert_eq!(block.len(), 8 * 8 * 4);
        assert!(block.chunks(4).all(|p| p == [9, 8, 7, 255]));
        assert_eq!(encode_surface("PF_DXT1", &block, 8, 8).unwrap().len(), 32);
    }

    #[test]
    fn unsupported_formats_are_refused_not_approximated() {
        assert!(encodable("PF_BC7").is_err());
        assert!(encodable("PF_BC6H").is_err());
        assert!(encodable("PF_Nonesuch").is_err());
        assert!(encodable("PF_DXT1").is_ok());
    }
}
