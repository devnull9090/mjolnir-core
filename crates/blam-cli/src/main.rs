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

mod defs;
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
    /// Histogram the field record aux word, grouped by type name.
    Aux(AuxArgs),
    /// Check structural invariants across every shipped tag.
    Validate(ValidateArgs),
    /// Export the definition corpus as JSON.
    Defs(DefsArgs),
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
    let visible: usize = corpus.groups.values().map(|g| g.visible_field_count()).sum();
    let resolved = corpus
        .groups
        .values()
        .filter(|g| (g.coverage() - 1.0).abs() < f32::EPSILON)
        .count();
    let bytes = std::fs::metadata(&a.out).map(|m| m.len()).unwrap_or(0);

    println!("wrote {}", a.out.display());
    println!("  groups          {}", corpus.groups.len());
    println!("  structs         {}", corpus.groups.values().map(|g| g.structs.len()).sum::<usize>());
    println!("  fields          {total_fields} ({visible} visible)");
    println!("  fully resolved  {resolved}/{}", corpus.groups.len());
    println!("  size            {:.1} KiB", bytes as f64 / 1024.0);
    Ok(())
}

fn groups(a: GroupsArgs) -> Result<()> {
    let idx = index::build(&a.src.paks)?;
    let by_group = idx.by_group();
    println!("group\tfourcc\tver\tcount\tstrings\toptions\ttypes\tfields\tblocks\tstructs\tdata\troot");

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
        let Ok(buf) = idx.read(entry, None, &oodle) else {
            c.header_failed += 1;
            continue;
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

        let mut type_ok = true;
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
                "struct" => {
                    if ranges.get(f.aux as usize).is_none() {
                        struct_ok = false;
                    }
                }
                "array" => {
                    let in_range = l
                        .arrays
                        .get(f.aux as usize)
                        .is_some_and(|arr| ranges.get(arr.struct_index as usize).is_some());
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
    Ok(())
}
