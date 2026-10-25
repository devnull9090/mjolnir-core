//! MCC Halo 2 maps: the scenario map and `shared.map` beside it, read as one
//! tag space, and staged for the conversion pipeline.
//!
//! A [`Struct`] is a view onto one tag struct (a tag's root or a block
//! element) in the file that holds it: its blocks and tag references are that
//! file's, so a weapon in `shared.map` follows its own pointers and its own
//! index, whichever map placed it.

pub mod cache;
pub mod collision;
pub mod animation;
pub mod bitmap;
pub mod geometry;
pub mod phantom;
pub mod render;
pub mod sound;
pub mod stage;

use std::path::{Path, PathBuf};

pub use cache::{CacheFile, Group, TagEntry};
use cache::{f32_at, i16_at, u16_at, u32_at};

use crate::Error;

/// The scenario map and the shared map its tags lean on.
pub struct Cache {
    pub map: CacheFile,
    pub shared: Option<CacheFile>,
    /// `textures.dat`, where MCC keeps every bitmap's pixels.
    pub textures: Option<PathBuf>,
}

impl Cache {
    /// Open a scenario map; `shared.map` and `textures.dat` are taken from
    /// `resources` (the map's own folder when `None`).
    pub fn open(map: &Path, resources: Option<&Path>) -> Result<Cache, Error> {
        let dir = resources
            .map(Path::to_path_buf)
            .or_else(|| map.parent().map(Path::to_path_buf))
            .unwrap_or_default();
        let map = CacheFile::open(map)?;
        let shared_path = dir.join("shared.map");
        let shared = if shared_path.is_file() && map.path != shared_path {
            Some(CacheFile::open(&shared_path)?)
        } else {
            None
        };
        let textures = Some(dir.join("textures.dat")).filter(|p| p.is_file());
        Ok(Cache { map, shared, textures })
    }

    fn files(&self) -> impl Iterator<Item = &CacheFile> {
        std::iter::once(&self.map).chain(self.shared.as_ref())
    }

    /// The tag a datum names in `file`'s index, wherever its data is.
    pub fn tag<'a>(&'a self, file: &'a CacheFile, datum: u32) -> Option<Tag<'a>> {
        let entry = file.entry(datum)?;
        self.tag_entry(file, entry)
    }

    fn tag_entry<'a>(&'a self, file: &'a CacheFile, entry: &'a TagEntry) -> Option<Tag<'a>> {
        if let Some(at) = entry.address.and_then(|a| file.offset(a)) {
            return Some(Tag { file, entry, root: Struct { file, at } });
        }
        // Data elsewhere: the same group and name in a file that holds it.
        self.files().find_map(|f| {
            let i = f.find(entry.group, &entry.name)?;
            let e = &f.tags[i];
            let at = f.offset(e.address?)?;
            Some(Tag { file: f, entry: e, root: Struct { file: f, at } })
        })
    }

    /// The scenario tag (the map's index entry 0 is its scenario).
    pub fn scenario(&self) -> Result<Tag<'_>, Error> {
        let e = self
            .map
            .tags
            .iter()
            .find(|e| e.group == Group::new(b"scnr") && e.address.is_some())
            .ok_or_else(|| Error::Format("no scenario tag in the map".into()))?;
        self.tag_entry(&self.map, e).ok_or_else(|| Error::Format("scenario data not found".into()))
    }

    /// Follow a tag reference read from `s`.
    pub fn follow<'a>(&'a self, r: TagRef<'a>) -> Option<Tag<'a>> {
        self.tag(r.file, r.datum)
    }
}

/// A tag with its data located.
#[derive(Clone, Copy)]
pub struct Tag<'a> {
    pub file: &'a CacheFile,
    pub entry: &'a TagEntry,
    pub root: Struct<'a>,
}

impl<'a> Tag<'a> {
    pub fn name(&self) -> &'a str {
        &self.entry.name
    }
    pub fn group(&self) -> Group {
        self.entry.group
    }
}

/// A tag reference as read from a struct: group, datum, and the file whose
/// index the datum belongs to.
#[derive(Clone, Copy)]
pub struct TagRef<'a> {
    pub group: Group,
    pub datum: u32,
    pub file: &'a CacheFile,
}

impl<'a> TagRef<'a> {
    /// The referenced tag's path, from the index (empty for a null reference).
    pub fn name(&self) -> &'a str {
        self.file.entry(self.datum).map(|e| e.name.as_str()).unwrap_or("")
    }
}

/// A view onto one struct in a cache file.
#[derive(Clone, Copy)]
pub struct Struct<'a> {
    pub file: &'a CacheFile,
    pub at: usize,
}

impl<'a> Struct<'a> {
    /// The struct embedded at `off` (a collision BSP inside an instanced
    /// geometry definition, say).
    pub fn at(&self, off: usize) -> Struct<'a> {
        Struct { file: self.file, at: self.at + off }
    }
    pub fn bytes(&self, off: usize, len: usize) -> &'a [u8] {
        &self.file.data[self.at + off..self.at + off + len]
    }
    pub fn u8(&self, off: usize) -> u8 {
        self.file.data[self.at + off]
    }
    pub fn u16(&self, off: usize) -> u16 {
        u16_at(&self.file.data, self.at + off)
    }
    pub fn i16(&self, off: usize) -> i16 {
        i16_at(&self.file.data, self.at + off)
    }
    pub fn u32(&self, off: usize) -> u32 {
        u32_at(&self.file.data, self.at + off)
    }
    pub fn f32(&self, off: usize) -> f32 {
        f32_at(&self.file.data, self.at + off)
    }
    pub fn vec3(&self, off: usize) -> [f32; 3] {
        [self.f32(off), self.f32(off + 4), self.f32(off + 8)]
    }
    /// A string id field's text.
    pub fn sid(&self, off: usize) -> &'a str {
        self.file.string(self.u32(off))
    }
    /// A tag block field: `{u32 count, u32 address}`.
    pub fn block(&self, off: usize, element_size: usize) -> Block<'a> {
        let count = self.u32(off) as usize;
        let at = if count == 0 { None } else { self.file.offset(self.u32(off + 4)) };
        Block { file: self.file, count: if at.is_some() { count } else { 0 }, at, element_size }
    }
    /// A tag reference field: `{u32 group, u32 datum}`; `None` when null.
    pub fn tagref(&self, off: usize) -> Option<TagRef<'a>> {
        let datum = self.u32(off + 4);
        (datum != u32::MAX).then(|| TagRef { group: Group(self.u32(off)), datum, file: self.file })
    }
}

/// A tag block's elements.
#[derive(Clone, Copy)]
pub struct Block<'a> {
    file: &'a CacheFile,
    pub count: usize,
    at: Option<usize>,
    element_size: usize,
}

impl<'a> Block<'a> {
    /// Element `i`, if the block has it and it lies inside the file.
    pub fn get(&self, i: usize) -> Option<Struct<'a>> {
        let at = self.at? + i * self.element_size;
        (i < self.count && at + self.element_size <= self.file.data.len()).then(|| Struct { file: self.file, at })
    }
    pub fn iter(&self) -> impl Iterator<Item = Struct<'a>> + 'a {
        let b = *self;
        (0..b.count).filter_map(move |i| b.get(i))
    }
}
