//! `mjolnir ue` — read and edit the properties of any cooked Unreal package,
//! not just a tag: a material instance's parameters, a data asset's fields,
//! a component template's settings.
//!
//! `get` flattens an export's property block to `path = value` rows; `set`
//! changes one value by path and writes the package into an override
//! container the game loads in front of the shipped one (the `_P` sibling
//! model every other override here uses). The block goes through the
//! lossless encoder in `ue_asset::props`, so every byte the cook wrote and
//! this command did not touch comes back as it was — including the class's
//! native tail after the properties. Object references cannot be retargeted:
//! that needs import-map surgery this foundation does not do.

use std::path::PathBuf;

use anyhow::{bail, Context, Result};
use clap::{Args, Subcommand};

use crate::Source;

#[derive(Args)]
pub struct UeArgs {
    #[command(subcommand)]
    pub command: UeCommand,
}

#[derive(Subcommand)]
pub enum UeCommand {
    /// List an export's properties as `path = value` rows.
    Get(GetArgs),
    /// Set one property by path and write an override container.
    Set(SetArgs),
    /// Decode and re-encode every export of the packages matching a
    /// substring, counting the ones that come back byte for byte.
    Roundtrip(RoundtripArgs),
    /// Add a button to a menu widget (the main menu by default) that opens
    /// one of our screens, and write the menu into an override container.
    MenuButton(MenuButtonArgs),
    /// Print a Blueprint function's bytecode, statement by statement.
    Disasm(DisasmArgs),
}

#[derive(Args)]
pub struct MenuButtonArgs {
    #[command(flatten)]
    pub src: Source,
    /// The menu widget's package.
    #[arg(long, default_value = "ui/Frontend/MainMenu/Widgets/WBP_MainMenu")]
    pub package: String,
    /// The new button's name (also its class variable's).
    #[arg(long, default_value = "MultiplayerButton")]
    pub name: String,
    /// Its label.
    #[arg(long, default_value = "MULTIPLAYER")]
    pub label: String,
    /// The button to copy; the new one goes right after it.
    #[arg(long, default_value = "RemixButton")]
    pub template: String,
    /// The widget class the button opens.
    #[arg(
        long,
        default_value = "/Game/MJOLNIR/UI/WBP_MJOLNIRLobby.WBP_MJOLNIRLobby_C"
    )]
    pub opens: String,
    /// A substring of the class path in the menu's own push to copy.
    #[arg(long, default_value = "WBP_CustomizationCategoryMenu")]
    pub push_like: String,
    /// Directory to write the container into.
    #[arg(long, default_value = ".")]
    pub out_dir: PathBuf,
    /// Container name (`_P` is added when missing).
    #[arg(long, default_value = "pakchunk985-MJOLNIRMENU_P")]
    pub container: String,
}

#[derive(Args)]
pub struct DisasmArgs {
    #[command(flatten)]
    pub src: Source,
    /// The package, as `/Game/...` or a substring of its path.
    #[arg(long)]
    pub package: String,
    /// The function export, by index or name.
    #[arg(long)]
    pub export: String,
}

#[derive(Args)]
pub struct GetArgs {
    #[command(flatten)]
    pub src: Source,
    /// The package, as `/Game/...` or a substring of its path.
    #[arg(long)]
    pub package: String,
    /// Which export; the first with a script class when omitted.
    #[arg(long)]
    pub export: Option<usize>,
    /// Only rows whose path contains this.
    #[arg(long)]
    pub filter: Option<String>,
}

#[derive(Args)]
pub struct SetArgs {
    #[command(flatten)]
    pub src: Source,
    /// The package, as `/Game/...` or a substring of its path.
    #[arg(long)]
    pub package: String,
    /// Which export; the first with a script class when omitted.
    #[arg(long)]
    pub export: Option<usize>,
    /// The property path, e.g. `ScalarParameterValues[0].ParameterValue`.
    /// Repeat with `--value` to set several in one container.
    #[arg(long, required = true)]
    pub field: Vec<String>,
    /// The new value as text, one per `--field`.
    #[arg(long, required = true)]
    pub value: Vec<String>,
    /// Directory to write the container into.
    #[arg(long, default_value = ".")]
    pub out_dir: PathBuf,
    /// Container name (the game needs a `_P` suffix to treat it as an
    /// override; it is added when missing).
    #[arg(long, default_value = "pakchunk996-MJOLNIRUE_P")]
    pub name: String,
}

#[derive(Args)]
pub struct RoundtripArgs {
    #[command(flatten)]
    pub src: Source,
    /// Packages whose path contains this.
    #[arg(long)]
    pub filter: String,
    /// Stop after this many packages.
    #[arg(long, default_value_t = 500)]
    pub limit: usize,
}

pub fn run(a: UeArgs) -> Result<()> {
    match a.command {
        UeCommand::Get(a) => get(a),
        UeCommand::Set(a) => set(a),
        UeCommand::Roundtrip(a) => roundtrip(a),
        UeCommand::MenuButton(a) => menu_button(a),
        UeCommand::Disasm(a) => disasm(a),
    }
}

/// The package's container, chunk and full path, by `/Game/...` name or a
/// path substring (exact name first).
fn locate(
    containers: &[ue_iostore::Container],
    want: &str,
) -> Result<(usize, ue_iostore::ChunkEntry, String)> {
    let lower = want.to_ascii_lowercase();
    // The exact name wins, then an exact leaf, then the first substring hit.
    let mut by_leaf: Option<(usize, ue_iostore::ChunkEntry, String)> = None;
    let mut by_substring: Option<(usize, ue_iostore::ChunkEntry, String)> = None;
    for (ci, c) in containers.iter().enumerate() {
        for (rel, chunk_index) in &c.files {
            let full = c.full_path(rel);
            if !(full.ends_with(".uasset") || full.ends_with(".umap")) {
                continue;
            }
            let Some(name) = ue_asset::level::package_name_of(&full) else {
                continue;
            };
            if name.eq_ignore_ascii_case(want) {
                return Ok((ci, c.chunks[*chunk_index], name));
            }
            let leaf = name.rsplit('/').next().unwrap_or(&name);
            if by_leaf.is_none() && leaf.eq_ignore_ascii_case(want) {
                by_leaf = Some((ci, c.chunks[*chunk_index], name.clone()));
            }
            if by_substring.is_none() && full.to_ascii_lowercase().contains(&lower) {
                by_substring = Some((ci, c.chunks[*chunk_index], name));
            }
        }
    }
    by_leaf
        .or(by_substring)
        .with_context(|| format!("no package matching {want:?}"))
}

fn open(
    a_src: &Source,
    want: &str,
    export: Option<usize>,
) -> Result<(
    Vec<ue_iostore::Container>,
    Vec<PathBuf>,
    usize,
    ue_iostore::ChunkEntry,
    String,
    Vec<u8>,
    ue_asset::package::ZenPackage,
    ue_asset::Usmap,
    ue_asset::zen::ScriptObjects,
    ue_asset::edit::ExportEdit,
)> {
    let containers = ue_iostore::load_all(&a_src.paks)?;
    let oodle = a_src.oodle_roots();
    let (ci, chunk, name) = locate(&containers, want)?;
    let data = ue_iostore::read_chunk(&containers[ci], &chunk, None, &oodle)?;
    let pkg = ue_asset::package::ZenPackage::parse(&data)?;
    let usmap = crate::mesh::usmap()?;
    let scripts = crate::mesh::script_objects(&containers, &oodle)?;
    let index = match export {
        Some(i) => i,
        None => (0..pkg.export_map.len())
            .find(|i| ue_asset::edit::export_class(&pkg, &scripts, *i).is_some())
            .context("no export with a script class")?,
    };
    let edit = ue_asset::edit::open_export(&pkg, &usmap, &scripts, index)
        .map_err(|e| anyhow::anyhow!("{name}: {e}"))?;
    Ok((
        containers, oodle, ci, chunk, name, data, pkg, usmap, scripts, edit,
    ))
}

fn get(a: GetArgs) -> Result<()> {
    let (_, _, _, _, name, _, pkg, usmap, scripts, edit) = open(&a.src, &a.package, a.export)?;
    println!("{name}");
    for (i, e) in pkg.export_map.iter().enumerate() {
        let class = ue_asset::edit::export_class(&pkg, &scripts, i)
            .unwrap_or_else(|| "(Blueprint class)".into());
        println!(
            "  export {i}: {} : {class}, {} bytes{}",
            pkg.mapped_name(e.name_index, e.name_number),
            e.cooked_serial_size,
            if i == edit.index { "  <- shown" } else { "" }
        );
    }
    let rows = ue_asset::edit::describe(&usmap, &edit.class, &pkg.names.names, &edit.block);
    let filter = a.filter.map(|f| f.to_ascii_lowercase());
    for r in rows {
        if let Some(f) = &filter {
            if !r.path.to_ascii_lowercase().contains(f) {
                continue;
            }
        }
        println!("  {} = {}   ({})", r.path, r.value, r.ty);
    }
    println!("  native tail: {} bytes", edit.tail.len());
    Ok(())
}

fn set(a: SetArgs) -> Result<()> {
    let (containers, oodle, ci, chunk, name, data, mut pkg, usmap, _scripts, mut edit) =
        open(&a.src, &a.package, a.export)?;
    if a.field.len() != a.value.len() {
        bail!("{} --field but {} --value", a.field.len(), a.value.len());
    }
    let names_before = pkg.names.names.clone();
    println!("{name} export {} ({})", edit.index, edit.class);
    let mut set_values: Vec<ue_asset::props::Val> = Vec::new();
    for (field, value) in a.field.iter().zip(&a.value) {
        let (before, ty) =
            match ue_asset::edit::get(&usmap, &edit.class, &pkg.names.names, &edit.block, field) {
                Ok((v, ty)) => (
                    ue_asset::edit::value_text(&pkg.names.names, Some(&ty), &v),
                    Some(ty),
                ),
                Err(_) => ("(absent)".to_string(), None),
            };
        let new = ue_asset::edit::set(
            &usmap,
            &edit.class,
            &mut pkg.names,
            &mut edit.block,
            field,
            value,
        )
        .map_err(|e| anyhow::anyhow!("{name}: {e}"))?;
        let after = ue_asset::edit::value_text(&pkg.names.names, ty.as_ref(), &new);
        println!("  {field} : {before} -> {after}");
        set_values.push(new);
    }
    if pkg.names.names.len() != names_before.len() {
        println!(
            "  {} name(s) added to the package",
            pkg.names.names.len() - names_before.len()
        );
    }
    ue_asset::edit::write_export(&mut pkg, &usmap, &edit)
        .map_err(|e| anyhow::anyhow!("{name}: {e}"))?;
    let patched = pkg.write();

    // Read it back the way the game will: the same export decodes to the
    // values that were set.
    let check = ue_asset::package::ZenPackage::parse(&patched)?;
    let scripts = crate::mesh::script_objects(&containers, &oodle)?;
    let back = ue_asset::edit::open_export(&check, &usmap, &scripts, edit.index)
        .map_err(|e| anyhow::anyhow!(e))?;
    for (field, new) in a.field.iter().zip(&set_values) {
        let (v, _) =
            ue_asset::edit::get(&usmap, &back.class, &check.names.names, &back.block, field)
                .map_err(|e| anyhow::anyhow!(e))?;
        if v != *new {
            bail!("the rewritten package reads back differently at {field}: {v:?}");
        }
    }

    write_override(
        &containers[ci],
        &oodle,
        chunk,
        &name,
        data.len(),
        patched,
        &a.out_dir,
        &a.name,
    )
}

/// Put a rewritten package into an override container (`_P`), read it back
/// through its perfect hash, and write the stub `.pak` beside it.
#[allow(clippy::too_many_arguments)]
fn write_override(
    source: &ue_iostore::Container,
    oodle: &[PathBuf],
    chunk: ue_iostore::ChunkEntry,
    name: &str,
    original_len: usize,
    patched: Vec<u8>,
    out_dir: &std::path::Path,
    container_name: &str,
) -> Result<()> {
    let patched_len = patched.len();
    let built = blam_pack::build_override(
        source,
        oodle,
        &[blam_pack::ChunkEdit {
            label: format!("{name}.uasset"),
            chunk,
            // A cooked Unreal package has no Blam `BinaryBlobSize` to keep in
            // step: declaring the patched length keeps the packer on the
            // plain-replacement path (package_override.rs).
            original_len: patched_len,
            patched,
        }],
    )
    .map_err(|e| anyhow::anyhow!(e))?;
    let mut container = container_name.to_string();
    if !container.ends_with("_P") {
        container.push_str("_P");
    }
    std::fs::create_dir_all(out_dir)?;
    let utoc = out_dir.join(format!("{container}.utoc"));
    let ucas = out_dir.join(format!("{container}.ucas"));
    std::fs::write(&utoc, &built.utoc)?;
    std::fs::write(&ucas, &built.ucas)?;
    blam_pack::verify_written(&utoc, oodle, &built.expect).map_err(|e| anyhow::anyhow!(e))?;
    std::fs::write(
        out_dir.join(format!("{container}.pak")),
        ue_iostore::pak::stub_for(&container),
    )?;
    println!(
        "  wrote {} ({original_len} -> {patched_len} bytes in the package)",
        utoc.display()
    );
    Ok(())
}

fn menu_button(a: MenuButtonArgs) -> Result<()> {
    let containers = ue_iostore::load_all(&a.src.paks)?;
    let oodle = a.src.oodle_roots();
    let (ci, chunk, name) = locate(&containers, &a.package)?;
    let data = ue_iostore::read_chunk(&containers[ci], &chunk, None, &oodle)?;
    let mut pkg = ue_asset::package::ZenPackage::parse(&data)?;
    let usmap = crate::mesh::usmap()?;
    let scripts = crate::mesh::script_objects(&containers, &oodle)?;
    let spec = ue_asset::menu_button::MenuButton {
        name: &a.name,
        label: &a.label,
        template: &a.template,
        opens: &a.opens,
        push_like: &a.push_like,
    };
    let added = ue_asset::menu_button::add_menu_button(&mut pkg, &usmap, &scripts, &spec)
        .map_err(|e| anyhow::anyhow!("{name}: {e}"))?;
    println!("{name}");
    println!(
        "  {} after {} (container index {}), labelled {:?}",
        a.name, a.template, added.position, a.label
    );
    println!(
        "  exports {} (click), {} (slot), {} (button); the click enters the ubergraph at {}",
        added.function, added.slot, added.button, added.entry
    );
    println!("  opens {}", a.opens);
    let patched = pkg.write();
    ue_asset::package::ZenPackage::parse(&patched)?;
    write_override(
        &containers[ci],
        &oodle,
        chunk,
        &name,
        data.len(),
        patched,
        &a.out_dir,
        &a.container,
    )
}

/// Export names and `/Script` import leaves, for the disassembly.
struct PkgNames<'a> {
    pkg: &'a ue_asset::package::ZenPackage,
    scripts: &'a ue_asset::zen::ScriptObjects,
}

impl ue_asset::kismet::Names for PkgNames<'_> {
    fn name(&self, index: u32, number: u32) -> String {
        self.pkg.mapped_name(index, number)
    }
    fn object(&self, index: i32) -> String {
        if index > 0 {
            let e = &self.pkg.export_map[(index - 1) as usize];
            self.pkg.mapped_name(e.name_index, e.name_number)
        } else if index < 0 {
            let id = self
                .pkg
                .import_map
                .get((-index - 1) as usize)
                .copied()
                .unwrap_or(u64::MAX);
            self.scripts
                .leaf(ue_asset::zen::ObjectIndex(id))
                .map(str::to_string)
                .unwrap_or_else(|| format!("import{}", -index - 1))
        } else {
            "null".into()
        }
    }
}

fn disasm(a: DisasmArgs) -> Result<()> {
    let containers = ue_iostore::load_all(&a.src.paks)?;
    let oodle = a.src.oodle_roots();
    let (ci, chunk, name) = locate(&containers, &a.package)?;
    let data = ue_iostore::read_chunk(&containers[ci], &chunk, None, &oodle)?;
    let pkg = ue_asset::package::ZenPackage::parse(&data)?;
    let scripts = crate::mesh::script_objects(&containers, &oodle)?;
    let index = match a.export.parse::<usize>() {
        Ok(i) => i,
        Err(_) => (0..pkg.export_map.len())
            .find(|&i| {
                let e = &pkg.export_map[i];
                pkg.mapped_name(e.name_index, e.name_number) == a.export
            })
            .with_context(|| format!("no export named {}", a.export))?,
    };
    let bytes = pkg.export_bytes(index).context("export out of range")?;
    let names = PkgNames {
        pkg: &pkg,
        scripts: &scripts,
    };
    let script = ue_asset::kismet::script(bytes, &names)
        .map_err(|e| anyhow::anyhow!("{name} export {index}: {e}"))?;
    println!(
        "{name} export {index}: {} statement(s), {} bytes in memory",
        script.stmts.len(),
        script.memory_size
    );
    for s in &script.stmts {
        println!("{:6}: {}", s.offset, s.text);
    }
    Ok(())
}

fn roundtrip(a: RoundtripArgs) -> Result<()> {
    let containers = ue_iostore::load_all(&a.src.paks)?;
    let oodle = a.src.oodle_roots();
    let usmap = crate::mesh::usmap()?;
    let scripts = crate::mesh::script_objects(&containers, &oodle)?;
    let lower = a.filter.to_ascii_lowercase();
    let mut by_class: std::collections::BTreeMap<String, (usize, usize, usize)> =
        Default::default();
    let mut first: Option<String> = None;
    let mut packages = 0usize;
    'outer: for c in &containers {
        let mut names: Vec<&String> = c.files.keys().collect();
        names.sort();
        for rel in names {
            let full = c.full_path(rel);
            if !(full.ends_with(".uasset") || full.ends_with(".umap"))
                || !full.to_ascii_lowercase().contains(&lower)
            {
                continue;
            }
            if packages >= a.limit {
                break 'outer;
            }
            packages += 1;
            let data = ue_iostore::read_chunk(c, &c.chunks[c.files[rel]], None, &oodle)?;
            let Ok(pkg) = ue_asset::package::ZenPackage::parse(&data) else {
                continue;
            };
            // The whole package must also come back byte for byte.
            let whole = pkg.write() == data;
            for i in 0..pkg.export_map.len() {
                let Some(class) = ue_asset::edit::export_class(&pkg, &scripts, i) else {
                    continue;
                };
                let entry = by_class.entry(class.clone()).or_default();
                let bytes = pkg.export_bytes(i).unwrap_or(&[]);
                match ue_asset::props::decode_prefix(&usmap, &class, bytes) {
                    Ok((block, used)) => match block.encode(&usmap, &class) {
                        Ok(back) if back == bytes[..used] && whole => entry.0 += 1,
                        Ok(_) => {
                            entry.1 += 1;
                            first.get_or_insert_with(|| {
                                format!(
                                    "{full} [{i}] {class}: bytes differ{}",
                                    if whole { "" } else { " (package layout)" }
                                )
                            });
                        }
                        Err(e) => {
                            entry.2 += 1;
                            first.get_or_insert_with(|| format!("{full} [{i}] {class}: {e}"));
                        }
                    },
                    Err(e) => {
                        entry.2 += 1;
                        first.get_or_insert_with(|| format!("{full} [{i}] {class}: {e}"));
                    }
                }
            }
        }
    }
    println!("{packages} package(s)");
    println!("{:>7} {:>7} {:>7}  class", "exact", "differ", "unsupp");
    for (class, (a, b, c)) in &by_class {
        println!("{a:7} {b:7} {c:7}  {class}");
    }
    if let Some(f) = first {
        println!("first problem: {f}");
    }
    Ok(())
}
