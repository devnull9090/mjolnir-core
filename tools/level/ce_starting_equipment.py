#!/usr/bin/env python3
"""Read what a Halo CE map hands a player at spawn, for a conversion's staging.

    python tools/level/ce_starting_equipment.py <map.map> [<staging dir>]

halo2ue stages a CE map's placements but not its scenario's starting
equipment, so this reads it from the map and writes
`<staging>/starting_equipment.json`, which tools/level/gen_ce_level.py turns
into the level's `starting_equipment` (docs/ce_map_conversion.md, "Starting
equipment"). Without a staging folder it prints what it read.

What the engine does with it (MCC's halo1.dll, 0xaa6084 and 0xaa5ef8):

- A player takes the first scenario entry (scnr +0x390, 0xCC each) whose four
  game type slots (+0x04) include the game's: 12 is every game, 13 every game
  but CTF, 14 every game but CTF and Race. Its weapons are the first item
  collection's (+0x3C, six references 16 bytes apart) and the next
  collection's that gives a different weapon; a collection of several
  permutations is drawn from by weight (itmc +0x00, 0x54 each: weight +0x20,
  item +0x24).
- With no entry for the game, the weapons are the first and fifth of the
  globals' weapon list (matg +0x14C, 16 bytes each).
- The grenades come from the globals' grenade list (matg +0x128, 0x44 each:
  maximum count, then the multiplayer spawn count): each kind's spawn count,
  and the fragmentation maximum instead when plasma's spawn count is 0, as
  it is in the stock globals. The maximums shrink with the size of the
  game: 4 as the tag has them up to four players, 2 from five to eight and
  1 beyond. An entry's flags (+0x00) then take the grenades away (bit 0) or
  turn them all into plasma (bit 1).

A game variant's traits hold one count for the whole match, so `grenades`
is what a game of five to eight players gets (GRENADE_CAP): two
fragmentation grenades from the stock globals, which is also their own
multiplayer spawn count. `grenade_kinds` keeps what the tag says.

Only what a game variant with "custom" starting equipment does is read here;
CE's "generic" variants ignore the scenario's entries.
"""
import json
import os
import struct
import sys

GAME_TYPES = {0: "None", 1: "Ctf", 2: "Slayer", 3: "Oddball", 4: "King", 5: "Race", 6: "Terminator",
              12: "AllGames", 13: "AllGamesExceptCtf", 14: "AllGamesExceptCtfAndRace"}
# The most grenades of a kind a player of a five-to-eight-player game holds.
GRENADE_CAP = 2
INDEX_HEADER = 0x28
TAG_ENTRY = 0x20
NONE = 0xFFFFFFFF


class Map:
    """A CE cache file's tags: class, path and body offset by tag id."""

    def __init__(self, path):
        self.d = d = open(path, "rb").read()
        if d[:4] != b"daeh":
            raise ValueError("not a Halo CE cache file")
        self.tag_off = tag_off = struct.unpack_from("<I", d, 0x10)[0]
        tags_at, self.scenario, _, count = struct.unpack_from("<IIII", d, tag_off)
        # The tag array follows the index header; everything is addressed
        # from where the engine loads it.
        self.magic = tags_at - (tag_off + INDEX_HEADER)
        self.tags = {}
        for i in range(count):
            cls, _, _, tid, name_at, data_at = struct.unpack_from("<4s4s4sIII", d, tag_off + INDEX_HEADER + i * TAG_ENTRY)
            self.tags[tid] = (cls[::-1].decode("latin1"), self.text(name_at), data_at)

    def off(self, address):
        return address - self.magic

    def text(self, address):
        at = self.off(address)
        return self.d[at:self.d.index(b"\0", at)].decode("latin1")

    def block(self, at):
        """A block reference at file offset `at`: (count, file offset)."""
        count, address = struct.unpack_from("<II", self.d, at)
        return count, (self.off(address) if count else 0)

    def reference(self, at):
        """The tag a 16-byte reference at file offset `at` names, or None."""
        tid = struct.unpack_from("<I", self.d, at + 0x0C)[0]
        return self.tags.get(tid) if tid != NONE else None

    def of_class(self, cls):
        return [t for t in self.tags.values() if t[0] == cls]


def collection(m, tag):
    """An item collection's permutations: asset, class and weight each."""
    count, at = m.block(m.off(tag[2]))
    items = []
    for i in range(count):
        e = at + i * 0x54
        item = m.reference(e + 0x24)
        if item:
            items.append({"asset": item[1], "tag_class": item[0], "weight": struct.unpack_from("<f", m.d, e + 0x20)[0]})
    return {"item_collection": tag[1], "items": items}


def read(path):
    m = Map(path)
    scenario = m.off(m.tags[m.scenario][2])
    count, at = m.block(scenario + 0x390)
    entries = []
    for i in range(count):
        e = at + i * 0xCC
        flags = struct.unpack_from("<I", m.d, e)[0]
        collections = [collection(m, tag) for k in range(6) if (tag := m.reference(e + 0x3C + 16 * k))]
        entries.append({
            "game_types": [GAME_TYPES.get(g, f"Unknown({g})") for g in struct.unpack_from("<4h", m.d, e + 4)],
            "flags": flags, "no_grenades": bool(flags & 1), "plasma_grenades": bool(flags & 2),
            "item_collections": collections,
        })
    out = {"source": os.path.basename(path), "starting_equipment": entries}
    globals_tags = m.of_class("matg")
    if globals_tags:
        g = m.off(globals_tags[0][2])
        count, at = m.block(g + 0x128)
        kinds = [struct.unpack_from("<hh", m.d, at + i * 0x44) for i in range(min(count, 2))]
        if len(kinds) == 2:
            out["grenade_kinds"] = [{"maximum": most, "multiplayer_spawn": spawn} for most, spawn in kinds]
            (frag_max, frag), (plasma_max, plasma) = [(min(most, GRENADE_CAP), spawn) for most, spawn in kinds]
            if plasma == 0:
                frag = frag_max
            out["grenades"] = [max(min(frag, frag_max), 0), max(min(plasma, plasma_max), 0)]
        count, at = m.block(g + 0x14C)
        fallback = [w for i in (0, 4) if i < count and (w := m.reference(at + i * 16))]
        out["fallback_weapons"] = [{"asset": w[1], "tag_class": w[0]} for w in fallback]
    return out


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    out = read(sys.argv[1])
    text = json.dumps(out, indent=1) + "\n"
    if len(sys.argv) == 3:
        with open(os.path.join(sys.argv[2], "starting_equipment.json"), "w", encoding="utf-8") as f:
            f.write(text)
        print(f"{out['source']}: {len(out['starting_equipment'])} starting equipment entr"
              f"{'y' if len(out['starting_equipment']) == 1 else 'ies'}, grenades {out.get('grenades')}")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
