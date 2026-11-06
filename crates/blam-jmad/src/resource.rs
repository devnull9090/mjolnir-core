//! A resource group: the body of one `tag resource groups` element.
//!
//! The body is three nested sections around the members' records and blobs.
//! Rebuilding it from its parts reproduces the bytes it came from.

use std::collections::BTreeSet;

use blam_tag::section::{read_at, Section};
use blam_tag::write::raw_section;

use crate::member::{Member, RECORD};
use crate::Error;

/// One resource group.
#[derive(Debug, Clone, PartialEq)]
pub struct Group {
    /// The content of the group's leading section: the member count and eight
    /// bytes this crate carries unread.
    pub lead: Vec<u8>,
    pub members: Vec<Member>,
}

fn section_named<'a>(b: &'a [u8], at: usize, name: &str) -> Result<Section<'a>, Error> {
    read_at(b, at)
        .filter(|s| s.is(name))
        .ok_or_else(|| Error::Format(format!("expected a {name} section at offset {at}")))
}

/// A `tgst` section, whose version word repeats its size.
fn wrapper(content: &[u8]) -> Vec<u8> {
    raw_section("tgst", content.len() as u32, content)
}

impl Group {
    /// Read a group from a `tag_resource`'s section body.
    pub fn read(body: &[u8]) -> Result<Group, Error> {
        let lead = section_named(body, 0, "tgdt")?;
        let outer = section_named(body, lead.total(), "tgst")?;
        let block = section_named(outer.content, 0, "tgbl")?;
        let b = block.content;
        if b.len() < 8 {
            return Err(Error::Format("member block too short".into()));
        }
        let count = u32::from_le_bytes(b[0..4].try_into().unwrap()) as usize;
        let flags = u32::from_le_bytes(b[4..8].try_into().unwrap());
        if flags != 0 {
            return Err(Error::Format(format!("member block flags {flags}")));
        }
        let mut at = 8 + count * RECORD;
        let mut members = Vec::with_capacity(count);
        for i in 0..count {
            let record = b
                .get(8 + i * RECORD..8 + (i + 1) * RECORD)
                .ok_or_else(|| Error::Format("member records run out".into()))?;
            let each = section_named(b, at, "tgst")?;
            let sizes = section_named(each.content, 0, "tgst")?;
            let data = section_named(each.content, sizes.total(), "tgda")?;
            if sizes.size != 0 {
                return Err(Error::Format("member size struct is not empty".into()));
            }
            members.push(Member::read(record, data.content)?);
            at += each.total();
        }
        if at != b.len() {
            return Err(Error::Format("bytes left after the last member".into()));
        }
        Ok(Group {
            lead: lead.content.to_vec(),
            members,
        })
    }

    /// Keep only these members, and say so in the lead.
    pub fn keep(&mut self, members: &BTreeSet<usize>) -> Result<(), Error> {
        if self.lead.len() < 4 {
            return Err(Error::Format("group lead too short".into()));
        }
        let mut at = 0;
        self.members.retain(|_| {
            at += 1;
            members.contains(&(at - 1))
        });
        if self.members.len() != members.len() {
            return Err(Error::Format("a kept member is not in its group".into()));
        }
        self.lead[..4].copy_from_slice(&(self.members.len() as u32).to_le_bytes());
        Ok(())
    }

    /// The section body, ready to go back in the tag.
    pub fn write(&self) -> Vec<u8> {
        let mut records = Vec::with_capacity(8 + self.members.len() * RECORD);
        records.extend_from_slice(&(self.members.len() as u32).to_le_bytes());
        records.extend_from_slice(&0u32.to_le_bytes());
        let mut wrappers = Vec::new();
        for m in &self.members {
            let (record, blob) = m.write();
            records.extend_from_slice(&record);
            let mut each = raw_section("tgst", 0, &[]);
            each.extend_from_slice(&raw_section("tgda", 0, &blob));
            wrappers.extend_from_slice(&wrapper(&each));
        }
        records.extend_from_slice(&wrappers);
        let mut out = raw_section("tgdt", 0, &self.lead);
        out.extend_from_slice(&wrapper(&raw_section("tgbl", 0, &records)));
        out
    }
}
