//! `mjolnir container` — name what an override container replaces.
//!
//! An override container is addressed entirely by chunk ID. That is what makes
//! it work — the ID is read straight out of the shipped index rather than
//! derived — and also what makes it opaque: the container carries no directory
//! index, so nothing in it says which asset a chunk *is*.
//!
//! The names are recoverable, though, because the shipped containers do carry
//! one. Matching the override's chunk IDs back against that index turns a list
//! of hex into a list of assets, which is the difference between "this mod
//! changes something" and "this mod changes A15.umap".
//!
//! Companion to `mjolnir pack`, which produces these containers.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use clap::Args;
use ue_iostore::toc::Toc;
use ue_iostore::Container;

use crate::Source;

#[derive(Args)]
pub struct ContainerArgs {
    #[command(flatten)]
    src: Source,
    /// The override containers to inspect, as `.utoc` paths.
    #[arg(required = true)]
    utocs: Vec<PathBuf>,
    /// Read every chunk back through the ordinary reader, the way the game
    /// would. Needs Oodle; without this the command only reads indexes.
    #[arg(long)]
    verify: bool,
}

/// The shipped assets, keyed the way a chunk identifies itself.
type Names = HashMap<(u64, u16, u8), String>;

/// `ContainerHeader`. Every container carries one describing itself, so it is
/// structural rather than an override and must not be counted as one — it
/// matches no shipped asset by design.
const CONTAINER_HEADER: u8 = 6;

/// Build the chunk-ID to asset-path map from every shipped container.
///
/// `skip` drops the containers being inspected, so one that carries its own
/// directory index cannot resolve its chunks against itself and report that it
/// overrides the very thing it is.
fn shipped_names(containers: &[Container], skip: &[PathBuf]) -> Names {
    let mut names = HashMap::new();
    for c in containers {
        if skip.iter().any(|s| same_file(s, &c.utoc_path)) {
            continue;
        }
        names.extend(index_of(c));
    }
    names
}

/// One container's own directory index, as chunk key to packaged path.
///
/// Empty for an override container, which is found by chunk ID and therefore
/// has nothing to list.
fn index_of(c: &Container) -> Names {
    c.files
        .iter()
        .map(|(rel, chunk_index)| {
            let chunk = c.chunks[*chunk_index];
            (
                (chunk.chunk_id, chunk.chunk_index, chunk.chunk_type),
                c.full_path(rel),
            )
        })
        .collect()
}

/// Whether two paths name the same file, falling back to a plain comparison
/// when either cannot be canonicalised.
fn same_file(a: &Path, b: &Path) -> bool {
    match (a.canonicalize(), b.canonicalize()) {
        (Ok(a), Ok(b)) => a == b,
        _ => a == b,
    }
}

pub fn run(a: ContainerArgs) -> Result<()> {
    let shipped = ue_iostore::load_all(&a.src.paks)?;
    let names = shipped_names(&shipped, &a.utocs);
    let oodle = a.src.oodle_roots();

    for (nth, utoc) in a.utocs.iter().enumerate() {
        if nth > 0 {
            println!();
        }
        report(utoc, &names, &oodle, a.verify)?;
    }
    Ok(())
}

fn report(utoc: &Path, names: &Names, oodle: &[PathBuf], verify: bool) -> Result<()> {
    let container = ue_iostore::load_container(utoc)
        .with_context(|| format!("cannot read {}", utoc.display()))?;
    let toc = Toc::read(utoc).with_context(|| format!("cannot read {}", utoc.display()))?;

    let file_name = utoc
        .file_name()
        .unwrap_or_default()
        .to_string_lossy()
        .to_string();
    println!("{file_name}");
    println!("  container id {:#018x}", container.container_id);
    println!("  {} chunk(s)", container.chunks.len());
    println!();

    // An override container carries no directory index, but a container that
    // adds content rather than replacing it does. Names from its own index
    // describe what it *is*; names from the shipped index describe what it
    // *replaces*, which is the question this command exists to answer, so the
    // shipped match wins where both are present.
    let own = index_of(&container);

    let mut unknown = 0;
    let mut added = 0;
    let mut replaced = 0;
    for chunk in &container.chunks {
        let key = (chunk.chunk_id, chunk.chunk_index, chunk.chunk_type);
        let name = match (names.get(&key), own.get(&key)) {
            (Some(path), _) => {
                replaced += 1;
                path.clone()
            }
            (None, Some(path)) => {
                added += 1;
                format!("{path}  (new; replaces nothing)")
            }
            (None, None) if chunk.chunk_type == CONTAINER_HEADER => {
                "<this container's own header>".to_string()
            }
            (None, None) => {
                unknown += 1;
                "<not in any shipped container>".to_string()
            }
        };
        println!(
            "  {:#018x} {:<16} {:>10} bytes  {name}",
            chunk.chunk_id,
            chunk.type_name(),
            chunk.length
        );
    }

    println!("\n  {replaced} shipped asset(s) replaced");
    if added > 0 {
        println!("  {added} asset(s) added rather than replaced");
    }

    // Everything below is a reason the game would ignore this container. They
    // are reported together because each one looks identical from the outside:
    // the mod simply does nothing, and the shipped asset loads instead.
    let mut warnings = Vec::new();
    if unknown > 0 {
        warnings.push(format!(
            "{unknown} chunk(s) match no shipped asset, so they override nothing. \
             Either they were built against a different game version, or the \
             container adds new content rather than replacing any."
        ));
    }
    if toc.chunks_without_perfect_hash != 0 {
        warnings.push(format!(
            "{} chunk(s) are findable only by scanning the overflow list. No shipped \
             container uses it and the game does not read it — these chunks are invisible.",
            toc.chunks_without_perfect_hash
        ));
    }
    // Only worth saying when the container is actually trying to override
    // something; a shipped container is not a patch container and does not
    // need telling.
    if replaced > 0 && !file_name.trim_end_matches(".utoc").ends_with("_P") {
        warnings.push(
            "the name does not end in `_P`, so this is not a patch container and the \
             shipped chunks win the lookup."
                .to_string(),
        );
    }

    if verify {
        for chunk in &container.chunks {
            match ue_iostore::read_chunk(&container, chunk, None, oodle) {
                Ok(bytes) if bytes.len() as u64 == chunk.length => {}
                Ok(bytes) => warnings.push(format!(
                    "chunk {:#018x} read back {} bytes, not the {} its index claims",
                    chunk.chunk_id,
                    bytes.len(),
                    chunk.length
                )),
                Err(e) => warnings.push(format!("chunk {:#018x} is unreadable: {e}", chunk.chunk_id)),
            }
        }
        if warnings.is_empty() {
            println!("\n  every chunk reads back at the size its index claims.");
        }
    }

    for warning in &warnings {
        println!("\n  warning: {warning}");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_file_survives_paths_that_do_not_exist() {
        // Canonicalisation fails for both, so the comparison falls back to the
        // literal paths rather than reporting every missing path as identical.
        let a = PathBuf::from("no/such/a.utoc");
        let b = PathBuf::from("no/such/b.utoc");
        assert!(same_file(&a, &a.clone()));
        assert!(!same_file(&a, &b));
    }
}
