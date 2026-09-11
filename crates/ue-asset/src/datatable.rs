//! `UDataTable` rows: the native tail a cooked data table carries after its
//! properties.
//!
//! `UDataTable::Serialize` writes `RowStruct` as a property; then comes the
//! `UObject` trailer every cooked export carries after its properties (a u32
//! "has guid" flag, zero), and then, natively, `i32 count` followed by each
//! row as an `FName` (a mapped name: u32 index, u32 number) and the row
//! struct in unversioned property form — the same block encoding
//! [`crate::props`] handles for exports, keyed on the row struct's schema. `scenario_register` rebuilds the shipped
//! table's rows byte for byte before it changes anything.
//!
//! Why this exists: the game registers its campaign maps at boot from the
//! tables `BuiltInMapInfoData` names (`DT_Scenarios`, `DT_Test_Scenarios`),
//! so a new scenario has to be a **cooked** row, not one injected at runtime.

use crate::props::{self, Block, Name};
use crate::Usmap;

/// One row: its name in the package name map, and its properties.
#[derive(Debug, Clone, PartialEq)]
pub struct Row {
    pub name: Name,
    pub block: Block,
}

/// Decode the rows at the head of `tail`, returning them and how many bytes
/// they took; anything after is the caller's to keep verbatim.
pub fn decode(usmap: &Usmap, row_struct: &str, tail: &[u8]) -> Result<(Vec<Row>, usize), String> {
    let u32_at = |at: usize| -> Result<u32, String> {
        tail.get(at..at + 4)
            .map(|b| u32::from_le_bytes(b.try_into().unwrap()))
            .ok_or_else(|| format!("data table tail truncated at {at}"))
    };
    let guid_flag = u32_at(0)?;
    if guid_flag != 0 {
        return Err(format!("object trailer flag is {guid_flag}, expected 0"));
    }
    let count = u32_at(4)? as usize;
    if count > 100_000 {
        return Err(format!("{count} rows is implausible"));
    }
    let mut at = 8;
    let mut rows = Vec::with_capacity(count);
    for i in 0..count {
        let name = Name {
            index: u32_at(at)?,
            number: u32_at(at + 4)?,
        };
        at += 8;
        let (block, used) = props::decode_prefix(usmap, row_struct, &tail[at..])
            .map_err(|e| format!("row {i}: {e}"))?;
        at += used;
        rows.push(Row { name, block });
    }
    Ok((rows, at))
}

/// Encode rows the way the cook does.
pub fn encode(usmap: &Usmap, row_struct: &str, rows: &[Row]) -> Result<Vec<u8>, String> {
    let mut out = Vec::new();
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&(rows.len() as u32).to_le_bytes());
    for (i, r) in rows.iter().enumerate() {
        out.extend_from_slice(&r.name.index.to_le_bytes());
        out.extend_from_slice(&r.name.number.to_le_bytes());
        let body = r
            .block
            .encode(usmap, row_struct)
            .map_err(|e| format!("row {i}: {e}"))?;
        out.extend_from_slice(&body);
    }
    Ok(out)
}
