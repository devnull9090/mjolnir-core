"""Generate the Forge guide's SVG plans from real source collision geometry.

Run from any directory with Python's standard library:
    python tools/forge/render_layout_plans.py

The courtyard matches docs/forge_guide.md. Crossline uses the current level's
metre-converted placements and each convex hull's projected footprint, retaining
door and junction openings. It is a top-down plan, not a height or navigation map.
Identical outputs go to the documentation and blog asset directories.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/images/forge-showcase"
BLOG = ROOT / "hub/public/blog-images/forge-building"
BG = "#0b131c"
PANEL = "#111f2b"
INK = "#e8f0f4"
MUTED = "#9bb0bd"
CYAN = "#69d8e5"
GOLD = "#e9b969"
GREEN = "#94e791"


class Svg:
    def __init__(self, width, height, title, description):
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{html.escape(title)}</title><desc id="desc">{html.escape(description)}</desc>',
            '<defs><marker id="arrow" viewBox="0 0 8 8" refX="4" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L8 4L0 8Z" fill="#9bb0bd"/></marker></defs>',
            f'<rect width="{width}" height="{height}" fill="{BG}"/>',
            '<g font-family="Arial, Helvetica, sans-serif">',
        ]

    def raw(self, s):
        self.parts.append(s)

    def text(self, x, y, text, size=16, color=INK, weight="normal", anchor="start", extra=""):
        self.raw(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}" {extra}>{html.escape(str(text))}</text>')

    def rect(self, x, y, w, h, fill, stroke="none", radius=0, extra=""):
        self.raw(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" {extra}/>')

    def line(self, x1, y1, x2, y2, color=MUTED, width=1, extra=""):
        self.raw(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}" {extra}/>')

    def poly(self, points, fill, stroke, width=.7, extra=""):
        p = " ".join(f"{x:.3f},{y:.3f}" for x, y in points)
        self.raw(f'<polygon points="{p}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" stroke-linejoin="round" {extra}/>')

    def circle(self, x, y, r, fill, stroke="none", extra=""):
        self.raw(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" {extra}/>')

    def finish(self):
        value = "\n".join(self.parts + ["</g></svg>"]) + "\n"
        ET.fromstring(value)
        return value


def hull2(points):
    points = sorted(set((round(v[0], 8), round(v[1], 8)) for v in points))
    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lo, hi = [], []
    for seq, out in ((points, lo), (reversed(points), hi)):
        for p in seq:
            while len(out) >= 2 and cross(out[-2], out[-1], p) <= 0:
                out.pop()
            out.append(p)
    return lo[:-1]+hi[:-1]


def source(pack):
    path = ROOT / "forge-packs" / pack / "source/geometry.json"
    return {p["id"]: p for p in json.loads(path.read_text())["pieces"]}


def transform(point, origin, yaw):
    a = math.radians(yaw)
    return (origin[0]+point[0]*math.cos(a)-point[1]*math.sin(a),
            origin[1]+point[0]*math.sin(a)+point[1]*math.cos(a))


def draw_piece(svg, piece, origin, yaw, screen, fill, edge, width=.7):
    svg.raw(f'<g><title>{html.escape(piece["name"])}; bottom Z {origin[2]:g} m</title>')
    for hull in piece["collision"]["hulls"]:
        footprint = hull2(hull["vertices"])
        if len(footprint) >= 3:
            svg.poly([screen(*transform(v, origin, yaw)) for v in footprint], fill, edge, width)
    svg.raw('</g>')


def north(svg, x, y):
    svg.line(x, y+35, x, y, CYAN, 2)
    svg.poly([(x, y-5), (x-5, y+7), (x+5, y+7)], CYAN, CYAN)
    svg.text(x, y-17, "N / +Y", 12, CYAN, "bold", "middle")


def courtyard():
    pieces = source("foundry-wide")
    s = Svg(1200, 900, "Build a raised courtyard", "Ten real Foundry Wide pieces. A sixteen-metre square deck sits two metres above ground, reached by an eight-metre ramp. Overall footprint sixteen by twenty-four metres. Four-metre planning grid.")
    s.text(54, 54, "FORGE / BUILD RECIPE 01", 13, CYAN, "bold", extra='letter-spacing="2"')
    s.text(54, 99, "A raised courtyard", 38, INK, "bold")
    s.text(54, 130, "10 pieces · 16 × 16 m deck · 2 m rise · open sky", 18, MUTED)
    s.rect(270, 165, 540, 615, PANEL, "#243b4b", 12)
    scale = 22
    def screen(x, y): return 550+x*scale, 380-y*scale
    for x in range(-8, 9, 4):
        s.line(*screen(x, -16), *screen(x, 8), "#263b48", 1)
    for y in range(-16, 9, 4):
        s.line(*screen(-8, y), *screen(8, y), "#263b48", 1)
    rows = [("floor_4x4", (0, 0, 1.5), 0, "#244b59", CYAN),
            ("ramp_wide", (0, -12, 0), 0, "#665232", GOLD)]
    rows += [("wall", (x, 7.5, 2), 0, "#6a7c85", "#c6d1d6") for x in (-4, 4)]
    rows += [("wall", (x, y, 2), 90, "#6a7c85", "#c6d1d6") for x in (-7.5, 7.5) for y in (-4, 4)]
    rows += [("cover", (x, -7, 2), 0, "#80673c", GOLD) for x in (-6, 6)]
    assert len(rows) == 10
    for ident, origin, yaw, fill, edge in rows:
        draw_piece(s, pieces[ident], origin, yaw, screen, fill, edge, 1.2)
    for x in (-4, 0, 4):
        s.line(*screen(x, -7), *screen(x, 7), "#47717b", 1, 'stroke-dasharray="3 5"')
    for y in (-4, 0, 4):
        s.line(*screen(-7, y), *screen(7, y), "#47717b", 1, 'stroke-dasharray="3 5"')
    s.line(*screen(0, -15), *screen(0, -9), GOLD, 3, 'marker-end="url(#arrow)"')
    s.text(550, 353, "COURTYARD", 20, INK, "bold", "middle")
    s.text(550, 379, "finished floor +2 m", 16, CYAN, anchor="middle")
    s.text(550, 618, "UP", 14, GOLD, "bold", "middle")
    s.text(550, 706, "8 m run / 2 m rise", 14, GOLD, anchor="middle")
    s.text(550, 757, "GROUND APPROACH", 12, MUTED, "bold", "middle", 'letter-spacing="1.5"')
    # Overall dimensions and witnesses.
    s.line(374, 184, 726, 184, MUTED, 1, 'marker-start="url(#arrow)" marker-end="url(#arrow)"')
    s.rect(516, 173, 68, 20, PANEL)
    s.text(550, 189, "16 m", 15, INK, "bold", "middle")
    for x in (374, 726): s.line(x, 195, x, 204, MUTED)
    s.line(323, 204, 323, 732, MUTED, 1, 'marker-start="url(#arrow)" marker-end="url(#arrow)"')
    for y in (204, 732): s.line(332, y, 365, y, MUTED)
    s.text(308, 468, "24 m overall", 14, INK, anchor="middle", extra='transform="rotate(-90 308 468)"')
    north(s, 773, 231)
    # Editorial legend tied to physical piece quantities.
    s.text(850, 202, "THE TEN PIECES", 13, CYAN, "bold", extra='letter-spacing="1.5"')
    entries = [
        ("01", "One large floor", "16 × 16 × 0.5 m", "Underside at +1.5 m", CYAN),
        ("02", "One broad ramp", "8 × 8 m · rise 2 m", "High edge meets floor top", GOLD),
        ("03", "Six full walls", "8 × 1 × 3 m each", "Two on each of three sides", "#c6d1d6"),
        ("04", "Two low cover pieces", "4 × 1.5 × 1 m each", "Leave the 8 m entrance clear", GOLD),
    ]
    for i, (n, title, a, b, color) in enumerate(entries):
        y = 240+i*91
        s.text(850, y, n, 12, color, "bold")
        s.text(880, y, title, 17, INK, "bold")
        s.text(880, y+25, a, 14, color)
        s.text(880, y+46, b, 13, MUTED)
    s.text(850, 640, "KEEP THE JOIN FLUSH", 13, CYAN, "bold", extra='letter-spacing="1"')
    s.poly([(850, 724), (950, 699), (950, 724)], "#665232", GOLD)
    s.rect(950, 699, 180, 6.25, "#244b59", CYAN)
    s.line(840, 724, 1140, 724, "#455863", 1, 'stroke-dasharray="3 4"')
    s.text(850, 747, "ramp nose 0 m", 12, MUTED)
    s.text(1130, 682, "walking surface +2 m", 13, CYAN, anchor="end")
    s.text(1130, 770, "0.5 m slab → underside +1.5 m", 13, MUTED, anchor="end")
    s.text(54, 824, "PLAN, NOT AN IN-GAME SCREENSHOT", 12, CYAN, "bold", extra='letter-spacing="1"')
    s.text(54, 851, "4 m grid. All heights measured from ground. Piece origins and dimensions match the building guide.", 16, MUTED)
    s.text(54, 878, "Forge has placement snapping, not automatic edge docking or numeric coordinate entry.", 14, MUTED)
    return s.finish()


def crossline():
    level_path = ROOT / "forge-maps/crossline/crossline.level.json"
    layout_path = ROOT / "forge-maps/crossline/crossline.layout.json"
    level = json.loads(level_path.read_text())
    layout = json.loads(layout_path.read_text())
    packs = {name: source(name) for name in ("foundry", "foundry-wide")}
    assert layout["dimensions_m"][:2] == [96, 160], layout["dimensions_m"]
    s = Svg(1200, 1120, "Crossline: routes and utility lanes", "Source-derived top-down plan of Crossline 0.3, ninety-six by one-hundred-sixty metres. Footprints show the actual authored construction pieces; raised routes and ground routes overlap in plan. Blue base is north, red base south. Galleries are four-and-a-half metres high.")
    s.raw(f'<metadata>Source SHA-256: {hashlib.sha256(level_path.read_bytes()).hexdigest()}; metres Z-up; UE centimetres and yaw converted before projection.</metadata>')
    s.text(54, 54, "FORGE / CROSSLINE 0.3", 13, CYAN, "bold", extra='letter-spacing="2"')
    s.text(54, 99, "Room to build. Routes to explore.", 36, INK, "bold")
    s.text(54, 131, "96 × 160 m · Red vs Blue bases · native utility demonstration lanes", 18, MUTED)
    def screen(x, y): return 600+x*5, 570-y*5
    s.rect(360, 170, 480, 800, PANEL, "#38505f")
    for x in range(-48, 49, 8): s.line(*screen(x, -80), *screen(x, 80), "#1e313e", .7)
    for y in range(-80, 81, 8): s.line(*screen(-48, y), *screen(48, y), "#1e313e", .7)
    # Show the route on the ground before plotting raised geometry over it.
    s.rect(580, 210, 40, 720, "#182b38")
    s.line(*screen(0, -72), *screen(0, 72), "#536f7d", 1, 'stroke-dasharray="4 7"')
    objects = level["blam"]["objects"]
    def object_point(index):
        pos = objects[index]["pos"]
        return pos[0]/100, -pos[1]/100
    def showcase_point(name):
        return object_point(next(row["object_index"] for row in layout["showcase"] if row["name"] == name))
    rows = []
    for i, obj in enumerate(objects):
        tag = obj.get("tag", "").split("\\")
        if len(tag) < 2 or tag[-2] not in packs or tag[-1] not in packs[tag[-2]]:
            continue
        p = packs[tag[-2]][tag[-1]]
        origin = (obj["pos"][0]/100, -obj["pos"][1]/100, obj["pos"][2]/100)
        yaw = -obj.get("rot", [0, 0, 0])[1]
        assert obj.get("rot", [0, 0, 0])[0] == obj.get("rot", [0, 0, 0])[2] == 0
        rows.append((origin[2]+p["dimensions_m"][2], i, p, origin, yaw))
    for _, _, p, origin, yaw in sorted(rows):
        ident, category = p["id"], p["category"]
        fill, edge = "#526874", "#8ea7b2"
        if category in ("floors", "bridges"):
            fill, edge = ("#294959", "#678b9a") if origin[2] >= 3 else ("#263b46", "#526f7c")
            if abs(origin[1]) >= 48 and abs(origin[0]) <= 24:
                fill, edge = ("#244b72", "#598bc1") if origin[1] > 0 else ("#63353b", "#ba6a70")
        if "ramp" in ident or ident == "stairs": fill, edge = "#5e5036", GOLD
        if "glass" in ident or ident == "window_glazed": fill, edge = "#326674", CYAN
        if "teleporter" in ident: fill, edge = "#426545", GREEN
        if "door_panel" in ident or ident == "door_vehicle_panel": fill, edge = "#a67e40", GOLD
        if ident == "lift_station": fill, edge = "#286c79", CYAN
        if ident in ("wall", "wall_long", "wall_half", "railing"):
            fill, edge = "#69777e", "#a2b0b7"
        draw_piece(s, p, origin, yaw, screen, fill, edge)
    # Native markers: symbols overlay the visible architectural footprint.
    for obj in objects:
        ident = obj.get("tag", "").split("\\")[-1]
        if ident != "player_spawn": continue
        team = obj.get("set", {}).get("multiplayer data.owner team", "neutral")
        color = {"attacker": "#8ab6f6", "defender": "#ef8b91"}.get(team, "#f1e2b0")
        x, y = screen(obj["pos"][0]/100, -obj["pos"][1]/100)
        s.circle(x, y, 3, BG, color, 'stroke-width="1.4"')
    for row in layout["teleporters"]:
        obj = objects[row["object_index"]]
        x, y = screen(obj["pos"][0]/100, -obj["pos"][1]/100)
        s.circle(x, y, 10, BG, GREEN, 'stroke-width="2"')
        s.text(x, y+4, "T", 12, GREEN, "bold", "middle")
    def plate(x, y, title, sub, color):
        s.rect(x-90, y-21, 180, 47, BG, "none", 4, 'fill-opacity=".88"')
        s.text(x, y-2, title, 17, color, "bold", "middle")
        s.text(x, y+17, sub, 12, MUTED, anchor="middle")
    plate(*screen(0, 58), "BLUE BASE", "deck +4.5 m", "#99c3fa")
    plate(*screen(0, -58), "RED BASE", "deck +4.5 m", "#f2a0a3")
    def callout(side, y, point, title, sub, color=CYAN):
        tx = 55 if side == "left" else 887
        elbow = 323 if side == "left" else 865
        endpoint = 275 if side == "left" else 880
        x, sy = screen(*point)
        s.raw(f'<polyline points="{x},{sy} {elbow},{sy} {elbow},{y+8} {endpoint},{y+8}" fill="none" stroke="{color}" stroke-width="1.2"/>')
        s.circle(x, sy, 3.5, color)
        s.text(tx, y, title, 17, INK, "bold")
        s.text(tx, y+24, sub, 13, MUTED)
    callout("left", 259, showcase_point("cross bridge"), "Bridge shape tour", "T, cross and open-corner decks")
    callout("left", 452, showcase_point("glazed window"), "Glass lane", "Solid transparent panes", CYAN)
    callout("left", 645, showcase_point("infantry door moving panel"), "Infantry door", "4 × 3.5 m opening", GOLD)
    callout("left", 808, showcase_point("vehicle gate moving panel"), "Vehicle gate", "8 × 5.5 m opening", GOLD)
    callout("right", 223, object_point(layout["teleporters"][1]["object_index"]), "Paired teleporters", "Green fields + native markers", GREEN)
    ramp_route = next(r for r in layout["routes"] if r["name"] == "blue main ramp 8")
    callout("right", 366, ramp_route["points_m"][2][:2], "Broad base ramps", "8 m wide · 4 m rise / 32 m run", GOLD)
    callout("right", 486, object_point(layout["lifts"][0]["object_index"]), "Lift + landing", "0.5 m deck → 4.5 m gallery", CYAN)
    gallery = next(r for r in layout["routes"] if r["name"] == "east gallery")["points_m"]
    midpoint = tuple((gallery[0][i]+gallery[-1][i])/2 for i in range(2))
    callout("right", 615, midpoint, "Raised galleries", "Crossbridge at +4.5 m", CYAN)
    callout("right", 808, showcase_point("wide high ramp"), "Ramp experiments", "Wide, high and shallow pieces", GOLD)
    north(s, 902, 940)
    s.line(360, 990, 840, 990, MUTED, 1, 'marker-start="url(#arrow)" marker-end="url(#arrow)"')
    s.rect(566, 979, 68, 22, BG)
    s.text(600, 996, "96 m", 15, INK, "bold", "middle")
    s.text(345, 570, "160 m", 14, MUTED, anchor="middle", extra='transform="rotate(-90 345 570)"')
    s.text(55, 1034, "SOURCE-DERIVED TOP VIEW", 12, CYAN, "bold", extra='letter-spacing="1.3"')
    s.text(55, 1063, "Ground routes pass beneath raised decks. Outlines are projected piece footprints, not a single walking surface.", 15, MUTED)
    s.text(55, 1088, "8 m grid · perimeter 9 m high · small circles mark team / neutral starts · all dimensions in metres", 14, MUTED)
    return s.finish()


def main():
    for name, value in (("courtyard-plan.svg", courtyard()), ("crossline-plan.svg", crossline())):
        for out in (DOCS, BLOG):
            out.mkdir(parents=True, exist_ok=True)
            (out/name).write_text(value, encoding="utf-8", newline="\n")
        print(f"{name}: {len(value.encode('utf-8')):,} bytes; identical documentation/blog copies")


if __name__ == "__main__":
    main()
