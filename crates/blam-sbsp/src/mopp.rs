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
    }

    /// A split whose children are two leaves yields both primitives.
    #[test]
    fn walks_both_children() {
        // 0x10 split, left child at +4 (terminal 1), right at +4+1 (terminal 2)
        let code = [0x10, 0x80, 0x40, 0x01, 0x31, 0x32];
        let mut got = terminals(&code).unwrap();
        got.sort();
        assert_eq!(got, vec![(1, 1), (2, 1)]);
    }
}
