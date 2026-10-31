//! Probe the pathfinding `level bake` generates for a converted shell
//! (`blam_sbsp::pathfinding`), at points given in world units:
//!
//!   cargo run -p blam-sbsp --example pf_where -- <sbsp> [x,y,z ...]
//!       the floor sector under each point and its connected component
//!   cargo run -p blam-sbsp --example pf_where -- <sbsp> route x,y,z x,y,z
//!       the fewest-sector route between two points, link by link
//!   cargo run -p blam-sbsp --example pf_where -- <sbsp> links x,y,z
//!       every link of the floor sector under a point, and hints naming them
//!   cargo run -p blam-sbsp --example pf_where -- <sbsp> headroom x0,y0,x1,y1 <limit>
//!       floor sectors in a box with less than `limit` wu under a ceiling
//!   cargo run -p blam-sbsp --example pf_where -- <sbsp> surf <sector | sNNN surface> ...
//!       polygons and normals
//!   cargo run -p blam-sbsp --example pf_where -- <sbsp> dump x0,y0,x1,y1
//!       every shell surface touching a box, one JSON line each
//!   cargo run -p blam-sbsp --example pf_where -- <sbsp> hex <first> <end>
//!       the `sectors` block bytes of a run of sectors, to find in memory
use blam_sbsp::pathfinding::{shell_collision, Pathfinding};
use std::collections::{HashMap, VecDeque};

fn point(s: &str) -> [f32; 3] {
    let v: Vec<f32> = s.split(',').map(|s| s.parse().unwrap()).collect();
    [v[0], v[1], v[2]]
}

/// z of `surface`'s plane at (x, y) when (x, y) lies inside its polygon.
fn plane_z(c: &blam_sbsp::ce::Collision, surface: usize, x: f32, y: f32) -> Option<f32> {
    let n = blam_sbsp::pathfinding::surface_normal(c, surface);
    let poly = blam_sbsp::unpack16::polygon(c, surface);
    if poly.len() < 3 || n[2].abs() < 1e-3 {
        return None;
    }
    let mut sign = 0.0f32;
    for i in 0..poly.len() {
        let (p, q) = (poly[i], poly[(i + 1) % poly.len()]);
        let cross = (q[0] - p[0]) * (y - p[1]) - (q[1] - p[1]) * (x - p[0]);
        if cross.abs() < 1e-6 {
            continue;
        }
        if sign == 0.0 {
            sign = cross.signum();
        } else if cross.signum() != sign {
            return None;
        }
    }
    let p = poly[0];
    Some(p[2] - (n[0] * (x - p[0]) + n[1] * (y - p[1])) / n[2])
}

/// Headroom over a floor sector: the least height of any surface above it
/// that faces down (a ceiling), on a 0.1 wu grid over its polygon (pulled
/// 0.05 wu in from its edges), and the surface that gives it.
fn headroom(
    c: &blam_sbsp::ce::Collision,
    own: usize,
    poly: &[[f32; 3]],
    near: &[usize],
) -> (f32, usize, f32) {
    let mut who = usize::MAX;
    let mut nz = 0.0;
    let (mut x0, mut y0, mut x1, mut y1) = (f32::MAX, f32::MAX, f32::MIN, f32::MIN);
    for p in poly {
        x0 = x0.min(p[0]);
        y0 = y0.min(p[1]);
        x1 = x1.max(p[0]);
        y1 = y1.max(p[1]);
    }
    let mut best = f32::MAX;
    let mut x = x0 + 0.05;
    while x <= x1 - 0.05 {
        let mut y = y0 + 0.05;
        while y <= y1 - 0.05 {
            if let Some(z) = plane_z(c, own, x, y) {
                for &s in near {
                    if s == own {
                        continue;
                    }
                    let sn = blam_sbsp::pathfinding::surface_normal(c, s);
                    if sn[2] > -0.5 {
                        continue;
                    }
                    if let Some(zc) = plane_z(c, s, x, y) {
                        if zc > z + 0.02 && zc - z < best {
                            best = zc - z;
                            who = s;
                            nz = sn[2];
                        }
                    }
                }
            }
            y += 0.1;
        }
        x += 0.1;
    }
    (best, who, nz)
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let bsp = std::fs::read(&a[0]).expect("sbsp");
    let c = shell_collision(&bsp).expect("shell");
    let pf = Pathfinding::build(&c).expect("build");
    if a.get(1).map(String::as_str) == Some("links") {
        // Every link of the floor sector under a point: flags, the sector
        // across, the hint and the edge.
        let (s, _) = pf.sector_at(&c, point(&a[2])).expect("no floor sector");
        println!(
            "sector {s} flags {:#x} hint {}",
            pf.sectors[s].flags, pf.sectors[s].hint
        );
        for (i, l) in pf.links.iter().enumerate() {
            if l.left as usize != s && l.right as i64 != s as i64 {
                continue;
            }
            let (p, q) = (pf.vertices[l.v1 as usize], pf.vertices[l.v2 as usize]);
            println!(
                "  link {i}: left {} right {} flags {:#x} hint {} ({:.2},{:.2},{:.2})-({:.2},{:.2},{:.2})",
                l.left, l.right, l.flags, l.hint, p[0], p[1], p[2], q[0], q[1], q[2]
            );
        }
        for (i, h) in pf.hints.iter().enumerate() {
            let joined = h.data[0];
            if let Some(l) = usize::try_from(joined).ok().and_then(|j| pf.links.get(j)) {
                if l.left as usize == s || l.right as i64 == s as i64 {
                    println!(
                        "  hint {i}: kind {} joins link {joined} ({} <-> {})",
                        h.kind, l.left, l.right
                    );
                }
            }
        }
        return;
    }
    if a.get(1).map(String::as_str) == Some("hex") {
        // The `sectors` block bytes of sectors i..j, as the bake writes them.
        let (i, j): (usize, usize) = (a[2].parse().unwrap(), a[3].parse().unwrap());
        let b = pf.sectors_bytes();
        let hex: String = b[i * 8..j * 8].iter().map(|x| format!("{x:02x}")).collect();
        println!("{hex}");
        return;
    }
    if a.get(1).map(String::as_str) == Some("dump") {
        // Every shell surface touching a box x0,y0,x1,y1, one JSON line each.
        let b: Vec<f32> = a[2].split(',').map(|s| s.parse().unwrap()).collect();
        for s in 0..c.surfaces.len() {
            let poly = blam_sbsp::unpack16::polygon(&c, s);
            if !poly
                .iter()
                .any(|p| p[0] > b[0] && p[0] < b[2] && p[1] > b[1] && p[1] < b[3])
            {
                continue;
            }
            let n = blam_sbsp::pathfinding::surface_normal(&c, s);
            let sector = pf.surface_sector[s].map_or(-1, |k| k as i64);
            let pts: Vec<String> = poly
                .iter()
                .map(|p| format!("[{:.3},{:.3},{:.3}]", p[0], p[1], p[2]))
                .collect();
            println!(
                "{{\"s\":{s},\"sector\":{sector},\"n\":[{:.3},{:.3},{:.3}],\"p\":[{}]}}",
                n[0],
                n[1],
                n[2],
                pts.join(",")
            );
        }
        return;
    }
    if a.get(1).map(String::as_str) == Some("surf") {
        // Polygons of shell surfaces (sNNN) or sectors (NNN).
        for w in &a[2..] {
            let surface = match w.strip_prefix('s') {
                Some(n) => n.parse().unwrap(),
                None => pf.sector_surface[w.parse::<usize>().unwrap()],
            };
            let n = blam_sbsp::pathfinding::surface_normal(&c, surface);
            let poly = blam_sbsp::unpack16::polygon(&c, surface);
            let pts: Vec<String> = poly
                .iter()
                .map(|p| format!("({:.2},{:.2},{:.2})", p[0], p[1], p[2]))
                .collect();
            println!(
                "{w}: surface {surface} normal ({:.2},{:.2},{:.2}) {}",
                n[0],
                n[1],
                n[2],
                pts.join(" ")
            );
        }
        return;
    }
    if a.get(1).map(String::as_str) == Some("headroom") {
        // Floor sectors in a box x0,y0,x1,y1 with less headroom than `limit`.
        let b: Vec<f32> = a[2].split(',').map(|s| s.parse().unwrap()).collect();
        let limit: f32 = a[3].parse().unwrap();
        let near: Vec<usize> = (0..c.surfaces.len())
            .filter(|&s| {
                let poly = blam_sbsp::unpack16::polygon(&c, s);
                poly.iter().any(|p| {
                    p[0] > b[0] - 5.0 && p[0] < b[2] + 5.0 && p[1] > b[1] - 5.0 && p[1] < b[3] + 5.0
                })
            })
            .collect();
        for (sector, &surface) in pf.sector_surface.iter().enumerate() {
            let poly = blam_sbsp::unpack16::polygon(&c, surface);
            let cx = poly.iter().map(|p| p[0]).sum::<f32>() / poly.len() as f32;
            let cy = poly.iter().map(|p| p[1]).sum::<f32>() / poly.len() as f32;
            if cx < b[0] || cx > b[2] || cy < b[1] || cy > b[3] {
                continue;
            }
            let (h, who, nz) = headroom(&c, surface, &poly, &near);
            if h < limit {
                let lo = poly.iter().map(|p| p[2]).fold(f32::MAX, f32::min);
                let hi = poly.iter().map(|p| p[2]).fold(f32::MIN, f32::max);
                println!(
                    "sector {sector} flags {:#x} at ({cx:.2},{cy:.2}) z {lo:.2}..{hi:.2}: headroom {h:.2} under surface {who} (nz {nz:.2})",
                    pf.sectors[sector].flags
                );
            }
        }
        return;
    }
    let mut size: HashMap<usize, usize> = HashMap::new();
    for &k in &pf.component {
        *size.entry(k).or_default() += 1;
    }
    let main = size
        .iter()
        .max_by_key(|(_, n)| **n)
        .map(|(k, _)| *k)
        .unwrap();
    let zr = |s: usize| {
        let poly = blam_sbsp::unpack16::polygon(&c, pf.sector_surface[s]);
        let lo = poly.iter().map(|p| p[2]).fold(f32::MAX, f32::min);
        let hi = poly.iter().map(|p| p[2]).fold(f32::MIN, f32::max);
        let cx = poly.iter().map(|p| p[0]).sum::<f32>() / poly.len() as f32;
        let cy = poly.iter().map(|p| p[1]).sum::<f32>() / poly.len() as f32;
        (lo, hi, cx, cy, poly.len())
    };
    if a.get(1).map(String::as_str) == Some("route") {
        let (from, _) = pf.sector_at(&c, point(&a[2])).expect("from");
        let (to, _) = pf.sector_at(&c, point(&a[3])).expect("to");
        // Neighbours through every two-sided link.
        let mut next: Vec<Vec<(usize, usize)>> = vec![Vec::new(); pf.sectors.len()];
        for (i, l) in pf.links.iter().enumerate() {
            if l.right >= 0 {
                next[l.left as usize].push((l.right as usize, i));
                next[l.right as usize].push((l.left as usize, i));
            }
        }
        let mut came: Vec<Option<(usize, usize)>> = vec![None; pf.sectors.len()];
        let mut q = VecDeque::from([from]);
        came[from] = Some((from, usize::MAX));
        while let Some(s) = q.pop_front() {
            if s == to {
                break;
            }
            for &(t, l) in &next[s] {
                if came[t].is_none() {
                    came[t] = Some((s, l));
                    q.push_back(t);
                }
            }
        }
        let mut route = vec![(to, usize::MAX)];
        let mut s = to;
        while s != from {
            let (p, l) = came[s].expect("no route");
            route.last_mut().unwrap().1 = l;
            route.push((p, usize::MAX));
            s = p;
        }
        route.reverse();
        // route[i] = (sector, link that led into the next sector... shifted)
        for (i, &(s, _)) in route.iter().enumerate() {
            let (lo, hi, cx, cy, n) = zr(s);
            let via = if i + 1 < route.len() {
                route[i + 1].1
            } else {
                usize::MAX
            };
            let link = if via != usize::MAX {
                let l = pf.links[via];
                let (p, q) = (pf.vertices[l.v1 as usize], pf.vertices[l.v2 as usize]);
                let len = ((p[0] - q[0]).powi(2) + (p[1] - q[1]).powi(2)).sqrt();
                format!(
                    " -> link {via} flags {:#x} hint {} portal {len:.2} wu ({:.2},{:.2},{:.2})-({:.2},{:.2},{:.2})",
                    l.flags, l.hint, p[0], p[1], p[2], q[0], q[1], q[2]
                )
            } else {
                String::new()
            };
            println!(
                "sector {s} flags {:#x} at ({cx:.1},{cy:.1}) z {lo:.2}..{hi:.2} ({n} sides){link}",
                pf.sectors[s].flags
            );
        }
        return;
    }
    println!(
        "{} sectors, {} links, {} components, main {} with {} sectors",
        pf.sectors.len(),
        pf.links.len(),
        size.len(),
        main,
        size[&main]
    );
    for p in &a[1..] {
        match pf.sector_at(&c, point(p)) {
            Some((s, z)) => {
                let k = pf.component[s];
                println!(
                    "{p}: sector {s} (flags {:#x}) floor z {z:.2}, component {k} ({} sectors){}",
                    pf.sectors[s].flags,
                    size[&k],
                    if k == main { ", main" } else { "" }
                );
            }
            None => println!("{p}: no floor sector below"),
        }
    }
}
