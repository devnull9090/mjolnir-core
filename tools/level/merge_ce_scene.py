#!/usr/bin/env python3
"""Merge a staged CE map's scenery and sky into its BSP render mesh.

    merge_ce_scene.py <staging dir> <out.gltf> [--sky-radius 4000]

The converted terrain is one mesh (tools/level/convert_ce_map.sh, step 3), so
the scenery the scenario places and the sky draw as more sections of it, each
with the material of its CE shader:

- every scenery and light fixture placement's model (`models/*.gltf`), moved
  to its CE position and rotation, and lit the way CE lights objects (no
  lightmap of their own: an ambient term, a light from the dominant
  direction and a bounce off the floor, all taken from the BSP under the
  object; see `object_lighting`). Each placement gets one texel of a page of
  its own (`object_lighting.png`, material `<shader>__lmobj`) holding its
  brightest lighting, and each vertex an incident direction whose dot with
  the vertex normal is that vertex's share of it, which the environment
  master's bumped-lightmap term, lm * sat(N.L) at full weight, multiplies
  back out. The page's other columns hold each placement's reflection tint
  and change colours A-D (`change_colors`), which object shaders read;
- the scenario's first sky model (`*__sky.gltf`; the BSP draws the first
  of the skies a scenario lists), its origin (the viewer) put at the map's
  centre and scaled until its nearest layer is `--sky-radius` metres away,
  so the map sits well inside it;
  its sections are named `<shader>__sky` and carry no lightmap or fog.

Writes a self-contained glTF (one .bin beside it) with the BSP's attributes
on every primitive: POSITION, NORMAL, TANGENT, TEXCOORD_0, TEXCOORD_1 and
_INCIDENT. With --translucent, the transparent (chicago, water) shaders' sections go
to a second glTF: Unreal only puts a mesh in its translucency pass when the
mesh's own material slots ask for it, and a rewritten mesh keeps its donor's
single slot.
"""
import argparse
import json
import math
import os
import struct
import sys

import numpy as np

WU_TO_M = 3.048
TRANSPARENT = ("schi", "scex", "swat", "sgla")
# The placed objects' lighting, one texel block each (see object_lighting).
OBJECT_LIGHTING_PAGE = "object_lighting.png"
LUMA = np.array([0.2126, 0.7152, 0.0722])


def load_gltf(path):
    g = json.load(open(path, encoding="utf-8"))
    buf = open(os.path.join(os.path.dirname(path), g["buffers"][0]["uri"]), "rb").read()
    return g, buf


def accessor(g, buf, i):
    a = g["accessors"][i]
    bv = g["bufferViews"][a["bufferView"]]
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    dtype = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[a["componentType"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0)
    count = a["count"]
    item = np.dtype(dtype).itemsize * n
    if stride and stride != item:
        raw = np.frombuffer(buf, np.uint8, count * stride, off).reshape(count, stride)[:, :item]
        out = raw.copy().view(dtype).reshape(count, n)
    else:
        out = np.frombuffer(buf, dtype, count * n, off).reshape(count, n)
    return out.astype(np.float64) if dtype == np.float32 else out.astype(np.uint32)


def primitives(g, buf):
    """Every primitive of every mesh, with its node transform applied, as
    dicts of numpy arrays plus its material's name and extras."""
    out = []
    for node in g["nodes"]:
        if "mesh" not in node:
            continue
        m = np.eye(4)
        if "matrix" in node:
            m = np.array(node["matrix"]).reshape(4, 4).T
        else:
            t = node.get("translation", [0, 0, 0])
            r = node.get("rotation", [0, 0, 0, 1])
            s = node.get("scale", [1, 1, 1])
            x, y, z, w = r
            rot = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
            m[:3, :3] = rot * np.array(s)
            m[:3, 3] = t
        for p in g["meshes"][node["mesh"]]["primitives"]:
            at = p["attributes"]
            pos = accessor(g, buf, at["POSITION"])
            pos = pos @ m[:3, :3].T + m[:3, 3]
            nrm = accessor(g, buf, at["NORMAL"]) @ m[:3, :3].T if "NORMAL" in at else np.tile([0, 1, 0], (len(pos), 1))
            nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
            mat = g["materials"][p["material"]] if "material" in p else {"name": "none"}
            out.append({
                "pos": pos, "nrm": nrm,
                "uv0": accessor(g, buf, at["TEXCOORD_0"]) if "TEXCOORD_0" in at else np.zeros((len(pos), 2)),
                "uv1": accessor(g, buf, at["TEXCOORD_1"]) if "TEXCOORD_1" in at else None,
                "tan": accessor(g, buf, at["TANGENT"]) if "TANGENT" in at else None,
                "inc": accessor(g, buf, at["_INCIDENT"]) if "_INCIDENT" in at else None,
                "idx": accessor(g, buf, p["indices"]).reshape(-1),
                "material": mat["name"], "extras": mat.get("extras", {}),
            })
    return out


def ce_to_gltf(v):
    """CE world units (x, y, z) to glTF metres (x, z, -y)."""
    v = np.asarray(v, dtype=np.float64)
    return np.stack([v[..., 0], v[..., 2], -v[..., 1]], axis=-1) * WU_TO_M


def ce_rotation(yaw, pitch, roll):
    """CE's object rotation (yaw about z, then pitch, then roll), as a matrix
    acting on glTF-space vectors."""
    cy, sy, cp, sp, cr, sr = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch), math.cos(roll), math.sin(roll)
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    ry = np.array([[cp, 0, -sp], [0, 1, 0], [sp, 0, cp]])
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    r_ce = rz @ ry @ rx
    # glTF (x, y, z) = CE (x, z, -y)
    swap = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])
    return swap @ r_ce @ swap.T


def tangents_for(nrm):
    """Any unit tangent perpendicular to each normal, handedness +1."""
    ref = np.where(np.abs(nrm[:, 1:2]) < 0.9, np.array([[0, 1, 0]]), np.array([[1, 0, 0]]))
    t = np.cross(ref, nrm)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    return np.hstack([t, np.ones((len(t), 1))])


class Ground:
    """Lightmap lookups on the BSP: what lies straight below a point."""

    def __init__(self, bsp_prims):
        tris, uvs, incs, pages, shaders = [], [], [], [], []
        for p in bsp_prims:
            halo = p["extras"].get("halo", {})
            page = halo.get("lightmap_index")
            if p["uv1"] is None or page is None or not halo.get("lightmap_texture"):
                continue
            ix = p["idx"].reshape(-1, 3)
            tris.append(p["pos"][ix])
            uvs.append(p["uv1"][ix])
            incs.append(p["inc"][ix] if p["inc"] is not None else np.zeros((len(ix), 3, 3)))
            pages += [page] * len(ix)
            shaders += [halo.get("material")] * len(ix)
        self.tris = np.concatenate(tris)
        self.uvs = np.concatenate(uvs)
        self.incs = np.concatenate(incs)
        self.pages = np.array(pages)
        self.shaders = shaders

    def below(self, point):
        """(page, lightmap uv) of the highest BSP surface under `point`
        (glTF metres, y up), or None."""
        hit = self.sample(point)
        return (hit["page"], hit["uv"]) if hit else None

    def sample(self, point):
        """The highest BSP surface under `point` (glTF metres, y up): its
        lightmap page and uv, incident vector, unit normal and shader, or
        None."""
        a, b, c = self.tris[:, 0], self.tris[:, 1], self.tris[:, 2]
        # Barycentric coordinates in the horizontal (x, z) plane.
        v0, v1 = b - a, c - a
        v2 = np.array([point[0], 0, point[2]]) - a * np.array([1, 0, 1])
        d00 = v0[:, 0] ** 2 + v0[:, 2] ** 2
        d01 = v0[:, 0] * v1[:, 0] + v0[:, 2] * v1[:, 2]
        d11 = v1[:, 0] ** 2 + v1[:, 2] ** 2
        d20 = v2[:, 0] * v0[:, 0] + v2[:, 2] * v0[:, 2]
        d21 = v2[:, 0] * v1[:, 0] + v2[:, 2] * v1[:, 2]
        den = d00 * d11 - d01 * d01
        ok = np.abs(den) > 1e-12
        with np.errstate(divide="ignore", invalid="ignore"):
            v = (d11 * d20 - d01 * d21) / den
            w = (d00 * d21 - d01 * d20) / den
            u = 1 - v - w
        inside = ok & (u >= -1e-4) & (v >= -1e-4) & (w >= -1e-4)
        if not inside.any():
            return None
        with np.errstate(invalid="ignore"):
            h = u * a[:, 1] + v * b[:, 1] + w * c[:, 1]
        # The highest surface at or a little above the origin (objects sit
        # on the ground; a roof far above does not light them).
        cand = inside & (h <= point[1] + 0.5)
        if not cand.any():
            cand = inside
        i = np.where(cand)[0][np.argmax(h[cand])]
        bary = np.array([u[i], v[i], w[i]])
        normal = np.cross(b[i] - a[i], c[i] - a[i])
        normal /= max(np.linalg.norm(normal), 1e-12)
        if normal[1] < 0:
            normal = -normal
        return {"page": int(self.pages[i]), "uv": bary @ self.uvs[i], "inc": bary @ self.incs[i],
                "normal": normal, "shader": self.shaders[i]}


# CE's lighting for an object with no ground under it (default_object_lighting):
# ambient, then (colour, direction towards the light) pairs, in glTF axes.
DEFAULT_OBJECT_LIGHTING = (np.full(3, 0.2), [
    (np.ones(3), np.array([0.57735, 0.57735, -0.57735])),
    (np.array([0.4, 0.4, 0.5]), np.array([0.0, -1.0, 0.0])),
], np.ones(3))


def object_lighting(ground, centre, radius, texel, base_colour):
    """CE's distant lighting for an object (lights_prepare_for_object_static):
    the ground straight under its bounding sphere's centre and under four
    points 0.7071 of its radius out diagonally, averaged; from that, an
    ambient of 0.4 L + 0.03, a light of the lightmap colour L from the
    incident direction, and a bounce of the ground's base colour times L's
    brightness, travelling up off the ground (so it lights what faces down).
    Returns (ambient, [(colour, direction towards the light), ...], reflection
    tint), or None when nothing lies below. The tint is what CE scales an
    object's reflection by: clamp(3 D + 0.5) * clamp(2 L + 0.25) in colour,
    times clamp(1.5 brightness + 0.25).

    CE baked its lightmaps with the objects in place, so the ground straight
    under a large one is its own shadow, as it is in CE."""
    k = 0.70710678 * radius
    points = [centre] + [centre + np.array([sx * k, 0.0, sz * k]) for sx in (-1, 1) for sz in (-1, 1)]
    hits = [h for h in (ground.sample(p) for p in points) if h]
    if not hits:
        return None
    light = np.mean([texel(h["page"], h["uv"]) for h in hits], axis=0)
    floor = np.mean([base_colour(h["shader"]) for h in hits], axis=0)
    inc = np.sum([h["inc"] for h in hits], axis=0)
    towards = inc / np.linalg.norm(inc) if np.linalg.norm(inc) > 1e-6 else np.array([0.0, 1.0, 0.0])
    up = np.sum([h["normal"] for h in hits], axis=0)
    up /= max(np.linalg.norm(up), 1e-12)
    brightness = float(light @ np.array([0.299, 0.587, 0.114]))
    tint = np.clip(3.0 * floor + 0.5, 0.0, 1.0) * np.clip(2.0 * light + 0.25, 0.0, 1.0)
    tint *= min(1.0, 1.5 * brightness + 0.25)
    return 0.4 * light + 0.03, [(light, towards), (floor * brightness, -up)], tint


def light_vertices(nrm, lighting):
    """Each vertex's CE lighting colour: the ambient plus every light by its
    cosine on the vertex normal."""
    ambient, lights, _ = lighting
    out = np.tile(ambient, (len(nrm), 1))
    for colour, towards in lights:
        out += np.clip(nrm @ towards, 0.0, None)[:, None] * colour[None, :]
    return out


def change_colors(entry):
    """A placement's four change colours (A-D), from its tag's permutations
    (halo2ue's `change_colors`): per slot, the first permutation whose weight
    reaches a value drawn from the placement's position (the weights are
    running cut-offs, as in CE), at a blend between its bounds drawn the same
    way. Our own hash of the position, not CE's, so the mix matches CE's and
    a given crate's colour may not. Unclaimed and missing slots are white."""
    out = [np.ones(3) for _ in range(4)]
    x, y, z = (float(v) for v in entry.get("pos", (0.0, 0.0, 0.0)))
    for k, slot in enumerate((entry.get("change_colors") or [])[:4]):
        def draw(salt):
            v = math.sin(x * 12.9898 + y * 78.233 + z * 37.719 + 17.17 * k + salt) * 43758.5453
            return v - math.floor(v)
        pick, blend = draw(0.0), draw(5.31)
        for perm in slot.get("permutations") or []:
            if perm["weight"] >= pick:
                lo, hi = np.array(perm["lower"], dtype=float), np.array(perm["upper"], dtype=float)
                out[k] = np.clip(lo + (hi - lo) * blend, 0.0, 1.0)
                break
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("staging")
    ap.add_argument("out")
    ap.add_argument("--translucent", help="write the transparent shaders' sections (schi, scex, swat: the sky, "
                                          "lights, teleporter fields) here instead, as a mesh of their own")
    ap.add_argument("--sky", help="write the sky's sections here instead, as a mesh of their own (with "
                                  "--translucent: the sky is kilometres across, and sharing one normalised mesh "
                                  "with the map's transparent pieces cost those centimetres of precision)")
    ap.add_argument("--sky-radius", type=float, default=3000.0,
                    help="metres from the map centre to the sky's nearest layer (default 3000)")
    a = ap.parse_args()

    bsp_g, bsp_buf = load_gltf(os.path.join(a.staging, "bsp", "bsp_0.gltf"))
    bsp = primitives(bsp_g, bsp_buf)
    ground = Ground(bsp)
    lightmap_pages = {}
    for p in bsp:
        h = p["extras"].get("halo", {})
        if h.get("lightmap_texture"):
            lightmap_pages[h["lightmap_index"]] = h["lightmap_texture"]

    from PIL import Image

    page_pixels = {}

    def texel(page, uv):
        """A lightmap texel's colour, 0..1 (grey when the page is missing)."""
        if page not in page_pixels:
            path = os.path.join(a.staging, "textures", lightmap_pages.get(page) or "")
            try:
                page_pixels[page] = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0
            except OSError:
                page_pixels[page] = None
        px = page_pixels[page]
        if px is None:
            return np.full(3, 0.5)
        hgt, wid = px.shape[:2]
        x = min(wid - 1, max(0, int(uv[0] % 1.0 * wid)))
        y = min(hgt - 1, max(0, int(uv[1] % 1.0 * hgt)))
        return px[y, x]

    shaders = json.load(open(os.path.join(a.staging, "materials.json"), encoding="utf-8"))
    base_colours = {}

    def base_colour(shader):
        """The mean colour of a shader's base map (CE reads the floor's base
        map under the object for its bounce light), grey without one."""
        if shader not in base_colours:
            info = shaders.get(shader) or {}
            png = info.get("base_map") or (info.get("shader") or {}).get("base_map")
            try:
                px = np.asarray(Image.open(os.path.join(a.staging, "textures", png)).convert("RGB"), dtype=np.float64)
                base_colours[shader] = px.reshape(-1, 3).mean(axis=0) / 255.0
            except (OSError, TypeError):
                base_colours[shader] = np.full(3, 0.5)
        return base_colours[shader]

    # One 4x4 block of the object lighting page per placement, sampled at its
    # centre so the bilinear filter only ever mixes the block's own texels.
    # The page is eight columns of such blocks, the same block in each: the
    # placement's light, its reflection tint, then its change colours A-D
    # (the environment master reads them at fixed offsets of 1/8).
    BLOCK, PER_ROW, COLUMNS = 4, 16, 8
    object_texels, object_prims = [], []

    placement = json.load(open(os.path.join(a.staging, "placement.json"), encoding="utf-8"))
    out = list(bsp)
    placed, unlit = 0, 0
    cache = {}
    skies_seen = 0
    for e in placement["entries"]:
        if e.get("kind") not in ("scenery", "light_fixture", "sky") or not e.get("model"):
            continue
        if e["kind"] == "sky":
            # A scenario can list several skies (Gephyrophobia: its night
            # sky, then dusk three times); its BSP draws the first.
            skies_seen += 1
            if skies_seen > 1:
                continue
        path = os.path.join(a.staging, e["model"])
        if not os.path.exists(path):
            print(f"  missing {e['model']}", file=sys.stderr)
            continue
        if path not in cache:
            cache[path] = primitives(*load_gltf(path))
        if e["kind"] in ("scenery", "light_fixture"):
            r = ce_rotation(*e.get("rot", [0, 0, 0]))
            t = ce_to_gltf(e["pos"])
            # The bounding sphere, which CE samples the ground under.
            ext = np.concatenate([p["pos"] @ r.T for p in cache[path]])
            centre = (ext.min(axis=0) + ext.max(axis=0)) / 2 if len(ext) else np.zeros(3)
            radius = float(np.max(np.linalg.norm(ext - centre, axis=1))) if len(ext) else 0.5
            lighting = object_lighting(ground, t + centre, radius, texel, base_colour)
            if lighting is None:
                unlit += 1
                lighting = DEFAULT_OBJECT_LIGHTING
            prims = []
            for p in cache[path]:
                pos = p["pos"] @ r.T + t
                nrm = p["nrm"] @ r.T
                prims.append({"pos": pos, "nrm": nrm, "uv0": p["uv0"], "idx": p["idx"],
                              "tan": tangents_for(nrm), "material": f"{p['material']}__lmobj",
                              "extras": {"halo": {**p["extras"].get("halo", {}), "lightmap_index": "objects",
                                                  "lightmap_texture": OBJECT_LIGHTING_PAGE}}})
            # The texel holds the object's brightest lighting; each vertex's
            # incident direction is tilted off its normal until their dot is
            # the vertex's share of that, and at full weight the master's
            # bumped-lightmap term, sat(N.L), gives it back.
            lit = [light_vertices(q["nrm"], lighting) for q in prims]
            peak = np.clip(np.max(np.concatenate(lit), axis=0) if prims else np.ones(3), 1e-3, 1.0)
            for q, colour in zip(prims, lit):
                share = np.clip((colour @ LUMA) / float(peak @ LUMA), 0.0, 1.0)[:, None]
                q["inc"] = share * q["nrm"] + np.sqrt(1.0 - share * share) * q["tan"][:, :3]
                q["block"] = len(object_texels)
                out.append(q)
            object_texels.append([peak, lighting[2]] + change_colors(e))
            object_prims += prims
            placed += 1
        else:
            prims = cache[path]
            allpos = np.concatenate([p["pos"] for p in prims])
            # A CE sky is modelled around the viewer at its origin, hundreds
            # of kilometres out; it is scaled about that origin, so every
            # layer keeps its distance relative to the others.
            centre = np.zeros(3)
            nearest = np.min(np.linalg.norm(allpos, axis=1))
            scale = a.sky_radius / max(nearest, 1e-3)
            bsp_pos = np.concatenate([p["pos"] for p in bsp])
            map_centre = (bsp_pos.max(0) + bsp_pos.min(0)) / 2
            # First in the mesh: translucent sections of one mesh draw in
            # section order, and the sky must be under everything in front
            # of it (the teleporter fields, the lights).
            for k, p in enumerate(prims):
                n = len(p["pos"])
                out.insert(k, {"pos": (p["pos"] - centre) * scale + map_centre, "nrm": p["nrm"], "uv0": p["uv0"],
                            "idx": p["idx"], "tan": tangents_for(p["nrm"]), "inc": np.zeros((n, 3)),
                            "uv1": np.zeros((n, 2)), "material": f"{p['material']}__sky",
                            "extras": {"halo": {**p["extras"].get("halo", {}), "lightmap_index": None,
                                                "lightmap_texture": None, "sky": True}}})
            print(f"  sky {os.path.basename(path)}: scale {scale:.4f}, nearest layer {a.sky_radius:.0f} m, "
                  f"farthest {np.max(np.linalg.norm(allpos, axis=1)) * scale:.0f} m")

    if object_texels:
        column = BLOCK * PER_ROW
        wid = column * COLUMNS
        rows = -(-len(object_texels) // PER_ROW)
        hgt = 1 << max(2, (rows * BLOCK - 1).bit_length())
        page = np.zeros((hgt, wid, 3), dtype=np.uint8)
        for k, colours in enumerate(object_texels):
            y, x = divmod(k, PER_ROW)
            for c, colour in enumerate(colours):
                x0 = c * column + x * BLOCK
                page[y * BLOCK:(y + 1) * BLOCK, x0:x0 + BLOCK] = np.round(np.clip(colour, 0.0, 1.0) * 255.0)
        Image.fromarray(page, "RGB").save(os.path.join(a.staging, "textures", OBJECT_LIGHTING_PAGE))
        for q in object_prims:
            y, x = divmod(q.pop("block"), PER_ROW)
            uv = ((x + 0.5) * BLOCK / wid, (y + 0.5) * BLOCK / hgt)
            q["uv1"] = np.tile(uv, (len(q["pos"]), 1))
        print(f"  {len(object_texels)} object lighting texel(s) -> textures/{OBJECT_LIGHTING_PAGE} ({wid}x{hgt})")

    out = with_passes(out, shaders)

    if a.translucent:
        # A mesh enters Unreal's translucency pass only if its own material
        # slots ask for it, and a rewritten mesh keeps its donor's one slot:
        # transparent sections must be a mesh of their own, whose slot 0 is
        # one of them (the sky first, so it draws under the rest).
        clear = [p for p in out if p["extras"].get("halo", {}).get("shader_class") in TRANSPARENT]
        out = [p for p in out if p["extras"].get("halo", {}).get("shader_class") not in TRANSPARENT]
        if a.sky:
            # The sky is kilometres across: normalised into one donor shape
            # together, the map's teleporter fields and light strips lost
            # their precision and sat off their walls (Danger Canyon,
            # 2026-10-01). It is a mesh of its own, drawn first by its
            # translucency sort priority instead of its section order.
            is_sky = lambda p: p["extras"].get("halo", {}).get("sky")
            sky = [p for p in clear if is_sky(p)] + [p for p in out if is_sky(p)]
            clear = [p for p in clear if not is_sky(p)]
            out = [p for p in out if not is_sky(p)]
            write_gltf(sky, a.sky)
            print(f"  {len(sky)} sky primitive(s) -> {a.sky}")
        write_gltf(clear, a.translucent)
        print(f"  {len(clear)} transparent primitive(s) -> {a.translucent}")
    write_gltf(out, a.out)
    print(f"{len(bsp)} BSP section(s) + {placed} scenery placement(s) ({unlit} with no ground below) "
          f"-> {len(out)} primitive(s) in {a.out}")


def extra_passes(shader):
    """The passes a CE shader draws before its own, each a copy of its
    surface with a material of its own: water flag 1 (base map colour
    modulates background) multiplies the frame by the base map first; glass
    tints the frame, then adds its reflection, before its diffuse pass."""
    t = (shader or {}).get("shader", {}).get("tag") or {}
    cls = (shader or {}).get("shader_class")
    if cls == "swat" and t.get("flags", 0) & 2:
        return ["background"]
    if cls == "sgla" and t:
        # Glass: the tint pass when a tint map or colour is set, the
        # reflection pass when a brightness and a reflection map are; the
        # surface itself is the diffuse pass, last.
        passes = []
        if t.get("background_tint_map") or any(t.get("background_tint_color") or []):
            passes.append("tint")
        if (t.get("perpendicular_brightness", 0) > 0 or t.get("parallel_brightness", 0) > 0) and t.get("reflection_map"):
            passes.append("reflection")
        return passes
    return []


def with_passes(prims, shaders):
    """Each primitive preceded by a copy per extra pass (`extra_passes`),
    named <material>__<pass> with `pass` in its halo extras: sections of one
    mesh draw in order, so a pass drawn first comes first."""
    out = []
    for p in prims:
        halo = p["extras"].get("halo", {})
        for name in extra_passes(shaders.get(halo.get("material", ""))):
            out.append({**p, "material": f"{p['material']}__{name}",
                        "extras": {**p["extras"], "halo": {**halo, "pass": name}}})
        out.append(p)
    return out


def write_gltf(prims, path):
    materials, mat_index = [], {}
    blob = bytearray()
    views, accessors, meshes_prims = [], [], []

    def add(arr, kind, comp, target=None):
        arr = np.ascontiguousarray(arr)
        while len(blob) % 4:
            blob.append(0)
        off = len(blob)
        blob.extend(arr.tobytes())
        view = {"buffer": 0, "byteOffset": off, "byteLength": arr.nbytes}
        if target:
            view["target"] = target
        views.append(view)
        acc = {"bufferView": len(views) - 1, "componentType": comp, "count": len(arr), "type": kind}
        if kind == "VEC3" and comp == 5126:
            acc["min"] = arr.min(0).tolist()
            acc["max"] = arr.max(0).tolist()
        accessors.append(acc)
        return len(accessors) - 1

    for p in prims:
        name = p["material"]
        if name not in mat_index:
            mat_index[name] = len(materials)
            materials.append({"name": name, "extras": p.get("extras", {})})
        f32 = lambda x: np.asarray(x, dtype=np.float32)
        attrs = {
            "POSITION": add(f32(p["pos"]), "VEC3", 5126, 34962),
            "NORMAL": add(f32(p["nrm"]), "VEC3", 5126, 34962),
            "TANGENT": add(f32(p["tan"]), "VEC4", 5126, 34962),
            "TEXCOORD_0": add(f32(p["uv0"]), "VEC2", 5126, 34962),
            "TEXCOORD_1": add(f32(p["uv1"]), "VEC2", 5126, 34962),
            "_INCIDENT": add(f32(p["inc"]), "VEC3", 5126, 34962),
        }
        idx = add(np.asarray(p["idx"], dtype=np.uint32), "SCALAR", 5125, 34963)
        meshes_prims.append({"attributes": attrs, "indices": idx, "material": mat_index[name], "mode": 4})

    bin_name = os.path.splitext(os.path.basename(path))[0] + ".bin"
    with open(os.path.join(os.path.dirname(os.path.abspath(path)), bin_name), "wb") as f:
        f.write(blob)
    g = {
        "asset": {"version": "2.0", "generator": "merge_ce_scene.py"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "scene"}],
        "meshes": [{"name": "scene", "primitives": meshes_prims}],
        "materials": materials,
        "buffers": [{"uri": bin_name, "byteLength": len(blob)}],
        "bufferViews": views,
        "accessors": accessors,
    }
    json.dump(g, open(path, "w", encoding="utf-8"))


if __name__ == "__main__":
    main()
