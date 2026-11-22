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
