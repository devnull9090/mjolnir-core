//! Sanity-check the model-viewer geometry extraction against real tags.
//!
//!   cargo run --example dump_geometry -- objects/characters/elite/elite
//!   cargo run --example dump_geometry -- warthog

use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::geometry;
use tag_editor_lib::install;

fn main() -> Result<(), String> {
    let query = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "objects/characters/elite/elite".to_string());

    let found = install::detect();
    let (paks, oodle) = (found.paks.unwrap(), found.oodle.unwrap());
    let catalog = Catalog::open(&paks, &oodle)?;

    let index = catalog
        .tags
        .iter()
        .position(|t| t.group == "model" && t.short.contains(&query))
        .ok_or_else(|| format!("no model tag matching {query:?}"))?;
    let entry = &catalog.tags[index];
    println!("hlmt: {}", entry.short);

    // Mirror the command's resolution: hlmt refs -> coll + skel.
    let file = catalog.read_tag(index)?;
    let refs = geometry::model_refs(&file)?;
    let mut geo = geometry::ModelGeometry::default();
    for r in &refs {
        let want = r.path.replace('\\', "/").to_ascii_lowercase();
        let found = catalog
            .tags
            .iter()
            .position(|t| t.group == r.group && t.short.to_ascii_lowercase() == want);
        println!("  ref {} -> {} ({})", r.path, r.group, found.map_or("MISSING".into(), |i| catalog.tags[i].short.clone()));
        let Some(i) = found else { continue };
        let file = catalog.read_tag(i)?;
        match r.group {
            "collision_model" => geo.meshes = geometry::collision_meshes(&file)?,
            _ => {
                let (nodes, groups) = geometry::skeleton(&file)?;
                geo.nodes = nodes;
                geo.marker_groups = groups;
            }
        }
    }

    println!("\nnodes: {}", geo.nodes.len());
    for n in geo.nodes.iter().take(8) {
        println!(
            "  {:<24} parent {:>3}  t ({:+.3} {:+.3} {:+.3})  q ({:+.3} {:+.3} {:+.3} {:+.3})",
            n.name, n.parent, n.translation[0], n.translation[1], n.translation[2],
            n.rotation[0], n.rotation[1], n.rotation[2], n.rotation[3],
        );
    }

    let groups = geo.marker_groups.len();
    let markers: usize = geo.marker_groups.iter().map(|g| g.markers.len()).sum();
    println!("marker groups: {groups} ({markers} markers)");

    println!("meshes: {}", geo.meshes.len());
    let mut verts = 0usize;
    let mut tris = 0usize;
    let mut bad_index = 0usize;
    for m in &geo.meshes {
        let vc = m.positions.len() / 3;
        let tc = m.indices.len() / 3;
        verts += vc;
        tris += tc;
        bad_index += m.indices.iter().filter(|&&i| i as usize >= vc).count();
        // Quaternion sanity for the node it attaches to.
        println!(
            "  {:<12}/{:<12} node {:>3}  {:>5} verts {:>5} tris",
            m.region, m.permutation, m.node, vc, tc
        );
    }
    println!("total: {verts} verts, {tris} tris, {bad_index} out-of-range indices");

    // Bounds over all meshes, ignoring node transforms (a rough size check).
    let mut min = [f32::MAX; 3];
    let mut max = [f32::MIN; 3];
    for m in &geo.meshes {
        for v in m.positions.chunks_exact(3) {
            for a in 0..3 {
                min[a] = min[a].min(v[a]);
                max[a] = max[a].max(v[a]);
            }
        }
    }
    println!(
        "bounds (bone-local union): ({:+.3} {:+.3} {:+.3}) .. ({:+.3} {:+.3} {:+.3})",
        min[0], min[1], min[2], max[0], max[1], max[2]
    );

    // Rest-pose world positions, both quaternion conventions, to settle
    // whether skeleton_model stores rotations directly or inverted the way
    // classic mod2 did. The right one puts feet near z=0 and the head above
    // the pelvis.
    for conjugate in [false, true] {
        let mut worlds: Vec<([f32; 3], [f32; 4])> = Vec::new();
        for n in &geo.nodes {
            let mut q = n.rotation;
            if conjugate {
                q = [-q[0], -q[1], -q[2], q[3]];
            }
            let (t, q) = if n.parent >= 0 {
                let (pt, pq) = worlds[n.parent as usize];
                let rotated = rotate(pq, n.translation);
                (
                    [pt[0] + rotated[0], pt[1] + rotated[1], pt[2] + rotated[2]],
                    mul(pq, q),
                )
            } else {
                (n.translation, q)
            };
            worlds.push((t, q));
        }
        println!("\nworld z per node ({}quats):", if conjugate { "conjugated " } else { "direct " });
        for (n, (t, _)) in geo.nodes.iter().zip(&worlds) {
            if n.name.contains("foot") || n.name.contains("head") || n.name.contains("pelvis") {
                println!("  {:<24} z {:+.3}  ({:+.3} {:+.3})", n.name, t[2], t[0], t[1]);
            }
        }
    }
    Ok(())
}

fn rotate(q: [f32; 4], v: [f32; 3]) -> [f32; 3] {
    // v' = v + 2 * cross(q.xyz, cross(q.xyz, v) + q.w * v)
    let u = [q[0], q[1], q[2]];
    let c1 = cross(u, v);
    let c1 = [c1[0] + q[3] * v[0], c1[1] + q[3] * v[1], c1[2] + q[3] * v[2]];
    let c2 = cross(u, c1);
    [v[0] + 2.0 * c2[0], v[1] + 2.0 * c2[1], v[2] + 2.0 * c2[2]]
}

fn cross(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}

fn mul(a: [f32; 4], b: [f32; 4]) -> [f32; 4] {
    [
        a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
        a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
        a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3],
        a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2],
    ]
}
