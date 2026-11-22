//! What shipped pathfinding sectors look like, as numbers a generator can aim
//! at: ring sizes, how far a sector strays from a plane, slope, convexity and
//! winding in plan, areas and edge lengths, and the flags in use.
//!   cargo run -p blam-sbsp --example pf_stats -- <scenario> [bsp index]
use blam_tag::blockedit::find_block;
use std::collections::BTreeMap;

fn u16_at(b: &[u8], o: usize) -> u16 {
    u16::from_le_bytes([b[o], b[o + 1]])
}
fn i32_at(b: &[u8], o: usize) -> i32 {
    i32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}
fn f32_at(b: &[u8], o: usize) -> f32 {
    f32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

fn pct(sorted: &[f32], q: f32) -> f32 {
    if sorted.is_empty() {
        return 0.0;
    }
    sorted[((sorted.len() - 1) as f32 * q) as usize]
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let scn = std::fs::read(&a[0]).expect("scenario");
    let only: Option<usize> = a.get(1).and_then(|s| s.parse().ok());
    let tag = blam_tag::TagFile::parse(&scn, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let all = find_block(&layout, &scn, &root, "ai pathfinding data").expect("pathfinding");
    for bi in 0..all.block.count as usize {
        if only.is_some_and(|o| o != bi) {
            continue;
        }
        let pf = format!("ai pathfinding data[{bi}]");
        let blk = |n: &str| find_block(&layout, &scn, &root, &format!("{pf}.{n}")).expect(n).block;
        let (sectors, links, verts) = (blk("sectors"), blk("links"), blk("vertices"));
        let (ns, nl, nv) = (sectors.count as usize, links.count as usize, verts.count as usize);
        if ns == 0 {
            continue;
        }
        let vertex = |i: usize| {
            let e = verts.element(i).unwrap();
            [f32_at(e, 0), f32_at(e, 4), f32_at(e, 8)]
        };
        let link = |i: usize| {
            let e = links.element(i).unwrap();
            // v1, v2, flags, hint, forward, reverse, left, right
            [0, 2, 4, 6, 8, 10, 12, 14].map(|o| u16_at(e, o) as usize)
        };
        let mut ring_sizes: BTreeMap<usize, usize> = BTreeMap::new();
        let mut sector_flags: BTreeMap<u16, usize> = BTreeMap::new();
        let mut link_flags: BTreeMap<u16, usize> = BTreeMap::new();
        let (mut broken, mut concave, mut cw, mut ccw, mut bad_vertex) = (0, 0, 0, 0, 0);
        let (mut dev, mut area, mut edge, mut nz) = (Vec::new(), Vec::new(), Vec::new(), Vec::new());
        let mut worst_concave = 0f32;
        for i in 0..nl {
            *link_flags.entry(link(i)[2] as u16).or_default() += 1;
        }
        for s in 0..ns {
            let se = sectors.element(s).unwrap();
            let flags = u16_at(se, 0);
            *sector_flags.entry(flags).or_default() += 1;
            let first = i32_at(se, 4);
            if first < 0 || first as usize >= nl {
                broken += 1;
                continue;
            }
            let mut ring = Vec::new();
            let mut l = first as usize;
            let mut ok = false;
            for _ in 0..4096 {
                let k = link(l);
                let (from, next) = if k[6] == s {
                    (k[0], k[4])
                } else if k[7] == s {
                    (k[1], k[5])
                } else {
                    break;
                };
                if from >= nv {
                    bad_vertex += 1;
                    break;
                }
                ring.push(vertex(from));
                if next == first as usize {
                    ok = true;
                    break;
                }
                if next >= nl {
                    break;
                }
                l = next;
            }
            if !ok || ring.len() < 3 {
                broken += 1;
                continue;
            }
            *ring_sizes.entry(ring.len()).or_default() += 1;
            let n = ring.len();
            // Newell normal and centroid.
            let (mut nrm, mut c) = ([0f64; 3], [0f64; 3]);
            for i in 0..n {
                let (p, q) = (ring[i], ring[(i + 1) % n]);
                nrm[0] += (p[1] as f64 - q[1] as f64) * (p[2] as f64 + q[2] as f64);
                nrm[1] += (p[2] as f64 - q[2] as f64) * (p[0] as f64 + q[0] as f64);
                nrm[2] += (p[0] as f64 - q[0] as f64) * (p[1] as f64 + q[1] as f64);
                for k in 0..3 {
                    c[k] += p[k] as f64 / n as f64;
                }
                let d: f32 = (0..3).map(|k| (p[k] - q[k]).powi(2)).sum::<f32>().sqrt();
                edge.push(d);
            }
            let len = (nrm[0] * nrm[0] + nrm[1] * nrm[1] + nrm[2] * nrm[2]).sqrt();
            if len < 1e-12 {
                continue;
            }
            area.push((len / 2.0) as f32);
            let u = [nrm[0] / len, nrm[1] / len, nrm[2] / len];
            nz.push(u[2] as f32);
            if u[2] > 0.0 {
                ccw += 1;
            } else {
                cw += 1;
            }
            let d = ring
                .iter()
                .map(|p| ((0..3).map(|k| (p[k] as f64 - c[k]) * u[k]).sum::<f64>()).abs())
                .fold(0.0, f64::max);
            dev.push(d as f32);
            // Convexity in the sector's own plane: every turn the same way as the normal.
            let mut worst = 0f32;
            for i in 0..n {
                let (p, q, r) = (ring[i], ring[(i + 1) % n], ring[(i + 2) % n]);
                let e1 = [q[0] - p[0], q[1] - p[1], q[2] - p[2]];
                let e2 = [r[0] - q[0], r[1] - q[1], r[2] - q[2]];
                let x = [
                    e1[1] * e2[2] - e1[2] * e2[1],
                    e1[2] * e2[0] - e1[0] * e2[2],
                    e1[0] * e2[1] - e1[1] * e2[0],
                ];
                let turn = (x[0] as f64 * u[0] + x[1] as f64 * u[1] + x[2] as f64 * u[2]) as f32;
                let l1 = (e1[0] * e1[0] + e1[1] * e1[1] + e1[2] * e1[2]).sqrt();
                // The reflex vertex's depth: how far q sits inside the chord p-r, in wu.
                if turn < 0.0 && l1 > 0.0 {
                    worst = worst.max(-turn / l1);
                }
            }
            if worst > 0.002 {
                concave += 1;
                worst_concave = worst_concave.max(worst);
            }
        }
        // Connected ground: sectors joined by a link with one on each side.
        let mut parent: Vec<usize> = (0..ns).collect();
        fn find(p: &mut [usize], x: usize) -> usize {
            let mut r = x;
            while p[r] != r {
                r = p[r];
            }
            p[x] = r;
            r
        }
        for i in 0..nl {
            let k = link(i);
            if k[6] < ns && k[7] < ns {
                let (x, y) = (find(&mut parent, k[6]), find(&mut parent, k[7]));
                parent[x] = y;
            }
        }
        let mut sizes: BTreeMap<usize, usize> = BTreeMap::new();
        for s in 0..ns {
            *sizes.entry(find(&mut parent, s)).or_default() += 1;
        }
        let mut sizes: Vec<usize> = sizes.into_values().collect();
        sizes.sort_unstable_by(|a, b| b.cmp(a));
        println!("  components: {}, largest {:?}", sizes.len(), &sizes[..sizes.len().min(8)]);
        // The same without sectors on moving objects (`sector mobile`), to set
        // against ground generated for the static instances alone.
        let mobile = |s: usize| u16_at(sectors.element(s).unwrap(), 0) & 0x4 != 0;
        let mut parent: Vec<usize> = (0..ns).collect();
        for i in 0..nl {
            let k = link(i);
            if k[6] < ns && k[7] < ns && !mobile(k[6]) && !mobile(k[7]) {
                let (x, y) = (find(&mut parent, k[6]), find(&mut parent, k[7]));
                parent[x] = y;
            }
        }
        let mut sizes: BTreeMap<usize, usize> = BTreeMap::new();
        for s in (0..ns).filter(|&s| !mobile(s)) {
            *sizes.entry(find(&mut parent, s)).or_default() += 1;
        }
        let mut sizes: Vec<usize> = sizes.into_values().collect();
        sizes.sort_unstable_by(|a, b| b.cmp(a));
        println!("  components without mobile sectors: {}, largest {:?}", sizes.len(), &sizes[..sizes.len().min(8)]);
        for v in [&mut dev, &mut area, &mut edge, &mut nz] {
            v.sort_by(|a, b| a.partial_cmp(b).unwrap());
        }
        println!("bsp {bi}: {ns} sectors, {nl} links, {nv} vertices; {broken} broken rings, {bad_vertex} bad vertices");
        println!("  ring sizes: {ring_sizes:?}");
        println!(
            "  winding by normal z: {ccw} up, {cw} down; concave (reflex deeper than 0.002 wu): {concave}, worst {worst_concave:.3}"
        );
        println!(
            "  plane deviation wu: median {:.4}, p90 {:.4}, p99 {:.4}, max {:.4}",
            pct(&dev, 0.5), pct(&dev, 0.9), pct(&dev, 0.99), pct(&dev, 1.0)
        );
        println!(
            "  area wu^2: median {:.3}, p90 {:.3}, p99 {:.3}, max {:.3}, total {:.1}",
            pct(&area, 0.5), pct(&area, 0.9), pct(&area, 0.99), pct(&area, 1.0), area.iter().sum::<f32>()
        );
        println!(
            "  edge wu: p1 {:.4}, median {:.3}, p90 {:.3}, p99 {:.3}, max {:.3}",
            pct(&edge, 0.01), pct(&edge, 0.5), pct(&edge, 0.9), pct(&edge, 0.99), pct(&edge, 1.0)
        );
        println!(
            "  normal z: min {:.3}, p1 {:.3}, p10 {:.3}, median {:.3}",
            pct(&nz, 0.0), pct(&nz, 0.01), pct(&nz, 0.1), pct(&nz, 0.5)
        );
        // Hints by type, and how many links of each flag bit have a sector on both sides.
        let hints = blk("pathfinding hints");
        let mut kinds: BTreeMap<u16, usize> = BTreeMap::new();
        for h in 0..hints.count as usize {
            *kinds.entry(u16_at(hints.element(h).unwrap(), 0)).or_default() += 1;
        }
        let mut sided: BTreeMap<u16, [usize; 2]> = BTreeMap::new();
        for i in 0..nl {
            let k = link(i);
            let two = usize::from(k[6] < ns && k[7] < ns);
            if k[2] == 0 {
                sided.entry(0).or_default()[two] += 1;
            }
            for bit in 0..16 {
                if k[2] & (1 << bit) != 0 {
                    sided.entry(1 << bit).or_default()[two] += 1;
                }
            }
        }
        println!("  hint types -> count: {kinds:?}");
        println!(
            "  link flag bit -> [one-sided, two-sided]: {}",
            sided.iter().map(|(k, v)| format!("{k:#x}:{v:?}")).collect::<Vec<_>>().join(" ")
        );
        let fmt = |m: &BTreeMap<u16, usize>| m.iter().map(|(k, v)| format!("{k:#x}:{v}")).collect::<Vec<_>>().join(" ");
        println!("  sector flags: {}", fmt(&sector_flags));
        println!("  link flags: {}", fmt(&link_flags));
    }
}
