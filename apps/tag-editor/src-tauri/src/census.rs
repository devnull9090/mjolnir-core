//! The census fingerprint table: a few locator byte-runs per catalog tag.
//!
//! A census (see `blam_live::census`) finds every loaded tag in one sweep of
//! the game's memory, but it needs a fingerprint per tag to look for — and
//! picking those means reading every tag payload, the same tens-of-seconds
//! pass the reverse-reference index pays. Like that index, the result is a
//! pure function of the tag chunks, so it is cached to disk under the same
//! installation fingerprint and reloaded in well under a second afterwards.
//!
//! The table also carries what judging a hit needs — the root element's
//! bytes, which of them are scalars, and where its block headers are — so a
//! census never goes back to the containers for a tag it found. Reading and
//! decoding two thousand hit payloads cost 46 seconds, measured, against a
//! 19-second sweep.

use std::ops::Range;

use serde::{Deserialize, Serialize};

use crate::catalog::Catalog;

/// One tag's census fingerprint, plus what judging a candidate base needs.
pub struct TagPrint {
    /// Catalog tag index. Stable for as long as the installation fingerprint
    /// holds, because the fingerprint covers the tag list in catalog order.
    pub index: u32,
    /// The resident data section within the payload.
    pub region: Range<usize>,
    /// The root element within it — what the engine keeps at file offsets,
    /// and what a candidate base is verified against.
    pub root: Range<usize>,
    /// `(file offset, bytes)` locator runs, as `blam_live::print_stable` (or,
    /// for a tag with no scalars, `blam_live::print_n`) picked them.
    pub runs: Vec<(usize, Vec<u8>)>,
    /// One mask per run, as `blam_live::Print` carries them; empty for the
    /// plain print.
    pub masks: Vec<Vec<u8>>,
    /// The payload bytes over `span`, with their scalar mask, so a hit can be
    /// judged without reading the tag again. Empty when the span was too big
    /// to keep (see [`KEEP`]); the caller reads the payload then.
    pub bytes: Vec<u8>,
    pub stable: Vec<bool>,
    /// What `bytes` covers: the root element for a masked print, the whole
    /// data section for a plain one (which is scored byte for byte).
    pub span: Range<usize>,
    /// File offsets of the root element's block fields with elements.
    pub headers: Vec<usize>,
}

/// Biggest span kept in the table, per tag. Root elements are a kilobyte or
/// two; a plain-printed data section can be anything, and past this the
/// judge reads the tag from the containers instead.
const KEEP: usize = 64 * 1024;

/// The on-disk shape. Bytes are hex in one string per field — compact
/// enough, and `serde_json` is already the caching format everywhere else.
#[derive(Serialize, Deserialize)]
struct Row {
    i: u32,
    r0: usize,
    r1: usize,
    /// The root element.
    e0: usize,
    e1: usize,
    offs: Vec<u32>,
    hex: String,
    /// Masks, concatenated like `hex`; empty for an unmasked print.
    #[serde(default)]
    masks: String,
    /// The judged span and its bytes and scalar mask (bit-packed, LSB first).
    #[serde(default)]
    s0: usize,
    #[serde(default)]
    s1: usize,
    #[serde(default)]
    bytes: String,
    #[serde(default)]
    stable: String,
    #[serde(default)]
    hdr: Vec<u32>,
}

/// Bumped whenever how prints are picked changes (run counts, anchor rules),
/// so a cache built by an older build is rebuilt rather than trusted — the
/// installation fingerprint alone cannot see that.
const FORMAT: u32 = 4;

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

fn pack_bits(flags: &[bool]) -> Vec<u8> {
    let mut out = vec![0u8; flags.len().div_ceil(8)];
    for (i, f) in flags.iter().enumerate() {
        if *f {
            out[i / 8] |= 1 << (i % 8);
        }
    }
    out
}

fn unpack_bits(packed: &[u8], len: usize) -> Option<Vec<bool>> {
    if packed.len() != len.div_ceil(8) {
        return None;
    }
    Some((0..len).map(|i| packed[i / 8] & (1 << (i % 8)) != 0).collect())
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
        let masks: Vec<Vec<u8>> = if row.masks.is_empty() {
            Vec::new()
        } else {
            let m = hex_decode(&row.masks)?;
            if m.len() != bytes.len() {
                return None;
            }
            m.chunks(file.run_len).map(|c| c.to_vec()).collect()
        };
        let span = row.s0..row.s1;
        let (span_bytes, stable) = if row.bytes.is_empty() {
            (Vec::new(), Vec::new())
        } else {
            let b = hex_decode(&row.bytes)?;
            if b.len() != span.len() {
                return None;
            }
            let s = unpack_bits(&hex_decode(&row.stable)?, span.len())?;
            (b, s)
        };
        out.push(TagPrint {
            index: row.i,
            region: row.r0..row.r1,
            root: row.e0..row.e1,
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
            masks,
            bytes: span_bytes,
            stable,
            span,
            headers: row.hdr.iter().map(|h| *h as usize).collect(),
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
                e0: p.root.start,
                e1: p.root.end,
                offs: p.runs.iter().map(|(o, _)| *o as u32).collect(),
                hex: hex_encode(
                    &p.runs
                        .iter()
                        .flat_map(|(_, r)| r.iter().copied())
                        .collect::<Vec<u8>>(),
                ),
                masks: hex_encode(&p.masks.concat()),
                s0: p.span.start,
                s1: p.span.end,
                bytes: hex_encode(&p.bytes),
                stable: if p.bytes.is_empty() {
                    String::new()
                } else {
                    hex_encode(&pack_bits(&p.stable))
                },
                hdr: p.headers.iter().map(|h| *h as u32).collect(),
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

/// Build one tag's print, or `None` when it cannot be fingerprinted.
fn print_of(c: &Catalog, i: usize) -> Option<TagPrint> {
    let payload = c.read_tag(i).ok()?;
    // Only the data section is resident in the game (see `blam_live`); a tag
    // whose header does not parse cannot be located and is skipped.
    let tag = blam_tag::TagFile::parse(&payload, Some(payload.len())).ok()?;
    let data = tag.data()?;
    let layout = tag.layout().ok()?;
    let block = tag.read_data(&layout).ok()?;
    let start = data.content.as_ptr() as usize - payload.as_ptr() as usize;
    let region = start..start + data.content.len();
    let root_off = block.elements.as_ptr() as usize - payload.as_ptr() as usize;
    let root = root_off..root_off + block.element_size as usize;
    let stable = blam_tag::view::scalar_mask(&layout, &block, &payload);
    let headers: Vec<usize> = blam_tag::patch::root_blocks(&layout, &payload, &block)
        .iter()
        .filter(|(_, n)| *n > 0)
        .map(|(h, _)| h.header)
        .collect();
    let shape = blam_live::Shape {
        region: region.clone(),
        root: root.clone(),
        stable: &stable,
        headers: &headers,
    };
    // Scenarios get locate's full 32-run spread: the engine rewrites a
    // scenario harder than any other tag, and it is the tag that names the
    // level, so its census odds are worth a few extra table slots.
    let count = if c.tags[i].group == "scenario" { 32 } else { 12 };
    // The engine keeps only the root element's scalars at file offsets, so
    // the print is masked to those; a tag with too few scalars to fingerprint
    // gets the plain byte-run print instead, and is judged byte for byte
    // over the whole data section as before.
    let (print, span) = match blam_live::print_stable(i as u32, &payload, &shape, count) {
        Some(p) => (p, root.clone()),
        None => (
            blam_live::print_n(i as u32, &payload, &region, count)?,
            region.clone(),
        ),
    };
    let (bytes, kept) = if span.len() <= KEEP {
        (payload[span.clone()].to_vec(), stable[span.clone()].to_vec())
    } else {
        (Vec::new(), Vec::new())
    };
    Some(TagPrint {
        index: print.id,
        region,
        root,
        runs: print.runs,
        masks: print.masks,
        bytes,
        stable: kept,
        span,
        headers,
    })
}

/// The fingerprint table for every printable tag in the catalog: cached on
/// disk, or built by reading every tag payload — a minute or so on half the
/// machine's cores, so callers run it off the UI thread and say why they are
/// waiting.
pub fn table(c: &Catalog) -> Vec<TagPrint> {
    let fingerprint = c.install_fingerprint();
    if let Some(prints) = load(c, fingerprint) {
        return prints;
    }
    // Decoding and walking twelve thousand tags is CPU-bound and every tag
    // is independent, so the build is split across threads. Half the
    // machine, as the sweep does: this runs while the game is up.
    let threads = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4)
        .div_ceil(2)
        .clamp(1, 8);
    let next = std::sync::atomic::AtomicUsize::new(0);
    let total = c.tags.len();
    let mut prints: Vec<TagPrint> = std::thread::scope(|s| {
        let workers: Vec<_> = (0..threads)
            .map(|_| {
                let next = &next;
                s.spawn(move || {
                    let mut out = Vec::new();
                    loop {
                        let i = next.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                        if i >= total {
                            break;
                        }
                        if let Some(p) = print_of(c, i) {
                            out.push(p);
                        }
                    }
                    out
                })
            })
            .collect();
        workers
            .into_iter()
            .flat_map(|w| w.join().expect("print worker panicked"))
            .collect()
    });
    prints.sort_by_key(|p| p.index);
    store(c, fingerprint, &prints);
    prints
}

/// Which of several candidate bases is the tag's working copy, and how well
/// it scores — or `None` when none is.
///
/// The votes cannot tell the engine's working copy from the loader's
/// byte-perfect image of the file — a census in a30 found nineteen weapons
/// at 100%, none of them what the simulation reads — but the block headers
/// can: only the working copy has them rewritten. `blam_live::accept`
/// applies that, and the root element's scalars, to every candidate. The
/// print carries what that needs; `read` supplies the payload only for a
/// tag whose span was too big to keep in the table.
pub fn judge(
    process: &blam_live::Process,
    print: &TagPrint,
    bases: &[u64],
    read: impl Fn() -> Option<Vec<u8>>,
) -> Option<(u64, f32)> {
    // A payload with only the judged span filled in is enough: scoring reads
    // nothing outside it.
    let (payload, stable) = if print.bytes.is_empty() {
        let payload = read()?;
        let tag = blam_tag::TagFile::parse(&payload, Some(payload.len())).ok()?;
        let layout = tag.layout().ok()?;
        let block = tag.read_data(&layout).ok()?;
        let stable = blam_tag::view::scalar_mask(&layout, &block, &payload);
        (payload, stable)
    } else {
        let mut payload = vec![0u8; print.span.end];
        let mut stable = vec![false; print.span.end];
        payload[print.span.clone()].copy_from_slice(&print.bytes);
        stable[print.span.clone()].copy_from_slice(&print.stable);
        (payload, stable)
    };
    let shape = blam_live::Shape {
        region: print.region.clone(),
        root: print.root.clone(),
        stable: &stable,
        headers: &print.headers,
    };
    // The first candidate that passes is the answer: rivals tied on votes are
    // identical copies, so none scores higher than another. The cap is for
    // tags that tie across hundreds of buffers — a family of near-identical
    // sounds — where scoring every one cost twenty seconds a census and
    // "the" working copy is not a meaningful question past the first few.
    const MOST: usize = 48;
    bases
        .iter()
        .take(MOST)
        .find(|&&base| blam_live::accept(process, &payload, &shape, base))
        .map(|&base| (base, blam_live::score(process, &payload, &shape, base)))
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

    #[test]
    fn bit_masks_round_trip() {
        let flags: Vec<bool> = (0..37).map(|i| i % 3 == 0 || i == 36).collect();
        let packed = pack_bits(&flags);
        assert_eq!(packed.len(), 5);
        assert_eq!(unpack_bits(&packed, flags.len()), Some(flags.clone()));
        assert_eq!(unpack_bits(&packed, 40), Some({
            let mut f = flags;
            f.extend([false; 3]);
            f
        }));
        assert_eq!(unpack_bits(&packed, 100), None);
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
        let t0 = std::time::Instant::now();
        let prints = table(&c);
        eprintln!(
            "{} prints ({} masked, {} carrying bytes) in {:.1?}",
            prints.len(),
            prints.iter().filter(|p| !p.masks.is_empty()).count(),
            prints.iter().filter(|p| !p.bytes.is_empty()).count(),
            t0.elapsed()
        );

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
    /// of the whole pipeline: fingerprint table, sweep, judgement, level.
    ///
    /// Ignored by default; set `MJOLNIR_PAKS`, have the game in a mission, and
    /// run with `--ignored --nocapture`.
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
                masks: p.masks.clone(),
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
            "sweep: {} hits, {} with rivals, {:.1} GB read in {:.1?}",
            outcome.hits.len(),
            outcome.ambiguous,
            outcome.scanned as f64 / (1u64 << 30) as f64,
            t1.elapsed()
        );

        let t2 = std::time::Instant::now();
        let by_id: std::collections::HashMap<u32, &TagPrint> =
            prints.iter().map(|p| (p.index, p)).collect();
        let mut verified: Vec<usize> = Vec::new();
        let mut rejected = 0usize;
        let mut fell_back = 0usize;
        for hit in &outcome.hits {
            let print = by_id[&hit.id];
            let mut bases = vec![hit.base];
            bases.extend(&hit.rivals);
            let entry = c.entry(hit.id as usize).expect("hit tag exists");
            if print.bytes.is_empty() {
                fell_back += 1;
            }
            match judge(&process, print, &bases, || c.read_tag(hit.id as usize).ok()) {
                Some((base, f)) => {
                    verified.push(hit.id as usize);
                    if entry.group == "scenario" {
                        eprintln!(
                            "  scenario loaded: {} at {base:#x} ({:.0}% verified)",
                            entry.short,
                            f * 100.0
                        );
                    }
                }
                None => rejected += 1,
            }
        }
        eprintln!(
            "verified {} loaded tags ({rejected} rejected, {fell_back} read from the \
             containers) in {:.1?}; {:.1?} total",
            verified.len(),
            t2.elapsed(),
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
