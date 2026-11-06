//! Give a cooked SkeletalMesh's every LOD a second, constant UV channel.
//!
//! The editor's glTF import of a skinned mesh keeps one UV channel. A vehicle's
//! object lighting needs a second, which is one texel of the lighting page for
//! the whole mesh, so it is added here: the vertex buffer's channel count goes to
//! two, the channels interleave per vertex, and the LOD's block size grows.
//!
//! skin_uv <in .uasset> <u> <v> <out .uasset>
//!
//! Works on LODs inlined in the export. Stops if a LOD has other than one channel.
use std::error::Error;
use ue_asset::package::ZenPackage;

fn word(d: &[u8], at: usize) -> Option<u32> {
    Some(u32::from_le_bytes(d.get(at..at + 4)?.try_into().ok()?))
}

/// A float as IEEE half. Normal values only: a UV in 0..1 with a few bits.
fn half(f: f32) -> u16 {
    let b = f.to_bits();
    if f == 0.0 {
        return 0;
    }
    let exponent = ((b >> 23) & 0xff) as i32 - 127 + 15;
    assert!((1..31).contains(&exponent), "{f} is out of half range");
    (((b >> 16) & 0x8000) | ((exponent as u32) << 10) | ((b >> 13) & 0x3ff)) as u16
}

/// One LOD's vertex buffers, by where their fields sit in the export.
struct Lod {
    size_word: usize,
    texcoords: usize,
    uv_header: usize,
    uv_data: usize,
    vertices: usize,
    full_precision: bool,
}

/// Finds every position buffer: stride 12, count, element 12, count, then the
/// vertex data, a strip word and the static buffer's own vertex count.
fn find_lods(d: &[u8]) -> Result<Vec<Lod>, Box<dyn Error>> {
    let mut out = Vec::new();
    let mut at = 0;
    while at + 16 <= d.len() {
        let hit = word(d, at) == Some(12)
            && word(d, at + 8) == Some(12)
            && word(d, at + 4) == word(d, at + 12);
        let n = word(d, at + 4).unwrap_or(0) as usize;
        if !hit || n == 0 || at + 16 + n * 12 + 18 > d.len() {
            at += 1;
            continue;
        }
        let after = at + 16 + n * 12 + 2;
        if word(d, after + 4) != Some(n as u32) {
            at += 1;
            continue;
        }
        let texcoords = after;
        let full_precision = word(d, after + 8) != Some(0);
        let tangent = if word(d, after + 12) != Some(0) {
            16
        } else {
            8
        };
        let (element, count) = (
            word(d, after + 16).ok_or("cut short")?,
            word(d, after + 20).ok_or("cut short")?,
        );
        if element as usize * count as usize != tangent * n {
            return Err(format!("{n} vertices but {element} x {count} tangents").into());
        }
        let uv_header = after + 24 + tangent * n;
        // Back over the index buffer to the block's size word: a strip word, an
        // index width byte, element size, count, then the indices.
        let mut size_word = None;
        for width in [2usize, 4] {
            for bytes in 0..at.saturating_sub(9) {
                let start = at - bytes;
                if d[start - 9] as usize == width
                    && word(d, start - 8) == Some(width as u32)
                    && word(d, start - 4).map(|c| c as usize * width) == Some(bytes)
                {
                    size_word = Some(start - 9 - 2 - 4);
                    break;
                }
            }
            if size_word.is_some() {
                break;
            }
        }
        let size_word = size_word.ok_or("no index buffer before the positions")?;
        out.push(Lod {
            size_word,
            texcoords,
            uv_header,
            uv_data: uv_header + 8,
            vertices: n,
            full_precision,
        });
        at = uv_header;
    }
    Ok(out)
}

fn main() -> Result<(), Box<dyn Error>> {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let [input, u, v, out] = a.as_slice() else {
        return Err("skin_uv <in .uasset> <u> <v> <out .uasset>".into());
    };
    let (u, v): (f32, f32) = (u.parse()?, v.parse()?);
    let data = std::fs::read(input)?;
    let mut pkg = ZenPackage::parse(&data)?;
    let index = (0..pkg.export_map.len())
        .max_by_key(|i| pkg.export_bytes(*i).map_or(0, <[u8]>::len))
        .ok_or("no exports")?;
    let export = pkg.export_bytes(index).ok_or("no export bytes")?.to_vec();
    let lods = find_lods(&export)?;
    if lods.is_empty() {
        return Err("no inlined LOD".into());
    }

    let mut bytes = export.clone();
    // Last LOD first, so earlier offsets stay good.
    for lod in lods.iter().rev() {
        if word(&bytes, lod.texcoords) != Some(1) {
            return Err(format!("a LOD with {:?} UV channels", word(&bytes, lod.texcoords)).into());
        }
        let size = if lod.full_precision { 8 } else { 4 };
        if word(&bytes, lod.uv_header).map(|e| e as usize) != Some(size)
            || word(&bytes, lod.uv_header + 4).map(|c| c as usize) != Some(lod.vertices)
        {
            return Err("unexpected texcoord bulk header".into());
        }
        let second: Vec<u8> = if lod.full_precision {
            [u.to_le_bytes(), v.to_le_bytes()].concat()
        } else {
            [half(u).to_le_bytes(), half(v).to_le_bytes()].concat()
        };
        let mut uvs = Vec::with_capacity(lod.vertices * size * 2);
        for k in 0..lod.vertices {
            uvs.extend_from_slice(&bytes[lod.uv_data + k * size..lod.uv_data + (k + 1) * size]);
            uvs.extend_from_slice(&second);
        }
        bytes.splice(lod.uv_data..lod.uv_data + lod.vertices * size, uvs);
        bytes[lod.texcoords..lod.texcoords + 4].copy_from_slice(&2u32.to_le_bytes());
        bytes[lod.uv_header + 4..lod.uv_header + 8]
            .copy_from_slice(&(2 * lod.vertices as u32).to_le_bytes());
        let block =
            word(&bytes, lod.size_word).ok_or("no size word")? + (lod.vertices * size) as u32;
        bytes[lod.size_word..lod.size_word + 4].copy_from_slice(&block.to_le_bytes());
    }

    // A bulk entry placed after the insert moves with the bytes it follows.
    let grown = (bytes.len() - export.len()) as u64;
    let end = pkg.export_map[index].cooked_serial_offset + export.len() as u64;
    let first_uv = pkg.export_map[index].cooked_serial_offset + lods[0].uv_data as u64;
    for b in &mut pkg.bulk {
        if (b.serial_offset as u64) >= first_uv && (b.serial_offset as u64) <= end {
            b.serial_offset += grown as i64;
        }
    }
    pkg.set_export_bytes(index, bytes)?;
    let written = pkg.write();
    let back = ZenPackage::parse(&written)?;
    let lods = find_lods(back.export_bytes(index).ok_or("no export on read back")?)?;
    if !lods
        .iter()
        .all(|l| word(back.export_bytes(index).unwrap(), l.texcoords) == Some(2))
    {
        return Err("the second channel did not read back".into());
    }
    std::fs::write(out, written)?;
    println!(
        "{}: {} LOD(s), second UV channel {u} {v}",
        pkg.name(),
        lods.len()
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A LOD block as a cook lays it out: `n` vertices, one UV channel.
    fn block(n: u32) -> Vec<u8> {
        let mut d = vec![0xaa; 3];
        d.extend_from_slice(&999u32.to_le_bytes()); // block size
        d.extend_from_slice(&[0, 0, 2]); // strip word, index width
        d.extend_from_slice(&2u32.to_le_bytes());
        d.extend_from_slice(&3u32.to_le_bytes());
        d.extend_from_slice(&[1, 0, 2, 0, 3, 0]);
        for v in [12, n, 12, n] {
            d.extend_from_slice(&v.to_le_bytes());
        }
        d.extend(vec![0; 12 * n as usize]);
        d.extend_from_slice(&[0, 0]);
        for v in [1, n, 0, 0, 8, n] {
            d.extend_from_slice(&v.to_le_bytes());
        }
        d.extend(vec![0; 8 * n as usize]);
        for v in [4, n] {
            d.extend_from_slice(&v.to_le_bytes());
        }
        d.extend(vec![7; 4 * n as usize]);
        d
    }

    #[test]
    fn finds_a_lod_and_its_size_word() {
        let d = block(2);
        let lods = find_lods(&d).unwrap();
        assert_eq!(lods.len(), 1);
        assert_eq!(lods[0].vertices, 2);
        assert_eq!(word(&d, lods[0].size_word), Some(999));
        assert_eq!(word(&d, lods[0].texcoords), Some(1));
        assert_eq!(word(&d, lods[0].uv_header), Some(4));
        assert_eq!(d[lods[0].uv_data], 7);
    }

    #[test]
    fn half_values() {
        assert_eq!(half(0.5), 0x3800);
        assert_eq!(half(0.00390625), 0x1c00);
        assert_eq!(half(0.0), 0);
    }
}
