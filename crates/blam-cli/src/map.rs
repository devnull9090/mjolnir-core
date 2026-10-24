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
    /// Package the CE runtime pack (tools/level/build_ce_runtime.sh's output)
    /// as the `.mjolnir` content mod every map pack depends on.
    Runtime(RuntimeArgs),
}

#[derive(Args)]
pub struct RuntimeArgs {
    /// The folder of runtime containers (`.utoc`/`.ucas` pairs).
    pub dir: PathBuf,
    /// The release version (semver).
    #[arg(long)]
    pub version: String,
    /// The archive to write; `mjolnir-ce-runtime-<version>.mjolnir` in the
    /// current folder by default.
    #[arg(long)]
    pub out: Option<PathBuf>,
    #[command(flatten)]
    pub signing: Signing,
}

/// How an archive is signed. The hub refuses unsigned uploads.
#[derive(Args)]
pub struct Signing {
    /// Sign the archive with this machine's device key, the one the tag
    /// editor created and registered on the hub.
    #[arg(long, conflicts_with = "sign_seed")]
    pub sign: bool,
    /// Sign with the key in this seed file (32 raw bytes or 64 hex
    /// characters) instead. Register its public key on the hub first.
    #[arg(long, value_name = "FILE")]
    pub sign_seed: Option<PathBuf>,
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
    /// The hub slug; `ce-<title>` by default (`ce-blood-gulch`), `h2-<title>`
    /// for a Halo 2 map.
    #[arg(long)]
    pub slug: Option<String>,
    /// The game the map comes from, `halo1` or `halo2`, for the hub's game
    /// filter; the staging manifest's `game` by default (a Halo 2
    /// conversion's says `halo2`), else `halo1`.
    #[arg(long, value_parser = ["halo1", "halo2"])]
    pub game: Option<String>,
    /// The catalog's size: `small`, `medium` or `large`.
    #[arg(long, value_parser = ["small", "medium", "large"])]
    pub size: Option<String>,
    /// The player counts it suits, `MIN-MAX` (`2-8`).
    #[arg(long, value_name = "MIN-MAX")]
    pub players: Option<String>,
    /// Whether it has vehicles.
    #[arg(long)]
    pub vehicles: Option<bool>,
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
    #[command(flatten)]
    pub signing: Signing,
}

/// The CE runtime pack every converted map depends on.
pub const RUNTIME_SLUG: &str = "mjolnir-ce-runtime";

const RUNTIME_SUMMARY: &str = "What every classic CE map shares: the CE materials, the CTF \
    flag, health packs, spawn points, teleporters, event sounds and the multiplayer screens.";

pub fn run(a: MapArgs) -> Result<()> {
    match a.command {
        MapCommand::Pack(p) => pack(p),
        MapCommand::Runtime(r) => runtime(r),
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
    // A Halo 2 map's turning parts: a container per tag of each machine
    // (`machines/pakchunk986-MJOLNIRMACH-<CODE>-<k><g>_P`, tools/level/
    // h2_machines.py). Without them the parts turn but their collision
    // stays where it was baked.
    let machines = dir.join("machines");
    if machines.is_dir() {
        let mut more: Vec<PathBuf> = std::fs::read_dir(&machines)?
            .filter_map(|e| e.ok().map(|e| e.path()))
            .filter(|p| {
                p.file_name()
                    .and_then(|n| n.to_str())
                    .and_then(|n| n.strip_suffix(".utoc"))
                    .is_some_and(|stem| stem.contains(&format!("-MJOLNIRMACH-{code}-")) && stem.ends_with("_P"))
            })
            .collect();
        more.sort();
        for path in more {
            if !path.with_extension("ucas").is_file() {
                bail!("{} has no .ucas beside it", path.display());
            }
            found.push(path);
        }
    }
    Ok(found)
}

/// The game a conversion's staging says it comes from (`staging/manifest.json`
/// `game`: `halo2` for `mjolnir cache stage`), if it says.
fn staged_game(dir: &Path) -> Option<String> {
    let bytes = std::fs::read(dir.join("staging").join("manifest.json")).ok()?;
    let manifest: serde_json::Value = serde_json::from_slice(&bytes).ok()?;
    match manifest.get("game")?.as_str()? {
        g @ ("halo1" | "halo2") => Some(g.to_string()),
        _ => None,
    }
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

/// Now, as RFC 3339 UTC to the second (`2026-10-01T22:15:00Z`), for the
/// signed statement.
fn signed_at_now() -> String {
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);
    let (days, rem) = (secs.div_euclid(86_400), secs.rem_euclid(86_400));
    // Civil date from days since the epoch (Howard Hinnant's algorithm).
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + i64::from(month <= 2);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        rem / 3600,
        rem % 3600 / 60,
        rem % 60
    )
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
    let game = match &a.game {
        Some(g) => g.clone(),
        None => staged_game(&a.dir).unwrap_or_else(|| "halo1".into()),
    };
    let prefix = if game == "halo2" { "h2" } else { "ce" };
    let slug = a
        .slug
        .clone()
        .unwrap_or_else(|| format!("{prefix}-{}", slugify(&title)));
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
        "map": { "code": code, "title": title, "modes": modes, "game": game },
        "deps": [{ "slug": RUNTIME_SLUG, "range": a.runtime }],
    });
    let mut manifest = manifest;
    if let Some(size) = &a.size {
        manifest["map"]["size"] = serde_json::json!(size);
    }
    if let Some(players) = &a.players {
        let (min, max) = players
            .split_once('-')
            .and_then(|(lo, hi)| Some((lo.trim().parse::<u8>().ok()?, hi.trim().parse::<u8>().ok()?)))
            .filter(|(lo, hi)| (1..=16).contains(lo) && (1..=16).contains(hi) && lo <= hi)
            .with_context(|| format!("--players {players:?}: want MIN-MAX, 1 to 16"))?;
        manifest["map"]["players"] = serde_json::json!({ "min": min, "max": max });
    }
    if let Some(vehicles) = a.vehicles {
        manifest["map"]["vehicles"] = serde_json::json!(vehicles);
    }

    let mut members: Vec<(String, Vec<u8>)> =
        vec![("mjolnir.json".into(), serde_json::to_vec_pretty(&manifest)?)];
    for utoc in containers(&a.dir, &code)? {
        for path in [utoc.clone(), utoc.with_extension("ucas")] {
            let file = path.file_name().unwrap().to_string_lossy().to_string();
            members.push((format!("content/{file}"), std::fs::read(&path)?));
        }
    }
    // A remastered map's data beside its level file (the loader reads them
    // relative to it): the foliage placements the level names, and its
    // decals' textures.
    let mut extra = Vec::new();
    if let Some(file) = level.pointer("/foliage/file").and_then(|v| v.as_str()) {
        if file.contains(['/', '\\']) || file.starts_with('.') {
            bail!("foliage.file {file:?} must be a plain file name beside the level file");
        }
        extra.push((file.to_string(), a.dir.join(file)));
    }
    let decals = a.dir.join("decals");
    if decals.is_dir() {
        let mut files: Vec<PathBuf> = std::fs::read_dir(&decals)?
            .filter_map(|e| e.ok().map(|e| e.path()))
            .filter(|p| p.is_file())
            .collect();
        files.sort();
        for p in files {
            let name = p.file_name().unwrap().to_string_lossy().to_string();
            extra.push((format!("decals/{name}"), p));
        }
    }
    members.push(("map/level.json".into(), level_bytes));
    members.push((
        "map/registration.json".into(),
        serde_json::to_vec_pretty(&reg)?,
    ));
    for (rel, path) in extra {
        let bytes =
            std::fs::read(&path).with_context(|| format!("reading {}", path.display()))?;
        members.push((format!("map/{rel}"), bytes));
    }
    if let Some(readme) = &a.readme {
        members.push(("docs/README.md".into(), std::fs::read(readme)?));
    }

    let out = a
        .out
        .clone()
        .unwrap_or_else(|| PathBuf::from(format!("{slug}-{}.mjolnir", a.version)));
    write_archive(members, &slug, &a.version, &a.signing, &out)?;
    println!(
        "  {slug} {}: map {code} \"{title}\", modes {modes}",
        a.version
    );
    Ok(())
}

/// The CE runtime pack: every container in the folder, as a content mod.
fn runtime(a: RuntimeArgs) -> Result<()> {
    let manifest = serde_json::json!({
        "schema_version": 1,
        "name": "MJOLNIR CE runtime",
        "version": a.version,
        "type": "content",
        "summary": RUNTIME_SUMMARY,
    });
    let mut members: Vec<(String, Vec<u8>)> =
        vec![("mjolnir.json".into(), serde_json::to_vec_pretty(&manifest)?)];
    let mut utocs: Vec<PathBuf> = std::fs::read_dir(&a.dir)
        .with_context(|| format!("reading {}", a.dir.display()))?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|x| x == "utoc"))
        .collect();
    utocs.sort();
    if utocs.is_empty() {
        bail!(
            "no containers in {}: run tools/level/build_ce_runtime.sh first",
            a.dir.display()
        );
    }
    for utoc in utocs {
        let ucas = utoc.with_extension("ucas");
        if !ucas.is_file() {
            bail!("{} has no .ucas beside it", utoc.display());
        }
        for path in [utoc, ucas] {
            let file = path.file_name().unwrap().to_string_lossy().to_string();
            members.push((format!("content/{file}"), std::fs::read(&path)?));
        }
    }
    let out = a
        .out
        .clone()
        .unwrap_or_else(|| PathBuf::from(format!("{RUNTIME_SLUG}-{}.mjolnir", a.version)));
    write_archive(members, RUNTIME_SLUG, &a.version, &a.signing, &out)
}

/// Sign (when asked) and zip an archive's members. The signature covers
/// every other member's digest, built from the same list that is zipped, so
/// the two cannot drift.
fn write_archive(
    mut members: Vec<(String, Vec<u8>)>,
    slug: &str,
    version: &str,
    signing: &Signing,
    out: &Path,
) -> Result<()> {
    let signer = if signing.sign {
        Some(crate::signkey::device_identity()?)
    } else if let Some(seed) = &signing.sign_seed {
        Some(crate::signkey::seed_file_identity(seed)?)
    } else {
        None
    };
    if let Some(identity) = &signer {
        let refs: Vec<(String, &[u8])> = members
            .iter()
            .map(|(p, b)| (p.clone(), b.as_slice()))
            .collect();
        let envelope = identity
            .sign_members(slug, version, None, &signed_at_now(), &refs)
            .map_err(|e| anyhow::anyhow!("signing: {e}"))?;
        println!("  signed   key {}", identity.fingerprint());
        members.push((
            mjolnir_sign::SIGNATURE_MEMBER.to_string(),
            envelope.into_bytes(),
        ));
    }

    let file = std::fs::File::create(out).with_context(|| format!("creating {}", out.display()))?;
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
    let size = std::fs::metadata(out)?.len();
    println!("wrote {} ({size} bytes, {total} unpacked)", out.display());
    if signer.is_none() {
        println!("unsigned: the hub refuses unsigned uploads; pass --sign to sign with this machine's device key");
    }
    Ok(())
}
