//! Put glTF geometry into a shipped mesh package, in the game's own
//! serialisation, and prove the result reads back.
//!
//! ```text
//! cargo run -p ue-asset --example mesh_rewrite -- \
//!     <paks> <donor path substring> <mesh.gltf> <out.uasset> //!     [--selftest] [--offset x,y,z] [--rename /Game/Path/SM_Name]
//! ```
//!
//! `--rename` also renames the package and its mesh export, so the result is a
//! **new** package rather than a replacement for the donor. That matters
//! because overriding a shipped mesh replaces every use of it in the game;
//! a renamed clone is placed by nothing and can be added alongside with
//! `blam-pack --example package_add`.
//!
//! `--selftest` rewrites the donor with the donor's *own* geometry first and
//! checks it survives a parse, which separates "the writer is wrong" from
//! "this particular geometry is wrong".
//!
//! The geometry is normalised into the donor's bounding box, because the
//! bounds the engine culls against live in the tail this rewrite preserves.
//! The scale it prints is what the spawned component has to use to put the
//! mesh back at its intended size.
use ue_asset::mesh_write::{rewrite_static_mesh, Geometry};
use ue_asset::unversioned::Ctx;

fn accessor_floats(doc: &serde_json::Value, bin: &[u8], index: usize, comps: usize) -> Vec<f32> {
    let acc = &doc["accessors"][index];
    let count = acc["count"].as_u64().unwrap() as usize;
    let view = &doc["bufferViews"][acc["bufferView"].as_u64().unwrap() as usize];
    let base = view["byteOffset"].as_u64().unwrap_or(0) as usize
        + acc["byteOffset"].as_u64().unwrap_or(0) as usize;
    let stride = view["byteStride"].as_u64().unwrap_or(0) as usize;
    let step = if stride > 0 { stride } else { comps * 4 };
    let mut out = Vec::with_capacity(count * comps);
    for i in 0..count {
        for c in 0..comps {
            let at = base + i * step + c * 4;
            out.push(f32::from_le_bytes(bin[at..at + 4].try_into().unwrap()));
        }
    }
    out
}

fn accessor_indices(doc: &serde_json::Value, bin: &[u8], index: usize) -> Vec<u32> {
    let acc = &doc["accessors"][index];
    let count = acc["count"].as_u64().unwrap() as usize;
    let ctype = acc["componentType"].as_u64().unwrap();
    let view = &doc["bufferViews"][acc["bufferView"].as_u64().unwrap() as usize];
    let base = view["byteOffset"].as_u64().unwrap_or(0) as usize
        + acc["byteOffset"].as_u64().unwrap_or(0) as usize;
    let width = match ctype {
        5121 => 1,
        5123 => 2,
        _ => 4,
    };
    (0..count)
        .map(|i| {
            let at = base + i * width;
            match width {
                1 => bin[at] as u32,
                2 => u16::from_le_bytes(bin[at..at + 2].try_into().unwrap()) as u32,
                _ => u32::from_le_bytes(bin[at..at + 4].try_into().unwrap()),
            }
        })
        .collect()
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    if a.len() < 4 {
        eprintln!("usage: mesh_rewrite <paks> <donor substring> <mesh.gltf> <out.bin> [--selftest]");
        std::process::exit(2);
    }
    let (paks, donor_want, gltf_path, out_path) = (&a[0], a[1].to_ascii_lowercase(), &a[2], &a[3]);
    let selftest = a.iter().any(|s| s == "--selftest");
    let oodle: Vec<std::path::PathBuf> = Vec::new();

    let usmap_bytes = std::fs::read("defs/ue/Meteorite-2607-CU3.usmap").expect("read usmap");
    let usmap = ue_asset::Usmap::parse(&usmap_bytes).expect("parse usmap");
    let containers = ue_iostore::load_all(paks).expect("load containers");
    let global = containers
        .iter()
        .find(|c| c.utoc_path.file_name().unwrap() == "global.utoc")
        .expect("no global.utoc");
    let sc = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .expect("no ScriptObjects");
    let scripts =
        ue_asset::zen::ScriptObjects::parse(&ue_iostore::read_chunk(global, sc, None, &oodle).unwrap())
            .expect("parse scripts");

    // ---- the donor -------------------------------------------------------
    let (ci, cidx, path) = containers
        .iter()
        .enumerate()
        .find_map(|(ci, c)| {
            c.files
                .iter()
                .find(|(p, _)| p.ends_with(".uasset") && p.to_ascii_lowercase().contains(&donor_want))
                .map(|(p, i)| (ci, *i, p.clone()))
        })
        .expect("no donor matched");
    let data = ue_iostore::read_chunk(&containers[ci], &containers[ci].chunks[cidx], None, &oodle)
        .expect("read donor");
    let package = ue_asset::zen::Package::parse(&data).expect("parse donor package");
    let export = package
        .exports
        .iter()
        .position(|e| scripts.leaf(e.class) == Some("StaticMesh"))
        .expect("donor has no StaticMesh export");
    let bytes = package.export_data(&data, export).expect("export data");
    let ctx = Ctx {
        usmap: &usmap,
        names: &package.names,
    };
    println!("donor {path}\n  export {export}, {} bytes", bytes.len());

    let check = |label: &str, produced: &[u8], want_v: usize, want_i: usize| {
        match ue_asset::mesh::parse_static_mesh(&ctx, produced, None) {
            Ok(m) => {
                let lod = m.lods.iter().find(|l| !l.positions.is_empty());
                match lod {
                    Some(l) => {
                        let ok = l.positions.len() / 3 == want_v && l.indices.len() == want_i;
                        println!(
                            "  {label}: reads back {} vert(s), {} index/indices, {} section(s) -- {}",
                            l.positions.len() / 3,
                            l.indices.len(),
                            l.sections.len(),
                            if ok { "MATCHES" } else { "MISMATCH" }
                        );
                        ok
                    }
                    None => {
                        println!("  {label}: parsed but no LOD carries buffers -- MISMATCH");
                        false
                    }
                }
            }
            Err(e) => {
                println!("  {label}: does not parse: {e} -- MISMATCH");
                false
            }
        }
    };

    if selftest {
        let orig = ue_asset::mesh::parse_static_mesh(&ctx, bytes, None).expect("parse donor mesh");
        let lod = orig
            .lods
            .iter()
            .find(|l| !l.positions.is_empty())
            .expect("donor LOD");
        let geo = Geometry {
            positions: lod.positions.clone(),
            normals: lod.normals.clone(),
            uvs: lod.uvs.clone(),
            indices: lod.indices.clone(),
            sections: lod
                .sections
                .iter()
                .map(|s| (s.material_index, s.first_index, s.num_triangles))
                .collect(),
        };
        let (v, i) = (geo.vertices(), geo.indices.len());
        let produced = rewrite_static_mesh(&ctx, bytes, &geo).expect("rewrite donor with itself");
        println!("  selftest: {} -> {} bytes", bytes.len(), produced.len());
        if !check("selftest", &produced, v, i) {
            std::process::exit(1);
        }
    }

    // ---- the glTF --------------------------------------------------------
    let doc: serde_json::Value =
        serde_json::from_slice(&std::fs::read(gltf_path).expect("read gltf")).expect("parse gltf");
    let bin_uri = doc["buffers"][0]["uri"].as_str().expect("external .bin");
    let bin_path = std::path::Path::new(gltf_path)
        .parent()
        .unwrap()
        .join(bin_uri);
    let bin = std::fs::read(&bin_path).expect("read gltf .bin");

    let mut geo = Geometry::default();
    for mesh in doc["meshes"].as_array().unwrap_or(&vec![]) {
        for prim in mesh["primitives"].as_array().unwrap_or(&vec![]) {
            let base = geo.vertices() as u32;
            let pos_acc = prim["attributes"]["POSITION"].as_u64().unwrap() as usize;
            let positions = accessor_floats(&doc, &bin, pos_acc, 3);
            let count = positions.len() / 3;
            geo.positions.extend(positions);
            if let Some(n) = prim["attributes"]["NORMAL"].as_u64() {
                geo.normals
                    .extend(accessor_floats(&doc, &bin, n as usize, 3));
            } else {
                geo.normals.extend(std::iter::repeat(0.0).take(count * 3));
            }
            if let Some(t) = prim["attributes"]["TEXCOORD_0"].as_u64() {
                geo.uvs.extend(accessor_floats(&doc, &bin, t as usize, 2));
            } else {
                geo.uvs.extend(std::iter::repeat(0.0).take(count * 2));
            }
            let first = geo.indices.len() as u32;
            let idx = accessor_indices(&doc, &bin, prim["indices"].as_u64().unwrap() as usize);
            let tris = (idx.len() / 3) as u32;
            geo.indices.extend(idx.into_iter().map(|i| i + base));
            // Every section uses the donor's one material slot: the slots are
            // properties and this rewrite does not touch them.
            geo.sections.push((0, first, tris));
        }
    }
    println!(
        "gltf {gltf_path}\n  {} vert(s), {} triangle(s), {} section(s)",
        geo.vertices(),
        geo.indices.len() / 3,
        geo.sections.len()
    );

    // glTF axes to game axes. halo2ue writes Halo (x, -y, z) as glTF
    // (x, z, y) in metres, so a vertex is at (gx, gz, gy) * 100 centimetres
    // plus the offset the collision transplant used to move Blood Gulch into
    // B40's world box -- which reproduces the decor position the level file
    // already carries, (-10789.9, -46076.6, 13411.2).
    let off: [f32; 3] = match a.iter().position(|s| s == "--offset") {
        Some(i) => {
            let v: Vec<f32> = a[i + 1].split(',').map(|x| x.parse().unwrap()).collect();
            [v[0], v[1], v[2]]
        }
        None => [-10789.9, -46076.6, 13411.2],
    };
    let to_cm = |p: &[f32]| {
        [
            p[0] * 100.0 + off[0],
            p[2] * 100.0 + off[1],
            p[1] * 100.0 + off[2],
        ]
    };

    let mut lo = [f32::MAX; 3];
    let mut hi = [f32::MIN; 3];
    for p in geo.positions.chunks_exact(3) {
        let v = to_cm(p);
        for k in 0..3 {
            lo[k] = lo[k].min(v[k]);
            hi[k] = hi[k].max(v[k]);
        }
    }
    let centre = [
        (lo[0] + hi[0]) * 0.5,
        (lo[1] + hi[1]) * 0.5,
        (lo[2] + hi[2]) * 0.5,
    ];
    println!(
        "  world box (cm): x [{:.0}, {:.0}]  y [{:.0}, {:.0}]  z [{:.0}, {:.0}]",
        lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]
    );
    // Normalise into the donor's box: the bounds the engine culls against live
    // in the tail this rewrite preserves, so the geometry has to fit them and
    // the component scales it back up.
    const DONOR_HALF: f32 = 50.0;
    let half = (0..3)
        .map(|k| (hi[k] - lo[k]) * 0.5)
        .fold(0.0f32, f32::max)
        .max(1e-6);
    let fit = DONOR_HALF / half;
    let mut normalised = Vec::with_capacity(geo.positions.len());
    for p in geo.positions.chunks_exact(3) {
        let v = to_cm(p);
        for k in 0..3 {
            normalised.push((v[k] - centre[k]) * fit);
        }
    }
    geo.positions = normalised;
    let mut swapped = Vec::with_capacity(geo.normals.len());
    for n in geo.normals.chunks_exact(3) {
        swapped.extend_from_slice(&[n[0], n[2], n[1]]);
    }
    geo.normals = swapped;
    // The donor's bounds are a box AND a sphere, and the engine culls against
    // both, so report the radius the normalised geometry actually needs.
    let mut radius = 0.0f32;
    for p in geo.positions.chunks_exact(3) {
        radius = radius.max((p[0] * p[0] + p[1] * p[1] + p[2] * p[2]).sqrt());
    }
    println!(
        "  normalised bounding sphere {radius:.1} (donor's box half-extent is {DONOR_HALF};          its sphere radius must be at least this)"
    );
    println!(
        "  SPAWN: location ({:.1}, {:.1}, {:.1}) cm, uniform scale {:.4}",
        centre[0],
        centre[1],
        centre[2],
        1.0 / fit
    );

    let (want_v, want_i) = (geo.vertices(), geo.indices.len());
    let produced = rewrite_static_mesh(&ctx, bytes, &geo).expect("rewrite with gltf geometry");
    println!("  rewrote export {} -> {} bytes", bytes.len(), produced.len());
    let mut ok = check("rewrite", &produced, want_v, want_i);

    // Put the export back into the package and re-read it the long way, which
    // is the end-to-end gate: the bytes that ship have to parse as this mesh.
    let mut zp = ue_asset::package::ZenPackage::parse(&data).expect("parse donor as ZenPackage");
    zp.set_export_bytes(export, produced).expect("set export bytes");
    let package_bytes = zp.write();
    println!(
        "  package {} -> {} bytes",
        data.len(),
        package_bytes.len()
    );
    match ue_asset::zen::Package::parse(&package_bytes)
        .ok()
        .and_then(|p| p.export_data(&package_bytes, export).ok().map(|b| b.to_vec()))
    {
        Some(round) => {
            if !check("packaged", &round, want_v, want_i) {
                ok = false;
            }
        }
        None => {
            println!("  packaged: the rebuilt package does not re-parse -- MISMATCH");
            ok = false;
        }
    }
    // Optional rename, so the result is a new package instead of a
    // replacement for the donor.
    let package_bytes = match a.iter().position(|s| s == "--rename") {
        None => package_bytes,
        Some(i) => {
            let new_path = a[i + 1].clone();
            let leaf = new_path.rsplit('/').next().unwrap().to_string();
            let mut zp =
                ue_asset::package::ZenPackage::parse(&package_bytes).expect("re-parse for rename");
            let old_header = u32::from_le_bytes(package_bytes[4..8].try_into().unwrap());
            let old_name = zp.name();

            zp.name_index = zp.names.intern(&new_path);
            zp.name_number = 0;
            // The mesh export carries the object name, and its public export
            // hash derives from that name: `/Game/..../Leaf.Leaf`.
            zp.export_map[export].name_index = zp.names.intern(&leaf);
            zp.export_map[export].name_number = 0;
            zp.export_map[export].public_export_hash =
                ue_asset::package::public_export_hash(&leaf);

            // The header just changed length. Keep the gap between the real
            // header and the cooked one constant, since that is the only thing
            // any consumer of CookedHeaderSize can be measuring.
            let once = zp.write();
            let new_header = u32::from_le_bytes(once[4..8].try_into().unwrap());
            zp.cooked_header_size =
                (zp.cooked_header_size as i64 + new_header as i64 - old_header as i64) as u32;
            let out = zp.write();
            println!(
                "  renamed {old_name} -> {new_path} (export {export} -> {leaf}); header {old_header} -> {new_header}"
            );
            match ue_asset::zen::Package::parse(&out) {
                Ok(p) => println!("  renamed package reports name {}", p.name),
                Err(e) => {
                    println!("  renamed package does not re-parse: {e} -- MISMATCH");
                    ok = false;
                }
            }
            out
        }
    };

    std::fs::write(out_path, &package_bytes).expect("write package");
    println!("  wrote {out_path}");
    if !ok {
        std::process::exit(1);
    }
}
