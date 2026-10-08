//! The solved light onto lightmap pages. The bounce and ambient light are
//! what the vertices hold, drawn Gouraud over each patch's lightmap UVs at
//! a multiple of the shipped page's size; the sun and the sky's fill are
//! evaluated again at every texel from its own position and normal, so a
//! shadow's edge lands where the geometry puts it and not on the nearest
//! patch boundary (tool.exe's pages are too coarse to show the
//! difference; ours are not). Pages are dilated so bilinear filtering at
//! a chart's edge never reads an empty texel.

use crate::elements::{Element, Elements, Patch};
use crate::math::{add, mul, norm, V3};
use crate::transport::{direct_light, Light, Occluders, Options, Set};
use rayon::prelude::*;

/// One lightmap page, RGB in 0..1 with a coverage mask.
pub struct Page {
    pub width: usize,
    pub height: usize,
    pub rgb: Vec<V3>,
    pub covered: Vec<bool>,
}

/// tool.exe's vertex colour: divided by its largest channel when that
/// exceeds 1, then clamped.
pub fn vertex_colour(total: V3) -> V3 {
    let m = total[0].max(total[1]).max(total[2]);
    let c = if m > 1.0 { [total[0] / m, total[1] / m, total[2] / m] } else { total };
    [c[0].clamp(0.0, 1.0), c[1].clamp(0.0, 1.0), c[2].clamp(0.0, 1.0)]
}

impl Page {
    pub fn new(width: usize, height: usize) -> Page {
        Page { width, height, rgb: vec![[0.0; 3]; width * height], covered: vec![false; width * height] }
    }

    /// Every texel a triangle (UVs in 0..1) touches, with its barycentric
    /// weights (clamped and renormalised just outside the edges): texels
    /// whose centre lies within half a texel of the triangle count, so
    /// neighbouring charts meet without a gap and a sliver still marks.
    /// `f(index, inside, weights)`.
    pub fn rasterize(&self, uv: [[f32; 2]; 3], f: &mut dyn FnMut(usize, bool, [f32; 3])) {
        let (w, h) = (self.width as f32, self.height as f32);
        let p: Vec<[f32; 2]> = uv.iter().map(|t| [t[0] * w, t[1] * h]).collect();
        let area = (p[1][0] - p[0][0]) * (p[2][1] - p[0][1]) - (p[2][0] - p[0][0]) * (p[1][1] - p[0][1]);
        if area.abs() < 1e-12 {
            return;
        }
        let x0 = (p.iter().map(|q| q[0]).fold(f32::MAX, f32::min) - 1.0).floor().max(0.0) as usize;
        let x1 = ((p.iter().map(|q| q[0]).fold(f32::MIN, f32::max) + 1.0).ceil() as usize).min(self.width);
        let y0 = (p.iter().map(|q| q[1]).fold(f32::MAX, f32::min) - 1.0).floor().max(0.0) as usize;
        let y1 = ((p.iter().map(|q| q[1]).fold(f32::MIN, f32::max) + 1.0).ceil() as usize).min(self.height);
        // Half a texel, in barycentric units along each edge's normal.
        let edge_len = |a: [f32; 2], b: [f32; 2]| ((b[0] - a[0]).powi(2) + (b[1] - a[1]).powi(2)).sqrt();
        let slack = [
            0.5 * edge_len(p[1], p[2]) / area.abs(),
            0.5 * edge_len(p[2], p[0]) / area.abs(),
            0.5 * edge_len(p[0], p[1]) / area.abs(),
        ];
        for y in y0..y1 {
            for x in x0..x1 {
                let (cx, cy) = (x as f32 + 0.5, y as f32 + 0.5);
                let w0 = ((p[1][0] - cx) * (p[2][1] - cy) - (p[2][0] - cx) * (p[1][1] - cy)) / area;
                let w1 = ((p[2][0] - cx) * (p[0][1] - cy) - (p[0][0] - cx) * (p[2][1] - cy)) / area;
                let w2 = 1.0 - w0 - w1;
                if w0 < -slack[0] || w1 < -slack[1] || w2 < -slack[2] {
                    continue;
                }
                let inside = w0 >= 0.0 && w1 >= 0.0 && w2 >= 0.0;
                let (a, b, c) = (w0.max(0.0), w1.max(0.0), w2.max(0.0));
                let s = (a + b + c).max(1e-6);
                f(y * self.width + x, inside, [a / s, b / s, c / s]);
            }
        }
    }

    /// A triangle Gouraud between its corner values. A texel inside a
    /// triangle is its own; one only within reach of the edge takes the
    /// triangle's value unless something already drew it.
    pub fn triangle(&mut self, uv: [[f32; 2]; 3], c: [V3; 3]) {
        let mut writes: Vec<(usize, V3)> = Vec::new();
        self.rasterize(uv, &mut |i, inside, w| {
            if inside || !self.covered[i] {
                writes.push((i, [
                    c[0][0] * w[0] + c[1][0] * w[1] + c[2][0] * w[2],
                    c[0][1] * w[0] + c[1][1] * w[1] + c[2][1] * w[2],
                    c[0][2] * w[0] + c[1][2] * w[1] + c[2][2] * w[2],
                ]));
            }
        });
        for (i, v) in writes {
            self.rgb[i] = v;
            self.covered[i] = true;
        }
    }

    /// `self` box-filtered down by `k`: a texel is the mean of its covered
    /// subtexels, and covered when any is.
    pub fn downsample(&self, k: usize) -> Page {
        let (w, h) = (self.width / k, self.height / k);
        let mut out = Page::new(w.max(1), h.max(1));
        for y in 0..h {
            for x in 0..w {
                let mut sum = [0.0f32; 3];
                let mut n = 0;
                for sy in 0..k {
                    for sx in 0..k {
                        let i = (y * k + sy) * self.width + x * k + sx;
                        if self.covered[i] {
                            sum = add(sum, self.rgb[i]);
                            n += 1;
                        }
                    }
                }
                if n > 0 {
                    let i = y * w + x;
                    out.rgb[i] = mul(sum, 1.0 / n as f32);
                    out.covered[i] = true;
                }
            }
        }
        out
    }

    /// Fill every empty texel from a covered neighbour, repeatedly, as
    /// tool.exe dilates its chart bitmaps.
    pub fn dilate(&mut self, rounds: usize) {
        for _ in 0..rounds {
            let prev = self.covered.clone();
            let src = self.rgb.clone();
            let mut changed = false;
            for y in 0..self.height {
                for x in 0..self.width {
                    let i = y * self.width + x;
                    if prev[i] {
                        continue;
                    }
                    let mut sum = [0.0f32; 3];
                    let mut n = 0;
                    for (dx, dy) in [(-1i32, 0i32), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)] {
                        let (nx, ny) = (x as i32 + dx, y as i32 + dy);
                        if nx < 0 || ny < 0 || nx >= self.width as i32 || ny >= self.height as i32 {
                            continue;
                        }
                        let j = ny as usize * self.width + nx as usize;
                        if prev[j] {
                            sum = add(sum, src[j]);
                            n += 1;
                        }
                    }
                    if n > 0 {
                        self.rgb[i] = mul(sum, 1.0 / n as f32);
                        self.covered[i] = true;
                        changed = true;
                    }
                }
            }
            if !changed {
                break;
            }
        }
    }

    pub fn write_png(&self, path: &std::path::Path) -> Result<(), String> {
        let file = std::fs::File::create(path).map_err(|e| format!("{}: {e}", path.display()))?;
        let mut enc = png::Encoder::new(std::io::BufWriter::new(file), self.width as u32, self.height as u32);
        enc.set_color(png::ColorType::Rgb);
        enc.set_depth(png::BitDepth::Eight);
        let mut w = enc.write_header().map_err(|e| e.to_string())?;
        let data: Vec<u8> = self
            .rgb
            .iter()
            .flat_map(|c| c.iter().map(|x| (x.clamp(0.0, 1.0) * 255.0).round() as u8).collect::<Vec<_>>())
            .collect();
        w.write_image_data(&data).map_err(|e| e.to_string())
    }
}

/// What the pages are drawn from.
pub struct Draw<'a> {
    pub elements: &'a Elements,
    /// Page `i` at `sizes[i]` texels.
    pub sizes: &'a [(usize, usize)],
    /// Drawn at this multiple and box-filtered down (tool.exe: 3).
    pub supersample: usize,
    /// With these three, the sun and fill are re-evaluated per texel
    /// (`Options::texel_direct`); the vertices then give only the bounce
    /// and ambient.
    pub occluders: Option<&'a Occluders>,
    /// The exterior and interior sets' lights.
    pub lights: Option<&'a (Vec<Light>, Vec<Light>)>,
    pub cluster_sets: Option<&'a [Set]>,
    pub options: &'a Options,
}

fn leaves(e: &Element) -> &[Patch] {
    if e.children.is_empty() {
        std::slice::from_ref(&e.patch)
    } else {
        &e.children
    }
}

/// Every lightmap page of the solve.
pub fn pages(draw: &Draw) -> Vec<Page> {
    let el = draw.elements;
    let k = draw.supersample.max(1);
    let per_texel = draw.occluders.is_some() && draw.lights.is_some() && draw.options.texel_direct;
    // The Gouraud part: everything the vertices hold, or only what the
    // texel pass does not redo.
    let value = |v: u32| -> V3 {
        let vert = &el.pool.vertices[v as usize];
        if per_texel {
            [vert.total[0] - vert.sun[0], vert.total[1] - vert.sun[1], vert.total[2] - vert.sun[2]]
        } else {
            vert.total
        }
    };
    let mut hi: Vec<Page> = draw.sizes.iter().map(|&(w, h)| Page::new((w * k).max(1), (h * k).max(1))).collect();
    for e in &el.elements {
        let page = el.materials[e.material as usize].page;
        let Some(p) = hi.get_mut(page) else { continue };
        for patch in leaves(e) {
            p.triangle(patch.uv1, [value(patch.v[0]), value(patch.v[1]), value(patch.v[2])]);
        }
    }

    if per_texel {
        let occ = draw.occluders.unwrap();
        let (exterior, interior) = draw.lights.unwrap();
        let sets = draw.cluster_sets.unwrap_or(&[]);
        // Per page at the drawn resolution: every texel's position, normal
        // and light set from the patches covering it (inside a patch takes
        // that patch; only within reach of an edge, the first), then the
        // direct light at each in parallel, added before the box filter so
        // the shadow edge is antialiased like the rest.
        for (pi, page) in hi.iter_mut().enumerate() {
            let mut sample: Vec<Option<(V3, V3, Set)>> = vec![None; page.width * page.height];
            let mut owned: Vec<bool> = vec![false; page.width * page.height];
            for e in &el.elements {
                if el.materials[e.material as usize].page != pi {
                    continue;
                }
                let set = if e.cluster >= 0 { sets.get(e.cluster as usize).copied().unwrap_or(Set::Exterior) } else { Set::Exterior };
                for patch in leaves(e) {
                    let pv = [
                        &el.pool.vertices[patch.v[0] as usize],
                        &el.pool.vertices[patch.v[1] as usize],
                        &el.pool.vertices[patch.v[2] as usize],
                    ];
                    page.rasterize(patch.uv1, &mut |i, inside, w| {
                        if inside || !owned[i] {
                            let p = add(add(mul(pv[0].p, w[0]), mul(pv[1].p, w[1])), mul(pv[2].p, w[2]));
                            let n = norm(add(add(mul(pv[0].n, w[0]), mul(pv[1].n, w[1])), mul(pv[2].n, w[2])));
                            sample[i] = Some((p, n, set));
                            owned[i] = inside;
                        }
                    });
                }
            }
            let direct: Vec<Option<V3>> = sample
                .par_iter()
                .map(|s| {
                    s.map(|(p, n, set)| {
                        let lights = match set {
                            Set::Exterior => exterior,
                            Set::Interior => interior,
                        };
                        direct_light(occ, lights, p, n, draw.options)
                    })
                })
                .collect();
            for (i, d) in direct.iter().enumerate() {
                if let Some(d) = d {
                    page.rgb[i] = add(page.rgb[i], *d);
                    page.covered[i] = true;
                }
            }
        }
    }
    let mut out: Vec<Page> = hi
        .iter()
        .map(|p| if k > 1 { p.downsample(k) } else { Page { width: p.width, height: p.height, rgb: p.rgb.clone(), covered: p.covered.clone() } })
        .collect();
    for p in out.iter_mut() {
        for c in p.rgb.iter_mut() {
            *c = vertex_colour(*c);
        }
        p.dilate(8);
    }
    out
}
