//! Census of the Halo 2 shaders across a set of maps: every `shad` tag by
//! its template, with the maps it is on, the passes the template draws
//! (`spas` its `stem` references), how many shaders use each bitmap slot
//! (a placeholder counts as unused) and a few example names. The shared
//! map's shaders count once, as "shared".
//!
//!   h2_shader_census <maps dir> <out.json>
use blam_cache::h2::{Cache, CacheFile, Group, Struct};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

#[derive(Default)]
struct Row {
    shaders: BTreeSet<String>,
    maps: BTreeSet<String>,
    passes: Vec<String>,
    slots: BTreeMap<usize, usize>,
}

fn placeholder(name: &str) -> bool {
    let n = name.to_ascii_lowercase();
    n.contains("default_bitmaps") || n.starts_with("rasterizer")
}

/// The passes a template draws, in order: its postprocess definition's
/// pass block (stem +0x58, definition +0x10, 10 bytes: the `spas`
/// reference first). Each pass's specular colours, where it feeds vertex
/// registers 10 and 11 from the shader's vertex constants
/// (`stencil_light_specular_tangentspace_sphere` copies them to the pixel
/// shader), follow its name as `[vc a, vc b]`.
fn passes(stem: &blam_cache::h2::Tag<'_>) -> Vec<String> {
    let Some(d) = stem.root.block(0x58, 0x28).get(0) else { return Vec::new() };
    let imps = d.block(0x18, 6);
    let remaps = d.block(0x20, 4);
    let range = |v: u16| ((v & 0x1FF) as usize, (v >> 9) as usize);
    let mut out = Vec::new();
    for pass in d.block(0x10, 10).iter() {
        let mut leaf = stem.file.entry(pass.u32(4)).map(|t| t.name.rsplit('\\').next().unwrap_or("").to_string()).unwrap_or_default();
        let (start, count) = range(pass.u16(8));
        let mut regs = [None, None];
        for i in start..start + count {
            let Some(im) = imps.get(i) else { continue };
            let (s, n) = range(im.u16(4));
            for r in (s..s + n).filter_map(|r| remaps.get(r)) {
                let v = r.u16(0);
                if (v >> 10) & 7 == 7 && matches!(v & 31, 10 | 11) {
                    regs[(v & 31) as usize - 10] = Some(r.u8(3));
                }
            }
        }
        if let [Some(a), Some(b)] = regs {
            leaf = format!("{leaf} [vc {a}, vc {b}]");
        }
        out.push(leaf);
    }
    out
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let dir = Path::new(&a[1]);
    let mut maps: Vec<_> = std::fs::read_dir(dir)
        .expect("maps dir")
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|x| x == "map"))
        .filter(|p| !matches!(p.file_stem().and_then(|s| s.to_str()), Some("shared" | "mainmenu")))
        .collect();
    maps.sort();
    let mut rows: BTreeMap<String, Row> = BTreeMap::new();
    let mut shared_done = false;
    for path in &maps {
        let name = path.file_stem().unwrap().to_string_lossy().to_string();
        let cache = match Cache::open(path, None) {
            Ok(c) => c,
            Err(e) => {
                eprintln!("{name}: {e}");
                continue;
            }
        };
        let mut files: Vec<(&CacheFile, String)> = vec![(&cache.map, name.clone())];
        if !shared_done {
            if let Some(s) = cache.shared.as_ref() {
                files.push((s, "shared".into()));
                shared_done = true;
            }
        }
        let mut n = 0;
        for (file, label) in files {
            for e in file.tags.iter().filter(|e| e.group == Group::new(b"shad")) {
                let Some(off) = e.address.and_then(|x| file.offset(x)) else { continue };
                let root = Struct { file, at: off };
                let Some(stem) = root.tagref(0).and_then(|r| cache.follow(r)) else { continue };
                let template = stem.name().rsplit('\\').next().unwrap_or("").to_string();
                let row = rows.entry(template).or_default();
                if row.passes.is_empty() {
                    row.passes = passes(&stem);
                }
                if row.shaders.insert(e.name.clone()) {
                    if let Some(p) = root.block(0x20, 0x7C).get(0) {
                        for (s, b) in p.block(0x04, 0x0C).iter().enumerate() {
                            let used = cache.tag(file, b.u32(0)).is_some_and(|t| !placeholder(t.name()));
                            if used {
                                *row.slots.entry(s).or_default() += 1;
                            }
                        }
                    }
                }
                row.maps.insert(label.clone());
                n += 1;
            }
        }
        eprintln!("{name}: {n} shader(s)");
    }
    let out: Vec<Value> = rows
        .iter()
        .map(|(t, r)| {
            json!({
                "template": t, "shaders": r.shaders.len(), "maps": r.maps,
                "passes": r.passes, "slots_used": r.slots,
                "examples": r.shaders.iter().take(4).collect::<Vec<_>>(),
            })
        })
        .collect();
    std::fs::write(&a[2], serde_json::to_string_pretty(&out).unwrap()).expect("write");
    eprintln!("{} template(s) -> {}", rows.len(), a[2]);
}
