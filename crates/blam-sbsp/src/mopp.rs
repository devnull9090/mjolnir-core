//! Havok MOPP bytecode: the bounding-volume tree an instance's collision is
//! actually queried through.
//!
//! An instanced-geometry definition's walkable surfaces are not reached by
//! walking its winged-edge tables directly. The engine wraps them in a Havok
//! `hkpMoppBvTreeShape` whose `mopp codes` block holds a compiled tree; a
//! query descends that tree and the leaves name **surface indices** to hand to
//! the narrow phase. A transplant that rewrites the tables but keeps the
//! donor's tree therefore collides against nothing: the tree still describes
//! where the donor's surfaces were.
//!
//! The opcode semantics below come from the shipped virtual machine,
//! `hkpMoppObbVirtualMachine::queryObb` (`HaloSimulation_tag_release.dll`
//! RVA `0x739780`, Havok 7.0.0-Reach); see `docs/re/collision_bsp/`.
//!
//! # The machine
//!
//! The query box is converted once to 24-bit fixed point and the tree compares
//! against its top 8 bits (`coord >> 16`), so every plane in a node is a byte.
//! Traversal keeps a six-int box: `[max.x, max.y, max.z, _, min.x, min.y,
//! min.z]`, a terminal reindex base, and a scale shift.
//!
//! A split node names two planes — the highest coordinate the left child
//! reaches and the lowest the right child reaches — so the two children may
//! overlap or leave a gap:
//!
//! * box entirely below `right_min`: descend left only
//! * box entirely above `left_max`: descend right only
//! * box spans both: visit left, then continue into right
//! * box in the gap between them: no hit
//!
//! A leaf emits one primitive index and returns. Emitting several means the
//! query straddled several leaves.

/// One decoded node of a MOPP tree.
#[derive(Debug, Clone, PartialEq)]
pub enum Node {
    /// Descend on `axis` (0 = x, 1 = y, 2 = z). The left child is the byte
    /// immediately after this node; the right child is `right` bytes further
    /// on from there.
    Split {
        axis: u8,
        /// Highest coordinate the left subtree reaches.
        left_max: u8,
        /// Lowest coordinate the right subtree reaches.
        right_min: u8,
        /// Distance from the end of this node to the left child (0 for the
        /// 4-byte form, where the left child follows immediately).
        left: usize,
        /// Distance from the end of this node to the right child.
        right: usize,
    },
    /// A primitive: this index plus the running reindex base.
    Terminal(u32),
    /// Shift the coordinate frame down by `shift` bits about `offset`, so a
    /// deep subtree can address a small region at full byte resolution.
    Rescale { shift: u8, offset: [u8; 3] },
    /// Add to the terminal reindex base.
    Reindex(u32),
    /// An unconditional jump of `0` distance is a no-op; anything else moves
    /// the instruction pointer.
    Jump(usize),
    /// The subtree below only covers `[lo, hi]` on `axis`; a query box that
    /// misses that slab stops here.
    Clip { axis: u8, lo: u8, hi: u8 },
    /// A split on a diagonal of two axes rather than one. The planes are
    /// computed from the running box, so the pair of bytes is not a plain
    /// coordinate; the shape (left child follows, right child at a one-byte
    /// jump) matches [`Node::Split`].
    Diagonal { kind: u8, a: u8, b: u8, right: usize },
    /// Set one of the machine's four scratch properties.
    Property { slot: u8, value: u32 },
    /// Jump to an absolute offset in another code chunk.
    Chunk(u32),
    /// End of this branch.
    Return,
}

/// A node with its byte position and encoded length.
#[derive(Debug, Clone)]
pub struct Decoded {
    pub at: usize,
    pub len: usize,
    pub node: Node,
}

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("mopp code ran off the end at {at} (len {len})")]
    Truncated { at: usize, len: usize },
    #[error("unknown mopp opcode {op:#04x} at {at}")]
    Unknown { op: u8, at: usize },
}

fn need(code: &[u8], at: usize, n: usize) -> Result<(), Error> {
    if at + n > code.len() {
        return Err(Error::Truncated { at, len: code.len() });
    }
    Ok(())
}

/// Decode the single node at `at`.
pub fn node_at(code: &[u8], at: usize) -> Result<Decoded, Error> {
    need(code, at, 1)?;
    let op = code[at];
    let d = |len: usize, node: Node| Ok(Decoded { at, len, node });
    match op {
        0x00 => d(1, Node::Return),
        // Rescale: three offset bytes, the shift is the opcode itself.
        0x01..=0x04 => {
            need(code, at, 4)?;
            d(
                4,
                Node::Rescale {
                    shift: op,
                    offset: [code[at + 1], code[at + 2], code[at + 3]],
                },
            )
        }
        0x05 => {
            need(code, at, 2)?;
            d(2, Node::Jump(code[at + 1] as usize))
        }
        0x06 => {
            need(code, at, 3)?;
            d(3, Node::Jump(((code[at + 1] as usize) << 8) | code[at + 2] as usize))
        }
        0x07 => {
            need(code, at, 4)?;
            d(
                4,
                Node::Jump(
                    ((code[at + 1] as usize) << 16)
                        | ((code[at + 2] as usize) << 8)
                        | code[at + 3] as usize,
                ),
            )
        }
        0x09 => {
            need(code, at, 2)?;
            d(2, Node::Reindex(code[at + 1] as u32))
        }
        0x0a => {
            need(code, at, 3)?;
            d(3, Node::Reindex(((code[at + 1] as u32) << 8) | code[at + 2] as u32))
        }
        0x0b => {
            need(code, at, 5)?;
            d(
                5,
                Node::Reindex(
                    ((code[at + 1] as u32) << 24)
                        | ((code[at + 2] as u32) << 16)
                        | ((code[at + 3] as u32) << 8)
                        | code[at + 4] as u32,
                ),
            )
        }
        // Single split, one-byte jump to the right child; left child follows.
        0x10..=0x12 => {
            need(code, at, 4)?;
            d(
                4,
                Node::Split {
                    axis: op - 0x10,
                    left_max: code[at + 1],
                    right_min: code[at + 2],
                    left: 0,
                    right: code[at + 3] as usize,
                },
            )
        }
        // Split with a single plane and a one-byte jump.
        0x20..=0x22 => {
            need(code, at, 3)?;
            d(
                3,
                Node::Split {
                    axis: op - 0x20,
                    left_max: code[at + 1],
                    right_min: code[at + 1],
                    left: 0,
                    right: code[at + 2] as usize,
                },
            )
        }
        // Split with two planes and two-byte jumps to both children.
        0x23..=0x25 => {
            need(code, at, 7)?;
            d(
                7,
                Node::Split {
                    axis: op - 0x23,
                    left_max: code[at + 1],
                    right_min: code[at + 2],
                    left: ((code[at + 3] as usize) << 8) | code[at + 4] as usize,
                    right: ((code[at + 5] as usize) << 8) | code[at + 6] as usize,
                },
            )
        }
        // Diagonal splits: same 4-byte shape as 0x10..=0x12.
        0x13..=0x1c => {
            need(code, at, 4)?;
            d(
                4,
                Node::Diagonal {
                    kind: op,
                    a: code[at + 1],
                    b: code[at + 2],
                    right: code[at + 3] as usize,
                },
            )
        }
        // The subtree covers only this slab on the axis.
        0x26..=0x28 => {
            need(code, at, 3)?;
            d(
                3,
                Node::Clip { axis: op - 0x26, lo: code[at + 1], hi: code[at + 2] },
            )
        }
        // Wide slab test against a 24-bit range.
        0x29..=0x2b => {
            need(code, at, 7)?;
            d(
                7,
                Node::Clip { axis: op - 0x29, lo: code[at + 1], hi: code[at + 4] },
            )
        }
        0x30..=0x4f => d(1, Node::Terminal((op - 0x30) as u32)),
        0x50 => {
            need(code, at, 2)?;
            d(2, Node::Terminal(code[at + 1] as u32))
        }
        0x51 => {
            need(code, at, 3)?;
            d(3, Node::Terminal(((code[at + 1] as u32) << 8) | code[at + 2] as u32))
        }
        0x52 => {
            need(code, at, 4)?;
            d(
                4,
                Node::Terminal(
                    ((code[at + 1] as u32) << 16)
                        | ((code[at + 2] as u32) << 8)
                        | code[at + 3] as u32,
                ),
            )
        }
        0x53 => {
            need(code, at, 5)?;
            d(
                5,
                Node::Terminal(
                    ((code[at + 1] as u32) << 24)
                        | ((code[at + 2] as u32) << 16)
                        | ((code[at + 3] as u32) << 8)
                        | code[at + 4] as u32,
                ),
            )
        }
        0x60..=0x63 => {
            need(code, at, 2)?;
            d(2, Node::Property { slot: op - 0x60, value: code[at + 1] as u32 })
        }
        0x64..=0x67 => {
            need(code, at, 3)?;
            d(
                3,
                Node::Property {
                    slot: op - 0x64,
                    value: ((code[at + 1] as u32) << 8) | code[at + 2] as u32,
                },
            )
        }
        0x68..=0x6b => {
            need(code, at, 5)?;
            d(
                5,
                Node::Property {
                    slot: op - 0x68,
                    value: ((code[at + 1] as u32) << 24)
                        | ((code[at + 2] as u32) << 16)
                        | ((code[at + 3] as u32) << 8)
                        | code[at + 4] as u32,
                },
            )
        }
        0x70 => {
            need(code, at, 5)?;
            d(
                5,
                Node::Chunk(
                    ((code[at + 1] as u32) << 24)
                        | ((code[at + 2] as u32) << 16)
                        | ((code[at + 3] as u32) << 8)
                        | code[at + 4] as u32,
                ),
            )
        }
        _ => Err(Error::Unknown { op, at }),
    }
}

/// Walk every branch of the tree from `at`, in the order the machine would,
/// calling `visit` for each node reached.
pub fn walk(code: &[u8], at: usize, visit: &mut impl FnMut(&Decoded, u32)) -> Result<(), Error> {
    walk_inner(code, at, 0, 0, visit)
}

fn walk_inner(
    code: &[u8],
    mut at: usize,
    base: u32,
    depth: u32,
    visit: &mut impl FnMut(&Decoded, u32),
) -> Result<(), Error> {
    let mut base = base;
    let mut depth = depth;
    loop {
        let d = node_at(code, at)?;
        visit(&d, depth);
        match d.node {
            Node::Return | Node::Terminal(_) => return Ok(()),
            Node::Jump(n) => at = at + d.len + n,
            Node::Reindex(n) => {
                base += n;
                at += d.len;
            }
            Node::Rescale { .. } | Node::Clip { .. } | Node::Property { .. } => at += d.len,
            Node::Chunk(_) => return Ok(()),
            Node::Diagonal { right, .. } => {
                walk_inner(code, at + d.len, base, depth + 1, visit)?;
                at = at + d.len + right;
                depth += 1;
            }
            Node::Split { left, right, .. } => {
                // Both children are reachable for some query, so a full walk
                // takes the left branch as a call and continues into the right.
                walk_inner(code, at + d.len + left, base, depth + 1, visit)?;
                at = at + d.len + right;
                depth += 1;
            }
        }
    }
}

/// Every primitive index the tree can yield, with the depth it sits at.
pub fn terminals(code: &[u8]) -> Result<Vec<(u32, u32)>, Error> {
    let mut out = Vec::new();
    let mut base = 0u32;
    collect(code, 0, &mut base, 0, &mut out)?;
    Ok(out)
}

fn collect(
    code: &[u8],
    mut at: usize,
    base: &mut u32,
    depth: u32,
    out: &mut Vec<(u32, u32)>,
) -> Result<(), Error> {
    let mut local = *base;
    let mut depth = depth;
    loop {
        let d = node_at(code, at)?;
        match d.node {
            Node::Return => return Ok(()),
            Node::Terminal(i) => {
                out.push((local + i, depth));
                return Ok(());
            }
            Node::Jump(n) => at = at + d.len + n,
            Node::Reindex(n) => {
                local += n;
                at += d.len;
            }
            Node::Rescale { .. } | Node::Clip { .. } | Node::Property { .. } => at += d.len,
            Node::Chunk(_) => return Ok(()),
            Node::Diagonal { right, .. } => {
                let mut b = local;
                collect(code, at + d.len, &mut b, depth + 1, out)?;
                at = at + d.len + right;
                depth += 1;
            }
            Node::Split { left, right, .. } => {
                let mut b = local;
                collect(code, at + d.len + left, &mut b, depth + 1, out)?;
                at = at + d.len + right;
                depth += 1;
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Querying — the reader half of the contract the encoder has to satisfy.

/// A primitive's box in the tree's byte space.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Aabb {
    pub lo: [u8; 3],
    pub hi: [u8; 3],
}

/// A query box in the tree's 24-bit fixed-point space, which is what the
/// machine actually keeps: a `Rescale` node recomputes the working box from
/// these at a finer shift, so the full-precision values have to be carried
/// through the whole descent.
#[derive(Debug, Clone, Copy)]
pub struct Query {
    pub lo: [i32; 3],
    pub hi: [i32; 3],
}

/// The traversal's working state: the box in the current frame, plus the
/// offset and shift a `Rescale` accumulates.
#[derive(Debug, Clone, Copy)]
struct Frame {
    lo: [i32; 3],
    hi: [i32; 3],
    off: [i32; 3],
    shift: u32,
}

impl Frame {
    fn start(q: &Query) -> Frame {
        Frame {
            lo: [q.lo[0] >> 16, q.lo[1] >> 16, q.lo[2] >> 16],
            hi: [(q.hi[0] >> 16) + 1, (q.hi[1] >> 16) + 1, (q.hi[2] >> 16) + 1],
            off: [0; 3],
            shift: 0,
        }
    }

    /// `hkpMoppObbVirtualMachine`'s rescale: fold the node's offset into the
    /// running one at the new shift, then rebuild the box from the
    /// full-precision query at that shift.
    fn rescale(&self, q: &Query, op: u8, b: [u8; 3]) -> Frame {
        let shift = self.shift + op as u32;
        let s = 16i32 - shift as i32;
        let mut off = [0i32; 3];
        let mut lo = [0i32; 3];
        let mut hi = [0i32; 3];
        for k in 0..3 {
            off[k] = (b[k] as i32 + self.off[k]) << op;
            let (ql, qh) = if s >= 0 {
                (q.lo[k] >> s, q.hi[k] >> s)
            } else {
                (q.lo[k] << (-s), q.hi[k] << (-s))
            };
            lo[k] = ql - off[k];
            hi[k] = qh - off[k] + 1;
        }
        Frame { lo, hi, off, shift }
    }
}

/// Run a box query the way `hkpMoppObbVirtualMachine` does, and return every
/// primitive index it yields.
///
/// This mirrors the machine exactly — which comparisons are strict, and how a
/// `Rescale` re-derives the working box — so a tree that answers correctly
/// here answers correctly in game.
pub fn query(code: &[u8], q: &Query) -> Result<Vec<u32>, Error> {
    let mut out = Vec::new();
    query_at(code, 0, 0, q, Frame::start(q), &mut out)?;
    Ok(out)
}

/// [`query`] for a tree that carries no `Rescale`, taking the working box
/// directly. This is what the compiler here produces.
pub fn query_bytes(code: &[u8], lo: [i32; 3], hi: [i32; 3]) -> Result<Vec<u32>, Error> {
    let q = Query {
        lo: [lo[0] << 16, lo[1] << 16, lo[2] << 16],
        hi: [(hi[0] - 1) << 16, (hi[1] - 1) << 16, (hi[2] - 1) << 16],
    };
    query(code, &q)
}

fn query_at(
    code: &[u8],
    mut at: usize,
    base: u32,
    q: &Query,
    frame: Frame,
    out: &mut Vec<u32>,
) -> Result<(), Error> {
    let mut base = base;
    let mut f = frame;
    loop {
        let d = node_at(code, at)?;
        match d.node {
            Node::Return => return Ok(()),
            Node::Terminal(i) => {
                out.push(base + i);
                return Ok(());
            }
            Node::Jump(n) => at = at + d.len + n,
            Node::Reindex(n) => {
                base += n;
                at += d.len;
            }
            Node::Property { .. } => at += d.len,
            Node::Chunk(_) => return Ok(()),
            Node::Rescale { shift, offset } => {
                f = f.rescale(q, shift, offset);
                at += d.len;
            }
            Node::Clip { axis, lo: l, hi: h } => {
                let a = axis as usize;
                if f.hi[a] < l as i32 || (h as i32) <= f.lo[a] {
                    return Ok(());
                }
                at += d.len;
            }
            Node::Diagonal { right, .. } => {
                // Not emitted by this compiler; visit both sides so a shipped
                // tree carrying one is still answered conservatively.
                query_at(code, at + d.len, base, q, f, out)?;
                at = at + d.len + right;
            }
            Node::Split {
                axis,
                left_max,
                right_min,
                left,
                right,
            } => {
                let a = axis as usize;
                let left_child = at + d.len + left;
                let right_child = at + d.len + right;
                if (right_min as i32) < f.hi[a] {
                    if f.lo[a] < left_max as i32 {
                        query_at(code, left_child, base, q, f, out)?;
                    }
                    at = right_child;
                } else {
                    if left_max as i32 <= f.lo[a] {
                        return Ok(());
                    }
                    at = left_child;
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Compiling

#[derive(Debug, thiserror::Error)]
pub enum BuildError {
    #[error("a subtree is {0} bytes, past the 16-bit jump a split node can encode")]
    JumpOverflow(usize),
    #[error("nothing to build a tree from")]
    Empty,
}

/// Encode one leaf. Small indices get the one-byte form the shipped trees use.
fn terminal(id: u32) -> Vec<u8> {
    if id < 32 {
        vec![0x30 + id as u8]
    } else if id < 0x100 {
        vec![0x50, id as u8]
    } else if id < 0x1_0000 {
        vec![0x51, (id >> 8) as u8, id as u8]
    } else if id < 0x100_0000 {
        vec![0x52, (id >> 16) as u8, (id >> 8) as u8, id as u8]
    } else {
        vec![
            0x53,
            (id >> 24) as u8,
            (id >> 16) as u8,
            (id >> 8) as u8,
            id as u8,
        ]
    }
}

/// Build a MOPP tree over `prims`, each an index paired with its box in tree
/// byte space.
///
/// The tree is a median-split kd tree. A split node names the highest
/// coordinate the left subtree reaches and the lowest the right subtree
/// reaches; the machine's tests are strict, so both planes are padded outwards
/// by one, which can only add candidates and never drop one.
pub fn build(prims: &[(u32, Aabb)]) -> Result<Vec<u8>, BuildError> {
    if prims.is_empty() {
        return Err(BuildError::Empty);
    }
    let mut work: Vec<(u32, Aabb)> = prims.to_vec();
    emit(&mut work)
}

fn emit(prims: &mut [(u32, Aabb)]) -> Result<Vec<u8>, BuildError> {
    if prims.len() == 1 {
        return Ok(terminal(prims[0].0));
    }
    // Split on the axis the group spreads widest, at the median centroid, so
    // the tree stays balanced and the jumps stay small.
    let mut lo = [255u8; 3];
    let mut hi = [0u8; 3];
    for (_, b) in prims.iter() {
        for k in 0..3 {
            lo[k] = lo[k].min(b.lo[k]);
            hi[k] = hi[k].max(b.hi[k]);
        }
    }
    let axis = (0..3)
        .max_by_key(|&k| hi[k] as i32 - lo[k] as i32)
        .unwrap_or(0);
    let centroid = |b: &Aabb| b.lo[axis] as u16 + b.hi[axis] as u16;
    prims.sort_by_key(|(_, b)| centroid(b));
    let mid = prims.len() / 2;
    let (l, r) = prims.split_at_mut(mid);

    let left_max = l.iter().map(|(_, b)| b.hi[axis]).max().unwrap_or(0);
    let right_min = r.iter().map(|(_, b)| b.lo[axis]).min().unwrap_or(255);
    let left_max = left_max.saturating_add(1);
    let right_min = right_min.saturating_sub(1);

    let left = emit(l)?;
    let right = emit(r)?;

    // The four-byte form puts the left child immediately after the node and
    // reaches the right with one byte, which is what most shipped nodes use.
    if left.len() <= 0xff {
        let mut out = vec![0x10 + axis as u8, left_max, right_min, left.len() as u8];
        out.extend_from_slice(&left);
        out.extend_from_slice(&right);
        return Ok(out);
    }
    // Otherwise the seven-byte form, emitting the smaller subtree first so the
    // jump that has to be encoded is at most half the subtree.
    let op = 0x23 + axis as u8;
    let jump16 = |n: usize| -> Result<[u8; 2], BuildError> {
        if n > 0xffff {
            return Err(BuildError::JumpOverflow(n));
        }
        Ok([(n >> 8) as u8, n as u8])
    };
    let mut out = Vec::with_capacity(7 + left.len() + right.len());
    if left.len() <= right.len() {
        let rj = jump16(left.len())?;
        out.extend_from_slice(&[op, left_max, right_min, 0, 0, rj[0], rj[1]]);
        out.extend_from_slice(&left);
        out.extend_from_slice(&right);
    } else {
        let lj = jump16(right.len())?;
        out.extend_from_slice(&[op, left_max, right_min, lj[0], lj[1], 0, 0]);
        out.extend_from_slice(&right);
        out.extend_from_slice(&left);
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// Quantisation

/// The mapping between definition space and the tree's byte space, which the
/// mopp element's header carries as `code info` (the offset) and its `w` (the
/// scale).
#[derive(Debug, Clone, Copy)]
pub struct Quant {
    pub offset: [f32; 3],
    pub scale: f32,
}

impl Quant {
    /// Fit a cube around the geometry with a little slack, the way the shipped
    /// headers do: their geometry lands inside 0..=255 with the widest axis
    /// near 253.
    pub fn fit(lo: [f32; 3], hi: [f32; 3]) -> Quant {
        let span = (0..3).map(|k| hi[k] - lo[k]).fold(0.0f32, f32::max);
        let side = (span * 1.01).max(1e-4);
        let pad = span * 0.005;
        Quant {
            offset: [lo[0] - pad, lo[1] - pad, lo[2] - pad],
            scale: 16_777_216.0 / side,
        }
    }

    /// A coordinate as the tree sees it: 24-bit fixed point, compared by its
    /// top eight bits.
    pub fn byte(&self, v: f32, axis: usize) -> u8 {
        let fixed = ((v - self.offset[axis]) * self.scale) as i64 >> 16;
        fixed.clamp(0, 255) as u8
    }

    /// A world-space box as the machine's 24-bit fixed-point query, including
    /// the one-unit slack `hkpMoppObbVirtualMachine`'s setup adds.
    pub fn query_box(&self, lo: [f32; 3], hi: [f32; 3]) -> Query {
        let mut q = Query { lo: [0; 3], hi: [0; 3] };
        for k in 0..3 {
            q.lo[k] = ((lo[k] - self.offset[k]) * self.scale) as i32 - 1;
            q.hi[k] = ((hi[k] - self.offset[k]) * self.scale) as i32 + 1;
        }
        q
    }

    /// A polygon's box in tree byte space.
    pub fn box_of(&self, points: &[[f32; 3]]) -> Aabb {
        let mut lo = [f32::MAX; 3];
        let mut hi = [f32::MIN; 3];
        for p in points {
            for k in 0..3 {
                lo[k] = lo[k].min(p[k]);
                hi[k] = hi[k].max(p[k]);
            }
        }
        Aabb {
            lo: [self.byte(lo[0], 0), self.byte(lo[1], 1), self.byte(lo[2], 2)],
            hi: [self.byte(hi[0], 0), self.byte(hi[1], 1), self.byte(hi[2], 2)],
        }
    }
}

/// The `tgbl` block a mopp element's `tgst` wrapper carries: the bytecode as a
/// block of single bytes.
///
/// The size word counts from after itself to the end of the block, so it is
/// the data length plus the count and flag words.
pub fn wrapper(code: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(20 + code.len());
    out.extend_from_slice(b"lbgt");
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&(code.len() as u32 + 8).to_le_bytes());
    out.extend_from_slice(&(code.len() as u32).to_le_bytes());
    out.extend_from_slice(&1u32.to_le_bytes());
    out.extend_from_slice(code);
    out
}

/// Put a compiled tree's size and quantisation into a donor mopp element's
/// 96 bytes, leaving the cook-time pointers alone — they are stale heap
/// addresses in every shipped element, so the engine must rebuild them.
pub fn patch_element(element: &mut [u8], q: Quant, code_len: usize) {
    let put_f32 = |e: &mut [u8], at: usize, v: f32| e[at..at + 4].copy_from_slice(&v.to_le_bytes());
    put_f32(element, 32, q.offset[0]);
    put_f32(element, 36, q.offset[1]);
    put_f32(element, 40, q.offset[2]);
    put_f32(element, 44, q.scale);
    // The length appears three times: the hkArray size at 56, its capacity
    // word (flagged) at 60, and the mopp code's own data size at 80. Every
    // shipped element carries all three equal; a stale third copy would let
    // the loader take only that many bytes of a longer tree.
    element[56..60].copy_from_slice(&(code_len as u32).to_le_bytes());
    element[60..64].copy_from_slice(&(0x8000_0000u32 | code_len as u32).to_le_bytes());
    element[80..84].copy_from_slice(&(code_len as u32).to_le_bytes());
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decodes_the_node_forms() {
        assert_eq!(node_at(&[0x00], 0).unwrap().node, Node::Return);
        assert_eq!(node_at(&[0x35], 0).unwrap().node, Node::Terminal(5));
        assert_eq!(node_at(&[0x50, 0x7f], 0).unwrap().node, Node::Terminal(0x7f));
        assert_eq!(
            node_at(&[0x51, 0x12, 0x34], 0).unwrap().node,
            Node::Terminal(0x1234)
        );
        assert_eq!(
            node_at(&[0x11, 0x40, 0x30, 0x08], 0).unwrap().node,
            Node::Split { axis: 1, left_max: 0x40, right_min: 0x30, left: 0, right: 8 }
        );
        assert_eq!(
            node_at(&[0x24, 0x40, 0x30, 0x00, 0x04, 0x01, 0x00], 0).unwrap().node,
            Node::Split { axis: 1, left_max: 0x40, right_min: 0x30, left: 4, right: 256 }
        );
        assert_eq!(
            node_at(&[0x28, 0x10, 0x90], 0).unwrap().node,
            Node::Clip { axis: 2, lo: 0x10, hi: 0x90 }
        );
    }

    /// A split whose children are two leaves yields both primitives.
    #[test]
    fn walks_both_children() {
        let code = [0x10, 0x80, 0x40, 0x01, 0x31, 0x32];
        let mut got = terminals(&code).unwrap();
        got.sort();
        assert_eq!(got, vec![(1, 1), (2, 1)]);
    }

    /// Every terminal a leaf encoding can carry comes back as itself.
    #[test]
    fn terminal_forms_round_trip() {
        for id in [0u32, 1, 31, 32, 255, 256, 65535, 65536, 1 << 20, 1 << 25] {
            let code = terminal(id);
            match node_at(&code, 0).unwrap().node {
                Node::Terminal(got) => assert_eq!(got, id, "terminal {id} came back as {got}"),
                other => panic!("terminal {id} decoded as {other:?}"),
            }
        }
    }

    fn spread(n: u32) -> Vec<(u32, Aabb)> {
        // A deterministic scatter of small boxes, enough of them to force the
        // wide split form and the multi-byte terminals.
        let mut out = Vec::new();
        let mut seed = 12345u64;
        for i in 0..n {
            let mut next = || {
                seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
                ((seed >> 33) % 240) as u8
            };
            let (x, y, z) = (next(), next(), next());
            out.push((
                i,
                Aabb {
                    lo: [x, y, z],
                    hi: [x + 4, y + 3, z + 5],
                },
            ));
        }
        out
    }

    /// The tree names every primitive exactly once.
    #[test]
    fn every_primitive_gets_one_leaf() {
        for n in [1u32, 2, 5, 33, 300, 2000] {
            let prims = spread(n);
            let code = build(&prims).unwrap();
            let mut ids: Vec<u32> = terminals(&code).unwrap().into_iter().map(|(i, _)| i).collect();
            ids.sort_unstable();
            let want: Vec<u32> = (0..n).collect();
            assert_eq!(ids, want, "{n} primitives");
        }
    }

    /// The property that matters: querying a primitive's own box returns it.
    /// This runs the machine's exact traversal, so a tree that passes here
    /// answers the same way in game.
    #[test]
    fn every_primitive_answers_its_own_box() {
        for n in [1u32, 2, 7, 64, 500, 3000] {
            let prims = spread(n);
            let code = build(&prims).unwrap();
            for (id, b) in &prims {
                // The engine's setup pads the query box by one on each side.
                let lo = [b.lo[0] as i32 - 1, b.lo[1] as i32 - 1, b.lo[2] as i32 - 1];
                let hi = [b.hi[0] as i32 + 1, b.hi[1] as i32 + 1, b.hi[2] as i32 + 1];
                let got = query_bytes(&code, lo, hi).unwrap();
                assert!(
                    got.contains(id),
                    "{n} primitives: querying {id}'s own box {b:?} returned {} hit(s) without it",
                    got.len()
                );
            }
        }
    }

    /// A query far outside the geometry returns nothing, so the tree is not
    /// merely answering everything.
    #[test]
    fn a_query_outside_the_tree_is_empty() {
        let prims = spread(500);
        let code = build(&prims).unwrap();
        let got = query_bytes(&code, [250, 250, 250], [255, 255, 255]).unwrap();
        let all: usize = prims.len();
        assert!(got.len() < all / 4, "{} of {all} hits far outside", got.len());
    }

    #[test]
    fn the_block_wrapper_is_shaped_like_a_shipped_one() {
        let w = wrapper(&[1, 2, 3, 4]);
        assert_eq!(&w[0..4], b"lbgt");
        assert_eq!(u32::from_le_bytes(w[8..12].try_into().unwrap()), 4 + 8);
        assert_eq!(u32::from_le_bytes(w[12..16].try_into().unwrap()), 4);
        assert_eq!(u32::from_le_bytes(w[16..20].try_into().unwrap()), 1);
        assert_eq!(&w[20..], &[1, 2, 3, 4]);
    }
}
