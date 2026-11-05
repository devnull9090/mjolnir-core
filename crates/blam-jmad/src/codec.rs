//! The frame codecs a resource member's data segments use.
//!
//! Every codec block opens with the same 0x20 byte header (see
//! `docs/jmad_format.md`). Static poses (codec 1) store one value per node;
//! the animated codecs store each node's frames back to back, rotations
//! first. Codecs 2 and 8 hold float rotations, codec 3 holds 16 bit ones, and
//! all three hold translations and scales as floats.

/// Bytes of the header every codec block starts with.
pub const HEADER: usize = 0x20;

/// One value per node.
pub const STATIC: u8 = 1;
/// Float rotations: the uncompressed copy every member carries.
pub const RAW: u8 = 2;
/// 16 bit rotations.
pub const PACKED: u8 = 3;
/// Laid out as [`RAW`], but found in the compressed slot.
pub const RAW_ALT: u8 = 8;

/// A rotation as stored: i, j, k, w.
pub type Quat = [f32; 4];
pub type Vec3 = [f32; 3];

/// A rotation component to its 16 bit form.
pub fn pack(c: f32) -> i16 {
    (c * 32767.0).round().clamp(-32767.0, 32767.0) as i16
}

/// A 16 bit rotation component to its float form.
pub fn unpack(c: i16) -> f32 {
    c as f32 / 32767.0
}

pub(crate) fn u32_at(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}

pub(crate) fn f32_at(b: &[u8], at: usize) -> f32 {
    f32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}

pub(crate) fn i16_at(b: &[u8], at: usize) -> i16 {
    i16::from_le_bytes(b[at..at + 2].try_into().unwrap())
}

fn floats<const N: usize>(b: &[u8], at: usize) -> [f32; N] {
    std::array::from_fn(|i| f32_at(b, at + 4 * i))
}

fn put_floats(out: &mut Vec<u8>, v: &[f32]) {
    for c in v {
        out.extend_from_slice(&c.to_le_bytes());
    }
}

struct Header {
    codec: u8,
    counts: [usize; 3],
    quality: [f32; 2],
    translations_at: usize,
    scales_at: usize,
    strides: [usize; 3],
}

impl Header {
    fn read(b: &[u8]) -> Option<Header> {
        if b.len() < HEADER {
            return None;
        }
        Some(Header {
            codec: b[0],
            counts: [b[1] as usize, b[2] as usize, b[3] as usize],
            quality: [f32_at(b, 4), f32_at(b, 8)],
            translations_at: u32_at(b, 12) as usize,
            scales_at: u32_at(b, 16) as usize,
            strides: [
                u32_at(b, 20) as usize,
                u32_at(b, 24) as usize,
                u32_at(b, 28) as usize,
            ],
        })
    }

    fn write(&self, out: &mut Vec<u8>) {
        out.push(self.codec);
        out.extend(self.counts.iter().map(|&c| c as u8));
        put_floats(out, &self.quality);
        for v in [
            self.translations_at,
            self.scales_at,
            self.strides[0],
            self.strides[1],
            self.strides[2],
        ] {
            out.extend_from_slice(&(v as u32).to_le_bytes());
        }
    }
}

/// A codec 1 block: the nodes that hold still.
#[derive(Debug, Clone, PartialEq)]
pub struct StaticPose {
    pub quality: [f32; 2],
    pub rotations: Vec<[i16; 4]>,
    pub translations: Vec<Vec3>,
    pub scales: Vec<f32>,
}

impl StaticPose {
    /// The block, or `None` if it is not laid out as a static pose.
    pub fn read(b: &[u8]) -> Option<StaticPose> {
        let h = Header::read(b)?;
        let [nr, nt, ns] = h.counts;
        let fits = h.codec == STATIC
            && h.strides == [0, 0, 0]
            && h.translations_at == HEADER + 8 * nr
            && h.scales_at == h.translations_at + 12 * nt
            && b.len() == h.scales_at + 4 * ns;
        fits.then(|| StaticPose {
            quality: h.quality,
            rotations: (0..nr)
                .map(|i| std::array::from_fn(|c| i16_at(b, HEADER + 8 * i + 2 * c)))
                .collect(),
            translations: (0..nt)
                .map(|i| floats(b, h.translations_at + 12 * i))
                .collect(),
            scales: (0..ns).map(|i| f32_at(b, h.scales_at + 4 * i)).collect(),
        })
    }

    pub fn write(&self) -> Vec<u8> {
        let (nr, nt, ns) = (
            self.rotations.len(),
            self.translations.len(),
            self.scales.len(),
        );
        let translations_at = HEADER + 8 * nr;
        let h = Header {
            codec: STATIC,
            counts: [nr, nt, ns],
            quality: self.quality,
            translations_at,
            scales_at: translations_at + 12 * nt,
            strides: [0, 0, 0],
        };
        let mut out = Vec::with_capacity(h.scales_at + 4 * ns);
        h.write(&mut out);
        for q in &self.rotations {
            for c in q {
                out.extend_from_slice(&c.to_le_bytes());
            }
        }
        for t in &self.translations {
            put_floats(&mut out, t);
        }
        put_floats(&mut out, &self.scales);
        out
    }
}

/// How an animated block stores its rotations, node-major.
#[derive(Debug, Clone, PartialEq)]
pub enum Rotations {
    Packed(Vec<[i16; 4]>),
    Float(Vec<Quat>),
}

impl Rotations {
    fn len(&self) -> usize {
        match self {
            Rotations::Packed(v) => v.len(),
            Rotations::Float(v) => v.len(),
        }
    }

    pub fn get(&self, i: usize) -> Quat {
        match self {
            Rotations::Packed(v) => v[i].map(unpack),
            Rotations::Float(v) => v[i],
        }
    }
}

/// A codec 2, 3 or 8 block: every frame of the nodes that move. Each list is
/// node-major, so `translations[k * frames + f]` is frame `f` of the `k`th
/// translating node.
#[derive(Debug, Clone, PartialEq)]
pub struct Frames {
    pub codec: u8,
    pub quality: [f32; 2],
    pub frames: usize,
    pub rotation_nodes: usize,
    pub translation_nodes: usize,
    pub scale_nodes: usize,
    pub rotations: Rotations,
    pub translations: Vec<Vec3>,
    pub scales: Vec<f32>,
}

impl Frames {
    /// The block for `frames` frames, or `None` if it is not laid out as one
    /// of the animated codecs this crate reads.
    pub fn read(b: &[u8], frames: usize) -> Option<Frames> {
        let h = Header::read(b)?;
        let width = match h.codec {
            RAW | RAW_ALT => 16,
            PACKED => 8,
            _ => return None,
        };
        let [nr, nt, ns] = h.counts;
        let fits = h.strides == [width * frames, 12 * frames, 4 * frames]
            && h.translations_at == HEADER + width * frames * nr
            && h.scales_at == h.translations_at + 12 * frames * nt
            && b.len() == h.scales_at + 4 * frames * ns;
        if !fits {
            return None;
        }
        let n = nr * frames;
        let rotations = if h.codec == PACKED {
            Rotations::Packed(
                (0..n)
                    .map(|i| std::array::from_fn(|c| i16_at(b, HEADER + 8 * i + 2 * c)))
                    .collect(),
            )
        } else {
            Rotations::Float((0..n).map(|i| floats(b, HEADER + 16 * i)).collect())
        };
        Some(Frames {
            codec: h.codec,
            quality: h.quality,
            frames,
            rotation_nodes: nr,
            translation_nodes: nt,
            scale_nodes: ns,
            rotations,
            translations: (0..nt * frames)
                .map(|i| floats(b, h.translations_at + 12 * i))
                .collect(),
            scales: (0..ns * frames)
                .map(|i| f32_at(b, h.scales_at + 4 * i))
                .collect(),
        })
    }

    pub fn write(&self) -> Vec<u8> {
        let width = if matches!(self.rotations, Rotations::Packed(_)) {
            8
        } else {
            16
        };
        debug_assert_eq!(self.rotations.len(), self.rotation_nodes * self.frames);
        let translations_at = HEADER + width * self.rotations.len();
        let h = Header {
            codec: self.codec,
            counts: [
                self.rotation_nodes,
                self.translation_nodes,
                self.scale_nodes,
            ],
            quality: self.quality,
            translations_at,
            scales_at: translations_at + 12 * self.translations.len(),
            strides: [width * self.frames, 12 * self.frames, 4 * self.frames],
        };
        let mut out = Vec::with_capacity(h.scales_at + 4 * self.scales.len());
        h.write(&mut out);
        match &self.rotations {
            Rotations::Packed(v) => {
                for q in v {
                    for c in q {
                        out.extend_from_slice(&c.to_le_bytes());
                    }
                }
            }
            Rotations::Float(v) => {
                for q in v {
                    put_floats(&mut out, q);
                }
            }
        }
        for t in &self.translations {
            put_floats(&mut out, t);
        }
        put_floats(&mut out, &self.scales);
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn moving(codec: u8, rotations: Rotations) -> Frames {
        Frames {
            codec,
            quality: [0.0, 0.625],
            frames: 2,
            rotation_nodes: 1,
            translation_nodes: 1,
            scale_nodes: 1,
            rotations,
            translations: vec![[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
            scales: vec![1.0, 1.5],
        }
    }

    #[test]
    fn a_static_pose_reads_back_as_written() {
        let pose = StaticPose {
            quality: [0.0, 0.0],
            rotations: vec![[0, 0, 0, 32767], [-32767, 1, 2, 3]],
            translations: vec![[0.25, 0.5, 0.75]],
            scales: vec![1.0, 2.0, 3.0],
        };
        let bytes = pose.write();
        assert_eq!(bytes.len(), HEADER + 16 + 12 + 12);
        assert_eq!(StaticPose::read(&bytes), Some(pose));
    }

    #[test]
    fn each_animated_codec_reads_back_as_written() {
        let float = Rotations::Float(vec![[0.0, 0.0, 0.0, 1.0], [0.5, 0.5, 0.5, 0.5]]);
        let packed = Rotations::Packed(vec![[0, 0, 0, 32767], [16384, 16384, 16384, 16384]]);
        for f in [
            moving(RAW, float.clone()),
            moving(RAW_ALT, float),
            moving(PACKED, packed),
        ] {
            assert_eq!(Frames::read(&f.write(), 2), Some(f));
        }
    }

    #[test]
    fn a_block_for_another_frame_count_is_refused() {
        let f = moving(RAW, Rotations::Float(vec![[0.0, 0.0, 0.0, 1.0]; 2]));
        assert_eq!(Frames::read(&f.write(), 3), None);
    }

    #[test]
    fn an_unknown_codec_is_not_read() {
        let mut b = moving(RAW, Rotations::Float(vec![[0.0, 0.0, 0.0, 1.0]; 2])).write();
        b[0] = 9;
        assert_eq!(Frames::read(&b, 2), None);
    }

    #[test]
    fn packing_survives_unpacking() {
        for c in [-32767i16, -1, 0, 1, 12345, 32767] {
            assert_eq!(pack(unpack(c)), c);
        }
    }
}
