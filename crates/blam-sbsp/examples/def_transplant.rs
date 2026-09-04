//! Put a staged CE collision BSP into one instanced-geometry definition, and
//! point its instance at it.
//!
//! ```text
//! cargo run -p blam-sbsp --example def_transplant -- \
//!     <donor.ubulk> <collision.json> <out.ubulk> <def index> <instance index> [dx dy dz]
//! ```
//!
//! The world shell is not what the simulation walks on; instanced geometry is,
//! and each instance's Havok shape is built at load from its definition's
//! collision tables. So the terrain goes into a definition, and the instance
//! that names it is reset to an identity frame (scale 1, world axes, origin)
//! so definition-local coordinates are world units.
use blam_sbsp::ce;
use blam_sbsp::pack16;
use blam_sbsp::transplant::{self, passthrough_from};
use blam_tag::blockedit::{find_block, replace_nested, NestedReplace};

const INSTANCES: &str = "instanced geometry instances";

fn main() {
    let mut args: Vec<String> = std::env::args().skip(1).collect();
    let passthrough = args.iter().any(|a| a == "--passthrough-supernode");
    // Leave the instance where it sits (only its rotation and scale are reset)
    // and pre-subtract its position from the geometry. An instance that keeps
    // its place stays inside the instance-group volumes the broadphase walks;
    // one moved to the origin is culled before its shape is ever tested.
    let keep_pos = args.iter().any(|a| a == "--keep-position");
    args.retain(|a| a != "--passthrough-supernode" && a != "--keep-position");
    if args.len() < 5 {
        eprintln!(
            "usage: def_transplant <donor.ubulk> <collision.json> <out.ubulk> \
             <def index> <instance index> [dx dy dz]"
        );
        std::process::exit(2);
    }
    let donor = std::fs::read(&args[0]).expect("donor");
    let staged = ce::load(std::path::Path::new(&args[1])).expect("staging");
    let def: usize = args[3].parse().expect("def index");
    let instance: usize = args[4].parse().expect("instance index");
    let delta = if args.len() >= 8 {
        [
            args[5].parse().expect("dx"),
            args[6].parse().expect("dy"),
            args[7].parse().expect("dz"),
        ]
    } else {
        [0.0f32; 3]
    };

    // The instance's own frame, needed before the geometry is placed.
    let probe = blam_tag::TagFile::parse(&donor, None).expect("parse");
    let probe_layout = probe.layout().expect("layout");
    let probe_root = probe.read_data(&probe_layout).expect("data");
    let inst_block = find_block(&probe_layout, &donor, &probe_root, INSTANCES).expect("instances");
    let inst_bytes = inst_block.block.element(instance).expect("instance");
    let read_f32 = |o: usize| f32::from_le_bytes(inst_bytes[o..o + 4].try_into().unwrap());
    let inst_pos = [read_f32(40), read_f32(44), read_f32(48)];

    let mut collision = staged.collision;
    let local_delta = if keep_pos {
        [
            delta[0] - inst_pos[0],
            delta[1] - inst_pos[1],
            delta[2] - inst_pos[2],
        ]
    } else {
        delta
    };
    if local_delta != [0.0; 3] {
        pack16::translate(&mut collision, local_delta);
    }
    let local_bounds = collision.bounds().expect("bounds");
    let bounds = if keep_pos {
        blam_sbsp::ce::Bounds {
            min: [
                local_bounds.min[0] + inst_pos[0],
                local_bounds.min[1] + inst_pos[1],
                local_bounds.min[2] + inst_pos[2],
            ],
            max: [
                local_bounds.max[0] + inst_pos[0],
                local_bounds.max[1] + inst_pos[1],
                local_bounds.max[2] + inst_pos[2],
            ],
        }
    } else {
        local_bounds
    };
    println!(
        "  collision {} surface(s), {} vertices, bounds x[{:.2},{:.2}] y[{:.2},{:.2}] z[{:.2},{:.2}]",
        collision.surfaces.len(),
        collision.vertices.len(),
        bounds.min[0], bounds.max[0], bounds.min[1], bounds.max[1], bounds.min[2], bounds.max[2],
    );

    // Every CE material lands on the definition's material 0: what the floor
    // sounds like is a later pass.
    let packed = pack16::pack(&collision, &(|_: i16| 0i16)).expect("pack");

    let base = transplant::definition(def);
    let mut edits = transplant::tables_at(&base, &packed);

    // Supernodes are a kd index over the node forest, sized to the forest that
    // shipped; nine shipped definitions carry none at all, so the plain tree
    // from node 0 is a legal configuration. A single pass-through supernode
    // over a 12,000-node tree hung the simulation, so none is the default and
    // `--passthrough-supernode` asks for the other behaviour.
    let tag = blam_tag::TagFile::parse(&donor, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let supers = find_block(&layout, &donor, &root, &format!("{base}.bsp3d supernodes"))
        .expect("supernodes");
    let (count, bytes) = if passthrough {
        let e = supers
            .block
            .element(0)
            .map(passthrough_from)
            .expect("the definition has no supernode to build a pass-through from");
        (1, e)
    } else {
        (0, Vec::new())
    };
    edits.push(NestedReplace {
        path: format!("{base}.bsp3d supernodes"),
        count,
        elements: bytes,
        wrappers: None,
    });

    let mut file = replace_nested(&donor, &edits).expect("replace");

    // The instance: identity frame at the origin, bounds and bounding sphere
    // around the new geometry, so nothing culls it before the trace runs.
    let centre = [
        (bounds.min[0] + bounds.max[0]) / 2.0,
        (bounds.min[1] + bounds.max[1]) / 2.0,
        (bounds.min[2] + bounds.max[2]) / 2.0,
    ];
    let radius = ((bounds.max[0] - centre[0]).powi(2)
        + (bounds.max[1] - centre[1]).powi(2)
        + (bounds.max[2] - centre[2]).powi(2))
    .sqrt();
    let p = format!("{INSTANCES}[{instance}]");
    let sets: Vec<(String, String)> = vec![
        (format!("{p}.scale"), "1.0".into()),
        (format!("{p}.forward"), "(1.0, 0.0, 0.0)".into()),
        (format!("{p}.left"), "(0.0, 1.0, 0.0)".into()),
        (format!("{p}.up"), "(0.0, 0.0, 1.0)".into()),
        (
            format!("{p}.position"),
            if keep_pos {
                format!("({}, {}, {})", inst_pos[0], inst_pos[1], inst_pos[2])
            } else {
                "(0.0, 0.0, 0.0)".into()
            },
        ),
        (format!("{p}.bounds x0"), format!("{}", bounds.min[0])),
        (format!("{p}.bounds x1"), format!("{}", bounds.max[0])),
        (format!("{p}.bounds y0"), format!("{}", bounds.min[1])),
        (format!("{p}.bounds y1"), format!("{}", bounds.max[1])),
        (format!("{p}.bounds z0"), format!("{}", bounds.min[2])),
        (format!("{p}.bounds z1"), format!("{}", bounds.max[2])),
        (
            format!("{p}.world bounding sphere center"),
            format!("({}, {}, {})", centre[0], centre[1], centre[2]),
        ),
        (format!("{p}.world bounding sphere radius"), format!("{radius}")),
        // The Havok shape's own box, which the broadphase reads before the
        // tree is walked: leaving the donor's tiny box behind the new geometry
        // is asking for trouble.
        (
            format!("{p}.physics[0].collision geometry shape[0].center"),
            format!("({}, {}, {})", centre[0], centre[1], centre[2]),
        ),
        (
            format!("{p}.physics[0].collision geometry shape[0].half extent"),
            format!(
                "({}, {}, {})",
                (bounds.max[0] - bounds.min[0]) / 2.0,
                (bounds.max[1] - bounds.min[1]) / 2.0,
                (bounds.max[2] - bounds.min[2]) / 2.0
            ),
        ),
        (
            format!("{p}.physics[0].collision geometry shape[0].scale"),
            "1.0".into(),
        ),
    ];
    for (path, value) in &sets {
        match transplant::set_scalar(&file, path, value) {
            Ok(out) => {
                file = out;
                println!("  set {path} = {value}");
            }
            Err(e) => println!("  skip {path}: {e}"),
        }
    }

    // It must still walk exactly, or the game will not read it.
    let tag = blam_tag::TagFile::parse(&file, None).expect("reparse");
    let l = tag.layout().expect("relayout");
    let block = tag.read_data(&l).expect("reread");
    let payload = tag.data().expect("bdat");
    assert_eq!(
        block.consumed, payload.size as usize,
        "the rewritten payload does not walk exactly"
    );
    std::fs::write(&args[2], &file).expect("write");
    println!(
        "  wrote {} ({} -> {} bytes, walks exactly)",
        args[2],
        donor.len(),
        file.len()
    );
}
