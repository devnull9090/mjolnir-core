//! Blam script (HSC) carried by Halo Campaign Evolved `scenario` tags.
//!
//! A shipped scenario carries the mission's scripting twice over. The
//! `source files` block holds the original `.hsc` text, comments and all, and
//! `hs syntax datums` holds what the compiler made of it: a flat array of
//! 24-byte expression nodes threaded into trees by datum handle. The game runs
//! the second one, so editing a script means rewriting the tree, not the text.
//!
//! This crate reads both, renders the tree back to source, and compiles source
//! back to a tree. It reads the scenario through [`blam_tag`] rather than
//! parsing bytes itself, so it inherits that crate's guarantee that a decoded
//! tag re-encodes to the same bytes.
//!
//! Nothing here embeds game content. The expression layout and the meaning of
//! the value-type enum come from the tag's own `blay` definitions, the same way
//! [`blam_tag`] recovers field definitions — see `docs/tag_body_format.md`.

pub mod compile;
pub mod corpus;
pub mod decompile;
pub mod emit;
pub mod expr;
pub mod lex;
pub mod parse;
pub mod read;

pub use compile::{Compiled, Compiler, Diagnostic, Severity};
pub use corpus::{CorpusBuilder, FunctionDef, ScriptCorpus};
pub use decompile::Decompiler;
pub use expr::{DatumHandle, Expression, ExpressionType, ValueTypes};
pub use parse::{Declaration, Vocabulary};
pub use read::{Global, Script, ScriptSection, SourceFile};

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("tag error: {0}")]
    Tag(#[from] blam_tag::Error),
    #[error("the scenario has no {0} field")]
    MissingField(&'static str),
    #[error("{0} is not the shape the definitions describe")]
    UnexpectedShape(&'static str),
    #[error("an expression datum is {0} bytes, expected {expected}", expected = expr::DATUM_SIZE)]
    DatumSize(usize),
    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("rewriting the tag failed: {0}")]
    Rewrite(String),
    #[error("the block shapes are not known; read the section from a tag first")]
    UnknownShapes,
    #[error("{count} {what} exceed the {max} the definitions allow")]
    TooManyElements {
        what: &'static str,
        count: usize,
        max: u32,
    },
}
