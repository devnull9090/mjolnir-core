//! The solved light onto lightmap pages. The bounce and ambient light are
//! what the vertices hold, drawn Gouraud over each patch's lightmap UVs at
//! a multiple of the shipped page's size; the sun and the sky's fill are
//! evaluated again at every texel from its own position and normal, so a
//! shadow's edge lands where the geometry puts it and not on the nearest
//! patch boundary (tool.exe's pages are too coarse to show the
//! difference; ours are not). Pages are dilated so bilinear filtering at
//! a chart's edge never reads an empty texel.

use crate::elements::{Element, Elements, Patch};
use crate::math::{add, luma, mul, norm, V3};
use crate::transport::{direct_terms_placed, Light, Occluders, Options, PlacedLights, Set};
use rayon::prelude::*;

/// A texel's direct light: (all, the sun's part, the sun's potential, the
/// sun's visibility), as `direct_terms` gives it.
type Terms = (V3, V3, V3, f32);

/// One lightmap page, RGB in 0..1 with a coverage mask.
pub struct Page {
    pub width: usize,
    pub height: usize,
    pub rgb: Vec<V3>,
    pub covered: Vec<bool>,
    /// Covered by a drawn patch, before the dilation (which fills `covered`
    /// outwards): where a chart really is, what `--compare` scores.
    pub drawn: Vec<bool>,
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
        Page { width, height, rgb: vec![[0.0; 3]; width * height], covered: vec![false; width * height], drawn: vec![false; width * height] }
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
    /// subtexels, and covered when any is. Rows in parallel.
    pub fn downsample(&self, k: usize) -> Page {
        let (w, h) = (self.width / k, self.height / k);
        let mut out = Page::new(w.max(1), h.max(1));
        let ow = out.width;
        out.rgb
            .par_chunks_mut(ow)
            .zip(out.covered.par_chunks_mut(ow))
            .zip(out.drawn.par_chunks_mut(ow))
            .enumerate()
            .take(h)
            .for_each(|(y, ((rgb, covered), drawn))| {
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
                        rgb[x] = mul(sum, 1.0 / n as f32);
                        covered[x] = true;
                        drawn[x] = true;
                    }
                }
            });
        out
    }

    /// Fill every empty texel from a covered neighbour, repeatedly, as
    /// tool.exe dilates its chart bitmaps: each round, every empty texel
    /// beside a covered one takes its covered neighbours' mean. Only that
    /// frontier is visited (a round over the whole page cost seconds on a
    /// mostly empty 2048 page at 64 rounds).
    pub fn dilate(&mut self, rounds: usize) {
        const AROUND: [(i32, i32); 8] = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)];
        let (width, w, h) = (self.width, self.width as i32, self.height as i32);
        let near = move |i: usize| {
            let (x, y) = ((i % width) as i32, (i / width) as i32);
            AROUND.iter().filter_map(move |(dx, dy)| {
                let (nx, ny) = (x + dx, y + dy);
                (nx >= 0 && ny >= 0 && nx < w && ny < h).then_some(ny as usize * width + nx as usize)
            })
        };
        let covered = &self.covered;
        let mut frontier: Vec<usize> = (0..covered.len()).into_par_iter().filter(|&i| !covered[i] && near(i).any(|j| covered[j])).collect();
        let mut queued = vec![false; self.covered.len()];
        for _ in 0..rounds {
            if frontier.is_empty() {
                break;
            }
            let (covered, rgb) = (&self.covered, &self.rgb);
            let fills: Vec<V3> = frontier
                .par_iter()
                .map(|&i| {
                    let mut sum = [0.0f32; 3];
                    let mut n = 0;
                    for j in near(i) {
                        if covered[j] {
                            sum = add(sum, rgb[j]);
                            n += 1;
                        }
                    }
                    mul(sum, 1.0 / n as f32)
                })
                .collect();
            for (&i, c) in frontier.iter().zip(&fills) {
                self.rgb[i] = *c;
                self.covered[i] = true;
            }
            let mut next = Vec::new();
            for &i in &frontier {
                for j in near(i) {
                    if !self.covered[j] && !queued[j] {
                        queued[j] = true;
                        next.push(j);
                    }
                }
            }
            for &j in &next {
                queued[j] = false;
            }
            frontier = next;
        }
    }

    /// RGB from `self`, alpha from `alpha`'s red channel (a page of the
    /// same size).
    pub fn write_png_rgba(&self, alpha: &Page, path: &std::path::Path) -> Result<(), String> {
        if alpha.width != self.width || alpha.height != self.height {
            return Err(format!("{}: alpha page {}x{} against {}x{}", path.display(), alpha.width, alpha.height, self.width, self.height));
        }
        let file = std::fs::File::create(path).map_err(|e| format!("{}: {e}", path.display()))?;
        let mut enc = png::Encoder::new(std::io::BufWriter::new(file), self.width as u32, self.height as u32);
        enc.set_color(png::ColorType::Rgba);
        enc.set_depth(png::BitDepth::Eight);
        let mut w = enc.write_header().map_err(|e| e.to_string())?;
        let q = |x: f32| (x.clamp(0.0, 1.0) * 255.0).round() as u8;
        let data: Vec<u8> = self.rgb.iter().zip(&alpha.rgb).flat_map(|(c, a)| [q(c[0]), q(c[1]), q(c[2]), q(a[0])]).collect();
        w.write_image_data(&data).map_err(|e| e.to_string())
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
    /// The placed lights, re-evaluated per texel like the sun.
    pub placed: Option<&'a PlacedLights>,
    pub cluster_sets: Option<&'a [Set]>,
    pub options: &'a Options,
    /// Dilation rounds after the draw: the charts' padding grows with the
    /// page scale, and a mip chain averages whatever is left empty into the
    /// charts' edges (8 per unit of scale).
    pub dilate: usize,
    /// Where to add the seconds the per-texel direct pass took.
    pub texel_direct_seconds: Option<&'a mut f64>,
    /// Casts the per-texel pass's rays when set (dropped on a failure).
    pub gpu: Option<&'a mut crate::gpu::Gpu>,
}

fn leaves(e: &Element) -> &[Patch] {
    if e.children.is_empty() {
        std::slice::from_ref(&e.patch)
    } else {
        &e.children
    }
}

/// Every lightmap page of the solve and, with the per-texel pass, three
/// companions per page of the same size and coverage: the sun's visibility
/// (grey); the texel's light without the sun (CE's ambient, fill and
/// bounce, as a lightmap page of its own: no shadow edge crosses it); and
/// the sun's potential (grey: of the light the texel would hold with the
/// sun unblocked, the sun's share), for the masters that draw CE's ambient
/// and leave every sun shadow to Unreal. The ambient is its own page rather
/// than a share of the lightmap because two bilinear samples multiplied are
/// not the bilinear sample of the product: a share drew a bright rim along
/// every shadow's texel contour (Blood Gulch, 2026-10-08).
pub fn pages(draw: &mut Draw) -> (Vec<Page>, Vec<Page>, Vec<Page>, Vec<Page>) {
    let el = draw.elements;
    let k = draw.supersample.max(1);
    let per_texel = draw.occluders.is_some() && draw.lights.is_some() && draw.options.texel_direct;
    // The Gouraud part: everything the vertices hold, or only what the
    // texel pass does not redo.
    let value = |v: u32| -> V3 {
        let vert = &el.pool.vertices[v as usize];
        if per_texel {
            [
                vert.total[0] - vert.sun[0] - vert.placed[0],
                vert.total[1] - vert.sun[1] - vert.placed[1],
                vert.total[2] - vert.sun[2] - vert.placed[2],
            ]
        } else {
            vert.total
        }
    };
    let mut hi: Vec<Page> = draw.sizes.iter().map(|&(w, h)| Page::new((w * k).max(1), (h * k).max(1))).collect();
    for e in &el.elements {
        let m = &el.materials[e.material as usize];
        let Some(p) = hi.get_mut(m.page) else { continue };
        for patch in leaves(e) {
            match m.fixed {
                Some(c) => p.triangle(patch.uv1, [c; 3]),
                None => p.triangle(patch.uv1, [value(patch.v[0]), value(patch.v[1]), value(patch.v[2])]),
            }
        }
    }

    let mut sun_hi: Vec<Page> = Vec::new();
    let mut ambient_hi: Vec<Page> = Vec::new();
    let mut potential_hi: Vec<Page> = Vec::new();
    if per_texel {
        let occ = draw.occluders.unwrap();
        let (exterior, interior) = draw.lights.unwrap();
        let none = PlacedLights::default();
        let placed = draw.placed.unwrap_or(&none);
        let sets = draw.cluster_sets.unwrap_or(&[]);
        // Per page at the drawn resolution: every texel's position, normal
        // and light set from the patches covering it (inside a patch takes
        // that patch; only within reach of an edge, the first), then the
        // direct light at each in parallel, added before the box filter so
        // the shadow edge is antialiased like the rest.
        for (pi, page) in hi.iter_mut().enumerate() {
            let mut sample: Vec<Option<(V3, V3, Set, i32)>> = vec![None; page.width * page.height];
            let mut owned: Vec<bool> = vec![false; page.width * page.height];
            for e in &el.elements {
                if el.materials[e.material as usize].page != pi || el.materials[e.material as usize].fixed.is_some() {
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
                            sample[i] = Some((p, n, set, e.cluster));
                            owned[i] = inside;
                        }
                    });
                }
            }
            let texel_started = std::time::Instant::now();
            let mut on_gpu: Option<Vec<Option<Terms>>> = None;
            if let Some(g) = draw.gpu.as_deref_mut() {
                let at: Vec<usize> = (0..sample.len()).filter(|&i| sample[i].is_some()).collect();
                let list: Vec<(V3, V3, u32, i32)> = at
                    .iter()
                    .map(|&i| {
                        let (p, n, set, cluster) = sample[i].unwrap();
                        (p, n, if set == Set::Interior { 1 } else { 0 }, cluster)
                    })
                    .collect();
                match g.direct(&list, exterior, interior, placed, draw.options) {
                    Ok(v) => {
                        let mut d = vec![None; sample.len()];
                        for (&i, x) in at.iter().zip(v) {
                            d[i] = Some(x);
                        }
                        on_gpu = Some(d);
                    }
                    Err(e) => {
                        eprintln!("GPU per-texel pass failed ({e}); finishing on the CPU");
                        draw.gpu = None;
                    }
                }
            }
            let direct: Vec<Option<Terms>> = if let Some(d) = on_gpu {
                d
            } else {
                sample
                .par_iter()
                .map(|s| {
                    s.map(|(p, n, set, cluster)| {
                        let lights = match set {
                            Set::Exterior => exterior,
                            Set::Interior => interior,
                        };
                        direct_terms_placed(occ, lights, placed, cluster, p, n, draw.options)
                    })
                })
                .collect()
            };
            if let Some(t) = draw.texel_direct_seconds.as_deref_mut() {
                *t += texel_started.elapsed().as_secs_f64();
            }
            let mut sun = Page::new(page.width, page.height);
            let mut ambient = Page::new(page.width, page.height);
            let mut potential_page = Page::new(page.width, page.height);
            // A fixed material's texels: the constant on the ambient page
            // too, no sun on the companions.
            for e in &el.elements {
                let m = &el.materials[e.material as usize];
                if m.page != pi {
                    continue;
                }
                if let Some(c) = m.fixed {
                    for patch in leaves(e) {
                        ambient.triangle(patch.uv1, [c; 3]);
                        sun.triangle(patch.uv1, [[0.0; 3]; 3]);
                        potential_page.triangle(patch.uv1, [[0.0; 3]; 3]);
                    }
                }
            }
            for (i, d) in direct.iter().enumerate() {
                if let Some((all, sun_part, potential, vis)) = d {
                    // What the vertices hold here is the bounce, ambient and
                    // (per texel) the fill: the texel's light without the sun.
                    let without = add(page.rgb[i], [all[0] - sun_part[0], all[1] - sun_part[1], all[2] - sun_part[2]]);
                    let total = add(without, *sun_part);
                    let full = add(without, *potential);
                    // The sun's potential as a share of the page's values,
                    // clamped as tool.exe clamps (a sunlit texel saturates):
                    // the ambient page's value divided by (1 - G) is the
                    // texel's light with the sun unblocked. Neither side has
                    // a shadow edge, so the share interpolates cleanly.
                    let (lw, lf) = (luma(vertex_colour(without)), luma(vertex_colour(full)));
                    let g = if lf > 1e-6 { (1.0 - lw / lf).clamp(0.0, 1.0) } else { 0.0 };
                    page.rgb[i] = total;
                    page.covered[i] = true;
                    sun.rgb[i] = [*vis; 3];
                    sun.covered[i] = true;
                    ambient.rgb[i] = without;
                    ambient.covered[i] = true;
                    potential_page.rgb[i] = [g; 3];
                    potential_page.covered[i] = true;
                }
            }
            sun_hi.push(sun);
            ambient_hi.push(ambient);
            potential_hi.push(potential_page);
        }
    }
    let dilate = draw.dilate.max(1);
    let finish = |hi: &Vec<Page>, clamp: bool| -> Vec<Page> {
        hi.par_iter()
            .map(|p| {
                let mut p = if k > 1 { p.downsample(k) } else { Page { width: p.width, height: p.height, rgb: p.rgb.clone(), covered: p.covered.clone(), drawn: p.covered.clone() } };
                if clamp {
                    p.rgb.par_iter_mut().for_each(|c| *c = vertex_colour(*c));
                }
                p.drawn = p.covered.clone();
                p.dilate(dilate);
                p
            })
            .collect()
    };
    let ((out, sun), (ambient, potential)) =
        rayon::join(|| rayon::join(|| finish(&hi, true), || finish(&sun_hi, false)), || rayon::join(|| finish(&ambient_hi, true), || finish(&potential_hi, false)));
    (out, sun, ambient, potential)
}
