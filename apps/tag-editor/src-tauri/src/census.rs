//! The census fingerprint table: a few locator byte-runs per catalog tag.
//!
//! A census (see `blam_live::census`) finds every loaded tag in one sweep of
//! the game's memory, but it needs a fingerprint per tag to look for — and
//! picking those means reading every tag payload, the same tens-of-seconds
//! pass the reverse-reference index pays. Like that index, the result is a
//! pure function of the tag chunks, so it is cached to disk under the same
//! installation fingerprint and reloaded in well under a second afterwards.

use std::ops::Range;

use serde::{Deserialize, Serialize};

use crate::catalog::Catalog;

/// One tag's census fingerprint, plus what verification needs later: the
/// data-section range to re-score a candidate base against.
pub struct TagPrint {
    /// Catalog tag index. Stable for as long as the installation fingerprint
    /// holds, because the fingerprint covers the tag list in catalog order.
    pub index: u32,
    /// The resident data section within the payload.
    pub region: Range<usize>,
    /// `(file offset, bytes)` locator runs, as `blam_live::print` picked them.
    pub runs: Vec<(usize, Vec<u8>)>,
}

/// The on-disk shape. Run bytes are hex in one string per tag — compact
/// enough, and `serde_json` is already the caching format everywhere else.
#[derive(Serialize, Deserialize)]
struct Row {
    i: u32,
    r0: usize,
    r1: usize,
    offs: Vec<u32>,
    hex: String,
}

/// Bumped whenever how prints are picked changes (run counts, anchor rules),
/// so a cache built by an older build is rebuilt rather than trusted — the
/// installation fingerprint alone cannot see that.
const FORMAT: u32 = 2;

#[derive(Serialize, Deserialize)]
struct CacheFile {
    format: u32,
    fingerprint: u64,
    run_len: usize,
    rows: Vec<Row>,
}

fn hex_encode(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn hex_decode(s: &str) -> Option<Vec<u8>> {
    if s.len() % 2 != 0 {
        return None;
    }
    (0..s.len() / 2)
        .map(|i| u8::from_str_radix(&s[i * 2..i * 2 + 2], 16).ok())
        .collect()
}

fn cache_path(c: &Catalog) -> Option<std::path::PathBuf> {
    crate::refcache::cache_file(c.paks(), "census")
}

fn load(c: &Catalog, fingerprint: u64) -> Option<Vec<TagPrint>> {
    let text = std::fs::read_to_string(cache_path(c)?).ok()?;
    let file: CacheFile = serde_json::from_str(&text).ok()?;
    if file.format != FORMAT || file.fingerprint != fingerprint || file.run_len == 0 {
        return None;
    }
    let mut out = Vec::with_capacity(file.rows.len());
    for row in file.rows {
        let bytes = hex_decode(&row.hex)?;
        if bytes.len() != row.offs.len() * file.run_len {
            return None;
        }
        out.push(TagPrint {
            index: row.i,
            region: row.r0..row.r1,
            runs: row
                .offs
                .iter()
                .enumerate()
                .map(|(n, &off)| {
                    (
                        off as usize,
                        bytes[n * file.run_len..(n + 1) * file.run_len].to_vec(),
                    )
                })
                .collect(),
        });
    }
    Some(out)
}

fn store(c: &Catalog, fingerprint: u64, prints: &[TagPrint]) {
    let Some(path) = cache_path(c) else {
        return;
    };
    let run_len = prints
        .first()
        .and_then(|p| p.runs.first())
        .map(|(_, r)| r.len())
        .unwrap_or(0);
    if run_len == 0 {
        return;
    }
    let file = CacheFile {
        format: FORMAT,
        fingerprint,
        run_len,
        rows: prints
            .iter()
            .map(|p| Row {
                i: p.index,
                r0: p.region.start,
                r1: p.region.end,
                offs: p.runs.iter().map(|(o, _)| *o as u32).collect(),
                hex: hex_encode(
                    &p.runs
                        .iter()
                        .flat_map(|(_, r)| r.iter().copied())
                        .collect::<Vec<u8>>(),
                ),
            })
            .collect(),
    };
    if let Some(dir) = path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    if let Ok(text) = serde_json::to_string(&file) {
        // Write-then-rename, as refcache does, so a crash cannot leave a torn
        // file to half-parse next launch.
        let tmp = path.with_extension("json.tmp");
        if std::fs::write(&tmp, text).is_ok() {
            let _ = std::fs::rename(&tmp, &path);
        }
    }
}

/// The fingerprint table for every printable tag in the catalog: cached on
/// disk, or built by reading every tag payload (tens of seconds, so callers
/// run it off the UI thread and say why they are waiting).
pub fn table(c: &Catalog) -> Vec<TagPrint> {
    let fingerprint = c.install_fingerprint();
    if let Some(prints) = load(c, fingerprint) {
        return prints;
    }
    let mut prints = Vec::new();
    for i in 0..c.tags.len() {
        let Ok(payload) = c.read_tag(i) else {
            continue;
        };
        // Only the data section is resident in the game (see `blam_live`);
        // a tag whose header does not parse cannot be located and is skipped.
        let Some(region) = blam_tag::TagFile::parse(&payload, Some(payload.len()))
            .ok()
            .and_then(|tag| tag.data().map(|d| {
                let start = d.content.as_ptr() as usize - payload.as_ptr() as usize;
                start..start + d.content.len()
            }))
        else {
            continue;
        };
        // Scenarios get locate's full 32-run spread: the engine rewrites a
        // scenario harder than any other tag, and it is the tag that names
        // the level, so its census odds are worth a few extra table slots.
        let print = if c.tags[i].group == "scenario" {
            blam_live::print_n(i as u32, &payload, &region, 32)
        } else {
            blam_live::print(i as u32, &payload, &region)
        };
        if let Some(print) = print {
            prints.push(TagPrint {
                index: print.id,
                region,
                runs: print.runs,
            });
        }
    }
    store(c, fingerprint, &prints);
    prints
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_round_trips() {
        let bytes: Vec<u8> = (0..=255).collect();
        assert_eq!(hex_decode(&hex_encode(&bytes)), Some(bytes));
        assert_eq!(hex_decode("0g"), None);
        assert_eq!(hex_decode("abc"), None);
    }

    /// Statistics over the real fingerprint table: how clustered run prefixes
    /// are, and how hot the worst ones would run against common heap content.
    /// Needs only the installation, not the game.
    #[test]
    #[ignore = "needs an installed game; set MJOLNIR_PAKS"]
    fn census_table_diagnostics() {
        use std::collections::HashMap;

        let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
        let c = Catalog::open(&paks, "").expect("catalog opens");
        let prints = table(&c);

        let mut by_prefix: HashMap<u32, u32> = HashMap::new();
        let mut by_run: HashMap<&[u8], u32> = HashMap::new();
        let mut total_runs = 0usize;
        for p in &prints {
            for (_, run) in &p.runs {
                let prefix = u32::from_le_bytes(run[..4].try_into().unwrap());
                *by_prefix.entry(prefix).or_default() += 1;
                *by_run.entry(run.as_slice()).or_default() += 1;
                total_runs += 1;
            }
        }
        eprintln!(
            "{} runs, {} distinct prefixes, {} distinct run bodies",
            total_runs,
            by_prefix.len(),
            by_run.len()
        );
        let mut hot: Vec<(u32, u32)> = by_prefix.iter().map(|(k, v)| (*k, *v)).collect();
        hot.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
        for (prefix, n) in hot.iter().take(15) {
            eprintln!("  prefix {prefix:#010x}: {n} runs");
        }
        let dup_runs: u32 = by_run.values().filter(|n| **n > 1).sum();
        eprintln!("runs sharing an identical body with another tag: {dup_runs}");
    }

    /// Census the running game and report what is loaded — the manual proof
    /// of the whole pipeline: fingerprint table, sweep, verification, level.
    ///
    /// Ignored by default; set `MJOLNIR_PAKS`, have the game in a mission, and
    /// run with `--release --ignored --nocapture` (a debug-profile sweep is
    /// unoptimized and takes many times longer).
    #[test]
    #[ignore = "needs an installed game, running; set MJOLNIR_PAKS"]
    fn census_of_the_running_game() {
        let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
        let c = Catalog::open(&paks, "").expect("catalog opens");

        let t0 = std::time::Instant::now();
        let prints = table(&c);
        eprintln!(
            "prints: {} of {} tags in {:.1?}",
            prints.len(),
            c.tags.len(),
            t0.elapsed()
        );

        let process = blam_live::Process::attach().expect("game running");
        let search: Vec<blam_live::Print> = prints
            .iter()
            .map(|p| blam_live::Print {
                id: p.index,
                runs: p.runs.clone(),
            })
            .collect();

        let t1 = std::time::Instant::now();
        let last = std::sync::atomic::AtomicU64::new(0);
        let outcome = blam_live::census(&process, &search, &|d, t| {
            let step = d >> 30;
            if last.swap(step, std::sync::atomic::Ordering::Relaxed) != step {
                eprintln!("  swept {} / {} GB", d >> 30, t >> 30);
            }
        })
        .expect("census sweeps");
        eprintln!(
            "sweep: {} hits, {} ambiguous, {:.1} GB read in {:.1?}",
            outcome.hits.len(),
            outcome.ambiguous,
            outcome.scanned as f64 / (1u64 << 30) as f64,
            t1.elapsed()
        );

        let by_id: std::collections::HashMap<u32, &TagPrint> =
            prints.iter().map(|p| (p.index, p)).collect();
        let mut verified: Vec<usize> = Vec::new();
        let mut rejected = 0usize;
        for hit in &outcome.hits {
            let print = by_id[&hit.id];
            let payload = c.read_tag(hit.id as usize).expect("hit tag reads");
            let f = blam_live::verify(&process, &payload, &print.region, hit.base);
            let entry = c.entry(hit.id as usize).expect("hit tag exists");
            if f > 0.10 {
                verified.push(hit.id as usize);
                if entry.group == "scenario" {
                    eprintln!(
                        "  scenario loaded: {} at {:#x} ({:.0}% verified)",
                        entry.short,
                        hit.base,
                        f * 100.0
                    );
                }
            } else {
                rejected += 1;
                eprintln!(
                    "  rejected: {}.{} at {:#x} scored {f:.3}",
                    entry.short, entry.group, hit.base
                );
            }
        }
        eprintln!(
            "verified {} loaded tags ({rejected} rejected) in {:.1?} total",
            verified.len(),
            t0.elapsed()
        );

        // The reference-graph level inference, as the app performs it when no
        // scenario tag verified directly.
        let mut score: std::collections::HashMap<usize, usize> = Default::default();
        for &i in &verified {
            for s in c.referencing(i, 64).unwrap_or_default() {
                if s.group == "scenario" {
                    *score.entry(s.index).or_default() += 1;
                }
            }
        }
        let mut ranked: Vec<(usize, usize)> = score.into_iter().collect();
        ranked.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
        for (i, n) in ranked.iter().take(5) {
            eprintln!(
                "  level by references: {} covered by {n} loaded tags",
                c.entry(*i).map(|e| e.short.as_str()).unwrap_or("?")
            );
        }
    }
}
