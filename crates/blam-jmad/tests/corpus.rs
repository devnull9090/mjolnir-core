//! Checks over real tags. Point `JMAD_CORPUS` at a directory of extracted
//! graphs (`mjolnir extract --group model_animation_graph --shipped-only`);
//! game data stays out of the repository, so without it these pass empty.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use blam_jmad::graph::{link, AnimationEdit};
use blam_jmad::member::{has_bit, set_bits};
use blam_jmad::{rewrite, Channel, Clip, Graph, NodeSpec, Rewrite, Skeleton, Spec, Track};

fn walk(dir: &Path, out: &mut Vec<PathBuf>) {
    for e in std::fs::read_dir(dir).unwrap().flatten() {
        let p = e.path();
        if p.is_dir() {
            walk(&p, out);
        } else if p.extension().is_some_and(|x| x == "model_animation_graph") {
            out.push(p);
        }
    }
}

fn corpus() -> Vec<PathBuf> {
    let Ok(dir) = std::env::var("JMAD_CORPUS") else {
        eprintln!("JMAD_CORPUS not set: skipping");
        return Vec::new();
    };
    let mut out = Vec::new();
    walk(Path::new(&dir), &mut out);
    out.sort();
    out
}

fn tag(leaf: &str) -> Option<Vec<u8>> {
    corpus()
        .iter()
        .find(|p| p.ends_with(leaf))
        .map(|p| std::fs::read(p).unwrap())
}

/// Every graph decodes and writes back identical, whole file.
#[test]
fn shipped_graphs_write_back_byte_for_byte() {
    let mut members = 0;
    let mut codecs = BTreeMap::new();
    for p in corpus() {
        let file = std::fs::read(&p).unwrap();
        let graph = Graph::read(&file).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        let back = graph.write_resources(&file).unwrap();
        assert!(back == file, "{} differs", p.display());
        for m in graph.groups.iter().flatten().flat_map(|g| &g.members) {
            members += 1;
            *codecs.entry(m.animated.codec()).or_insert(0) += 1;
        }
    }
    eprintln!("{members} members, compressed slot by codec: {codecs:?}");
}

/// What the rewrite's rules rest on, measured on every graph.
#[test]
fn shipped_graphs_keep_the_rules_the_writer_assumes() {
    let mut worst_base = 0f32;
    let mut no_frames = 0;
    let mut orders = BTreeMap::new();
    for p in corpus() {
        let file = std::fs::read(&p).unwrap();
        let g = Graph::read(&file).unwrap();
        let name = p.display();
        let parents = g.parents();
        let defaults = g.defaults();
        let links = link(&parents, &g.sibling_ranks());
        for (i, n) in g.nodes.iter().enumerate() {
            assert_eq!(
                (n.first_child, n.next_sibling),
                links[i],
                "{name}: node {i} links"
            );
        }
        let falling = link(
            &parents,
            &vec![0; parents.len()]
                .iter()
                .enumerate()
                .map(|(i, _)| usize::MAX - i)
                .collect::<Vec<_>>(),
        );
        let rising = link(&parents, &vec![0; parents.len()]);
        *orders
            .entry((links == falling, links == rising))
            .or_insert(0) += 1;
        for a in &g.animations {
            let Some(d) = &a.data else { continue };
            let m = g
                .member(d)
                .unwrap_or_else(|| panic!("{name}: {} has no member", a.name));
            assert_eq!(
                d.nodes as usize,
                g.nodes.len(),
                "{name}: {} node count",
                a.name
            );
            assert_eq!(
                (d.nodes, d.frames, d.movement_kind),
                (m.nodes, m.frames, m.movement_kind),
                "{name}: {}",
                a.name
            );
            let (s, f) = (&m.static_flags, &m.animated_flags);
            for (x, y) in [
                (&s.rotation, &f.rotation),
                (&s.translation, &f.translation),
                (&s.scale, &f.scale),
            ] {
                assert!(
                    x.iter().zip(y).all(|(a, b)| a & b == 0),
                    "{name}: {} static and animated overlap",
                    a.name
                );
            }
            if let Some(os) = &m.object_space {
                assert_eq!(os.frames as i16, m.frames, "{name}: {}", a.name);
                for i in 0..g.nodes.len() {
                    let posed = has_bit(&s.rotation, i)
                        || has_bit(&f.rotation, i)
                        || has_bit(&s.translation, i)
                        || has_bit(&f.translation, i)
                        || has_bit(&s.scale, i)
                        || has_bit(&f.scale, i);
                    assert_eq!(
                        posed,
                        has_bit(&os.mask, i),
                        "{name}: {} mask node {i}",
                        a.name
                    );
                }
                if d.kind == 1 {
                    if let Ok(clip) = Clip::read(m) {
                        let want = clip.object_space(Skeleton {
                            parents: &parents,
                            defaults: &defaults,
                        });
                        assert_eq!(want.mask, os.mask);
                        for (a, b) in want.poses.iter().zip(&os.poses) {
                            let rot = (0..4)
                                .map(|c| (a[c] - b[c]).abs())
                                .fold(0f32, f32::max)
                                .min((0..4).map(|c| (a[c] + b[c]).abs()).fold(0f32, f32::max));
                            let rest = (4..8).map(|c| (a[c] - b[c]).abs()).fold(0f32, f32::max);
                            worst_base = worst_base.max(rot).max(rest);
                        }
                    }
                }
            }
            if m.raw.is_none() {
                no_frames += 1;
            }
        }
    }
    eprintln!("base object space vs forward kinematics: worst {worst_base}; members with no raw copy {no_frames}; sibling orders (falling, rising) {orders:?}");
}

/// The experiment: Warthog `any:idle` and everything else at another node
/// count, then through our reader and writer again.
#[test]
fn the_warthog_rewrites_for_fewer_nodes() {
    let Some(file) = tag("warthog/warthog.model_animation_graph") else {
        return;
    };
    let donor = Graph::read(&file).unwrap();
    let keep: Vec<String> = [
        "pedestal",
        "root",
        "chassis",
        "body",
        "steering_wheel",
        "suspension_arm_front_right",
    ]
    .map(String::from)
    .to_vec();
    let spec = Spec {
        keep,
        ..Default::default()
    };
    let plan = spec.resolve(&donor).unwrap();
    let out = rewrite(&file, &plan).unwrap();

    let g = Graph::read(&out).unwrap();
    assert_eq!(g.nodes.len(), 6);
    assert_eq!(g.animations.len(), donor.animations.len());
    for a in &g.animations {
        let d = a.data.unwrap();
        assert_eq!(d.nodes, 6, "{}", a.name);
        let m = g.member(&d).unwrap();
        assert_eq!(m.nodes, 6);
    }
    assert!(
        g.write_resources(&out).unwrap() == out,
        "not stable through the reader"
    );

    // The kept nodes' idle frames are the donor's.
    let idle = |g: &Graph| {
        let d = g
            .animations
            .iter()
            .find(|a| a.name == "any:idle")
            .unwrap()
            .data
            .unwrap();
        Clip::read(g.member(&d).unwrap()).unwrap()
    };
    let (before, after) = (idle(&donor), idle(&g));
    for (i, s) in plan.nodes.iter().enumerate() {
        let parent_is_donors = s.parent.map(|p| plan.nodes[p].source)
            == donor.nodes[s.source.unwrap()].parent.map(Some);
        if parent_is_donors {
            assert_eq!(
                after.nodes[i],
                before.nodes[s.source.unwrap()],
                "{}",
                s.name
            );
        }
    }

    // Every animation decoded from the new tag encodes to the same bytes.
    let parents = g.parents();
    let defaults = g.defaults();
    let skeleton = Skeleton {
        parents: &parents,
        defaults: &defaults,
    };
    for a in &g.animations {
        let m = g.member(a.data.as_ref().unwrap()).unwrap();
        let again = Clip::read(m)
            .unwrap()
            .write(skeleton, false, m.data_tail)
            .unwrap();
        assert_eq!(again.static_pose, m.static_pose, "{}", a.name);
        assert_eq!(again.animated, m.animated, "{}", a.name);
        assert_eq!(again.raw, m.raw, "{}", a.name);
        assert_eq!(again.static_flags, m.static_flags, "{}", a.name);
        assert_eq!(again.animated_flags, m.animated_flags, "{}", a.name);
        assert_eq!(again.opaque, m.opaque, "{}", a.name);
    }
}

#[test]
fn the_warthog_takes_a_node_of_its_own() {
    let Some(file) = tag("warthog/warthog.model_animation_graph") else {
        return;
    };
    let donor = Graph::read(&file).unwrap();
    let spec: Spec = serde_json::from_str(
        r#"{ "keep": ["pedestal", "root", "chassis"],
             "nodes": [{ "name": "handlebar", "parent": "chassis", "translation": [0.5, 0, 0.25] }],
             "animations": [{ "name": "any:idle", "frames": 3,
                "nodes": { "handlebar": { "rotation": [[0,0,0,1],[0,0,0.3826834,0.9238795],[0,0,0.7071068,0.7071068]] } } }] }"#,
    )
    .unwrap();
    let plan = spec.resolve(&donor).unwrap();
    let out = rewrite(&file, &plan).unwrap();
    let g = Graph::read(&out).unwrap();
    assert_eq!(g.nodes[3].name, "handlebar");
    assert_eq!(g.nodes[2].first_child, Some(3));
    let d = g
        .animations
        .iter()
        .find(|a| a.name == "any:idle")
        .unwrap()
        .data
        .unwrap();
    assert_eq!((d.nodes, d.frames), (4, 3));
    let m = g.member(&d).unwrap();
    assert_eq!(set_bits(&m.animated_flags.rotation), vec![3]);
    assert!(g.write_resources(&out).unwrap() == out);
}

/// Every member through codec 3, on the shipped skeleton: what the in-game
/// check of the encoder installs.
#[test]
fn the_warthog_reencodes_whole() {
    let Some(file) = tag("warthog/warthog.model_animation_graph") else {
        return;
    };
    let donor = Graph::read(&file).unwrap();
    let plan = Spec {
        reencode: true,
        ..Default::default()
    }
    .resolve(&donor)
    .unwrap();
    let out = rewrite(&file, &plan).unwrap();
    let g = Graph::read(&out).unwrap();
    assert_eq!(g.nodes, donor.nodes);
    for (a, b) in g.animations.iter().zip(&donor.animations) {
        let (m, d) = (
            g.member(a.data.as_ref().unwrap()).unwrap(),
            donor.member(b.data.as_ref().unwrap()).unwrap(),
        );
        assert_eq!(m.animated.codec(), 3, "{}", a.name);
        assert_eq!(m.raw, d.raw, "{}", a.name);
        assert_eq!(m.object_space, d.object_space, "{}", a.name);
        assert_eq!(m.static_flags, d.static_flags, "{}", a.name);
        assert_eq!(m.animated_flags, d.animated_flags, "{}", a.name);
        assert_eq!(
            m.static_pose.rotations, d.static_pose.rotations,
            "{}",
            a.name
        );
        assert_eq!(m.opaque, d.opaque, "{}", a.name);
        assert_eq!(
            (m.checksum, m.animation_index),
            (d.checksum, d.animation_index),
            "{}",
            a.name
        );
    }
    assert!(g.write_resources(&out).unwrap() == out);
}

/// An edit to an overlay keeps the stored object-space frames of the nodes it
/// does not move.
#[test]
fn an_overlay_edit_leaves_other_nodes_object_frames_alone() {
    let Some(file) = tag("warthog/warthog.model_animation_graph") else {
        return;
    };
    let donor = Graph::read(&file).unwrap();
    let spec: Spec = serde_json::from_str(
        r#"{ "animations": [{ "name": "vehicle:steering", "frames": 5,
                "nodes": { "steering_wheel": { "rotation": [0, 0, 0, 1] } } }] }"#,
    )
    .unwrap();
    let out = rewrite(&file, &spec.resolve(&donor).unwrap()).unwrap();
    let g = Graph::read(&out).unwrap();
    let frames = |g: &Graph| {
        let d = g
            .animations
            .iter()
            .find(|a| a.name == "vehicle:steering")
            .unwrap()
            .data
            .unwrap();
        g.member(&d).unwrap().object_space.clone().unwrap()
    };
    let (before, after) = (frames(&donor), frames(&g));
    assert_eq!(before.mask, after.mask);
    let wheel = donor
        .nodes
        .iter()
        .position(|n| n.name == "steering_wheel")
        .unwrap();
    let f = before.frames;
    for (k, node) in set_bits(&before.mask).into_iter().enumerate() {
        let same = before.poses[k * f..(k + 1) * f] == after.poses[k * f..(k + 1) * f];
        assert!(same || node == wheel, "{}", donor.nodes[node].name);
    }
}

/// An identity rewrite leaves the file alone.
#[test]
fn the_same_nodes_change_nothing() {
    for leaf in [
        "warthog/warthog.model_animation_graph",
        "elevator_a/elevator_a_b40.model_animation_graph",
    ] {
        let Some(file) = tag(leaf) else { continue };
        let g = Graph::read(&file).unwrap();
        let nodes = g
            .nodes
            .iter()
            .enumerate()
            .map(|(i, n)| NodeSpec {
                name: n.name.clone(),
                parent: n.parent,
                source: Some(i),
                default: None,
            })
            .collect();
        let out = rewrite(
            &file,
            &Rewrite {
                nodes,
                ..Default::default()
            },
        )
        .unwrap();
        assert!(Graph::read(&out).unwrap() == g, "{leaf}");
        assert!(out.len() == file.len(), "{leaf}");
    }
}

/// Every vehicle's graph takes a node list change: the data a rewrite refuses
/// belongs to bipeds.
#[test]
fn vehicle_graphs_lose_a_node() {
    let mut refused = Vec::new();
    let mut done = 0;
    for p in corpus()
        .iter()
        .filter(|p| p.to_string_lossy().contains("Vehicles"))
    {
        let file = std::fs::read(p).unwrap();
        let g = Graph::read(&file).unwrap();
        let Some(leaf) = (0..g.nodes.len())
            .rev()
            .find(|&i| g.nodes[i].first_child.is_none() && g.nodes.len() > 1)
        else {
            continue;
        };
        let keep = g
            .nodes
            .iter()
            .enumerate()
            .filter(|(i, _)| *i != leaf)
            .map(|(_, n)| n.name.clone())
            .collect();
        let plan = Spec {
            keep,
            ..Default::default()
        }
        .resolve(&g)
        .unwrap();
        match rewrite(&file, &plan) {
            Ok(out) => {
                assert_eq!(Graph::read(&out).unwrap().nodes.len(), g.nodes.len() - 1);
                done += 1;
            }
            Err(e) => refused.push(format!("{}: {e}", p.display())),
        }
    }
    eprintln!(
        "vehicle graphs rewritten: {done}, refused: {}",
        refused.len()
    );
    for r in refused.iter().take(12) {
        eprintln!("  {}", &r[r.len().saturating_sub(180)..]);
    }
}

/// An edit on a graph with IK chains keeps the member's chain segments, and
/// nothing else in the graph moves.
#[test]
fn the_spartan_keeps_its_chains_through_an_edit() {
    let Some(file) = tag("spartans.model_animation_graph") else {
        return;
    };
    let donor = Graph::read(&file).unwrap();
    let name = "ghost_d:idle";
    let data = donor.animations.iter().find(|a| a.name == name);
    let data = data.and_then(|a| a.data).unwrap();
    let root = donor.nodes.iter().position(|n| n.name == "root_m").unwrap();
    let mut plan = Spec::default().resolve(&donor).unwrap();
    plan.edits.push(AnimationEdit {
        name: name.to_string(),
        frames: data.frames as usize,
        tracks: vec![(
            root,
            Track {
                translation: Channel::Static([-0.05, 0.0, 0.03]),
                ..Track::ABSENT
            },
        )],
    });
    let written = rewrite(&file, &plan).unwrap();
    let graph = Graph::read(&written).unwrap();
    let (a, b) = (donor.member(&data).unwrap(), graph.member(&data).unwrap());
    assert!(!a.opaque[9].is_empty() && !a.opaque[10].is_empty());
    assert_eq!(a.opaque, b.opaque);
    assert_ne!(a.static_pose, b.static_pose);

    let mut changed = 0;
    for (x, y) in donor.groups.iter().zip(&graph.groups) {
        let (Some(x), Some(y)) = (x, y) else { continue };
        changed += x
            .members
            .iter()
            .zip(&y.members)
            .filter(|(p, q)| p != q)
            .count();
    }
    assert_eq!(changed, 1);
    assert!(donor.write_resources(&written).unwrap() == file);

    plan.edits[0].frames = data.frames as usize + 1;
    assert!(rewrite(&file, &plan).is_err());
}
