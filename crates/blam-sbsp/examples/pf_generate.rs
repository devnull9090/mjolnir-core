//! Generate pathfinding for a structure BSP's instanced geometry and report
//! what came out: sizes against the engine's limits, ring and hint checks,
//! connected ground. With a scenario, compare which surfaces got a sector with
//! the shipped data's own choice.
//!   cargo run --release -p blam-sbsp --example pf_generate -- <sbsp> [options]
//!     --static             only instances whose pathfinding policy is static
//!     --instances a-b      only these instance indices
//!     --tolerance <wu>     plane tolerance of a merged sector (default 0.2)
//!     --ring <n>           most corners of a merged sector (default 16)
//!     --island <wu^2>      leave out connected floor smaller than this
//!     --dent <wu>          how far a sector's corner may lie inside its hull
//!     --border <wu>        how far a border between two sectors may move
//!     --ground <wu^2>      leave out connected ground (seams included) smaller than this
//!     --headroom <wu>      cut away floor that another floor covers closer than this
//!     --step <wu>          how far apart in height a seam may join two floors (default 0.1)
//!     --drops              how the pieces other than the largest sit on it
//!     --why <instance> <surface>   what became of one surface
//!     --box x0,y0,x1,y1    the sectors centred in a box, highest first: centre, area, piece, instances
//!     --compare <scenario> <bsp index>
use blam_sbsp::navmesh::{self, Options, POLICY_STATIC};
use blam_sbsp::pathfinding::{Pathfinding, INDEX_LIMIT};
use blam_tag::blockedit::find_block;
use std::collections::BTreeMap;

fn area(ring: &[[f32; 3]]) -> f64 {
    let mut n = [0f64; 3];
    for i in 0..ring.len() {
        let (p, q) = (ring[i], ring[(i + 1) % ring.len()]);
        n[0] += (p[1] as f64 - q[1] as f64) * (p[2] as f64 + q[2] as f64);
        n[1] += (p[2] as f64 - q[2] as f64) * (p[0] as f64 + q[0] as f64);
        n[2] += (p[0] as f64 - q[0] as f64) * (p[1] as f64 + q[1] as f64);
    }
    (n[0] * n[0] + n[1] * n[1] + n[2] * n[2]).sqrt() / 2.0
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let sbsp = std::fs::read(&a[0]).expect("sbsp");
    let mut o = Options::default();
    let (mut only_static, mut range, mut compare, mut ground) = (false, None, None, 0.0);
    let (mut headroom, mut drops) = (0.0f32, false);
    let mut why: Vec<(u32, u32)> = Vec::new();
    let mut boxes: Vec<[f32; 4]> = Vec::new();
    let mut i = 1;
    while i < a.len() {
        match a[i].as_str() {
            "--static" => only_static = true,
            "--instances" => {
                let (lo, hi) = a[i + 1].split_once('-').expect("a-b");
                range = Some((lo.parse::<usize>().unwrap(), hi.parse::<usize>().unwrap()));
                i += 1;
            }
            "--tolerance" => {
                o.plane_tolerance = a[i + 1].parse().unwrap();
                i += 1;
            }
            "--ring" => {
                o.max_ring = a[i + 1].parse().unwrap();
                i += 1;
            }
            "--island" => {
                o.min_island_area = a[i + 1].parse().unwrap();
                i += 1;
            }
            "--dent" => {
                o.dent = a[i + 1].parse().unwrap();
                i += 1;
            }
            "--ground" => {
                ground = a[i + 1].parse().unwrap();
                i += 1;
            }
            "--border" => {
                o.border = a[i + 1].parse().unwrap();
                i += 1;
            }
            "--headroom" => {
                headroom = a[i + 1].parse().unwrap();
                i += 1;
            }
            "--step" => {
                o.seam_step = a[i + 1].parse().unwrap();
                i += 1;
            }
            "--drops" => drops = true,
            "--box" => {
                let v: Vec<f32> = a[i + 1].split(',').map(|x| x.parse().unwrap()).collect();
                boxes.push([v[0], v[1], v[2], v[3]]);
                i += 1;
            }
            "--why" => {
                why.push((a[i + 1].parse().unwrap(), a[i + 2].parse().unwrap()));
                i += 2;
            }
            "--compare" => {
                compare = Some((a[i + 1].clone(), a[i + 2].parse::<usize>().unwrap()));
                i += 2;
            }
            other => panic!("unknown option {other}"),
        }
        i += 1;
    }

    let t0 = std::time::Instant::now();
    // An instance that copies the shell (a converted map's stand-in for it) is not ground of its own.
    let copies = blam_sbsp::pathfinding::shell_collision(&sbsp)
        .and_then(|shell| blam_sbsp::pathfinding::shell_copies(&sbsp, &shell))
        .unwrap_or_default();
    let (instances, polygons) = navmesh::instance_polygons(&sbsp, &|i, inst| {
        (!only_static || inst.policy == POLICY_STATIC)
            && range.is_none_or(|(lo, hi)| (lo..=hi).contains(&i))
            && !copies.get(i).copied().unwrap_or(false)
    })
    .expect("instances");
    let mut policy: BTreeMap<u8, usize> = BTreeMap::new();
    for inst in &instances {
        *policy.entry(inst.policy).or_default() += 1;
    }
    let objects: std::collections::BTreeSet<u32> = polygons.iter().map(|p| p.object).collect();
    println!(
        "{} instances (policy -> count {policy:?}); {} taken, {} polygons",
        instances.len(),
        objects.len(),
        polygons.len()
    );
    for &(object, surface) in &why {
        for (n, p) in polygons.iter().enumerate().filter(|(_, p)| p.object == object && p.surface == surface) {
            println!("why {object}/{surface}: polygon {n}, breakable {}, ring {:?}", p.breakable, p.ring);
        }
    }
    let raw_why: Vec<usize> = polygons.iter().enumerate().filter(|(_, p)| why.contains(&(p.object, p.surface))).map(|(n, _)| n).collect();
    let mut why_note = String::new();
    let polygons = if headroom > 0.0 {
        let piece = navmesh::ground_pieces(&polygons, &o).expect("pieces");
        let (cut, stats) = navmesh::cut_covered(&polygons, &piece, headroom);
        for &n in &raw_why {
            why_note += &format!("  polygon {n}: piece {}, touched {}, {} piece(s) left\n", piece[n] as i64, stats.touched[n], stats.source.iter().filter(|&&s| s as usize == n).count());
        }
        {
            let mut by: BTreeMap<u32, (usize, usize)> = BTreeMap::new();
            for (i, p) in polygons.iter().enumerate() {
                let e = by.entry(p.object).or_default();
                e.0 += 1;
                e.1 += stats.touched[i] as usize;
            }
            let mut by: Vec<_> = by.into_iter().filter(|x| x.1 .1 > 0).collect();
            by.sort_by_key(|x| std::cmp::Reverse(x.1 .1));
            println!(
                "floors cut, by instance (of its polygons): {}",
                by.iter().take(30).map(|(o, (n, t))| format!("{o}: {t} of {n}")).collect::<Vec<_>>().join(", ")
            );
        }
        println!(
            "covered floor: {} floors cut ({} whole) into {} pieces, {:.0} wu^2 taken, {} corners inserted; {} polygons  [{:.1}s]",
            stats.cut, stats.gone, stats.pieces, stats.area, stats.inserted, cut.len(), t0.elapsed().as_secs_f32()
        );
        cut
    } else {
        polygons
    };
    let (mesh, pf) = match navmesh::generate(&polygons, &|_, _| true, &o, ground) {
        Ok(x) => x,
        Err(e) => {
            println!("failed: {e}");
            let mesh = navmesh::merge(&polygons, &|_, _| true, &o);
            let pf = Pathfinding::build_oversize(&mesh.collision).expect("build");
            (mesh, pf)
        }
    };
    println!(
        "floors {} ({} left out as islands) -> {} merged floors, {} corners dropped; collision {} surfaces, {} edges, {} vertices  [{:.1}s]",
        mesh.floors,
        mesh.island_floors,
        mesh.merged,
        mesh.corners_dropped,
        mesh.collision.surfaces.len(),
        mesh.collision.edges.len(),
        mesh.collision.vertices.len(),
        t0.elapsed().as_secs_f32()
    );
    println!("neighbours kept apart by: {:?}", mesh.blocked);
    // What the floors' edges face: another floor, something that is not one, or nothing.
    {
        let c = &mesh.collision;
        let is_floor = |s: i32| {
            s >= 0 && c.surfaces[s as usize].flags == 0 && blam_sbsp::pathfinding::surface_normal(c, s as usize)[2] >= 0.65
        };
        let (mut both, mut other, mut open) = (0, 0, 0);
        for e in &c.edges {
            match (is_floor(e.left), is_floor(e.right)) {
                (true, true) => both += 1,
                (true, false) | (false, true) => {
                    if e.left < 0 || e.right < 0 {
                        open += 1
                    } else {
                        other += 1
                    }
                }
                _ => {}
            }
        }
        println!("floor edges: {both} between floors, {other} against a surface that is no floor, {open} open");
    }
    let steps = pf.sectors.iter().filter(|s| !s.is_floor()).count();
    println!(
        "sectors {} ({steps} steps), links {} of {INDEX_LIMIT}, vertices {} of {INDEX_LIMIT}, hints {} of 32767, seams dropped {}  [{:.1}s]",
        pf.sectors.len(),
        pf.links.len(),
        pf.vertices.len(),
        pf.hints.len(),
        pf.cracks_dropped,
        t0.elapsed().as_secs_f32()
    );
    println!("rings: {:?}; hints: {:?}", pf.check_rings(), pf.check_hints());
    for b in &boxes {
        let mut found: Vec<(f32, String)> = Vec::new();
        for (sector, &surface) in pf.sector_surface.iter().enumerate() {
            let ring = blam_sbsp::unpack16::polygon(&mesh.collision, surface);
            let c = [0, 1, 2].map(|k| ring.iter().map(|v| v[k]).sum::<f32>() / ring.len() as f32);
            if c[0] < b[0] || c[0] > b[2] || c[1] < b[1] || c[1] > b[3] {
                continue;
            }
            let objects: std::collections::BTreeSet<u32> = mesh.members[surface].iter().map(|&m| polygons[m as usize].object).collect();
            found.push((c[2], format!("  sector {sector} at ({:.1}, {:.1}, {:.2}), {:.1} wu^2, piece {}, instances {objects:?}", c[0], c[1], c[2], area(&ring), pf.component[sector])));
        }
        found.sort_by(|x, y| y.0.total_cmp(&x.0));
        println!("box {b:?}: {} sectors", found.len());
        for (_, line) in found.iter().take(25) {
            println!("{line}");
        }
    }
    if !why.is_empty() {
        print!("{why_note}");
        for (n, p) in polygons.iter().enumerate().filter(|(_, p)| why.contains(&(p.object, p.surface))) {
            let sector = mesh.surface_of[n].and_then(|s| pf.surface_sector[s as usize]);
            let m = [0, 1, 2].map(|k| p.ring.iter().map(|v| v[k]).sum::<f32>() / p.ring.len() as f32);
            println!("  after: polygon {n} of {}/{}: sector {sector:?}; under its middle {m:?}: {:?}", p.object, p.surface, pf.sector_at(&mesh.collision, m));
        }
    }

    // Connected ground, by area.
    let mut by_component: BTreeMap<usize, (usize, f64)> = BTreeMap::new();
    let mut sizes: BTreeMap<usize, usize> = BTreeMap::new();
    for (s, &surface) in pf.sector_surface.iter().enumerate() {
        let ring = blam_sbsp::unpack16::polygon(&mesh.collision, surface);
        let e = by_component.entry(pf.component[s]).or_default();
        e.0 += 1;
        e.1 += area(&ring);
        *sizes.entry(ring.len()).or_default() += 1;
    }
    let mut components: Vec<(usize, f64)> = by_component.into_values().collect();
    components.sort_by(|x, y| y.1.total_cmp(&x.1));
    let total: f64 = components.iter().map(|c| c.1).sum();
    println!(
        "{} components, {:.1} wu^2 in all; largest: {}",
        components.len(),
        total,
        components.iter().take(5).map(|c| format!("{} sectors {:.1} wu^2", c.0, c.1)).collect::<Vec<_>>().join(", ")
    );
    println!("ring sizes: {sizes:?}");
    // How the other pieces sit on the largest: for each of their outer edges,
    // how far below its middle the largest piece's floor lies.
    if drops {
        let mut area_of: BTreeMap<usize, f64> = BTreeMap::new();
        for (s, &surface) in pf.sector_surface.iter().enumerate() {
            *area_of.entry(pf.component[s]).or_default() += area(&blam_sbsp::unpack16::polygon(&mesh.collision, surface));
        }
        let main = *area_of.iter().max_by(|x, y| x.1.total_cmp(y.1)).unwrap().0;
        let mut drops: BTreeMap<usize, Vec<(f32, f32)>> = BTreeMap::new();
        for l in &pf.links {
            let (left, right) = (l.left as i64, l.right as i64);
            if right >= 0 && (right as usize) < pf.sectors.len() && left >= 0 { continue; }
            let s = if left >= 0 && (left as usize) < pf.sectors.len() { left } else { right } as usize;
            if s >= pf.sectors.len() || !pf.sectors[s].is_floor() { continue; }
            let c = pf.component[s];
            if c == main || area_of[&c] < 100.0 { continue; }
            let (a, b) = (pf.vertices[l.v1 as usize], pf.vertices[l.v2 as usize]);
            let len = ((b[0]-a[0]).powi(2) + (b[1]-a[1]).powi(2)).sqrt();
            let m = [(a[0]+b[0])/2.0, (a[1]+b[1])/2.0, (a[2]+b[2])/2.0];
            let mut best: Option<f32> = None;
            for (t, &surface) in pf.sector_surface.iter().enumerate() {
                if pf.component[t] != main || !pf.sectors[t].is_floor() { continue; }
                if let Some(z) = blam_sbsp::pathfinding::Pathfinding::surface_z(&mesh.collision, surface, m[0], m[1]) {
                    if z <= m[2] + 0.5 && best.is_none_or(|bz| z > bz) { best = Some(z); }
                }
            }
            drops.entry(c).or_default().push((best.map_or(f32::NAN, |z| m[2] - z), len));
        }
        for (c, d) in &drops {
            let mut h: BTreeMap<i32, f32> = BTreeMap::new();
            let mut none = 0.0;
            for &(dz, len) in d {
                if dz.is_nan() { none += len } else { *h.entry((dz * 10.0).floor() as i32).or_default() += len }
            }
            println!("  piece {c} ({:.0} wu^2): {} outer edges; length by drop (0.1 wu bins): {:?}; no ground under {none:.0} wu",
                area_of[c], d.len(), h.iter().map(|(k, v)| (*k as f32 / 10.0, v.round())).collect::<Vec<_>>());
        }
    }
    // Where each piece of ground other than the largest lies, and whose it is.
    {
        let mut pieces: BTreeMap<usize, (f64, [f64; 2], std::collections::BTreeSet<u32>)> = BTreeMap::new();
        for (s, &surface) in pf.sector_surface.iter().enumerate() {
            let ring = blam_sbsp::unpack16::polygon(&mesh.collision, surface);
            let a = area(&ring);
            let e = pieces.entry(pf.component[s]).or_insert((0.0, [0.0; 2], Default::default()));
            e.0 += a;
            for k in 0..2 {
                e.1[k] += a * ring.iter().map(|p| p[k] as f64).sum::<f64>() / ring.len() as f64;
            }
            for &m in &mesh.members[surface] {
                e.2.insert(polygons[m as usize].object);
            }
        }
        let mut pieces: Vec<_> = pieces.into_values().collect();
        pieces.sort_by(|x, y| y.0.total_cmp(&x.0));
        for (a, c, objects) in pieces.iter().skip(1).take(8) {
            println!(
                "  piece of {a:.0} wu^2 centred ({:.1}, {:.1}) wu = ({:.0}, {:.0}) m, instances {:?}",
                c[0] / a,
                c[1] / a,
                c[0] / a * 3.048,
                c[1] / a * 3.048,
                objects.iter().take(12).collect::<Vec<_>>()
            );
        }
    }

    let Some((scenario, bi)) = compare else { return };
    let scn = std::fs::read(&scenario).expect("scenario");
    let tag = blam_tag::TagFile::parse(&scn, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let pfp = format!("ai pathfinding data[{bi}]");
    let igr = find_block(&layout, &scn, &root, &format!("{pfp}.instanced geometry refs")).expect("instanced refs");
    // (ours, theirs) -> (surfaces, area)
    let mut table: BTreeMap<(bool, bool), (usize, f64)> = BTreeMap::new();
    let mut theirs_cache: BTreeMap<u32, Vec<i32>> = BTreeMap::new();
    for (n, p) in polygons.iter().enumerate() {
        let theirs = theirs_cache.entry(p.object).or_insert_with(|| {
            let e = igr.block.element(p.object as usize).unwrap();
            let object = i16::from_le_bytes([e[0], e[1]]);
            let refs = find_block(&layout, &scn, &root, &format!("{pfp}.object refs[{object}].bsps[0].bsp2d refs")).expect("refs");
            (0..refs.block.count as usize)
                .map(|k| i32::from_le_bytes(refs.block.element(k).unwrap()[0..4].try_into().unwrap()))
                .collect()
        });
        let ours = mesh.surface_of[n].and_then(|s| pf.surface_sector[s as usize]).is_some();
        let theirs = theirs.get(p.surface as usize).is_some_and(|&r| r != -1);
        let e = table.entry((ours, theirs)).or_default();
        e.0 += 1;
        e.1 += area(&p.ring);
    }
    println!("surface has a sector (ours, shipped) -> surfaces, area wu^2:");
    for ((ours, theirs), (count, area)) in &table {
        println!("  ours {ours:5}  shipped {theirs:5}: {count:6} surfaces, {area:9.1}");
    }
}
