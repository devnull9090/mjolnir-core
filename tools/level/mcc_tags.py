"""Bungie's source tags from MCC's Halo CE editing kit (HCEEK), read where a
classic Custom Edition map has only Gearbox's PC stand-in.

The PC port drew every `shader_transparent_generic` (the Xbox's register
combiner shader) as a `shader_transparent_chicago`, and a classic map carries
only that: Death Island's teleporter field is two grey dust maps tiled once,
a soft green blob, where MCC draws the Xbox shader's wavy energy. MCC's kit
ships the original tags, so a chicago shader whose path MCC has as a
`shader_transparent_generic` is read from there instead (ce_material_spec.py
`generic`), its bitmaps exported beside the map's own (`mcc_` names).

Tag files are big-endian: a 64-byte header, the root struct, then each
field's child data in field order (a reference's path and NUL when it has
one; a block's elements, then each element's own children; tag data's
bytes). Field layouts follow halo2ue's shader_fields.rs, the public H1
definitions; a map's and a stage's flags are a u16 then 2 bytes of padding
in a tag file (one little-endian u32 in a cache file). Pixel data inside a bitmap tag is little-endian, as the
PC renderer uploads it.

    python mcc_tags.py <tag path>     # print a generic shader as JSON
"""
import json
import os
import struct
import sys

TAGS = os.environ.get("MCC_TAGS", r"C:\Program Files (x86)\Steam\steamapps\common\HCEEK\tags")

# Field kinds: (kind, name[, extra]). Sizes in bytes.
SIZES = {"u8": 1, "i8": 1, "u16": 2, "i16": 2, "u32": 4, "f32": 4, "rgb": 12, "argb": 16,
         "pt2": 8, "ref": 16, "block": 12, "data": 20}
FORMATS = {"u8": ">B", "i8": ">b", "u16": ">H", "i16": ">h", "u32": ">I", "f32": ">f",
           "rgb": ">3f", "argb": ">4f", "pt2": ">2f"}


SHADER_HEADER = [
    ("u16", "radiosity_flags"), ("u16", "detail_level"), ("f32", "power"),
    ("rgb", "color_of_emitted_light"), ("rgb", "tint_color"), ("pad", 2), ("u16", "material_type"),
    ("u16", "shader_type"), ("pad", 2),
]


def anim(p):
    return [("u16", f"{p}_animation_source"), ("u16", f"{p}_animation_function"),
            ("f32", f"{p}_animation_period"), ("f32", f"{p}_animation_phase"), ("f32", f"{p}_animation_scale")]


GENERIC_MAP = [
    ("u16", "flags"), ("pad", 2), ("f32", "map_u_scale"), ("f32", "map_v_scale"), ("f32", "map_u_offset"),
    ("f32", "map_v_offset"), ("f32", "map_rotation"), ("f32", "mipmap_bias"), ("ref", "map"),
] + anim("u") + anim("v") + anim("rotation") + [("pt2", "rotation_animation_center")]

GENERIC_STAGE = [
    ("u16", "flags"), ("pad", 2), ("u16", "color0_source"), ("u16", "color0_animation_function"),
    ("f32", "color0_animation_period"), ("argb", "color0_animation_lower_bound"),
    ("argb", "color0_animation_upper_bound"), ("argb", "color1"),
] + [(t, f"color_input_{x}{s}") for x in "abcd" for t, s in (("u16", ""), ("u16", "_mapping"))] + [
    ("u16", "color_output_ab"), ("u16", "color_output_ab_function"), ("u16", "color_output_cd"),
    ("u16", "color_output_cd_function"), ("u16", "color_output_ab_cd_mux_sum"), ("u16", "color_output_mapping"),
] + [(t, f"alpha_input_{x}{s}") for x in "abcd" for t, s in (("u16", ""), ("u16", "_mapping"))] + [
    ("u16", "alpha_output_ab"), ("u16", "alpha_output_cd"), ("u16", "alpha_output_ab_cd_mux_sum"),
    ("u16", "alpha_output_mapping"),
]

SOTR = SHADER_HEADER + [
    ("i8", "numeric_counter_limit"), ("u8", "flags"), ("u16", "first_map_type"),
    ("u16", "framebuffer_blend_function"), ("u16", "framebuffer_fade_mode"), ("u16", "framebuffer_fade_source"),
    ("pad", 2), ("f32", "lens_flare_spacing"), ("ref", "lens_flare"),
    ("block", "extra_layers", (16, [("ref", "shader")])),
    ("block", "maps", (100, GENERIC_MAP)),
    ("block", "stages", (112, GENERIC_STAGE)),
]

SPRITE = [("u16", "bitmap_index"), ("pad", 6), ("f32", "left"), ("f32", "right"), ("f32", "top"),
          ("f32", "bottom"), ("pt2", "registration_point")]
SEQUENCE = [("pad", 32), ("u16", "first_bitmap_index"), ("u16", "bitmap_count"), ("pad", 16),
            ("block", "sprites", (32, SPRITE))]
BITMAP_DATA = [("pad", 4), ("u16", "width"), ("u16", "height"), ("u16", "depth"), ("u16", "type"),
               ("u16", "format"), ("u16", "flags"), ("i16", "registration_x"), ("i16", "registration_y"),
               ("u16", "mipmap_count"), ("pad", 2), ("u32", "pixels_offset"), ("pad", 20)]
BITM = [
    ("u16", "type"), ("u16", "format"), ("u16", "usage"), ("u16", "flags"), ("f32", "detail_fade_factor"),
    ("f32", "sharpen_amount"), ("f32", "bump_height"), ("u16", "sprite_budget_size"),
    ("u16", "sprite_budget_count"), ("u16", "color_plate_width"), ("u16", "color_plate_height"),
    ("data", "compressed_color_plate_data"), ("data", "processed_pixel_data"), ("f32", "blur_filter_size"),
    ("f32", "alpha_bias"), ("u16", "mipmap_count"), ("u16", "sprite_usage"), ("u16", "sprite_spacing"),
    ("pad", 2), ("block", "sequences", (64, SEQUENCE)), ("block", "bitmaps", (48, BITMAP_DATA)),
]


def struct_size(layout):
    return sum(f[1] if f[0] == "pad" else SIZES[f[0]] for f in layout)


class TagFile:
    """One tag file read against a layout."""

    def __init__(self, path, group, layout):
        self.d = open(path, "rb").read()
        if self.d[36:40] != group.encode() or self.d[60:64] != b"blam":
            raise ValueError(f"{path}: not a {group} tag")
        self.pos = 64
        fixed, pending = self.fixed(64, layout)
        self.pos = 64 + struct_size(layout)
        self.root = self.children(fixed, pending)

    def fixed(self, off, layout):
        vals, pending = {}, []
        for f in layout:
            kind = f[0]
            if kind == "pad":
                off += f[1]
                continue
            name = f[1]
            if kind == "ref":
                group, _, length, _ = struct.unpack_from(">4sIiI", self.d, off)
                vals[name] = None
                pending.append((name, "ref", (group, length)))
            elif kind == "block":
                count = struct.unpack_from(">i", self.d, off)[0]
                pending.append((name, "block", (count,) + f[2]))
            elif kind == "data":
                size = struct.unpack_from(">i", self.d, off)[0]
                pending.append((name, "data", size))
            else:
                v = struct.unpack_from(FORMATS[kind], self.d, off)
                vals[name] = list(v) if len(v) > 1 else v[0]
            off += SIZES[kind]
        return vals, pending

    def children(self, vals, pending):
        for name, kind, info in pending:
            if kind == "ref":
                group, length = info
                if length > 0:
                    path = self.d[self.pos:self.pos + length].decode("latin-1")
                    self.pos += length + 1
                    vals[name] = {"group": group.decode("latin-1"), "path": path}
            elif kind == "data":
                vals[name] = self.d[self.pos:self.pos + info]
                self.pos += info
            else:
                count, size, layout = info
                base = self.pos
                self.pos += count * size
                elements = [self.fixed(base + i * size, layout) for i in range(count)]
                vals[name] = [self.children(v, p) for v, p in elements]
        return vals


def tag_file(tag_path, extension):
    return os.path.join(TAGS, tag_path.replace("/", "\\") + "." + extension)


def generic_shader(tag_path):
    """MCC's shader_transparent_generic at a shader's tag path, or None."""
    path = tag_file(tag_path, "shader_transparent_generic")
    if not os.path.exists(path):
        return None
    return TagFile(path, "sotr", SOTR).root


# Pixel formats: bytes per pixel, or block size for DXT.
_DXT = {14: 8, 15: 16, 16: 16}
_BPP = {0: 1, 1: 1, 2: 1, 3: 2, 6: 2, 8: 2, 9: 2, 10: 4, 11: 4, 17: 1}


def _expand565(c):
    import numpy as np
    r = ((c >> 11) & 31) * 255 // 31
    g = ((c >> 5) & 63) * 255 // 63
    b = (c & 31) * 255 // 31
    return np.stack([r, g, b], -1).astype(np.int32)


def _dxt(data, w, h, fmt):
    """DXT1/3/5 blocks to an RGBA uint8 array (h, w, 4)."""
    import numpy as np
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    bs = _DXT[fmt]
    blocks = np.frombuffer(data, np.uint8, bw * bh * bs).reshape(bw * bh, bs)
    col = blocks[:, bs - 8:]
    c0 = col[:, 0].astype(np.int32) | (col[:, 1].astype(np.int32) << 8)
    c1 = col[:, 2].astype(np.int32) | (col[:, 3].astype(np.int32) << 8)
    idx = col[:, 4].astype(np.uint32) | (col[:, 5].astype(np.uint32) << 8) | \
        (col[:, 6].astype(np.uint32) << 16) | (col[:, 7].astype(np.uint32) << 24)
    p0, p1 = _expand565(c0), _expand565(c1)
    four = (c0 > c1) | (fmt != 14)
    pal = np.zeros((len(c0), 4, 4), np.int32)
    pal[:, 0, :3], pal[:, 1, :3] = p0, p1
    pal[:, 2, :3] = np.where(four[:, None], (2 * p0 + p1) // 3, (p0 + p1) // 2)
    pal[:, 3, :3] = np.where(four[:, None], (p0 + 2 * p1) // 3, 0)
    pal[:, :, 3] = 255
    if fmt == 14:
        pal[:, 3, 3] = np.where(four, 255, 0)
    sel = (idx[:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3
    px = np.take_along_axis(pal, sel[:, :, None].astype(np.int64).repeat(4, 2), 1)
    if fmt == 15:
        a = blocks[:, :8]
        nib = np.stack([a & 15, a >> 4], -1).reshape(len(a), 16).astype(np.int32)
        px[:, :, 3] = nib * 17
    elif fmt == 16:
        a0, a1 = blocks[:, 0].astype(np.int32), blocks[:, 1].astype(np.int32)
        bits = 0
        for k in range(6):
            bits = bits | (blocks[:, 2 + k].astype(np.uint64) << np.uint64(8 * k))
        ai = (bits[:, None] >> (np.uint64(3) * np.arange(16, dtype=np.uint64))) & np.uint64(7)
        ai = ai.astype(np.int32)
        apal = np.zeros((len(a0), 8), np.int32)
        apal[:, 0], apal[:, 1] = a0, a1
        eight = a0 > a1
        for k in range(1, 7):
            apal[:, k + 1] = np.where(eight, ((7 - k) * a0 + k * a1) // 7, 0)
        for k in range(1, 5):
            apal[:, k + 1] = np.where(eight, apal[:, k + 1], ((5 - k) * a0 + k * a1) // 5)
        apal[:, 6] = np.where(eight, apal[:, 6], 0)
        apal[:, 7] = np.where(eight, apal[:, 7], 255)
        px[:, :, 3] = np.take_along_axis(apal, ai, 1)
    img = px.reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return img[:h, :w].astype(np.uint8)


def _raw(data, w, h, fmt):
    """An uncompressed level to RGBA uint8 (h, w, 4)."""
    import numpy as np
    n = w * h
    if fmt in (10, 11):
        p = np.frombuffer(data, np.uint8, n * 4).reshape(h, w, 4)
        out = p[:, :, [2, 1, 0, 3]].copy()
        if fmt == 10:
            out[:, :, 3] = 255
        return out
    if fmt in (6, 8, 9):
        c = np.frombuffer(data, "<u2", n).astype(np.int32).reshape(h, w)
        if fmt == 6:
            rgb = _expand565(c)
            a = np.full((h, w), 255, np.int32)
        elif fmt == 8:
            rgb = np.stack([((c >> 10) & 31) * 255 // 31, ((c >> 5) & 31) * 255 // 31, (c & 31) * 255 // 31], -1)
            a = np.where(c & 0x8000, 255, 0)
        else:
            rgb = np.stack([((c >> 8) & 15) * 17, ((c >> 4) & 15) * 17, (c & 15) * 17], -1)
            a = ((c >> 12) & 15) * 17
        return np.concatenate([rgb, a[:, :, None]], -1).astype(np.uint8)
    b = np.frombuffer(data, np.uint8, n * _BPP[fmt]).reshape(h, w, -1)
    if fmt == 0:  # A8: white with alpha
        return np.concatenate([np.full((h, w, 3), 255, np.uint8), b], -1)
    if fmt == 1:  # Y8
        return np.concatenate([b.repeat(3, 2), np.full((h, w, 1), 255, np.uint8)], -1)
    if fmt == 2:  # AY8: the same byte as intensity and alpha
        return b.repeat(4, 2)
    if fmt == 3:  # A8Y8: y low byte, a high byte
        return np.concatenate([b[:, :, :1].repeat(3, 2), b[:, :, 1:2]], -1)
    raise ValueError(f"unsupported bitmap format {fmt}")


def _level_size(w, h, fmt):
    if fmt in _DXT:
        return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * _DXT[fmt]
    return w * h * _BPP[fmt]


def bitmap_levels(tag_path, index=0):
    """A bitmap tag's 2D bitmap `index` as its mip levels (RGBA uint8 arrays,
    largest first), or None when the tag is missing or not a 2D texture."""
    path = tag_file(tag_path, "bitmap")
    if not os.path.exists(path):
        return None
    t = TagFile(path, "bitm", BITM).root
    bitmaps = t.get("bitmaps") or []
    if index >= len(bitmaps):
        return None
    b = bitmaps[index]
    fmt, w, h = b["format"], b["width"], b["height"]
    if b["type"] != 0 or (fmt not in _DXT and fmt not in _BPP) or fmt == 17 or b["flags"] & 8:
        return None
    pixels = t["processed_pixel_data"]
    off = b["pixels_offset"]
    levels = []
    for _ in range(b["mipmap_count"] + 1):
        size = _level_size(w, h, fmt)
        data = pixels[off:off + size]
        if len(data) < size:
            break
        levels.append(_dxt(data, w, h, fmt) if fmt in _DXT else _raw(data, w, h, fmt))
        off += size
        if w == 1 and h == 1:
            break
        w, h = max(1, w // 2), max(1, h // 2)
    return levels


def write_bitmap(tag_path, out_dir, stem, index=0):
    """A bitmap tag written as `<stem>.png` (the top level) and `<stem>.dds`
    (BGRA8, the tag's own mip chain, completed down to 1x1 by box filtering),
    the pair ce_material_spec.py imports. Returns the PNG's file name or None."""
    import numpy as np
    from PIL import Image
    levels = bitmap_levels(tag_path, index)
    if not levels:
        return None
    while levels[-1].shape[0] > 1 or levels[-1].shape[1] > 1:
        last = levels[-1]
        h, w = max(1, last.shape[0] // 2), max(1, last.shape[1] // 2)
        levels.append(np.asarray(Image.fromarray(last).resize((w, h), Image.BOX)))
    os.makedirs(out_dir, exist_ok=True)
    png = stem + ".png"
    Image.fromarray(levels[0], "RGBA").save(os.path.join(out_dir, png))
    h, w = levels[0].shape[:2]
    # 128 bytes: magic, the 124-byte header (7 fields, 44 reserved, the
    # 32-byte pixel format, caps 1-4 and a reserved word). 12 more bytes of
    # padding once shifted every MCC texture 3 texels (Gephyrophobia's ring
    # tore where a vertical strip met a horizontal one, 2026-10-09).
    header = struct.pack(
        "<4sIIIIIII44sIIIIIIIIIIIII",
        b"DDS ", 124, 0x2100F, h, w, w * 4, 0, len(levels), bytes(44),
        32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000,
        0x401008, 0, 0, 0, 0)
    assert len(header) == 128
    with open(os.path.join(out_dir, stem + ".dds"), "wb") as f:
        f.write(header)
        for lv in levels:
            f.write(np.ascontiguousarray(lv[:, :, [2, 1, 0, 3]]).tobytes())
    return png


def stem_for(tag_path):
    """The `mcc_` texture stem for a bitmap tag path, as halo2ue names a
    staged bitmap (path parts joined by `_`, spaces to `_`)."""
    return "mcc_" + tag_path.replace("\\", "_").replace("/", "_").replace(" ", "_").replace("-", "_").lower()


def _jsonable(v):
    if isinstance(v, bytes):
        return f"<{len(v)} bytes>"
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v


if __name__ == "__main__":
    print(json.dumps(_jsonable(generic_shader(sys.argv[1])), indent=1))
