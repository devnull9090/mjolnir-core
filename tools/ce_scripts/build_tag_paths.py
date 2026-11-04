#!/usr/bin/env python3
"""Build ce_tag_paths.json: CE tag paths to the CU4 tags that stand for them.

    build_tag_paths.py <corpus.json> <all_tags.txt> [--stock D:/halomaps/stock_tags.json]

`corpus.json` is check_corpus.py's: it names every tag literal the maps use and
no table covers yet. `all_tags.txt` is `mjolnir list --limit 100000`.

CU4 keeps Halo 1's content under other folders, usually with the same last name
(`effects\\explosions\\medium explosion` is `.../medium_explosion`). A CE path
matches a CU4 tag of the group its literal needs when their leaf names are the
same, once case, spaces and underscores are out. Where several match, the one
sharing most folder words wins, and a tie is left out: a literal with no entry
loses its statement, which is better than the wrong effect. Only stock CE paths
are tried: a map's own tags are not in the game, whatever they are called.

CU4 script literals are `path/to/tag.group`, as shipped scripts write them.
"""
import argparse
import collections
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ce_tag_paths.json")
# A literal's value type and the CU4 group names that serve it.
GROUPS = {"sound": ["sound"], "looping_sound": ["sound_looping"], "effect": ["effect"], "damage": ["damage_effect"],
          "damage_effect": ["damage_effect"], "animation_graph": ["model_animation_graph"],
          "object_definition": ["vehicle", "weapon", "equipment", "scenery", "crate", "biped"]}


def squash(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def words(path):
    return set(re.split(r"[\\/ _]+", path.lower()))


def index(lines):
    """CU4 tags by group and squashed leaf: group -> leaf -> [path]."""
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for line in lines:
        parts = line.rstrip().split("\t")
        if len(parts) < 3 or "/Tags/" not in parts[2]:
            continue
        group = parts[0]
        path = parts[2].split("/Tags/", 1)[1]
        path = re.sub(r"\.ubulk$", "", path)
        path = path[: -(len(group) + 1)] if path.endswith("-" + group) else path
        leaf = path.rsplit("/", 1)[-1]
        out[group][squash(leaf)].append(f"{path}.{group}".lower())
    return out


def match(ce, vtype, tags):
    leaf = squash(re.split(r"[\\/]", ce)[-1])
    hits = [p for g in GROUPS.get(vtype, []) for p in tags[g].get(leaf, [])]
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    scored = sorted(((len(words(ce) & words(p)), p) for p in hits), reverse=True)
    return scored[0][1] if scored[0][0] > scored[1][0] else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("corpus")
    ap.add_argument("tags")
    ap.add_argument("--stock", default="D:/halomaps/stock_tags.json")
    a = ap.parse_args()
    with open(a.corpus, encoding="utf-8") as f:
        tally = collections.defaultdict(collections.Counter)
        for row in json.load(f)["rows"]:
            for kind, what in row["notes"].items():
                tally[kind].update(what.keys())
    with open(a.tags, encoding="utf-8") as f:
        tags = index(f)
    with open(a.stock, encoding="utf-8") as f:
        stock = json.load(f)["tags"]
    stock = {p.lower().replace("/", "\\") for paths in stock.values() for p in paths}
    paths, misses, custom = {}, collections.Counter(), collections.Counter()
    for kind, literals in tally.items():
        if not kind.startswith("no CU4 tag: "):
            continue
        vtype = kind.rsplit(": ", 1)[1]
        for ce, maps in literals.items():
            if ce.lower() not in stock:
                custom[ce] += maps
                continue
            hit = match(ce, vtype, tags)
            if hit:
                paths[ce.lower()] = hit
            else:
                misses[ce] += maps
    with open(OUT, encoding="utf-8") as f:
        table = json.load(f)
    table["paths"] = {**table["paths"], **paths}
    table["paths"] = dict(sorted(table["paths"].items()))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(table, f, indent=1)
    print(f"{len(paths)} matched, {len(misses)} stock paths with no CU4 tag, {len(custom)} custom paths")
    for ce, n in misses.most_common(15):
        print(f"  {n:4} {ce}")


if __name__ == "__main__":
    main()
