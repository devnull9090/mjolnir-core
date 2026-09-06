//! `mjolnir texture` — inspect, export and swap cooked textures.
//!
//! A swap re-encodes the replacement image at the shipped texture's own
//! dimensions and pixel format, which lands on a payload of exactly the
//! shipped byte size. Nothing in the metadata has to move, so the override
//! container carries one chunk: the `.ubulk`. See `docs/texture_swapping.md`.

use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::{Args, Subcommand};
use ue_iostore::{ChunkEntry, Container};
use ue_texture::encode::Image;

use crate::Source;

#[derive(Args)]
pub struct TextureArgs {
    #[command(subcommand)]
    pub command: TextureCommand,
}

#[derive(Subcommand)]
pub enum TextureCommand {
    /// List cooked textures, with their format and dimensions.
    List(ListArgs),
    /// Print one texture's cooked layout in full.
    Info(OneArgs),
    /// Write one texture's top mip out as a PNG.
    Export(ExportArgs),
    /// Build an override container that replaces a texture's pixels.
    Swap(SwapArgs),
}

#[derive(Args)]
pub struct ListArgs {
    #[command(flatten)]
    pub src: Source,
    /// Only list assets whose path contains this, case-insensitively.
    #[arg(long)]
    pub filter: Option<String>,
    /// Read every match's header to report its real format and size. Slower,
    /// because it decompresses each export.
    #[arg(long)]
    pub detail: bool,
}

#[derive(Args)]
pub struct OneArgs {
    #[command(flatten)]
    pub src: Source,
    /// Substring of the asset path, e.g. `assaultrifle_default_D`.
    #[arg(long)]
    pub asset: String,
}

#[derive(Args)]
pub struct ExportArgs {
    #[command(flatten)]
    pub one: OneArgs,
    /// PNG file to write.
    #[arg(long)]
    pub out: PathBuf,
    /// Which mip to export; 0 is the largest.
    #[arg(long, default_value_t = 0)]
    pub mip: u32,
}

#[derive(Args)]
pub struct SwapArgs {
    #[command(flatten)]
    pub one: OneArgs,
    /// The replacement image. Resampled to the shipped texture's dimensions,
    /// so it does not have to match them.
    #[arg(long)]
    pub image: PathBuf,
    /// Directory to write the container into — the game's `Paks` folder to
    /// install it directly.
    #[arg(long)]
    pub out_dir: PathBuf,
    /// Container base name; `.utoc` and `.ucas` are appended.
    ///
    /// The `_P` suffix makes it a patch container, which is what wins the
    /// chunk lookup, and `pakchunk999` mounts after everything shipped.
    #[arg(long, default_value = "pakchunk999-MJOLNIR-texture_P")]
    pub name: String,
    /// Also write the rewritten payload back out as a PNG — the top mip
    /// exactly as the game will decode it.
    #[arg(long)]
    pub preview: Option<PathBuf>,
}

/// One cooked texture located in the containers.
struct Located {
    container: usize,
    uasset: ChunkEntry,
    ubulk: Option<ChunkEntry>,
    path: String,
}

/// Every asset that looks like a cooked texture, as `(uasset, ubulk)` pairs.
fn all_textures(containers: &[Container]) -> Vec<Located> {
    use std::collections::BTreeMap;
    let mut by_stem: BTreeMap<String, Located> = BTreeMap::new();
    for (ci, c) in containers.iter().enumerate() {
        for (rel, chunk_index) in &c.files {
            let full = c.full_path(rel);
            let (stem, is_uasset) = match () {
                _ if full.ends_with(".uasset") => (full.trim_end_matches(".uasset"), true),
                _ if full.ends_with(".ubulk") => (full.trim_end_matches(".ubulk"), false),
                _ => continue,
            };
            let chunk = c.chunks[*chunk_index];
            let slot = by_stem.entry(stem.to_string()).or_insert_with(|| Located {
                container: ci,
                uasset: chunk,
                ubulk: None,
                path: stem.to_string(),
            });
            if is_uasset {
                slot.container = ci;
                slot.uasset = chunk;
            } else {
                slot.ubulk = Some(chunk);
            }
        }
    }
    by_stem.into_values().collect()
}

/// Resolve `--asset` to exactly one texture.
///
/// An ambiguous substring is an error rather than a silent first-match: a swap
/// writes over whichever asset it picked, and picking the wrong one is a
/// confusing failure to debug in game.
fn locate(containers: &[Container], want: &str) -> Result<Located> {
    let needle = want.to_ascii_lowercase();
    let mut hits: Vec<Located> = all_textures(containers)
        .into_iter()
        .filter(|t| t.path.to_ascii_lowercase().contains(&needle))
        .collect();
    match hits.len() {
        0 => anyhow::bail!("no asset matching {want:?}"),
        1 => Ok(hits.remove(0)),
        n => {
            let names: Vec<&str> = hits.iter().take(8).map(|h| h.path.as_str()).collect();
            anyhow::bail!(
                "{n} assets match {want:?}; narrow it down:\n  {}{}",
                names.join("\n  "),
                if n > 8 { "\n  ..." } else { "" }
            )
        }
    }
}

/// Read a located texture's export blob, bulk payload and parsed header.
fn read(
    containers: &[Container],
    t: &Located,
    oodle: &[PathBuf],
) -> Result<(Vec<u8>, usize, Vec<u8>, ue_texture::Texture)> {
    let c = &containers[t.container];
    let uasset = ue_iostore::read_chunk(c, &t.uasset, None, oodle)?;
    let header = ue_texture::zen_header_size(&uasset)
        .context("not a zen package")?;
    let tex = ue_texture::parse_texture(&uasset[header..]).map_err(|e| anyhow::anyhow!(e))?;
    let ubulk = match &t.ubulk {
        Some(chunk) => ue_iostore::read_chunk(c, chunk, None, oodle)?,
        None => Vec::new(),
    };
    Ok((uasset, header, ubulk, tex))
}

pub fn run(a: TextureArgs) -> Result<()> {
    match a.command {
        TextureCommand::List(a) => list(a),
        TextureCommand::Info(a) => info(a),
        TextureCommand::Export(a) => export(a),
        TextureCommand::Swap(a) => swap(a),
    }
}

fn list(a: ListArgs) -> Result<()> {
    let containers = ue_iostore::load_all(&a.src.paks)?;
    let oodle = a.src.oodle_roots();
    let needle = a.filter.unwrap_or_default().to_ascii_lowercase();

    let mut shown = 0;
    for t in all_textures(&containers) {
        if !t.path.to_ascii_lowercase().contains(&needle) {
            continue;
        }
        if !a.detail {
            println!(
                "{:>12}  {}",
                t.ubulk.map(|c| c.length).unwrap_or(0),
                t.path
            );
            shown += 1;
            continue;
        }
        // Anything that is not really a texture fails to parse; say so on the
        // line rather than dropping it, so a filter never looks like it missed.
        match read(&containers, &t, &oodle) {
            Ok((_, _, _, tex)) => {
                let kind = match tex.payload {
                    ue_texture::Payload::Virtual(_) => "virtual",
                    ue_texture::Payload::Classic(_) => "classic",
                };
                println!(
                    "{:>6}x{:<6} {:<16} {:<8} {:>2} mips  {}",
                    tex.width, tex.height, tex.format, kind, tex.num_mips, t.path
                );
            }
            Err(e) => println!("{:>27}  {:<8} {}  ({e})", "-", "-", t.path),
        }
        shown += 1;
    }
    println!("\n{shown} asset(s)");
    Ok(())
}

fn info(a: OneArgs) -> Result<()> {
    let containers = ue_iostore::load_all(&a.src.paks)?;
    let oodle = a.src.oodle_roots();
    let t = locate(&containers, &a.asset)?;
    let (uasset, header, ubulk, tex) = read(&containers, &t, &oodle)?;

    println!("{}", t.path);
    println!(
        "  container {}",
        containers[t.container]
            .utoc_path
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
    );
    println!("  uasset    {} bytes (zen header {header})", uasset.len());
    println!("  ubulk     {} bytes", ubulk.len());
    println!("  format    {}", tex.format);
    println!("  size      {}x{}", tex.width, tex.height);
    println!("  mips      {}", tex.num_mips);

    match &tex.payload {
        ue_texture::Payload::Virtual(vt) => {
            println!("  payload   virtual texture");
            println!(
                "    tiles   {}px + {}px border = {} bytes each",
                vt.tile_size, vt.tile_border, vt.tile_bytes
            );
            println!("    chunks  {:?}", vt.chunk_sizes);
            let total: u64 = vt.chunk_sizes.iter().map(|s| *s as u64).sum();
            println!(
                "            {total} bytes total, ubulk is {} — {}",
                ubulk.len(),
                if total == ubulk.len() as u64 {
                    "exact"
                } else {
                    "MISMATCH"
                }
            );
            for (m, table) in vt.tables.iter().enumerate() {
                let tiles: usize = (0..table.height)
                    .flat_map(|ty| (0..table.width).map(move |tx| (tx, ty)))
                    .filter(|(tx, ty)| table.has_tile(*tx, *ty))
                    .count();
                println!(
                    "    mip {m:<2} {:>5}x{:<5} grid {}x{}, {tiles} tile(s), chunk {} at +{}",
                    (vt.width >> m).max(1),
                    (vt.height >> m).max(1),
                    table.width,
                    table.height,
                    vt.chunk_index_per_mip[m],
                    vt.mip_offset_in_chunk[m]
                );
            }
        }
        ue_texture::Payload::Classic(mips) => {
            println!("  payload   classic mip chain");
            for (m, mip) in mips.iter().enumerate() {
                let where_ = match &mip.source {
                    ue_texture::MipSource::Bulk { offset, len } => {
                        format!("ubulk +{offset}, {len} bytes")
                    }
                    ue_texture::MipSource::Inline { at, bytes } => {
                        format!("inline at +{at}, {} bytes", bytes.len())
                    }
                };
                println!("    mip {m:<2} {:>5}x{:<5} {where_}", mip.width, mip.height);
            }
        }
    }
    Ok(())
}

fn export(a: ExportArgs) -> Result<()> {
    let containers = ue_iostore::load_all(&a.one.src.paks)?;
    let oodle = a.one.src.oodle_roots();
    let t = locate(&containers, &a.one.asset)?;
    let (_, _, ubulk, tex) = read(&containers, &t, &oodle)?;

    let img = ue_texture::assemble_mip(&tex, &ubulk, a.mip).map_err(|e| anyhow::anyhow!(e))?;
    let png = ue_texture::to_png(&img).map_err(|e| anyhow::anyhow!(e))?;
    std::fs::write(&a.out, &png).with_context(|| format!("cannot write {}", a.out.display()))?;
    println!(
        "{}\n  mip {} {}x{} {} -> {} ({} bytes)",
        t.path,
        img.mip,
        img.width,
        img.height,
        img.format,
        a.out.display(),
        png.len()
    );
    Ok(())
}

fn swap(a: SwapArgs) -> Result<()> {
    let containers = ue_iostore::load_all(&a.one.src.paks)?;
    let oodle = a.one.src.oodle_roots();
    let t = locate(&containers, &a.one.asset)?;
    let (_, _, ubulk, tex) = read(&containers, &t, &oodle)?;

    let png = std::fs::read(&a.image)
        .with_context(|| format!("cannot read {}", a.image.display()))?;
    let img = Image::from_png(&png).map_err(|e| anyhow::anyhow!(e))?;

    println!("{}", t.path);
    println!("  shipped  {}x{} {}", tex.width, tex.height, tex.format);
    println!(
        "  image    {}x{} {}",
        img.width,
        img.height,
        if (img.width, img.height) == (tex.width, tex.height) {
            "(exact)"
        } else {
            "(will be resampled)"
        }
    );

    // Every safety gate — the inline-mip refusal, the length invariant and the
    // readback comparison — lives in the crate, so this command and the tag
    // editor cannot drift apart on what counts as a swap worth shipping.
    let out = ue_texture::encode::swap(&tex, &ubulk, &img)
        .map_err(|e| anyhow::anyhow!("{}: {e}", t.path))?;
    println!(
        "  rewrote  {} mip(s), {} of {} payload bytes changed",
        out.mips,
        out.changed,
        ubulk.len()
    );
    println!("  readback mean channel error {:.2} / 255", out.error);

    if let Some(path) = &a.preview {
        let png = ue_texture::to_png(&out.decoded).map_err(|e| anyhow::anyhow!(e))?;
        std::fs::write(path, &png)
            .with_context(|| format!("cannot write {}", path.display()))?;
        println!("  preview  {}", path.display());
    }

    let chunk = t
        .ubulk
        .context("this texture keeps every mip inline, so it has no bulk chunk to replace")?;
    let source = &containers[t.container];
    let built = blam_pack::build_override(
        source,
        &oodle,
        &[blam_pack::ChunkEdit {
            label: format!("{}.ubulk", t.path),
            chunk,
            original_len: ubulk.len(),
            patched: out.ubulk,
        }],
    )
    .map_err(|e| anyhow::anyhow!(e))?;

    for p in &built.entries {
        println!(
            "  chunk    id {:#018x} index {} type {} (from {})",
            p.id.id,
            p.id.index,
            p.id.kind,
            source
                .utoc_path
                .file_name()
                .unwrap_or_default()
                .to_string_lossy()
        );
    }

    std::fs::create_dir_all(&a.out_dir)?;
    let utoc = a.out_dir.join(format!("{}.utoc", a.name));
    let ucas = a.out_dir.join(format!("{}.ucas", a.name));
    std::fs::write(&utoc, &built.utoc)?;
    std::fs::write(&ucas, &built.ucas)?;
    blam_pack::verify_written(&utoc, &oodle, &built.expect).map_err(|e| anyhow::anyhow!(e))?;

    // A container without a `.pak` sibling is never discovered, so an empty
    // one rides along (`ue_iostore::pak::write_stub`).
    let pak = a.out_dir.join(format!("{}.pak", a.name));
    std::fs::write(&pak, ue_iostore::pak::stub_for(&a.name))?;

    println!("\n  wrote {} ({} bytes)", utoc.display(), built.utoc.len());
    println!("  wrote {} ({} bytes)", ucas.display(), built.ucas.len());
    if pak.exists() {
        println!("  wrote {}", pak.display());
    }
    println!("\n  verified: the container reads back byte-exact through the game's own path.");
    Ok(())
}

