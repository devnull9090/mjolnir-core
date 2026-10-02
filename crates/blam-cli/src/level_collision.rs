//! `mjolnir level collision` — a classic CE collision BSP, staged by halo2ue,
//! into a canvas structure BSP the simulation walks on, in one step.
//!
//! The canvas BSP is read from the game's own containers (never a mod's), the
//! terrain is put into a host definition and the broadphase above it is
//! recompiled ([`blam_sbsp::convert`]), and a transform file records where
//! the terrain went so the level generator and the mesh step place
//! everything else with the same numbers.

use std::path::PathBuf;

use anyhow::{bail, Context, Result};
use clap::Args;

use crate::index;
use crate::Source;
use blam_sbsp::convert::{self, Host, Options, Park, ShellOptions};
use blam_tag::TagFile;

/// A canvas BSP a terrain can be hosted in: the scenario, the BSP tag's leaf
/// name, the BSP's index in that scenario, the host slots, and the anchor the
/// terrain is centred on.
struct Canvas {
    scenario: &'static str,
    bsp_tag: &'static str,
    bsp_index: usize,
    host: Host,
    anchor: [f32; 3],
    /// A shipped shell with exactly one kd supernode, whose root companion
    /// tables go with the pass-through supernode.
    kd_template: &'static str,
}

/// B40's start BSP is the only host proven in game (2026-09-09).
const CANVASES: &[Canvas] = &[Canvas {
    scenario: "B40",
    bsp_tag: "BSP_01_1_Start",
    bsp_index: 8,
    host: Host::B40_START,
    anchor: convert::B40_START_ANCHOR,
    kd_template: "BSP_03_1_Chasm_old",
}];

#[derive(Args)]
pub struct CollisionArgs {
    /// The staged CE collision BSP: halo2ue's `collision_<N>.json` (its
    /// `.bin` sits beside it).
    pub collision: PathBuf,
    #[command(flatten)]
    pub src: Source,
    /// Where to write the converted scenario_structure_bsp tag file. Pass it
    /// to `level bake --standalone CODE --bsp INDEX=<this>`.
    #[arg(long)]
    pub out: PathBuf,
    /// Where to write the transform (JSON). Defaults to `<out>.transform.json`.
    #[arg(long)]
    pub transform: Option<PathBuf>,
    /// The canvas scenario hosting the terrain.
    #[arg(long, default_value = "B40")]
    pub canvas: String,
    /// Move the terrain by this CE-to-canvas offset instead of centring it
    /// on the canvas anchor.
    #[arg(long, num_args = 3, value_names = ["DX", "DY", "DZ"], allow_hyphen_values = true)]
    pub delta: Option<Vec<f32>>,
    /// Centre the terrain's footprint on this canvas point instead of the
    /// canvas's own anchor; its lowest point goes to Z.
    #[arg(long, num_args = 3, value_names = ["X", "Y", "Z"], allow_hyphen_values = true, conflicts_with = "delta")]
    pub anchor: Option<Vec<f32>>,
    /// Park exactly these canvas instances (comma separated) instead of every
    /// instance under the terrain's footprint.
    #[arg(long, value_delimiter = ',', conflicts_with_all = ["park_margin", "no_park"])]
    pub park: Option<Vec<usize>>,
    /// Grow the footprint used to pick instances to park by this many wu.
    #[arg(long, default_value_t = 2.0)]
    pub park_margin: f32,
    /// Leave every canvas instance where it is.
    #[arg(long)]
    pub no_park: bool,
    /// Where parked instances go.
    #[arg(long, default_value_t = -500.0, allow_hyphen_values = true)]
    pub park_z: f32,
    /// Leave the canvas's world shell alone. Its inside/outside test then
    /// decides whether the terrain is in the world at all, which holds only
    /// where the terrain overlaps the canvas's own playable space.
    #[arg(long)]
    pub keep_canvas_shell: bool,
    /// Build a BSP that is only the CE map: its collision in the world shell
    /// of a one-supernode donor (the canvas's small kd template BSP), the
    /// donor's instances parked, and the static Havok body listing exactly
    /// the CE surfaces. Nothing of the canvas mission's geometry is used, so
    /// the map keeps its own coordinates.
    #[arg(long, conflicts_with_all = ["keep_canvas_shell", "anchor", "park"])]
    pub own_bsp: bool,
    /// With `--own-bsp`: raise the map this many wu. The map keeps its CE
    /// coordinates by default; the generated level loads only its own BSP
    /// (`blam.active_bsps`), so no canvas BSP claims its space. Keep it inside
    /// the canvas level's overall extent: lifted 800 wu above B40, Havok
    /// flung vehicles hundreds of wu and nothing held.
    #[arg(long, default_value_t = 0.0, allow_hyphen_values = true)]
    pub lift: f32,
    /// With `--own-bsp`: build the BSP for this index in the baked scenario
    /// instead of the canvas slot it is cloned into. `0` goes with the bake's
    /// `blam.single_bsp`, which leaves the map's BSP the scenario's only one.
    #[arg(long, requires = "own_bsp")]
    pub bsp_index: Option<u8>,
}

/// What `level collision` wrote, for the steps that place things on top.
#[derive(serde::Serialize)]
struct Transform {
    /// Added to every CE world coordinate to reach canvas world space.
    delta: [f32; 3],
    canvas: String,
    bsp_tag: String,
    /// The canvas scenario's index for this BSP: `level bake --bsp INDEX=`.
    bsp_index: usize,
    /// The index the BSP is built for in the baked scenario: `bsp_index`,
    /// or 0 for a scenario trimmed to this BSP alone (`blam.single_bsp`).
    scenario_bsp_index: usize,
    /// The terrain's box in canvas world space: `blam.world_bounds`.
    world_bounds: Bounds,
    host: HostOut,
    parked: Vec<usize>,
    /// The BSP is the CE map alone (`--own-bsp`): its world box is the
    /// terrain's, not grown to cover the canvas BSP's.
    own_bsp: bool,
}

#[derive(serde::Serialize)]
struct Bounds {
    min: [f32; 3],
    max: [f32; 3],
}

#[derive(serde::Serialize)]
struct HostOut {
    definition: usize,
    instance: usize,
    group: usize,
}

pub fn run(a: CollisionArgs) -> Result<()> {
    let canvas = CANVASES
        .iter()
        .find(|c| c.scenario.eq_ignore_ascii_case(&a.canvas))
        .with_context(|| {
            let known: Vec<&str> = CANVASES.iter().map(|c| c.scenario).collect();
            format!(
                "no host is known in canvas {:?}; known: {known:?}",
                a.canvas
            )
        })?;

    let staged = blam_sbsp::ce::load(&a.collision)
        .map_err(|e| anyhow::anyhow!("{e}"))
        .with_context(|| format!("reading {}", a.collision.display()))?;
    let ce_bounds = staged
        .collision
        .bounds()
        .context("the collision BSP has no vertices")?;

    let idx = index::build(&a.src.paks)?;
    let shipped_bsp = |leaf: &str| -> Result<Vec<u8>> {
        let want = format!(
            "/solo/{}/_generated_/{}-scenario_structure_bsp.ubulk",
            canvas.scenario, leaf
        )
        .to_lowercase();
        let entry = idx
            .tags
            .iter()
            .find(|e| {
                e.path.to_lowercase().ends_with(&want)
                    && !crate::extract::is_override(&idx.containers[e.container])
            })
            .with_context(|| format!("no shipped {} {leaf} in the containers", canvas.scenario))?;
        println!("{}", entry.path);
        idx.read(entry, None, &a.src.oodle_roots())
    };
    if a.own_bsp {
        let donor = shipped_bsp(canvas.kd_template)?;
        println!("  donor    {} bytes ({})", donor.len(), canvas.kd_template);
        let delta = match &a.delta {
            Some(d) if d.len() == 3 => [d[0], d[1], d[2]],
            _ => [0.0, 0.0, a.lift],
        };
        println!(
            "  delta    ({:.3}, {:.3}, {:.3})",
            delta[0], delta[1], delta[2]
        );
        // Each surface keeps its CE material, and the BSP gets the game's
        // material for each (write_collision_materials).
        let materials = staged.manifest.materials.clone();
        // A map whose scenery collision overflows one definition's 16-bit
        // tables (Timberland's trees) keeps the BSP in definition 0 and puts
        // the scenery behind instances of its own, 8,192 surfaces each so
        // every surface keeps a key of its own in the structure body.
        let mut collision = staged.collision;
        let mut scenery = Vec::new();
        if let (Err(why), Some(tail)) = (collision.fits_16bit(), staged.manifest.scenery_surfaces) {
            let first = collision.surfaces.len().saturating_sub(tail.surfaces);
            scenery = blam_sbsp::split::split_standalone(
                &mut collision,
                first,
                convert::MAX_SURFACE_KEYS,
            )
            .map_err(|e| anyhow::anyhow!("{e}"))?;
            println!(
                "  scenery  {why}: {} scenery surface(s) of {} object(s) go to {} instance(s) of their own",
                tail.surfaces,
                tail.objects,
                scenery.len()
            );
        }
        let scenario_bsp = a.bsp_index.unwrap_or(canvas.bsp_index as u8);
        let (mut out, r) = convert::convert_own(
            &donor,
            collision,
            scenery,
            delta,
            scenario_bsp,
            !materials.is_empty(),
        )
        .map_err(|e| anyhow::anyhow!("{e}"))?;
        if a.bsp_index.is_some() {
            // The donor's own headers and shapes still name its index.
            let (o, n) =
                convert::retarget_bsp(&out, scenario_bsp).map_err(|e| anyhow::anyhow!("{e}"))?;
            out = o;
            println!("  bsp      built for scenario index {scenario_bsp} ({n} kd header(s) and shape(s) set)");
        }
        if !r.scenery.instances.is_empty() {
            println!(
                "  scenery  {} surface(s) behind instance(s) {:?}",
                r.scenery.surfaces, r.scenery.instances
            );
        }
        let names = write_collision_materials(&mut out, &materials, &idx, &a.src.oodle_roots())?;
        let mut tally: std::collections::BTreeMap<&str, usize> = Default::default();
        for n in &names {
            *tally.entry(n.as_str()).or_default() += 1;
        }
        println!(
            "  material {} collision material(s): {}",
            names.len(),
            tally
                .iter()
                .map(|(n, c)| format!("{n} x{c}"))
                .collect::<Vec<_>>()
                .join(", ")
        );
        let b = r.bounds;
        println!(
            "  terrain  x[{:.2}, {:.2}] y[{:.2}, {:.2}] z[{:.2}, {:.2}], {} surface(s) in the shell and definition 0",
            b.min[0], b.max[0], b.min[1], b.max[1], b.min[2], b.max[2], r.surfaces
        );
        println!(
            "  havok    structure_physics: {} shell + {} kept + {} new key(s), {} B; kd roots {:?}",
            r.structure.shell, r.structure.kept, r.structure.added, r.structure.code, r.kd_roots
        );
        std::fs::write(&a.out, &out).with_context(|| format!("writing {}", a.out.display()))?;
        println!(
            "wrote {} ({} bytes, walks exactly)",
            a.out.display(),
            out.len()
        );
        let transform = Transform {
            delta,
            canvas: canvas.scenario.to_string(),
            bsp_tag: canvas.bsp_tag.to_string(),
            bsp_index: canvas.bsp_index,
            scenario_bsp_index: scenario_bsp as usize,
            world_bounds: Bounds {
                min: b.min,
                max: b.max,
            },
            host: HostOut {
                definition: 0,
                instance: 0,
                group: 0,
            },
            parked: r.parked,
            own_bsp: true,
        };
        let tpath = a.transform.clone().unwrap_or_else(|| {
            let mut p = a.out.clone().into_os_string();
            p.push(".transform.json");
            PathBuf::from(p)
        });
        std::fs::write(
            &tpath,
            serde_json::to_string_pretty(&transform)?
                + "
",
        )
        .with_context(|| format!("writing {}", tpath.display()))?;
        println!("wrote {}", tpath.display());
        return Ok(());
    }
    let donor = shipped_bsp(canvas.bsp_tag)?;
    println!("  canvas   {} bytes", donor.len());
    let shell = if a.keep_canvas_shell {
        None
    } else {
        Some(ShellOptions {
            kd_template: shipped_bsp(canvas.kd_template)?,
        })
    };

    let mut opts = Options {
        host: canvas.host,
        delta: convert::delta_to_anchor(ce_bounds, canvas.anchor),
        park: Park::Footprint {
            margin: a.park_margin,
        },
        park_z: a.park_z,
        shell,
        bsp_index: canvas.bsp_index as u8,
        keep_materials: false,
    };
    if let Some(p) = &a.anchor {
        if p.len() != 3 {
            bail!("--anchor takes three numbers");
        }
        opts.delta = convert::delta_to_anchor(ce_bounds, [p[0], p[1], p[2]]);
    }
    if let Some(d) = &a.delta {
        if d.len() != 3 {
            bail!("--delta takes three numbers");
        }
        opts.delta = [d[0], d[1], d[2]];
    }
    if a.no_park {
        opts.park = Park::None;
    } else if let Some(ids) = &a.park {
        opts.park = Park::Listed(ids.clone());
    }
    println!(
        "  CE       x[{:.2}, {:.2}] y[{:.2}, {:.2}] z[{:.2}, {:.2}], {} surface(s)",
        ce_bounds.min[0],
        ce_bounds.max[0],
        ce_bounds.min[1],
        ce_bounds.max[1],
        ce_bounds.min[2],
        ce_bounds.max[2],
        staged.collision.surfaces.len()
    );
    println!(
        "  delta    ({:.3}, {:.3}, {:.3})",
        opts.delta[0], opts.delta[1], opts.delta[2]
    );

    let (out, r) =
        convert::convert(&donor, staged.collision, &opts).map_err(|e| anyhow::anyhow!("{e}"))?;
    let b = r.bounds;
    println!(
        "  terrain  x[{:.2}, {:.2}] y[{:.2}, {:.2}] z[{:.2}, {:.2}]",
        b.min[0], b.max[0], b.min[1], b.max[1], b.min[2], b.max[2]
    );
    println!(
        "  host     definition {} ({} surface(s), {} fan-split), instance {}, group {} (sphere r {:.2})",
        opts.host.definition, r.surfaces, r.split, opts.host.instance, opts.host.group, r.sphere_radius
    );
    println!(
        "  mopp     definition {} B, group {} B, cluster {} B",
        r.definition_code, r.group_code, r.cluster_code
    );
    println!(
        "  parked   {} canvas instance(s) at z {}",
        r.parked.len(),
        a.park_z
    );
    // Every instance of the host definition carries the terrain, each at its
    // own frame; any but the host that is not parked is a second copy.
    let sharing: Vec<usize> = convert::instances_of(&out, opts.host.definition)
        .map_err(|e| anyhow::anyhow!("{e}"))?
        .into_iter()
        .filter(|i| *i != opts.host.instance && !r.parked.contains(i))
        .collect();
    if !sharing.is_empty() {
        println!("  WARNING  instance(s) {sharing:?} also name definition {} and now carry the terrain too", opts.host.definition);
    }
    println!(
        "  havok    structure_physics rebuilt: {} shell + {} kept + {} new key(s), {} dropped, {} B",
        r.structure.shell, r.structure.kept, r.structure.added, r.structure.dropped, r.structure.code
    );
    if !r.kd_roots.is_empty() {
        println!(
            "  kd       host added to collision kd root node(s) {:?}",
            r.kd_roots
        );
    }
    println!(
        "  shell    {}",
        if a.keep_canvas_shell {
            "the canvas's own (inside test unchanged)"
        } else {
            "the terrain, pass-through supernode (inside test follows the CE map)"
        }
    );

    std::fs::write(&a.out, &out).with_context(|| format!("writing {}", a.out.display()))?;
    println!(
        "wrote {} ({} bytes, walks exactly)",
        a.out.display(),
        out.len()
    );

    let transform = Transform {
        delta: opts.delta,
        canvas: canvas.scenario.to_string(),
        bsp_tag: canvas.bsp_tag.to_string(),
        bsp_index: canvas.bsp_index,
        scenario_bsp_index: canvas.bsp_index,
        world_bounds: Bounds {
            min: b.min,
            max: b.max,
        },
        host: HostOut {
            definition: opts.host.definition,
            instance: opts.host.instance,
            group: opts.host.group,
        },
        parked: r.parked,
        own_bsp: false,
    };
    let tpath = a.transform.clone().unwrap_or_else(|| {
        let mut p = a.out.clone().into_os_string();
        p.push(".transform.json");
        PathBuf::from(p)
    });
    std::fs::write(&tpath, serde_json::to_string_pretty(&transform)? + "\n")
        .with_context(|| format!("writing {}", tpath.display()))?;
    println!("wrote {}", tpath.display());
    println!("  This is game content. Keep it local; the repository does not take tag data.");
    Ok(())
}

/// The game material a CE shader `material type` becomes: the name of a
/// globals `materials` entry that ships a `shaders\<name>` render method
/// (the shipped BSPs' collision materials point at those).
fn game_material_for(ce_type: Option<u16>) -> &'static str {
    match ce_type {
        Some(0) => "tough_terrain_dirt",
        Some(1) => "tough_terrain_sand",
        Some(2) => "hard_terrain_stone",
        Some(3) => "soft_terrain_snow",
        Some(4) => "tough_organic_wood",
        Some(5) | Some(6) => "hard_metal_thin",
        Some(7) => "hard_metal_thick",
        Some(8) => "tough_inorganic_rubber",
        Some(9) => "brittle_glass",
        Some(10) => "energy_hologram",
        Some(28) => "liquid_thin_water",
        Some(29) => "soft_organic_plant",
        Some(31) => "hard_terrain_ice",
        _ => "default_material",
    }
}

fn text_of(v: &blam_tag::Scalar) -> String {
    match v {
        blam_tag::Scalar::Text(t) => t.clone(),
        other => other.display().trim_matches('"').to_string(),
    }
}

/// Give the converted BSP one `collision materials` entry per CE collision
/// material, in CE order, so a surface's kept material index finds its own:
/// the render method is the game's `shaders\<material>` and the runtime
/// global material index is that material's place in `globals`. Footsteps,
/// tire dust and bullet impacts are picked from these.
fn write_collision_materials(
    file: &mut Vec<u8>,
    materials: &[blam_sbsp::ce::Material],
    idx: &index::Index,
    oodle: &[PathBuf],
) -> Result<Vec<String>> {
    use blam_tag::patch::{self, ElementOp};

    let read_tag = |suffix: &str| -> Result<Vec<u8>> {
        let want = suffix.to_lowercase();
        let entry = idx
            .tags
            .iter()
            .find(|e| e.path.to_lowercase().ends_with(&want))
            .with_context(|| format!("no {suffix} in the containers"))?;
        idx.read(entry, None, oodle)
    };
    let resolve = |bytes: &[u8], path: &str| -> Result<blam_tag::Scalar> {
        let tag = TagFile::parse(bytes, Some(bytes.len()))?;
        let l = tag.layout()?;
        let block = tag.read_data(&l)?;
        Ok(patch::resolve(&l, bytes, &block, path)?.current)
    };

    // globals: material name -> index.
    let globals = read_tag("/tags/globals/globals-globals.ubulk")?;
    let mut global_index = std::collections::HashMap::new();
    {
        let tag = TagFile::parse(&globals, Some(globals.len()))?;
        let l = tag.layout()?;
        let block = tag.read_data(&l)?;
        for i in 0.. {
            match patch::resolve(&l, &globals, &block, &format!("materials[{i}].name")) {
                Ok(t) => {
                    global_index.insert(text_of(&t.current), i as i64);
                }
                Err(_) => break,
            }
        }
    }

    // One entry per CE material; the shader's own `material name` decides the
    // global index (shaders\invalid is hard_metal_solid, not "invalid").
    let mut wanted = Vec::new();
    let mut names = Vec::new();
    for m in materials {
        let name = m
            .game_material
            .clone()
            .unwrap_or_else(|| game_material_for(m.material_type).to_string());
        let shader = read_tag(&format!("/tags/shaders/{name}-shader.ubulk"))
            .with_context(|| format!("no shipped shaders\\{name} for {}", m.shader_path))?;
        let material_name = text_of(&resolve(&shader, "material name")?);
        let global = *global_index.get(&material_name).with_context(|| {
            format!("shaders\\{name} names material {material_name:?}, not in globals")
        })?;
        wanted.push((format!("rmsh:shaders\\{name}"), global));
        names.push(name);
    }
    if wanted.is_empty() {
        return Ok(names);
    }

    // Size the block by duplicating or removing elements of the donor's own.
    let edit = |file: &mut Vec<u8>, op: ElementOp| -> Result<()> {
        let tag = TagFile::parse(file, Some(file.len()))?;
        let l = tag.layout()?;
        let block = tag.read_data(&l)?;
        let (out, _) = patch::edit_elements(&l, file, &block, "collision materials", op)?;
        *file = out;
        Ok(())
    };
    let count = || -> Result<usize> {
        let mut n = 0;
        while resolve(file, &format!("collision materials[{n}].render method")).is_ok() {
            n += 1;
        }
        Ok(n)
    };
    let mut have = count()?;
    if have == 0 {
        bail!("the donor BSP has no collision materials to clone");
    }
    while have < wanted.len() {
        edit(file, ElementOp::Duplicate(0))?;
        have += 1;
    }
    while have > wanted.len() {
        edit(file, ElementOp::Remove(have - 1))?;
        have -= 1;
    }
    for (i, (reference, global)) in wanted.iter().enumerate() {
        set_field(
            file,
            &format!("collision materials[{i}].render method"),
            &crate::parse_reference(reference)?,
        )?;
        set_field(
            file,
            &format!("collision materials[{i}].runtime global material index"),
            &blam_tag::Scalar::Int(*global),
        )?;
    }
    Ok(names)
}

fn set_field(file: &mut Vec<u8>, path: &str, value: &blam_tag::Scalar) -> Result<()> {
    let tag = TagFile::parse(file, Some(file.len()))?;
    let l = tag.layout()?;
    let block = tag.read_data(&l)?;
    let target = blam_tag::patch::resolve(&l, file, &block, path)?;
    // References (and string ids) live in the text section.
    let (out, _) = if target.section.is_some() {
        blam_tag::patch::set_text(&l, file, &block, path, value)?
    } else {
        blam_tag::patch::set(&l, file, &block, path, value)?
    };
    *file = out;
    Ok(())
}
