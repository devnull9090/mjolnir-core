//! One resource member: the frames of one animation.
//!
//! A member is a 100 byte record (counts and seventeen segment sizes) and one
//! data blob holding the segments back to back. The segments this crate
//! understands are decoded into fields; the rest are carried as bytes, so that
//! reading a member and writing it again reproduces it exactly.

use crate::codec::{f32_at, u32_at, Frames, StaticPose};
use crate::Error;

/// Bytes of a member's fixed record.
pub const RECORD: usize = 100;
/// How many data segments a member can hold.
pub const SEGMENTS: usize = 17;

/// Segment numbers, in blob order. See `docs/jmad_format.md`: these describe
/// what the bytes were measured to hold.
pub mod seg {
    pub const STATIC_POSE: usize = 0;
    pub const ANIMATED: usize = 1;
    pub const STATIC_FLAGS: usize = 2;
    pub const ANIMATED_FLAGS: usize = 3;
    pub const MOVEMENT: usize = 4;
    pub const PILL: usize = 5;
    pub const RAW: usize = 6;
    pub const BLEND_SCREEN: usize = 7;
    pub const OBJECT_SPACE: usize = 13;
    pub const OBJECT_SPACE_MASK: usize = 15;
}

/// Segments whose bytes name nodes in ways this crate does not decode.
pub const NODE_BOUND_OPAQUE: [usize; 7] = [8, 9, 10, 11, 12, 14, 16];

/// Which nodes a pose covers, one bit a node, per channel.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct NodeFlags {
    pub rotation: Vec<u32>,
    pub translation: Vec<u32>,
    pub scale: Vec<u32>,
}

/// Words of a node bit vector.
pub fn words(nodes: usize) -> usize {
    nodes.div_ceil(32)
}

/// The set bits of a bit vector, ascending.
pub fn set_bits(words: &[u32]) -> Vec<usize> {
    (0..words.len() * 32)
        .filter(|&i| has_bit(words, i))
        .collect()
}

pub fn has_bit(words: &[u32], i: usize) -> bool {
    words.get(i / 32).is_some_and(|w| w >> (i % 32) & 1 != 0)
}

pub fn set_bit(words: &mut [u32], i: usize) {
    words[i / 32] |= 1 << (i % 32);
}

impl NodeFlags {
    pub fn new(nodes: usize) -> NodeFlags {
        let w = vec![0; words(nodes)];
        NodeFlags {
            rotation: w.clone(),
            translation: w.clone(),
            scale: w,
        }
    }

    fn read(b: &[u8], nodes: usize) -> Option<NodeFlags> {
        let w = words(nodes);
        if b.len() != 12 * w {
            return None;
        }
        let part = |k: usize| (0..w).map(|i| u32_at(b, 4 * (k * w + i))).collect();
        Some(NodeFlags {
            rotation: part(0),
            translation: part(1),
            scale: part(2),
        })
    }

    fn write(&self) -> Vec<u8> {
        self.rotation
            .iter()
            .chain(&self.translation)
            .chain(&self.scale)
            .flat_map(|w| w.to_le_bytes())
            .collect()
    }
}

/// A node's pose in the object's space on one frame: rotation (four floats),
/// position (three) and scale.
pub type ObjectPose = [f32; 8];

/// The object-space frames, for the nodes the mask names, node-major.
#[derive(Debug, Clone, PartialEq)]
pub struct ObjectSpace {
    pub frames: usize,
    pub poses: Vec<ObjectPose>,
    /// 256 bits, whatever the node count.
    pub mask: [u32; 8],
}

impl ObjectSpace {
    fn read(frames: &[u8], mask: &[u8]) -> Option<ObjectSpace> {
        if mask.len() != 32 || frames.len() < 4 {
            return None;
        }
        let nodes = u16::from_le_bytes([frames[0], frames[1]]) as usize;
        let count = u16::from_le_bytes([frames[2], frames[3]]) as usize;
        if frames.len() != 4 + 32 * nodes * count {
            return None;
        }
        let mask: [u32; 8] = std::array::from_fn(|i| u32_at(mask, 4 * i));
        if mask.iter().map(|w| w.count_ones() as usize).sum::<usize>() != nodes {
            return None;
        }
        let poses = (0..nodes * count)
            .map(|i| std::array::from_fn(|c| f32_at(frames, 4 + 32 * i + 4 * c)))
            .collect();
        Some(ObjectSpace {
            frames: count,
            poses,
            mask,
        })
    }

    pub fn nodes(&self) -> usize {
        self.mask.iter().map(|w| w.count_ones() as usize).sum()
    }

    fn write(&self) -> (Vec<u8>, Vec<u8>) {
        let mut out = Vec::with_capacity(4 + 32 * self.poses.len());
        out.extend_from_slice(&(self.nodes() as u16).to_le_bytes());
        out.extend_from_slice(&(self.frames as u16).to_le_bytes());
        for p in &self.poses {
            for c in p {
                out.extend_from_slice(&c.to_le_bytes());
            }
        }
        (
            out,
            self.mask.iter().flat_map(|w| w.to_le_bytes()).collect(),
        )
    }
}

/// The compressed slot: decoded, or kept as the bytes it was read from.
#[derive(Debug, Clone, PartialEq)]
pub enum Animated {
    Frames(Frames),
    Opaque(Vec<u8>),
}

impl Animated {
    /// The codec number the block opens with.
    pub fn codec(&self) -> u8 {
        match self {
            Animated::Frames(f) => f.codec,
            Animated::Opaque(b) => b.first().copied().unwrap_or(0),
        }
    }
}

/// One resource member.
#[derive(Debug, Clone, PartialEq)]
pub struct Member {
    pub animation_index: i32,
    pub checksum: u32,
    pub frames: i16,
    pub nodes: u8,
    pub movement_kind: u8,
    /// The last sixteen bytes of the record, after the blob's size.
    pub data_tail: [u8; 16],
    pub static_pose: StaticPose,
    pub animated: Animated,
    pub static_flags: NodeFlags,
    pub animated_flags: NodeFlags,
    /// The uncompressed copy of the animated data. Three shipped members have
    /// none.
    pub raw: Option<Frames>,
    pub object_space: Option<ObjectSpace>,
    /// Every other segment, as bytes. The slots of the decoded segments stay
    /// empty.
    pub opaque: [Vec<u8>; SEGMENTS],
}

impl Member {
    /// Read a member from its record and its blob.
    pub fn read(record: &[u8], blob: &[u8]) -> Result<Member, Error> {
        if record.len() != RECORD {
            return Err(Error::Format(format!(
                "member record is {} bytes",
                record.len()
            )));
        }
        let sizes: [usize; SEGMENTS] = std::array::from_fn(|i| u32_at(record, 12 + 4 * i) as usize);
        let total: usize = sizes.iter().sum();
        let declared = u32_at(record, 80) as usize;
        if total != declared || declared != blob.len() {
            return Err(Error::Format(format!(
                "member sizes add to {total}, the record says {declared}, the blob is {}",
                blob.len()
            )));
        }
        let mut parts: [&[u8]; SEGMENTS] = [&[]; SEGMENTS];
        let mut at = 0;
        for (part, &size) in parts.iter_mut().zip(&sizes) {
            *part = &blob[at..at + size];
            at += size;
        }
        let frames = i16::from_le_bytes([record[8], record[9]]);
        let nodes = record[10];
        let count = frames.max(0) as usize;
        let bad =
            |what: &str| Error::Format(format!("{what} of a {nodes} node, {frames} frame member"));

        let static_pose =
            StaticPose::read(parts[seg::STATIC_POSE]).ok_or_else(|| bad("static pose"))?;
        let static_flags = NodeFlags::read(parts[seg::STATIC_FLAGS], nodes as usize)
            .ok_or_else(|| bad("static flags"))?;
        let animated_flags = NodeFlags::read(parts[seg::ANIMATED_FLAGS], nodes as usize)
            .ok_or_else(|| bad("animated flags"))?;
        let animated = match Frames::read(parts[seg::ANIMATED], count) {
            Some(f) => Animated::Frames(f),
            None => Animated::Opaque(parts[seg::ANIMATED].to_vec()),
        };
        let raw = match parts[seg::RAW] {
            [] => None,
            b => Some(Frames::read(b, count).ok_or_else(|| bad("uncompressed copy"))?),
        };
        let object_space = match (parts[seg::OBJECT_SPACE], parts[seg::OBJECT_SPACE_MASK]) {
            ([], []) => None,
            (f, m) => Some(ObjectSpace::read(f, m).ok_or_else(|| bad("object-space frames"))?),
        };
        let mut opaque: [Vec<u8>; SEGMENTS] = Default::default();
        for (i, part) in parts.iter().enumerate() {
            let decoded = matches!(
                i,
                seg::STATIC_POSE
                    | seg::ANIMATED
                    | seg::STATIC_FLAGS
                    | seg::ANIMATED_FLAGS
                    | seg::RAW
                    | seg::OBJECT_SPACE
                    | seg::OBJECT_SPACE_MASK
            );
            if !decoded {
                opaque[i] = part.to_vec();
            }
        }
        Ok(Member {
            animation_index: u32_at(record, 0) as i32,
            checksum: u32_at(record, 4),
            frames,
            nodes,
            movement_kind: record[11],
            data_tail: record[84..100].try_into().unwrap(),
            static_pose,
            animated,
            static_flags,
            animated_flags,
            raw,
            object_space,
            opaque,
        })
    }

    /// The member's record and its blob.
    pub fn write(&self) -> (Vec<u8>, Vec<u8>) {
        let mut parts = self.opaque.clone();
        parts[seg::STATIC_POSE] = self.static_pose.write();
        parts[seg::ANIMATED] = match &self.animated {
            Animated::Frames(f) => f.write(),
            Animated::Opaque(b) => b.clone(),
        };
        parts[seg::STATIC_FLAGS] = self.static_flags.write();
        parts[seg::ANIMATED_FLAGS] = self.animated_flags.write();
        if let Some(raw) = &self.raw {
            parts[seg::RAW] = raw.write();
        }
        if let Some(os) = &self.object_space {
            (parts[seg::OBJECT_SPACE], parts[seg::OBJECT_SPACE_MASK]) = os.write();
        }
        let blob = parts.concat();
        let mut record = Vec::with_capacity(RECORD);
        record.extend_from_slice(&self.animation_index.to_le_bytes());
        record.extend_from_slice(&self.checksum.to_le_bytes());
        record.extend_from_slice(&self.frames.to_le_bytes());
        record.push(self.nodes);
        record.push(self.movement_kind);
        for p in &parts {
            record.extend_from_slice(&(p.len() as u32).to_le_bytes());
        }
        record.extend_from_slice(&(blob.len() as u32).to_le_bytes());
        record.extend_from_slice(&self.data_tail);
        (record, blob)
    }

    /// The segments that survive only as bytes, by number.
    pub fn opaque_segments(&self) -> Vec<usize> {
        (0..SEGMENTS)
            .filter(|&i| !self.opaque[i].is_empty())
            .collect()
    }
}
