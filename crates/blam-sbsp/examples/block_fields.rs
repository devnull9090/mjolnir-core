//! Print the field names of one block's elements.
//!
//!   cargo run -p blam-sbsp --example block_fields -- <payload> <block path>
use blam_tag::blockedit::find_block;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let found = find_block(&layout, &file, &root, &args[1]).expect("block");
    println!("{}: {} element(s)", args[1], found.block.count);

    let run = layout
        .struct_run(found.block.struct_index)
        .expect("struct run");
    let range = layout.struct_ranges()[run].clone();
    let mut offset = 0u32;
    for i in range {
        let field = layout.fields[i];
        let name = layout.string_at(field.name_offset).unwrap_or("?");
        let kind = layout.type_name_of(&field);
        let size = layout.field_size(&field).unwrap_or(0);
        println!("  +{offset:<5} {kind:<26} {name}");
        offset += size;
    }
}
