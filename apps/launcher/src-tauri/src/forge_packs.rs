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

/// Entry kinds this launcher, the bake and Forge handle (docs/forge_packs.md).
/// A pack with any other kind, a weapon say, needs a newer launcher: it must
/// never be installed and handed to Forge as building blocks.
pub const KINDS: &[&str] = &["block"];
/// Features a pack may require beyond catalog schema 1. None exist yet.
pub const FEATURES: &[&str] = &[];

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ForgePack {
    pub schema_version: u32,
    pub id: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub requires: Vec<String>,
    pub blocks: Vec<Block>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Block {
    pub id: String,
    /// Absent means "block".
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub kind: Option<String>,
    pub name: String,
    pub tag: String,
    pub category: String,
    pub dimensions_m: [f64; 3],
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub snap_m: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub light: Option<Light>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lift: Option<Lift>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub door: Option<Door>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub surfaces: Option<Vec<Surface>>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Surface { pub slot: u8, pub profile: String }

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Lift {
    pub offset_m: [f64; 3],
    pub size_m: [f64; 3],
    pub direction: [f64; 3],
    pub acceleration_m_s2: f64,
    pub max_speed_m_s: f64,
    pub negates_gravity: bool,
}
impl Lift {
    fn valid(&self) -> bool {
        self.offset_m.iter().all(|n| n.is_finite() && n.abs() <= 100.0)
            && self.size_m.iter().all(|n| n.is_finite() && (0.1..=100.0).contains(n))
            && self.direction.iter().all(|n| n.is_finite() && n.abs() <= 1.0)
            && (self.direction.iter().map(|n| n*n).sum::<f64>() - 1.0).abs() <= 0.001
            && self.acceleration_m_s2.is_finite() && (0.1..=100.0).contains(&self.acceleration_m_s2)
            && self.max_speed_m_s.is_finite() && (0.1..=30.0).contains(&self.max_speed_m_s)
    }
}
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Door {
    pub travel_m: f64,
    pub speed_m_s: f64,
    pub trigger_size_m: [f64; 3],
    pub hold_open_s: f64,
}
impl Door {
    fn valid(&self) -> bool {
        self.travel_m.is_finite() && self.travel_m > 0.0 && self.travel_m <= 16.0
            && self.speed_m_s.is_finite() && self.speed_m_s > 0.0 && self.speed_m_s <= 8.0
            && self.trigger_size_m.iter().all(|n| n.is_finite() && *n > 0.0 && *n <= 32.0)
            && self.hold_open_s.is_finite() && (0.0..=10.0).contains(&self.hold_open_s)
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Light {
    pub offset_m: [f64; 3],
    pub color_rgb: [f64; 3],
    pub intensity_cd: f64,
    pub radius_m: f64,
}

impl Light {
    fn valid(&self) -> bool {
        self.offset_m.iter().all(|n| n.is_finite() && n.abs() <= 100.0)
            && self.color_rgb.iter().all(|n| n.is_finite() && (0.0..=1.0).contains(n))
            && self.intensity_cd.is_finite()
            && self.intensity_cd > 0.0
            && self.intensity_cd <= 10000.0
            && self.radius_m.is_finite()
            && self.radius_m > 0.0
            && self.radius_m <= 100.0
    }
}

/// Why this launcher cannot use a catalog written for a newer one, read from
/// the raw JSON so the answer is "update" rather than a parse error about a
/// field a newer catalog may legitimately have.
fn needs_newer_launcher(value: &serde_json::Value, slug: &str) -> Option<String> {
    let schema = value.get("schema_version").and_then(|v| v.as_u64());
    if schema.is_some_and(|n| n > 1) {
        return Some(format!("{slug} is a Forge pack for a newer MJOLNIR launcher (catalog schema {}). Update the launcher to use it.", schema.unwrap_or(0)));
    }
    let unknown = |list: Option<&serde_json::Value>, known: &[&str]| {
        list.and_then(|v| v.as_array()).into_iter().flatten()
            .filter_map(|v| v.as_str())
            .find(|s| !known.contains(s))
            .map(str::to_string)
    };
    if let Some(feature) = unknown(value.get("requires"), FEATURES) {
        return Some(format!("{slug} needs the Forge pack feature \"{feature}\", which needs a newer MJOLNIR launcher. Update the launcher to use it."));
    }
    let kinds: Vec<_> = value.get("blocks").and_then(|v| v.as_array()).into_iter().flatten()
        .filter_map(|b| b.get("kind")).cloned().collect();
    if let Some(kind) = unknown(Some(&serde_json::Value::Array(kinds)), KINDS) {
        return Some(format!("{slug} has {kind} pieces, which need a newer MJOLNIR launcher. Update the launcher to use it."));
    }
    None
}

impl ForgePack {
    pub fn validate(&self, slug: &str) -> Result<(), String> {
        if let Some(why) = serde_json::to_value(self).ok().and_then(|v| needs_newer_launcher(&v, slug)) {
            return Err(why);
        }
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
            if block.light.as_ref().is_some_and(|light| !light.valid()) {
                return Err(format!("Invalid light settings for {}", block.id));
            }
            if block.lift.as_ref().is_some_and(|lift| !lift.valid()) {
                return Err(format!("Invalid lift settings for {}", block.id));
            }
            if block.door.as_ref().is_some_and(|door| !door.valid() || block.dimensions_m.iter().any(|n| *n > 64.0)) {
                return Err(format!("Invalid door settings for {}", block.id));
            }
            if let Some(surfaces) = &block.surfaces {
                let mut slots = BTreeSet::new();
                if surfaces.len() > 16 || surfaces.iter().any(|s| s.slot > 15 || !slots.insert(s.slot)
                    || !matches!(s.profile.as_str(), "glass_cyan" | "teleporter_green")) {
                    return Err(format!("Invalid surface settings for {}", block.id));
                }
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
    let version = manifest["version"].as_str().ok_or("Forge pack version is missing")?;
    if version.len() > 96 || !semver::Version::parse(version).is_ok_and(|v| v.build.is_empty()) {
        return Err("Forge pack version must be exact SemVer without build metadata, at most 96 bytes".into());
    }
    if let Some(why) = needs_newer_launcher(value, slug) {
        return Err(why);
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

/// The releases a saved layout loads with: the one it was saved with, or a
/// later one in its caret line. The Hub refuses a release that drops or
/// changes an entry of an earlier one in the same line, and the recorded
/// SHA-256 stays for diagnostics, not as a gate.
pub fn layout_range(pin: &LayoutPin) -> String {
    format!("^{}", pin.version)
}

/// Combine one more layout's pin on a pack: two layouts saved in the same
/// caret line need the later release; different lines cannot share a game.
pub fn merge_layout_pin(
    pins: &mut std::collections::BTreeMap<String, LayoutPin>,
    pin: LayoutPin,
) -> Result<(), String> {
    let Some(old) = pins.get(&pin.slug) else {
        pins.insert(pin.slug.clone(), pin);
        return Ok(());
    };
    let parse = |v: &str| semver::Version::parse(v).map_err(|e| e.to_string());
    let (lower, higher) = if parse(&old.version)? <= parse(&pin.version)? { (old, &pin) } else { (&pin, old) };
    if !matches(&layout_range(lower), &higher.version)? {
        return Err(format!(
            "Saved Forge layouts need incompatible releases of {} ({} and {}). Move one layout aside before launching.",
            pin.slug, old.version, pin.version
        ));
    }
    let higher = higher.clone();
    pins.insert(higher.slug.clone(), higher);
    Ok(())
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
        let manifest = serde_json::json!({"type":"content", "version":"1.0.0", "forge_pack":{
            "schema_version":1,"id":"alloy","blocks":[{
                "id":"block_2m","name":"Block","category":"blocks",
                "tag":"objects\\mjolnir\\forge\\alloy\\block_2m",
                "dimensions_m":[2,2,2],"snap_m":1
            }]
        }});
        assert!(read_pack(&manifest, "alloy").unwrap().is_some());
        assert!(read_pack(&manifest, "another").is_err());
        for version in ["1.0.0+build", "01.0.0", "1.0.0-01", "18446744073709551616.0.0", "1.0.0-"] {
            let mut bad = manifest.clone();
            bad["version"] = version.into();
            assert!(read_pack(&bad, "alloy").is_err(), "{version}");
        }
        let mut long = manifest.clone();
        long["version"] = format!("1.0.0-{}", "a".repeat(91)).into();
        assert!(read_pack(&long, "alloy").is_err());
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
    fn a_pack_for_a_newer_launcher_asks_for_an_update_instead_of_installing_as_blocks() {
        let manifest = serde_json::json!({"type":"content", "version":"1.0.0", "forge_pack":{
            "schema_version":1,"id":"alloy","blocks":[{
                "id":"block_2m","kind":"block","name":"Block","category":"blocks",
                "tag":"objects\\mjolnir\\forge\\alloy\\block_2m","dimensions_m":[2,2,2]
            }]
        }});
        let pack = read_pack(&manifest, "alloy").unwrap().unwrap();
        assert_eq!(pack.blocks[0].kind.as_deref(), Some("block"));
        let mut weapon = manifest.clone();
        weapon["forge_pack"]["blocks"][0]["kind"] = "weapon".into();
        // A newer weapon entry may carry fields this launcher has never seen.
        weapon["forge_pack"]["blocks"][0]["light"] = serde_json::json!({"flash": true});
        let why = read_pack(&weapon, "alloy").unwrap_err();
        assert!(why.contains("weapon pieces") && why.contains("newer MJOLNIR launcher"), "{why}");
        let mut feature = manifest.clone();
        feature["forge_pack"]["requires"] = serde_json::json!(["turrets"]);
        let why = read_pack(&feature, "alloy").unwrap_err();
        assert!(why.contains("\"turrets\"") && why.contains("newer MJOLNIR launcher"), "{why}");
        let mut schema = manifest.clone();
        schema["forge_pack"]["schema_version"] = 2.into();
        let why = read_pack(&schema, "alloy").unwrap_err();
        assert!(why.contains("catalog schema 2"), "{why}");
        let mut none = manifest.clone();
        none["forge_pack"]["requires"] = serde_json::json!([]);
        assert!(read_pack(&none, "alloy").unwrap().is_some());
        // A validated pack keeps its gates when the launcher writes it out.
        let mut stored = pack.clone();
        stored.blocks[0].kind = Some("vehicle".into());
        assert!(stored.validate("alloy").unwrap_err().contains("vehicle pieces"));
    }

    #[test]
    fn saved_layouts_accept_later_releases_in_their_caret_line() {
        let pin = |version: &str| LayoutPin { slug: "alloy".into(), version: version.into(), sha256: "a".repeat(64) };
        assert!(matches(&layout_range(&pin("0.2.0")), "0.2.3").unwrap());
        assert!(!matches(&layout_range(&pin("0.2.3")), "0.2.0").unwrap());
        assert!(!matches(&layout_range(&pin("0.2.0")), "0.3.0").unwrap());
        assert!(matches(&layout_range(&pin("1.2.0")), "1.9.0").unwrap());
        assert!(!matches(&layout_range(&pin("1.2.0")), "2.0.0").unwrap());
        let mut pins = std::collections::BTreeMap::new();
        merge_layout_pin(&mut pins, pin("0.2.1")).unwrap();
        merge_layout_pin(&mut pins, pin("0.2.4")).unwrap();
        merge_layout_pin(&mut pins, pin("0.2.0")).unwrap();
        assert_eq!(pins["alloy"].version, "0.2.4");
        assert!(merge_layout_pin(&mut pins, pin("0.3.0")).unwrap_err().contains("incompatible releases"));
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

    #[test]
    fn light_metadata_survives_catalog_storage_and_absent_lights_stay_absent() {
        let manifest = serde_json::json!({"type":"content", "version":"1.0.0", "forge_pack":{
            "schema_version":1,"id":"alloy","blocks":[{
                "id":"lamp","name":"Lamp","category":"lights",
                "tag":"objects\\mjolnir\\forge\\alloy\\lamp","dimensions_m":[1,1,1],
                "light":{"offset_m":[-100,0,100],"color_rgb":[1,0,0.5],"intensity_cd":10000,"radius_m":100}
            }]
        }});
        let pack = read_pack(&manifest, "alloy").unwrap().unwrap();
        let stored = serde_json::to_vec(&pack).unwrap();
        let restored: ForgePack = serde_json::from_slice(&stored).unwrap();
        restored.validate("alloy").unwrap();
        let light = restored.blocks[0].light.as_ref().unwrap();
        assert_eq!(light.offset_m, [-100.0, 0.0, 100.0]);
        assert_eq!(light.color_rgb, [1.0, 0.0, 0.5]);
        assert_eq!((light.intensity_cd, light.radius_m), (10000.0, 100.0));
        for absent in [None, Some(serde_json::Value::Null)] {
            let mut old = manifest.clone();
            old["forge_pack"]["blocks"][0].as_object_mut().unwrap().remove("light");
            if let Some(value) = absent { old["forge_pack"]["blocks"][0]["light"] = value; }
            let old = read_pack(&old, "alloy").unwrap().unwrap();
            assert!(old.blocks[0].light.is_none());
            assert!(serde_json::to_value(old).unwrap()["blocks"][0].get("light").is_none());
        }
    }

    #[test]
    fn lift_door_and_surface_metadata_roundtrip_and_reject_invalid_settings() {
        let lift=serde_json::json!({"offset_m":[0.0,0.0,0.45],"size_m":[4.0,4.0,3.5],"direction":[0.0,0.0,1.0],
            "acceleration_m_s2":20.0,"max_speed_m_s":4.5,"negates_gravity":true});
        let door=serde_json::json!({"travel_m":4.0,"speed_m_s":4.0,"trigger_size_m":[8.0,16.0,6.0],"hold_open_s":2.0});
        let value=serde_json::json!({"type":"content","version":"1.0.0","forge_pack":{
            "schema_version":1,"id":"alloy","blocks":[{"id":"utility","name":"Utility","category":"utility",
            "tag":"objects\\mjolnir\\forge\\alloy\\utility","dimensions_m":[8,1,4],"lift":lift,"door":door,
            "surfaces":[{"slot":7,"profile":"glass_cyan"}]}]}});
        let pack=read_pack(&value,"alloy").unwrap().unwrap();
        let encoded=serde_json::to_value(&pack).unwrap();
        assert_eq!(encoded["blocks"][0]["lift"],value["forge_pack"]["blocks"][0]["lift"]);
        assert_eq!(encoded["blocks"][0]["door"],value["forge_pack"]["blocks"][0]["door"]);
        let restored:ForgePack=serde_json::from_value(encoded).unwrap(); restored.validate("alloy").unwrap();
        for (pointer,bad_value) in [
            ("/lift/direction",serde_json::json!([0,0,0])), ("/lift/size_m",serde_json::json!([4,4,101])),
            ("/lift/acceleration_m_s2",serde_json::json!(0)), ("/lift/max_speed_m_s",serde_json::json!(31)),
            ("/lift/negates_gravity",serde_json::json!(1)), ("/door/travel_m",serde_json::json!(17)),
            ("/door/speed_m_s",serde_json::json!(9)), ("/door/trigger_size_m",serde_json::json!([8,33,6])),
            ("/door/hold_open_s",serde_json::json!(-1)), ("/dimensions_m",serde_json::json!([8,1,65])),
            ("/surfaces",serde_json::json!([{"slot":16,"profile":"glass_cyan"}])),
            ("/surfaces",serde_json::json!([{"slot":0,"profile":"glass_cyan"},{"slot":0,"profile":"teleporter_green"}])),
        ] {
            let mut bad=value.clone(); *bad.pointer_mut(&format!("/forge_pack/blocks/0{pointer}")).unwrap()=bad_value;
            assert!(read_pack(&bad,"alloy").is_err(),"{pointer}");
        }
        for field in ["lift","door"] {
            let mut bad=value.clone(); bad["forge_pack"]["blocks"][0][field]["script"]=serde_json::json!("x");
            assert!(read_pack(&bad,"alloy").is_err());
        }
        for n in [f64::NAN,f64::INFINITY,f64::NEG_INFINITY] {
            let mut bad=pack.clone();bad.blocks[0].lift.as_mut().unwrap().direction[0]=n;
            assert!(bad.validate("alloy").is_err());
            let mut bad=pack.clone();bad.blocks[0].door.as_mut().unwrap().travel_m=n;
            assert!(bad.validate("alloy").is_err());
        }
        let mut old=value.clone();
        for field in ["lift","door","surfaces"] {old["forge_pack"]["blocks"][0][field]=serde_json::Value::Null;}
        let old=serde_json::to_value(read_pack(&old,"alloy").unwrap().unwrap()).unwrap();
        for field in ["lift","door","surfaces"] {assert!(old["blocks"][0].get(field).is_none());}
    }

    #[test]
    fn lights_reject_invalid_vectors_unknown_settings_and_unbounded_values() {
        let light = serde_json::json!({"offset_m":[0,0,1],"color_rgb":[1,0,0],"intensity_cd":25,"radius_m":8});
        for (key, value) in [
            ("offset_m", serde_json::json!([0,0,100.01])),
            ("offset_m", serde_json::json!([-100.01,0,0])),
            ("color_rgb", serde_json::json!([1.01,0,0])),
            ("color_rgb", serde_json::json!([0,-0.01,0])),
            ("radius_m", serde_json::json!(0)),
            ("radius_m", serde_json::json!(100.01)),
            ("intensity_cd", serde_json::json!(0)),
            ("intensity_cd", serde_json::json!(-1)),
            ("intensity_cd", serde_json::json!(10000.01)),
        ] {
            let mut invalid = light.clone();
            invalid[key] = value;
            assert!(!serde_json::from_value::<Light>(invalid).unwrap().valid(), "{key}");
        }
        for (key, value) in [
            ("color_rgb", serde_json::json!([1,0])),
            ("offset_m", serde_json::json!([0,0,0,0])),
            ("script", serde_json::json!("untrusted.lua")),
        ] {
            let mut invalid = light.clone();
            invalid[key] = value;
            assert!(serde_json::from_value::<Light>(invalid).is_err(), "{key}");
        }
        for value in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            for field in 0..4 {
                let mut invalid: Light = serde_json::from_value(light.clone()).unwrap();
                match field {
                    0 => invalid.offset_m[0] = value,
                    1 => invalid.color_rgb[0] = value,
                    2 => invalid.intensity_cd = value,
                    _ => invalid.radius_m = value,
                }
                assert!(!invalid.valid());
            }
        }
    }
}
