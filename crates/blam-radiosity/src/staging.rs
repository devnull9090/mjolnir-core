//! What the halo2ue staging says about the light: each shader's radiosity
//! header and base map, the sky's lights and ambient, and the BSP's
//! clusters (`bsp/clusters_0.json`, when the export has it).

use crate::math::V3;
use serde::Deserialize;
use std::collections::HashMap;
use std::path::{Path, PathBuf};

/// A CE shader's radiosity properties (the 40-byte header every shader
/// class starts with) and its base map.
#[derive(Clone, Debug)]
pub struct Shader {
    pub name: String,
    /// `senv`, `soso`, `schi`, ...
    pub class: String,
    /// The header's shader type: 3 environment, 4 model, 9 meter.
    pub shader_type: u16,
    pub simple_parameterization: bool,
    pub ignore_normals: bool,
    pub transparent_lit: bool,
    /// The quality row.
    pub detail_level: usize,
    /// `color_of_emitted_light x power`: the surface's unshot energy at the start.
    pub emission: V3,
    pub tint: V3,
    /// The base map, decoded, when the shader has one (`senv` only in
    /// tool.exe; the others reflect nothing).
    pub base_map: Option<Image>,
}

impl Shader {
    /// Whether tool.exe lights surfaces of this shader at all.
    pub fn lit(&self) -> bool {
        matches!(self.shader_type, 3 | 4 | 9) || self.emission.iter().any(|c| *c != 0.0)
    }
}

/// An RGB image in linear-ish 0..1 (the PNG's bytes / 255, as tool.exe
/// reads the bitmap's own bytes).
#[derive(Clone, Debug)]
pub struct Image {
    pub width: usize,
    pub height: usize,
    pub rgb: Vec<[f32; 3]>,
}

impl Image {
    pub fn load(path: &Path) -> Result<Image, String> {
        let decoder = png::Decoder::new(std::fs::File::open(path).map_err(|e| format!("{}: {e}", path.display()))?);
        let mut reader = decoder.read_info().map_err(|e| format!("{}: {e}", path.display()))?;
        let mut buf = vec![0; reader.output_buffer_size()];
        let info = reader.next_frame(&mut buf).map_err(|e| format!("{}: {e}", path.display()))?;
        let (w, h) = (info.width as usize, info.height as usize);
        let ch = match info.color_type {
            png::ColorType::Rgb => 3,
            png::ColorType::Rgba => 4,
            png::ColorType::Grayscale => 1,
            png::ColorType::GrayscaleAlpha => 2,
            other => return Err(format!("{}: colour type {other:?}", path.display())),
        };
        if info.bit_depth != png::BitDepth::Eight {
            return Err(format!("{}: {:?} bits", path.display(), info.bit_depth));
        }
        let rgb = buf[..w * h * ch]
            .chunks_exact(ch)
            .map(|px| match ch {
                1 | 2 => [px[0] as f32 / 255.0; 3],
                _ => [px[0] as f32 / 255.0, px[1] as f32 / 255.0, px[2] as f32 / 255.0],
            })
            .collect();
        Ok(Image { width: w, height: h, rgb })
    }

    /// The image's mean colour (its smallest mip).
    pub fn mean(&self) -> [f32; 3] {
        let n = self.rgb.len().max(1) as f32;
        let mut s = [0.0f32; 3];
        for c in &self.rgb {
            s = [s[0] + c[0], s[1] + c[1], s[2] + c[2]];
        }
        [s[0] / n, s[1] / n, s[2] / n]
    }

    /// The texel under a UV, wrapping (the nearest one: tool.exe's sampler
    /// is not in the dump, and three corner samples average anyway).
    pub fn sample(&self, uv: [f32; 2]) -> [f32; 3] {
        let x = ((uv[0].rem_euclid(1.0) * self.width as f32) as usize).min(self.width - 1);
        let y = ((uv[1].rem_euclid(1.0) * self.height as f32) as usize).min(self.height - 1);
        self.rgb[y * self.width + x]
    }
}

/// One of the sky's lights (the `lights` block): the sun, or a fill.
#[derive(Clone, Debug, Deserialize)]
pub struct SkyLight {
    pub color: V3,
    pub power: f32,
    /// Radians, z up, pointing at the light.
    pub yaw: f32,
    pub pitch: f32,
    /// Radians: the half-width of the sample grid.
    pub diameter: f32,
    #[serde(default)]
    pub affects_exteriors: bool,
    #[serde(default)]
    pub affects_interiors: bool,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub struct Ambient {
    #[serde(default)]
    pub color: V3,
    #[serde(default)]
    pub power: f32,
}

#[derive(Clone, Debug, Default)]
pub struct Sky {
    pub lights: Vec<SkyLight>,
    pub outdoor_ambient: Ambient,
    pub indoor_ambient: Ambient,
}

/// The BSP's clusters, as `bsp/clusters_0.json` carries them.
#[derive(Clone, Debug, Default, Deserialize)]
pub struct Clusters {
    #[serde(default)]
    pub clusters: Vec<Cluster>,
    /// Each sbsp surface's cluster, in sbsp order; -1 for one in no cluster.
    #[serde(default)]
    pub surface_cluster: Vec<i32>,
    /// Per glTF primitive of `bsp_0.gltf` (the merged scene keeps them
    /// first, in order), each triangle's cluster.
    #[serde(default)]
    pub primitives: Vec<PrimitiveClusters>,
    /// Per cluster, the clusters it sees (tool.exe's PVS).
    #[serde(default)]
    pub visibility: Vec<Vec<u32>>,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub struct PrimitiveClusters {
    #[serde(default)]
    pub material: u32,
    #[serde(default)]
    pub triangle_cluster: Vec<i32>,
}

impl Clusters {
    /// The cluster of a BSP triangle given by its glTF material's name and
    /// its index within that primitive (the transparent pieces, split out
    /// of the BSP glTF by material); -1 when unknown.
    pub fn of_material(&self, names: &[String], name: &str, index: u32) -> i32 {
        self.primitives
            .iter()
            .find(|p| names.get(p.material as usize).map(|n| n == name).unwrap_or(false))
            .and_then(|p| p.triangle_cluster.get(index as usize))
            .copied()
            .unwrap_or(-1)
    }

    /// The cluster of a scene triangle, by its primitive and index; -1
    /// when the table does not cover it (a placed object's triangle).
    pub fn of(&self, prim: u32, index: u32) -> i32 {
        self.primitives
            .get(prim as usize)
            .and_then(|p| p.triangle_cluster.get(index as usize))
            .copied()
            .unwrap_or(-1)
    }
}

#[derive(Clone, Debug, Default, Deserialize)]
pub struct Cluster {
    /// The scenario sky this cluster sees, -1 indoors.
    #[serde(default = "minus_one")]
    pub sky: i32,
}

fn minus_one() -> i32 {
    -1
}

pub struct Staging {
    pub dir: PathBuf,
    pub shaders: HashMap<String, Shader>,
    /// The shaders the collision BSP's surfaces carry (`bsp/collision_0.json`
    /// `materials`, as materials.json names them): what tool.exe's shadow
    /// rays can meet. A rendered surface with no collision (water, light
    /// strips, glow decals) is not in a ray's way at all.
    pub collision_shaders: std::collections::HashSet<String>,
    /// The shaders of collision surfaces whose material type is water
    /// (28): tool.exe gives their charts a constant (0.9, 0.9, 1.0) instead
    /// of a solve (Death Island's sea floor, every texel 230 230 255).
    pub water_shaders: std::collections::HashSet<String>,
    pub sky: Sky,
    pub clusters: Option<Clusters>,
    /// The lightmap pages' file names, page 0 first.
    pub pages: Vec<String>,
    /// `bsp/bsp_0.gltf`'s material names, which the cluster table's
    /// primitives index: the merged scene's transparent pieces keep them.
    pub bsp_material_names: Vec<String>,
}

fn v3(v: &serde_json::Value, default: V3) -> V3 {
    match v.as_array() {
        Some(a) if a.len() >= 3 => [
            a[0].as_f64().unwrap_or(0.0) as f32,
            a[1].as_f64().unwrap_or(0.0) as f32,
            a[2].as_f64().unwrap_or(0.0) as f32,
        ],
        _ => default,
    }
}

impl Staging {
    pub fn load(dir: &Path) -> Result<Staging, String> {
        let read = |name: &str| -> Result<serde_json::Value, String> {
            let p = dir.join(name);
            serde_json::from_slice(&std::fs::read(&p).map_err(|e| format!("{}: {e}", p.display()))?)
                .map_err(|e| format!("{}: {e}", p.display()))
        };
        let materials = read("materials.json")?;
        let mut shaders = HashMap::new();
        let mut images: HashMap<String, Option<Image>> = HashMap::new();
        for (name, info) in materials.as_object().ok_or("materials.json is not an object")? {
            let shader = &info["shader"];
            let tag = &shader["tag"];
            let flags = tag["radiosity_flags"].as_u64().unwrap_or(0);
            let power = tag["power"].as_f64().unwrap_or(0.0) as f32;
            let colour = v3(&tag["color_of_emitted_light"], [0.0; 3]);
            let base = info["base_map"].as_str().or_else(|| shader["base_map"].as_str()).map(str::to_string);
            let class = shader["shader_class"].as_str().unwrap_or("").to_string();
            // Only an environment shader reflects its base map in tool.exe.
            let base_map = match (&base, class.as_str()) {
                (Some(file), "senv") => images
                    .entry(file.clone())
                    .or_insert_with(|| Image::load(&dir.join("textures").join(file)).ok())
                    .clone(),
                _ => None,
            };
            shaders.insert(
                name.clone(),
                Shader {
                    name: name.clone(),
                    class,
                    shader_type: tag["shader_type"].as_u64().unwrap_or(0) as u16,
                    simple_parameterization: flags & 1 != 0,
                    ignore_normals: flags & 2 != 0,
                    transparent_lit: flags & 4 != 0,
                    detail_level: (tag["detail_level"].as_i64().unwrap_or(0).clamp(0, 3)) as usize,
                    emission: [colour[0] * power, colour[1] * power, colour[2] * power],
                    tint: v3(&tag["tint_color"], [0.0; 3]),
                    base_map,
                },
            );
        }

        let placement = read("placement.json")?;
        let mut sky = Sky::default();
        if let Some(entry) = placement["entries"].as_array().and_then(|es| es.iter().find(|e| e["kind"] == "sky")) {
            sky.lights = serde_json::from_value(entry["lights"].clone()).unwrap_or_default();
            sky.outdoor_ambient = serde_json::from_value(entry["outdoor_ambient"].clone()).unwrap_or_default();
            sky.indoor_ambient = serde_json::from_value(entry["indoor_ambient"].clone()).unwrap_or_default();
        }

        let manifest = read("manifest.json")?;
        let pages = manifest["bsps"][0]["lightmap_pages"]
            .as_array()
            .map(|a| a.iter().filter_map(|p| p.as_str().map(str::to_string)).collect())
            .unwrap_or_default();

        let clusters = match std::fs::read(dir.join("bsp").join("clusters_0.json")) {
            Ok(bytes) => Some(serde_json::from_slice(&bytes).map_err(|e| format!("clusters_0.json: {e}"))?),
            Err(_) => None,
        };
        let collision_materials: Vec<(String, u64)> = std::fs::read(dir.join("bsp").join("collision_0.json"))
            .ok()
            .and_then(|b| serde_json::from_slice::<serde_json::Value>(&b).ok())
            .and_then(|c| {
                c["materials"].as_array().map(|ms| {
                    ms.iter()
                        .filter_map(|m| {
                            let path = m["shader_path"].as_str()?;
                            let name = path.chars().map(|ch| if ch == '\\' || ch == '/' || ch == ' ' { '_' } else { ch }).collect::<String>();
                            Some((name, m["material_type"].as_u64().unwrap_or(0)))
                        })
                        .collect()
                })
            })
            .unwrap_or_default();
        let collision_shaders = collision_materials.iter().map(|(n, _)| n.clone()).collect();
        let water_shaders = collision_materials.iter().filter(|(_, t)| *t == 28).map(|(n, _)| n.clone()).collect();
        let bsp_material_names = std::fs::read(dir.join("bsp").join("bsp_0.gltf"))
            .ok()
            .and_then(|b| serde_json::from_slice::<serde_json::Value>(&b).ok())
            .and_then(|g| g["materials"].as_array().map(|ms| ms.iter().map(|m| m["name"].as_str().unwrap_or("").to_string()).collect()))
            .unwrap_or_default();
        Ok(Staging { dir: dir.to_path_buf(), shaders, collision_shaders, water_shaders, sky, clusters, pages, bsp_material_names })
    }
}
