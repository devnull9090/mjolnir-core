//! Replay the instanced-geometry broadphase for a box around a world point:
//! cluster tree -> instance groups -> group trees -> instances -> each
//! instance's definition tree, in the instance's local frame. Shows which
//! link drops the point.
//!
//!   cargo run -p blam-sbsp --example havok_path -- <payload> <x> <y> <z> [radius]
use blam_sbsp::{mopp, transplant};

fn f32_at(b: &[u8], o: usize) -> f32 {
    f32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

/// (code, quantisation) of one mopp element and its `tgbl` wrapper.
fn tree(file: &[u8], path: &str, i: usize) -> Option<(Vec<u8>, mopp::Quant)> {
    let (e, w) = transplant::donor_element(file, path, i).ok()?;
    let n = u32::from_le_bytes(w[12..16].try_into().unwrap()) as usize;
    let code = w[20..20 + n].to_vec();
    let q = mopp::Quant {
        offset: [f32_at(&e, 32), f32_at(&e, 36), f32_at(&e, 40)],
        scale: f32_at(&e, 44),
    };
    Some((code, q))
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let p = [
        a[1].parse::<f32>().unwrap(),
        a[2].parse().unwrap(),
        a[3].parse().unwrap(),
    ];
    let r: f32 = a.get(4).map(|s| s.parse().unwrap()).unwrap_or(0.5);
    let bx = |c: [f32; 3]| {
        (
            [c[0] - r, c[1] - r, c[2] - r],
            [c[0] + r, c[1] + r, c[2] + r],
        )
    };

    let (code, q) = tree(&file, "cluster to instance group mopps", 0).expect("cluster tree");
    let (lo, hi) = bx(p);
    let groups = mopp::query(&code, &q.query_box(lo, hi)).expect("cluster query");
    println!("cluster tree -> groups {groups:?}");
    for g in groups {
        let Some((code, q)) = tree(&file, "instance group to instance mopps", g as usize) else {
            println!("  group {g}: no tree");
            continue;
        };
        let insts = mopp::query(&code, &q.query_box(lo, hi)).expect("group query");
        println!("  group {g} -> instances {insts:?}");
        for i in insts {
            let (e, _) =
                transplant::donor_element(&file, "instanced geometry instances", i as usize)
                    .expect("instance");
            let s = f32_at(&e, 0);
            let fwd = [f32_at(&e, 4), f32_at(&e, 8), f32_at(&e, 12)];
            let left = [f32_at(&e, 16), f32_at(&e, 20), f32_at(&e, 24)];
            let up = [f32_at(&e, 28), f32_at(&e, 32), f32_at(&e, 36)];
            let pos = [f32_at(&e, 40), f32_at(&e, 44), f32_at(&e, 48)];
            let def = i16::from_le_bytes([e[52], e[53]]) as usize;
            let d = [p[0] - pos[0], p[1] - pos[1], p[2] - pos[2]];
            let dot = |a: [f32; 3], b: [f32; 3]| a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
            let local = [dot(d, fwd) / s, dot(d, left) / s, dot(d, up) / s];
            let base = transplant::definition(def);
            let base = base.trim_end_matches(".collision info");
            let Some((code, q)) = tree(&file, &format!("{base}.mopp codes"), 0) else {
                println!("    instance {i} (def {def}): no definition tree");
                continue;
            };
            let rl = r / s;
            let hits = mopp::query(
                &code,
                &q.query_box(
                    [local[0] - rl, local[1] - rl, local[2] - rl],
                    [local[0] + rl, local[1] + rl, local[2] + rl],
                ),
            )
            .expect("definition query");
            println!(
                "    instance {i} (def {def}, pos z {:.1}): local ({:.2}, {:.2}, {:.2}) -> {} surface(s)",
                pos[2], local[0], local[1], local[2], hits.len()
            );
        }
    }
}
