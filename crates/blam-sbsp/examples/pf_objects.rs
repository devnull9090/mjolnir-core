//! How a scenario's pathfinding sits on instanced geometry: for each instance
//! with a pathfinding object, the object ref's 2D refs against the definition's
//! surfaces, and its slice of `vertices` against the definition's own vertices
//! (local and world-placed), to learn the layout a generator must write.
//!   cargo run -p blam-sbsp --example pf_objects -- <scenario> <sbsp> <bsp index> [instances to show]
use blam_tag::blockedit::find_block;

fn f32_at(b: &[u8], o: usize) -> f32 {
    f32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}
fn i32_at(b: &[u8], o: usize) -> i32 {
    i32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}
fn i16_at(b: &[u8], o: usize) -> i16 {
    i16::from_le_bytes([b[o], b[o + 1]])
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let scn = std::fs::read(&a[0]).expect("scenario");
    let sbsp = std::fs::read(&a[1]).expect("sbsp");
    let bi: usize = a[2].parse().unwrap();
    let show: usize = a.get(3).and_then(|s| s.parse().ok()).unwrap_or(4);

    let tag = blam_tag::TagFile::parse(&scn, None).expect("parse scenario");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let pf = format!("ai pathfinding data[{bi}]");
    let blk = |p: &str| find_block(&layout, &scn, &root, &format!("{pf}.{p}")).expect(p);
    let igr = blk("instanced geometry refs");
    let verts = blk("vertices");
    let objs = blk("object refs");
    let sectors = blk("sectors");
    println!(
        "{} sectors, {} vertices, {} object refs, {} instanced refs (element {} bytes), object ref element {} bytes",
        sectors.block.count, verts.block.count, objs.block.count, igr.block.count,
        igr.block.elements.len() / igr.block.count.max(1) as usize,
        objs.block.elements.len() / objs.block.count.max(1) as usize
    );
    let vertex = |i: usize| {
        let e = verts.block.element(i).unwrap();
        [f32_at(e, 0), f32_at(e, 4), f32_at(e, 8)]
    };

    let stag = blam_tag::TagFile::parse(&sbsp, None).expect("parse sbsp");
    let slay = stag.layout().expect("sbsp layout");
    let sroot = stag.read_data(&slay).expect("sbsp data");
    let inst = find_block(&slay, &sbsp, &sroot, "instanced geometry instances").expect("instances");
    let mut shown = 0;
    let mut objects_seen = std::collections::BTreeMap::new();
    for i in 0..igr.block.count as usize {
        let r = igr.block.element(i).unwrap();
        let object = i16_at(r, 0);
        if object < 0 {
            continue;
        }
        let b = inst.block.element(i).unwrap();
        let scale = f32_at(b, 0);
        let fwd = [f32_at(b, 4), f32_at(b, 8), f32_at(b, 12)];
        let left = [f32_at(b, 16), f32_at(b, 20), f32_at(b, 24)];
        let up = [f32_at(b, 28), f32_at(b, 32), f32_at(b, 36)];
        let pos = [f32_at(b, 40), f32_at(b, 44), f32_at(b, 48)];
        let def = i16_at(b, 52);
        objects_seen.entry(object).or_insert_with(Vec::new).push((i, def));
        if shown >= show {
            continue;
        }
        shown += 1;
        let base = blam_sbsp::transplant::definition(def as usize);
        let get = |n: &str| -> &[u8] {
            find_block(&slay, &sbsp, &sroot, &format!("{base}.{n}")).map(|f| f.block.elements).unwrap_or(&[])
        };
        let t = blam_sbsp::unpack16::Tables {
            bsp3d_nodes: get("bsp3d nodes"),
            planes: get("planes"),
            leaves: get("leaves"),
            bsp2d_references: get("bsp2d references"),
            bsp2d_nodes: get("bsp2d nodes"),
            surfaces: get("surfaces"),
            edges: get("edges"),
            vertices: get("vertices"),
        };
        let (d, _) = blam_sbsp::unpack16::unpack(&t).expect("unpack definition");
        let ob = find_block(&layout, &scn, &root, &format!("{pf}.object refs[{object}].bsps")).unwrap();
        println!(
            "instance {i}: definition {def}, scale {scale:.3}, pos ({:.2},{:.2},{:.2}), fwd ({:.2},{:.2},{:.2}); object {object} has {} bsp(s); definition {} surfaces {} vertices",
            pos[0], pos[1], pos[2], fwd[0], fwd[1], fwd[2], ob.block.count, d.surfaces.len(), d.vertices.len()
        );
        for k in 0..ob.block.count as usize {
            let e = ob.block.element(k).unwrap();
            let refs = find_block(&layout, &scn, &root, &format!("{pf}.object refs[{object}].bsps[{k}].bsp2d refs")).unwrap();
            let vo = i32_at(e, e.len() - 4);
            let values: Vec<i32> = (0..refs.block.count as usize).map(|n| i32_at(refs.block.element(n).unwrap(), 0)).collect();
            let none = values.iter().filter(|&&v| v == -1).count();
            let nodes = values.iter().filter(|&&v| v < -1).count();
            let mut secs: Vec<i32> = values.iter().copied().filter(|&v| v >= 0).collect();
            secs.sort();
            secs.dedup();
            println!(
                "  bsp {k}: reference {:#x} node {} refs {} (none {none}, nodes {nodes}, sectors {}..{} distinct {}), vertex offset {vo}",
                i32_at(e, 0), i16_at(e, 4), values.len(),
                secs.first().copied().unwrap_or(-1), secs.last().copied().unwrap_or(-1), secs.len()
            );
            for v in 0..3 {
                let p = vertex(vo as usize + v);
                let w = d.vertices.get(v).map(|x| x.point).unwrap_or([0.0; 3]);
                let placed = [0, 1, 2].map(|q| pos[q] + scale * (w[0] * fwd[q] + w[1] * left[q] + w[2] * up[q]));
                println!(
                    "    pf v{} ({:.3},{:.3},{:.3})  def v{v} local ({:.3},{:.3},{:.3}) world ({:.3},{:.3},{:.3})",
                    vo as usize + v, p[0], p[1], p[2], w[0], w[1], w[2], placed[0], placed[1], placed[2]
                );
            }
        }
    }
    let shared = objects_seen.values().filter(|v| v.len() > 1).count();
    println!(
        "{} objects used by {} instances; {} objects shared by several instances",
        objects_seen.len(),
        objects_seen.values().map(Vec::len).sum::<usize>(),
        shared
    );
    if let Some((o, list)) = objects_seen.iter().find(|(_, v)| v.len() > 1) {
        println!("  e.g. object {o}: instances/definitions {list:?}");
    }
}
