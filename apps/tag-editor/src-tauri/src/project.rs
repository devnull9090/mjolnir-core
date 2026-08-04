//! Mod projects: a mod is a saved recipe of edits, not baked binaries.
//!
//! A project is a plain folder holding `mod.json` (what the mod is) and
//! `edits.json` (what it changes). Edits are keyed by group, tag path and
//! field path — never by catalog index — so a recipe survives game updates
//! and container reshuffles, and re-applies against whatever the player's
//! own installation ships. Containers are baked from the recipe only when
//! the mod is tested, exported or published.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

pub const MOD_FILE: &str = "mod.json";
pub const EDITS_FILE: &str = "edits.json";

/// What the mod is. A superset of the hub's `mjolnir.json`: the archive
/// manifest is derived from this at export time.
#[derive(Clone, Serialize, Deserialize)]
pub struct Meta {
    pub schema_version: u32,
    pub name: String,
    /// Hub slug; also names the baked containers. Lowercase letters, digits
    /// and hyphens, the same rule the hub enforces.
    pub slug: String,
    /// Semver, the same rule the hub enforces on `mjolnir.json`.
    pub version: String,
    #[serde(default)]
    pub summary: String,
}

/// One field change, keyed by identity rather than index.
#[derive(Clone, Serialize, Deserialize)]
pub struct SavedEdit {
    /// Group directory name, e.g. `weapon`.
    pub group: String,
    /// Short tag path, e.g. `objects/weapons/pistol/pistol`.
    pub tag: String,
    /// Field path, e.g. `magazines[0].rounds loaded maximum`.
    pub field: String,
    /// The text the user typed, re-parsed against the layout on each use.
    pub value: String,
}

/// A scenario whose Blam script the mod replaces.
///
/// The source itself is not in `edits.json`: a mission's script runs to
/// hundreds of kilobytes, and a mod author wants it as `.hsc` files they can
/// open in any editor and put under version control. They live under
/// `scripts/<group>/<tag>/`, and this records which tags have them.
#[derive(Clone, Serialize, Deserialize)]
pub struct SavedScript {
    pub group: String,
    pub tag: String,
}

#[derive(Serialize, Deserialize)]
struct EditsFile {
    schema_version: u32,
    edits: Vec<SavedEdit>,
    /// Absent in projects written before script editing existed, which is what
    /// the default is for.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    scripts: Vec<SavedScript>,
}

/// Where a tag's `.hsc` files live inside a project.
pub fn script_dir(root: &Path, group: &str, tag: &str) -> PathBuf {
    let mut dir = root.join("scripts").join(group);
    for part in tag.split('/') {
        dir.push(part);
    }
    dir
}

pub struct Project {
    pub root: PathBuf,
    pub meta: Meta,
}

/// The hub's slug rule: `^[a-z0-9][a-z0-9-]{1,63}$`.
pub fn validate_slug(slug: &str) -> Result<(), String> {
    let ok = (2..=64).contains(&slug.len())
        && slug.starts_with(|c: char| c.is_ascii_lowercase() || c.is_ascii_digit())
        && slug
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-');
    if ok {
        Ok(())
    } else {
        Err("a slug is 2-64 lowercase letters, digits and hyphens, e.g. faster-pistol".into())
    }
}

/// The hub's version rule: `^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$`.
pub fn validate_version(version: &str) -> Result<(), String> {
    let (core, pre) = version.split_once('-').unwrap_or((version, ""));
    let parts: Vec<&str> = core.split('.').collect();
    let core_ok = parts.len() == 3
        && parts
            .iter()
            .all(|p| !p.is_empty() && p.chars().all(|c| c.is_ascii_digit()));
    let pre_ok = version.find('-').is_none()
        || (!pre.is_empty()
            && pre
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '.' || c == '-'));
    if core_ok && pre_ok {
        Ok(())
    } else {
        Err("a version is semver, e.g. 1.2.0".into())
    }
}

fn validate(meta: &Meta) -> Result<(), String> {
    if meta.name.trim().is_empty() || meta.name.len() > 120 {
        return Err("a mod needs a name of at most 120 characters".into());
    }
    if meta.summary.len() > 300 {
        return Err("a summary is at most 300 characters".into());
    }
    validate_slug(&meta.slug)?;
    validate_version(&meta.version)
}

fn read_json<T: serde::de::DeserializeOwned>(path: &Path) -> Result<T, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    serde_json::from_str(&text).map_err(|e| format!("{}: {e}", path.display()))
}

fn write_json<T: Serialize>(path: &Path, value: &T) -> Result<(), String> {
    let json = serde_json::to_string_pretty(value).map_err(|e| e.to_string())?;
    std::fs::write(path, json + "\n").map_err(|e| format!("{}: {e}", path.display()))
}

impl Project {
    /// Start a project in `root`, creating the folder if needed. Refuses to
    /// adopt a folder that already holds a project, so an accidental double
    /// "new" cannot silently overwrite one.
    pub fn create(root: &Path, meta: Meta) -> Result<Project, String> {
        validate(&meta)?;
        if root.join(MOD_FILE).exists() {
            return Err(format!(
                "{} already holds a mod project; open it instead",
                root.display()
            ));
        }
        std::fs::create_dir_all(root).map_err(|e| format!("{}: {e}", root.display()))?;
        let project = Project {
            root: root.to_path_buf(),
            meta,
        };
        project.save_meta()?;
        project.save_edits(&[])?;
        // A README seed, so the folder explains itself and the hub page has
        // somewhere to grow from.
        let readme = root.join("README.md");
        if !readme.exists() {
            let text = format!(
                "# {}\n\n{}\n",
                project.meta.name,
                if project.meta.summary.is_empty() {
                    "Describe your mod here."
                } else {
                    project.meta.summary.as_str()
                }
            );
            let _ = std::fs::write(readme, text);
        }
        Ok(project)
    }

    pub fn open(root: &Path) -> Result<(Project, Vec<SavedEdit>), String> {
        let meta: Meta = read_json(&root.join(MOD_FILE))?;
        if meta.schema_version != 1 {
            return Err(format!(
                "this project was written by a newer editor (schema {})",
                meta.schema_version
            ));
        }
        validate(&meta)?;
        let edits: EditsFile = read_json(&root.join(EDITS_FILE))?;
        Ok((
            Project {
                root: root.to_path_buf(),
                meta,
            },
            edits.edits,
        ))
    }

    pub fn save_meta(&self) -> Result<(), String> {
        validate(&self.meta)?;
        write_json(&self.root.join(MOD_FILE), &self.meta)
    }

    pub fn save_edits(&self, edits: &[SavedEdit]) -> Result<(), String> {
        let scripts = self.load_scripts().unwrap_or_default();
        self.save_edits_and_scripts(edits, &scripts)
    }

    pub fn save_edits_and_scripts(
        &self,
        edits: &[SavedEdit],
        scripts: &[SavedScript],
    ) -> Result<(), String> {
        write_json(
            &self.root.join(EDITS_FILE),
            &EditsFile {
                schema_version: 1,
                edits: edits.to_vec(),
                scripts: scripts.to_vec(),
            },
        )
    }

    /// Which tags have a script override, from `edits.json`.
    pub fn load_scripts(&self) -> Result<Vec<SavedScript>, String> {
        let path = self.root.join(EDITS_FILE);
        if !path.exists() {
            return Ok(Vec::new());
        }
        let text = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
        let file: EditsFile = serde_json::from_str(&text).map_err(|e| e.to_string())?;
        Ok(file.scripts)
    }

    /// Read one tag's `.hsc` files back, in name order.
    ///
    /// Order matters: it is the order the compiler sees declarations in, and
    /// therefore the order they end up in the tag. Sorting by name keeps a
    /// rebuild from the same folder deterministic.
    pub fn read_script_files(&self, group: &str, tag: &str) -> Result<Vec<(String, String)>, String> {
        let dir = script_dir(&self.root, group, tag);
        let mut out = Vec::new();
        let entries = match std::fs::read_dir(&dir) {
            Ok(e) => e,
            Err(_) => return Ok(out),
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) != Some("hsc") {
                continue;
            }
            let name = path
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or_default()
                .to_string();
            let text = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
            out.push((name, text));
        }
        out.sort_by(|a, b| a.0.cmp(&b.0));
        Ok(out)
    }

    /// Write one tag's `.hsc` files, replacing whatever was there.
    pub fn write_script_files(
        &self,
        group: &str,
        tag: &str,
        files: &[(String, String)],
    ) -> Result<(), String> {
        let dir = script_dir(&self.root, group, tag);
        // Removing first means a file the user deleted in the editor does not
        // linger on disk and get compiled back in on the next build.
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        for (name, text) in files {
            // A source file's name comes from the tag, so it is not trusted to
            // be a safe path component.
            let safe: String = name
                .chars()
                .map(|c| if c.is_alphanumeric() || c == '_' || c == '-' { c } else { '_' })
                .collect();
            if safe.is_empty() {
                continue;
            }
            std::fs::write(dir.join(format!("{safe}.hsc")), text).map_err(|e| e.to_string())?;
        }
        Ok(())
    }

    pub fn remove_script_files(&self, group: &str, tag: &str) -> Result<(), String> {
        let dir = script_dir(&self.root, group, tag);
        if dir.exists() {
            std::fs::remove_dir_all(&dir).map_err(|e| e.to_string())?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn meta() -> Meta {
        Meta {
            schema_version: 1,
            name: "Faster Pistol".into(),
            slug: "faster-pistol".into(),
            version: "0.1.0".into(),
            summary: String::new(),
        }
    }

    #[test]
    fn slugs_follow_the_hub_rule() {
        assert!(validate_slug("faster-pistol").is_ok());
        assert!(validate_slug("x2").is_ok());
        assert!(validate_slug("x").is_err(), "too short");
        assert!(validate_slug("Faster").is_err(), "uppercase");
        assert!(validate_slug("-lead").is_err(), "leading hyphen");
        assert!(validate_slug("a b").is_err(), "space");
    }

    #[test]
    fn versions_follow_the_hub_rule() {
        assert!(validate_version("1.2.0").is_ok());
        assert!(validate_version("0.1.0-beta.1").is_ok());
        assert!(validate_version("1.2").is_err());
        assert!(validate_version("1.2.x").is_err());
        assert!(validate_version("1.2.3-").is_err());
    }

    #[test]
    fn a_project_round_trips_through_its_folder() {
        let dir = std::env::temp_dir().join(format!("mjolnir-project-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);

        let project = Project::create(&dir, meta()).unwrap();
        let saved = vec![SavedEdit {
            group: "weapon".into(),
            tag: "objects/weapons/pistol/pistol".into(),
            field: "magazines[0].rounds loaded maximum".into(),
            value: "24".into(),
        }];
        project.save_edits(&saved).unwrap();

        let (again, edits) = Project::open(&dir).unwrap();
        assert_eq!(again.meta.slug, "faster-pistol");
        assert_eq!(edits.len(), 1);
        assert_eq!(edits[0].field, "magazines[0].rounds loaded maximum");

        // A second create on the same folder must refuse, not overwrite.
        assert!(Project::create(&dir, meta()).is_err());
        let _ = std::fs::remove_dir_all(&dir);
    }
}
