//! Validated Forge catalog data and dependency requirements. Community packs
//! contain inert assets; this module never installs code from an archive.

use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Dependency {
    pub slug: String,
    #[serde(default = "any_version")]
    pub range: String,
}

fn any_version() -> String {
    "*".into()
}

pub fn valid_slug(value: &str) -> bool {
    (2..=64).contains(&value.len())
        && value.as_bytes()[0].is_ascii_alphanumeric()
        && value
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}

fn valid_id(value: &str) -> bool {
    (1..=64).contains(&value.len())
        && value.as_bytes()[0].is_ascii_alphanumeric()
        && value
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || matches!(b, b'-' | b'_'))
}

/// Bare complete versions are exact pins (the archive convention), whereas
/// semver's Rust default would interpret them as caret requirements.
pub fn requirement(range: &str) -> Result<semver::VersionReq, String> {
    let range = range.trim();
    if range.is_empty() || range.len() > 120 {
        return Err("Dependency range must be 1–120 characters".into());
    }
    let normalized = if semver::Version::parse(range).is_ok() {
        format!("={range}")
    } else {
        range.to_string()
    };
    semver::VersionReq::parse(&normalized)
        .map_err(|e| format!("Unsupported dependency range {range:?}: {e}"))
}

pub fn matches(range: &str, version: &str) -> Result<bool, String> {
    let req = requirement(range)?;
    let version = semver::Version::parse(version)
        .map_err(|e| format!("Invalid installed dependency version {version:?}: {e}"))?;
    Ok(req.matches(&version))
}

pub fn dependencies(manifest: &serde_json::Value, owner: &str) -> Result<Vec<Dependency>, String> {
    let deps: Vec<Dependency> = match manifest.get("deps") {
        None => Vec::new(),
        Some(value) => serde_json::from_value(value.clone())
            .map_err(|e| format!("Invalid dependencies: {e}"))?,
    };
    if deps.len() > 64 {
        return Err("An archive may have at most 64 dependencies".into());
    }
    let mut seen = BTreeSet::new();
    for dep in &deps {
        if !valid_slug(&dep.slug) || dep.slug == owner || !seen.insert(&dep.slug) {
            return Err(format!(
                "Invalid, duplicate, or self dependency: {}",
                dep.slug
            ));
        }
        requirement(&dep.range)?;
    }
    Ok(deps)
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ForgePack {
    pub schema_version: u32,
    pub id: String,
    pub blocks: Vec<Block>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Block {
    pub id: String,
    pub name: String,
    pub tag: String,
    pub category: String,
    pub dimensions_m: [f64; 3],
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub snap_m: Option<f64>,
}

impl ForgePack {
    pub fn validate(&self, slug: &str) -> Result<(), String> {
        if self.schema_version != 1 || self.id != slug || !valid_slug(slug) {
            return Err("Forge pack identity or schema version is invalid".into());
        }
        if self.blocks.is_empty() || self.blocks.len() > 256 {
            return Err("A Forge pack must contain 1–256 blocks".into());
        }
        let mut ids = BTreeSet::new();
        for block in &self.blocks {
            if !valid_id(&block.id) || !ids.insert(&block.id) || !valid_id(&block.category) {
                return Err(format!("Invalid or duplicate Forge block: {}", block.id));
            }
            if block.name.trim().is_empty() || block.name.chars().count() > 80 {
                return Err(format!("Invalid Forge block name: {}", block.id));
            }
            let tag = format!("objects\\mjolnir\\forge\\{slug}\\{}", block.id);
            if block.tag != tag {
                return Err(format!("Forge block {} must use tag {tag}", block.id));
            }
            if block
                .dimensions_m
                .iter()
                .any(|n| !n.is_finite() || *n <= 0.0)
                || block.snap_m.is_some_and(|n| !n.is_finite() || n <= 0.0)
            {
                return Err(format!("Invalid dimensions or snap size for {}", block.id));
            }
        }
        Ok(())
    }
}

pub fn read_pack(manifest: &serde_json::Value, slug: &str) -> Result<Option<ForgePack>, String> {
    let Some(value) = manifest.get("forge_pack") else {
        return Ok(None);
    };
    if manifest["type"] != "content" {
        return Err("Only content archives may carry forge_pack".into());
    }
    let pack: ForgePack =
        serde_json::from_value(value.clone()).map_err(|e| format!("Invalid Forge pack: {e}"))?;
    pack.validate(slug)?;
    Ok(Some(pack))
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LayoutPin {
    pub slug: String,
    pub version: String,
    pub sha256: String,
}

/// The native Forge sidecar is deliberately small, non-executable text.
/// Palette indices bind tags; exact versions and hashes bind their bytes.
pub fn layout_pins(text: &str) -> Result<Vec<LayoutPin>, String> {
    if text.len() > 1024 * 1024 {
        return Err("Forge layout sidecar is too large".into());
    }
    let mut lines = text.lines();
    if lines.next() != Some("forge-packs 1") {
        return Err("Unsupported Forge layout pack sidecar".into());
    }
    let mut indices = BTreeSet::new();
    let mut pins = std::collections::BTreeMap::new();
    for line in lines {
        let fields: Vec<_> = line.split('\t').collect();
        if fields.len() != 5 {
            return Err("Malformed Forge layout pack binding".into());
        }
        if fields[0].is_empty() || !fields[0].bytes().all(|b| b.is_ascii_digit()) {
            return Err("Invalid Forge palette index".into());
        }
        let index = fields[0]
            .parse::<u16>()
            .map_err(|_| "Invalid Forge palette index")?;
        if index > 254 {
            return Err("Forge palette index exceeds 254".into());
        }
        if !indices.insert(index) {
            return Err("Duplicate Forge palette index".into());
        }
        let (tag, slug, version, sha256) = (fields[1], fields[2], fields[3], fields[4]);
        let prefix = format!("objects\\mjolnir\\forge\\{slug}\\");
        if !valid_slug(slug)
            || !tag.strip_prefix(&prefix).is_some_and(valid_id)
            || version.len() > 96
            || semver::Version::parse(version).is_err()
            || sha256.len() != 64
            || !sha256
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            return Err("Invalid Forge layout pack identity or fingerprint".into());
        }
        let pin = LayoutPin {
            slug: slug.into(),
            version: version.into(),
            sha256: sha256.into(),
        };
        if pins.get(slug).is_some_and(|old| old != &pin) {
            return Err(format!(
                "Forge layout requires conflicting releases of {slug}"
            ));
        }
        pins.insert(slug.to_string(), pin);
    }
    Ok(pins.into_values().collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dependency_ranges_keep_upper_bounds_and_exact_pins() {
        for (range, yes, no) in [
            ("^1.8.0", "1.10.0", "2.0.0"),
            ("~1.8.0", "1.8.7", "1.9.0"),
            ("1.8.0", "1.8.0", "1.8.1"),
            (">=1.8.0, <2.0.0", "1.9.0", "2.0.0"),
            ("=1.0.0-beta.2", "1.0.0-beta.2", "1.0.0-beta.3"),
        ] {
            assert!(matches(range, yes).unwrap(), "{range}: {yes}");
            assert!(!matches(range, no).unwrap(), "{range}: {no}");
        }
        for bad in ["", "banana", "latest", ">=1.0.0 <2.0.0"] {
            assert!(requirement(bad).is_err(), "{bad}");
        }
        assert!(!matches("*", "1.0.0-beta.1").unwrap());
    }

    #[test]
    fn dependency_identity_cannot_redirect_requests_or_form_self_cycles() {
        for slug in ["../bad", "https://bad", "owner", "UPPER", "x?token"] {
            assert!(dependencies(&serde_json::json!({"deps":[{"slug":slug}]}), "owner").is_err());
        }
        assert!(dependencies(
            &serde_json::json!({"deps":[{"slug":"pack"},{"slug":"pack"}]}),
            "owner"
        )
        .is_err());
        assert!(dependencies(&serde_json::json!({"deps":null}), "owner").is_err());
    }

    #[test]
    fn pack_tags_stay_in_the_authors_namespace() {
        let manifest = serde_json::json!({"type":"content", "forge_pack":{
            "schema_version":1,"id":"alloy","blocks":[{
                "id":"block_2m","name":"Block","category":"blocks",
                "tag":"objects\\mjolnir\\forge\\alloy\\block_2m",
                "dimensions_m":[2,2,2],"snap_m":1
            }]
        }});
        assert!(read_pack(&manifest, "alloy").unwrap().is_some());
        assert!(read_pack(&manifest, "another").is_err());
        for path in [
            "objects\\weapons\\pistol",
            "objects\\mjolnir\\forge\\other\\block_2m",
        ] {
            let mut bad = manifest.clone();
            bad["forge_pack"]["blocks"][0]["tag"] = path.into();
            assert!(read_pack(&bad, "alloy").is_err());
        }
        let mut bad = manifest.clone();
        bad["forge_pack"]["blocks"][0]["dimensions_m"] = serde_json::json!([0, 2, 2]);
        assert!(read_pack(&bad, "alloy").is_err());
        let mut duplicate = manifest.clone();
        duplicate["forge_pack"]["blocks"]
            .as_array_mut()
            .unwrap()
            .push(manifest["forge_pack"]["blocks"][0].clone());
        assert!(read_pack(&duplicate, "alloy").is_err());
    }

    #[test]
    fn layouts_pin_exact_bytes_and_reject_ambiguous_bindings() {
        let hash = "a".repeat(64);
        let row = format!("0\tobjects\\mjolnir\\forge\\alloy\\block\talloy\t1.0.0\t{hash}");
        let text = format!("forge-packs 1\n{row}\n");
        assert_eq!(
            layout_pins(&text).unwrap(),
            vec![LayoutPin {
                slug: "alloy".into(),
                version: "1.0.0".into(),
                sha256: hash,
            }]
        );
        for bad in [
            text.replace("forge-packs 1", "forge-packs 2"),
            text.replace("alloy\\block", "another\\block"),
            text.replace("1.0.0", "*"),
            format!("{text}{row}\n"),
            format!(
                "{text}{}\n",
                row.replacen("0\t", "1\t", 1).replace("1.0.0", "2.0.0")
            ),
            format!("{text}\n"),
            text.replacen("0\t", "255\t", 1),
            text.replacen("0\t", "+1\t", 1),
        ] {
            assert!(layout_pins(&bad).is_err(), "{bad}");
        }
    }
}
