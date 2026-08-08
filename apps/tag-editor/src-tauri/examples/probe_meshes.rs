//! Survey the raw IoStore index for UE mesh/material/blueprint packages —
//! the assets the catalog deliberately does not index. Counts paths by
//! bucket and prints samples matching an optional query.
//!
//!   cargo run --example probe_meshes -- Elite

use tag_editor_lib::install;

fn main() -> Result<(), String> {
    let query = std::env::args().nth(1).unwrap_or_default().to_lowercase();

    let found = install::detect();
    let paks = found.paks.ok_or("no install")?;
    let containers = ue_iostore::load_all(&paks).map_err(|e| e.to_string())?;

    let mut buckets: std::collections::BTreeMap<&str, (u64, u64)> = Default::default();
    let mut samples: Vec<(String, u64)> = Vec::new();

    for c in &containers {
        for (rel, &idx) in &c.files {
            let full = c.full_path(rel);
            let lower = full.to_lowercase();
            let len = c.chunks[idx].length;
            let leaf = lower.rsplit('/').next().unwrap_or("");
            let bucket = if lower.contains("/tags/") {
                "blam tag"
            } else if leaf.starts_with("sk_") {
                "SK_ skeletal mesh"
            } else if leaf.starts_with("sm_") {
                "SM_ static mesh"
            } else if leaf.starts_with("t_") || lower.contains("/textures/") {
                "texture"
            } else if leaf.starts_with("m_") || leaf.starts_with("mi_") || lower.contains("/materials/") {
                "material"
            } else if leaf.starts_with("bp_") {
                "blueprint"
            } else if leaf.ends_with(".umap") {
                "umap"
            } else if lower.contains("/meshes/") {
                "other in /Meshes/"
            } else {
                "other"
            };
            let e = buckets.entry(bucket).or_default();
            e.0 += 1;
            e.1 += len;
            if !query.is_empty()
                && lower.contains(&query)
                && (leaf.starts_with("sk_") || leaf.starts_with("sm_") || lower.contains("/meshes/"))
            {
                samples.push((full.clone(), len));
            }
        }
    }

    println!("== buckets (files, bytes) ==");
    for (name, (count, bytes)) in &buckets {
        println!("  {:>8} files  {:>10.1} MiB  {}", count, *bytes as f64 / (1 << 20) as f64, name);
    }

    samples.sort();
    println!("\n== mesh-ish paths matching {query:?} ({}) ==", samples.len());
    for (path, len) in samples.iter().take(40) {
        println!("  {:>9} b  {}", len, path);
    }
    Ok(())
}
