//! Material instance reading: enough to chase a mesh section to the textures
//! it samples.
//!
//! A `MaterialInstanceConstant` carries `TextureParameterValues` — parameter
//! name plus an object reference into the import map — and a `Parent` chain
//! for values it inherits. Resolving the object reference through the package
//! import gives the texture's package name, which the tag editor's catalog
//! already knows how to decode.

use crate::unversioned::{Ctx, Error as PropError, Keep, Value, Walker};
use crate::zen::{ObjectRef, Package};

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error(transparent)]
    Props(#[from] PropError),
}

#[derive(Debug, Clone)]
pub struct TextureParameter {
    pub name: String,
    /// Package name of the referenced texture, e.g.
    /// `/Game/Characters/Elite/Minor/Textures/T_Elite_Body_D`.
    pub package: String,
}

#[derive(Debug, Clone)]
pub struct ColorParameter {
    pub name: String,
    /// Linear RGBA.
    pub value: [f64; 4],
}

#[derive(Debug, Default)]
pub struct MaterialInfo {
    /// Package name of the parent material or instance, when imported.
    pub parent: Option<String>,
    pub textures: Vec<TextureParameter>,
    pub colors: Vec<ColorParameter>,
}

/// The imported package a `FPackageIndex` object reference points into, if it
/// is an import backed by a package import.
pub fn import_package_name(package: &Package, object: i32) -> Option<String> {
    if object >= 0 {
        return None;
    }
    let import = package.imports.get((-object - 1) as usize)?;
    match import.classify() {
        ObjectRef::PackageImport(v) => {
            // FPackageImportReference: imported-package index in the upper
            // half of the 62-bit payload.
            let index = ((v >> 32) & 0x3FFF_FFFF) as usize;
            package.imported_package_names.get(index).cloned()
        }
        _ => None,
    }
}

/// Read the texture bindings of a MaterialInstanceConstant export.
pub fn parse_material_instance(
    ctx: &Ctx<'_>,
    package: &Package,
    data: &[u8],
) -> Result<MaterialInfo, Error> {
    let mut w = Walker::new(ctx, data);
    let props = w.read_object(
        "MaterialInstanceConstant",
        Keep::Names(&["Parent", "TextureParameterValues", "VectorParameterValues"]),
    )?;

    let mut out = MaterialInfo::default();
    if let Some(v) = props.get("Parent").and_then(|v| v.as_object()) {
        out.parent = import_package_name(package, v);
    }
    if let Some(Value::Array(list)) = props.get("TextureParameterValues") {
        for entry in list {
            let Value::Struct(fields) = entry else {
                continue;
            };
            let name = fields
                .get("ParameterInfo")
                .and_then(|v| match v {
                    Value::Struct(info) => info.get("Name").and_then(|n| n.as_str()),
                    _ => None,
                })
                .unwrap_or("")
                .to_string();
            let Some(object) = fields.get("ParameterValue").and_then(|v| v.as_object()) else {
                continue;
            };
            let Some(package_name) = import_package_name(package, object) else {
                continue;
            };
            out.textures.push(TextureParameter {
                name,
                package: package_name,
            });
        }
    }
    if let Some(Value::Array(list)) = props.get("VectorParameterValues") {
        for entry in list {
            let Value::Struct(fields) = entry else {
                continue;
            };
            let name = fields
                .get("ParameterInfo")
                .and_then(|v| match v {
                    Value::Struct(info) => info.get("Name").and_then(|n| n.as_str()),
                    _ => None,
                })
                .unwrap_or("")
                .to_string();
            let Some(Value::Array(rgba)) = fields.get("ParameterValue") else {
                continue;
            };
            if rgba.len() < 4 {
                continue;
            }
            let f = |i: usize| match rgba[i] {
                Value::Float(x) => x,
                _ => 0.0,
            };
            out.colors.push(ColorParameter {
                name,
                value: [f(0), f(1), f(2), f(3)],
            });
        }
    }
    Ok(out)
}

/// Pick the base-colour texture from a parameter list: prefer parameter names
/// that say so, fall back to texture naming conventions. The material
/// library's `CO`/`COH` maps are channel-packed masks, not colour — layered
/// materials get their colour from vector parameters instead (see
/// [`base_color_tint`]).
pub fn base_color<'a>(textures: &'a [TextureParameter]) -> Option<&'a TextureParameter> {
    let by_param = textures.iter().find(|t| {
        let n = t.name.to_ascii_lowercase();
        n.contains("basecolor")
            || n.contains("base color")
            || n.contains("albedo")
            || n.contains("diffuse")
            || n == "color"
    });
    if by_param.is_some() {
        return by_param;
    }
    textures.iter().find(|t| {
        let leaf = t.package.rsplit('/').next().unwrap_or("").to_ascii_lowercase();
        leaf.ends_with("_d") || leaf.ends_with("_bc") || leaf.ends_with("_albedo") || leaf.ends_with("_diff")
    })
}

/// Pick a flat base colour from the vector parameters — what the material
/// library's layered materials use instead of an albedo texture.
///
/// Colour parameters repeat per material layer (`BaseColor` at indices 2, 3,
/// 4…), and the under-layers are near-black primer while the paint sits on
/// top (`Color Top` on the warthog is its olive). The brightest colour-named
/// parameter is the paint, empirically.
pub fn base_color_tint(colors: &[ColorParameter]) -> Option<[f64; 4]> {
    // The paint gradient, when the material has one, is the colour to show.
    for wanted in ["color top", "color mid", "color bottom"] {
        if let Some(c) = colors
            .iter()
            .find(|c| c.name.eq_ignore_ascii_case(wanted))
        {
            return Some(c.value);
        }
    }
    colors
        .iter()
        .filter(|c| {
            let n = c.name.to_ascii_lowercase();
            n.contains("color")
                && !n.contains("mask")
                && !n.contains("channel")
                && !n.contains("direction")
                && !n.contains("override")
                && !n.contains("emiss")
                // A tint is a multiplier over the layers, not the paint.
                && !n.contains("tint")
        })
        .max_by(|a, b| {
            let lum = |v: &[f64; 4]| 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
            lum(&a.value).total_cmp(&lum(&b.value))
        })
        .map(|c| c.value)
}
