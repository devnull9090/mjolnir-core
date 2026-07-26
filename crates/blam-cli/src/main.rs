//! `mjolnir` — inspect Halo Campaign Evolved tag data.
//!
//! Reads directly from an installed game's IoStore containers. Nothing is
//! written to disk: extracted tag data is copyrighted game content and stays in
//! memory.

use std::collections::BTreeMap;
use std::path::PathBuf;

use anyhow::{bail, Context, Result};
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
    /// Summarise the shipped tag groups.
    Groups(GroupsArgs),
    /// List tag paths.
    List(ListArgs),
    /// Print the embedded layout section for one group.
    Layout(LayoutArgs),
    /// Histogram field type codes across groups, to drive type mapping.
    TypeCodes(TypeCodesArgs),
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
    /// Print at most this many field records.
    #[arg(long, default_value_t = 40)]
    fields: usize,
}

#[derive(Args)]
struct TypeCodesArgs {
    #[command(flatten)]
    src: Source,
    /// Show up to this many example field names per type code.
    #[arg(long, default_value_t = 4)]
    examples: usize,
}

fn main() -> Result<()> {
    match Cli::parse().command {
        Command::Groups(a) => groups(a),
        Command::List(a) => list(a),
        Command::Layout(a) => layout(a),
        Command::TypeCodes(a) => type_codes(a),
    }
}

fn groups(a: GroupsArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    println!("group\tfourcc\tver\tcount\tblay_size\tstrings\toptions\tfields\ttrunc");

    let mut truncated = 0usize;
    for (group, entries) in &by_group {
        let first = entries[0];
        let buf = idx.read(first, None, &a.src.oodle_roots())?;
        let (cc, ver, blay, nstr, nopt, nfld, trunc) =
            match TagFile::parse(&buf, Some(first.chunk.length as usize)) {
                Ok(tag) => match tag.layout() {
                    Ok(l) => (
                        tag.header.group.as_str(),
                        tag.header.group_version,
                        l.size,
                        l.strings().len(),
                        l.option_offsets.len(),
                        l.fields.len(),
                        l.options_truncated,
                    ),
                    Err(e) => {
                        eprintln!("{group}: layout parse failed: {e}");
                        continue;
                    }
                },
                Err(e) => {
                    eprintln!("{group}: header parse failed: {e}");
                    continue;
                }
            };
        if trunc {
            truncated += 1;
        }
        println!(
            "{group}\t{cc}\t{ver}\t{}\t{blay}\t{nstr}\t{nopt}\t{nfld}\t{trunc}",
            entries.len()
        );
    }
    println!(
        "\n{} groups, {} payloads, {truncated} with a truncated option table",
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

fn layout(a: LayoutArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let entries = by_group
        .get(a.group.as_str())
        .with_context(|| format!("unknown group {:?}", a.group))?;
    let entry = entries[0];

    let buf = idx.read(entry, None, &a.src.oodle_roots())?;
    let tag = TagFile::parse(&buf, Some(entry.chunk.length as usize))?;
    let l = tag.layout()?;

    println!("{} ({}) v{}", a.group, tag.header.group, tag.header.group_version);
    println!("  path            {}", entry.path);
    println!("  blay            v{} size {:#x}", l.version, l.size);
    println!("  strings         {}", l.strings().len());
    println!("  options         {}", l.option_offsets.len());
    println!("  field records   {}", l.fields.len());
    println!("  header words    {:?}", l.header_words);

    if a.options {
        println!("\n  options:");
        for (i, o) in l.options().iter().enumerate() {
            println!("    [{i:>4}] {o}");
        }
    }

    println!("\n  fields:");
    for (i, (name, code, aux)) in l.named_fields().iter().take(a.fields).enumerate() {
        println!("    [{i:>4}] type {code:>3}  aux {aux:>6}  {name}");
    }
    Ok(())
}

fn type_codes(a: TypeCodesArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    let oodle = a.src.oodle_roots();

    let mut counts: BTreeMap<u32, usize> = BTreeMap::new();
    let mut examples: BTreeMap<u32, Vec<String>> = BTreeMap::new();
    let mut aux_values: BTreeMap<u32, BTreeMap<u32, usize>> = BTreeMap::new();
    let mut parsed = 0usize;
    let mut failed = 0usize;

    for (group, entries) in &by_group {
        let entry = entries[0];
        let buf = match idx.read(entry, None, &oodle) {
            Ok(b) => b,
            Err(_) => {
                failed += 1;
                continue;
            }
        };
        let tag = match TagFile::parse(&buf, Some(entry.chunk.length as usize)) {
            Ok(t) => t,
            Err(_) => {
                failed += 1;
                continue;
            }
        };
        let l = match tag.layout() {
            Ok(l) => l,
            Err(e) => {
                eprintln!("{group}: {e}");
                failed += 1;
                continue;
            }
        };
        parsed += 1;

        for (name, code, aux) in l.named_fields() {
            *counts.entry(code).or_default() += 1;
            *aux_values.entry(code).or_default().entry(aux).or_default() += 1;
            let ex = examples.entry(code).or_default();
            if ex.len() < a.examples && !name.is_empty() && !ex.iter().any(|e| e == name) {
                ex.push(name.to_string());
            }
        }
    }

    if parsed == 0 {
        bail!("no layouts parsed");
    }

    println!("parsed {parsed} groups, {failed} failed\n");
    println!("code\tcount\tdistinct_aux\ttop_aux\texamples");
    for (code, count) in &counts {
        let aux = &aux_values[code];
        let top = aux.iter().max_by_key(|(_, n)| **n).map(|(v, _)| *v).unwrap_or(0);
        println!(
            "{code}\t{count}\t{}\t{top}\t{}",
            aux.len(),
            examples.get(code).map(|e| e.join(" | ")).unwrap_or_default()
        );
    }
    Ok(())
}
