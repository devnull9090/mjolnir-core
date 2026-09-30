//! Are the instance shape's `collision bsp reference pointer` fields payload
//! offsets? Print them beside the file offsets of the definition's tables.
//!
//!   cargo run -p blam-sbsp --example shape_ptrs -- <payload> <instance>...
use blam_sbsp::transplant;
use blam_tag::blockedit::find_block;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let base_ptr = file.as_ptr() as usize;
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let payload = tag.data().expect("bdat");
    println!("payload section at file offset {} size {}", payload.at, payload.size);
    let inst = find_block(&layout, &file, &root, "instanced geometry instances").expect("instances");
    for a in &args[1..] {
        let i: usize = a.parse().unwrap();
        let b = inst.block.element(i).unwrap();
        let def = i16::from_le_bytes([b[52], b[53]]) as usize;
        let shape = find_block(&layout, &file, &root, &format!("instanced geometry instances[{i}].physics[0].collision geometry shape")).expect("shape");
        let e = shape.block.element(0).unwrap();
        let p0 = i64::from_le_bytes(e[88..96].try_into().unwrap());
        let p1 = i64::from_le_bytes(e[96..104].try_into().unwrap());
        let rt = i32::from_le_bytes(e[80..84].try_into().unwrap());
        let off = |name: &str| -> usize {
            let f = find_block(&layout, &file, &root, &format!("{}.{name}", transplant::definition(def))).expect(name);
            f.block.elements.as_ptr() as usize - base_ptr
        };
        let defs = find_block(&layout, &file, &root, "resource interface.raw_resources[0].raw_items.instanced geometries definitions").expect("defs");
        let def_off = defs.block.element(def).unwrap().as_ptr() as usize - base_ptr;
        println!("instance {i} def {def}: ptr0 {p0} (0x{p0:x}) ptr1 {p1} (0x{p1:x}) runtime idx {rt}");
        println!("   def element @ {def_off} (payload-relative {}), nodes @ {}, surfaces @ {}, vertices @ {}",
            def_off as isize - payload.at as isize, off("bsp3d nodes"), off("surfaces"), off("vertices"));
    }
}
