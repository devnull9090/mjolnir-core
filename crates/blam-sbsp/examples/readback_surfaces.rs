//! Read selected native triangle surfaces in world units. Check that the
//! structure's static Havok tree and the definition's own tree both answer
//! at each triangle's centre. Arguments: BSP, instance, first, end, output.
use blam_sbsp::{convert, mopp, transplant, unpack16};
use blam_tag::blockedit::find_block;
use std::io::Write;

fn number(bytes: &[u8], offset: usize) -> f32 {
    f32::from_le_bytes(bytes[offset..offset + 4].try_into().unwrap())
}

fn tree(file: &[u8], path: &str) -> (Vec<u8>, mopp::Quant) {
    let (element, wrapper) = transplant::donor_element(file, path, 0).expect("tree block");
    let length = u32::from_le_bytes(wrapper[12..16].try_into().unwrap()) as usize;
    let quant = mopp::Quant {
        offset: [32, 36, 40].map(|k| number(&element, k)),
        scale: number(&element, 44),
    };
    (wrapper[20..20 + length].to_vec(), quant)
}

fn centre(points: &[[f32; 3]]) -> [f32; 3] {
    [0, 1, 2].map(|k| points.iter().map(|p| p[k]).sum::<f32>() / points.len() as f32)
}

fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("BSP payload");
    let inst: usize = args[1].parse().unwrap();
    let first: usize = args[2].parse().unwrap();
    let end: usize = args[3].parse().unwrap();
    let tag = blam_tag::TagFile::parse(&file, None).expect("tag");
    let layout = tag.layout().unwrap();
    let root = tag.read_data(&layout).unwrap();
    let instances = find_block(&layout, &file, &root, "instanced geometry instances").unwrap();
    let frame = instances.block.element(inst).unwrap();
    let definition = i16::from_le_bytes([frame[52], frame[53]]) as usize;
    let path = transplant::definition(definition);
    let get = |n: &str| {
        find_block(&layout, &file, &root, &format!("{path}.{n}"))
            .map(|b| b.block.elements)
            .unwrap_or(&[])
    };
    let tables = unpack16::Tables {
        bsp3d_nodes: get("bsp3d nodes"),
        planes: get("planes"),
        leaves: get("leaves"),
        bsp2d_references: get("bsp2d references"),
        bsp2d_nodes: get("bsp2d nodes"),
        surfaces: get("surfaces"),
        edges: get("edges"),
        vertices: get("vertices"),
    };
    let collision = unpack16::unpack(&tables).unwrap().0;
    let (root_code, root_q) = tree(&file, "structure_physics.mopp code block");
    let (code, q) = tree(
        &file,
        &format!("{}.mopp codes", path.trim_end_matches(".collision info")),
    );
    let mut output = std::io::BufWriter::new(std::fs::File::create(&args[4]).unwrap());
    for surface in first..end {
        let poly = unpack16::polygon(&collision, surface);
        assert_eq!(poly.len(), 3);
        let p = centre(&poly);
        let candidates = mopp::query(&code, &q.query_box(p, p)).unwrap();
        assert!(
            candidates.contains(&(surface as u32)),
            "missing definition surface {surface}"
        );
        let world: Vec<[f32; 3]> = poly
            .iter()
            .map(|v| {
                [0, 1, 2].map(|axis| {
                    let rotated = (0..3)
                        .map(|k| v[k] * number(frame, 4 + 12 * k + 4 * axis))
                        .sum::<f32>();
                    number(frame, 40 + axis * 4) + number(frame, 0) * rotated
                })
            })
            .collect();
        let w = centre(&world);
        let keys = mopp::query(&root_code, &root_q.query_box(w, w)).unwrap();
        assert!(
            keys.contains(&convert::instance_key(inst as u32))
                || keys.contains(&convert::surface_key(surface as u32, inst as u32)),
            "missing static shape for instance {inst}, surface {surface}"
        );
        for xyz in world {
            for v in xyz {
                output.write_all(&v.to_le_bytes()).unwrap();
            }
        }
    }
    output.flush().unwrap();
    println!(
        "verified {} world-space native surfaces in instance {inst}",
        end - first
    );
}
