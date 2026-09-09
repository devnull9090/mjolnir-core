//! Recompile the instanced-geometry broadphase above a definition: the
//! instance-group MOPP, and the cluster MOPP above that.
//!
//!   cargo run -p blam-sbsp --example group_mopp -- <payload> <out> <group>... [--cluster]
//!
//! Collision reaches an instance through two bounding-volume trees before its
//! own MOPP is ever consulted:
//!
//!     cluster -> instance group -> instance -> the definition's mopp
//!
//! Moving or growing an instance leaves both of the upper trees describing
//! where it used to be, so a query out at the new geometry never returns the
//! instance and the pawn falls through however good the definition's own tree
//! is. Widening the group's *sphere* is not enough — the sphere and the tree
//! are separate tests.
//!
//! Terminal convention, read off the shipped trees: an instance-group tree
//! names **absolute instance indices** (group 58 ships `Reindex` nodes so its
//! terminals come out as 165..779, exactly its member list), and the cluster
//! tree names **absolute group indices** (0..91). Both are reproduced here.
use blam_sbsp::mopp;
use blam_tag::blockedit::{find_block, replace_nested, NestedReplace};

const INSTANCES: &str = "instanced geometry instances";
const GROUP_MOPPS: &str = "instance group to instance mopps";
const GROUP_SPHERES: &str = "instance group to instance spheres";
const CLUSTER_MOPPS: &str = "cluster to instance group mopps";

fn f32_at(b: &[u8], o: usize) -> f32 {
    f32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

/// An instance's world-space box, as the tag stores it at offsets 76..100.
fn instance_box(elem: &[u8]) -> ([f32; 3], [f32; 3]) {
    (
        [f32_at(elem, 76), f32_at(elem, 84), f32_at(elem, 92)],
        [f32_at(elem, 80), f32_at(elem, 88), f32_at(elem, 96)],
    )
}

fn fit_and_build(
    prims: &[(u32, [f32; 3], [f32; 3])],
    label: &str,
) -> (Vec<u8>, mopp::Quant) {
    let mut lo = [f32::MAX; 3];
    let mut hi = [f32::MIN; 3];
    for (_, l, h) in prims {
        for k in 0..3 {
            lo[k] = lo[k].min(l[k]);
            hi[k] = hi[k].max(h[k]);
        }
    }
    let q = mopp::Quant::fit(lo, hi);
    let boxes: Vec<(u32, mopp::Aabb)> = prims
        .iter()
        .map(|(id, l, h)| {
            (
                *id,
                q.box_of(&[
                    [l[0], l[1], l[2]],
                    [h[0], h[1], h[2]],
                ]),
            )
        })
        .collect();
    let code = mopp::build(&boxes).expect("build mopp");

    // Every member must answer a query of its own box, or it is unreachable.
    let mut miss = 0;
    for (id, b) in &boxes {
        let ql = [b.lo[0] as i32 - 1, b.lo[1] as i32 - 1, b.lo[2] as i32 - 1];
        let qh = [b.hi[0] as i32 + 1, b.hi[1] as i32 + 1, b.hi[2] as i32 + 1];
        if !mopp::query_bytes(&code, ql, qh).unwrap().contains(id) {
            miss += 1;
        }
    }
    assert_eq!(miss, 0, "{label}: {miss} member(s) do not answer their own box");
    println!(
        "  {label}: {} member(s) -> {} code byte(s); box [{:.1}, {:.1}] x [{:.1}, {:.1}] x [{:.1}, {:.1}]",
        prims.len(),
        code.len(),
        lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]
    );
    (code, q)
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.len() < 3 {
        eprintln!("usage: group_mopp <payload> <out> <group>... [--cluster]");
        std::process::exit(2);
    }
    let cluster = args.iter().any(|a| a == "--cluster");
    let file = std::fs::read(&args[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");

    let instances = find_block(&layout, &file, &root, INSTANCES).expect("instances");
    let spheres = find_block(&layout, &file, &root, GROUP_SPHERES).expect("group spheres");
    let group_count = spheres.block.count as usize;

    let members_of = |g: usize| -> Vec<u16> {
        match find_block(
            &layout,
            &file,
            &root,
            &format!("{GROUP_SPHERES}[{g}].instance indices"),
        ) {
            Ok(m) => (0..m.block.count as usize)
                .map(|k| {
                    let b = m.block.element(k).unwrap();
                    u16::from_le_bytes([b[0], b[1]])
                })
                .collect(),
            Err(_) => Vec::new(),
        }
    };
    let group_box = |g: usize| -> Option<([f32; 3], [f32; 3])> {
        let mut lo = [f32::MAX; 3];
        let mut hi = [f32::MIN; 3];
        let mut any = false;
        for i in members_of(g) {
            if let Some(e) = instances.block.element(i as usize) {
                let (l, h) = instance_box(e);
                for k in 0..3 {
                    lo[k] = lo[k].min(l[k]);
                    hi[k] = hi[k].max(h[k]);
                }
                any = true;
            }
        }
        any.then_some((lo, hi))
    };

    // A NestedReplace rewrites a whole block, so gather every element of the
    // mopp blocks and patch only the ones being recompiled.
    let gather = |path: &str, count: usize| -> (Vec<Vec<u8>>, Vec<Vec<u8>>) {
        let mut els = Vec::with_capacity(count);
        let mut wraps = Vec::with_capacity(count);
        for i in 0..count {
            let (e, w) = blam_sbsp::transplant::donor_element(&file, path, i)
                .unwrap_or_else(|err| panic!("{path}[{i}]: {err}"));
            els.push(e);
            wraps.push(w);
        }
        (els, wraps)
    };
    let group_mopp_count = find_block(&layout, &file, &root, GROUP_MOPPS)
        .expect("group mopps")
        .block
        .count as usize;
    let (mut group_els, mut group_wraps) = gather(GROUP_MOPPS, group_mopp_count);
    let mut touched_groups = false;

    let mut edits: Vec<NestedReplace> = Vec::new();

    for a in args[2..].iter().filter(|a| a.parse::<usize>().is_ok()) {
        let g: usize = a.parse().unwrap();
        let ids = members_of(g);
        if ids.is_empty() {
            println!("  group {g}: no members, skipped");
            continue;
        }
        let prims: Vec<(u32, [f32; 3], [f32; 3])> = ids
            .iter()
            .filter_map(|i| {
                instances.block.element(*i as usize).map(|e| {
                    let (l, h) = instance_box(e);
                    // Absolute instance index, the way the shipped tree names them.
                    (*i as u32, l, h)
                })
            })
            .collect();
        let (code, q) = fit_and_build(&prims, &format!("group {g}"));
        mopp::patch_element(&mut group_els[g], q, code.len());
        group_wraps[g] = mopp::wrapper(&code);
        touched_groups = true;
    }
    if touched_groups {
        edits.push(NestedReplace {
            path: GROUP_MOPPS.to_string(),
            count: group_mopp_count as u32,
            elements: group_els.concat(),
            wrappers: Some(group_wraps),
        });
    }

    if cluster {
        let prims: Vec<(u32, [f32; 3], [f32; 3])> = (0..group_count)
            .filter_map(|g| group_box(g).map(|(l, h)| (g as u32, l, h)))
            .collect();
        let (code, q) = fit_and_build(&prims, "cluster");
        let count = find_block(&layout, &file, &root, CLUSTER_MOPPS)
            .expect("cluster mopps")
            .block
            .count as usize;
        let (mut els, mut wraps) = gather(CLUSTER_MOPPS, count);
        mopp::patch_element(&mut els[0], q, code.len());
        wraps[0] = mopp::wrapper(&code);
        edits.push(NestedReplace {
            path: CLUSTER_MOPPS.to_string(),
            count: count as u32,
            elements: els.concat(),
            wrappers: Some(wraps),
        });
    }

    let out = replace_nested(&file, &edits).expect("replace");
    let tag = blam_tag::TagFile::parse(&out, None).expect("reparse");
    let l = tag.layout().expect("relayout");
    let block = tag.read_data(&l).expect("reread");
    let payload = tag.data().expect("bdat");
    assert_eq!(block.consumed, payload.size as usize, "does not walk exactly");
    std::fs::write(&args[1], &out).expect("write");
    println!("  wrote {} ({} bytes, walks exactly)", args[1], out.len());
}
