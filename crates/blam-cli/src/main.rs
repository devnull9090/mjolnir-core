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

mod index;

#[derive(Parser)]
#[command(name = "mjolnir", version, about, long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Args, Clone)]
struct Source {
    /// Path to the game's `Meteorite/Content/Paks` directory.
    #[arg(long, env = "HCE_PAKS")]
    paks: PathBuf,
    /// Path to `oo2core_*_win64.dll`, or a directory containing one.
    #[arg(long, env = "OODLE")]
    oodle: PathBuf,
}

impl Source {
    fn oodle_roots(&self) -> Vec<PathBuf> {
        vec![self.oodle.clone()]
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

fn main() -> Result<()> {
    match Cli::parse().command {
        Command::Groups(a) => groups(a),
        Command::List(a) => list(a),
        Command::Layout(a) => layout(a),
        Command::Fields(a) => fields(a),
        Command::Types(a) => types(a),
    }
}

fn groups(a: GroupsArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    println!("group\tfourcc\tver\tcount\tstrings\toptions\ttypes\tfields\tblocks\tstructs\tdata");

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
        println!(
            "{group}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{data}",
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
            println!("    +{:<8} {}  v{:<3} size {}", s.at, s.name(), s.version, s.size);
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
            for (i, s) in l.structs.iter().enumerate() {
                let guid: String = s.guid.iter().map(|b| format!("{b:02x}")).collect();
                println!(
                    "    [{i:>3}] {guid}  {}",
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
                    println!("  [{i:>4}] +{offset:<6} {sz:>4}b  {type_name:<28} {shown}");
                    offset += sz;
                }
                None => println!(
                    "  [{i:>4}] +{offset:<6}    ?b  <type {}>{:<14} {shown}",
                    f.type_index, ""
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
            .map(|(s, n)| if consistent { s.to_string() } else { format!("{s}:{n}") })
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
