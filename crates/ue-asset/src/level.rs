//! Reading a cooked level cell: the placed static meshes and their world
//! transforms.
//!
//! A World Partition level ships as a persistent `.umap` plus one generated
//! streaming cell per grid square (`<Level>/_Generated_/<id>.umap`). Each
//! cell holds actors and their scene components as exports. A component's
//! transform is `RelativeLocation` / `RelativeRotation` / `RelativeScale3D`
//! composed up its `AttachParent` chain; an instanced component (the bulk of
//! every cell — foliage, scree, rocks) keeps its per-instance matrices in
//! the native bytes that trail its properties, bulk-serialized as
//! `[element size 128][count][count × FMatrix of doubles]`.
//!
//! A property a placed component leaves unset is inherited from its
//! template: a Blueprint's component template in the Blueprint package
//! (`StaticMeshComponent0_GEN_VARIABLE`), reached through the export's
//! template reference. The rock Blueprints get their mesh that way.
//!
//! Matrices here are Unreal's: row-major, row vectors (`v' = v × M`),
//! translation in the last row, centimetres, +Z up. The glTF writer converts.

use std::cell::RefCell;
use std::collections::{BTreeMap, HashMap};
use std::rc::Rc;

use crate::unversioned::{Ctx, Keep, Value, Walker};
use crate::zen::{ObjectRef, Package, ScriptObjects};
use crate::Usmap;

pub type Matrix = [[f64; 4]; 4];

/// The `/Game/...` (or `/Engine/...`, `/<Plugin>/...`) package name of a
/// container file path such as `../../../Meteorite/Content/Env/X.uasset`,
/// without its extension. None for files outside a content root.
pub fn package_name_of(full_path: &str) -> Option<String> {
    let path = full_path.strip_prefix("../../../").unwrap_or(full_path);
    let stem = path
        .strip_suffix(".uasset")
        .or_else(|| path.strip_suffix(".umap"))
        .or_else(|| path.strip_suffix(".ubulk"))
        .or_else(|| path.strip_suffix(".uptnl"))?;
    if let Some(rest) = stem.strip_prefix("Meteorite/Content/") {
        return Some(format!("/Game/{rest}"));
    }
    if let Some(rest) = stem.strip_prefix("Engine/Content/") {
        return Some(format!("/Engine/{rest}"));
    }
    // A plugin mounts its Content folder under its own name.
    let at = stem.find("/Content/")?;
    let plugin = stem[..at].rsplit('/').next()?;
    Some(format!("/{plugin}/{}", &stem[at + "/Content/".len()..]))
}

pub const IDENTITY: Matrix = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
];

/// `a` then `b`, in row-vector convention: `v × a × b`.
pub fn multiply(a: &Matrix, b: &Matrix) -> Matrix {
    let mut out = [[0.0; 4]; 4];
    for (i, row) in out.iter_mut().enumerate() {
        for (j, cell) in row.iter_mut().enumerate() {
            *cell = (0..4).map(|k| a[i][k] * b[k][j]).sum();
        }
    }
    out
}

/// Unreal's `FScaleRotationTranslationMatrix`: scale, then the rotator
/// (pitch about Y, yaw about Z, roll about X, in degrees), then translation.
pub fn transform_matrix(location: [f64; 3], rotator: [f64; 3], scale: [f64; 3]) -> Matrix {
    let (sp, cp) = rotator[0].to_radians().sin_cos();
    let (sy, cy) = rotator[1].to_radians().sin_cos();
    let (sr, cr) = rotator[2].to_radians().sin_cos();
    let [sx, sy_, sz] = scale;
    [
        [cp * cy * sx, cp * sy * sx, sp * sx, 0.0],
        [
            (sr * sp * cy - cr * sy) * sy_,
            (sr * sp * sy + cr * cy) * sy_,
            -sr * cp * sy_,
            0.0,
        ],
        [
            -(cr * sp * cy + sr * sy) * sz,
            (cy * sr - cr * sp * sy) * sz,
            cr * cp * sz,
            0.0,
        ],
        [location[0], location[1], location[2], 1.0],
    ]
}

/// The translation row of a matrix.
pub fn translation(m: &Matrix) -> [f64; 3] {
    [m[3][0], m[3][1], m[3][2]]
}

fn f64_at(d: &[u8], at: usize) -> Option<f64> {
    d.get(at..at + 8)
        .map(|b| f64::from_le_bytes(b.try_into().unwrap()))
}

fn u32_at(d: &[u8], at: usize) -> Option<u32> {
    d.get(at..at + 4)
        .map(|b| u32::from_le_bytes(b.try_into().unwrap()))
}

/// The per-instance matrices bulk-serialized in the native bytes that trail
/// an instanced static mesh component's properties. Found by its header —
/// element size 128, then the count — within the leading bytes, and accepted
/// only when every matrix is affine (a `[0, 0, 0, 1]` last column).
pub fn instance_matrices(tail: &[u8]) -> Result<Vec<Matrix>, String> {
    const STRIDE: usize = 128;
    let window = tail.len().min(256);
    let mut at = 0;
    while at + 8 <= window {
        if u32_at(tail, at) == Some(STRIDE as u32) {
            let count = u32_at(tail, at + 4).unwrap_or(0) as usize;
            let start = at + 8;
            if count <= 4_000_000 && start + count * STRIDE <= tail.len() {
                let mut out = Vec::with_capacity(count);
                let mut affine = true;
                'matrices: for i in 0..count {
                    let base = start + i * STRIDE;
                    let mut m = [[0.0; 4]; 4];
                    for (r, row) in m.iter_mut().enumerate() {
                        for (c, cell) in row.iter_mut().enumerate() {
                            *cell = f64_at(tail, base + (r * 4 + c) * 8).unwrap_or(f64::NAN);
                        }
                    }
                    let last_column_ok =
                        m[0][3] == 0.0 && m[1][3] == 0.0 && m[2][3] == 0.0 && m[3][3] == 1.0;
                    let finite = m.iter().flatten().all(|v| v.is_finite());
                    if !last_column_ok || !finite {
                        affine = false;
                        break 'matrices;
                    }
                    out.push(m);
                }
                if affine {
                    return Ok(out);
                }
            }
        }
        at += 4;
    }
    Err("no instance array with affine matrices in the component's native bytes".into())
}

/// The bounds a component cached at cook time (`FBoxSphereBounds`, doubles),
/// which the instanced components carry right after their properties.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CachedBounds {
    pub origin: [f64; 3],
    pub extent: [f64; 3],
    pub radius: f64,
}

/// The cached bounds at the head of a component's native bytes, when the
/// flag before them says they were written.
pub fn cached_bounds(tail: &[u8]) -> Option<CachedBounds> {
    if u32_at(tail, 0)? != 0 || u32_at(tail, 4)? != 1 || tail.len() < 64 {
        return None;
    }
    let d = |i: usize| f64_at(tail, 8 + i * 8);
    let b = CachedBounds {
        origin: [d(0)?, d(1)?, d(2)?],
        extent: [d(3)?, d(4)?, d(5)?],
        radius: d(6)?,
    };
    let sane = b
        .origin
        .iter()
        .chain(b.extent.iter())
        .all(|v| v.is_finite() && v.abs() < 1.0e9)
        && b.radius.is_finite()
        && b.radius >= 0.0
        && b.extent.iter().all(|v| *v >= 0.0);
    sane.then_some(b)
}

/// What a placed mesh refers to.
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum MeshRef {
    /// A `StaticMesh` asset in another package, by `/Game/...` name.
    Package(String),
    /// A `StaticMesh` export inside the cell itself, by export index.
    Embedded(usize),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Kind {
    /// A plain `StaticMeshComponent`.
    Static,
    /// An instanced component: one placement per instance.
    Instanced,
    /// A hierarchical-LOD proxy of far detail, off by default.
    Hlod,
}

/// One component in the cell that carries a transform.
#[derive(Debug, Clone)]
pub struct Component {
    pub export: usize,
    pub name: String,
    pub class: String,
    pub actor: String,
    pub kind: Option<Kind>,
    pub mesh: Option<MeshRef>,
    /// Composed up the attach chain.
    pub world: Matrix,
    pub cached_bounds: Option<CachedBounds>,
    /// Instance count for an instanced component, 1 for a static one.
    pub instances: usize,
}

/// One mesh placed in the world.
#[derive(Debug, Clone)]
pub struct Placement {
    pub mesh: MeshRef,
    pub world: Matrix,
    /// Index into [`Cell::components`].
    pub component: usize,
    pub kind: Kind,
}

#[derive(Debug, Default)]
pub struct Cell {
    pub package: String,
    /// Exports whose outer is the level itself.
    pub actors: usize,
    pub components: Vec<Component>,
    pub placements: Vec<Placement>,
    /// Why parts of the cell were not placed, by reason.
    pub skips: BTreeMap<String, usize>,
}

impl Cell {
    pub fn unique_meshes(&self) -> usize {
        let mut seen: Vec<&MeshRef> = self.placements.iter().map(|p| &p.mesh).collect();
        seen.sort();
        seen.dedup();
        seen.len()
    }
}

/// Reads cells, with the Blueprint packages they lean on loaded on demand.
pub struct CellReader<'a> {
    pub usmap: &'a Usmap,
    pub scripts: &'a ScriptObjects,
    /// Package bytes by `/Game/...` name, for Blueprint templates.
    pub load_package: &'a dyn Fn(&str) -> Option<Vec<u8>>,
    /// Place the hierarchical-LOD proxies too.
    pub include_hlod: bool,
    packages: RefCell<HashMap<String, Option<Rc<Loaded>>>>,
}

struct Loaded {
    package: Package,
    data: Vec<u8>,
}

const KEEP: &[&str] = &[
    "RelativeLocation",
    "RelativeRotation",
    "RelativeScale3D",
    "bAbsoluteLocation",
    "bAbsoluteRotation",
    "bAbsoluteScale",
    "AttachParent",
    "StaticMesh",
    "bHiddenInGame",
    "bVisible",
];

fn vec3(v: Option<&Value>, default: f64) -> [f64; 3] {
    match v {
        Some(Value::Array(items)) if items.len() >= 3 => {
            let f = |i: usize| match items[i] {
                Value::Float(x) => x,
                Value::Int(x) => x as f64,
                _ => default,
            };
            [f(0), f(1), f(2)]
        }
        Some(Value::Zeroed) => [0.0; 3],
        _ => [default; 3],
    }
}

fn flag(v: Option<&Value>) -> bool {
    matches!(v, Some(Value::Bool(true)))
}

impl<'a> CellReader<'a> {
    pub fn new(
        usmap: &'a Usmap,
        scripts: &'a ScriptObjects,
        load_package: &'a dyn Fn(&str) -> Option<Vec<u8>>,
    ) -> CellReader<'a> {
        CellReader {
            usmap,
            scripts,
            load_package,
            include_hlod: false,
            packages: RefCell::new(HashMap::new()),
        }
    }

    /// Does `class` derive from `base` in the usmap?
    fn derives(&self, class: &str, base: &str) -> bool {
        let mut current = Some(class.to_string());
        let mut depth = 0;
        while let Some(name) = current {
            if name == base {
                return true;
            }
            depth += 1;
            if depth > 32 {
                break;
            }
            current = self
                .usmap
                .structs
                .get(&name)
                .and_then(|s| s.super_name.clone());
        }
        false
    }

    /// The class of an export as a leaf name: the script class, or the
    /// Blueprint package's leaf prefixed `bp:` when it is not a script class.
    fn class_leaf(&self, package: &Package, export: usize) -> String {
        let e = &package.exports[export];
        match e.class.classify() {
            ObjectRef::Script(_) => self.scripts.leaf(e.class).unwrap_or("?").to_string(),
            ObjectRef::PackageImport(_) => match package.import_target(e.class) {
                Some(t) => format!("bp:{}", t.package.rsplit('/').next().unwrap_or(&t.package)),
                None => "bp:?".into(),
            },
            ObjectRef::Export(x) => format!("export:{}", package.exports[x].name),
            ObjectRef::Null => "null".into(),
        }
    }

    fn package(&self, name: &str) -> Option<Rc<Loaded>> {
        if let Some(hit) = self.packages.borrow().get(name) {
            return hit.clone();
        }
        let loaded = (self.load_package)(name).and_then(|data| {
            let package = Package::parse(&data).ok()?;
            Some(Rc::new(Loaded { package, data }))
        });
        self.packages
            .borrow_mut()
            .insert(name.to_string(), loaded.clone());
        loaded
    }

    /// The kept properties of an export, with its template's underneath so
    /// an unset property reads as inherited. Returns the class the walk used.
    fn merged_props(
        &self,
        package: &Package,
        data: &[u8],
        export: usize,
        depth: usize,
    ) -> Option<(HashMap<String, Value>, String)> {
        let class = self.class_leaf(package, export);
        let bytes = package.export_data(data, export).ok()?;
        let ctx = Ctx {
            usmap: self.usmap,
            names: &package.names,
        };
        let mut w = Walker::new(&ctx, bytes);
        let mut own = w.read_object(&class, Keep::Names(KEEP)).ok()?;
        // Object references are package-local; keep the ones that resolve
        // to another package as names so they survive the merge.
        if let Some(Value::Object(o)) = own.get("StaticMesh").cloned() {
            if let Some(t) = package.import_target_of(o) {
                own.insert("StaticMesh".into(), Value::Str(t.package));
            }
        }
        if depth < 4 {
            let template = package.exports[export].template;
            let inherited = match template.classify() {
                ObjectRef::PackageImport(_) => package.import_target(template).and_then(|t| {
                    let loaded = self.package(&t.package)?;
                    let index = loaded
                        .package
                        .exports
                        .iter()
                        .position(|e| e.public_hash == t.public_hash)?;
                    self.merged_props(&loaded.package, &loaded.data, index, depth + 1)
                }),
                ObjectRef::Export(x) if x != export => {
                    self.merged_props(package, data, x, depth + 1)
                }
                _ => None,
            };
            if let Some((base, _)) = inherited {
                for (k, v) in base {
                    // The template's attach parent is its own package's
                    // export; only transform and mesh inherit.
                    if k == "AttachParent" {
                        continue;
                    }
                    own.entry(k).or_insert(v);
                }
            }
        }
        Some((own, class))
    }

    /// Read one cell package.
    pub fn read(&self, data: &[u8]) -> Result<Cell, crate::zen::Error> {
        let package = Package::parse(data)?;
        let mut cell = Cell {
            package: package.name.clone(),
            ..Cell::default()
        };
        let level = package
            .exports
            .iter()
            .position(|e| self.scripts.leaf(e.class) == Some("Level"));
        let outer_export = |e: &crate::zen::Export| match e.outer.classify() {
            ObjectRef::Export(x) => Some(x),
            _ => None,
        };
        let export_count = package.exports.len();
        let skip = |cell: &mut Cell, reason: &str| {
            *cell.skips.entry(reason.to_string()).or_default() += 1;
        };

        // Pass 1: every scene component, its properties merged with its
        // template, its kind, and what it attaches to.
        struct Raw {
            export: usize,
            class: String,
            props: HashMap<String, Value>,
            parent: Option<usize>,
            kind: Option<Kind>,
            mesh: Option<MeshRef>,
            tail_start: usize,
        }
        let mut raws: Vec<Raw> = Vec::new();
        let mut by_export: HashMap<usize, usize> = HashMap::new();
        for ei in 0..export_count {
            let e = &package.exports[ei];
            if Some(ei) == level {
                continue;
            }
            if outer_export(e) == level {
                cell.actors += 1;
            }
            let class = self.class_leaf(&package, ei);
            if class.starts_with("bp:") || class.starts_with("export:") {
                // A Blueprint-defined component class has no usmap schema.
                if outer_export(e) != level && e.name.contains("Component") {
                    skip(&mut cell, "component of a Blueprint class (no schema)");
                }
                continue;
            }
            if !self.derives(&class, "SceneComponent") {
                continue;
            }
            if self.derives(&class, "LandscapeComponent")
                || self.derives(&class, "LandscapeHeightfieldCollisionComponent")
            {
                skip(&mut cell, "landscape component");
                continue;
            }
            if self.derives(&class, "ChildActorComponent") {
                skip(&mut cell, "child actor component");
            }
            let Some((props, _)) = self.merged_props(&package, data, ei, 0) else {
                skip(&mut cell, &format!("unreadable {class}"));
                continue;
            };
            let kind = if self.derives(&class, "InstancedStaticMeshComponent") {
                if class.contains("HLOD") {
                    Some(Kind::Hlod)
                } else {
                    Some(Kind::Instanced)
                }
            } else if self.derives(&class, "StaticMeshComponent") {
                Some(Kind::Static)
            } else {
                if self.derives(&class, "SkinnedMeshComponent") {
                    skip(&mut cell, "skeletal mesh component");
                }
                None
            };
            let mesh = match props.get("StaticMesh") {
                Some(Value::Str(name)) => Some(MeshRef::Package(name.clone())),
                Some(Value::Object(o)) if *o > 0 => Some(MeshRef::Embedded((*o - 1) as usize)),
                _ => None,
            };
            let parent = match props.get("AttachParent") {
                Some(Value::Object(o)) if *o > 0 && ((*o - 1) as usize) < export_count => {
                    Some((*o - 1) as usize)
                }
                _ => None,
            };
            // Where the native bytes begin: walk again with nothing kept.
            let ctx = Ctx {
                usmap: self.usmap,
                names: &package.names,
            };
            let bytes = package.export_data(data, ei)?;
            let mut w = Walker::new(&ctx, bytes);
            let tail_start = match w.read_object(&class, Keep::None) {
                Ok(_) => w.pos,
                Err(_) => bytes.len(),
            };
            by_export.insert(ei, raws.len());
            raws.push(Raw {
                export: ei,
                class,
                props,
                parent,
                kind,
                mesh,
                tail_start,
            });
        }

        // Pass 2: world transforms up the attach chain.
        let mut world: Vec<Option<Matrix>> = vec![None; raws.len()];
        fn resolve(
            i: usize,
            raws: &[Raw],
            by_export: &HashMap<usize, usize>,
            world: &mut Vec<Option<Matrix>>,
            depth: usize,
        ) -> Matrix {
            if let Some(m) = world[i] {
                return m;
            }
            let r = &raws[i];
            let location = vec3(r.props.get("RelativeLocation"), 0.0);
            let rotation = vec3(r.props.get("RelativeRotation"), 0.0);
            let scale = vec3(r.props.get("RelativeScale3D"), 1.0);
            let local = transform_matrix(location, rotation, scale);
            let absolute = flag(r.props.get("bAbsoluteLocation"))
                || flag(r.props.get("bAbsoluteRotation"))
                || flag(r.props.get("bAbsoluteScale"));
            let m = match r.parent.and_then(|p| by_export.get(&p).copied()) {
                Some(p) if !absolute && depth < 64 && p != i => {
                    let parent = resolve(p, raws, by_export, world, depth + 1);
                    multiply(&local, &parent)
                }
                _ => local,
            };
            world[i] = Some(m);
            m
        }
        for i in 0..raws.len() {
            resolve(i, &raws, &by_export, &mut world, 0);
        }

        // Pass 3: placements.
        for (i, r) in raws.iter().enumerate() {
            let e = &package.exports[r.export];
            let actor = outer_export(e)
                .map(|x| package.exports[x].name.clone())
                .unwrap_or_default();
            let bytes = package.export_data(data, r.export)?;
            let tail = &bytes[r.tail_start.min(bytes.len())..];
            let world_m = world[i].unwrap_or(IDENTITY);
            let mut component = Component {
                export: r.export,
                name: e.name.clone(),
                class: r.class.clone(),
                actor,
                kind: r.kind,
                mesh: r.mesh.clone(),
                world: world_m,
                cached_bounds: cached_bounds(tail),
                instances: 0,
            };
            let index = cell.components.len();
            let Some(kind) = r.kind else {
                cell.components.push(component);
                continue;
            };
            let hidden = flag(r.props.get("bHiddenInGame"))
                || matches!(r.props.get("bVisible"), Some(Value::Bool(false)));
            if hidden {
                skip(&mut cell, "hidden component");
                cell.components.push(component);
                continue;
            }
            if kind == Kind::Hlod && !self.include_hlod {
                skip(&mut cell, "hierarchical-LOD proxy (use --hlod)");
                cell.components.push(component);
                continue;
            }
            let Some(mesh) = r.mesh.clone() else {
                skip(&mut cell, "mesh component without a mesh reference");
                cell.components.push(component);
                continue;
            };
            match kind {
                Kind::Static => {
                    component.instances = 1;
                    cell.placements.push(Placement {
                        mesh,
                        world: world_m,
                        component: index,
                        kind,
                    });
                }
                Kind::Instanced | Kind::Hlod => match instance_matrices(tail) {
                    Ok(matrices) => {
                        component.instances = matrices.len();
                        for m in matrices {
                            cell.placements.push(Placement {
                                mesh: mesh.clone(),
                                world: multiply(&m, &world_m),
                                component: index,
                                kind,
                            });
                        }
                    }
                    Err(_) => skip(&mut cell, "instance data unreadable"),
                },
            }
            cell.components.push(component);
        }

        // Blueprint actors whose template components never made it into
        // the cell: their meshes sit at their defaults and are not placed.
        for ei in 0..export_count {
            let e = &package.exports[ei];
            if outer_export(e) != level {
                continue;
            }
            let Some(target) = (match e.class.classify() {
                ObjectRef::PackageImport(_) => package.import_target(e.class),
                _ => None,
            }) else {
                continue;
            };
            let Some(bp) = self.package(&target.package) else {
                let leaf = target.package.rsplit('/').next().unwrap_or(&target.package);
                skip(&mut cell, &format!("Blueprint package not found ({leaf})"));
                continue;
            };
            let instanced: Vec<&str> = package
                .exports
                .iter()
                .filter(|c| outer_export(c) == Some(ei))
                .map(|c| c.name.as_str())
                .collect();
            for t in &bp.package.exports {
                let Some(base) = t.name.strip_suffix("_GEN_VARIABLE") else {
                    continue;
                };
                let class = match t.class.classify() {
                    ObjectRef::Script(_) => self.scripts.leaf(t.class).unwrap_or(""),
                    _ => "",
                };
                if !self.derives(class, "StaticMeshComponent") {
                    continue;
                }
                if !instanced.contains(&base) {
                    skip(
                        &mut cell,
                        "Blueprint template component not instanced in the cell",
                    );
                }
            }
        }
        Ok(cell)
    }
}

/// The level packages of one mission among `names` (`/Game/...` package
/// names, any case): the persistent level first, then its generated cells
/// in id order. A mission is the folder pair `<m>/<m>/_Generated_/` under
/// `/Game/Levels/`, e.g. `a30`.
pub fn mission_cells<'n>(names: impl Iterator<Item = &'n str>, mission: &str) -> Vec<String> {
    let mission = mission.to_ascii_lowercase();
    let marker = format!("/{mission}/{mission}/_generated_/");
    let persistent = format!("/{mission}/{mission}");
    let mut out: Vec<String> = names
        .filter(|n| {
            let lower = n.to_ascii_lowercase();
            lower.starts_with("/game/levels/")
                && (lower.contains(&marker) || lower.ends_with(&persistent))
        })
        .map(|n| n.to_string())
        .collect();
    out.sort_by_key(|n| n.to_ascii_lowercase());
    out
}

#[derive(Debug, Clone, Copy, Default)]
pub struct ExportOptions {
    /// The full-detail Nanite geometry for each mesh instead of the classic
    /// fallback LOD.
    pub nanite: bool,
    /// Place the hierarchical-LOD proxies as well as the real meshes.
    pub include_hlod: bool,
}

/// What one cell came to.
#[derive(Debug, Default)]
pub struct CellExport {
    /// The cell id: the package's leaf name.
    pub id: String,
    pub package: String,
    pub actors: usize,
    pub placements: usize,
    pub instanced: usize,
    pub meshes: usize,
    pub skips: BTreeMap<String, usize>,
    /// Meshes that would not read, with the placements dropped for each.
    pub missing: BTreeMap<String, usize>,
    /// The `.glb`, when asked for and the cell placed anything readable.
    pub glb: Option<Vec<u8>>,
}

/// The geometry of one mesh as the exporter places it.
struct MeshGeometry {
    materials: Vec<(String, i32)>,
    lod: crate::mesh::Lod,
}

/// Exports a mission's cells, caching each distinct mesh's geometry across
/// cells.
pub struct Exporter<'a> {
    reader: CellReader<'a>,
    /// A package's `.ubulk` by `/Game/...` name.
    load_bulk: &'a dyn Fn(&str) -> Option<Vec<u8>>,
    options: ExportOptions,
    geometry: HashMap<String, Option<Rc<MeshGeometry>>>,
}

impl<'a> Exporter<'a> {
    pub fn new(
        usmap: &'a Usmap,
        scripts: &'a ScriptObjects,
        load_package: &'a dyn Fn(&str) -> Option<Vec<u8>>,
        load_bulk: &'a dyn Fn(&str) -> Option<Vec<u8>>,
        options: ExportOptions,
    ) -> Exporter<'a> {
        let mut reader = CellReader::new(usmap, scripts, load_package);
        reader.include_hlod = options.include_hlod;
        Exporter {
            reader,
            load_bulk,
            options,
            geometry: HashMap::new(),
        }
    }

    fn mesh_geometry(
        &self,
        name: &str,
        package_data: &[u8],
        bulk: Option<&[u8]>,
        export: Option<usize>,
    ) -> Result<MeshGeometry, String> {
        let package = Package::parse(package_data).map_err(|e| e.to_string())?;
        let export = match export {
            Some(e) => e,
            None => package
                .exports
                .iter()
                .position(|e| self.reader.scripts.leaf(e.class) == Some("StaticMesh"))
                .ok_or_else(|| format!("{name}: no StaticMesh export"))?,
        };
        let bytes = package
            .export_data(package_data, export)
            .map_err(|e| e.to_string())?;
        let ctx = Ctx {
            usmap: self.reader.usmap,
            names: &package.names,
        };
        let bulk_map = crate::mesh::bulk_map_of(package_data);
        let sm = crate::mesh::parse_static_mesh_with_bulk_map(&ctx, bytes, bulk, &bulk_map)
            .map_err(|e| format!("{name}: {e}"))?;
        let lod = if self.options.nanite {
            sm.preferred().map(|(l, _)| l.clone())
        } else {
            sm.lods
                .iter()
                .find(|l| !l.positions.is_empty() && !l.indices.is_empty())
                .cloned()
                .or_else(|| sm.nanite.clone())
        }
        .ok_or_else(|| format!("{name}: no LOD with geometry"))?;
        Ok(MeshGeometry {
            materials: sm.materials,
            lod,
        })
    }

    /// Read one cell by package name and, when `write_glb`, build its
    /// `.glb`. A mesh that will not read drops its placements and is named
    /// in `missing`; the first such failure per mesh is returned in `notes`.
    pub fn export_cell(&mut self, name: &str, write_glb: bool) -> Result<CellExport, String> {
        let data =
            (self.reader.load_package)(name).ok_or_else(|| format!("{name}: package not found"))?;
        let cell = self
            .reader
            .read(&data)
            .map_err(|e| format!("{name}: {e}"))?;
        let id = name.rsplit('/').next().unwrap_or(name).to_string();
        let mut out = CellExport {
            id: id.clone(),
            package: cell.package.clone(),
            actors: cell.actors,
            placements: cell.placements.len(),
            instanced: cell
                .placements
                .iter()
                .filter(|p| p.kind != Kind::Static)
                .count(),
            meshes: cell.unique_meshes(),
            skips: cell.skips.clone(),
            ..CellExport::default()
        };
        if !write_glb || cell.placements.is_empty() {
            return Ok(out);
        }

        // Geometry per distinct mesh, then a node per placement.
        let mut cell_bulk: Option<Option<Vec<u8>>> = None;
        let mut slots: Vec<(MeshRef, Rc<MeshGeometry>)> = Vec::new();
        let mut slot_of: HashMap<MeshRef, Option<usize>> = HashMap::new();
        for p in &cell.placements {
            if let Some(slot) = slot_of.get(&p.mesh) {
                if slot.is_none() {
                    let label = match &p.mesh {
                        MeshRef::Package(n) => n.clone(),
                        MeshRef::Embedded(e) => format!("embedded export {e}"),
                    };
                    *out.missing.entry(label).or_default() += 1;
                }
                continue;
            }
            let geometry = match &p.mesh {
                MeshRef::Package(mesh_name) => {
                    if !self.geometry.contains_key(mesh_name) {
                        let loaded = (self.reader.load_package)(mesh_name).and_then(|mdata| {
                            let mbulk = (self.load_bulk)(mesh_name);
                            match self.mesh_geometry(mesh_name, &mdata, mbulk.as_deref(), None) {
                                Ok(g) => Some(Rc::new(g)),
                                Err(e) => {
                                    eprintln!("  {e}");
                                    None
                                }
                            }
                        });
                        self.geometry.insert(mesh_name.clone(), loaded);
                    }
                    self.geometry[mesh_name].clone()
                }
                MeshRef::Embedded(export) => {
                    let bulk = cell_bulk.get_or_insert_with(|| (self.load_bulk)(name));
                    match self.mesh_geometry(
                        &format!("{id}:{export}"),
                        &data,
                        bulk.as_deref(),
                        Some(*export),
                    ) {
                        Ok(g) => Some(Rc::new(g)),
                        Err(e) => {
                            eprintln!("  {e}");
                            None
                        }
                    }
                }
            };
            match geometry {
                Some(g) => {
                    slot_of.insert(p.mesh.clone(), Some(slots.len()));
                    slots.push((p.mesh.clone(), g));
                }
                None => {
                    let label = match &p.mesh {
                        MeshRef::Package(n) => n.clone(),
                        MeshRef::Embedded(e) => format!("embedded export {e}"),
                    };
                    *out.missing.entry(label).or_default() += 1;
                    slot_of.insert(p.mesh.clone(), None);
                }
            }
        }
        let meshes: Vec<crate::gltf::SceneMesh<'_>> = slots
            .iter()
            .map(|(r, g)| crate::gltf::SceneMesh {
                name: match r {
                    MeshRef::Package(n) => n.rsplit('/').next().unwrap_or(n).to_string(),
                    MeshRef::Embedded(e) => format!("embedded_{e}"),
                },
                materials: &g.materials,
                lod: &g.lod,
            })
            .collect();
        let mut nodes: Vec<crate::gltf::SceneNode> = Vec::new();
        for p in &cell.placements {
            let Some(Some(slot)) = slot_of.get(&p.mesh) else {
                continue;
            };
            let c = &cell.components[p.component];
            nodes.push(crate::gltf::SceneNode {
                name: format!("{}/{}", c.actor, c.name),
                mesh: *slot,
                matrix: gltf_node_matrix(&p.world),
            });
        }
        if !nodes.is_empty() {
            out.glb = Some(
                crate::gltf::write_scene_glb(&id, &meshes, &nodes)
                    .map_err(|e| format!("{id}: {e}"))?,
            );
        }
        Ok(out)
    }
}

/// An Unreal world matrix as a glTF node matrix, column-major: the axis swap
/// `(x, y, z) → (x, z, y)` on both sides and centimetres to metres on the
/// translation, matching how the mesh vertices are converted.
pub fn gltf_node_matrix(m: &Matrix) -> [f32; 16] {
    let p = |i: usize| match i {
        1 => 2,
        2 => 1,
        i => i,
    };
    let mut out = [0.0f32; 16];
    for r in 0..3 {
        for c in 0..3 {
            // Column-vector linear part is the transpose of the row-vector
            // one, then the permutation on both sides.
            out[c * 4 + r] = m[p(c)][p(r)] as f32;
        }
    }
    let t = translation(m);
    out[12] = (t[0] * 0.01) as f32;
    out[13] = (t[2] * 0.01) as f32;
    out[14] = (t[1] * 0.01) as f32;
    out[15] = 1.0;
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Against the installed game: every A30 cell reads; the instanced
    /// components' placements land inside the bounds the cook cached for
    /// them, which pins the matrix conventions (row vectors, child then
    /// parent, instance then component); every mesh a placement names is a
    /// package in the containers.
    #[test]
    fn shipped_cells_place_inside_their_cached_bounds() {
        let Ok(paks) = std::env::var("HCE_PAKS") else {
            return;
        };
        let containers = ue_iostore::load_all(&paks).unwrap();
        let global = containers
            .iter()
            .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
            .unwrap();
        let script_chunk = global
            .chunks
            .iter()
            .find(|c| c.type_name() == "ScriptObjects")
            .unwrap();
        let scripts =
            ScriptObjects::parse(&ue_iostore::read_chunk(global, script_chunk, None, &[]).unwrap())
                .unwrap();
        static USMAP: &[u8] = include_bytes!("../../../defs/ue/Meteorite-2607-CU3.usmap");
        let usmap = Usmap::parse(USMAP).unwrap();

        // Package name -> (container, chunk).
        let mut index: HashMap<String, (usize, usize)> = HashMap::new();
        for (ci, c) in containers.iter().enumerate() {
            for (rel, chunk) in &c.files {
                let full = c.full_path(rel);
                if full.ends_with(".ubulk") || full.ends_with(".uptnl") {
                    continue;
                }
                if let Some(name) = package_name_of(&full) {
                    index.insert(name.to_ascii_lowercase(), (ci, *chunk));
                }
            }
        }
        let load = |name: &str| -> Option<Vec<u8>> {
            let (ci, chunk) = index.get(&name.to_ascii_lowercase())?;
            ue_iostore::read_chunk(&containers[*ci], &containers[*ci].chunks[*chunk], None, &[])
                .ok()
        };
        let reader = CellReader::new(&usmap, &scripts, &load);

        let limit: usize = std::env::var("LEVEL_TEST_LIMIT")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(150);
        let mut cells: Vec<&String> = index
            .keys()
            .filter(|k| k.contains("/a30/a30/_generated_/"))
            .collect();
        cells.sort();
        let mut read = 0usize;
        let mut placements = 0usize;
        let mut checked = 0usize;
        let mut outside = 0usize;
        let mut missing_meshes = 0usize;
        let mut missing_names: std::collections::BTreeSet<String> = Default::default();
        let mut worst = String::new();
        for key in cells.iter().take(limit) {
            let data = load(key).unwrap();
            let cell = reader.read(&data).unwrap();
            read += 1;
            placements += cell.placements.len();
            for p in &cell.placements {
                if let MeshRef::Package(name) = &p.mesh {
                    if !index.contains_key(&name.to_ascii_lowercase()) {
                        missing_meshes += 1;
                        missing_names.insert(name.clone());
                    }
                }
            }
            for (ci, c) in cell.components.iter().enumerate() {
                let (Some(b), Some(Kind::Instanced)) = (c.cached_bounds, c.kind) else {
                    continue;
                };
                for p in cell.placements.iter().filter(|p| p.component == ci) {
                    checked += 1;
                    let t = translation(&p.world);
                    let inside =
                        (0..3).all(|k| (t[k] - b.origin[k]).abs() <= b.extent[k] * 1.05 + 100.0);
                    if !inside {
                        outside += 1;
                        if worst.is_empty() {
                            worst = format!(
                                "{}/{} in {}: instance at {t:?}, bounds {:?} ± {:?}",
                                c.actor, c.name, cell.package, b.origin, b.extent
                            );
                        }
                    }
                }
            }
        }
        eprintln!(
            "{read} cells, {placements} placements, {checked} instance(s) checked against cached bounds, {outside} outside, {missing_meshes} mesh refs unresolved"
        );
        if !worst.is_empty() {
            eprintln!("first outside: {worst}");
        }
        for name in &missing_names {
            eprintln!("unresolved mesh: {name}");
        }
        assert!(
            read > 0 && placements > 1000,
            "too little read: {read} cells, {placements} placements"
        );
        assert!(
            checked > 100,
            "too few instances carried cached bounds: {checked}"
        );
        assert!(
            outside * 100 <= checked,
            "{outside} of {checked} instances fall outside their component's cached bounds"
        );
        assert_eq!(missing_meshes, 0);
    }

    fn close(a: f64, b: f64) -> bool {
        (a - b).abs() < 1e-9
    }

    #[test]
    fn package_names_follow_the_mount_points() {
        assert_eq!(
            package_name_of("../../../Meteorite/Content/Env/Bio/SM_Rock.uasset").as_deref(),
            Some("/Game/Env/Bio/SM_Rock")
        );
        assert_eq!(
            package_name_of("../../../Engine/Content/BasicShapes/Plane.uasset").as_deref(),
            Some("/Engine/BasicShapes/Plane")
        );
        assert_eq!(
            package_name_of("../../../Meteorite/Plugins/FluidFlux/Content/Meshes/SM_Flux.ubulk")
                .as_deref(),
            Some("/FluidFlux/Meshes/SM_Flux")
        );
        assert_eq!(
            package_name_of("../../../Meteorite/Content/Paks/x.pak"),
            None
        );
    }

    #[test]
    fn yaw_turns_x_into_y() {
        let m = transform_matrix([10.0, 20.0, 30.0], [0.0, 90.0, 0.0], [1.0, 1.0, 1.0]);
        // Row vector [1,0,0] × M.
        assert!(close(m[0][0], 0.0) && close(m[0][1], 1.0) && close(m[0][2], 0.0));
        assert_eq!(translation(&m), [10.0, 20.0, 30.0]);
        let s = transform_matrix([0.0; 3], [0.0; 3], [2.0, 3.0, 4.0]);
        assert_eq!((s[0][0], s[1][1], s[2][2]), (2.0, 3.0, 4.0));
    }

    #[test]
    fn multiply_composes_child_then_parent() {
        let parent = transform_matrix([100.0, 0.0, 0.0], [0.0, 90.0, 0.0], [1.0; 3]);
        let child = transform_matrix([10.0, 0.0, 0.0], [0.0; 3], [1.0; 3]);
        let world = multiply(&child, &parent);
        // The child sits 10 along the parent's local X, which is world Y.
        let t = translation(&world);
        assert!(close(t[0], 100.0) && close(t[1], 10.0) && close(t[2], 0.0));
    }

    #[test]
    fn instance_matrices_find_the_bulk_header() {
        let mut tail = vec![0u8; 20];
        tail.extend_from_slice(&128u32.to_le_bytes());
        tail.extend_from_slice(&2u32.to_le_bytes());
        for i in 0..2 {
            let m = transform_matrix([i as f64, 0.0, 0.0], [0.0; 3], [1.0; 3]);
            for row in m {
                for v in row {
                    tail.extend_from_slice(&v.to_le_bytes());
                }
            }
        }
        tail.extend_from_slice(&[4, 0, 0, 0, 0, 0, 0, 0]);
        let found = instance_matrices(&tail).unwrap();
        assert_eq!(found.len(), 2);
        assert_eq!(translation(&found[1]), [1.0, 0.0, 0.0]);
        // A non-affine matrix is rejected.
        tail[28 + 3 * 8] = 1;
        assert!(instance_matrices(&tail).is_err());
        assert!(instance_matrices(&[0u8; 8]).is_err());
    }

    #[test]
    fn cached_bounds_need_the_flag() {
        let mut tail = vec![0, 0, 0, 0, 1, 0, 0, 0];
        for v in [1.0f64, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0] {
            tail.extend_from_slice(&v.to_le_bytes());
        }
        let b = cached_bounds(&tail).unwrap();
        assert_eq!(b.origin, [1.0, 2.0, 3.0]);
        assert_eq!(b.radius, 7.0);
        tail[4] = 0;
        assert!(cached_bounds(&tail).is_none());
    }

    #[test]
    fn gltf_matrix_swaps_axes_and_scales_translation() {
        let m = transform_matrix([100.0, 200.0, 300.0], [0.0, 90.0, 0.0], [1.0; 3]);
        let g = gltf_node_matrix(&m);
        assert_eq!(&g[12..15], &[1.0, 3.0, 2.0]);
        // Unreal yaw about Z is a rotation about glTF's Y: the column for
        // glTF X (Unreal X) points along glTF Z (Unreal Y).
        assert!((g[0]).abs() < 1e-6 && (g[2] - 1.0).abs() < 1e-6);
    }
}
