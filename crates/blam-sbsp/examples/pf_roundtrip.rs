//! Prove the writer for a pathfinding BSP's `object refs`: rebuild them the way
//! a generator must (new elements cloned from a donor with its wrapper, then
//! each object's `bsps` element and `bsp2d refs` replaced) and compare the file
//! with the original, byte for byte. Also shows what the naive write (no
//! wrappers) does to the same data.
//!   cargo run -p blam-sbsp --example pf_roundtrip -- <scenario> <bsp index>
use blam_tag::blockedit::{element_with_wrapper, find_block, replace_nested, NestedReplace};

struct Object {
    element: Vec<u8>,
    bsps: Vec<u8>,
    refs: Vec<u8>,
    ref_count: u32,
}

fn read(scn: &[u8], pf: &str) -> Vec<Object> {
    let tag = blam_tag::TagFile::parse(scn, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let objs = find_block(&layout, scn, &root, &format!("{pf}.object refs")).expect("object refs");
    (0..objs.block.count as usize)
        .map(|o| {
            let bsps = find_block(&layout, scn, &root, &format!("{pf}.object refs[{o}].bsps")).expect("bsps");
            assert_eq!(bsps.block.count, 1, "object {o} has one bsps entry");
            let refs = find_block(&layout, scn, &root, &format!("{pf}.object refs[{o}].bsps[0].bsp2d refs")).expect("refs");
            Object {
                element: objs.block.element(o).unwrap().to_vec(),
                bsps: bsps.block.element(0).unwrap().to_vec(),
                refs: refs.block.elements.to_vec(),
                ref_count: refs.block.count,
            }
        })
        .collect()
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let original = std::fs::read(&a[0]).expect("scenario");
    let bi: usize = a[1].parse().unwrap();
    let pf = format!("ai pathfinding data[{bi}]");
    let objects = read(&original, &pf);
    println!("{} object refs, {} refs in all", objects.len(), objects.iter().map(|o| o.ref_count).sum::<u32>());

    // Empty the block first, so nothing of the original survives by accident.
    let empty = replace_nested(
        &original,
        &[NestedReplace { path: format!("{pf}.object refs"), count: 0, elements: Vec::new(), wrappers: None }],
    )
    .expect("empty");
    assert_ne!(empty, original);

    // The donor: any object ref with its wrapper (its bsps child and that child's refs).
    let (_, donor) = element_with_wrapper(&original, &format!("{pf}.object refs"), 0).expect("donor");

    // 1. All objects, each with the donor's children.
    let mut file = replace_nested(
        &empty,
        &[NestedReplace {
            path: format!("{pf}.object refs"),
            count: objects.len() as u32,
            elements: objects.iter().flat_map(|o| o.element.clone()).collect(),
            wrappers: Some(vec![donor.clone(); objects.len()]),
        }],
    )
    .expect("objects");
    // 2. Each object's own refs (a leaf block), then its bsps element's bytes.
    for (o, object) in objects.iter().enumerate() {
        file = replace_nested(
            &file,
            &[NestedReplace {
                path: format!("{pf}.object refs[{o}].bsps[0].bsp2d refs"),
                count: object.ref_count,
                elements: object.refs.clone(),
                wrappers: None,
            }],
        )
        .expect("refs");
        let (_, wrapper) = element_with_wrapper(&file, &format!("{pf}.object refs[{o}].bsps"), 0).expect("bsps wrapper");
        file = replace_nested(
            &file,
            &[NestedReplace {
                path: format!("{pf}.object refs[{o}].bsps"),
                count: 1,
                elements: object.bsps.clone(),
                wrappers: Some(vec![wrapper]),
            }],
        )
        .expect("bsps");
    }
    println!(
        "rebuilt with wrappers: {} bytes, original {} bytes, identical: {}",
        file.len(),
        original.len(),
        file == original
    );
    let back = read(&file, &pf);
    let same = back.len() == objects.len()
        && back.iter().zip(&objects).all(|(x, y)| x.element == y.element && x.bsps == y.bsps && x.refs == y.refs);
    println!("reads back the same objects: {same}");

    // The naive write: elements with no wrappers.
    let naive = replace_nested(
        &empty,
        &[NestedReplace {
            path: format!("{pf}.object refs"),
            count: objects.len() as u32,
            elements: objects.iter().flat_map(|o| o.element.clone()).collect(),
            wrappers: None,
        }],
    )
    .expect("naive");
    let tag = blam_tag::TagFile::parse(&naive, None).expect("parse naive");
    let layout = tag.layout().expect("layout");
    match tag.read_data(&layout) {
        Ok(root) => match find_block(&layout, &naive, &root, &format!("{pf}.object refs[0].bsps")) {
            Ok(f) => println!(
                "naive write (no wrappers): element says {} bsps, the block holds {}",
                i32::from_le_bytes(objects[0].element[4..8].try_into().unwrap()),
                f.block.count
            ),
            Err(e) => println!("naive write (no wrappers): bsps unreadable: {e:?}"),
        },
        Err(e) => println!("naive write (no wrappers): the tag no longer reads: {e:?}"),
    }
}
