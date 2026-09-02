//! `mjolnir` — inspect Halo Campaign Evolved tag data.
//!
//! Reads directly from an installed game's IoStore containers. Nothing is
//! written to disk: extracted tag data is copyrighted game content and stays in
//! memory.

use std::collections::BTreeMap;
use std::path::PathBuf;

use anyhow::{Context, Result};
use blam_tag::TagFile;
use clap::{Args, Parser, Subcommand};

mod container;
mod defs;
mod hsc;
mod index;
mod tagdiff;
mod texture;

/// Find a data file that ships alongside the binary.
///
/// The defaults for `--corpus` are repository-relative, which is right when the
/// tool is run out of a checkout and useless when it is not: an installed build
/// lives wherever the packager put it, and the working directory is wherever the
/// person happens to be standing. So if the given path is not there, look
/// relative to the executable, in the four layouts this actually ships in:
///
/// | Where it came from | Binary | Data |
/// | --- | --- | --- |
/// | release archive, Scoop, Chocolatey | `<dir>/mjolnir` | `<dir>/defs/…` |
/// | .deb, .rpm, Homebrew | `<prefix>/bin/mjolnir` | `<prefix>/share/mjolnir/defs/…` |
/// | `cargo build` in a checkout | `target/release/mjolnir` | `<repo>/defs/…` |
///
/// An explicit `--corpus` that does not exist still comes back unchanged, so the
/// error names the path the caller asked for rather than one they never typed.
fn resolve_data_path(given: &std::path::Path) -> PathBuf {
    if given.exists() || given.is_absolute() {
        return given.to_path_buf();
    }
    let Ok(exe) = std::env::current_exe() else {
        return given.to_path_buf();
    };
    let Some(dir) = exe.parent() else {
        return given.to_path_buf();
    };
    let candidates = [
        dir.to_path_buf(),
        // FHS: /usr/bin/mjolnir reads /usr/share/mjolnir/…, and the same
        // relative step lands correctly under /usr/local and a Homebrew Cellar
        // prefix, which is what makes one binary work for every packager.
        dir.join("../share/mjolnir"),
        dir.join(".."),
        dir.join("../.."),
    ];
    for base in candidates {
        let candidate = base.join(given);
        if candidate.exists() {
            return candidate;
        }
    }
    given.to_path_buf()
}

fn hex(bytes: &[u8]) -> String {
    bytes
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<Vec<_>>()
        .join(" ")
}

#[derive(Parser)]
#[command(name = "mjolnir", version, about, long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Args, Clone)]
pub struct Source {
    /// Path to the game's `Meteorite/Content/Paks` directory.
    #[arg(long, env = "HCE_PAKS")]
    paks: PathBuf,
    /// Path to `oo2core_*_win64.dll`, or a directory containing one. Optional:
    /// without it the built-in decoder is used, which is slower but reads the
    /// same bytes.
    #[arg(long, env = "OODLE")]
    oodle: Option<PathBuf>,
}

impl Source {
    fn oodle_roots(&self) -> Vec<PathBuf> {
        self.oodle.clone().into_iter().collect()
    }
}

#[derive(Subcommand)]
enum Command {
    /// Summarise the shipped tag groups and their definition tables.
    Groups(GroupsArgs),
    /// List tag paths.
    List(ListArgs),
    /// Print the section tree and definition tables for one group.
    Layout(LayoutArgs),
    /// Print the resolved field list for one group.
    Fields(FieldsArgs),
    /// Histogram definition types across every group.
    Types(TypesArgs),
    /// Histogram the field record aux word, grouped by type name.
    Aux(AuxArgs),
    /// Check structural invariants across every shipped tag.
    Validate(ValidateArgs),
    /// Export the definition corpus as JSON.
    Defs(DefsArgs),
    /// Inspect the bdat data payload for one tag.
    Data(DataArgs),
    /// Histogram the tgly child sections and the blay preamble across groups.
    Sections(SectionsArgs),
    /// Histogram the version word of every section in the bdat payload.
    DataVersions(SectionsArgs),
    /// Re-serialise every tag and check the bytes come back identical.
    Roundtrip(ValidateArgs),
    /// Print one tag's fields with their decoded values.
    Values(ValuesArgs),
    /// Decode and re-encode every field, checking no byte changes.
    Recode(ValidateArgs),
    /// Change one field of a tag and report exactly which bytes moved.
    Set(SetArgs),
    /// Parse each .utoc container index and write it back, comparing bytes.
    TocRoundtrip(SectionsArgs),
    /// Build an override container holding one edited tag.
    Pack(PackArgs),
    /// Hexdump any chunk in the shipped containers, found by path.
    Chunk(ChunkArgs),
    /// Name the shipped assets an override container replaces.
    Container(container::ContainerArgs),
    /// Print or edit a tag payload already on disk, without the paks or Oodle.
    TagFile(TagFileArgs),
    /// Change a field in the *running* game, without rebuilding or restarting.
    Poke(PokeArgs),
    /// Read the Blam script a scenario carries.
    Script(ScriptArgs),
    /// Recover the scripting function table and export it as JSON.
    Scripting(ScriptingArgs),
    /// Compile `.hsc` files and report what the compiler makes of them.
    Compile(CompileArgs),
    /// Inspect, export and swap cooked textures.
    #[command(subcommand_help_heading = "Texture")]
    Texture(texture::TextureArgs),
    /// Diff the shipped tags of two builds, field by field.
    Tagdiff(tagdiff::TagDiffArgs),
}

#[derive(Args)]
struct CompileArgs {
    /// The `.hsc` files to compile. They are compiled together, so a script in
    /// one may call a script in another.
    #[arg(required = true)]
    files: Vec<PathBuf>,
    /// Recovered scripting corpus, which supplies the function table.
    #[arg(long, default_value = "defs/hce/scripting.json")]
    corpus: PathBuf,
    /// Print the tree the compiler produced, decompiled.
    #[arg(long)]
    show: bool,
}

#[derive(Args)]
struct ScriptingArgs {
    #[command(flatten)]
    src: Source,
    /// Output JSON path.
    #[arg(long, default_value = "defs/hce/scripting.json")]
    out: PathBuf,
    /// Build fingerprint to record in the corpus.
    #[arg(long, default_value = "")]
    build: String,
    /// Report what was recovered without writing the file.
    #[arg(long)]
    dry_run: bool,
    /// Share of agreeing observations needed to call a literal quoted.
    #[arg(long, default_value_t = blam_hsc::corpus::DEFAULT_QUOTED_MAJORITY)]
    quoted_threshold: f32,
}

#[derive(Args)]
struct ScriptArgs {
    #[command(flatten)]
    src: Source,
    /// Substring of the scenario tag path to select, otherwise every scenario
    /// is summarised.
    #[arg(long)]
    tag: Option<String>,
    /// Print this source file's text instead of the summary. Give the file's
    /// name as the summary lists it, e.g. `a30_audio`.
    #[arg(long)]
    source: Option<String>,
    /// List the scripts and globals the scenario declares.
    #[arg(long)]
    declarations: bool,
    /// Render the compiled expression tree back to HSC. With a name, only that
    /// script; without one, the whole scenario.
    #[arg(long, num_args = 0..=1, default_missing_value = "")]
    decompile: Option<String>,
    /// Decompile every script and compare it against the source the scenario
    /// shipped with.
    #[arg(long)]
    verify: bool,
    /// Compile the scenario's own source files back into an expression tree,
    /// then decompile that and check every script comes back unchanged.
    #[arg(long)]
    recompile: bool,
    /// Write the script section back unchanged and check the tag comes out byte
    /// for byte identical.
    #[arg(long)]
    rewrite_check: bool,
    /// Compile the scenario's own source, write it back into the tag, and check
    /// the result still reads exactly.
    #[arg(long)]
    rebuild_check: bool,
    /// With --verify, print the first few disagreements in full.
    #[arg(long, default_value_t = 5)]
    show: usize,
    /// Recovered scripting corpus, used to know which literals are quoted.
    /// Ignored if the file is absent.
    #[arg(long, default_value = "defs/hce/scripting.json")]
    corpus: PathBuf,
}

#[derive(Args)]
struct PokeArgs {
    #[command(flatten)]
    src: Source,
    /// Group directory name, e.g. `biped`.
    #[arg(long)]
    group: String,
    /// Substring of the tag path to select, otherwise the first tag is used.
    #[arg(long)]
    tag: Option<String>,
    /// Field path, e.g. `jump velocity`.
    #[arg(long)]
    field: String,
    /// New value, in the same form the inspector shows.
    #[arg(long)]
    value: String,
    /// Attach to this pid instead of finding the game automatically.
    #[arg(long)]
    pid: Option<u32>,
    /// Find the tag and report its live value, but change nothing.
    #[arg(long)]
    locate_only: bool,
}

#[derive(Args)]
struct GroupsArgs {
    #[command(flatten)]
    src: Source,
}

#[derive(Args)]
struct ListArgs {
    #[command(flatten)]
    src: Source,
    /// Restrict to one group directory name, e.g. `weapon`.
    #[arg(long)]
    group: Option<String>,
    /// Maximum rows to print.
    #[arg(long, default_value_t = 50)]
    limit: usize,
}

#[derive(Args)]
struct LayoutArgs {
    #[command(flatten)]
    src: Source,
    /// Group directory name, e.g. `weapon`.
    #[arg(long)]
    group: String,
    /// Print the resolved enum and bitfield option names.
    #[arg(long)]
    options: bool,
    /// Print the type, block, and struct tables.
    #[arg(long)]
    tables: bool,
    /// Dump one named section's content as annotated words, e.g. `arr!`.
    #[arg(long)]
    section: Option<String>,
}

#[derive(Args)]
struct FieldsArgs {
    #[command(flatten)]
    src: Source,
    /// Group directory name, e.g. `weapon`.
    #[arg(long)]
    group: String,
    /// Maximum fields to print.
    #[arg(long, default_value_t = 60)]
    limit: usize,
}

#[derive(Args)]
struct TypesArgs {
    #[command(flatten)]
    src: Source,
    /// Show up to this many example groups per type name.
    #[arg(long, default_value_t = 3)]
    examples: usize,
}

#[derive(Args)]
struct AuxArgs {
    #[command(flatten)]
    src: Source,
    /// Restrict to one type name, e.g. `pad`.
    #[arg(long, name = "type")]
    type_name: Option<String>,
}

#[derive(Args)]
struct ValidateArgs {
    #[command(flatten)]
    src: Source,
    /// Check every shipped tag rather than one per group.
    #[arg(long)]
    all: bool,
    /// Print each failure instead of only the totals.
    #[arg(long)]
    verbose: bool,
}

#[derive(Args)]
struct DefsArgs {
    #[command(flatten)]
    src: Source,
    /// Output JSON path.
    #[arg(long, default_value = "defs/hce/tag-definitions.json")]
    out: PathBuf,
    /// Build fingerprint to record in the corpus.
    #[arg(long, default_value = "")]
    build: String,
}

#[derive(Args)]
struct ValuesArgs {
    #[command(flatten)]
    src: Source,
    /// Group directory name, e.g. `weapon`.
    #[arg(long)]
    group: String,
    /// Substring of the tag path to select, otherwise the first tag is used.
    #[arg(long)]
    tag: Option<String>,
    /// Maximum nesting to print.
    #[arg(long, default_value_t = 3)]
    depth: u32,
    /// Maximum block elements to print per block.
    #[arg(long, default_value_t = 4)]
    elements: usize,
    /// Print fields whose value is empty or zero.
    #[arg(long)]
    all: bool,
}

#[derive(Args)]
struct SetArgs {
    #[command(flatten)]
    src: Source,
    /// Group directory name, e.g. `weapon`.
    #[arg(long)]
    group: String,
    /// Substring of the tag path to select, otherwise the first tag is used.
    #[arg(long)]
    tag: Option<String>,
    /// Field path, e.g. `unit.object.bounding radius` or `control points[3].position`.
    #[arg(long)]
    field: String,
    /// New value, in the same form the inspector shows.
    #[arg(long)]
    value: String,
    /// Write the patched tag here. Without this nothing is written to disk.
    #[arg(long)]
    out: Option<PathBuf>,
}

#[derive(Args)]
struct PackArgs {
    #[command(flatten)]
    src: Source,
    /// Group directory name, e.g. `weapon`.
    #[arg(long)]
    group: String,
    /// Substring of the tag path to select.
    #[arg(long)]
    tag: Option<String>,
    /// A field to change, as `path=value`. Repeatable.
    #[arg(long = "set", value_name = "PATH=VALUE")]
    sets: Vec<String>,
    /// Directory to write the container into.
    #[arg(long)]
    out_dir: PathBuf,
    /// Container base name; `.utoc` and `.ucas` are appended.
    ///
    /// The `_P` suffix is UE's patch-container convention and is what makes the
    /// override win the chunk lookup. Without it the shipped chunk is used and
    /// nothing appears to happen, so it is the default rather than an option.
    #[arg(long, default_value = "pakchunk999-MJOLNIR-Windows_P")]
    name: String,
}

#[derive(Args)]
struct TagFileArgs {
    /// A raw tag payload on disk — a bulk-data chunk extracted from a container.
    #[arg(long)]
    file: PathBuf,
    /// Field path to change, e.g. `magazines[0].rounds loaded maximum`.
    /// Without it, the tag's values are printed instead.
    #[arg(long)]
    field: Option<String>,
    /// New value, in the same form the inspector shows.
    #[arg(long)]
    value: Option<String>,
    /// Write the patched tag here. Without this nothing is written to disk.
    #[arg(long)]
    out: Option<PathBuf>,
    /// Maximum nesting to print.
    #[arg(long, default_value_t = 3)]
    depth: u32,
    /// Maximum block elements to print per block.
    #[arg(long, default_value_t = 4)]
    elements: usize,
    /// Print fields whose value is empty or zero.
    #[arg(long)]
    all: bool,
}

#[derive(Args)]
struct ChunkArgs {
    #[command(flatten)]
    src: Source,
    /// Substring of the packaged path, e.g. `assault_rifle-weapon.uasset`.
    #[arg(long)]
    path: String,
    /// Bytes to dump.
    #[arg(long, default_value_t = 256)]
    hexdump: usize,
    /// Report where this little-endian u32 appears in the chunk.
    #[arg(long)]
    find_u32: Option<u32>,
}

#[derive(Args)]
struct SectionsArgs {
    #[command(flatten)]
    src: Source,
}

#[derive(Args)]
struct DataArgs {
    #[command(flatten)]
    src: Source,
    /// Group directory name, e.g. `camera_track`.
    #[arg(long)]
    group: String,
    /// Substring of the tag path to select, otherwise the first tag is used.
    #[arg(long)]
    tag: Option<String>,
    /// Hexdump this many bytes of the data payload.
    #[arg(long, default_value_t = 256)]
    hexdump: usize,
    /// Print the value-tree walk step by step, including on failure.
    #[arg(long)]
    trace: bool,
    /// Maximum trace lines to print.
    #[arg(long, default_value_t = 200)]
    trace_limit: usize,
}

fn main() -> Result<()> {
    match Cli::parse().command {
        Command::Groups(a) => groups(a),
        Command::List(a) => list(a),
        Command::Layout(a) => layout(a),
        Command::Fields(a) => fields(a),
        Command::Types(a) => types(a),
        Command::Aux(a) => aux(a),
        Command::Validate(a) => validate(a),
        Command::Defs(a) => export_defs(a),
        Command::Data(a) => data(a),
        Command::Sections(a) => sections(a),
        Command::DataVersions(a) => data_versions(a),
        Command::Roundtrip(a) => roundtrip(a),
        Command::Values(a) => values(a),
        Command::Recode(a) => recode(a),
        Command::Set(a) => set(a),
        Command::TocRoundtrip(a) => toc_roundtrip(a),
        Command::Pack(a) => pack(a),
        Command::Chunk(a) => chunk(a),
        Command::Container(a) => container::run(a),
        Command::TagFile(a) => tag_file(a),
        Command::Poke(a) => poke(a),
        Command::Script(a) => script(a),
        Command::Scripting(a) => scripting(a),
        Command::Compile(a) => compile(a),
        Command::Texture(a) => texture::run(a),
        Command::Tagdiff(a) => tagdiff::run(a),
    }
}

/// Print or edit a tag payload that is already a file.
///
/// Every other command reaches a tag through the shipped containers, which
/// means Oodle, which means a DLL this repository cannot ship. But a tag's
/// layout comes from its own header rather than from any external definition,
/// so bytes on disk are enough — including the uncompressed payload sitting in
/// an override container we built ourselves.
fn tag_file(a: TagFileArgs) -> Result<()> {
    let file =
        std::fs::read(&a.file).with_context(|| format!("cannot read {}", a.file.display()))?;
    let tag = TagFile::parse(&file, Some(file.len()))?;
    let l = tag.layout()?;
    let block = tag
        .read_data(&l)
        .with_context(|| format!("{} is not readable as a tag", a.file.display()))?;

    let Some(field) = a.field.as_deref() else {
        let nodes = blam_tag::view::root_capped(&l, &block, build_cap(a.elements));
        println!("{}", a.file.display());
        println!(
            "  {} v{} - {} bytes, {} nodes\n",
            tag.header.group,
            tag.header.group_version,
            file.len(),
            nodes.iter().map(|n| n.len()).sum::<usize>()
        );
        for n in &nodes {
            print_node(
                n,
                1,
                &PrintOpts {
                    depth: a.depth,
                    elements: a.elements,
                    all: a.all,
                },
            );
        }
        return Ok(());
    };

    let value = a
        .value
        .as_deref()
        .context("--field needs --value; without both, this prints the tag")?;

    let target = blam_tag::patch::resolve(&l, &file, &block, field)?;
    let parsed = match target.type_name.as_str() {
        "tag reference" => parse_reference(value)?,
        "string id" => blam_tag::Scalar::Text(value.trim_matches('"').to_string()),
        _ => blam_tag::value::parse(&l, &target.field, value)?,
    };
    // A section-backed field resizes the tag, so it takes the rebuild path.
    let resizes = target.section.is_some();
    let (patched, applied) = if resizes {
        blam_tag::patch::set_text(&l, &file, &block, field, &parsed)?
    } else {
        blam_tag::patch::set(&l, &file, &block, field, &parsed)?
    };

    println!("{}", a.file.display());
    println!("  field    {}  [{}]", applied.path, applied.type_name);
    println!("  before   {}", applied.before.display());
    println!("  after    {}", applied.after.display());
    println!("  file     {} bytes -> {} bytes", file.len(), patched.len());

    // Re-reading is the real claim: an edit that does not walk is not an edit.
    let after = TagFile::parse(&patched, Some(patched.len()))?;
    let al = after.layout()?;
    let ab = after.read_data(&al)?;
    let ap = after.data().context("patched tag has no bdat section")?;
    println!(
        "  re-read  {}",
        blam_tag::patch::resolve(&al, &patched, &ab, field)?
            .current
            .display()
    );
    println!("  walk     {} of {} bytes consumed", ab.consumed, ap.size);
    if ab.consumed != ap.size as usize {
        anyhow::bail!("the patched tag no longer walks exactly");
    }

    if patched.len() == file.len() {
        let d: Vec<usize> = (0..file.len())
            .filter(|i| file[*i] != patched[*i])
            .collect();
        println!("  differs  {} byte(s) from the original", d.len());
        for i in d.iter().take(8) {
            println!(
                "           0x{i:X}: {:02x} -> {:02x}",
                file[*i], patched[*i]
            );
        }
    }

    match &a.out {
        Some(path) => {
            std::fs::write(path, &patched)?;
            println!("\n  wrote {}", path.display());
            println!(
                "  This is game content. Keep it local; the repository does not take tag data."
            );
        }
        None => println!("\n  dry run; pass --out <file> to write the patched tag"),
    }
    Ok(())
}

fn data(a: DataArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let entries = by_group
        .get(a.group.as_str())
        .with_context(|| format!("unknown group {:?}", a.group))?;
    let entry = match &a.tag {
        Some(want) => entries
            .iter()
            .find(|e| e.path.contains(want))
            .copied()
            .with_context(|| format!("no {} tag matching {want:?}", a.group))?,
        None => entries[0],
    };

    let buf = idx.read(entry, None, &a.src.oodle_roots())?;
    let tag = TagFile::parse(&buf, Some(entry.chunk.length as usize))?;
    let l = tag.layout()?;
    let payload = tag.data().context("tag has no bdat section")?;

    println!("{}", entry.path);
    println!("  chunk         {} bytes", entry.chunk.length);
    println!("  data (tgbl)   {} bytes", payload.size);
    let root = l.root_struct();
    let root_size = root.and_then(|r| l.struct_size(r));
    println!("  root struct   {root_size:?} bytes");

    if let (Some(run), Some(size)) = (root, root_size) {
        println!("\n  root fields:");
        let ranges = l.struct_ranges();
        // The payload opens with the root block's {count, flags} header; the
        // root element's packed fields start after it.
        const ELEMENTS: usize = 8;
        let mut offset = 0usize;
        for f in &l.fields[ranges[run].clone()] {
            let (name, type_name, _) = l.field_info(f);
            let width = l.field_size(f).unwrap_or(0) as usize;
            let bytes = payload
                .content
                .get(ELEMENTS + offset..ELEMENTS + offset + width)
                .unwrap_or(&[]);
            let shown = if name.is_empty() { "<unnamed>" } else { name };
            println!(
                "    +{offset:<5} {width:>4}b  {type_name:<24} {shown:<36} {}",
                hex(&bytes[..bytes.len().min(16)])
            );
            offset += width;
        }
        println!("\n  root consumes {offset} of {} bytes", payload.size);
        println!(
            "  remaining     {} bytes",
            payload.size as usize - size as usize
        );
    }

    if a.hexdump > 0 {
        println!("\n  data hexdump:");
        let end = a.hexdump.min(payload.content.len());
        for off in (0..end).step_by(16) {
            let row = &payload.content[off..(off + 16).min(end)];
            let ascii: String = row
                .iter()
                .map(|b| {
                    if (32..127).contains(b) {
                        *b as char
                    } else {
                        '.'
                    }
                })
                .collect();
            println!("    {off:08x}  {:<47}  |{ascii}|", hex(row));
        }
    }

    // Every dword-aligned position whose four bytes look like a section magic.
    let mut magics: BTreeMap<String, usize> = BTreeMap::new();
    let content = payload.content;
    // Magics are stored reversed, so a `tg..` section reads as `..gt` on disk.
    // Match on those two bytes only: at least one shipped magic carries a NUL
    // in its third character, so an is-alphanumeric filter hides it.
    for off in 0..content.len().saturating_sub(4) {
        if content[off + 3] != b't' || content[off + 2] != b'g' {
            continue;
        }
        let cc: String = content[off..off + 4]
            .iter()
            .rev()
            .map(|b| {
                if (32..127).contains(b) {
                    *b as char
                } else {
                    '.'
                }
            })
            .collect();
        *magics.entry(cc).or_default() += 1;
    }
    println!("\n  section magics in the data payload:");
    for (cc, n) in &magics {
        println!("    {cc}  x{n}");
    }

    if a.trace {
        let (result, report) = blam_tag::data::read_block_traced(&l, payload.content, 0);
        let trace = &report.trace;
        println!(
            "\n  walk trace ({} lines, {} sections):",
            trace.len(),
            report.sections.len()
        );
        let skipped = trace.len().saturating_sub(a.trace_limit);
        if skipped > 0 {
            println!("    ... {skipped} earlier lines elided ...");
        }
        for line in trace.iter().skip(skipped) {
            println!("    {line}");
        }
        if let Err(e) = &result {
            println!("    !! {e}");
        }
    }

    println!("\n  data walk:");
    match tag.read_data(&l) {
        Ok(block) => println!(
            "    ok - {} element(s), consumed {} of {} bytes{}",
            block.count,
            block.consumed,
            payload.size,
            if block.consumed == payload.size as usize {
                " (exact)"
            } else {
                " (MISMATCH)"
            }
        ),
        Err(e) => println!("    failed: {e}"),
    }
    Ok(())
}

/// Read each tag, write the value tree back out, and require the bytes to be
/// identical. This is the precondition for any editing feature: a writer that
/// cannot reproduce an untouched tag cannot be trusted with a modified one.
fn roundtrip(a: ValidateArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let oodle = a.src.oodle_roots();
    let by_group = idx.by_group();

    let targets: Vec<&index::TagEntry> = if a.all {
        idx.tags.iter().collect()
    } else {
        by_group.values().map(|v| v[0]).collect()
    };

    let (mut checked, mut identical, mut differs, mut unreadable) =
        (0usize, 0usize, 0usize, 0usize);
    let mut bytes = 0u64;

    for entry in targets {
        checked += 1;
        let Ok(buf) = idx.read(entry, None, &oodle) else {
            unreadable += 1;
            continue;
        };
        let Ok(tag) = TagFile::parse(&buf, Some(entry.chunk.length as usize)) else {
            unreadable += 1;
            continue;
        };
        let Ok(l) = tag.layout() else {
            unreadable += 1;
            continue;
        };
        let Some(payload) = tag.data() else {
            unreadable += 1;
            continue;
        };
        let block = match tag.read_data(&l) {
            Ok(b) => b,
            Err(_) => {
                unreadable += 1;
                continue;
            }
        };

        let written = blam_tag::write_block(&block);
        if written == payload.content {
            identical += 1;
            bytes += written.len() as u64;
        } else {
            differs += 1;
            if a.verbose {
                let at = written
                    .iter()
                    .zip(payload.content)
                    .position(|(x, y)| x != y)
                    .unwrap_or(written.len().min(payload.content.len()));
                eprintln!(
                    "{}: wrote {} bytes, original {}, first difference at {at}",
                    entry.path,
                    written.len(),
                    payload.content.len()
                );
            }
        }
    }

    let pct = |n: usize| {
        let base = identical + differs;
        if base == 0 {
            0.0
        } else {
            n as f64 * 100.0 / base as f64
        }
    };
    println!("checked {checked} tags");
    println!("  not readable, so not round-tripped  {unreadable}");
    println!(
        "  re-serialised byte for byte         {identical} ({:.1}%)",
        pct(identical)
    );
    println!("  differs                             {differs}");
    println!("  bytes reproduced                    {bytes}");
    Ok(())
}

/// Is a `bdat` section's version word reconstructable, or must a writer store
/// it? Tests each magic's version against the candidates a writer could compute.
fn data_versions(a: SectionsArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let oodle = a.src.oodle_roots();

    // magic -> (total, version==0, version==size, distinct versions)
    let mut hist: BTreeMap<String, (usize, usize, usize, BTreeMap<u32, usize>)> = BTreeMap::new();

    for entries in by_group.values() {
        let Ok(buf) = idx.read(entries[0], None, &oodle) else {
            continue;
        };
        let Ok(tag) = TagFile::parse(&buf, Some(entries[0].chunk.length as usize)) else {
            continue;
        };
        let Ok(l) = tag.layout() else { continue };
        let Some(payload) = tag.data() else { continue };

        let (_, report) = blam_tag::data::read_block_traced(&l, payload.content, 0);
        for st in &report.sections {
            let name: String = st
                .magic
                .iter()
                .rev()
                .map(|b| {
                    if (32..127).contains(b) {
                        *b as char
                    } else {
                        '.'
                    }
                })
                .collect();
            let e = hist.entry(name).or_default();
            e.0 += 1;
            if st.version == 0 {
                e.1 += 1;
            }
            if st.version == st.size {
                e.2 += 1;
            }
            *e.3.entry(st.version).or_default() += 1;
        }
    }

    println!("magic\tseen\tver==0\tver==size\tdistinct\tsample");
    for (magic, (total, zero, eq, versions)) in &hist {
        let sample = versions
            .iter()
            .take(5)
            .map(|(v, n)| format!("{v}x{n}"))
            .collect::<Vec<_>>()
            .join(" ");
        println!(
            "{magic}\t{total}\t{zero}\t{eq}\t{}\t{sample}",
            versions.len()
        );
    }
    println!("\nA writer can regenerate a version word only where one column equals `seen`.");
    Ok(())
}

/// Which `tgly` child sections carry content, and what the `blay` preamble
/// words correlate with.
fn sections(a: SectionsArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let oodle = a.src.oodle_roots();

    // magic -> (groups seen in, groups where size > 0, largest size)
    let mut seen: BTreeMap<String, (usize, usize, u32)> = BTreeMap::new();
    // preamble word index -> how many groups it matched each candidate in
    let mut matches: BTreeMap<usize, BTreeMap<String, usize>> = BTreeMap::new();
    let mut groups = 0usize;

    for entries in by_group.values() {
        let Ok(buf) = idx.read(entries[0], None, &oodle) else {
            continue;
        };
        let Ok(tag) = TagFile::parse(&buf, Some(entries[0].chunk.length as usize)) else {
            continue;
        };
        let Ok(l) = tag.layout() else { continue };
        groups += 1;

        for s in &l.sections {
            let e = seen.entry(s.name()).or_insert((0, 0, 0));
            e.0 += 1;
            if s.size > 0 {
                e.1 += 1;
            }
            e.2 = e.2.max(s.size);
        }

        // Candidate meanings for each preamble word, tested per group. Every
        // tgly child contributes its byte size and its size divided by the
        // plausible record widths, so a count lands whatever the record shape.
        let mut candidates: Vec<(String, u32)> = vec![
            ("blob bytes".to_string(), l.blob.len() as u32),
            ("options".to_string(), l.option_offsets.len() as u32),
            ("types".to_string(), l.types.len() as u32),
            ("fields".to_string(), l.fields.len() as u32),
            ("blocks".to_string(), l.blocks.len() as u32),
            ("structs".to_string(), l.structs.len() as u32),
            ("arrays".to_string(), l.arrays.len() as u32),
            ("enums".to_string(), l.enums.len() as u32),
        ];
        for sec in &l.sections {
            let name = sec.name();
            candidates.push((format!("{name} bytes"), sec.size));
            for width in [
                2u32, 4, 6, 8, 12, 16, 20, 24, 28, 32, 36, 40, 48, 56, 60, 64, 72,
            ] {
                if sec.size % width == 0 {
                    candidates.push((format!("{name}/{width}"), sec.size / width));
                }
            }
        }
        for (i, w) in l.header_words.iter().enumerate() {
            for (name, value) in &candidates {
                if w == value {
                    *matches
                        .entry(i)
                        .or_default()
                        .entry(name.clone())
                        .or_default() += 1;
                }
            }
        }
    }

    println!(
        "{groups} groups
"
    );
    println!("tgly child sections:");
    println!("  magic	groups	non_empty	max_size");
    for (magic, (n, nonempty, max)) in &seen {
        println!("  {magic}	{n}	{nonempty}	{max}");
    }

    println!(
        "
blay preamble words (body 0x0C..0x4C), matches across groups:"
    );
    for i in 0..19 {
        // Only report a candidate that holds for every group.
        let repr = matches
            .get(&i)
            .map(|m| {
                let mut all: Vec<&str> = m
                    .iter()
                    .filter(|(_, v)| **v == groups)
                    .map(|(k, _)| k.as_str())
                    .collect();
                all.sort_unstable();
                if all.is_empty() {
                    format!("(no candidate holds for all {groups})")
                } else {
                    all.join("  ==  ")
                }
            })
            .unwrap_or_else(|| "-".to_string());
        println!("  word {i:>2} (body 0x{:02X})  {repr}", 0x0C + i * 4);
    }
    Ok(())
}

/// Dump a chunk by its packaged path.
///
/// The tag index only tracks `.ubulk` payloads; this reaches anything in the
/// directory index, which is how the `.uasset` package headers are examined.
fn chunk(a: ChunkArgs) -> Result<()> {
    let containers = ue_iostore::load_all(&a.src.paks)?;
    for container in &containers {
        let mut hits: Vec<(&String, &usize)> = container
            .files
            .iter()
            .filter(|(path, _)| path.contains(&a.path))
            .collect();
        hits.sort();
        for (path, index) in hits {
            let entry = &container.chunks[*index];
            let bytes = ue_iostore::read_chunk(container, entry, None, &a.src.oodle_roots())?;
            println!(
                "{}
  {} bytes, chunk id {:#018x} index {} type {} ({})",
                path,
                bytes.len(),
                entry.chunk_id,
                entry.chunk_index,
                entry.chunk_type,
                ue_iostore::chunk_type_name(entry.chunk_type)
            );

            if let Some(want) = a.find_u32 {
                let needle = want.to_le_bytes();
                let at: Vec<usize> = bytes
                    .windows(4)
                    .enumerate()
                    .filter(|(_, w)| *w == needle)
                    .map(|(i, _)| i)
                    .collect();
                println!("  {want} appears at {at:?}");
            }

            let end = a.hexdump.min(bytes.len());
            for off in (0..end).step_by(16) {
                let row = &bytes[off..(off + 16).min(end)];
                let ascii: String = row
                    .iter()
                    .map(|b| {
                        if (32..127).contains(b) {
                            *b as char
                        } else {
                            '.'
                        }
                    })
                    .collect();
                println!("  {off:08x}  {:<47}  |{ascii}|", hex(row));
            }
            println!();
        }
    }
    Ok(())
}

/// Build a container holding one edited tag, to sit alongside the shipped ones.
///
/// Nothing in the game's installation is modified: this writes two new files,
/// and removing them undoes it entirely.
fn pack(a: PackArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let entries = by_group
        .get(a.group.as_str())
        .with_context(|| format!("unknown group {:?}", a.group))?;
    let entry = match &a.tag {
        Some(want) => entries
            .iter()
            .find(|e| e.path.contains(want))
            .copied()
            .with_context(|| format!("no {} tag matching {want:?}", a.group))?,
        None => entries[0],
    };

    let original = idx.read(entry, None, &a.src.oodle_roots())?;
    println!("{}", entry.path);
    println!("  source   {} bytes", original.len());

    // Apply every edit, then re-read the result from scratch so what goes into
    // the container is judged by what the bytes say, not by what we intended.
    let mut file = original.clone();
    for set in &a.sets {
        let (path, value) = set
            .split_once('=')
            .with_context(|| format!("--set takes path=value, got {set:?}"))?;
        let tag = TagFile::parse(&file, Some(file.len()))?;
        let l = tag.layout()?;
        let block = tag.read_data(&l)?;
        let target = blam_tag::patch::resolve(&l, &file, &block, path)?;
        // A section-backed value resizes the tag, so it takes the rebuild path.
        let resizes = target.section.is_some();
        let parsed = match target.type_name.as_str() {
            "string id" => blam_tag::Scalar::Text(value.trim_matches('"').to_string()),
            "tag reference" => parse_reference(value)?,
            _ => blam_tag::value::parse(&l, &target.field, value)?,
        };
        let (out, applied) = if resizes {
            blam_tag::patch::set_text(&l, &file, &block, path, &parsed)?
        } else {
            blam_tag::patch::set(&l, &file, &block, path, &parsed)?
        };
        println!(
            "  edit     {} : {} -> {}",
            applied.path,
            applied.before.display(),
            applied.after.display()
        );
        file = out;
    }

    if file.len() == original.len() {
        let changed = (0..file.len()).filter(|i| file[*i] != original[*i]).count();
        println!("  changed  {changed} byte(s), length unchanged");
    } else {
        println!(
            "  changed  payload {} -> {} bytes",
            original.len(),
            file.len()
        );
    }

    let tag = TagFile::parse(&file, Some(file.len()))?;
    let l = tag.layout()?;
    let block = tag.read_data(&l)?;
    let payload = tag.data().context("patched tag has no bdat section")?;
    if block.consumed != payload.size as usize {
        anyhow::bail!("the patched tag no longer walks exactly");
    }

    // Container construction is shared with the tag editor: blam-pack reuses
    // the shipped chunk IDs and rewrites `BinaryBlobSize` when the payload
    // resized. See that crate for the details this used to spell out inline.
    let source = &idx.containers[entry.container];
    let built = blam_pack::build_override(
        source,
        &a.src.oodle_roots(),
        &[blam_pack::ChunkEdit {
            label: entry.path.clone(),
            chunk: entry.chunk,
            original_len: original.len(),
            patched: file.clone(),
        }],
    )
    .map_err(|e| anyhow::anyhow!(e))?;
    for p in &built.entries {
        println!(
            "  chunk    id {:#018x} index {} type {} (from {}){}",
            p.id.id,
            p.id.index,
            p.id.kind,
            source
                .utoc_path
                .file_name()
                .unwrap_or_default()
                .to_string_lossy(),
            if p.resized {
                " — package BinaryBlobSize rewritten"
            } else {
                ""
            }
        );
    }

    std::fs::create_dir_all(&a.out_dir)?;
    let utoc = a.out_dir.join(format!("{}.utoc", a.name));
    let ucas = a.out_dir.join(format!("{}.ucas", a.name));
    std::fs::write(&utoc, &built.utoc)?;
    std::fs::write(&ucas, &built.ucas)?;

    // Byte-exact read-back first; the field prints below are for the human.
    blam_pack::verify_written(&utoc, &a.src.oodle_roots(), &built.expect)
        .map_err(|e| anyhow::anyhow!(e))?;

    println!("\n  wrote {} ({} bytes)", utoc.display(), built.utoc.len());
    println!("  wrote {} ({} bytes)", ucas.display(), built.ucas.len());

    // Read the container back through the ordinary reader, the same path the
    // game would take, and confirm the edits are visible through it. A
    // container our own reader cannot use is not worth putting in front of the
    // game.
    let check = ue_iostore::load_container(&utoc)?;
    let chunk = check
        .chunks
        .first()
        .context("the container we just wrote has no chunks")?;
    let bytes = ue_iostore::read_chunk(&check, chunk, None, &a.src.oodle_roots())?;
    let tag = TagFile::parse(&bytes, Some(bytes.len()))?;
    let l = tag.layout()?;
    let block = tag.read_data(&l)?;
    let payload = tag.data().context("no bdat section")?;
    println!(
        "\n  verify   read {} bytes back out of the container",
        bytes.len()
    );
    println!(
        "  verify   walks {} of {} bytes",
        block.consumed, payload.size
    );
    for set in &a.sets {
        if let Some((path, _)) = set.split_once('=') {
            let t = blam_tag::patch::resolve(&l, &bytes, &block, path)?;
            println!("  verify   {path} = {}", t.current.display());
        }
    }
    if block.consumed != payload.size as usize {
        anyhow::bail!("the packed tag does not walk exactly");
    }
    println!("\n  This container holds copyrighted game content. Keep it local.");
    println!("  To undo: delete those two files. Nothing else was modified.");
    Ok(())
}

/// Read every `.utoc`, write it back from the parsed structure, and require the
/// bytes to match.
///
/// The first step towards producing a container of our own: a writer that
/// cannot reproduce an existing index has the field layout wrong, and would
/// produce something the game silently refuses.
fn toc_roundtrip(a: SectionsArgs) -> Result<()> {
    let mut paths: Vec<PathBuf> = std::fs::read_dir(&a.src.paks)?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|x| x == "utoc"))
        .collect();
    paths.sort();

    let (mut ok, mut differs) = (0usize, 0usize);
    println!("container	bytes	chunks	blocks	dir_index	result");
    for path in &paths {
        let original = std::fs::read(path)?;
        let name = path.file_name().unwrap_or_default().to_string_lossy();
        let toc = match ue_iostore::toc::Toc::parse(&original) {
            Ok(t) => t,
            Err(e) => {
                println!("{name}	{}	-	-	-	parse failed: {e}", original.len());
                differs += 1;
                continue;
            }
        };
        let written = toc.write();
        let same = written == original;
        if same {
            ok += 1;
        } else {
            differs += 1;
        }
        let first = (0..original.len().min(written.len()))
            .find(|i| original[*i] != written[*i])
            .map(|i| format!("differs at 0x{i:X}"))
            .unwrap_or_else(|| format!("length {} vs {}", original.len(), written.len()));
        println!(
            "{name}	{}	{}	{}	{}	{}",
            original.len(),
            toc.chunk_ids.len(),
            toc.blocks.len(),
            toc.directory_index.len(),
            if same { "identical".to_string() } else { first }
        );
    }
    println!(
        "
{ok}/{} reproduced byte for byte, {differs} differ",
        paths.len()
    );
    if differs > 0 {
        anyhow::bail!("{differs} container index(es) did not round-trip");
    }
    Ok(())
}

/// Change one field and report precisely what that did to the file.
///
/// Nothing is written unless `--out` is given, and the patched bytes are read
/// back and re-walked before anything is reported as a success.
/// Parse `group:path` or `none` into a tag reference.
fn parse_reference(text: &str) -> Result<blam_tag::Scalar> {
    let t = text.trim();
    if t.is_empty() || t.eq_ignore_ascii_case("none") {
        return Ok(blam_tag::Scalar::Reference {
            group: String::new(),
            path: String::new(),
        });
    }
    let (group, path) = t.split_once(':').context(
        r"a tag reference is written as <group>:<path>, e.g. coll:fx\holograms\hologram_01",
    )?;
    Ok(blam_tag::Scalar::Reference {
        group: group.trim().to_string(),
        path: path.trim().to_string(),
    })
}

/// Decode what the live process currently holds for a field.
///
/// The bytes in memory are whatever container won, so the live value is very
/// often not the shipped one. Splicing them into a copy of the file and
/// re-resolving reuses the ordinary decoder instead of duplicating per-type
/// formatting here, so enums, bitfields and bounds print the way they do
/// everywhere else.
fn decode_live(
    file: &[u8],
    span: &std::ops::Range<usize>,
    live: &[u8],
    field: &str,
) -> Option<String> {
    let mut spliced = file.to_vec();
    spliced.get_mut(span.clone())?.copy_from_slice(live);
    let tag = TagFile::parse(&spliced, Some(spliced.len())).ok()?;
    let layout = tag.layout().ok()?;
    let block = tag.read_data(&layout).ok()?;
    Some(
        blam_tag::patch::resolve(&layout, &spliced, &block, field)
            .ok()?
            .current
            .display(),
    )
}

fn poke(a: PokeArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let entries = by_group
        .get(a.group.as_str())
        .with_context(|| format!("unknown group {:?}", a.group))?;
    let entry = match &a.tag {
        Some(want) => entries
            .iter()
            .find(|e| e.path.contains(want))
            .copied()
            .with_context(|| format!("no {} tag matching {want:?}", a.group))?,
        None => entries[0],
    };

    let file = idx.read(entry, None, &a.src.oodle_roots())?;
    let tag = TagFile::parse(&file, Some(entry.chunk.length as usize))?;
    let layout = tag.layout()?;
    let block = tag.read_data(&layout)?;
    let route = blam_tag::patch::route(&layout, &file, &block, &a.field)?;
    let target = &route.target;

    // A section-backed value lives in a trailing section, so changing it moves
    // every byte after it. In a file that is fine — the tag is rebuilt. In a
    // live heap buffer there is nowhere for the extra bytes to go.
    if target.section.is_some() {
        anyhow::bail!(
            "{:?} is a {} stored in a trailing section, so changing it resizes the tag. \
             A live poke can only replace bytes in place — use `set` and rebuild the mod.",
            a.field,
            target.type_name
        );
    }

    let parsed = blam_tag::value::parse(&layout, &target.field, &a.value)?;
    let (patched, applied) = blam_tag::patch::set(&layout, &file, &block, &a.field, &parsed)?;
    let span = target.file_offset..target.file_offset + target.size;
    // Take the whole field from the patched file rather than only the bytes that
    // differ from the shipped one. What is live may already be a modded value,
    // so a diff against the file says nothing about what memory holds.
    let bytes = patched
        .get(span.clone())
        .context("the field lies outside the tag payload")?
        .to_vec();

    let process = match a.pid {
        Some(pid) => blam_live::Process::open(pid)?,
        None => blam_live::Process::attach()?,
    };

    println!("{}", entry.path);
    println!("  field    {}  [{}]", applied.path, applied.type_name);
    println!("  process  pid {}", process.pid);

    // Only the data section is resident in the process — the header and the
    // layout tables are not per-tag — so the locator is pointed at that range.
    let data = tag
        .data()
        .context("this tag has no bdat section to locate")?;
    let data_start = data.content.as_ptr() as usize - file.as_ptr() as usize;
    let region = data_start..data_start + data.content.len();
    // Within it, only the root element keeps its file offsets: the engine
    // resolves every reference in place and moves block elements out, so the
    // tag is found by the root element's scalar fields and a field inside a
    // block is reached through the block's rewritten header.
    let root_off = block.elements.as_ptr() as usize - file.as_ptr() as usize;
    let root = root_off..root_off + block.element_size as usize;
    let stable = blam_tag::view::scalar_mask(&layout, &block, &file);
    let hop = |h: &blam_tag::patch::Hop| blam_live::Hop {
        header: h.header,
        index: h.index,
        element: h.element,
        element_size: h.element_size,
    };
    let blocks: Vec<(blam_live::Hop, u32)> = blam_tag::patch::root_blocks(&layout, &file, &block)
        .iter()
        .filter(|(_, n)| *n > 0)
        .map(|(h, n)| (hop(h), *n))
        .collect();
    let headers: Vec<usize> = blocks.iter().map(|(h, _)| h.header).collect();
    let hops: Vec<blam_live::Hop> = route.hops.iter().map(hop).collect();
    let shape = blam_live::Shape {
        region,
        root,
        stable: &stable,
        headers: &headers,
    };

    let at = blam_live::find(&process, &file, &shape, std::slice::from_ref(&span))?;
    println!(
        "  located  payload at 0x{:X}  ({} independent runs agree, best of {} candidate(s), \
         {:.1} GB scanned)",
        at.base,
        at.agreeing_runs,
        at.candidates,
        at.scanned as f64 / 1e9
    );
    println!(
        "           {:.0}% of the root element's scalar bytes match the file; the engine \
         rewrites the references around them",
        at.match_fraction * 100.0
    );

    let address = if hops.is_empty() {
        at.base + span.start as u64
    } else {
        let arena = blam_live::derive_arena(&process, at.base, &file, &stable, &blocks)
            .context(
                "the field sits inside a block element, which the engine keeps outside the \
                 tag, and the arena those live in could not be worked out from this tag",
            )?;
        blam_live::field_address(&process, at.base, arena, &hops, span.start)?
    };
    println!(
        "  address  0x{address:X}{}",
        if hops.is_empty() {
            String::new()
        } else {
            format!("  (inside a block element, {} hop(s) from the root)", hops.len())
        }
    );

    let live_before = process.read(address, target.size)?;
    let shown = decode_live(&file, &span, &live_before, &a.field);
    println!(
        "  live     {}   (shipped {})",
        shown.as_deref().unwrap_or("<unreadable>"),
        applied.before.display()
    );

    if a.locate_only {
        println!("\n  located only; pass without --locate-only to write");
        return Ok(());
    }

    process.write(address, &bytes)?;
    let read_back = process.read(address, bytes.len())?;
    let after = decode_live(&file, &span, &read_back, &a.field);
    println!("  wrote    {}", applied.after.display());
    println!(
        "  re-read  {}  ({})",
        after.as_deref().unwrap_or("<unreadable>"),
        if read_back == bytes {
            "bytes confirmed in the process"
        } else {
            "MISMATCH — the write did not stick"
        }
    );
    if read_back != bytes {
        anyhow::bail!("the value read back does not match what was written");
    }
    println!(
        "\n  This changed the running game only. Nothing on disk moved, so it is gone at\n  \
         the next launch, and the mod project is untouched."
    );
    Ok(())
}

fn set(a: SetArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let entries = by_group
        .get(a.group.as_str())
        .with_context(|| format!("unknown group {:?}", a.group))?;
    let entry = match &a.tag {
        Some(want) => entries
            .iter()
            .find(|e| e.path.contains(want))
            .copied()
            .with_context(|| format!("no {} tag matching {want:?}", a.group))?,
        None => entries[0],
    };

    let file = idx.read(entry, None, &a.src.oodle_roots())?;
    let tag = TagFile::parse(&file, Some(entry.chunk.length as usize))?;
    let l = tag.layout()?;
    let block = tag.read_data(&l)?;

    let target = blam_tag::patch::resolve(&l, &file, &block, &a.field)?;
    // A section-backed field resizes the tag, so it takes the rebuild path.
    let resizes = target.section.is_some();
    let parsed = match target.type_name.as_str() {
        "tag reference" => parse_reference(&a.value)?,
        "string id" => blam_tag::Scalar::Text(a.value.trim_matches('"').to_string()),
        _ => blam_tag::value::parse(&l, &target.field, &a.value)?,
    };
    let (patched, applied) = if resizes {
        blam_tag::patch::set_text(&l, &file, &block, &a.field, &parsed)?
    } else {
        blam_tag::patch::set(&l, &file, &block, &a.field, &parsed)?
    };

    println!("{}", entry.path);
    println!("  field    {}  [{}]", applied.path, applied.type_name);
    println!("  before   {}", applied.before.display());
    println!("  after    {}", applied.after.display());

    // The whole-file diff is the real claim: an in-place edit must not disturb
    // anything outside the field it names.
    let differing: Vec<usize> = (0..file.len().min(patched.len()))
        .filter(|i| file[*i] != patched[*i])
        .collect();
    if resizes {
        println!(
            "  file     {} bytes -> {} bytes (the value resizes its section)",
            file.len(),
            patched.len()
        );
    } else {
        println!(
            "  file     {} bytes, unchanged length {}",
            file.len(),
            file.len() == patched.len()
        );
    }
    if resizes {
        // A resize moves everything after the section, so a byte range says
        // nothing useful. What matters is that it still reads back correctly.
        let after = TagFile::parse(&patched, Some(patched.len()))?;
        let al = after.layout()?;
        let ab = after.read_data(&al)?;
        let ap = after.data().context("patched tag has no bdat section")?;
        println!(
            "  re-read  {}",
            blam_tag::patch::resolve(&al, &patched, &ab, &a.field)?
                .current
                .display()
        );
        println!("  walk     {} of {} bytes consumed", ab.consumed, ap.size);
        // A rebuild that changes nothing must reproduce the file exactly; that
        // is what shows the difference is the edit and not the rebuild.
        if patched.len() == file.len() {
            let d: Vec<usize> = (0..file.len())
                .filter(|i| file[*i] != patched[*i])
                .collect();
            println!("  differs  {} byte(s) from the original", d.len());
            for i in d.iter().take(8) {
                println!(
                    "           0x{i:X}: {:02x} -> {:02x}",
                    file[*i], patched[*i]
                );
            }
        }
        if ab.consumed != ap.size as usize {
            anyhow::bail!("the patched tag no longer walks exactly");
        }
        match &a.out {
            Some(path) => {
                std::fs::write(path, &patched)?;
                println!(
                    "
  wrote {}",
                    path.display()
                );
                println!(
                    "  This is game content. Keep it local; the repository does not take tag data."
                );
            }
            None => println!(
                "
  dry run; pass --out <file> to write the patched tag"
            ),
        }
        return Ok(());
    }
    match (differing.first(), differing.last()) {
        (Some(first), Some(last)) => {
            println!(
                "  changed  {} byte(s) at 0x{first:X}..=0x{last:X}, inside the field at 0x{:X}..0x{:X}",
                differing.len(),
                target.file_offset,
                target.file_offset + target.size
            );
            let inside = differing
                .iter()
                .all(|i| *i >= target.file_offset && *i < target.file_offset + target.size);
            println!("  contained within the field: {inside}");
            if !inside {
                anyhow::bail!("the edit changed bytes outside the field it names");
            }
        }
        _ => println!("  changed  nothing; the new value encodes to the same bytes"),
    }

    // Re-read the patched tag from scratch, so the report is about the file and
    // not about the in-memory value that produced it.
    let after = TagFile::parse(&patched, Some(patched.len()))?;
    let after_layout = after.layout()?;
    let after_block = after.read_data(&after_layout)?;
    let payload = after.data().context("patched tag has no bdat section")?;
    let walked = after_block.consumed == payload.size as usize;
    let reread = blam_tag::patch::resolve(&after_layout, &patched, &after_block, &a.field)?;
    println!(
        "  re-read  {}  (walk exact: {walked})",
        reread.current.display()
    );
    if !walked {
        anyhow::bail!("the patched tag no longer walks exactly");
    }

    match &a.out {
        Some(path) => {
            std::fs::write(path, &patched)?;
            println!("\n  wrote {}", path.display());
            println!(
                "  This is game content. Keep it local; the repository does not take tag data."
            );
        }
        None => println!("\n  dry run; pass --out <file> to write the patched tag"),
    }
    Ok(())
}

/// Decode every fixed-width field and immediately write the same value back,
/// requiring the bytes to be unchanged.
///
/// This is the property editing rests on. Saving a tag re-encodes every field,
/// not only the edited one, so any type whose decode and encode disagree would
/// quietly corrupt fields the user never touched.
fn recode(a: ValidateArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let oodle = a.src.oodle_roots();
    let by_group = idx.by_group();

    let targets: Vec<&index::TagEntry> = if a.all {
        idx.tags.iter().collect()
    } else {
        by_group.values().map(|v| v[0]).collect()
    };

    let (mut tags, mut checked, mut stable, mut changed, mut skipped) = (0, 0u64, 0u64, 0u64, 0u64);
    let mut offenders: BTreeMap<String, u64> = BTreeMap::new();

    for entry in targets {
        let Ok(buf) = idx.read(entry, None, &oodle) else {
            continue;
        };
        let Ok(tag) = TagFile::parse(&buf, Some(entry.chunk.length as usize)) else {
            continue;
        };
        let Ok(l) = tag.layout() else { continue };
        let Ok(block) = tag.read_data(&l) else {
            continue;
        };
        tags += 1;

        blam_tag::view::visit_fields(&l, &block, &mut |field, bytes| {
            if bytes.is_empty() {
                return;
            }
            checked += 1;
            let decoded = blam_tag::value::read(&l, field, bytes);
            let mut scratch = bytes.to_vec();
            match blam_tag::value::write(&l, field, &decoded, &mut scratch) {
                Ok(()) if scratch == bytes => stable += 1,
                Ok(()) => {
                    changed += 1;
                    *offenders
                        .entry(l.type_name_of(field).to_string())
                        .or_default() += 1;
                    if a.verbose {
                        eprintln!(
                            "{}: {} field {:?} changed on write-back",
                            entry.path,
                            l.type_name_of(field),
                            l.string_at(field.name_offset).unwrap_or("")
                        );
                    }
                }
                // Section-backed and structural types are not written in place.
                Err(_) => skipped += 1,
            }
        });
    }

    println!("checked {tags} tags, {checked} fixed-width fields");
    println!("  unchanged on write-back      {stable}");
    println!("  CHANGED                      {changed}");
    println!("  not editable in place        {skipped}");
    if !offenders.is_empty() {
        println!("\n  types that changed:");
        for (t, n) in &offenders {
            println!("    {t}\t{n}");
        }
    }
    Ok(())
}

/// Print a tag's values as an indented tree. This is the same tree the editor
/// renders, so it doubles as a check on it against real data.
fn values(a: ValuesArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let entries = by_group
        .get(a.group.as_str())
        .with_context(|| format!("unknown group {:?}", a.group))?;
    let entry = match &a.tag {
        Some(want) => entries
            .iter()
            .find(|e| e.path.contains(want))
            .copied()
            .with_context(|| format!("no {} tag matching {want:?}", a.group))?,
        None => entries[0],
    };

    let buf = idx.read(entry, None, &a.src.oodle_roots())?;
    let tag = TagFile::parse(&buf, Some(entry.chunk.length as usize))?;
    let l = tag.layout()?;
    let block = tag
        .read_data(&l)
        .with_context(|| format!("{} values are not readable", entry.path))?;
    let nodes = blam_tag::view::root_capped(&l, &block, build_cap(a.elements));

    println!("{}", entry.path);
    println!(
        "  {} ({}) v{} - {} nodes\n",
        a.group,
        tag.header.group,
        tag.header.group_version,
        nodes.iter().map(|n| n.len()).sum::<usize>()
    );
    for n in &nodes {
        print_node(
            n,
            1,
            &PrintOpts {
                depth: a.depth,
                elements: a.elements,
                all: a.all,
            },
        );
    }
    Ok(())
}

/// Read one scenario's script section, or every scenario's.
///
/// A scenario carries its scripting twice: the original `.hsc` text in `source
/// files`, and the compiled expression tree the game actually runs. This shows
/// both, so the two can be compared.
fn script(a: ScriptArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let entries = by_group
        .get("scenario")
        .context("this install ships no scenario tags")?;
    let oodle = a.src.oodle_roots();

    let selected: Vec<_> = match &a.tag {
        Some(want) => entries.iter().filter(|e| e.path.contains(want)).collect(),
        None => entries.iter().collect(),
    };
    if selected.is_empty() {
        anyhow::bail!("no scenario matching {:?}", a.tag.unwrap_or_default());
    }
    let mut totals = VerifyTotals::default();

    // Which literals are quoted is not in the tag; it comes from the recovered
    // corpus. Without it the decompiler still works, but tag paths come back
    // unquoted, so say so rather than quietly producing source that will not
    // compile.
    let corpus = match blam_hsc::ScriptCorpus::load(&resolve_data_path(&a.corpus)) {
        Ok(corpus) => Some(corpus),
        Err(_) if a.decompile.is_some() || a.verify => {
            eprintln!(
                "note: {} not found; string literals will not be quoted. \
                 Run `mjolnir scripting` to generate it.",
                a.corpus.display()
            );
            None
        }
        Err(_) => None,
    };

    for entry in selected {
        let buf = idx.read(entry, None, &oodle)?;
        let tag = TagFile::parse(&buf, Some(entry.chunk.length as usize))?;
        let l = tag.layout()?;
        let block = tag
            .read_data(&l)
            .with_context(|| format!("{} is not readable", entry.path))?;
        let hs = blam_hsc::read::read(&l, &block, &buf)?;

        // Printing one file's text is the whole output; the summary would only
        // get in the way of piping it.
        if let Some(want) = &a.source {
            let Some(file) = hs.source_files.iter().find(|f| f.name == *want) else {
                continue;
            };
            print!("{}", file.text());
            return Ok(());
        }

        if a.rebuild_check {
            rebuild_check(&hs, corpus.as_ref(), &buf, &entry.path, &mut totals);
            continue;
        }

        if a.rewrite_check {
            // Writing a section that was read and not modified must reproduce
            // the tag exactly. Anything else means the writer is guessing, and
            // an edit built on a guessing writer corrupts whatever it misses.
            let short = entry.path.rsplit('/').next().unwrap_or(&entry.path);
            match blam_hsc::emit::rewrite(&hs, &buf) {
                Ok(out) if out == buf => {
                    println!("{short:<28} identical ({} bytes)", out.len());
                    totals.matched += 1;
                }
                Ok(out) => {
                    let first = (0..out.len().min(buf.len())).find(|i| out[*i] != buf[*i]);
                    println!(
                        "{short:<28} DIFFERS: {} bytes vs {}{}",
                        out.len(),
                        buf.len(),
                        match first {
                            Some(at) => format!(", first at 0x{at:x}"),
                            None => String::new(),
                        }
                    );
                    if let Some(at) = first {
                        let from = at.saturating_sub(16);
                        let to = (at + 16).min(buf.len());
                        println!("    was:  {}", hex(&buf[from..to]));
                        println!("    ours: {}", hex(&out[from..to]));
                    }
                    totals.differs += 1;
                }
                Err(e) => {
                    println!("{short:<28} FAILED: {e}");
                    totals.differs += 1;
                }
            }
            continue;
        }

        if a.recompile {
            recompile_scripts(&hs, corpus.as_ref(), &entry.path, a.show, &mut totals);
            continue;
        }

        if a.verify {
            verify_scripts(&hs, corpus.as_ref(), &entry.path, a.show, &mut totals);
            continue;
        }

        if let Some(want) = &a.decompile {
            let d = match &corpus {
                Some(c) => blam_hsc::Decompiler::with_corpus(&hs, c),
                None => blam_hsc::Decompiler::new(&hs),
            };
            if want.is_empty() {
                print!("{}", d.scenario());
            } else if let Some(s) = hs.scripts.iter().find(|s| s.name == *want) {
                println!("{}", d.script(s));
            } else {
                anyhow::bail!("no script named {want:?} in {}", entry.path);
            }
            return Ok(());
        }

        println!("{}", entry.path);
        let live = hs.live().count();
        println!(
            "  {} scripts, {} globals, {} references",
            hs.scripts.len(),
            hs.globals.len(),
            hs.references.len()
        );
        println!(
            "  {live} live expressions in {} datum slots, {} of string data",
            hs.expressions.len(),
            human_bytes(hs.strings.len())
        );
        println!("  source files");
        for f in &hs.source_files {
            println!(
                "    {:<24} {:>10}  {} lines",
                f.name,
                human_bytes(f.source.len()),
                f.text().lines().count()
            );
        }

        if a.declarations {
            println!("  scripts");
            for s in &hs.scripts {
                let kind = hs.script_types.name_of(s.script_type).unwrap_or("?");
                let ret = hs.value_types.name_of(s.return_type).unwrap_or("?");
                let params: Vec<String> = s
                    .parameters
                    .iter()
                    .map(|p| {
                        format!(
                            "{} {}",
                            hs.value_types.name_of(p.value_type).unwrap_or("?"),
                            p.name
                        )
                    })
                    .collect();
                println!(
                    "    ({kind} {ret} {}{}{})",
                    s.name,
                    if params.is_empty() { "" } else { " " },
                    params.join(", ")
                );
            }
            println!("  globals");
            for g in &hs.globals {
                let ty = hs.value_types.name_of(g.value_type).unwrap_or("?");
                println!("    (global {ty} {})", g.name);
            }
        }
        println!();
    }

    if a.verify || a.recompile || a.rewrite_check || a.rebuild_check {
        println!(
            "total  {} of {} scripts match ({:.1}%), {} desugared cond, {} no source, {} differ",
            totals.matched,
            totals.total(),
            100.0 * totals.matched as f64 / totals.total().max(1) as f64,
            totals.cond,
            totals.no_source,
            totals.differs
        );
        for (kind, n) in &totals.kinds {
            println!("       {n:>5} {kind:?}");
        }
        if totals.compile_warnings > 0 {
            println!(
                "       {} literal(s) the compiler had to guess a type for",
                totals.compile_warnings
            );
        }
        if totals.fixpoint_ok + totals.fixpoint_broken > 0 {
            println!(
                "       {} of {} scenarios recompile their own output to the same tree",
                totals.fixpoint_ok,
                totals.fixpoint_ok + totals.fixpoint_broken
            );
        }
        if totals.fixpoint_broken > 0 {
            anyhow::bail!(
                "{} scenario(s) do not recompile to the same tree",
                totals.fixpoint_broken
            );
        }
        if totals.compile_errors > 0 {
            anyhow::bail!("{} compile error(s)", totals.compile_errors);
        }
        if totals.differs > 0 {
            anyhow::bail!(
                "{} script(s) do not decompile to their source",
                totals.differs
            );
        }
    }
    Ok(())
}

#[derive(Default)]
struct VerifyTotals {
    matched: usize,
    cond: usize,
    no_source: usize,
    differs: usize,
    shown: usize,
    compile_errors: usize,
    compile_warnings: usize,
    fixpoint_ok: usize,
    fixpoint_broken: usize,
    kinds: BTreeMap<hsc::Difference, usize>,
}

impl VerifyTotals {
    fn total(&self) -> usize {
        self.matched + self.cond + self.no_source + self.differs
    }
}

/// Decompile every script in one scenario and grade it against the shipped
/// source.
fn verify_scripts(
    hs: &blam_hsc::ScriptSection,
    corpus: Option<&blam_hsc::ScriptCorpus>,
    path: &str,
    show: usize,
    totals: &mut VerifyTotals,
) {
    use hsc::Verdict;

    let value_types: std::collections::BTreeSet<String> =
        hs.value_types.names().iter().cloned().collect();

    // A scenario's source files are separate compilation units, but a script is
    // defined in exactly one of them, so one merged lookup is enough.
    let mut blocks = BTreeMap::new();
    for f in &hs.source_files {
        blocks.extend(hsc::script_blocks(&f.text(), &value_types));
    }

    let d = match corpus {
        Some(c) => blam_hsc::Decompiler::with_corpus(hs, c),
        None => blam_hsc::Decompiler::new(hs),
    };
    let (mut matched, mut cond, mut no_source, mut differs) = (0, 0, 0, 0);

    for s in &hs.scripts {
        match hsc::compare(blocks.get(&s.name), &d.script(s), &value_types) {
            Verdict::Match => matched += 1,
            Verdict::DesugaredCond => cond += 1,
            Verdict::NoSource => no_source += 1,
            Verdict::Differs {
                at,
                kind,
                source,
                ours,
            } => {
                differs += 1;
                *totals.kinds.entry(kind).or_default() += 1;
                if totals.shown < show {
                    totals.shown += 1;
                    println!("  {} differs at token {at} ({kind:?})", s.name);
                    println!("    source: {source}");
                    println!("    ours:   {ours}");
                }
            }
        }
    }

    let total = matched + cond + no_source + differs;
    println!(
        "{:<28} {matched}/{total} match, {cond} cond, {no_source} no source, {differs} differ",
        path.rsplit('/').next().unwrap_or(path)
    );
    totals.matched += matched;
    totals.cond += cond;
    totals.no_source += no_source;
    totals.differs += differs;
}

/// Compile a scenario's own source and write the result back into the tag.
///
/// The end-to-end check: every earlier one stops at the expression tree, and
/// this is what says the tree can be put back into a scenario the game's own
/// reader still accepts. The rebuilt tag is re-read from scratch and its script
/// section compared against what went in.
fn rebuild_check(
    hs: &blam_hsc::ScriptSection,
    corpus: Option<&blam_hsc::ScriptCorpus>,
    file: &[u8],
    path: &str,
    totals: &mut VerifyTotals,
) {
    let short = path.rsplit('/').next().unwrap_or(path);
    let Some(corpus) = corpus else {
        println!("{short:<28} skipped: no scripting corpus");
        return;
    };

    let texts: Vec<(String, String)> = hs
        .source_files
        .iter()
        .map(|f| (f.name.clone(), f.text().into_owned()))
        .collect();
    let files: Vec<(&str, &str)> = texts
        .iter()
        .map(|(n, t)| (n.as_str(), t.as_str()))
        .collect();

    let compiled = blam_hsc::Compiler::from_corpus(corpus).compile(&files);
    if !compiled.ok() {
        println!(
            "{short:<28} FAILED to compile: {}",
            compiled.errors().count()
        );
        totals.differs += 1;
        return;
    }

    let mut section = compiled.section;
    section.shapes = hs.shapes;
    section.source_files = hs.source_files.clone();

    let rebuilt = match blam_hsc::emit::rewrite(&section, file) {
        Ok(b) => b,
        Err(e) => {
            println!("{short:<28} FAILED to write: {e}");
            totals.differs += 1;
            return;
        }
    };

    // Read it back the way the editor and the game would, from nothing but the
    // bytes.
    let reread = (|| -> anyhow::Result<blam_hsc::ScriptSection> {
        let tag = TagFile::parse(&rebuilt, Some(rebuilt.len()))?;
        let l = tag.layout()?;
        let block = tag.read_data(&l)?;
        let expected = tag
            .data()
            .map(|d| d.size as usize)
            .unwrap_or(block.consumed);
        anyhow::ensure!(
            block.consumed == expected,
            "the rebuilt tag does not walk exactly: {} consumed of {expected}",
            block.consumed
        );
        Ok(blam_hsc::read::read(&l, &block, &rebuilt)?)
    })();

    match reread {
        Err(e) => {
            println!("{short:<28} FAILED to read back: {e}");
            totals.differs += 1;
        }
        Ok(back) => {
            let same = back.scripts.len() == section.scripts.len()
                && back.globals.len() == section.globals.len()
                && back.live().count() == section.live().count()
                && back.source_files.len() == section.source_files.len();
            if same {
                println!(
                    "{short:<28} rebuilt ok: {} scripts, {} globals, {} expressions, {} bytes ({:+})",
                    back.scripts.len(),
                    back.globals.len(),
                    back.live().count(),
                    rebuilt.len(),
                    rebuilt.len() as i64 - file.len() as i64
                );
                totals.matched += 1;
            } else {
                println!(
                    "{short:<28} DIFFERS after reading back: {} scripts vs {}, {} expressions vs {}",
                    back.scripts.len(),
                    section.scripts.len(),
                    back.live().count(),
                    section.live().count()
                );
                totals.differs += 1;
            }
        }
    }
}

/// Compile a scenario's own source back into a tree, then decompile that and
/// check each script survived the trip.
///
/// This is the compiler's acceptance test and it is deliberately end-to-end.
/// The output tree is not byte-identical to the shipped one — generations, free slots
/// and string-blob layout are the compiler's own — so what is checked is that
/// the *meaning* survives: compile, decompile, and compare tokens against the
/// source that went in.
fn recompile_scripts(
    hs: &blam_hsc::ScriptSection,
    corpus: Option<&blam_hsc::ScriptCorpus>,
    path: &str,
    show: usize,
    totals: &mut VerifyTotals,
) {
    use hsc::Verdict;

    let short = path.rsplit('/').next().unwrap_or(path);
    let Some(corpus) = corpus else {
        println!("{short:<28} skipped: no scripting corpus to compile against");
        return;
    };

    // Every file at once: the scenario's sources are one compilation unit as
    // far as name resolution goes, and scripts routinely call across files.
    let texts: Vec<(String, String)> = hs
        .source_files
        .iter()
        .map(|f| (f.name.clone(), f.text().into_owned()))
        .collect();
    let files: Vec<(&str, &str)> = texts
        .iter()
        .map(|(n, t)| (n.as_str(), t.as_str()))
        .collect();

    let compiled = blam_hsc::Compiler::from_corpus(corpus).compile(&files);
    let errors: Vec<_> = compiled.errors().collect();
    if !errors.is_empty() {
        println!("{short:<28} {} compile error(s)", errors.len());
        for e in errors.iter().take(show) {
            println!("    {e}");
        }
        totals.compile_errors += errors.len();
    }
    totals.compile_warnings += compiled.diagnostics.len() - errors.len();

    // Grade against the source that went in, the same way `--verify` grades the
    // shipped tree, so the two numbers are comparable.
    let value_types: std::collections::BTreeSet<String> =
        hs.value_types.names().iter().cloned().collect();
    let mut blocks = BTreeMap::new();
    for f in &hs.source_files {
        blocks.extend(hsc::script_blocks(&f.text(), &value_types));
    }

    let d = blam_hsc::Decompiler::with_corpus(&compiled.section, corpus);
    let (mut matched, mut cond, mut no_source, mut differs) = (0, 0, 0, 0);
    for s in &compiled.section.scripts {
        match hsc::compare(blocks.get(&s.name), &d.script(s), &value_types) {
            Verdict::Match => matched += 1,
            Verdict::DesugaredCond => cond += 1,
            Verdict::NoSource => no_source += 1,
            Verdict::Differs {
                at,
                kind,
                source,
                ours,
            } => {
                differs += 1;
                *totals.kinds.entry(kind).or_default() += 1;
                if totals.shown < show {
                    totals.shown += 1;
                    println!("  {} differs at token {at} ({kind:?})", s.name);
                    println!("    source: {source}");
                    println!("    ours:   {ours}");
                }
            }
        }
    }

    // Compiling the decompiled output again must produce the same tree.
    //
    // The token comparison above cannot separate a compiler bug from the
    // decompiler rendering a literal differently — most of what it reports is
    // the known quoting classification, which is a rendering question. This
    // does: the tree is the compiler's own output either way, so any difference
    // is the compiler's.
    let second =
        blam_hsc::Compiler::from_corpus(corpus).compile(&[("<decompiled>", &d.scenario())]);
    match tree_difference(&compiled.section, &second.section) {
        None => totals.fixpoint_ok += 1,
        Some(why) => {
            totals.fixpoint_broken += 1;
            println!("  {short}: recompiling its own output changed the tree — {why}");
        }
    }

    let total = matched + cond + no_source + differs;
    println!(
        "{short:<28} {matched}/{total} match, {cond} cond, {no_source} no source, {differs} differ"
    );
    totals.matched += matched;
    totals.cond += cond;
    totals.no_source += no_source;
    totals.differs += differs;
}

/// The first way two compiled trees differ, or `None` if they agree.
///
/// Compares what the engine reads — shape, opcodes, types and strings — not the
/// raw bytes, because a string offset is only meaningful against its own blob.
fn tree_difference(a: &blam_hsc::ScriptSection, b: &blam_hsc::ScriptSection) -> Option<String> {
    if a.scripts.len() != b.scripts.len() {
        return Some(format!(
            "{} scripts became {}",
            a.scripts.len(),
            b.scripts.len()
        ));
    }
    if a.globals.len() != b.globals.len() {
        return Some(format!(
            "{} globals became {}",
            a.globals.len(),
            b.globals.len()
        ));
    }
    let (live_a, live_b) = (a.live().count(), b.live().count());
    if live_a != live_b {
        return Some(format!("{live_a} expressions became {live_b}"));
    }

    // Walk each declaration's tree from its root rather than comparing the
    // arrays position by position: the decompiler writes globals before
    // scripts, so the same tree lands at different indices the second time
    // round. What has to match is the shape reachable from each root.
    for (x, y) in a.scripts.iter().zip(&b.scripts) {
        if x.name != y.name || x.script_type != y.script_type || x.return_type != y.return_type {
            return Some(format!("script `{}` changed shape", x.name));
        }
        if x.parameters != y.parameters {
            return Some(format!("script `{}` changed its parameters", x.name));
        }
        if let Some(why) = walk_difference(a, x.root, b, y.root, &x.name, 0) {
            return Some(why);
        }
    }
    for (x, y) in a.globals.iter().zip(&b.globals) {
        if x.name != y.name || x.value_type != y.value_type {
            return Some(format!("global `{}` changed shape", x.name));
        }
        if let Some(why) = walk_difference(a, x.initializer, b, y.initializer, &x.name, 0) {
            return Some(why);
        }
    }
    None
}

/// Compare two subtrees node for node, in traversal order.
fn walk_difference(
    a: &blam_hsc::ScriptSection,
    ha: blam_hsc::DatumHandle,
    b: &blam_hsc::ScriptSection,
    hb: blam_hsc::DatumHandle,
    what: &str,
    depth: u32,
) -> Option<String> {
    if depth > 128 {
        return None;
    }
    let (ea, eb) = (a.get(ha), b.get(hb));
    let (ea, eb) = match (ea, eb) {
        (None, None) => return None,
        (Some(ea), Some(eb)) => (ea, eb),
        _ => {
            return Some(format!(
                "`{what}`: one side has a node where the other has none"
            ))
        }
    };

    if ea.expression_type != eb.expression_type
        || ea.opcode != eb.opcode
        || ea.value_type != eb.value_type
    {
        return Some(format!(
            "`{what}`: {:?}/{:#x}/{} became {:?}/{:#x}/{}",
            ea.expression_type,
            ea.opcode,
            ea.value_type,
            eb.expression_type,
            eb.opcode,
            eb.value_type
        ));
    }
    if a.string_at(ea.string_offset) != b.string_at(eb.string_offset) {
        return Some(format!(
            "`{what}`: {:?} became {:?}",
            a.string_at(ea.string_offset),
            b.string_at(eb.string_offset)
        ));
    }
    // A call's `data` is a handle into its own array, so only a literal's
    // payload can be compared directly.
    if !ea.expression_type.has_children() && ea.data != eb.data {
        return Some(format!("`{what}`: {:#x} became {:#x}", ea.data, eb.data));
    }

    let (args_a, args_b) = (a.arguments(ea), b.arguments(eb));
    if args_a.len() != args_b.len() {
        return Some(format!(
            "`{what}`: a call with {} children became one with {}",
            args_a.len(),
            args_b.len()
        ));
    }
    for (ca, cb) in args_a.into_iter().zip(args_b) {
        if let Some(why) = walk_difference(a, ca, b, cb, what, depth + 1) {
            return Some(why);
        }
    }
    None
}

/// Compile `.hsc` files from disk.
///
/// Needs no game installation: the function table and both enums come from the
/// committed corpus, so a mod author can check a script without one.
fn compile(a: CompileArgs) -> Result<()> {
    let corpus = blam_hsc::ScriptCorpus::load(&resolve_data_path(&a.corpus)).with_context(|| {
        format!(
            "cannot read {}. Run `mjolnir scripting` against an installed game to generate it.",
            a.corpus.display()
        )
    })?;

    let mut sources = Vec::new();
    for path in &a.files {
        let text = std::fs::read_to_string(path)
            .with_context(|| format!("cannot read {}", path.display()))?;
        let name = path
            .file_stem()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_else(|| path.display().to_string());
        sources.push((name, text));
    }
    let files: Vec<(&str, &str)> = sources
        .iter()
        .map(|(n, t)| (n.as_str(), t.as_str()))
        .collect();

    let compiled = blam_hsc::Compiler::from_corpus(&corpus).compile(&files);
    for d in &compiled.diagnostics {
        eprintln!("{d}");
    }

    let warnings = compiled.diagnostics.len() - compiled.errors().count();
    println!(
        "  {} script(s), {} global(s), {} expression(s), {} of strings",
        compiled.section.scripts.len(),
        compiled.section.globals.len(),
        compiled.section.live().count(),
        human_bytes(compiled.section.strings.len())
    );
    println!(
        "  {} error(s), {warnings} warning(s)",
        compiled.errors().count()
    );

    if a.show {
        println!();
        print!(
            "{}",
            blam_hsc::Decompiler::with_corpus(&compiled.section, &corpus).scenario()
        );
    }

    if !compiled.ok() {
        anyhow::bail!("compilation failed");
    }
    Ok(())
}

/// Recover the scripting function table from every shipped scenario.
///
/// The opcode table is not in the definitions the way field names are: an
/// opcode is only a number until something names it. Every compiled call
/// carries that name on the child node that names its callee, so reading all
/// thirteen scenarios recovers the table without touching the engine binary.
fn scripting(a: ScriptingArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let entries = by_group
        .get("scenario")
        .context("this install ships no scenario tags")?;
    let oodle = a.src.oodle_roots();

    let mut builder = blam_hsc::CorpusBuilder::new();
    for entry in entries {
        let buf = idx.read(entry, None, &oodle)?;
        let tag = TagFile::parse(&buf, Some(entry.chunk.length as usize))?;
        let l = tag.layout()?;
        let block = tag
            .read_data(&l)
            .with_context(|| format!("{} is not readable", entry.path))?;
        builder.observe(&blam_hsc::read::read(&l, &block, &buf)?);
    }

    // An opcode seen under two names would mean the recovery rule is wrong, so
    // it stops the export rather than being averaged away.
    let conflicts = builder.conflicts();
    if !conflicts.is_empty() {
        for c in &conflicts {
            eprintln!("  opcode 0x{:04x} names: {}", c.opcode, c.names.join(", "));
        }
        anyhow::bail!(
            "{} opcode(s) resolved to more than one name; the table is not trustworthy",
            conflicts.len()
        );
    }

    let scenarios = builder.scenarios();
    let corpus = builder.finish_at(
        format!("mjolnir {}", env!("CARGO_PKG_VERSION")),
        a.build,
        a.quoted_threshold,
    );

    let thin = corpus.thinly_attested();
    let variadic = corpus
        .functions
        .values()
        .filter(|f| f.is_variadic())
        .count();
    let calls: u32 = corpus.functions.values().map(|f| f.call_sites).sum();

    println!("  scenarios read  {scenarios}");
    println!("  opcodes         {}", corpus.functions.len());
    println!("  call sites      {calls}");
    println!("  variadic        {variadic}");
    println!(
        "  thinly attested {} (fewer than {} call sites)",
        thin.len(),
        blam_hsc::corpus::WELL_ATTESTED
    );
    println!("  value types     {}", corpus.value_types.len());

    if a.dry_run {
        println!("\ndry run: nothing written");
        return Ok(());
    }

    corpus.save(&a.out)?;
    let bytes = std::fs::metadata(&a.out).map(|m| m.len()).unwrap_or(0);
    println!(
        "\nwrote {} ({:.1} KiB)",
        a.out.display(),
        bytes as f64 / 1024.0
    );
    Ok(())
}

fn human_bytes(n: usize) -> String {
    if n < 1024 {
        format!("{n} B")
    } else {
        format!("{:.1} KiB", n as f64 / 1024.0)
    }
}

/// How much of a tag's value tree to print.
///
/// Split out from `ValuesArgs` so the same printer serves both the paks-backed
/// inspector and the file-backed one.
struct PrintOpts {
    depth: u32,
    elements: usize,
    all: bool,
}

/// How many elements per block to materialise so `--elements n` can print `n`.
///
/// The printer can only show what the tree holds, so a cap below `--elements`
/// silently truncates the listing. The default cap is still the floor: it keeps
/// the node totals `values` prints stable for the common case, and asking for
/// fewer elements is a display choice, not a reason to build a smaller tree.
fn build_cap(elements: usize) -> usize {
    elements.max(blam_tag::view::DEFAULT_MAX_ELEMENTS)
}

/// The `[n element(s) of max]` summary for a block.
///
/// The count is [`blam_tag::view::Node::count`] — what the tag holds — not
/// `children.len()`, which is only what the walk materialised. Reading the
/// latter made every `unic` tag report exactly 64 string references, the
/// per-block build cap, in place of the hundreds actually there.
///
/// `shown` is how many elements the printer is about to list, or `None` when it
/// lists none because the depth limit stops here.
fn block_summary(node: &blam_tag::view::Node, shown: Option<usize>) -> String {
    let total = node.count.map(|c| c as usize).unwrap_or(node.children.len());
    let limit = node
        .max_count
        .map(|m| format!(" of {m}"))
        .unwrap_or_default();
    let cut = match shown {
        Some(n) if n < total => format!(", showing {n}"),
        _ => String::new(),
    };
    format!("[{total} element(s){limit}{cut}]")
}

fn print_node(node: &blam_tag::view::Node, depth: u32, a: &PrintOpts) {
    use blam_tag::view::Kind;

    if depth > a.depth + 1 {
        return;
    }
    let indent = "  ".repeat(depth as usize);
    let name = if node.name.is_empty() {
        "<unnamed>"
    } else {
        &node.name
    };

    // Children are printed one level down, which the depth limit may cut off.
    let lists_children = depth < a.depth + 1;

    match node.kind {
        Kind::Block => {
            let shown = lists_children.then(|| node.children.len().min(a.elements));
            println!(
                "{indent}{name}  {}  {}",
                block_summary(node, shown),
                node.block_name.as_deref().unwrap_or("")
            );
        }
        Kind::Array => println!(
            "{indent}{name}  [array of {}]",
            node.count.map(|c| c as usize).unwrap_or(node.children.len())
        ),
        Kind::Element => println!("{indent}{name}"),
        Kind::Struct => println!("{indent}{name}  ({})", node.type_name),
        Kind::Field => {
            let shown = node.value.display();
            if shown.is_empty() && !a.all {
                return;
            }
            println!("{indent}{name} = {shown}    [{}]", node.type_name);
        }
    }

    let limit = if matches!(node.kind, Kind::Block | Kind::Array) {
        a.elements
    } else {
        usize::MAX
    };
    for child in node.children.iter().take(limit) {
        print_node(child, depth + 1, a);
    }
    // What is left unprinted is measured against the real count, so elements
    // the build cap never materialised are counted too.
    let total = node.count.map(|c| c as usize).unwrap_or(node.children.len());
    if lists_children && total > limit {
        println!("{indent}  ... {} more", total - limit);
    }
}

fn export_defs(a: DefsArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let oodle = a.src.oodle_roots();

    let mut corpus = blam_defs::DefCorpus {
        generator: format!("mjolnir {}", env!("CARGO_PKG_VERSION")),
        build: a.build,
        groups: BTreeMap::new(),
    };

    for (group, entries) in &by_group {
        let buf = idx.read(entries[0], None, &oodle)?;
        let tag = TagFile::parse(&buf, Some(entries[0].chunk.length as usize))?;
        let l = tag.layout()?;
        let def = defs::build_group(
            group,
            &tag.header.group.as_str(),
            tag.header.group_version,
            entries.len(),
            &l,
        );
        corpus.groups.insert(group.to_string(), def);
    }

    corpus.save(&a.out)?;

    let total_fields: usize = corpus.groups.values().map(|g| g.field_count()).sum();
    let visible: usize = corpus
        .groups
        .values()
        .map(|g| g.visible_field_count())
        .sum();
    let resolved = corpus
        .groups
        .values()
        .filter(|g| (g.coverage() - 1.0).abs() < f32::EPSILON)
        .count();
    let bytes = std::fs::metadata(&a.out).map(|m| m.len()).unwrap_or(0);

    println!("wrote {}", a.out.display());
    println!("  groups          {}", corpus.groups.len());
    println!(
        "  structs         {}",
        corpus
            .groups
            .values()
            .map(|g| g.structs.len())
            .sum::<usize>()
    );
    println!("  fields          {total_fields} ({visible} visible)");
    println!("  fully resolved  {resolved}/{}", corpus.groups.len());
    println!("  size            {:.1} KiB", bytes as f64 / 1024.0);
    Ok(())
}

fn groups(a: GroupsArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    println!(
        "group\tfourcc\tver\tcount\tstrings\toptions\ttypes\tfields\tblocks\tstructs\tdata\troot"
    );

    let mut parsed = 0usize;
    let mut with_fields = 0usize;
    for (group, entries) in &by_group {
        let first = entries[0];
        let buf = idx.read(first, None, &a.src.oodle_roots())?;
        let tag = match TagFile::parse(&buf, Some(first.chunk.length as usize)) {
            Ok(t) => t,
            Err(e) => {
                eprintln!("{group}: header parse failed: {e}");
                continue;
            }
        };
        let l = match tag.layout() {
            Ok(l) => l,
            Err(e) => {
                eprintln!("{group}: layout parse failed: {e}");
                continue;
            }
        };
        parsed += 1;
        if !l.fields.is_empty() {
            with_fields += 1;
        }
        let data = tag.data().map(|d| d.size).unwrap_or(0);
        let root = l
            .root_struct()
            .and_then(|r| l.struct_size(r))
            .map(|s| s.to_string())
            .unwrap_or_else(|| "?".to_string());
        println!(
            "{group}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{data}\t{root}",
            tag.header.group,
            tag.header.group_version,
            entries.len(),
            l.strings().len(),
            l.option_offsets.len(),
            l.types.len(),
            l.fields.len(),
            l.blocks.len(),
            l.structs.len(),
        );
    }
    println!(
        "\n{parsed}/{} groups parsed, {with_fields} with a field list, {} payloads",
        by_group.len(),
        idx.tags.len()
    );
    Ok(())
}

fn list(a: ListArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let mut shown = 0;
    for t in &idx.tags {
        if let Some(g) = &a.group {
            if &t.group != g {
                continue;
            }
        }
        println!("{}\t{}\t{}", t.group, t.chunk.length, t.path);
        shown += 1;
        if shown >= a.limit {
            break;
        }
    }
    Ok(())
}

/// Read one group's first tag and hand it to `f` as a parsed layout.
fn with_group<T>(
    src: &Source,
    group: &str,
    f: impl FnOnce(&blam_tag::TagFile<'_>, &blam_tag::Layout<'_>) -> T,
) -> Result<T> {
    let idx = index::build(&src.paks)?;
    let by_group = idx.by_group();
    let entries = by_group
        .get(group)
        .with_context(|| format!("unknown group {group:?}"))?;
    let entry = entries[0];
    let buf = idx.read(entry, None, &src.oodle_roots())?;
    let tag = TagFile::parse(&buf, Some(entry.chunk.length as usize))?;
    let l = tag.layout()?;
    Ok(f(&tag, &l))
}

fn layout(a: LayoutArgs) -> Result<()> {
    with_group(&a.src, &a.group, |tag, l| {
        println!(
            "{} ({}) v{}",
            a.group, tag.header.group, tag.header.group_version
        );
        println!("  blay v{} size {}", l.version, l.size);
        println!("  strings   {}", l.strings().len());
        println!("  options   {}", l.option_offsets.len());
        println!("  types     {}", l.types.len());
        println!("  fields    {}", l.fields.len());
        println!("  blocks    {}", l.blocks.len());
        println!("  structs   {}", l.structs.len());
        if let Some(d) = tag.data() {
            println!("  data      {} bytes (tgbl)", d.size);
        }
        println!("  flat size {:?}", l.flat_size());

        println!("\n  section chain under tgly:");
        for s in &l.sections {
            println!(
                "    +{:<8} {}  v{:<3} size {}",
                s.at,
                s.name(),
                s.version,
                s.size
            );
        }

        if a.tables {
            println!("\n  types:");
            for (i, t) in l.types.iter().enumerate() {
                println!(
                    "    [{i:>3}] size {:>5}  flags {:>3}  {}",
                    t.size,
                    t.flags,
                    l.string_at(t.name_offset).unwrap_or("")
                );
            }
            println!("\n  blocks:");
            for (i, b) in l.blocks.iter().enumerate() {
                println!(
                    "    [{i:>3}] max {:>6}  aux {:>6}  {}",
                    b.max_count,
                    b.aux,
                    l.string_at(b.name_offset).unwrap_or("")
                );
            }
            println!("\n  structs:");
            let ranges = l.struct_ranges();
            for (i, s) in l.structs.iter().enumerate() {
                let guid: String = s.guid.iter().map(|b| format!("{b:02x}")).collect();
                let span = l
                    .struct_run(i)
                    .and_then(|r| ranges.get(r))
                    .map(|r| format!("{}..{}", r.start, r.end))
                    .unwrap_or_else(|| "?".into());
                println!(
                    "    [{i:>3}] first_field {:>5}  fields {span:<14} {guid}  {}",
                    s.first_field,
                    l.string_at(s.name_offset).unwrap_or("")
                );
            }
        }

        if a.options {
            println!("\n  options:");
            for (i, o) in l.options().iter().enumerate() {
                println!("    [{i:>4}] {o}");
            }
        }

        if let Some(want) = &a.section {
            match l.sections.iter().find(|s| s.name() == *want) {
                Some(s) => {
                    println!("\n  section {want} v{} size {}:", s.version, s.size);
                    for (i, c) in s.content.chunks_exact(4).enumerate() {
                        let v = u32::from_le_bytes(c.try_into().unwrap());
                        let note = match l.string_at(v) {
                            Some(t) if !t.is_empty() => format!("  -> {t:?}"),
                            _ => String::new(),
                        };
                        println!("    [{i:>4}] {v:>10}{note}");
                    }
                }
                None => println!("\n  no section named {want}"),
            }
        }
    })
}

fn fields(a: FieldsArgs) -> Result<()> {
    with_group(&a.src, &a.group, |_tag, l| {
        println!("{}: {} fields", a.group, l.fields.len());
        let mut offset = 0u32;
        for (i, f) in l.fields.iter().take(a.limit).enumerate() {
            let (name, type_name, size) = l.field_info(f);
            let shown = if name.is_empty() { "<unnamed>" } else { name };
            match size {
                Some(sz) => {
                    println!(
                        "  [{i:>4}] +{offset:<6} {sz:>4}b  aux {:>8}  {type_name:<28} {shown}",
                        f.aux
                    );
                    offset += sz;
                }
                None => println!(
                    "  [{i:>4}] +{offset:<6}    ?b  aux {:>8}  <type {}>  {shown}",
                    f.aux, f.type_index
                ),
            }
        }
    })
}

fn types(a: TypesArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let oodle = a.src.oodle_roots();

    // type name -> observed sizes -> count
    let mut sizes: BTreeMap<String, BTreeMap<u32, usize>> = BTreeMap::new();
    let mut examples: BTreeMap<String, Vec<String>> = BTreeMap::new();

    for (group, entries) in &by_group {
        let Ok(buf) = idx.read(entries[0], None, &oodle) else {
            continue;
        };
        let Ok(tag) = TagFile::parse(&buf, Some(entries[0].chunk.length as usize)) else {
            continue;
        };
        let Ok(l) = tag.layout() else { continue };

        for t in &l.types {
            let Some(name) = l.string_at(t.name_offset) else {
                continue;
            };
            if name.is_empty() {
                continue;
            }
            *sizes
                .entry(name.to_string())
                .or_default()
                .entry(t.size)
                .or_default() += 1;
            let ex = examples.entry(name.to_string()).or_default();
            if ex.len() < a.examples && !ex.iter().any(|e| e == group) {
                ex.push(group.to_string());
            }
        }
    }

    println!("type\tsize\tgroups\tconsistent\tseen_in");
    let mut inconsistent = 0usize;
    for (name, observed) in &sizes {
        let total: usize = observed.values().sum();
        let consistent = observed.len() == 1;
        if !consistent {
            inconsistent += 1;
        }
        let size_repr = observed
            .iter()
            .map(|(s, n)| {
                if consistent {
                    s.to_string()
                } else {
                    format!("{s}:{n}")
                }
            })
            .collect::<Vec<_>>()
            .join(" ");
        println!(
            "{name}\t{size_repr}\t{total}\t{consistent}\t{}",
            examples.get(name).map(|e| e.join(", ")).unwrap_or_default()
        );
    }
    println!(
        "\n{} distinct type names, {inconsistent} with an inconsistent size",
        sizes.len()
    );
    Ok(())
}

fn aux(a: AuxArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let oodle = a.src.oodle_roots();

    // type name -> aux value -> count
    let mut hist: BTreeMap<String, BTreeMap<u32, usize>> = BTreeMap::new();

    for entries in by_group.values() {
        let Ok(buf) = idx.read(entries[0], None, &oodle) else {
            continue;
        };
        let Ok(tag) = TagFile::parse(&buf, Some(entries[0].chunk.length as usize)) else {
            continue;
        };
        let Ok(l) = tag.layout() else { continue };

        for f in &l.fields {
            let (_, type_name, _) = l.field_info(f);
            if type_name.is_empty() {
                continue;
            }
            if let Some(want) = &a.type_name {
                if type_name != want {
                    continue;
                }
            }
            *hist
                .entry(type_name.to_string())
                .or_default()
                .entry(f.aux)
                .or_default() += 1;
        }
    }

    println!("type\tfields\tdistinct_aux\tmin\tmax\tall_zero\tsample");
    for (name, values) in &hist {
        let total: usize = values.values().sum();
        let min = values.keys().next().copied().unwrap_or(0);
        let max = values.keys().next_back().copied().unwrap_or(0);
        let all_zero = values.len() == 1 && min == 0;
        let sample = values
            .iter()
            .take(8)
            .map(|(v, n)| format!("{v}x{n}"))
            .collect::<Vec<_>>()
            .join(" ");
        println!(
            "{name}\t{total}\t{}\t{min}\t{max}\t{all_zero}\t{sample}",
            values.len()
        );
    }
    Ok(())
}

/// Structural invariants the recovered model must satisfy.
#[derive(Default)]
struct Checks {
    tags: usize,
    parsed: usize,
    header_failed: usize,
    layout_failed: usize,
    /// One `terminator X` per entry in the struct table.
    struct_count_matches: usize,
    struct_count_mismatched: usize,
    /// Every field's type index is inside the type table.
    type_index_ok: usize,
    type_index_bad: usize,
    /// Every block field's aux indexes the block table.
    block_aux_ok: usize,
    block_aux_bad: usize,
    /// Every struct field's aux indexes a struct field run.
    struct_aux_ok: usize,
    struct_aux_bad: usize,
    /// Every array field resolves to an in-range element struct.
    array_aux_ok: usize,
    array_aux_bad: usize,
    /// The root struct size resolves to a concrete number.
    root_size_ok: usize,
    root_size_unknown: usize,
    /// A bdat data section is present.
    has_data: usize,
    /// Every `blay` preamble count matches the table it counts.
    preamble_ok: usize,
    preamble_bad: usize,
    /// Every `*_block_index` field's aux indexes the block table.
    block_index_ok: usize,
    block_index_bad: usize,
    /// Every `stv4` entry's `first_field` lands on a field run start.
    struct_first_field_ok: usize,
    struct_first_field_bad: usize,
    /// The data walk succeeded.
    data_walk_ok: usize,
    data_walk_failed: usize,
    /// The data walk consumed the payload exactly.
    data_exact: usize,
    data_short: usize,
    data_over: usize,
}

fn validate(a: ValidateArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let oodle = a.src.oodle_roots();
    let by_group = idx.by_group();

    let targets: Vec<&index::TagEntry> = if a.all {
        idx.tags.iter().collect()
    } else {
        by_group.values().map(|v| v[0]).collect()
    };

    let mut c = Checks::default();
    for entry in targets {
        c.tags += 1;
        let buf = match idx.read(entry, None, &oodle) {
            Ok(buf) => buf,
            Err(e) => {
                c.header_failed += 1;
                if a.verbose {
                    eprintln!("{}: {e:#}", entry.path);
                }
                continue;
            }
        };
        let tag = match TagFile::parse(&buf, Some(entry.chunk.length as usize)) {
            Ok(t) => t,
            Err(e) => {
                c.header_failed += 1;
                if a.verbose {
                    eprintln!("{}: {e}", entry.path);
                }
                continue;
            }
        };
        let l = match tag.layout() {
            Ok(l) => l,
            Err(e) => {
                c.layout_failed += 1;
                if a.verbose {
                    eprintln!("{}: {e}", entry.path);
                }
                continue;
            }
        };
        c.parsed += 1;

        let ranges = l.struct_ranges();
        if ranges.len() == l.structs.len() {
            c.struct_count_matches += 1;
        } else {
            c.struct_count_mismatched += 1;
            if a.verbose {
                eprintln!(
                    "{}: {} terminators vs {} struct entries",
                    entry.path,
                    ranges.len(),
                    l.structs.len()
                );
            }
        }

        let preamble: Vec<_> = l
            .declared_vs_actual()
            .into_iter()
            .filter(|(_, declared, actual)| declared != actual)
            .collect();
        if preamble.is_empty() {
            c.preamble_ok += 1;
        } else {
            c.preamble_bad += 1;
            if a.verbose {
                for (name, declared, actual) in preamble {
                    eprintln!(
                        "{}: blay preamble declares {declared} {name} records, section holds {actual}",
                        entry.path
                    );
                }
            }
        }

        if l.struct_run_map().iter().all(|r| r.is_some()) {
            c.struct_first_field_ok += 1;
        } else {
            c.struct_first_field_bad += 1;
            if a.verbose {
                eprintln!("{}: an stv4 first_field misses a run start", entry.path);
            }
        }

        let mut type_ok = true;
        let mut block_index_ok = true;
        let mut block_ok = true;
        let mut struct_ok = true;
        let mut array_bad = false;
        for f in &l.fields {
            if l.types.get(f.type_index as usize).is_none() {
                type_ok = false;
                continue;
            }
            match l.type_name_of(f) {
                "block" => {
                    if l.blocks.get(f.aux as usize).is_none() {
                        block_ok = false;
                    }
                }
                name if name.ends_with("block index") => {
                    if l.blocks.get(f.aux as usize).is_none() {
                        block_index_ok = false;
                    }
                }
                "struct" => {
                    if l.struct_run(f.aux as usize).is_none() {
                        struct_ok = false;
                    }
                }
                "array" => {
                    let in_range = l
                        .arrays
                        .get(f.aux as usize)
                        .is_some_and(|arr| l.struct_run(arr.struct_index as usize).is_some());
                    if !in_range {
                        array_bad = true;
                    }
                }
                _ => {}
            }
        }
        if array_bad {
            c.array_aux_bad += 1;
            if a.verbose {
                eprintln!("{}: array target out of range", entry.path);
            }
        } else {
            c.array_aux_ok += 1;
        }
        if type_ok {
            c.type_index_ok += 1;
        } else {
            c.type_index_bad += 1;
        }
        if block_index_ok {
            c.block_index_ok += 1;
        } else {
            c.block_index_bad += 1;
            if a.verbose {
                eprintln!("{}: a block-index aux is out of range", entry.path);
            }
        }
        if block_ok {
            c.block_aux_ok += 1;
        } else {
            c.block_aux_bad += 1;
        }
        if struct_ok {
            c.struct_aux_ok += 1;
        } else {
            c.struct_aux_bad += 1;
        }

        match l.root_struct().and_then(|r| l.struct_size(r)) {
            Some(_) => c.root_size_ok += 1,
            None => c.root_size_unknown += 1,
        }
        if tag.data().is_some() {
            c.has_data += 1;
        }

        match tag.read_data(&l) {
            Ok(block) => {
                c.data_walk_ok += 1;
                let payload = tag.data().map(|d| d.size as usize).unwrap_or(0);
                match block.consumed.cmp(&payload) {
                    std::cmp::Ordering::Equal => c.data_exact += 1,
                    std::cmp::Ordering::Less => {
                        c.data_short += 1;
                        if a.verbose {
                            eprintln!(
                                "{}: walk consumed {} of {payload}",
                                entry.path, block.consumed
                            );
                        }
                    }
                    std::cmp::Ordering::Greater => c.data_over += 1,
                }
            }
            Err(e) => {
                c.data_walk_failed += 1;
                if a.verbose {
                    eprintln!("{}: {e}", entry.path);
                }
            }
        }
    }

    let pct = |n: usize| {
        if c.parsed == 0 {
            0.0
        } else {
            n as f64 * 100.0 / c.parsed as f64
        }
    };

    println!("checked {} tags ({} parsed)", c.tags, c.parsed);
    println!("  header parse failures        {}", c.header_failed);
    println!("  layout parse failures        {}", c.layout_failed);
    println!(
        "  terminators == struct table  {} ok, {} mismatched  ({:.1}%)",
        c.struct_count_matches,
        c.struct_count_mismatched,
        pct(c.struct_count_matches)
    );
    println!(
        "  blay preamble counts match   {} ok, {} bad  ({:.1}%)",
        c.preamble_ok,
        c.preamble_bad,
        pct(c.preamble_ok)
    );
    println!(
        "  stv4 first_field hits a run   {} ok, {} bad  ({:.1}%)",
        c.struct_first_field_ok,
        c.struct_first_field_bad,
        pct(c.struct_first_field_ok)
    );
    println!(
        "  field type index in range    {} ok, {} bad  ({:.1}%)",
        c.type_index_ok,
        c.type_index_bad,
        pct(c.type_index_ok)
    );
    println!(
        "  block aux indexes blv2       {} ok, {} bad  ({:.1}%)",
        c.block_aux_ok,
        c.block_aux_bad,
        pct(c.block_aux_ok)
    );
    println!(
        "  block-index aux in blv2       {} ok, {} bad  ({:.1}%)",
        c.block_index_ok,
        c.block_index_bad,
        pct(c.block_index_ok)
    );
    println!(
        "  struct aux indexes a run     {} ok, {} bad  ({:.1}%)",
        c.struct_aux_ok,
        c.struct_aux_bad,
        pct(c.struct_aux_ok)
    );
    println!(
        "  array target in range        {} ok, {} bad  ({:.1}%)",
        c.array_aux_ok,
        c.array_aux_bad,
        pct(c.array_aux_ok)
    );
    println!(
        "  root struct size resolves    {} ok, {} unknown  ({:.1}%)",
        c.root_size_ok,
        c.root_size_unknown,
        pct(c.root_size_ok)
    );
    println!(
        "  bdat data section present    {}  ({:.1}%)",
        c.has_data,
        pct(c.has_data)
    );
    println!(
        "  data walk succeeds           {} ok, {} failed  ({:.1}%)",
        c.data_walk_ok,
        c.data_walk_failed,
        pct(c.data_walk_ok)
    );
    println!(
        "  data walk consumes exactly   {} exact, {} short, {} over  ({:.1}%)",
        c.data_exact,
        c.data_short,
        c.data_over,
        pct(c.data_exact)
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use blam_tag::view::{Kind, Node};
    use blam_tag::Scalar;

    fn node(kind: Kind) -> Node {
        Node {
            kind,
            name: "string references".into(),
            type_name: "block".into(),
            offset: 0,
            size: 12,
            value: Scalar::Empty,
            options: Vec::new(),
            block_name: None,
            max_count: None,
            count: None,
            children: Vec::new(),
        }
    }

    /// A block holding `count` elements of which `built` were materialised.
    fn block(count: u32, built: usize, max: u32) -> Node {
        Node {
            count: Some(count),
            max_count: Some(max),
            children: vec![node(Kind::Element); built],
            ..node(Kind::Block)
        }
    }

    /// The regression: a `unic` tag's 318 string references were printed as 64,
    /// the per-block build cap, because the summary read `children.len()`.
    #[test]
    fn a_block_summary_reports_the_real_count_not_what_was_built() {
        let node = block(318, blam_tag::view::DEFAULT_MAX_ELEMENTS, 24576);
        assert_eq!(
            block_summary(&node, Some(4)),
            "[318 element(s) of 24576, showing 4]"
        );
    }

    /// A block printed whole says so, with no trailing note.
    #[test]
    fn a_fully_shown_block_is_not_marked_truncated() {
        let node = block(9, 9, 24576);
        assert_eq!(block_summary(&node, Some(9)), "[9 element(s) of 24576]");
    }

    /// When the depth limit stops before the elements, the count still stands
    /// on its own — claiming to be "showing 4" of a listing that prints nothing
    /// would be worse than saying nothing.
    #[test]
    fn a_depth_limited_block_states_its_count_alone() {
        let node = block(318, blam_tag::view::DEFAULT_MAX_ELEMENTS, 24576);
        assert_eq!(block_summary(&node, None), "[318 element(s) of 24576]");
    }

    /// `--elements` has to reach the builder, or the printer can never show
    /// more than the default cap however high it is set.
    #[test]
    fn the_build_cap_never_falls_below_what_was_asked_for() {
        assert_eq!(build_cap(4000), 4000);
        assert_eq!(build_cap(4), blam_tag::view::DEFAULT_MAX_ELEMENTS);
    }
}
