//! `mjolnir map` — package a converted map for the mod hub
//! (docs/map_distribution.md).
//!
//! `map pack` turns a conversion's output folder (tools/level/convert_ce_map.sh)
//! into a `.mjolnir` archive of type `map`: the map's own containers, its
//! level file and its registration record. The archive is unsigned; the tag
//! editor signs it with the author's device key as it publishes, the same
//! key every other release of theirs carries.

use std::io::Write;
use std::path::{Path, PathBuf};

use anyhow::{bail, Context, Result};
use clap::{Args, Subcommand};

#[derive(Args)]
pub struct MapArgs {
    #[command(subcommand)]
    pub command: MapCommand,
}

#[derive(Subcommand)]
pub enum MapCommand {
    /// Package a converted map as a `.mjolnir` map pack.
    Pack(PackArgs),
}

#[derive(Args)]
pub struct PackArgs {
    /// The conversion's output folder.
    pub dir: PathBuf,
    /// The map's codename (three characters), as converted.
    #[arg(long)]
    pub code: String,
    /// The release version (semver).
    #[arg(long)]
    pub version: String,
    /// The hub slug; `ce-<title>` by default (`ce-blood-gulch`).
    #[arg(long)]
    pub slug: Option<String>,
    /// The display name; the level file's title by default.
    #[arg(long)]
    pub name: Option<String>,
    /// One line for the hub card.
    #[arg(long, default_value = "")]
    pub summary: String,
    /// The CE runtime pack's version range this map needs.
    #[arg(long, default_value = "^1.0.0")]
    pub runtime: String,
    /// A README for the hub page.
    #[arg(long)]
    pub readme: Option<PathBuf>,
    /// The archive to write; `<slug>-<version>.mjolnir` in the current folder
    /// by default.
    #[arg(long)]
    pub out: Option<PathBuf>,
}

/// The CE runtime pack every converted map depends on.
pub const RUNTIME_SLUG: &str = "mjolnir-ce-runtime";

pub fn run(a: MapArgs) -> Result<()> {
    match a.command {
        MapCommand::Pack(p) => pack(p),
    }
}

/// The map's own containers in a conversion folder: its scenario, world and
/// mesh containers, each a `.utoc`/`.ucas` pair whose name ends in
/// `-<CODE>_P`, plus its cooked textures when they have a container of their
/// own. The shared ones (registration, materials cook, spawn and CTF scenery)
/// are not the map's: they come from the runtime pack or are built on the
/// player's machine.
fn containers(dir: &Path, code: &str) -> Result<Vec<PathBuf>> {
    let mut found = Vec::new();
    for e in std::fs::read_dir(dir).with_context(|| format!("reading {}", dir.display()))? {
        let path = e?.path();
        let Some(name) = path.file_name().and_then(|n| n.to_str()) else {
            continue;
        };
        let Some(stem) = name.strip_suffix(".utoc") else {
            continue;
        };
        if stem.ends_with(&format!("-{code}_P")) && !stem.contains("MJOLNIRREG") {
            if !path.with_extension("ucas").is_file() {
                bail!("{} has no .ucas beside it", path.display());
            }
            found.push(path);
        }
    }
    found.sort();
    if found.is_empty() {
        bail!(
            "no -{code}_P containers in {}: run the conversion (and its bake) first",
            dir.display()
        );
    }
    Ok(found)
}

fn level_file(dir: &Path) -> Result<PathBuf> {
    let mut found: Vec<PathBuf> = std::fs::read_dir(dir)?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.to_string_lossy().ends_with(".level.json"))
        .collect();
    found.sort();
    match found.len() {
        1 => Ok(found.remove(0)),
        0 => bail!("no .level.json in {}", dir.display()),
        _ => bail!("more than one .level.json in {}: {found:?}", dir.display()),
    }
}

/// The bake's registration record, or the same record rebuilt from the level
/// file for a bake that predates writing it: the canvas mission it clones,
/// the level's title and description, and the world renamed to the codename.
fn registration(
    dir: &Path,
    code: &str,
    level: &serde_json::Value,
) -> Result<blam_pack::scenario::Registration> {
    let record = dir.join(format!("{code}.registration.json"));
    if record.is_file() {
        return serde_json::from_slice(&std::fs::read(&record)?)
            .with_context(|| format!("reading {}", record.display()));
    }
    let from = level
        .pointer("/canvas/scenario")
        .and_then(|v| v.as_str())
        .context("the level file has no canvas.scenario")?
        .to_uppercase();
    let text = |k: &str| level.get(k).and_then(|v| v.as_str()).map(String::from);
    println!(
        "  note     no {}; rebuilt from the level file",
        record.display()
    );
    Ok(blam_pack::scenario::Registration {
        code: code.to_string(),
        from,
        title: text("title"),
        description: text("description"),
        world: Some(format!("/Game/Levels/Halo1/Solo/{code}/{code}.{code}")),
    })
}

/// A title as a hub slug: lowercase words joined by hyphens ("Blood Gulch"
/// -> "blood-gulch").
fn slugify(title: &str) -> String {
    title
        .split(|c: char| !c.is_ascii_alphanumeric())
        .filter(|w| !w.is_empty())
        .map(|w| w.to_ascii_lowercase())
        .collect::<Vec<_>>()
        .join("-")
}

fn pack(a: PackArgs) -> Result<()> {
    let code = a.code.to_uppercase();
    if code.len() != 3 {
        bail!("--code must be three characters");
    }
    let level_path = level_file(&a.dir)?;
    let level_bytes = std::fs::read(&level_path)?;
    let level: serde_json::Value = serde_json::from_slice(&level_bytes)
        .with_context(|| format!("reading {}", level_path.display()))?;
    if level.get("multiplayer") != Some(&serde_json::Value::Bool(true)) {
        bail!(
            "{} is not a multiplayer level (\"multiplayer\": true)",
            level_path.display()
        );
    }
    let reg = registration(&a.dir, &code, &level)?;
    let map_name = level
        .get("name")
        .and_then(|v| v.as_str())
        .unwrap_or(&code)
        .to_string();
    let title = reg.title.clone().unwrap_or_else(|| map_name.clone());
    let slug = a
        .slug
        .clone()
        .unwrap_or_else(|| format!("ce-{}", slugify(&title)));
    let name = a.name.clone().unwrap_or_else(|| title.clone());
    let modes = level
        .get("modes")
        .cloned()
        .unwrap_or_else(|| serde_json::json!(["slayer"]));

    let manifest = serde_json::json!({
        "schema_version": 1,
        "name": name,
        "version": a.version,
        "type": "map",
        "summary": a.summary,
        "map": { "code": code, "title": title, "modes": modes },
        "deps": [{ "slug": RUNTIME_SLUG, "range": a.runtime }],
    });

    let mut members: Vec<(String, Vec<u8>)> =
        vec![("mjolnir.json".into(), serde_json::to_vec_pretty(&manifest)?)];
    for utoc in containers(&a.dir, &code)? {
        for path in [utoc.clone(), utoc.with_extension("ucas")] {
            let file = path.file_name().unwrap().to_string_lossy().to_string();
            members.push((format!("content/{file}"), std::fs::read(&path)?));
        }
    }
    members.push(("map/level.json".into(), level_bytes));
    members.push((
        "map/registration.json".into(),
        serde_json::to_vec_pretty(&reg)?,
    ));
    if let Some(readme) = &a.readme {
        members.push(("docs/README.md".into(), std::fs::read(readme)?));
    }

    let out = a
        .out
        .clone()
        .unwrap_or_else(|| PathBuf::from(format!("{slug}-{}.mjolnir", a.version)));
    let file =
        std::fs::File::create(&out).with_context(|| format!("creating {}", out.display()))?;
    let mut zip = zip::ZipWriter::new(file);
    let options = zip::write::SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);
    let mut total = 0usize;
    for (path, bytes) in &members {
        zip.start_file(path.as_str(), options)?;
        zip.write_all(bytes)?;
        total += bytes.len();
        println!("  member   {path} ({} bytes)", bytes.len());
    }
    zip.finish()?;
    let size = std::fs::metadata(&out)?.len();
    println!(
        "wrote {} ({size} bytes, {total} unpacked): {slug} {} — map {code} \"{title}\", modes {modes}",
        out.display(),
        a.version
    );
    println!(
        "publish it from the tag editor (Publish map pack), which signs it with your device key"
    );
    Ok(())
}
