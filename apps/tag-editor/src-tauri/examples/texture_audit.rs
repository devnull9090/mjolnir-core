//! Decode every texture in the catalog and report the coverage, so a change
//! to the reader can be checked against a whole installation rather than a
//! handful of samples.
//!
//! Usage: cargo run --release --example texture_audit [-- <paks> <oodle>]

use std::collections::BTreeMap;

use tag_editor_lib::{catalog::Catalog, install, textures};

/// Collapse digit runs so like failures group into one bucket.
fn bucket(msg: &str) -> String {
    let mut out = String::new();
    let mut in_num = false;
    for ch in msg.chars() {
        if ch.is_ascii_digit() {
            if !in_num {
                out.push('#');
            }
            in_num = true;
        } else {
            in_num = false;
            out.push(ch);
        }
    }
    out
}

fn main() {
    let found = install::detect();
    let paks = std::env::args().nth(1).or(found.paks).expect("no paks dir");
    let oodle = std::env::args().nth(2).or(found.oodle).expect("no oodle dll");
    let c = Catalog::open(&paks, &oodle).expect("open catalog");
    eprintln!("{} textures in {paks}", c.textures.len());

    let mut by_format: BTreeMap<String, usize> = BTreeMap::new();
    let mut flat: Vec<String> = Vec::new();
    let mut errs: BTreeMap<String, Vec<String>> = BTreeMap::new();

    for (i, t) in c.textures.iter().enumerate() {
        let decoded = (|| -> Result<(String, bool), String> {
            let uasset = c.read_texture_uasset(i)?;
            let header = textures::zen_header_size(&uasset).ok_or("not a zen package")?;
            let tex = textures::parse_texture(&uasset[header..])?;
            // A texture whose mips are all inline has no bulk file at all.
            let ubulk = c.read_texture_ubulk(i).unwrap_or_default();
            let mut mip = 0;
            while mip + 1 < tex.num_mips {
                let (w, h) = tex.mip_dims(mip);
                if w.max(h) <= 4096 {
                    break;
                }
                mip += 1;
            }
            let img = textures::assemble_mip(&tex, &ubulk, mip)?;
            let head = &img.rgba[..4];
            let uniform = img.rgba.chunks(4).all(|p| p == head);
            Ok((tex.format.clone(), uniform))
        })();
        match decoded {
            Ok((format, uniform)) => {
                *by_format.entry(format).or_default() += 1;
                if uniform {
                    flat.push(t.short.clone());
                }
            }
            Err(e) => errs.entry(bucket(&e)).or_default().push(t.short.clone()),
        }
        if i % 500 == 0 {
            eprintln!("  {i}/{}", c.textures.len());
        }
    }

    let ok: usize = by_format.values().sum();
    println!("\n=== {ok} decoded / {} total ===", c.textures.len());
    println!("\nby pixel format:");
    for (f, n) in &by_format {
        println!("  {n:6}  {f}");
    }

    // Not a failure: the build ships placeholder and default textures that are
    // a single colour on purpose. Listed because it is also what a silent
    // decode failure would look like.
    println!("\n{} decoded to a single flat colour, e.g.:", flat.len());
    for n in flat.iter().take(5) {
        println!("          {n}");
    }

    let mut buckets: Vec<_> = errs.iter().collect();
    buckets.sort_by_key(|(_, v)| std::cmp::Reverse(v.len()));
    let failed: usize = errs.values().map(|v| v.len()).sum();
    println!("\n{failed} could not be decoded:");
    for (b, names) in buckets {
        println!("  {:6}  {b}", names.len());
        for n in names.iter().take(3) {
            println!("            e.g. {n}");
        }
    }
}
