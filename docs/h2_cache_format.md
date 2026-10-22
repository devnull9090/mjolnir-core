# MCC Halo 2 Cache Files

**Status:** 2026-10-21, Steam build 19905945. Every layout below was read off
the installed files (`halo2/h2_maps_win64_dx11`): the container on
lockout.map, coagulation.map, shared.map and mainmenu.map, the tag layouts on
Lockout and shared.map, the scenario layout on all 24 multiplayer maps. The
reader is `crates/blam-cache` (`h2::cache`, `h2::collision`, `h2::geometry`,
`h2::bitmap`); public tools (Assembly's Halo2MCC plugins, TagTool's Gen2
definitions, Reclaimer) agree except where noted. How a map is converted is in
[h2_map_conversion.md](h2_map_conversion.md).

## Telling the games apart

Every MCC title writes cache version 13 at offset 4. The game is the low byte
of the u32 at 0x0C, and the header ends with `foot` four bytes before its own
size (`blam_cache::detect`, `mjolnir cache info`):

| game | 0x0C | header | name | scenario path |
|---|---|---|---|---|
| Halo 1 | 0 | 0x800 | 0x20 | (none) |
| Halo 2 | 0x201 | 0x380 | 0xB0 | 0xD0 |
| Halo 3 | 0x202 | 0x4000 | 0xC0 | 0xE0 |
| Halo 4 | 0x203 | 0x1E000 | 0xB8 | 0xD8 |
| Halo 2 Anniversary MP (`groundhog`) | 0x204 | 0x1E000 | 0xB8 | 0xD8 |
| Halo: Reach | 0x206 | 0xA000 | 0xC0 | 0xE0 |

The classic builds keep their versions: Halo 1 Xbox 5, PC 7, Custom Edition
609 (what the stock-map conversions read, through halo2ue), Halo 2 Xbox and
Vista 8. MCC's Halo 1 maps (version 13, tag memory at 0x50000000) are not
read by halo2ue yet.

## Container

The file is the 0x380-byte header, then zlib chunks of at most 0x40000 bytes
each (zlib header `28 15`, a 1 KiB window). The chunk table is at the offset
the header gives at 0x310, with the count at 0x314: per chunk, u32 compressed
size and u32 file offset. The decompressed image is the header followed by
the chunks back to back; its length is the header's u32 at 0x08, and every
offset below is into it.

| offset | field |
|---|---|
| 0x10 | tag index offset |
| 0x14 | tag buffer size (index + tag data) |
| 0x20 / 0x24 / 0x2C | tag name count / name buffer / name offset table (u32, -1 none) |
| 0x30 / 0x34 / 0x38 / 0x3C | string id count / buffer / size / offset table |
| 0xB0 | map name (32) |
| 0xD0 | scenario path (256) |
| 0x2D0 | virtual base: 0x3200000 for a scenario map, 0 for shared.map and mainmenu.map |
| 0x2D4 / 0x2D8 | index size / tag data size |
| 0x2F0 | header size (0x380), where the chunks start |
| 0x308 / 0x310 / 0x314 | chunk size / chunk table offset / chunk count |
| 0x37C | `foot` |

**Addresses.** A tag address `a` is at image offset
`a - base(0x2D0) + index offset(0x10)`; tag data starts at the index offset
plus the index size. The sbsp and ltmp are ordinary tags (the scenario's
structure BSP entries keep offset/size/address 0, unlike Xbox and Vista).

**Tag index** at 0x10: u32 group table offset (relative, 0x20), group count,
tag table offset (relative), scenario datum, globals datum, checksum, tag
count, `tags`. Group entries are 12 bytes (fourcc, parent, grandparent); tag
entries 16 (fourcc, datum, address, size). `datum & 0xFFFF` is the index. A
scenario map holds only its own tags (Lockout: 224 of 23,131 index entries);
an entry with address 0 or -1 is in shared.map, found there by name (the
same index holds the same tag in both, but mainmenu.map's address range
overlaps shared.map's, so addresses never decide the file).

**Fields.** A tag block is `{u32 count, u32 address}`, a tag reference
`{u32 fourcc, u32 datum}`, a data reference `{u32 size, u32 address}`, a
string id 4 bytes: index in the low 24 bits, length in the top 8.

## Raw data

Geometry lives outside the tags. A geometry block info is u32 offset, u32
size, u32 section struct size, u32 resource size, then a resources block. The
offset's top two bits pick the file (0 the tag's own, 1 mainmenu.map, 2
shared.map, 3 single_player_shared.map); the low 30 are an offset into that
file's decompressed image. The block is `blkh`, u32 resource size, the section
struct, `rsrc`, the resources, `blkf`. A resource entry (16 bytes) is u8 type
(0 a tag block, 1 tag data, 2 a vertex buffer), u8, u16 the section field it
fills, u16, i16 element size or vertex buffer index, u32 size, u32 offset
from the `rsrc` marker.

The section struct (0x48 for BSP sections, 0x78 for render models): parts at
0x00 (72 bytes: i16 type, u16 flags (bit 3 triangle list), i16 material, i16
first index, i16 index count, ...), subparts 0x08, u16 indices 0x20, vertex
buffer descriptors 0x38 (32 bytes: vertex type, stride). MCC's vertex types,
all floats: 0x01 position (12), 0x17 texture coordinate (8), 0x19 normal,
binormal, tangent (36), 0x1D lightmap coordinate (8), 0x2F incident light
direction (12). BSP sections are triangle lists winding counter-clockwise
about their normals (7,048 of Lockout's 7,049); render models are strips.

**Bitmaps** are all in `textures.dat`. A `bitm` element (168 bytes on MCC,
116 on Xbox and Vista) has i16 width and height at 0x04, type at 0x0A (0 2D,
1 3D, 2 cube), format at 0x0C (0 A8, 1 Y8, 2 AY8, 3 A8Y8, 6 R5G6B5, 8
A1R5G5B5, 9 A4R4G4B4, 10 X8R8G8B8, 11 A8R8G8B8, 14 DXT1, 15 DXT3, 16 DXT5,
22 V8U8, 23 G8B8), mipmap count at 0x14, the entry's offset in textures.dat
at 0x38 and its size at 0x50. An entry is i32 n, i32 sizes[n], then the
chunks: positive sizes are zlib, negative ones stored. They concatenate to
every level from the largest down, unswizzled: Lockout's 512 x 256 X8R8G8B8
sky with nine mipmaps is 699,052 bytes, the levels down to 1 x 1.

## Tags the conversion reads

**scnr** (base 0x3E0): skies 0x08, scenery 0x50 / palette 0x58, vehicles
0x70, weapons 0x90, player starts 0x100 (0x34: position, facing, i16 team,
i16 BSP, four i16 game types), netgame flags 0x118 (0x20: position, facing,
i16 type, i16 team, i16 identifier, flags), netgame equipment 0x120 (0x90:
flags (bit 0 levitate), four game types, i16 team, i16 spawn time at 0x0E,
classification 0x14, position 0x40, yaw/pitch/roll 0x4C, item or vehicle
collection reference 0x58), structure BSPs 0x210 (0x44: sbsp reference
0x10, ltmp 0x18), crates 0x328 / palette 0x330. Placements share a 0x34-byte
header (palette index, name index, flags, position 0x08, yaw/pitch/roll 0x14,
scale 0x20, 0 meaning 1). Scenery +0x5A is the multiplayer game types it
appears in (bit 1 Slayer; 0 all).

Netgame flag types: 0 CTF flag spawn, 1 CTF flag return, 2 assault bomb
spawn, 3 assault bomb return, 4 oddball, 5 unused, 6 race checkpoint, 7
teleporter source, 8 teleporter destination (paired by identifier), 9
headhunter bin, 10 territory, 11-18 King of the Hill hills 0-7 (each hill a
ring of about eight flags). Game types: 0 none, 1 CTF, 2 Slayer, 3 Oddball,
4 KotH, 5 Race, 6 Headhunter, 7 Juggernaut, 8 Territories, 12 all, 13 all but
CTF, 14 all but CTF and Race.

**sbsp** (base 0x23C): collision materials 0x0C (0x14: old shader ref, i16
global material index, i16 conveyor surface, shader ref at 0x0C), collision
BSP 0x14 (0x40), clusters 0x9C (0xB0: vertex count at 0x00, geometry block
info at 0x28), materials 0xA4 (0x20: old shader ref, shader ref at 0x08),
instanced geometry definitions 0x138 (0xC8: vertex count 0x00, geometry
block info 0x28, bounding sphere 0x60, collision BSP 0x70), instances 0x140
(0x58: scale, forward, left, up, position; i16 definition 0x34; name 0x50).

**Collision BSP** (sbsp, instanced geometry, `coll`): eight blocks. 3D nodes
8 bytes (u16 plane, u24 back, u24 front; bit 23 leaf, 0xFFFFFF none); planes
16; leaves 4 (u8 flags, u8 2D reference count, u16 first); 2D references 4
(i16 plane, sign = flipped; i16 node, sign = surface); 2D nodes 16 (line,
i16 left, i16 right); surfaces 8 (u16 plane, 0x8000 = flipped; u16 first
edge; u8 flags; u8 breakable, 255 none; u16 material, 65535 none); edges 12
(six u16); vertices 16. Lockout's 3,162 surfaces are 3- to 8-sided polygons
lying within 2e-4 wu of their planes.

**ltmp**: lightmap groups at 0x80 (0x68): bitmap group reference 0x18,
cluster render info 0x28 and instance render info 0x48 (4 bytes: i16 bitmap
index, -1 for a vertex-lit instance), geometry buckets 0x40 (0x38: u16
flags, bit 0 incident direction, bit 1 colour; the raw block offset at 0x0C,
section struct size 0x14 (8), resources block 0x1C), instance bucket refs
0x50 (12 bytes: i16 flags, i16 bucket, a block of i16 section offsets: the
instance's first vertex in the bucket). A bucket's raw block is laid out as
a geometry section's, with vertex buffers of type 0x2F (12 bytes: the
incident light direction, in world space) and, for vertex-lit geometry, 0x2E
(u8 R, G, B, 0: the light's colour, in the pages' units, half intensity).
Definition vertex k of instance i is bucket vertex offset + k; every
instance has a ref, so every instance's incident directions come from its
bucket (no instanced geometry definition carries a 0x2F buffer). Checked on
all 24 maps' 2,341 instances. Lockout's 65 pages are A8R8G8B8.

**Nodes** (mode +0x48, 0x60 bytes): string id name, i16 parent, first
child, next sibling, import index; translation in the parent's space at
0x0C; rotation quaternion (i, j, k, w) at 0x18, the node's forward
rotation; inverse forward, left, up and position at 0x2C, 0x38, 0x44, 0x50.
A node's object transform is its parent's composed with its own (rotate,
then translate), parents first. A collision model's BSP vertices are in its
node's space (the coll node list matches the mode's by index); a render
section's vertices are already in object space, whatever their node
(rigid: section +0x2C; rigid boned and skinned: node map indices and
weights after each vertex's position), so the node transforms serve
animation only. Checked on Zanzibar's crane and hinged lights, where the
posed collision lands on the mesh within 1 cm.

**shad**: template (`stem`) 0x00, global material name 0x08, runtime
properties 0x0C (0x50: diffuse map 0x00), postprocess definition 0x20 (0x7C:
bitmaps at 0x04, 12 bytes each (datum, submap, log size); pixel constants
at 0x0C, 4 bytes each as D3DCOLOR (B, G, R, A); vertex constants at 0x14,
float4: for the opaque templates the maps' u and v scales, for the
transparent ones a 2 x 4 texture transform per map (u row, v row: scale
in .x/.y, offset in .w); overlays at 0x3C (0x14: f32 period at 8, the
function at 0xC as {size, address}: byte 0 type, 0 identity, the value at
t = 0 at +4 and at t = period at +8); overlay refs at 0x44 (i16 overlay,
i16 transform type: 4 translation u, 5 translation v); animated parameters
at 0x4C (u16: count in the top 7 bits, first in the low 9, into the overlay
refs); animated parameter refs at 0x54 (u16 descriptor, u8, i8 parameter; a
descriptor below 0x100 is the bitmap slot)). MCC keeps no parameter names;
each template's bitmap slots come in its own order (the table is
`h2::render::template`). The pixel math is in the compiled DXBC pixel
shaders inside the `spas` tags (postprocess definitions 0x1C, implementation
+0x132, three data refs); read back for the glass, plasma and "two plus
two" families: glass = base x albedo tint x base.a + cube(reflection) x
environment tint x specular mask, both scaled by a facing/glancing tint
(pixel constants 0 environment tint, 1 albedo tint; vertex constants 0
facing, 1 glancing), premultiplied blend; "two plus two" = the product of
its three maps, colour and alpha, alpha blended, two-sided; plasma = two
noise maps banded against each other through the mask's alpha, additive.
The opaque templates draw an albedo pass (base x detail x 2, alpha base.a
x detail.a; `tex_bump_detail_blend` blends its two details by the base's
alpha, the second where it is high) and a lightmap pass: 2 x light x
albedo, the light bent by the bump against the incident direction. The
`env` templates' lightmap pass adds cube(reflection) x lerp(glancing,
facing colour, N.V) x lerp(glancing, facing brightness, N.V) x albedo alpha
x min(1, 0.753 (r + g + b) of the light); the two colours sit just before
the first pair of pixel constants holding only alpha (the brightnesses).
The cube's bitmap slot differs by template. `tex_bump`'s lightmap pass has
no specular term, and its specular-sphere pass has no implementation.

**sky**: render model 0x00, flags 0x10 (bit 0 fixed in world space, bit 2
casts light from below, bit 5 use clear colour), render model scale 0x14,
indoor ambient 0x24, outdoor ambient 0x34, atmospheric fog 0x48 (0x18:
colour, maximum density 0x0C, start 0x10, opaque 0x14), lights 0x78 (0x34:
yaw 0x0C, pitch 0x10, radians, towards the sun as `(cos p cos y, cos p sin
y, sin p)`; radiosity block 0x2C (0x28: flags (bit 0 affects exteriors, bit
1 interiors, bit 2 direct light in the lightmaps, bit 3 indirect), colour
0x04, power 0x10, angular diameter 0x24)), clear colour 0xA0. Every
multiplayer map has one light; Lockout's has no radiosity flags and its
lightmaps' incident directions (yaw 78, pitch 48 degrees over flat ground)
match the sky model's brightness, not the light.

**Cube maps** (`bitm` type 2) are stored mip-major, the six faces of each
level together in the order +X, +Y, -X, -Y, +Z, -Z on Halo's axes, no face
flipped (every seam matched across the Lockout and Forerunner cubes).

**mode** (MCC): compression info 0x14 (0x38: seven ranges, position x, y,
z, texture u, v, secondary u, v), regions 0x1C (0x10: name, permutations at
0x08, 16 bytes: name, L1-L6 section indices), sections 0x24 (0x5C: u32, then
the section info from 0x04: vertex count 0x04, compression flags 0x1A (bit 0
position, bit 1 texture coordinate), its own compression info 0x1C, geometry
block info 0x38), nodes 0x48, materials 0x60 (0x20: shader ref at 0x08). A
compressed value is stored in -1..1 across its range (`min + (v + 1) / 2 *
(max - min)`): Lockout's sky spans hundreds of world units from vertices
within -1..1. BSP clusters and instanced geometry carry no ranges. **hlmt**: render model 0x00, collision model 0x08. Objects: model at
0x34. **sky**: render model 0x00. **itmc** / **vehc**: permutations 0x00
(0x10: weight, item reference, variant). **coll**: regions 0x1C (0x0C:
permutations at 0x04, 0x14 each: BSPs at 0x04, 0x44 each: i16 node, then the
collision BSP).
