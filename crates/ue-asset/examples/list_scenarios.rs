//! List every "*-scenario" tag package across the installed containers.
fn main() {
    let paks = std::env::args().nth(1).expect("usage: list_scenarios <paks>");
    let containers = ue_iostore::load_all(&paks).expect("load containers");
    let mut hits: Vec<(String, String, u64)> = Vec::new();
    for c in &containers {
        for (path, idx) in &c.files {
            if path.to_lowercase().contains("-scenario") {
                hits.push((
                    path.clone(),
                    c.utoc_path.file_name().unwrap().to_string_lossy().to_string(),
                    c.chunks[*idx].length,
                ));
            }
        }
    }
    hits.sort();
    for (p, c, n) in &hits {
        println!("{p}  [{c}]  {n} bytes");
    }
    println!("{} scenario-ish packages", hits.len());
}
