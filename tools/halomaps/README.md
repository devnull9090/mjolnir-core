# The halomaps.org archiver

[halomaps.org/hce](https://halomaps.org/hce/) is the community's archive of
Halo Custom Edition maps: a thousand and more multiplayer maps, each with its
author, upload date, size, user rating, description, the author's file notes
and screenshots. `halomaps.py` mirrors it into one folder, keeps everything
the site knows about each map as JSON, reads each `.map` for what the site
does not say, and converts the maps one at a time through
[`convert_ce_map.sh`](../level/convert_ce_map.sh), best-rated first. The point
is twofold: the original maps archived into the new game, and a survey of
what the conversion still cannot do (custom weapons, vehicles, scenery,
bipeds, machines) ordered by how many maps it touches.

```bash
python tools/halomaps/halomaps.py mirror                       # crawl, fetch, download, extract, catalog
python tools/halomaps/halomaps.py catalog --sort rating --top 30
python tools/halomaps/halomaps.py convert --next --pack        # the best unconverted map
python tools/halomaps/halomaps.py report                       # edge cases across the archive
python tools/halomaps/halomaps.py status
python tools/halomaps/halomaps.py show 525
```

Python 3 with no dependencies. The archive root is `HALOMAPS_ROOT`, or
`D:/halomaps`, or `--root`. Every stage skips what is already done, so a run
can be stopped and resumed. `mirror` fetches the pages and files first and
the screenshots last, because the maps are the point and a page's thirty
user screenshots take longer than its file. The five multiplayer sections
hold about 4,300 entries (2,256 in Halo CE Maps alone, 1,440 modified, 527
with AI), so a full mirror is a matter of hours.

## The stages

| Stage | Does | Writes |
|---|---|---|
| `crawl` | walks the listing pages of the multiplayer sections (`--sid` for others: 10 Halo CE Maps, 39 w/ AI, 24 Modified, 40 YELO, 29 Machinima; 41, 27, 35, 37 are single player, 11 the official files) | one record per map with the listing's fields; the pages under `listings/` |
| `fetch` | each map's detail page: rating, category, author, date, size, description, file notes, the download form's hash, the site's two screenshots and the users' (`--no-screenshots` leaves the pictures to `screenshots`) | `maps/<fid>/page.html`, `screenshots/`, the record |
| `screenshots` | the pictures of pages fetched without them | `maps/<fid>/screenshots/` |
| `download` | the file, through the download form (`--max-mb` skips the big ones for a first pass; they are picked up by the next run without it) | `maps/<fid>/<file as served>`, with its size and sha256 in the record |
| `extract` | unpacks it (zip in Python; rar, 7z and self-extracting exe through 7-Zip at `SEVENZIP` or `C:\Program Files\7-Zip\7z.exe`; one archive nested in another is unpacked beside it) and reads every `.map` and `.yelo` with `cemap.py` | `maps/<fid>/files/`, the record's `archive` block |
| `catalog` | one row per record, sortable (`--sort rating|screenshots|date|size|name|custom|fid`, `--convertible` for the queue) | `catalog.json`, `catalog.csv` |
| `convert` | one map through `convert_ce_map.sh` (`--fid`, or `--next` for the best unconverted; `--count N` for a run of them, stopped by a `convert.stop` file in the root; `--install` to put it in the game; `--pack` for the `.mjolnir` map pack, `--sign` to sign it) | `maps/<fid>/convert/<CODE>/` with the staging, containers, `convert.log`, README and pack; the record's `conversions` |
| `pack` | the map pack of a finished conversion again (`--fid`, `--code`, `--version`, `--sign`), without converting again | the `.mjolnir` beside the conversion |
| `report` | custom tags by class across every unpacked map, and what every conversion dropped, warned about or failed on (`--reparse` reads the kept logs again with the current parser) | `report.json`, `report.md` |

Requests go one at a time with a pause between them (`--delay`, 1.5 s;
`--image-delay` 0.4 s for screenshots), with a user agent that names this
tool, and a failed request is retried with backoff. The whole mirror is about
three thousand requests.

## The record

`maps/<fid>/meta.json`, keyed by the site's file id. The top level carries
the fields worth sorting on; the blocks carry each stage's detail.

```jsonc
{
  "fid": 525, "url": "https://halomaps.org/hce/detail.cfm?fid=525",
  "title": "Green Canyon", "author": "Arteen", "date": "2004-10-11",
  "rating": 8.5, "rating_text": "8.5",            // "pending" when nobody has rated it
  "section": {"sid": 10, "name": "Halo CE Maps"}, "category": "Halo CE Maps",
  "size_text": "11.8M", "size": 11824351,
  "description": "An outdoor map with modded weapons",
  "notes": "Map: Green Canyon\nCreator: Arteen\n...",  // the author's file notes
  "listing": {...}, "detail": {...},               // as each page had them
  "screenshots": {"official": [...], "user": [...], "sources": {...}},
  "download": {"hash": "...", "file_name": "Green_Canyon.zip", "size": ..., "sha256": "...", ...},
  "archive": {"format": "zip", "entries": [...], "readmes": [...], "maps": [
    {"file": "greencanyon.map", "name": "greencanyon", "build": "01.00.00.0609",
     "engine": "custom edition", "type": "multiplayer", "tag_count": 2455, "bsps": 1,
     "protected": false, "classes": {"bitm": 448, ...},
     "custom": {"total": 61, "counts": {"weap": 9, ...},
                "tags": {"weap": ["weapons/sentinel/sentinel", ...], "vehi": [...], ...}}}]},
  "code": "GRC",                                   // the codename its conversion took
  "conversions": [{"map": "greencanyon.map", "code": "GRC", "status": "converted",
                   "seconds": 312, "report": {"dropped": [...], "warnings": [...], ...}}]
}
```

**Popularity.** The site shows no download counter, so the queue is ordered
by user rating, then by the number of user-submitted screenshots (a map
people played enough to photograph), then by upload date. `catalog --sort`
offers the rest. A record with `"skip": "<reason>"` is left out of the queue.

**What the `.map` says** (`cemap.py`, no exporter needed; it reads the
header and the tag data, a few MB of a map's tens): the header's name, build
and type; the tag index's count and class histogram; the number of structure
BSPs; whether a protection tool scrambled the index (every class `ztpt`,
every path `<zteam>`: the exporter repairs those at conversion), or only
blanked some tag names to `<protected>` (`partially_protected`, with the
count in `placeholder_paths`; those tags are counted under the survey's
`placeholders`, since nobody can tell from the name whether they are custom);
and which tags no stock map carries, by class, with the object and shader
classes listed by path. The stock set is built once from the 19 shipped
multiplayer maps and `ui.map` in `--stock-maps` (`HALOMAPS_STOCK_MAPS`,
default `~/prj/HalcyonRing/maps`) into `stock_tags.json`. A protected map's
custom tags wait for the conversion's repaired index. `extract --resurvey`
reads every unpacked map again when the survey learns something new, without
unpacking.

## Converting

`convert` runs `tools/level/convert_ce_map.sh <map> <CODE> <out>` with the
map's title, `SOUNDS_MAP`, and the stock folder as the exporter's resources
(`bitmaps.map`) and reference maps (for protected maps). It needs what the
conversion needs: `HCE_PAKS` (the Steam install's `Meteorite\Content\Paks` by
default), the built `mjolnir` and example tools, the halo2ue exporter, and
the Unreal editor for the materials cook (`CE_COOK=0` for the textured
fallback).

The codename is proposed from the title (`GRE`, then the initials, then a
letter and the file id in base 36), never one taken: the game's missions, the
stock conversions, every code in the archive, and `reserved_codes.json` in
the root (a JSON list) for codes taken elsewhere. `--code` picks one by hand.
A map keeps its code in its record, so a re-run converts it under the same.

An entry holding several multiplayer maps converts its largest; `--map` picks
one, `--all-maps` every one. Single player and UI maps, and anything not
Custom Edition (build 609), are catalogued but not converted.

The conversion's log is parsed into the record: the exporter's init and
placement lines, the protected-map repair, every `dropped N x <tag>` line
(the placements with no equivalent in the game), the warnings and notes,
the level summary, collision parse errors, error lines, how far it got and
how long it took. `report` adds them up across the archive.
