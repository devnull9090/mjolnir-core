//! Build a data-only, optionally author-signed Forge pack for the Hub.
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use anyhow::{bail, Context, Result};
use clap::{Args, Subcommand};
use serde::Deserialize;
use serde_json::Value;

#[derive(Args)]
pub struct ForgeArgs {
    #[command(subcommand)]
    pub command: ForgeCommand,
}

#[derive(Subcommand)]
pub enum ForgeCommand {
    /// Package a Forge manifest and cooked IoStore containers as .mjolnir.
    Pack(PackArgs),
}

#[derive(Args)]
pub struct PackArgs {
    /// mjolnir.json (type content, with a forge_pack inventory).
    pub manifest: PathBuf,
    /// Folder of cooked .utoc/.ucas pairs (not source .blend or glTF files).
    #[arg(long)]
    pub content: PathBuf,
    /// Output .mjolnir archive; defaults to <pack-id>-<version>.mjolnir.
    #[arg(long)]
    pub out: Option<PathBuf>,
    /// Optional Markdown README to include as docs/README.md.
    #[arg(long)]
    pub readme: Option<PathBuf>,
    /// Optional declared changes.json to include at the archive root.
    #[arg(long)]
    pub changes: Option<PathBuf>,
    #[command(flatten)]
    pub signing: crate::map::Signing,
}

#[derive(Debug, Deserialize)]
struct Manifest {
    schema_version: u32,
    name: String,
    version: String,
    #[serde(rename = "type")]
    kind: String,
    forge_pack: ForgePack,
    #[serde(default)]
    deps: Vec<Dependency>,
    summary: Option<String>,
}

#[derive(Debug, Deserialize)]
struct ForgePack {
    schema_version: u32,
    id: String,
    blocks: Vec<Block>,
}

#[derive(Debug, Deserialize)]
struct Block {
    id: String,
    name: String,
    tag: String,
    category: String,
    dimensions_m: [f64; 3],
    snap_m: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct Dependency {
    slug: String,
    #[serde(default = "any_range")]
    range: String,
}

fn any_range() -> String { "*".into() }

pub(crate) fn valid_slug(value: &str) -> bool {
    (2..=64).contains(&value.len()) && value.as_bytes()[0].is_ascii_alphanumeric()
        && value.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}

pub(crate) fn valid_block_id(value: &str) -> bool {
    (1..=64).contains(&value.len()) && value.as_bytes()[0].is_ascii_alphanumeric()
        && value.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-' || b == b'_')
}

fn validate_manifest(value: &Value) -> Result<Manifest> {
    let manifest: Manifest = serde_json::from_value(value.clone()).context("invalid Forge pack manifest")?;
    if manifest.schema_version != 1 || manifest.kind != "content" || value.get("map").is_some() {
        bail!("a Forge pack is schema_version 1 content, with no map block");
    }
    if manifest.name.trim().is_empty() || manifest.name.chars().count() > 120
        || manifest.summary.as_ref().is_some_and(|s| s.chars().count() > 300) {
        bail!("pack name must be 1–120 characters; summary at most 300");
    }
    let version = semver::Version::parse(&manifest.version).context("pack version must be exact SemVer")?;
    if !version.build.is_empty() {
        bail!("Hub release versions do not support +build metadata; use a prerelease suffix instead");
    }
    let pack = &manifest.forge_pack;
    if pack.schema_version != 1 || !valid_slug(&pack.id) || pack.blocks.is_empty() || pack.blocks.len() > 256 {
        bail!("forge_pack needs schema_version 1, a valid Hub slug and 1–256 blocks");
    }
    let mut ids = BTreeSet::new();
    for block in &pack.blocks {
        if !valid_block_id(&block.id) || !ids.insert(&block.id) || !valid_block_id(&block.category) {
            bail!("invalid or duplicate Forge block id/category: {}", block.id);
        }
        if block.name.trim().is_empty() || block.name.chars().count() > 80 {
            bail!("Forge block {} name must be 1–80 characters", block.id);
        }
        let tag = format!("objects\\mjolnir\\forge\\{}\\{}", pack.id, block.id);
        if block.tag != tag { bail!("Forge block {} must use tag {tag}", block.id); }
        if block.dimensions_m.iter().any(|n| !n.is_finite() || *n <= 0.0)
            || block.snap_m.is_some_and(|n| !n.is_finite() || n <= 0.0) {
            bail!("Forge block {} dimensions and snap must be positive metres", block.id);
        }
    }
    if manifest.deps.len() > 64 { bail!("at most 64 dependencies are supported"); }
    let mut deps = BTreeSet::new();
    for dep in &manifest.deps {
        if !valid_slug(&dep.slug) || dep.slug == pack.id || !deps.insert(&dep.slug) {
            bail!("invalid, self or duplicate dependency: {}", dep.slug);
        }
        if dep.range.is_empty() || dep.range.len() > 120 { bail!("invalid dependency range for {}", dep.slug); }
        semver::VersionReq::parse(&dep.range).with_context(|| format!("unsupported dependency range for {}", dep.slug))?;
    }
    Ok(manifest)
}

/// Collect only container pairs. Other cooker output (including .pak stubs)
/// stays outside the install archive; the launcher generates its own stubs.
fn checked_toc(bytes: &[u8]) -> Result<ue_iostore::toc::Toc> {
    // Toc::parse preserves imperfect shipped tables for editing. Bound every
    // region first here: this command accepts arbitrary authored input.
    if bytes.len() < 144 || &bytes[..16] != ue_iostore::TOC_MAGIC { bail!("invalid IoStore header"); }
    let field = |at: usize| u32::from_le_bytes(bytes[at..at + 4].try_into().unwrap()) as u128;
    let header = field(20);
    let chunks = field(24);
    let blocks = field(28);
    let block_size = field(32);
    let methods = field(36);
    let method_size = field(40);
    if header < 144 || header > bytes.len() as u128 || block_size < 12
        || (methods > 0 && method_size == 0) { bail!("invalid IoStore section dimensions"); }
    let mut prefix = header + chunks * 22 + blocks * block_size + methods * method_size;
    if bytes[16] >= ue_iostore::VER_PERFECT_HASH { prefix += 4 * field(84); }
    if bytes[16] >= ue_iostore::VER_PERFECT_HASH_WITH_OVERFLOW { prefix += 4 * field(96); }
    if prefix > bytes.len() as u128 { bail!("truncated IoStore tables"); }
    if bytes[80] & ue_iostore::FLAG_SIGNED != 0 {
        if prefix + 4 > bytes.len() as u128 { bail!("truncated IoStore signature"); }
        let signature_size = field(prefix as usize);
        if signature_size > i32::MAX as u128 { bail!("invalid IoStore signature size"); }
        prefix += 4 + signature_size * (2 + blocks);
    }
    if prefix + field(48) + chunks * ue_iostore::toc::CHUNK_META as u128 > bytes.len() as u128 {
        bail!("truncated IoStore directory or chunk metadata");
    }
    Ok(ue_iostore::toc::Toc::parse(bytes)?)
}

fn content_members(dir: &Path) -> Result<Vec<(String, Vec<u8>)>> {
    let mut paths = Vec::new();
    for entry in std::fs::read_dir(dir).with_context(|| format!("reading {}", dir.display()))? {
        let entry = entry?;
        let path = entry.path();
        let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("");
        if !["utoc", "ucas"].iter().any(|wanted| ext.eq_ignore_ascii_case(wanted)) { continue; }
        if !["utoc", "ucas"].contains(&ext) || !entry.file_type()?.is_file() {
            bail!("containers must be regular files with lowercase extensions: {}", path.display());
        }
        let stem = path.file_stem().and_then(|s| s.to_str()).context("container name is not UTF-8")?;
        if stem.is_empty() || !stem.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-') {
            bail!("container names may use letters, digits, underscores and hyphens: {}", path.display());
        }
        paths.push(path);
    }
    paths.sort();
    if paths.is_empty() { bail!("no cooked .utoc/.ucas pairs in {}", dir.display()); }
    let mut names = BTreeSet::new();
    for path in &paths {
        let name = path.file_name().unwrap().to_string_lossy().to_lowercase();
        if !names.insert(name) { bail!("case-insensitive duplicate container: {}", path.display()); }
        let mate = path.with_extension(if path.extension().unwrap() == "utoc" { "ucas" } else { "utoc" });
        if !paths.contains(&mate) { bail!("{} has no matching {}", path.display(), mate.display()); }
    }
    let mut members = Vec::new();
    for utoc in paths.iter().filter(|p| p.extension().unwrap() == "utoc") {
        let toc_bytes = std::fs::read(utoc)?;
        let toc = checked_toc(&toc_bytes).with_context(|| format!("invalid {}", utoc.display()))?;
        if toc.flags & ue_iostore::FLAG_ENCRYPTED != 0 { bail!("encrypted containers are not supported: {}", utoc.display()); }
        if toc.chunk_ids.is_empty() || toc.chunk_offsets.len() != toc.chunk_ids.len() || toc.blocks.is_empty()
            || toc.partition_count > 1 { bail!("empty, incomplete or multipart container: {}", utoc.display()); }
        let declared_chunks = u32::from_le_bytes(toc_bytes[24..28].try_into().unwrap()) as usize;
        let declared_blocks = u32::from_le_bytes(toc_bytes[28..32].try_into().unwrap()) as usize;
        if declared_chunks != toc.chunk_ids.len() || declared_blocks != toc.blocks.len() {
            bail!("truncated container index: {}", utoc.display());
        }
        let ucas = utoc.with_extension("ucas");
        let cas_bytes = std::fs::read(&ucas)?;
        if cas_bytes.is_empty() || toc.blocks.iter().any(|b| {
            b.offset.checked_add(u64::from(b.compressed_size)).is_none_or(|end| end > cas_bytes.len() as u64)
        }) { bail!("container data is truncated: {}", ucas.display()); }
        members.push((format!("content/{}", utoc.file_name().unwrap().to_string_lossy()), toc_bytes));
        members.push((format!("content/{}", ucas.file_name().unwrap().to_string_lossy()), cas_bytes));
    }
    Ok(members)
}

fn pack(args: PackArgs) -> Result<()> {
    let value: Value = serde_json::from_slice(&std::fs::read(&args.manifest)?)
        .with_context(|| format!("reading {}", args.manifest.display()))?;
    let manifest = validate_manifest(&value)?;
    let mut members = vec![("mjolnir.json".into(), serde_json::to_vec_pretty(&value)?)];
    members.extend(content_members(&args.content)?);
    if let Some(path) = &args.readme {
        let text = std::fs::read_to_string(path).with_context(|| format!("reading {}", path.display()))?;
        members.push(("docs/README.md".into(), text.into_bytes()));
    }
    if let Some(path) = &args.changes {
        let bytes = std::fs::read(path)?;
        let changes: Value = serde_json::from_slice(&bytes).context("changes must be valid JSON")?;
        if bytes.len() > 512 * 1024 || changes["schema_version"] != 1 { bail!("changes.json must be schema_version 1 and at most 512 KiB"); }
        members.push(("changes.json".into(), bytes));
    }
    let size: usize = members.iter().map(|(_, b)| b.len()).sum();
    if size > 768 * 1024 * 1024 { bail!("unpacked content exceeds the Hub's 768 MiB limit"); }
    let out = args.out.unwrap_or_else(|| PathBuf::from(format!("{}-{}.mjolnir", manifest.forge_pack.id, manifest.version)));
    crate::map::write_archive(members, &manifest.forge_pack.id, &manifest.version, &args.signing, &out)
}

pub fn run(args: ForgeArgs) -> Result<()> {
    match args.command { ForgeCommand::Pack(args) => pack(args) }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read;
    use ue_iostore::toc::{ChunkId, Toc};

    struct Temp(PathBuf);
    impl Temp {
        fn new() -> Self {
            let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
            let path = std::env::temp_dir().join(format!("mjolnir-forge-test-{}-{stamp}", std::process::id()));
            std::fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for Temp {
        fn drop(&mut self) { let _ = std::fs::remove_dir_all(&self.0); }
    }

    fn manifest() -> Value {
        serde_json::json!({
            "schema_version": 1, "name": "Foundry", "version": "1.0.0", "type": "content",
            "summary": "Modular models", "deps": [{"slug":"mjolnir-ce-runtime","range":"=1.15.0"}],
            "forge_pack": {"schema_version":1,"id":"foundry","blocks":[{
                "id":"platform_4x4", "name":"Platform 4 × 4", "category":"platform",
                "tag":"objects\\mjolnir\\forge\\foundry\\platform_4x4",
                "dimensions_m":[4,4,0.5],"snap_m":0.5
            }]}
        })
    }

    fn containers(dir: &Path) {
        let template = Toc {
            version: 8, reserved0: [0;3], header_size: 144, block_entry_size: 12,
            method_name_length: 32, compression_block_size: 65536, partition_count: 1,
            container_id: 0, encryption_guid: [0;16], flags: ue_iostore::FLAG_INDEXED,
            reserved1: [0;3], perfect_hash_seed_count: 0, partition_size: u64::MAX,
            chunks_without_perfect_hash: 0, header_tail: vec![0;44], chunk_ids: vec![],
            chunk_offsets: vec![], perfect_hash: vec![], blocks: vec![], methods: vec![],
            signature: vec![], directory_index: vec![], chunk_meta: vec![], trailing: vec![],
        };
        let built = ue_iostore::pack::build(&template, 123, &[ue_iostore::pack::Entry {
            id: ChunkId { id: 456, index: 0, pad: 0, kind: 2 }, data: vec![7;32], meta: vec![0;24],
        }]);
        std::fs::write(dir.join("foundry_P.utoc"), built.utoc).unwrap();
        std::fs::write(dir.join("foundry_P.ucas"), built.ucas).unwrap();
    }

    #[test]
    fn manifest_namespace_dimensions_and_dependency_rules() {
        let valid = manifest();
        validate_manifest(&valid).unwrap();
        for (pointer, bad) in [
            ("/type", serde_json::json!("map")),
            ("/schema_version", serde_json::json!(2)),
            ("/version", serde_json::json!("01.0.0")),
            ("/version", serde_json::json!("1.0.0+unsupported")),
            ("/forge_pack/id", serde_json::json!("x")),
            ("/forge_pack/id", serde_json::json!("-foundry")),
            ("/forge_pack/blocks/0/id", serde_json::json!("_platform")),
            ("/forge_pack/blocks/0/tag", serde_json::json!("objects\\mjolnir\\forge\\other\\platform_4x4")),
            ("/forge_pack/blocks/0/category", serde_json::json!("Floors")),
            ("/forge_pack/blocks/0/dimensions_m", serde_json::json!([4,0,1])),
            ("/forge_pack/blocks/0/snap_m", serde_json::json!(-1)),
            ("/deps/0/slug", serde_json::json!("foundry")),
            ("/deps/0/slug", serde_json::json!("../runtime")),
            ("/deps/0/range", serde_json::json!("latest")),
        ] {
            let mut value = valid.clone();
            *value.pointer_mut(pointer).unwrap() = bad;
            assert!(validate_manifest(&value).is_err(), "{pointer}: {value}");
        }
        let mut duplicate = valid.clone();
        let block = duplicate["forge_pack"]["blocks"][0].clone();
        duplicate["forge_pack"]["blocks"].as_array_mut().unwrap().push(block);
        assert!(validate_manifest(&duplicate).is_err());
    }

    #[test]
    fn forge_pack_container_pair_and_extent_checks() {
        let dir = Temp::new();
        assert!(content_members(&dir.0).is_err());
        containers(&dir.0);
        std::fs::write(dir.0.join("source.py"), "not shipped").unwrap();
        let members = content_members(&dir.0).unwrap();
        assert_eq!(members.len(), 2);
        assert!(members.iter().all(|(p, _)| p.starts_with("content/")));
        std::fs::write(dir.0.join("orphan.ucas"), [1]).unwrap();
        assert!(content_members(&dir.0).is_err());
        std::fs::remove_file(dir.0.join("orphan.ucas")).unwrap();
        std::fs::write(dir.0.join("foundry_P.ucas"), [1]).unwrap();
        assert!(content_members(&dir.0).is_err());
        containers(&dir.0);
        let mut bytes = std::fs::read(dir.0.join("foundry_P.utoc")).unwrap();
        bytes[80] |= ue_iostore::FLAG_ENCRYPTED;
        std::fs::write(dir.0.join("foundry_P.utoc"), bytes).unwrap();
        assert!(content_members(&dir.0).is_err());
    }

    #[test]
    fn forge_pack_malformed_toc_headers_fail_without_panicking() {
        let dir = Temp::new();
        containers(&dir.0);
        let valid = std::fs::read(dir.0.join("foundry_P.utoc")).unwrap();
        checked_toc(&valid).unwrap();
        for (at, value) in [(20, 0), (20, u32::MAX), (24, u32::MAX), (28, u32::MAX),
            (32, 0), (32, 8), (32, u32::MAX), (36, u32::MAX), (48, u32::MAX), (84, u32::MAX)] {
            let mut invalid = valid.clone();
            invalid[at..at + 4].copy_from_slice(&value.to_le_bytes());
            assert!(checked_toc(&invalid).is_err(), "field {at}={value}");
        }
        for length in [0, 16, 143, 144, valid.len() - 1] {
            assert!(checked_toc(&valid[..length]).is_err(), "length {length}");
        }
    }

    #[test]
    fn signed_forge_archive_round_trip_verifies_every_member() {
        let dir = Temp::new();
        let content = dir.0.join("content");
        std::fs::create_dir(&content).unwrap();
        containers(&content);
        let manifest_path = dir.0.join("manifest.json");
        std::fs::write(&manifest_path, serde_json::to_vec(&manifest()).unwrap()).unwrap();
        let seed = dir.0.join("test-only.seed");
        std::fs::write(&seed, [42u8;32]).unwrap();
        let readme = dir.0.join("README.md");
        std::fs::write(&readme, "# Foundry\nOriginal modular models.\n").unwrap();
        let changes = dir.0.join("changes.json");
        std::fs::write(&changes, br#"{"schema_version":1,"tags":[]}"#).unwrap();
        let out = dir.0.join("foundry-1.0.0.mjolnir");
        pack(PackArgs {
            manifest: manifest_path, content, out: Some(out.clone()), readme: Some(readme), changes: Some(changes),
            signing: crate::map::Signing { sign: false, sign_seed: Some(seed) },
        }).unwrap();
        let mut zip = zip::ZipArchive::new(std::fs::File::open(&out).unwrap()).unwrap();
        let mut members = Vec::new();
        for i in 0..zip.len() {
            let mut entry = zip.by_index(i).unwrap();
            let name = entry.name().to_owned();
            let mut bytes = Vec::new();
            entry.read_to_end(&mut bytes).unwrap();
            members.push((name, bytes));
        }
        assert_eq!(members.len(), 6);
        let refs: Vec<_> = members.iter().map(|(name, bytes)| (name.clone(), bytes.as_slice())).collect();
        let envelope = refs.iter().find(|(name, _)| name == "signature.json").unwrap().1;
        mjolnir_sign::verify_members(envelope, "foundry", "1.0.0", &refs).unwrap();
        let incomplete: Vec<_> = refs.iter().filter(|(name, _)| name != "docs/README.md").cloned().collect();
        assert!(mjolnir_sign::verify_members(envelope, "foundry", "1.0.0", &incomplete).is_err());
    }
}
