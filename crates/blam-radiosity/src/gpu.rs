//! The GPU path (feature `gpu`): the two loops that cast the solve's rays,
//! the receivers' gather from each batch of shooters and the per-texel sky
//! light, as wgpu compute shaders (`gpu.wgsl`) on Vulkan, DX12 or Metal.
//! Everything else (choosing the shooters, settling the receivers, the
//! adaptive splits, drawing the pages) stays on the CPU, which also stays
//! the reference: the kernels follow transport.rs line for line, and a
//! solve with no usable adapter runs there.

use crate::elements::{Elements, Vertex};
use crate::math::V3;
use crate::transport::{Light, Occluders, Options, PlacedLights};
use wgpu::util::DeviceExt;

/// Targets (or samples) per submission: each submission stays far below
/// the driver's watchdog (Windows resets a GPU after two seconds of one).
const CHUNK: usize = 65536;

/// A storage buffer that grows to fit what it is given.
struct Grow {
    buf: wgpu::Buffer,
    cap: u64,
    usage: wgpu::BufferUsages,
    label: &'static str,
}

impl Grow {
    fn new(device: &wgpu::Device, label: &'static str, usage: wgpu::BufferUsages) -> Grow {
        let cap = 256;
        Grow { buf: device.create_buffer(&wgpu::BufferDescriptor { label: Some(label), size: cap, usage, mapped_at_creation: false }), cap, usage, label }
    }

    /// Room for `bytes`; true when the buffer was replaced (its contents and
    /// bind groups are gone).
    fn fit(&mut self, device: &wgpu::Device, bytes: u64) -> bool {
        if bytes <= self.cap {
            return false;
        }
        let cap = bytes.max(self.cap * 3 / 2).next_multiple_of(256);
        self.buf = device.create_buffer(&wgpu::BufferDescriptor { label: Some(self.label), size: cap, usage: self.usage, mapped_at_creation: false });
        self.cap = cap;
        true
    }
}

#[repr(C)]
#[derive(Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
struct SceneParams {
    tris: u32,
    solid_nodes: u32,
    solid_planes: u32,
    pad: u32,
}

#[repr(C)]
#[derive(Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
struct GatherParams {
    targets: u32,
    shooters: u32,
    cull: f32,
    offset: u32,
}

#[repr(C)]
#[derive(Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
struct DirectParams {
    samples: u32,
    lights: u32,
    placed: u32,
    words: u32,
    sun_ray: f32,
    sun_cosine: u32,
    offset: u32,
    pad: u32,
}

pub struct Gpu {
    device: wgpu::Device,
    queue: wgpu::Queue,
    /// The adapter, for the log: its name and backend.
    pub name: String,
    scene: wgpu::BindGroup,
    gather_layout: wgpu::BindGroupLayout,
    direct_layout: wgpu::BindGroupLayout,
    gather: wgpu::ComputePipeline,
    direct: wgpu::ComputePipeline,
    verts: Grow,
    /// How many of the pool's vertices `verts` holds (they never move once
    /// made, so each batch uploads only the new ones).
    uploaded: usize,
    targets: Grow,
    /// Which target list `targets` holds.
    targets_generation: Option<u64>,
    shooters: Grow,
    gathered: Grow,
    samples: Grow,
    lights: Grow,
    placed: Grow,
    reach: Grow,
    direct_out: Grow,
    readback: Grow,
    gather_params: wgpu::Buffer,
    direct_params: wgpu::Buffer,
}

fn storage_entry(binding: u32, read_only: bool) -> wgpu::BindGroupLayoutEntry {
    wgpu::BindGroupLayoutEntry {
        binding,
        visibility: wgpu::ShaderStages::COMPUTE,
        ty: wgpu::BindingType::Buffer { ty: wgpu::BufferBindingType::Storage { read_only }, has_dynamic_offset: false, min_binding_size: None },
        count: None,
    }
}

fn uniform_entry(binding: u32) -> wgpu::BindGroupLayoutEntry {
    wgpu::BindGroupLayoutEntry {
        binding,
        visibility: wgpu::ShaderStages::COMPUTE,
        ty: wgpu::BindingType::Buffer { ty: wgpu::BufferBindingType::Uniform, has_dynamic_offset: false, min_binding_size: None },
        count: None,
    }
}

/// `data` as a storage buffer, or a small zeroed one when it is empty (a
/// binding cannot be empty; the kernels never read past their counts).
fn init_buffer(device: &wgpu::Device, label: &str, data: &[u8]) -> wgpu::Buffer {
    let zero = [0u8; 16];
    device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some(label),
        contents: if data.is_empty() { &zero } else { data },
        usage: wgpu::BufferUsages::STORAGE,
    })
}

impl Gpu {
    /// The best GPU there is (a discrete one first, Vulkan before DX12),
    /// with the occluders uploaded; Err when there is none, or only a
    /// software one. The rays run on the GPU's ray tracing hardware when it
    /// has some wgpu can reach (ray queries, Vulkan), else through the CPU's
    /// BVH in a compute shader; `BLAM_RADIOSITY_GPU=bvh` forces the latter.
    pub fn new(occ: &Occluders) -> Result<Gpu, String> {
        let want_rt = !std::env::var("BLAM_RADIOSITY_GPU").map(|v| v.eq_ignore_ascii_case("bvh")).unwrap_or(false);
        if want_rt {
            match Self::open(occ, true) {
                Ok(g) => return Ok(g),
                Err(e) if e.starts_with("no GPU") => return Err(e),
                Err(_) => {}
            }
        }
        Self::open(occ, false)
    }

    fn adapter(backends: wgpu::Backends) -> Result<wgpu::Adapter, String> {
        let mut desc = wgpu::InstanceDescriptor::new_without_display_handle();
        desc.backends = backends;
        let instance = wgpu::Instance::new(desc);
        let adapters = pollster::block_on(instance.enumerate_adapters(backends));
        let rank = |a: &wgpu::Adapter| {
            let info = a.get_info();
            let kind = match info.device_type {
                wgpu::DeviceType::DiscreteGpu => 0,
                wgpu::DeviceType::IntegratedGpu => 1,
                wgpu::DeviceType::VirtualGpu | wgpu::DeviceType::Other => 2,
                wgpu::DeviceType::Cpu => 9,
            };
            let backend = match info.backend {
                wgpu::Backend::Vulkan | wgpu::Backend::Metal => 0,
                _ => 1,
            };
            (kind, backend)
        };
        adapters.into_iter().filter(|a| rank(a).0 < 9).min_by_key(rank).ok_or_else(|| "no GPU adapter (Vulkan, DX12 or Metal)".to_string())
    }

    /// The device and everything on it; `rt`: trace with ray queries (Err
    /// when the adapter has none, or setting them up fails).
    fn open(occ: &Occluders, rt: bool) -> Result<Gpu, String> {
        let adapter = Self::adapter(wgpu::Backends::VULKAN | wgpu::Backends::DX12 | wgpu::Backends::METAL)?;
        let info = adapter.get_info();
        if rt && !adapter.features().contains(wgpu::Features::EXPERIMENTAL_RAY_QUERY) {
            return Err(format!("{}: no ray queries", info.name));
        }
        // f64 lets the ray setup round exactly as the CPU does
        // (gpu_exact_f64.wgsl).
        let exact = adapter.features().contains(wgpu::Features::SHADER_F64);
        let name = format!(
            "{} ({:?}, driver {}, {}{})",
            info.name,
            info.backend,
            info.driver_info,
            if rt { "ray tracing hardware" } else { "compute BVH" },
            if exact { "" } else { ", no f64" }
        );
        let mut features = if exact { wgpu::Features::SHADER_F64 } else { wgpu::Features::empty() };
        if rt {
            features |= wgpu::Features::EXPERIMENTAL_RAY_QUERY;
        }
        let (device, queue) = pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor {
            label: Some("blam-radiosity"),
            required_features: features,
            required_limits: adapter.limits(),
            // SAFETY: the ray query feature is experimental in wgpu 30; the
            // solve checks its kernels against the CPU path (examples/gpu_check).
            experimental_features: if rt { unsafe { wgpu::ExperimentalFeatures::enabled() } } else { wgpu::ExperimentalFeatures::disabled() },
            ..Default::default()
        }))
        .map_err(|e| format!("{name}: {e}"))?;
        // Anything that fails validation below (a driver without the
        // shader's features, an acceleration structure it cannot build)
        // comes back as an Err rather than a panic.
        let scope = device.push_error_scope(wgpu::ErrorFilter::Validation);

        let arithmetic = if exact { include_str!("gpu_exact_f64.wgsl") } else { include_str!("gpu_exact_f32.wgsl") };
        let source = if rt {
            format!("enable wgpu_ray_query;\n{}\n{}\n{}", include_str!("gpu_trace_rt.wgsl"), arithmetic, include_str!("gpu.wgsl"))
        } else {
            format!("{}\n{}\n{}", include_str!("gpu_trace_bvh.wgsl"), arithmetic, include_str!("gpu.wgsl"))
        };
        let module = device.create_shader_module(wgpu::ShaderModuleDescriptor { label: Some("gpu.wgsl"), source: wgpu::ShaderSource::Wgsl(source.into()) });
        let scene_entries: Vec<wgpu::BindGroupLayoutEntry> = if rt {
            vec![
                wgpu::BindGroupLayoutEntry {
                    binding: 0,
                    visibility: wgpu::ShaderStages::COMPUTE,
                    ty: wgpu::BindingType::AccelerationStructure { vertex_return: false },
                    count: None,
                },
                storage_entry(1, true),
                storage_entry(3, true),
                storage_entry(4, true),
                uniform_entry(5),
            ]
        } else {
            vec![storage_entry(0, true), storage_entry(1, true), storage_entry(2, true), storage_entry(3, true), storage_entry(4, true), uniform_entry(5)]
        };
        let scene_layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor { label: Some("scene"), entries: &scene_entries });
        let gather_layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("gather"),
            entries: &[storage_entry(0, true), storage_entry(1, true), storage_entry(2, true), storage_entry(3, false), uniform_entry(4)],
        });
        let direct_layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("direct"),
            entries: &[storage_entry(0, true), storage_entry(1, true), storage_entry(2, true), storage_entry(3, true), storage_entry(4, false), uniform_entry(5)],
        });
        let pipeline = |layout: &wgpu::BindGroupLayout, entry: &str| {
            let pl = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
                label: Some(entry),
                bind_group_layouts: &[Some(&scene_layout), Some(layout)],
                immediate_size: 0,
            });
            device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
                label: Some(entry),
                layout: Some(&pl),
                module: &module,
                entry_point: Some(entry),
                compilation_options: Default::default(),
                cache: None,
            })
        };
        let gather = pipeline(&gather_layout, "gather");
        let direct = pipeline(&direct_layout, "direct_light");

        // The occluders, and the collision BSP.
        let (solid_nodes, solid_planes): (&[[i32; 3]], &[[f32; 4]]) = match &occ.solid {
            Some(c) => c.flat(),
            None => (&[], &[]),
        };
        let params = SceneParams { tris: occ.bvh.len() as u32, solid_nodes: solid_nodes.len() as u32, solid_planes: solid_planes.len() as u32, pad: 0 };
        let bsp_nodes = init_buffer(&device, "bsp nodes", bytemuck::cast_slice(solid_nodes));
        let bsp_planes = init_buffer(&device, "bsp planes", bytemuck::cast_slice(solid_planes));
        let scene_uniform = device.create_buffer_init(&wgpu::util::BufferInitDescriptor { label: Some("scene"), contents: bytemuck::bytes_of(&params), usage: wgpu::BufferUsages::UNIFORM });
        let scene = if rt {
            // One acceleration structure: the opaque triangles as an opaque
            // geometry, the glass as a non-opaque one (its panes come back
            // to the shader as candidates, in this order: their tints).
            let (tris, ids) = occ.bvh.triangles();
            let mut opaque: Vec<[f32; 3]> = Vec::new();
            let mut glass: Vec<[f32; 3]> = Vec::new();
            let mut tints: Vec<[f32; 4]> = Vec::new();
            for (t, &id) in tris.iter().zip(ids) {
                match occ.tint.get(id as usize).copied().flatten() {
                    Some(c) => {
                        glass.extend_from_slice(t);
                        tints.push([c[0], c[1], c[2], 1.0]);
                    }
                    None => opaque.extend_from_slice(t),
                }
            }
            if opaque.is_empty() && glass.is_empty() {
                return Err("no occluders to build an acceleration structure from".into());
            }
            let geometry = |vertices: &[[f32; 3]], flags: wgpu::AccelerationStructureGeometryFlags| {
                (
                    wgpu::BlasTriangleGeometrySizeDescriptor { vertex_format: wgpu::VertexFormat::Float32x3, vertex_count: vertices.len() as u32, index_format: None, index_count: None, flags },
                    device.create_buffer_init(&wgpu::util::BufferInitDescriptor { label: Some("occluder vertices"), contents: bytemuck::cast_slice(vertices), usage: wgpu::BufferUsages::BLAS_INPUT }),
                )
            };
            let mut parts = Vec::new();
            if !opaque.is_empty() {
                parts.push(geometry(&opaque, wgpu::AccelerationStructureGeometryFlags::OPAQUE));
            }
            if !glass.is_empty() {
                parts.push(geometry(&glass, wgpu::AccelerationStructureGeometryFlags::NO_DUPLICATE_ANY_HIT_INVOCATION));
            }
            let blas = device.create_blas(
                &wgpu::CreateBlasDescriptor { label: Some("occluders"), flags: wgpu::AccelerationStructureFlags::PREFER_FAST_TRACE, update_mode: wgpu::AccelerationStructureUpdateMode::Build },
                wgpu::BlasGeometrySizeDescriptors::Triangles { descriptors: parts.iter().map(|(s, _)| s.clone()).collect() },
            );
            let mut tlas = device.create_tlas(&wgpu::CreateTlasDescriptor {
                label: Some("occluders"),
                max_instances: 1,
                flags: wgpu::AccelerationStructureFlags::PREFER_FAST_TRACE,
                update_mode: wgpu::AccelerationStructureUpdateMode::Build,
            });
            *tlas.get_mut_single(0).ok_or("tlas instance")? = Some(wgpu::TlasInstance::new(&blas, [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0], 0, 0xff));
            let mut enc = device.create_command_encoder(&wgpu::CommandEncoderDescriptor { label: Some("acceleration structure") });
            let entry = wgpu::BlasBuildEntry {
                blas: &blas,
                geometry: wgpu::BlasGeometries::TriangleGeometries(
                    parts
                        .iter()
                        .map(|(size, buf)| wgpu::BlasTriangleGeometry {
                            size,
                            vertex_buffer: buf,
                            first_vertex: 0,
                            vertex_stride: 12,
                            index_buffer: None,
                            first_index: None,
                            transform_buffer: None,
                            transform_buffer_offset: None,
                        })
                        .collect(),
                ),
            };
            enc.build_acceleration_structures(std::iter::once(&entry), std::iter::once(&tlas));
            queue.submit([enc.finish()]);
            if tints.is_empty() {
                tints.push([1.0; 4]);
            }
            let glass_tints = init_buffer(&device, "glass tints", bytemuck::cast_slice(&tints));
            device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some("scene"),
                layout: &scene_layout,
                entries: &[
                    wgpu::BindGroupEntry { binding: 0, resource: tlas.as_binding() },
                    wgpu::BindGroupEntry { binding: 1, resource: glass_tints.as_entire_binding() },
                    wgpu::BindGroupEntry { binding: 3, resource: bsp_nodes.as_entire_binding() },
                    wgpu::BindGroupEntry { binding: 4, resource: bsp_planes.as_entire_binding() },
                    wgpu::BindGroupEntry { binding: 5, resource: scene_uniform.as_entire_binding() },
                ],
            })
        } else {
            // The CPU's BVH, and each triangle's tint in tree order.
            let (nodes, tris, ids) = occ.bvh.flat();
            let tint: Vec<[f32; 4]> = ids
                .iter()
                .map(|&id| match occ.tint.get(id as usize).copied().flatten() {
                    Some(c) => [c[0], c[1], c[2], 1.0],
                    None => [0.0; 4],
                })
                .collect();
            let buffers = [
                init_buffer(&device, "bvh nodes", bytemuck::cast_slice(&nodes)),
                init_buffer(&device, "bvh triangles", bytemuck::cast_slice(&tris)),
                init_buffer(&device, "tints", bytemuck::cast_slice(&tint)),
            ];
            device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some("scene"),
                layout: &scene_layout,
                entries: &[
                    wgpu::BindGroupEntry { binding: 0, resource: buffers[0].as_entire_binding() },
                    wgpu::BindGroupEntry { binding: 1, resource: buffers[1].as_entire_binding() },
                    wgpu::BindGroupEntry { binding: 2, resource: buffers[2].as_entire_binding() },
                    wgpu::BindGroupEntry { binding: 3, resource: bsp_nodes.as_entire_binding() },
                    wgpu::BindGroupEntry { binding: 4, resource: bsp_planes.as_entire_binding() },
                    wgpu::BindGroupEntry { binding: 5, resource: scene_uniform.as_entire_binding() },
                ],
            })
        };
        if let Some(e) = pollster::block_on(scope.pop()) {
            return Err(format!("{name}: {e}"));
        }

        let storage = wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST;
        let output = wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC;
        let uniform = |label: &str, size: u64| device.create_buffer(&wgpu::BufferDescriptor { label: Some(label), size, usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST, mapped_at_creation: false });
        Ok(Gpu {
            verts: Grow::new(&device, "vertices", storage | wgpu::BufferUsages::COPY_SRC),
            uploaded: 0,
            targets: Grow::new(&device, "targets", storage),
            targets_generation: None,
            shooters: Grow::new(&device, "shooters", storage),
            gathered: Grow::new(&device, "gathered", output),
            samples: Grow::new(&device, "samples", storage),
            lights: Grow::new(&device, "lights", storage),
            placed: Grow::new(&device, "placed lights", storage),
            reach: Grow::new(&device, "placed reach", storage),
            direct_out: Grow::new(&device, "direct", output),
            readback: Grow::new(&device, "readback", wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST),
            gather_params: uniform("gather params", std::mem::size_of::<GatherParams>() as u64),
            direct_params: uniform("direct params", std::mem::size_of::<DirectParams>() as u64),
            device,
            queue,
            name,
            scene,
            gather_layout,
            direct_layout,
            gather,
            direct,
        })
    }

    /// The pool's vertices on the GPU: those made since the last call.
    fn sync_vertices(&mut self, verts: &[Vertex]) {
        let flat = |v: &[Vertex]| -> Vec<[f32; 4]> { v.iter().flat_map(|v| [[v.p[0], v.p[1], v.p[2], 0.0], [v.n[0], v.n[1], v.n[2], 0.0]]).collect() };
        if self.verts.fit(&self.device, (verts.len() * 32) as u64) {
            self.uploaded = 0;
        }
        if verts.len() > self.uploaded {
            let data = flat(&verts[self.uploaded..]);
            self.queue.write_buffer(&self.verts.buf, (self.uploaded * 32) as u64, bytemuck::cast_slice(&data));
            self.uploaded = verts.len();
        }
    }

    /// Copy `bytes` of `src` back to the CPU, after everything submitted,
    /// and hand them to `take` as floats while they are mapped.
    /// `enc` (the work that fills `src`) goes in the same submission.
    fn read<T>(&mut self, mut enc: wgpu::CommandEncoder, src: &wgpu::Buffer, bytes: u64, take: impl FnOnce(&[f32]) -> T) -> Result<T, String> {
        self.readback.fit(&self.device, bytes);
        enc.copy_buffer_to_buffer(src, 0, &self.readback.buf, 0, bytes);
        self.queue.submit([enc.finish()]);
        let slice = self.readback.buf.slice(..bytes);
        let (tx, rx) = std::sync::mpsc::channel();
        slice.map_async(wgpu::MapMode::Read, move |r| {
            let _ = tx.send(r);
        });
        self.device.poll(wgpu::PollType::wait_indefinitely()).map_err(|e| format!("GPU: {e}"))?;
        rx.recv().map_err(|e| format!("GPU readback: {e}"))?.map_err(|e| format!("GPU readback: {e}"))?;
        let out = {
            let view = slice.get_mapped_range().map_err(|e| format!("GPU readback: {e}"))?;
            take(bytemuck::cast_slice::<u8, f32>(&view))
        };
        self.readback.buf.unmap();
        Ok(out)
    }

    /// `Solver::shoot`'s gather: for each of `targets` (vertex indices),
    /// the light `shooters` (element indices) give it and its
    /// luminance-weighted incident direction.
    /// `generation` names the target list: the same one as the last call's
    /// is not uploaded again.
    pub fn gather(&mut self, elements: &Elements, shooters: &[u32], targets: &[u32], generation: u64, cull: f32) -> Result<Vec<(V3, V3)>, String> {
        if targets.is_empty() {
            return Ok(Vec::new());
        }
        self.sync_vertices(&elements.pool.vertices);
        let shooter_data: Vec<[f32; 4]> = shooters
            .iter()
            .flat_map(|&s| {
                let e = &elements.elements[s as usize];
                let p = |k: usize| elements.pool.vertices[e.patch.v[k] as usize].p;
                let (a, b, c) = (p(0), p(1), p(2));
                let ignore = if elements.materials[e.material as usize].ignore_normals { 1.0 } else { 0.0 };
                [
                    [a[0], a[1], a[2], e.patch.area / 3.0],
                    [b[0], b[1], b[2], e.d],
                    [c[0], c[1], c[2], e.delta.iter().sum::<f32>()],
                    [e.normal[0], e.normal[1], e.normal[2], ignore],
                    [e.delta[0], e.delta[1], e.delta[2], 0.0],
                ]
            })
            .collect();
        if self.targets.fit(&self.device, (targets.len() * 4) as u64) {
            self.targets_generation = None;
        }
        self.shooters.fit(&self.device, (shooter_data.len() * 16) as u64);
        let out_bytes = (targets.len() * 24) as u64;
        self.gathered.fit(&self.device, out_bytes);
        if self.targets_generation != Some(generation) {
            self.queue.write_buffer(&self.targets.buf, 0, bytemuck::cast_slice(targets));
            self.targets_generation = Some(generation);
        }
        self.queue.write_buffer(&self.shooters.buf, 0, bytemuck::cast_slice(&shooter_data));
        let group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("gather"),
            layout: &self.gather_layout,
            entries: &[
                wgpu::BindGroupEntry { binding: 0, resource: self.verts.buf.as_entire_binding() },
                wgpu::BindGroupEntry { binding: 1, resource: self.targets.buf.as_entire_binding() },
                wgpu::BindGroupEntry { binding: 2, resource: self.shooters.buf.as_entire_binding() },
                wgpu::BindGroupEntry { binding: 3, resource: self.gathered.buf.as_entire_binding() },
                wgpu::BindGroupEntry { binding: 4, resource: self.gather_params.as_entire_binding() },
            ],
        });
        // One dispatch, two-dimensional past 65535 workgroups, and the copy
        // back in the same submission: a batch costs one round trip.
        let params = GatherParams { targets: targets.len() as u32, shooters: shooters.len() as u32, cull, offset: 0 };
        self.queue.write_buffer(&self.gather_params, 0, bytemuck::bytes_of(&params));
        let groups = targets.len().div_ceil(64);
        let (x, y) = (groups.min(65535), groups.div_ceil(groups.min(65535)));
        let mut enc = self.device.create_command_encoder(&wgpu::CommandEncoderDescriptor { label: Some("gather") });
        {
            let mut pass = enc.begin_compute_pass(&wgpu::ComputePassDescriptor { label: Some("gather"), timestamp_writes: None });
            pass.set_pipeline(&self.gather);
            pass.set_bind_group(0, &self.scene, &[]);
            pass.set_bind_group(1, &group, &[]);
            pass.dispatch_workgroups(x as u32, y as u32, 1);
        }
        let buf = self.gathered.buf.clone();
        self.read(enc, &buf, out_bytes, |raw| raw.chunks_exact(6).map(|c| ([c[0], c[1], c[2]], [c[3], c[4], c[5]])).collect())
    }

    /// `direct_terms_placed` at every sample (position, normal, set: 0
    /// exterior 1 interior, cluster): (all, the sun's part, the sun's
    /// potential, the sun's visibility).
    pub fn direct(&mut self, samples: &[(V3, V3, u32, i32)], exterior: &[Light], interior: &[Light], placed: &PlacedLights, opt: &Options) -> Result<Vec<(V3, V3, V3, f32)>, String> {
        if samples.is_empty() {
            return Ok(Vec::new());
        }
        let mut lights: Vec<[f32; 4]> = Vec::new();
        for (set, list) in [(0.0f32, exterior), (1.0, interior)] {
            for l in list {
                if let Light::Directional { towards, colour, sun } = l {
                    lights.push([towards[0], towards[1], towards[2], set]);
                    lights.push([colour[0], colour[1], colour[2], if *sun { 1.0 } else { 0.0 }]);
                }
            }
        }
        let words = placed.reach.iter().map(|r| r.len().div_ceil(32)).max().unwrap_or(0);
        let mut placed_data: Vec<[f32; 4]> = Vec::new();
        let mut reach: Vec<u32> = Vec::new();
        for (i, l) in placed.lights.iter().enumerate() {
            let Light::Point { pos, colour, reach: r, cone, .. } = l else { continue };
            let row = placed.reach.get(i).map(|r| r.as_slice()).unwrap_or(&[]);
            let first = reach.len();
            let mut bits = vec![0u32; words];
            for (c, &on) in row.iter().enumerate() {
                if on {
                    bits[c / 32] |= 1 << (c % 32);
                }
            }
            reach.extend(bits);
            let (axis, cf, cc, spot) = match cone {
                Some((a, cf, cc)) => (*a, *cf, *cc, 1.0),
                None => ([0.0; 3], 0.0, 0.0, 0.0),
            };
            placed_data.push([pos[0], pos[1], pos[2], *r]);
            placed_data.push([colour[0], colour[1], colour[2], spot]);
            placed_data.push([axis[0], axis[1], axis[2], cf]);
            placed_data.push([cc, if row.is_empty() { 1.0 } else { 0.0 }, first as f32, 0.0]);
        }
        let placed_count = placed_data.len() / 4;
        if lights.is_empty() {
            lights.push([0.0; 4]);
        }
        if placed_data.is_empty() {
            placed_data.push([0.0; 4]);
        }
        if reach.is_empty() {
            reach.push(0);
        }
        self.lights.fit(&self.device, (lights.len() * 16) as u64);
        self.placed.fit(&self.device, (placed_data.len() * 16) as u64);
        self.reach.fit(&self.device, (reach.len() * 4) as u64);
        self.queue.write_buffer(&self.lights.buf, 0, bytemuck::cast_slice(&lights));
        self.queue.write_buffer(&self.placed.buf, 0, bytemuck::cast_slice(&placed_data));
        self.queue.write_buffer(&self.reach.buf, 0, bytemuck::cast_slice(&reach));
        let n_lights = (exterior.iter().chain(interior).filter(|l| matches!(l, Light::Directional { .. })).count()) as u32;

        let mut out = Vec::with_capacity(samples.len());
        // A few million samples at a time: the upload and the readback stay
        // a few hundred megabytes.
        for part in samples.chunks(CHUNK * 32) {
            let flat: Vec<[f32; 4]> = part
                .iter()
                .flat_map(|(p, n, set, cluster)| [[p[0], p[1], p[2], f32::from_bits(*set)], [n[0], n[1], n[2], f32::from_bits(*cluster as u32)]])
                .collect();
            self.samples.fit(&self.device, (flat.len() * 16) as u64);
            let out_bytes = (part.len() * 48) as u64;
            self.direct_out.fit(&self.device, out_bytes);
            self.queue.write_buffer(&self.samples.buf, 0, bytemuck::cast_slice(&flat));
            let group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some("direct"),
                layout: &self.direct_layout,
                entries: &[
                    wgpu::BindGroupEntry { binding: 0, resource: self.samples.buf.as_entire_binding() },
                    wgpu::BindGroupEntry { binding: 1, resource: self.lights.buf.as_entire_binding() },
                    wgpu::BindGroupEntry { binding: 2, resource: self.placed.buf.as_entire_binding() },
                    wgpu::BindGroupEntry { binding: 3, resource: self.reach.buf.as_entire_binding() },
                    wgpu::BindGroupEntry { binding: 4, resource: self.direct_out.buf.as_entire_binding() },
                    wgpu::BindGroupEntry { binding: 5, resource: self.direct_params.as_entire_binding() },
                ],
            });
            for start in (0..part.len()).step_by(CHUNK) {
                let n = CHUNK.min(part.len() - start);
                let params = DirectParams {
                    samples: part.len() as u32,
                    lights: n_lights,
                    placed: placed_count as u32,
                    words: words as u32,
                    sun_ray: opt.sun_ray,
                    sun_cosine: opt.sun_cosine as u32,
                    offset: start as u32,
                    pad: 0,
                };
                self.queue.write_buffer(&self.direct_params, 0, bytemuck::bytes_of(&params));
                let mut enc = self.device.create_command_encoder(&wgpu::CommandEncoderDescriptor { label: Some("direct") });
                {
                    let mut pass = enc.begin_compute_pass(&wgpu::ComputePassDescriptor { label: Some("direct"), timestamp_writes: None });
                    pass.set_pipeline(&self.direct);
                    pass.set_bind_group(0, &self.scene, &[]);
                    pass.set_bind_group(1, &group, &[]);
                    pass.dispatch_workgroups(n.div_ceil(64) as u32, 1, 1);
                }
                self.queue.submit([enc.finish()]);
            }
            let buf = self.direct_out.buf.clone();
            let enc = self.device.create_command_encoder(&wgpu::CommandEncoderDescriptor { label: Some("readback") });
            self.read(enc, &buf, out_bytes, |raw| out.extend(raw.chunks_exact(12).map(|c| ([c[0], c[1], c[2]], [c[4], c[5], c[6]], [c[8], c[9], c[10]], c[3]))))?;
        }
        Ok(out)
    }
}
