//! Replace selected indexed members in a single IoStore container, retaining its identity and directory.
//! Usage: replace_members original.utoc path-matched-replacement-directory output-directory
use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
};
use ue_iostore::{
    pack::{build_indexed, Entry},
    toc::Toc,
};

fn files_under(root: &Path, here: &Path, files: &mut BTreeSet<String>) -> std::io::Result<()> {
    for entry in std::fs::read_dir(here)? {
        let path = entry?.path();
        if path.is_dir() {
            files_under(root, &path, files)?;
        } else {
            files.insert(
                path.strip_prefix(root)
                    .unwrap()
                    .to_str()
                    .unwrap()
                    .replace('\\', "/"),
            );
        }
    }
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<PathBuf> = std::env::args_os().skip(1).map(PathBuf::from).collect();
    if args.len() != 3 {
        return Err("usage: replace_members original.utoc replacements out".into());
    }
    let (source, folder, out) = (&args[0], &args[1], &args[2]);
    if out
        .join(source.file_name().ok_or("source filename")?)
        .exists()
    {
        return Err("Output exists".into());
    }
    let available = ue_iostore::load_all(source.parent().ok_or("source path")?)?;
    let owner = available
        .iter()
        .find(|c| c.utoc_path.file_name() == source.file_name())
        .ok_or("missing owner")?;
    let mut supplied = BTreeSet::new();
    files_under(folder, folder, &mut supplied)?;
    if supplied.is_empty() {
        return Err("No replacements".into());
    }
    let toc = Toc::read(source)?;
    let by_index: BTreeMap<_, _> = owner.files.iter().map(|(p, i)| (*i, p)).collect();
    let mut order: Vec<_> = owner.chunks.iter().collect();
    order.sort_by_key(|ch| ch.offset);
    let mut entries = Vec::with_capacity(order.len());
    let mut directory = Vec::new();
    for ch in order {
        let mut data = ue_iostore::read_chunk(owner, ch, None, &[])?;
        if let Some(path) = by_index.get(&ch.index) {
            let normalized = path.replace('\\', "/");
            if supplied.remove(&normalized) {
                let new = std::fs::read(folder.join(&normalized))?;
                println!("{}: {} -> {} bytes", normalized, data.len(), new.len());
                data = new;
            }
            directory.push(((*path).to_string(), entries.len()));
        }
        entries.push(Entry {
            // ShaderCode hashes occupy all eleven bytes before the chunk type.
            id: toc.chunk_ids[ch.index],
            data,
            meta: Vec::new(),
        });
    }
    if !supplied.is_empty() {
        return Err(format!("Replacement(s) have no original owner: {:?}", supplied).into());
    }
    let built = build_indexed(
        &toc,
        owner.container_id,
        &entries,
        Some((&owner.mount_point, &directory)),
    );
    std::fs::create_dir_all(out)?;
    let output = out.join(source.file_name().unwrap());
    std::fs::write(&output, built.utoc)?;
    std::fs::write(output.with_extension("ucas"), built.ucas)?;
    let back = ue_iostore::load_all(out)?;
    let sealed = back
        .iter()
        .find(|c| c.utoc_path.file_name() == source.file_name())
        .ok_or("missing result")?;
    if sealed.chunks.len() != entries.len() || sealed.files.len() != directory.len() {
        return Err("Result inventory changed".into());
    }
    let sealed_toc = Toc::read(&output)?;
    let intended: BTreeMap<_, _> = entries
        .iter()
        .map(|e| (e.id.bytes(), &e.data))
        .collect();
    for ch in &sealed.chunks {
        let id = &sealed_toc.chunk_ids[ch.index];
        let expected = intended
            .get(&id.bytes())
            .ok_or("Unexpected member")?;
        if sealed_toc.find_chunk(id) != Some(ch.index) {
            return Err("Chunk cannot be located by its complete ID".into());
        }
        if ue_iostore::read_chunk(sealed, ch, None, &[])?.as_slice() != expected.as_slice() {
            return Err("Member round trip changed".into());
        }
    }
    println!(
        "Verified {} chunks, {} paths",
        sealed.chunks.len(),
        sealed.files.len()
    );
    Ok(())
}
