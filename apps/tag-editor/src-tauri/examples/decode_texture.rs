//! Decode one shipped texture end-to-end and write a PNG, to verify the
//! reader against a real installation.
//!
//! Usage: cargo run --example decode_texture -- <name-substring> <out.png>

use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::{install, textures};

fn main() -> Result<(), String> {
    let mut args = std::env::args().skip(1);
    let query = args.next().unwrap_or_else(|| "T_GuiltySpark_D".to_string());
    let out = args.next().unwrap_or_else(|| "texture.png".to_string());

    let found = install::detect();
    let (paks, oodle) = match (found.paks, found.oodle) {
        (Some(p), Some(o)) => (p, o),
        _ => return Err(found.note.unwrap_or_else(|| "no installation found".into())),
    };
    let catalog = Catalog::open(&paks, &oodle)?;
    eprintln!("{} textures indexed", catalog.textures.len());

    let hits = catalog.search_textures(&query, 5);
    let (index, entry) = hits.first().ok_or("no texture matched")?;
    eprintln!("decoding {}", entry.short);

    let uasset = catalog.read_texture_uasset(*index)?;
    let header = textures::zen_header_size(&uasset).ok_or("not a zen package")?;
    let tex = textures::parse_texture(&uasset[header..])?;
    eprintln!(
        "{}x{} {} · {} mips · {}",
        tex.width,
        tex.height,
        tex.format,
        tex.num_mips,
        match &tex.payload {
            textures::Payload::Virtual(vt) => format!(
                "virtual · tile {}+{} · chunks {:?}",
                vt.tile_size, vt.tile_border, vt.chunk_sizes
            ),
            textures::Payload::Classic(_) => "classic mip chain".to_string(),
        }
    );

    let ubulk = catalog.read_texture_ubulk(*index).unwrap_or_default();
    let img = textures::assemble_mip(&tex, &ubulk, 0)?;
    let png = textures::to_png(&img)?;
    std::fs::write(&out, &png).map_err(|e| e.to_string())?;
    eprintln!("wrote {} ({} bytes)", out, png.len());
    Ok(())
}
