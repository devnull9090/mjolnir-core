//! Installed maps, and what is rebuilt from all of them together.
//!
//! Every installed map needs a row in the one cooked `DT_Scenarios` table and
//! a handle on the one campaign asset ([`crate::scenario`]), and the
//! multiplayer menu needs one list of maps. Neither can ship inside a map: two
//! maps would claim the same chunks and only one would start. So both are
//! rebuilt on the player's machine, from every installed map's record, each
//! time a map is installed, removed, enabled or disabled
//! (`docs/map_distribution.md`).
//!
//! A map is installed in one of two places:
//!
//! - `<ue4ss>/MJOLNIRMaps/<CODE>/`, from a map pack: `registration.json`
//!   (a [`Registration`]) and `level.json`;
//! - the level loader's own folder, by `mjolnir level bake --install-test` on
//!   a machine that converts maps itself: `registry/<CODE>.json` and
//!   `levels/<CODE>.level.json`.
//!
//! A pack wins over a local install of the same code.

use std::path::{Path, PathBuf};

use ue_asset::zen::ScriptObjects;
use ue_asset::Usmap;
use ue_iostore::Container;

use crate::scenario::{self, Registration};

/// The folder installed map packs live in, beside the mods (not inside the
/// level loader's own folder, which the launcher digests).
pub const MAPS_DIR: &str = "MJOLNIRMaps";
/// The multiplayer menu's map list, in [`MAPS_DIR`].
pub const MENU_LIST: &str = "maps.json";

/// One installed map.
#[derive(Clone, Debug)]
pub struct Installed {
    pub registration: Registration,
    /// The level file, when it reads.
    pub level: Option<serde_json::Value>,
    /// Where it came from, for logs.
    pub source: PathBuf,
}

/// The game's folders, derived from its `Meteorite/Content/Paks`.
#[derive(Clone, Debug)]
pub struct Layout {
    pub paks: PathBuf,
    /// `<ue4ss>/MJOLNIRMaps`.
    pub maps: PathBuf,
    /// `<ue4ss>/Mods/MJOLNIRLevelLoader`, when installed.
    pub loader: Option<PathBuf>,
}

impl Layout {
    /// The layout under a game install: UE4SS in `Binaries/Win64` (Steam) or
    /// `Binaries/WinGDK` (Game Pass), whichever has a `ue4ss` folder.
    pub fn for_paks(paks: &Path) -> Layout {
        let meteorite = paks.parent().and_then(Path::parent).unwrap_or(paks);
        let ue4ss = ["Win64", "WinGDK"]
            .iter()
            .map(|p| meteorite.join("Binaries").join(p).join("ue4ss"))
            .find(|p| p.is_dir())
            .unwrap_or_else(|| meteorite.join("Binaries").join("Win64").join("ue4ss"));
        let loader = ue4ss.join("Mods").join("MJOLNIRLevelLoader");
        Layout {
            paks: paks.to_path_buf(),
            maps: ue4ss.join(MAPS_DIR),
            loader: loader.is_dir().then_some(loader),
        }
    }
}

fn read_json<T: serde::de::DeserializeOwned>(path: &Path) -> Result<T, String> {
    let bytes = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
    serde_json::from_slice(&bytes).map_err(|e| format!("{}: {e}", path.display()))
}

fn json_files(dir: &Path) -> Vec<PathBuf> {
    let mut files: Vec<PathBuf> = std::fs::read_dir(dir)
        .map(|rd| {
            rd.filter_map(|e| e.ok().map(|e| e.path()))
                .filter(|p| p.extension().is_some_and(|x| x == "json"))
                .collect()
        })
        .unwrap_or_default();
    files.sort();
    files
}

/// Every installed map, packs first, sorted by code.
pub fn installed(layout: &Layout) -> Result<Vec<Installed>, String> {
    let mut maps: Vec<Installed> = Vec::new();
    let mut dirs: Vec<PathBuf> = std::fs::read_dir(&layout.maps)
        .map(|rd| {
            rd.filter_map(|e| e.ok().map(|e| e.path()))
                .filter(|p| p.is_dir())
                .collect()
        })
        .unwrap_or_default();
    dirs.sort();
    for dir in dirs {
        let record = dir.join("registration.json");
        if !record.is_file() {
            continue;
        }
        let registration: Registration = read_json(&record)?;
        let level = read_json(&dir.join("level.json")).ok();
        maps.push(Installed {
            registration,
            level,
            source: dir,
        });
    }
    if let Some(loader) = &layout.loader {
        for record in json_files(&loader.join("registry")) {
            let registration: Registration = read_json(&record)?;
            if maps
                .iter()
                .any(|m| m.registration.code == registration.code)
            {
                continue;
            }
            let level = read_json(
                &loader
                    .join("levels")
                    .join(format!("{}.level.json", registration.code)),
            )
            .ok();
            maps.push(Installed {
                registration,
                level,
                source: record,
            });
        }
    }
    maps.sort_by(|a, b| a.registration.code.cmp(&b.registration.code));
    Ok(maps)
}

/// The menu's list: each map's code, title, description and game types (the
/// level's `modes`, else its `variant`, else Slayer).
pub fn menu_list(maps: &[Installed]) -> serde_json::Value {
    serde_json::Value::Array(
        maps.iter()
            .map(|m| {
                let level = m.level.as_ref();
                let modes = level
                    .and_then(|l| l.get("modes").cloned())
                    .or_else(|| {
                        level
                            .and_then(|l| l.get("variant"))
                            .map(|v| serde_json::json!([v]))
                    })
                    .unwrap_or_else(|| serde_json::json!(["slayer"]));
                serde_json::json!({
                    "code": m.registration.code,
                    "title": m.registration.title,
                    "description": m.registration.description,
                    "modes": modes,
                })
            })
            .collect(),
    )
}

/// The script object table every package edit resolves imports against.
pub fn script_objects(
    containers: &[Container],
    oodle: &[PathBuf],
) -> Result<ScriptObjects, String> {
    let global = containers
        .iter()
        .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
        .ok_or("no global.utoc")?;
    let chunk = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .ok_or("global.utoc has no ScriptObjects chunk")?;
    let bytes = ue_iostore::read_chunk(global, chunk, None, oodle).map_err(|e| e.to_string())?;
    ScriptObjects::parse(&bytes).map_err(|e| e.to_string())
}

fn write_list(layout: &Layout, maps: &[Installed]) -> Result<PathBuf, String> {
    std::fs::create_dir_all(&layout.maps).map_err(|e| format!("{}: {e}", layout.maps.display()))?;
    let list = layout.maps.join(MENU_LIST);
    std::fs::write(
        &list,
        serde_json::to_vec_pretty(&menu_list(maps)).expect("a json value serialises"),
    )
    .map_err(|e| format!("{}: {e}", list.display()))?;
    Ok(list)
}

/// Rewrite only the menu's map list, from every installed map: what a map
/// installed while the game runs needs, since the registration container is
/// mounted then and the game registers the map in memory instead
/// (docs/live_map_install.md). Returns how many maps it lists.
pub fn write_menu_list(layout: &Layout) -> Result<usize, String> {
    let maps = installed(layout)?;
    write_list(layout, &maps)?;
    Ok(maps.len())
}

/// What [`rebuild`] did.
#[derive(Debug, Default)]
pub struct Rebuilt {
    pub maps: Vec<String>,
    pub log: Vec<String>,
}

/// Rebuild the registration container in `Paks` and the menu's map list in
/// [`MAPS_DIR`] from every installed map. With none installed, both are
/// removed, so the game is left as shipped.
pub fn rebuild(layout: &Layout, oodle: &[PathBuf], usmap: &Usmap) -> Result<Rebuilt, String> {
    let maps = installed(layout)?;
    let mut out = Rebuilt {
        maps: maps.iter().map(|m| m.registration.code.clone()).collect(),
        log: Vec::new(),
    };
    let file = |ext: &str| layout.paks.join(format!("{}.{ext}", scenario::CONTAINER));

    let list = write_list(layout, &maps)?;
    out.log
        .push(format!("wrote {} ({} map(s))", list.display(), maps.len()));

    if maps.is_empty() {
        for ext in ["utoc", "ucas", "pak"] {
            if std::fs::remove_file(file(ext)).is_ok() {
                out.log.push(format!("removed {}", file(ext).display()));
            }
        }
        return Ok(out);
    }

    // The shipped table and campaign asset, never a registration container
    // of ours: a rebuild starts from the game as shipped.
    let containers: Vec<Container> = ue_iostore::load_all(&layout.paks)
        .map_err(|e| e.to_string())?
        .into_iter()
        .filter(|c| !c.utoc_path.to_string_lossy().contains("MJOLNIRREG"))
        .collect();
    let scripts = script_objects(&containers, oodle)?;
    let regs: Vec<Registration> = maps.iter().map(|m| m.registration.clone()).collect();
    let (built, name, log) = scenario::register(&containers, oodle, usmap, &scripts, &regs)?;
    out.log.extend(log);
    let utoc = layout.paks.join(format!("{name}.utoc"));
    let ucas = layout.paks.join(format!("{name}.ucas"));
    let pak = layout.paks.join(format!("{name}.pak"));
    for (path, bytes) in [(&utoc, &built.utoc), (&ucas, &built.ucas)] {
        std::fs::write(path, bytes).map_err(|e| format!("{}: {e}", path.display()))?;
    }
    crate::verify_written(&utoc, oodle, &built.expect)?;
    // A .utoc/.ucas pair never mounts without a .pak sibling.
    std::fs::write(&pak, ue_iostore::pak::stub_for(&name))
        .map_err(|e| format!("{}: {e}", pak.display()))?;
    out.log.push(format!(
        "wrote {} ({} map(s) registered)",
        utoc.display(),
        regs.len()
    ));
    Ok(out)
}
