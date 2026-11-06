//! `mjolnir jmad`: read, verify and rewrite animation graphs on disk.
//!
//! Works on extracted tag files, so nothing here needs the paks. A rewritten
//! graph goes into the game through `mjolnir new-tag --payload`.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use anyhow::{bail, Context, Result};
use blam_jmad::clip::Channel;
use blam_jmad::member::{set_bits, Member, SEGMENTS};
use blam_jmad::{child, rewrite, Clip, Graph, Skeleton, Spec};
use clap::{Args, Subcommand};
use serde::Serialize;
use serde_json::{json, Value};

#[derive(Args)]
pub struct JmadArgs {
    #[command(subcommand)]
    command: JmadCommand,
}

#[derive(Subcommand)]
enum JmadCommand {
    /// Print a graph's skeleton size, animations and how each is stored.
    Info {
        /// A `.model_animation_graph` file.
        file: PathBuf,
        /// List every node too.
        #[arg(long)]
        nodes: bool,
    },
    /// Decode every member of the graphs under a path and write each file
    /// back, requiring identical bytes.
    Roundtrip {
        /// A graph, or a directory searched for them.
        path: PathBuf,
    },
    /// Rewrite a graph for another skeleton, from a JSON spec (see
    /// docs/jmad_format.md). The output is a payload for `new-tag --payload`.
    Rewrite {
        /// The donor `.model_animation_graph` file.
        file: PathBuf,
        /// The JSON spec.
        #[arg(long)]
        spec: PathBuf,
        /// Where to write the payload.
        #[arg(long)]
        out: PathBuf,
    },
    /// Cut a graph down to the animations named, over a parent that supplies
    /// the rest (docs/jmad_format.md). The output is a payload for
    /// `new-tag --payload`.
    Child {
        /// The full `.model_animation_graph` file.
        file: PathBuf,
        /// The parent graph's tag path.
        #[arg(long)]
        parent: String,
        /// An animation to keep: its row, or the row of the mode it moved
        /// with. Repeatable.
        #[arg(long = "animation", required_unless_present = "modes")]
        animations: Vec<String>,
        /// A mode to carry whole under a new label, as DONOR=NEW, leaving the
        /// donor's label to the parent. Repeatable.
        #[arg(long = "mode", value_parser = mode_pair)]
        modes: Vec<(String, String)>,
        /// Keep every member of a resource group in use, not only the kept
        /// animations' own.
        #[arg(long)]
        whole_groups: bool,
        /// Where to write the payload.
        #[arg(long)]
        out: PathBuf,
    },
    /// Write a graph's skeleton and the decoded frames of named animations as
    /// JSON, for tools that pose against it.
    Frames {
        /// A `.model_animation_graph` file.
        file: PathBuf,
        /// An animation to include. Repeatable.
        #[arg(long = "animation", required = true)]
        animations: Vec<String>,
        /// Where to write the JSON.
        #[arg(long)]
        out: PathBuf,
    },
    /// Compare two graphs: every member, and the tag outside its resources.
    Diff {
        /// The donor.
        a: PathBuf,
        /// The rewrite.
        b: PathBuf,
    },
}

pub fn run(a: JmadArgs) -> Result<()> {
    match a.command {
        JmadCommand::Info { file, nodes } => info(&file, nodes),
        JmadCommand::Roundtrip { path } => roundtrip(&path),
        JmadCommand::Rewrite { file, spec, out } => rewrite_file(&file, &spec, &out),
        JmadCommand::Child {
            file,
            parent,
            animations,
            modes,
            whole_groups,
            out,
        } => child_file(&file, &parent, &animations, &modes, whole_groups, &out),
        JmadCommand::Frames {
            file,
            animations,
            out,
        } => frames(&file, &animations, &out),
        JmadCommand::Diff { a, b } => diff(&a, &b),
    }
}

fn read(path: &Path) -> Result<Vec<u8>> {
    std::fs::read(path).with_context(|| format!("cannot read {}", path.display()))
}

fn info(file: &Path, list_nodes: bool) -> Result<()> {
    let bytes = read(file)?;
    let g = Graph::read(&bytes)?;
    println!("{}", file.display());
    println!(
        "  {} nodes, {} animations, {} resource groups",
        g.nodes.len(),
        g.animations.len(),
        g.groups.len()
    );
    if list_nodes {
        for (i, n) in g.nodes.iter().enumerate() {
            let parent = n.parent.map_or("-".to_string(), |p| p.to_string());
            println!("  node {i:3} parent {parent:>3}  {}", n.name);
        }
    }
    for a in &g.animations {
        let Some(d) = &a.data else {
            println!("  {:40} (in another graph)", a.name);
            continue;
        };
        let Some(m) = g.member(d) else {
            println!("  {:40} (no member {}.{})", a.name, d.group, d.member);
            continue;
        };
        let moving = set_bits(&m.animated_flags.rotation).len();
        let opaque = m.opaque_segments();
        println!(
            "  {:40} group {:3}.{:<3} kind {} frames {:4} nodes {:3} codec {} rotating {:3} other segments {:?}",
            a.name,
            d.group,
            d.member,
            d.kind,
            d.frames,
            d.nodes,
            m.animated.codec(),
            moving,
            opaque
        );
    }
    Ok(())
}

fn find_graphs(path: &Path, out: &mut Vec<PathBuf>) -> Result<()> {
    if path.is_file() {
        out.push(path.to_path_buf());
        return Ok(());
    }
    for e in std::fs::read_dir(path).with_context(|| format!("cannot read {}", path.display()))? {
        let p = e?.path();
        if p.is_dir() {
            find_graphs(&p, out)?;
        } else if p.extension().is_some_and(|x| x == "model_animation_graph") {
            out.push(p);
        }
    }
    Ok(())
}

fn roundtrip(path: &Path) -> Result<()> {
    let mut files = Vec::new();
    find_graphs(path, &mut files)?;
    files.sort();
    let mut slots: BTreeMap<(u8, bool), usize> = BTreeMap::new();
    let mut segments: BTreeMap<usize, usize> = BTreeMap::new();
    let (mut members, mut bytes_total, mut stable, mut undecoded) =
        (0usize, 0usize, 0usize, 0usize);
    let mut failed = Vec::new();
    for p in &files {
        let file = read(p)?;
        bytes_total += file.len();
        let g = match Graph::read(&file) {
            Ok(g) => g,
            Err(e) => {
                failed.push(format!("{}: {e}", p.display()));
                continue;
            }
        };
        if g.write_resources(&file)? != file {
            failed.push(format!("{}: bytes differ", p.display()));
        }
        let parents = g.parents();
        let defaults = g.defaults();
        let skeleton = Skeleton {
            parents: &parents,
            defaults: &defaults,
        };
        for m in g.groups.iter().flatten().flat_map(|group| &group.members) {
            members += 1;
            let decoded = matches!(m.animated, blam_jmad::member::Animated::Frames(_));
            *slots.entry((m.animated.codec(), decoded)).or_default() += 1;
            for s in m.opaque_segments() {
                *segments.entry(s).or_default() += 1;
            }
            let Ok(clip) = Clip::read(m) else {
                undecoded += 1;
                continue;
            };
            // Encoding what was decoded, decoding that and encoding again
            // must not move a byte.
            let once = clip.write(skeleton, true, m.data_tail)?;
            let again = Clip::read(&once)?.write(skeleton, true, m.data_tail)?;
            if once.write() == again.write() {
                stable += 1;
            } else {
                failed.push(format!(
                    "{}: a member's encoding is not stable",
                    p.display()
                ));
            }
        }
    }
    println!(
        "{} files, {bytes_total} bytes, {members} members",
        files.len()
    );
    for ((codec, decoded), count) in &slots {
        let how = if *decoded {
            "decoded and re-encoded"
        } else {
            "carried as bytes"
        };
        println!("  compressed slot, codec {codec}: {count} ({how})");
    }
    println!("  segments carried as bytes: {segments:?}");
    println!("  re-encode stable: {stable} of {members}; no decodable frames: {undecoded}");
    if !failed.is_empty() {
        for f in failed.iter().take(20) {
            eprintln!("{f}");
        }
        bail!("{} failures", failed.len());
    }
    println!("every file came back byte for byte");
    Ok(())
}

/// `DONOR=NEW`, for `--mode`.
fn mode_pair(text: &str) -> Result<(String, String), String> {
    match text.split_once('=') {
        Some((donor, label)) if !donor.is_empty() && !label.is_empty() => {
            Ok((donor.to_string(), label.to_string()))
        }
        _ => Err(format!("{text:?} is not DONOR=NEW")),
    }
}

fn child_file(
    file: &Path,
    parent: &str,
    names: &[String],
    modes: &[(String, String)],
    whole_groups: bool,
    out: &Path,
) -> Result<()> {
    let bytes = read(file)?;
    let made = child(&bytes, parent, names, modes, whole_groups)?;

    // Accept only what our own reader gets back, with each member untouched.
    let full = Graph::read(&bytes)?;
    let g = Graph::read(&made.file).context("the child does not read back")?;
    if g.write_resources(&made.file)? != made.file {
        bail!("the child is not stable through the reader");
    }
    for name in names.iter().chain(g.animations.iter().map(|a| &a.name)) {
        let member = |graph: &'_ Graph| -> Option<Member> {
            let a = graph.animations.iter().find(|a| a.name == *name)?;
            graph.member(a.data.as_ref()?).cloned()
        };
        let (a, b) = (member(&full), member(&g));
        if a.is_none() || a != b {
            bail!("{name} did not come through unchanged");
        }
    }
    std::fs::write(out, &made.file).with_context(|| format!("cannot write {}", out.display()))?;
    println!(
        "{} animations -> {}, {} resource groups -> {}",
        full.animations.len(),
        g.animations.len(),
        full.groups.len(),
        g.groups.len()
    );
    for row in &made.rows {
        println!("  row  {row}");
    }
    for row in &made.left_to_parent {
        println!("  left to the parent, which plays its own frames: {row}");
    }
    for what in &made.cleared {
        println!("  cleared {what}");
    }
    if made.overlay_groups != 0 {
        println!(
            "  own overlay groups {}, blend screens {}",
            made.overlay_groups, made.blend_screens
        );
    }
    println!(
        "  payload {} bytes, from {} -> {}",
        made.file.len(),
        bytes.len(),
        out.display()
    );
    Ok(())
}

fn rewrite_file(file: &Path, spec: &Path, out: &Path) -> Result<()> {
    let bytes = read(file)?;
    let text =
        std::fs::read_to_string(spec).with_context(|| format!("cannot read {}", spec.display()))?;
    let spec: Spec = serde_json::from_str(&text)
        .with_context(|| format!("{} is not a jmad spec", spec.display()))?;
    let donor = Graph::read(&bytes)?;
    let plan = spec.resolve(&donor)?;
    let written = rewrite(&bytes, &plan)?;

    // Accept only what our own reader gets back, unchanged, at the new size.
    let g = Graph::read(&written).context("the rewritten graph does not read back")?;
    if g.write_resources(&written)? != written {
        bail!("the rewritten graph is not stable through the reader");
    }
    for a in &g.animations {
        if let Some(d) = &a.data {
            if d.nodes as usize != g.nodes.len() {
                bail!(
                    "{} has {} nodes in a skeleton of {}",
                    a.name,
                    d.nodes,
                    g.nodes.len()
                );
            }
        }
    }
    std::fs::write(out, &written).with_context(|| format!("cannot write {}", out.display()))?;
    println!(
        "{} nodes -> {} nodes, {} animations edited",
        donor.nodes.len(),
        g.nodes.len(),
        plan.edits.len()
    );
    println!("  payload {} bytes -> {}", written.len(), out.display());
    Ok(())
}

fn channel_json<T: Serialize>(c: &Channel<T>) -> Value {
    match c {
        Channel::Absent => Value::Null,
        Channel::Static(v) => json!({ "static": v }),
        Channel::Animated(v) => json!({ "each": v }),
    }
}

fn frames(file: &Path, names: &[String], out: &Path) -> Result<()> {
    let bytes = read(file)?;
    let g = Graph::read(&bytes)?;
    let nodes: Vec<Value> = g
        .nodes
        .iter()
        .map(|n| {
            json!({
                "name": n.name,
                "parent": n.parent,
                "default": {
                    "rotation": n.default.rotation,
                    "translation": n.default.translation,
                    "scale": n.default.scale,
                },
            })
        })
        .collect();
    let mut animations = serde_json::Map::new();
    for name in names {
        let found = g.animations.iter().find(|a| &a.name == name);
        let data = found
            .and_then(|a| a.data.as_ref())
            .with_context(|| format!("no animation {name} with frames of its own"))?;
        let m = g
            .member(data)
            .with_context(|| format!("{name}: no member {}.{}", data.group, data.member))?;
        let clip = Clip::read(m)?;
        let tracks: Vec<Value> = clip
            .nodes
            .iter()
            .map(|t| {
                json!({
                    "rotation": channel_json(&t.rotation),
                    "translation": channel_json(&t.translation),
                    "scale": channel_json(&t.scale),
                })
            })
            .collect();
        animations.insert(
            name.clone(),
            json!({
                "frames": clip.frames,
                "kind": data.kind,
                "object_space": m.object_space.is_some(),
                "segments": m.opaque_segments(),
                "tracks": tracks,
            }),
        );
    }
    let text = serde_json::to_string(&json!({ "nodes": nodes, "animations": animations }))?;
    std::fs::write(out, text).with_context(|| format!("cannot write {}", out.display()))?;
    println!("{} animations -> {}", names.len(), out.display());
    Ok(())
}

/// The sizes of the segments that differ between two members' blobs.
fn segment_changes(a: &Member, b: &Member) -> Vec<String> {
    let parts = |m: &Member| {
        let (record, blob) = m.write();
        let mut at = 0;
        (0..SEGMENTS)
            .map(|i| {
                let size = u32::from_le_bytes(record[12 + 4 * i..16 + 4 * i].try_into().unwrap());
                let part = blob[at..at + size as usize].to_vec();
                at += size as usize;
                part
            })
            .collect::<Vec<_>>()
    };
    let (pa, pb) = (parts(a), parts(b));
    (0..SEGMENTS)
        .filter(|&i| pa[i] != pb[i])
        .map(|i| format!("{i}: {} -> {}", pa[i].len(), pb[i].len()))
        .collect()
}

fn diff(a: &Path, b: &Path) -> Result<()> {
    let (fa, fb) = (read(a)?, read(b)?);
    let (ga, gb) = (Graph::read(&fa)?, Graph::read(&fb)?);
    if ga.groups.len() != gb.groups.len() {
        bail!(
            "{} and {} resource groups",
            ga.groups.len(),
            gb.groups.len()
        );
    }
    let (mut same, mut changed) = (0usize, 0usize);
    for (gi, (x, y)) in ga.groups.iter().zip(&gb.groups).enumerate() {
        let (Some(x), Some(y)) = (x, y) else {
            if x.is_some() != y.is_some() {
                println!("group {gi}: a resource on one side only");
                changed += 1;
            }
            continue;
        };
        if x.members.len() != y.members.len() {
            bail!(
                "group {gi}: {} and {} members",
                x.members.len(),
                y.members.len()
            );
        }
        for (mi, (p, q)) in x.members.iter().zip(&y.members).enumerate() {
            if p.write() == q.write() {
                same += 1;
                continue;
            }
            changed += 1;
            let name = ga
                .animations
                .iter()
                .find(|n| n.data.is_some_and(|d| d.group == gi && d.member == mi))
                .map_or("<no animation>", |n| n.name.as_str());
            println!(
                "member {gi}.{mi} {name}: segments {}",
                segment_changes(p, q).join(", ")
            );
        }
    }
    println!("{same} members identical, {changed} changed");
    // With a's resources put into b, what is left is the tag around them.
    let outside = ga.write_resources(&fb)? == fa;
    println!(
        "tag outside the resources: {}",
        if outside { "identical" } else { "differs" }
    );
    Ok(())
}
