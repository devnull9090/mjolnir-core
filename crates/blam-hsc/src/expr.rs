//! The expression datum: one node of a compiled script.
//!
//! `hs syntax datums` is a Blam datum array, not a plain list. Nodes address
//! each other by handle rather than by index, and the array is sparse: slots
//! the compiler freed stay in place as fill. Walking it as a `Vec` and trusting
//! every slot would decode garbage, so [`Expression::is_free`] is the gate every
//! reader goes through.

use crate::Error;

/// On-disk width of one expression datum, from `hs_syntax_datum_block`.
pub const DATUM_SIZE: usize = 24;

/// The half-word the cooker leaves in slots no expression occupies.
///
/// Free slots read as `0xBA` fill with a zeroed leading generation. Freeness is
/// tested on the fill rather than on `generation == 0` because the fill is what the
/// shipped data actually shows, across all 272,190 datums in the campaign.
const FREE_FILL: u16 = 0xBABA;

/// A reference to another datum: index in the low half, generation in the high
/// half.
///
/// The generation is what makes a stale handle detectable — an index alone
/// would silently resolve to whatever later took the slot. Readers here compare
/// it to the target's own generation and treat a mismatch as a broken link.
///
/// Blam tooling calls this half-word the datum's *salt*, and the shipped
/// definitions call the field it lives in `datum header`. It is named
/// `generation` here because that is what it does, and because "salt" invites
/// exactly one wrong reading: this has nothing to do with cryptography. It is
/// an ABA counter for a slab allocator — never hashed, never secret, and
/// reproduced verbatim when a tag is written back.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct DatumHandle(pub u32);

impl DatumHandle {
    /// The handle that terminates a sibling chain.
    pub const NULL: DatumHandle = DatumHandle(u32::MAX);

    pub fn new(index: u16, generation: u16) -> Self {
        DatumHandle(((generation as u32) << 16) | index as u32)
    }

    pub fn index(self) -> usize {
        (self.0 & 0xFFFF) as usize
    }

    pub fn generation(self) -> u16 {
        (self.0 >> 16) as u16
    }

    pub fn is_null(self) -> bool {
        self.0 == u32::MAX
    }
}

impl std::fmt::Display for DatumHandle {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        if self.is_null() {
            f.write_str("null")
        } else {
            write!(f, "{}:{:04x}", self.index(), self.generation())
        }
    }
}

/// What a node *is*, as opposed to what it evaluates to.
///
/// The numbering is the engine's, and matches the Reach-era values Assembly
/// documents. Halo Campaign Evolved shares the numbering even though its
/// function opcodes are entirely its own.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExpressionType {
    /// A call: `data` points at the first child, which names the callee.
    Group,
    /// A leaf. Either the name of the enclosing group's callee, or a literal.
    Expression,
    /// A call to a script in this scenario; `opcode` indexes `scripts`.
    ScriptReference,
    /// A read of a scenario global; `opcode` indexes `globals`.
    GlobalsReference,
    /// A read of the enclosing script's parameter.
    ParameterReference,
    /// A value the engine uses that this crate does not model yet. Carried
    /// through rather than dropped, so a round-trip stays lossless.
    Other(u16),
}

impl ExpressionType {
    pub fn from_raw(v: u16) -> Self {
        match v {
            8 => ExpressionType::Group,
            9 => ExpressionType::Expression,
            10 => ExpressionType::ScriptReference,
            13 => ExpressionType::GlobalsReference,
            29 => ExpressionType::ParameterReference,
            other => ExpressionType::Other(other),
        }
    }

    pub fn to_raw(self) -> u16 {
        match self {
            ExpressionType::Group => 8,
            ExpressionType::Expression => 9,
            ExpressionType::ScriptReference => 10,
            ExpressionType::GlobalsReference => 13,
            ExpressionType::ParameterReference => 29,
            ExpressionType::Other(v) => v,
        }
    }

    /// Whether `data` holds a handle to this node's first child rather than a
    /// literal value.
    pub fn has_children(self) -> bool {
        matches!(
            self,
            ExpressionType::Group | ExpressionType::ScriptReference
        )
    }
}

/// One node of a compiled script.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Expression {
    /// This node's own generation, paired with its array index to form its handle.
    pub generation: u16,
    /// For a call, the engine function or script this invokes. For a global or
    /// parameter reference, the index of what is read. Otherwise unused.
    pub opcode: u16,
    /// Index into the scenario's value-type enum: what this evaluates to.
    pub value_type: u16,
    pub expression_type: ExpressionType,
    /// The next sibling in the enclosing call's argument list.
    pub next: DatumHandle,
    /// Byte offset into `script string data` of this node's name or string
    /// literal.
    pub string_offset: u32,
    /// A child handle for a call, otherwise the literal payload. Interpreting
    /// it needs `value_type`, so it is kept raw here.
    pub data: u32,
    /// Line in the source file this came from, 1-based.
    pub line: u16,
    /// A trailing half-word the definitions name `HMM` and that is zero in
    /// every shipped datum. Carried so a rewrite reproduces the original bytes.
    pub tail: u16,
}

impl Expression {
    pub fn parse(bytes: &[u8]) -> Result<Self, Error> {
        if bytes.len() < DATUM_SIZE {
            return Err(Error::DatumSize(bytes.len()));
        }
        let u16at = |o: usize| u16::from_le_bytes([bytes[o], bytes[o + 1]]);
        let u32at =
            |o: usize| u32::from_le_bytes([bytes[o], bytes[o + 1], bytes[o + 2], bytes[o + 3]]);
        Ok(Expression {
            generation: u16at(0),
            opcode: u16at(2),
            value_type: u16at(4),
            expression_type: ExpressionType::from_raw(u16at(6)),
            next: DatumHandle(u32at(8)),
            string_offset: u32at(12),
            data: u32at(16),
            line: u16at(20),
            tail: u16at(22),
        })
    }

    pub fn write(&self, out: &mut [u8]) -> Result<(), Error> {
        if out.len() < DATUM_SIZE {
            return Err(Error::DatumSize(out.len()));
        }
        out[0..2].copy_from_slice(&self.generation.to_le_bytes());
        out[2..4].copy_from_slice(&self.opcode.to_le_bytes());
        out[4..6].copy_from_slice(&self.value_type.to_le_bytes());
        out[6..8].copy_from_slice(&self.expression_type.to_raw().to_le_bytes());
        out[8..12].copy_from_slice(&self.next.0.to_le_bytes());
        out[12..16].copy_from_slice(&self.string_offset.to_le_bytes());
        out[16..20].copy_from_slice(&self.data.to_le_bytes());
        out[20..22].copy_from_slice(&self.line.to_le_bytes());
        out[22..24].copy_from_slice(&self.tail.to_le_bytes());
        Ok(())
    }

    /// A slot no expression occupies.
    pub fn is_free(&self) -> bool {
        self.opcode == FREE_FILL
            && self.value_type == FREE_FILL
            && self.expression_type == ExpressionType::Other(FREE_FILL)
    }

    /// The handle of this node's first child, if it has children.
    pub fn first_child(&self) -> Option<DatumHandle> {
        if !self.expression_type.has_children() {
            return None;
        }
        let h = DatumHandle(self.data);
        (!h.is_null()).then_some(h)
    }
}

/// The scenario's value-type enum, read from the tag's own definitions.
///
/// The engine identifies a value's type by its position in this list, and the
/// list is per-build: a game update that inserts a type shifts every later one.
/// Reading the names from the tag rather than hard-coding them means a new
/// build changes nothing here. Semantics are still keyed by name — see
/// [`ValueTypes::is_real`] and friends — because a name means the same thing
/// wherever it lands.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ValueTypes {
    names: Vec<String>,
}

impl ValueTypes {
    pub fn new(names: Vec<String>) -> Self {
        ValueTypes { names }
    }

    pub fn name_of(&self, index: u16) -> Option<&str> {
        self.names.get(index as usize).map(String::as_str)
    }

    pub fn index_of(&self, name: &str) -> Option<u16> {
        self.names.iter().position(|n| n == name).map(|i| i as u16)
    }

    pub fn names(&self) -> &[String] {
        &self.names
    }

    pub fn is_empty(&self) -> bool {
        self.names.is_empty()
    }

    /// The type a node carries when it names the function its parent calls.
    pub fn function_name(&self) -> Option<u16> {
        self.index_of("function_name")
    }

    pub fn is_real(&self, index: u16) -> bool {
        self.name_of(index) == Some("real")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The first live datum of `a30`, byte for byte as shipped: the `begin` of
    /// the mission's startup script.
    const A30_GROUP: [u8; DATUM_SIZE] = [
        0x77, 0xe3, 0x9c, 0x01, 0x04, 0x00, 0x08, 0x00, 0x08, 0x00, 0x7b, 0xe3, 0x00, 0x01, 0x00,
        0x00, 0x05, 0x00, 0x78, 0xe3, 0x05, 0x00, 0x00, 0x00,
    ];

    #[test]
    fn a_group_datum_decodes_to_its_parts() {
        let e = Expression::parse(&A30_GROUP).unwrap();
        assert_eq!(e.generation, 0xe377);
        assert_eq!(e.opcode, 0x019c);
        assert_eq!(e.expression_type, ExpressionType::Group);
        assert_eq!(e.next, DatumHandle::new(8, 0xe37b));
        assert_eq!(e.string_offset, 256);
        assert_eq!(e.line, 5);
        assert_eq!(e.tail, 0);
        // A group points at the child that names its callee.
        assert_eq!(e.first_child(), Some(DatumHandle::new(5, 0xe378)));
    }

    #[test]
    fn a_datum_rewrites_to_the_bytes_it_came_from() {
        let e = Expression::parse(&A30_GROUP).unwrap();
        let mut out = [0u8; DATUM_SIZE];
        e.write(&mut out).unwrap();
        assert_eq!(out, A30_GROUP);
    }

    #[test]
    fn fill_slots_are_free_and_live_ones_are_not() {
        let mut fill = [0xBAu8; DATUM_SIZE];
        fill[0] = 0;
        fill[1] = 0;
        assert!(Expression::parse(&fill).unwrap().is_free());
        assert!(!Expression::parse(&A30_GROUP).unwrap().is_free());
    }

    #[test]
    fn a_handle_splits_into_index_and_generation() {
        let h = DatumHandle::new(5, 0xe378);
        assert_eq!(h.0, 0xe378_0005);
        assert_eq!(h.index(), 5);
        assert_eq!(h.generation(), 0xe378);
        assert!(!h.is_null());
        assert!(DatumHandle::NULL.is_null());
    }

    #[test]
    fn only_calls_carry_children() {
        assert!(ExpressionType::Group.has_children());
        assert!(ExpressionType::ScriptReference.has_children());
        assert!(!ExpressionType::Expression.has_children());
        assert!(!ExpressionType::GlobalsReference.has_children());
    }

    #[test]
    fn an_unmodelled_expression_type_survives_a_round_trip() {
        let t = ExpressionType::from_raw(41);
        assert_eq!(t, ExpressionType::Other(41));
        assert_eq!(t.to_raw(), 41);
    }
}
