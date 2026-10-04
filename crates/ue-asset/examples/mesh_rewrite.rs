//! Put glTF geometry into a shipped mesh package, in the game's own
//! serialisation, and prove the result reads back.
//!
//! ```text
//! cargo run -p ue-asset --example mesh_rewrite -- \
//!     <paks> <donor path substring> <mesh.gltf> <out.uasset> //!     [--selftest] [--offset x,y,z] [--rename /Game/Path/SM_Name] \
//!     [--material Slot=/Game/Path/MI_X=pat1|pat2]... [--lightmap-uvs] [@args.txt]
//! ```
//!
//! `@args.txt` reads more arguments from a file, one per line.
//!
//! `--material` groups the glTF's own materials into numbered slots: every
//! primitive whose material name contains one of the patterns gets that slot's
//! index in its render-data section, and the tool prints the slot-to-material
//! table for the level file to apply at spawn. A pattern of `*` claims slot 0,
//! the donor's own, so unmatched primitives get it too. A pattern ending in
//! `$` must match the end of the name (`shader__lm1$` leaves `shader__lm13`).
//!
//! The materials themselves are assigned to the *component*, not baked into
//! the mesh: `--asset-imports` additionally writes them into the package as
//! `StaticMaterials` entries and package imports, but the loaded mesh still
//! reports the donor's one slot, so that form is kept only as a record of what
//! a cook would look like. See `docs/ue_mesh_write.md`.
//!
//! `--rename` also renames the package and its mesh export, so the result is a
//! **new** package rather than a replacement for the donor. That matters
//! because overriding a shipped mesh replaces every use of it in the game;
//! a renamed clone is placed by nothing and can be added alongside with
//! `blam-pack --example package_add`.
//!
//! `--lightmap-uvs` writes the glTF's `TEXCOORD_1` as a second UV channel
//! (a CE BSP's lightmap layout, which its materials sample for the baked
//! lighting); UVs are always written at full precision.
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
    // `@file` stands for the file's lines, one argument each: a map with
    // hundreds of material slots (Coldsnap) passes Windows' 32K command line.
    let a: Vec<String> = std::env::args()
        .skip(1)
        .flat_map(|s| match s.strip_prefix('@') {
            Some(f) => std::fs::read_to_string(f)
                .expect("read response file")
                .lines()
                .filter(|l| !l.is_empty())
                .map(str::to_string)
                .collect(),
            None => vec![s],
        })
        .collect();
    if a.len() < 4 {
        eprintln!(
            "usage: mesh_rewrite <paks> <donor substring> <mesh.gltf> <out.bin> [--selftest]"
        );
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
    let scripts = ue_asset::zen::ScriptObjects::parse(
        &ue_iostore::read_chunk(global, sc, None, &oodle).unwrap(),
    )
    .expect("parse scripts");

    // ---- the donor -------------------------------------------------------
    let (ci, cidx, path) = containers
        .iter()
        .enumerate()
        .find_map(|(ci, c)| {
            c.files
                .iter()
                .find(|(p, _)| {
                    p.ends_with(".uasset") && p.to_ascii_lowercase().contains(&donor_want)
                })
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
            uvs1: Vec::new(),
            tangents: Vec::new(),
            colors: Vec::new(),
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

    // Material slots: (slot name, package path, patterns). Slot 0 is the
    // donor's own; a spec whose patterns contain "*" replaces it.
    struct MatSpec {
        slot: String,
        package: String,
        patterns: Vec<String>,
        index: u32,
    }
    let asset_imports = a.iter().any(|s| s == "--asset-imports");
    let lightmap_uvs = a.iter().any(|s| s == "--lightmap-uvs");
    let mut specs: Vec<MatSpec> = Vec::new();
    let mut next_slot = 1u32;
    for (i, arg) in a.iter().enumerate() {
        if arg == "--material" {
            let spec = &a[i + 1];
            let mut parts = spec.splitn(3, '=');
            let slot = parts.next().unwrap().to_string();
            let package = parts
                .next()
                .expect("--material Slot=/pkg=pat|pat")
                .to_string();
            let patterns: Vec<String> = parts
                .next()
                .unwrap_or("")
                .split('|')
                .map(|s| s.to_ascii_lowercase())
                .collect();
            let index = if patterns.iter().any(|p| p == "*") {
                0
            } else {
                next_slot
            };
            if index != 0 {
                next_slot += 1;
            }
            specs.push(MatSpec {
                slot,
                package,
                patterns,
                index,
            });
        }
    }
    let material_names: Vec<String> = doc["materials"]
        .as_array()
        .map(|m| {
            m.iter()
                .map(|x| x["name"].as_str().unwrap_or("").to_ascii_lowercase())
                .collect()
        })
        .unwrap_or_default();
    let slot_for = |mat: Option<u64>| -> u32 {
        let name = mat
            .and_then(|i| material_names.get(i as usize))
            .cloned()
            .unwrap_or_default();
        for sp in &specs {
            if sp
                .patterns
                .iter()
                .any(|p| p != "*" && pattern_matches(p, &name))
            {
                return sp.index;
            }
        }
        0
    };

    let mut geo = Geometry::default();
    let mut tangents: Vec<f32> = Vec::new();
    let mut incident: Vec<f32> = Vec::new();
    let mut slot_tris: std::collections::BTreeMap<u32, u32> = Default::default();
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
            // The bump frame and the baked light's direction, when the glTF
            // carries them (halo2ue does for a CE BSP): kept per vertex so the
            // material can dot a bump normal with the incident direction.
            if lightmap_uvs {
                match prim["attributes"]["TANGENT"].as_u64() {
                    Some(t) => tangents.extend(accessor_floats(&doc, &bin, t as usize, 4)),
                    None => tangents.extend(std::iter::repeat(0.0).take(count * 4)),
                }
                match prim["attributes"]["_INCIDENT"].as_u64() {
                    Some(t) => incident.extend(accessor_floats(&doc, &bin, t as usize, 3)),
                    None => incident.extend(std::iter::repeat(0.0).take(count * 3)),
                }
            }
            // The second channel (a CE BSP's lightmap layout) when asked for;
            // primitives without one get zeros so the channels stay aligned.
            if lightmap_uvs {
                if let Some(t) = prim["attributes"]["TEXCOORD_1"].as_u64() {
                    geo.uvs1.extend(accessor_floats(&doc, &bin, t as usize, 2));
                } else {
                    geo.uvs1.extend(std::iter::repeat(0.0).take(count * 2));
                }
            }
            let first = geo.indices.len() as u32;
            let idx = accessor_indices(&doc, &bin, prim["indices"].as_u64().unwrap() as usize);
            let tris = (idx.len() / 3) as u32;
            geo.indices.extend(idx.into_iter().map(|i| i + base));
            let slot = slot_for(prim["material"].as_u64());
            *slot_tris.entry(slot).or_default() += tris;
            geo.sections.push((slot as i32, first, tris));
        }
    }
    println!(
        "gltf {gltf_path}\n  {} vert(s), {} triangle(s), {} section(s)",
        geo.vertices(),
        geo.indices.len() / 3,
        geo.sections.len()
    );
    for sp in &specs {
        println!(
            "  slot {} {} <- {}  ({} triangle(s))",
            sp.index,
            sp.slot,
            sp.package,
            slot_tris.get(&sp.index).copied().unwrap_or(0)
        );
    }
    if !specs.is_empty() {
        println!(
            "  slot 0 (the donor's) keeps {} triangle(s)",
            slot_tris.get(&0).copied().unwrap_or(0)
        );
        // The level file assigns these on the component at spawn; print them
        // in slot order so the entry can be copied straight across.
        let mut by_slot: Vec<String> = vec![String::new(); next_slot as usize];
        for sp in &specs {
            by_slot[sp.index as usize] =
                format!("{}.{}", sp.package, sp.package.rsplit('/').next().unwrap());
        }
        println!("  level-file materials: [{}]", by_slot.join(", "));
    }

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
    // The same swap for the bump frame. Exchanging two axes is a mirror, so the
    // bitangent's sign flips with it.
    if tangents.len() == geo.vertices() * 4
        && tangents
            .chunks_exact(4)
            .any(|t| t[0] != 0.0 || t[1] != 0.0 || t[2] != 0.0)
    {
        geo.tangents = tangents
            .chunks_exact(4)
            .flat_map(|t| [t[0], t[2], t[1], -t[3]])
            .collect();
    }
    // The incident direction, re-expressed in each vertex's own tangent frame
    // (x along the tangent, y the bitangent, z the normal) and packed into the
    // vertex colour, so a material reads it straight against a tangent-space
    // bump normal. CE looks the direction up through a normalisation cube, so
    // rgb holds the unit vector; alpha holds its length (at most ~1), which is
    // the best reading of the bumped lightmap pass's mix(1, N.L, v0.a) weight.
    if incident.len() == geo.vertices() * 3 {
        let frames = ue_asset::mesh_write::tangent_frames(&geo);
        let pack = |v: f32| ((v.clamp(-1.0, 1.0) * 0.5 + 0.5) * 255.0).round() as u8;
        geo.colors = incident
            .chunks_exact(3)
            .zip(&frames)
            .flat_map(|(d, (t, n, sign))| {
                let len = (d[0] * d[0] + d[1] * d[1] + d[2] * d[2]).sqrt();
                let k = if len > 1e-6 { 1.0 / len } else { 0.0 };
                let d = [d[0] * k, d[2] * k, d[1] * k];
                let b = [
                    (n[1] * t[2] - n[2] * t[1]) * sign,
                    (n[2] * t[0] - n[0] * t[2]) * sign,
                    (n[0] * t[1] - n[1] * t[0]) * sign,
                ];
                let dot = |a: [f32; 3]| a[0] * d[0] + a[1] * d[1] + a[2] * d[2];
                let weight = (len.clamp(0.0, 1.0) * 255.0).round() as u8;
                [pack(dot(*t)), pack(dot(b)), pack(dot(*n)), weight]
            })
            .collect();
    }
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
    println!(
        "  rewrote export {} -> {} bytes",
        bytes.len(),
        produced.len()
    );
    let mut ok = check("rewrite", &produced, want_v, want_i);

    // Put the export back into the package and re-read it the long way, which
    // is the end-to-end gate: the bytes that ship have to parse as this mesh.
    let mut zp = ue_asset::package::ZenPackage::parse(&data).expect("parse donor as ZenPackage");
    zp.set_export_bytes(export, produced)
        .expect("set export bytes");
    let package_bytes = zp.write();
    println!("  package {} -> {} bytes", data.len(), package_bytes.len());
    match ue_asset::zen::Package::parse(&package_bytes)
        .ok()
        .and_then(|p| {
            p.export_data(&package_bytes, export)
                .ok()
                .map(|b| b.to_vec())
        }) {
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
            zp.export_map[export].public_export_hash = ue_asset::package::public_export_hash(&leaf);

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

    // Material slots: each named material becomes a package import and a
    // StaticMaterials entry cloned from the donor's slot 0.
    let package_bytes = if specs.is_empty() || !asset_imports {
        package_bytes
    } else {
        use ue_asset::props::{Name, Val};
        let mut zp =
            ue_asset::package::ZenPackage::parse(&package_bytes).expect("parse for materials");
        let old_header = u32::from_le_bytes(package_bytes[4..8].try_into().unwrap());
        // Imports first, so the property edit can name them. A package import
        // index is type 2 in the top two bits over (package index << 32) |
        // public export hash index.
        let mut import_of: Vec<i32> = Vec::new();
        for sp in &specs {
            let leaf = sp.package.rsplit('/').next().unwrap().to_string();
            let pkg_idx = zp.imported_package_names.intern(&sp.package) as u64;
            while zp.imported_package_name_numbers.len() < zp.imported_package_names.names.len() {
                zp.imported_package_name_numbers.push(0);
            }
            zp.imported_public_export_hashes
                .push(ue_asset::package::public_export_hash(&leaf));
            let hash_idx = (zp.imported_public_export_hashes.len() - 1) as u64;
            zp.import_map
                .push((2u64 << 62) | (pkg_idx << 32) | hash_idx);
            let k = (zp.import_map.len() - 1) as i32;
            import_of.push(-k - 1);
            println!(
                "  import {k} <- {} (package {pkg_idx}, hash {hash_idx})",
                sp.package
            );
        }
        let slot_names: Vec<u32> = specs.iter().map(|sp| zp.names.intern(&sp.slot)).collect();

        // The cook lists the mesh's material import in the export's dependency
        // bundle as create-before-serialize (the donor's bundle is [-4, 1]:
        // its material, then its body setup), so the new imports go in after
        // the existing create-before-serialize entries of the same bundle.
        {
            let h = zp.dependency_bundle_headers[export];
            let at =
                (h.first_entry_index as usize) + (h.counts[0] + h.counts[1] + h.counts[2]) as usize;
            for (i, k) in import_of.iter().enumerate() {
                zp.dependency_bundle_entries.insert(at + i, *k);
            }
            zp.dependency_bundle_headers[export].counts[2] += import_of.len() as u32;
            for later in zp.dependency_bundle_headers.iter_mut().skip(export + 1) {
                later.first_entry_index += import_of.len() as i32;
            }
            println!(
                "  dependency bundle[{export}] now {:?} over {:?}",
                zp.dependency_bundle_headers[export].counts, zp.dependency_bundle_entries
            );
        }

        let mut edit =
            ue_asset::edit::open_export(&zp, &usmap, &scripts, export).expect("open export");
        let find_slot = |class: &str, want: &str| -> u16 {
            let total = usmap.total_slots(class);
            let mut slot = 0u16;
            while slot < total {
                if let Some((_, prop)) = usmap.resolve(class, slot) {
                    if prop.name == want {
                        return slot;
                    }
                    slot += prop.array_dim.max(1) as u16;
                } else {
                    slot += 1;
                }
            }
            panic!("{class} has no {want}");
        };
        let sm_slot = find_slot("StaticMesh", "StaticMaterials");
        let mi_slot = find_slot("StaticMaterial", "MaterialInterface");
        let name_slot = find_slot("StaticMaterial", "MaterialSlotName");
        let iname_slot = find_slot("StaticMaterial", "ImportedMaterialSlotName");
        let items = match edit.block.get(sm_slot) {
            Some(Val::Array(items)) => items.clone(),
            other => panic!("StaticMaterials is {other:?}"),
        };
        let template = items.first().cloned().expect("donor has a material slot");
        let mut new_items: Vec<Val> = vec![template.clone()];
        for (i, sp) in specs.iter().enumerate() {
            let mut item = match template.clone() {
                Val::Struct(b) => b,
                other => panic!("slot 0 is {other:?}"),
            };
            item.set(mi_slot, Val::Object(import_of[i]));
            item.set(
                name_slot,
                Val::Name(Name {
                    index: slot_names[i],
                    number: 0,
                }),
            );
            item.set(
                iname_slot,
                Val::Name(Name {
                    index: slot_names[i],
                    number: 0,
                }),
            );
            if sp.index == 0 {
                new_items[0] = Val::Struct(item);
            } else {
                new_items.push(Val::Struct(item));
            }
        }
        edit.block.set(sm_slot, Val::Array(new_items));
        ue_asset::edit::write_export(&mut zp, &usmap, &edit).expect("write export");
        // The header grew (names, imports): keep its distance from the cooked
        // header size constant, as the rename does.
        let once = zp.write();
        let new_header = u32::from_le_bytes(once[4..8].try_into().unwrap());
        zp.cooked_header_size =
            (zp.cooked_header_size as i64 + new_header as i64 - old_header as i64) as u32;
        let out = zp.write();
        println!("  header {old_header} -> {new_header}");

        // Read the slots back through the ordinary parser.
        let back = ue_asset::zen::Package::parse(&out).expect("re-parse");
        let bytes = back.export_data(&out, export).expect("export data");
        let ctx2 = Ctx {
            usmap: &usmap,
            names: &back.names,
        };
        let want = 1 + specs.iter().filter(|s| s.index != 0).count();
        match ue_asset::mesh::parse_static_mesh(&ctx2, bytes, None) {
            Ok(m) => {
                let names: Vec<String> = m
                    .materials
                    .iter()
                    .map(|(n, o)| {
                        let target = back
                            .import_target_of(*o)
                            .map(|t| t.package.rsplit('/').next().unwrap_or("").to_string())
                            .unwrap_or_else(|| format!("obj {o}"));
                        format!("{n}->{target}")
                    })
                    .collect();
                let good = m.materials.len() == want;
                println!(
                    "  materials read back: [{}] -- {}",
                    names.join(", "),
                    if good { "MATCHES" } else { "MISMATCH" }
                );
                if !good {
                    ok = false;
                }
            }
            Err(e) => {
                println!("  materials: re-parse failed: {e} -- MISMATCH");
                ok = false;
            }
        }
        out
    };

    std::fs::write(out_path, &package_bytes).expect("write package");
    println!("  wrote {out_path}");
    if !ok {
        std::process::exit(1);
    }
}

/// Whether a `--material` pattern claims a glTF material name: a substring
/// match, anchored to the end of the name when the pattern ends in `$`.
fn pattern_matches(pattern: &str, name: &str) -> bool {
    match pattern.strip_suffix('$') {
        Some(tail) => name.ends_with(tail),
        None => name.contains(pattern),
    }
}
