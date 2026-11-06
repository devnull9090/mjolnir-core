#!/usr/bin/env python3
"""Archive halomaps.org's Halo Custom Edition maps, and convert them one at a time.

halomaps.org/hce is the community's map archive: every map's page carries its
title, author, upload date, size, user rating, description, the author's file
notes and screenshots, and the file itself behind a download form. This tool
mirrors the multiplayer sections into one folder, keeps everything the site
knows about each map as JSON, reads each `.map`'s header and tag index (so the
catalogue knows a map's type, build, BSP count, protection and which of its
weapons, vehicles, scenery and bipeds are custom before anyone converts it),
and runs `tools/level/convert_ce_map.sh` on the most popular unconverted map
on request, keeping the conversion's report beside the metadata. The site
exposes no download counter, so popularity is the user rating, then the
number of user-submitted screenshots, then the upload date.

    maps/<fid>/meta.json          everything about one entry (the record)
    maps/<fid>/page.html          the detail page as fetched
    maps/<fid>/screenshots/       the site's and the users' screenshots
    maps/<fid>/<file>.zip         the download as served
    maps/<fid>/files/             the download unpacked: the .map files, readmes
    maps/<fid>/convert/<CODE>/    a conversion: staging, containers, log, pack
    listings/                     the listing pages as fetched
    catalog.json, catalog.csv     every record summarised, for sorting
    report.json, report.md        custom tags and conversion outcomes across the archive
    stock_tags.json               the stock maps' tag paths (cemap.py)

The stages, each resumable (what is done is skipped):

    python tools/halomaps/halomaps.py crawl              # the listings: one record per map
    python tools/halomaps/halomaps.py fetch              # each map's page and screenshots
    python tools/halomaps/halomaps.py download           # the files
    python tools/halomaps/halomaps.py extract            # unpack, read every .map's header and tags
    python tools/halomaps/halomaps.py scripts            # each scenario's scripts and devices (cescript.py)
    python tools/halomaps/halomaps.py catalog --sort rating --top 30
    python tools/halomaps/halomaps.py convert --next     # the best unconverted map, through convert_ce_map.sh
    python tools/halomaps/halomaps.py report             # custom tags and conversion outcomes

`mirror` runs crawl, fetch, download and extract in turn. The root is
`HALOMAPS_ROOT` or D:/halomaps; `--root` overrides it. Requests go one at a
time with a pause between them (`--delay`), with a user agent that names this
tool.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import html
import http.client
import http.cookiejar
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cemap  # noqa: E402
import cescript  # noqa: E402

SITE = "https://halomaps.org/hce/"
USER_AGENT = "mjolnir-halomaps-archiver/0.1 (+https://github.com/devnull9090/mjolnir-core)"
SCHEMA_VERSION = 1
DEFAULT_ROOT = Path(os.environ.get("HALOMAPS_ROOT") or "D:/halomaps")
DEFAULT_STOCK_MAPS = Path(os.environ.get("HALOMAPS_STOCK_MAPS") or Path.home() / "prj/HalcyonRing/maps")
DEFAULT_HCE_PAKS = Path(os.environ.get("HCE_PAKS")
                        or r"C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved\Meteorite\Content\Paks")
REPO = Path(__file__).resolve().parents[2]
CONVERT_SCRIPT = REPO / "tools/level/convert_ce_map.sh"
# This game's script functions and globals (mjolnir console), for the
# report's coverage of what the archive's scripts call.
CONSOLE_DEFS = REPO / "defs/hce/console.json"
PER_PAGE = 30

# The site's sections (`index.cfm?sid=`). The multiplayer ones are mirrored by
# default; the rest can be asked for with --sid.
SECTIONS = {
    10: "Halo CE Maps",
    39: "Multiplayer Maps w/ AI",
    24: "Modified Multiplayer Maps",
    40: "YELO - Open Sauce Maps",
    29: "Maps for Machinima",
    41: "Lumoria Campaign",
    27: "Modified Single Player Maps",
    35: "CMT Single Player Maps",
    37: "Custom Single Player Maps",
    11: "Official Halo CE Files",
}
MULTIPLAYER_SECTIONS = [10, 39, 24, 40, 29]

# Codenames no converted map may take: the game's own missions, the stock CE
# conversions, and the custom maps converted before this tool. A map keeps the
# code it is given (in its record), so the set only grows.
RESERVED_CODES = {
    "A10", "A30", "A50", "B30", "B40", "C10", "C20", "C40", "D20", "D40",
    "BCK", "BGL", "BDA", "CHL", "DCN", "DMN", "DRL", "DTI", "GPH", "HEH", "ICE", "INF", "LNG",
    "PRS", "PTP", "RAT", "SDW", "TMB", "WIZ",
    "YOY", "CSN",
}
# The shipped Custom Edition cache files: what "stock" means for a tag.
STOCK_MAP_NAMES = {
    "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout", "damnation", "dangercanyon",
    "deathisland", "gephyrophobia", "hangemhigh", "icefields", "infinity", "longest", "prisoner", "putput",
    "ratrace", "sidewinder", "timberland", "wizard", "ui",
}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".exe", ".ace", ".tar", ".gz", ".tgz"}
MAP_EXTENSIONS = {".map", ".yelo"}
README_EXTENSIONS = {".txt", ".md", ".rtf", ".htm", ".html", ".doc", ".pdf", ".nfo"}
SEVENZIP = os.environ.get("SEVENZIP") or shutil.which("7z") or r"C:\Program Files\7-Zip\7z.exe"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# The site
# ---------------------------------------------------------------------------

class Site:
    """One connection at a time, a pause between requests, retries on the
    errors a small server throws under load."""

    def __init__(self, delay: float = 1.5, retries: int = 4, timeout: float = 120):
        self.delay, self.retries, self.timeout = delay, retries, timeout
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.last = 0.0
        self.requests = 0

    def _pause(self, delay: float | None = None) -> None:
        gap = (self.delay if delay is None else delay) - (time.monotonic() - self.last)
        if gap > 0:
            time.sleep(gap)

    def open(self, url: str, data: bytes | None = None, referer: str | None = None, delay: float | None = None):
        req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, "Referer": referer or SITE})
        error: Exception | None = None
        for attempt in range(self.retries):
            self._pause(delay)
            try:
                resp = self.opener.open(req, timeout=self.timeout)
                self.last = time.monotonic()
                self.requests += 1
                return resp
            except urllib.error.HTTPError as e:
                self.last = time.monotonic()
                if e.code < 500:
                    raise
                error = e
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, OSError) as e:
                self.last = time.monotonic()
                error = e
            wait = 5 * 2 ** attempt
            log(f"  retry in {wait}s: {error}")
            time.sleep(wait)
        raise RuntimeError(f"{url}: {error}")

    def get(self, url: str, referer: str | None = None, delay: float | None = None) -> bytes:
        with self.open(url, referer=referer, delay=delay) as r:
            return r.read()

    def get_text(self, url: str, referer: str | None = None) -> str:
        return self.get(url, referer).decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# Parsing the pages
# ---------------------------------------------------------------------------

TAG_RE = re.compile(r"<[^>]+>")
BR_RE = re.compile(r"<br\s*/?>", re.I)
CARD_RE = re.compile(r'<div class="card mb-4 product-wap.*?</ul>', re.S)
FID_RE = re.compile(r"detail\.cfm\?fid=(\d+)")
LIST_FIELD_RE = re.compile(r"<li>([^:<]+):\s*(.*?)</li>", re.S)
TITLE_RE = re.compile(r'class="h3[^"]*"><strong>(.*?)</strong>', re.S)
THUMB_RE = re.compile(r'<img[^>]+src="([^"]+)"')
H1_RE = re.compile(r'<h1 class="h1[^"]*">(.*?)</h1>', re.S)
DESCRIPTION_RE = re.compile(r"<h6>Description:</h6>\s*<p>(.*?)</p>", re.S)
NOTES_RE = re.compile(r'File Notes</h6>\s*<p class="mb-5">(.*?)</p>', re.S)
HASH_RE = re.compile(r'name="hash" value="([0-9A-Fa-f]{32})"')
FORM_FID_RE = re.compile(r'name="fid" value="(\d+)"')
OFFICIAL_SHOT_RE = re.compile(r'<img class="card-img rounded border border-dark img-fluid" src="([^"]+)"')
USER_SHOT_RE = re.compile(r'src="(img/users/lg/[^"]+)"')
DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
SIZE_RE = re.compile(r"([\d.]+)\s*([KMG])B?", re.I)


def clean(fragment: str | None) -> str | None:
    """Page text: line breaks kept, tags dropped, entities decoded, whitespace
    tidied."""
    if fragment is None:
        return None
    text = BR_RE.sub("\n", fragment)
    text = TAG_RE.sub("", text)
    text = html.unescape(text).replace("\r", "")
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def parse_date(text: str | None) -> str | None:
    """The site's MM/DD/YYYY as YYYY-MM-DD; anything else as it came."""
    if not text:
        return None
    m = DATE_RE.search(text)
    if not m:
        return text.strip() or None
    month, day, year = (int(x) for x in m.groups())
    try:
        return dt.date(year, month, day).isoformat()
    except ValueError:
        return text.strip()


def parse_rating(text: str | None) -> float | None:
    try:
        return float(text.strip())
    except (AttributeError, ValueError):
        return None


def parse_size(text: str | None) -> int | None:
    """"11.8MB", "11.8M", "314.8M" as bytes, roughly."""
    if not text:
        return None
    m = SIZE_RE.search(text)
    if not m:
        return None
    scale = {"K": 1 << 10, "M": 1 << 20, "G": 1 << 30}[m.group(2).upper()]
    return int(float(m.group(1)) * scale)


def parse_listing(page: str) -> list[dict]:
    cards = []
    for m in CARD_RE.finditer(page):
        block = m.group(0)
        fid = FID_RE.search(block)
        if not fid:
            continue
        fields = {k.strip(): clean(v) for k, v in LIST_FIELD_RE.findall(block)}
        title = TITLE_RE.search(block)
        thumb = THUMB_RE.search(block)
        cards.append({
            "fid": int(fid.group(1)),
            "title": clean(title.group(1)) if title else None,
            "thumbnail": thumb.group(1) if thumb else None,
            "author": fields.get("Author") or None,
            "date": parse_date(fields.get("Date")),
            "size_text": fields.get("File Size"),
            "rating_text": fields.get("User Rating"),
        })
    return cards


def parse_detail(page: str) -> dict:
    def labelled(label: str) -> str | None:
        m = re.search(rf"<h6>{re.escape(label)}</h6>\s*</li>\s*<li[^>]*>\s*<(?:span|p)[^>]*><strong>(.*?)</strong>",
                      page, re.S)
        return clean(m.group(1)) if m else None

    title = H1_RE.search(page)
    description = DESCRIPTION_RE.search(page)
    notes = NOTES_RE.search(page)
    form_hash = HASH_RE.search(page)
    form_fid = FORM_FID_RE.search(page)
    # The site's own screenshots sit in the left column, before the card.
    head = page.split('<div class="card-body">', 1)[0]
    return {
        "title": clean(title.group(1)) if title else None,
        "rating_text": labelled("User Rating:"),
        "file_category": labelled("File Category:"),
        "author": labelled("Author:"),
        "date": parse_date(labelled("Date:")),
        "size_text": labelled("File Size:"),
        "description": clean(description.group(1)) if description else None,
        "notes": clean(notes.group(1)) if notes else None,
        "notes_html": notes.group(1).strip() if notes else None,
        "screenshots": OFFICIAL_SHOT_RE.findall(head),
        "user_screenshots": USER_SHOT_RE.findall(page),
        "hash": form_hash.group(1).upper() if form_hash else None,
        "form_fid": int(form_fid.group(1)) if form_fid else None,
    }


# ---------------------------------------------------------------------------
# The archive on disk
# ---------------------------------------------------------------------------

class Archive:
    def __init__(self, root: Path):
        self.root = Path(root)
        (self.root / "maps").mkdir(parents=True, exist_ok=True)
        (self.root / "listings").mkdir(exist_ok=True)

    def map_dir(self, fid: int) -> Path:
        return self.root / "maps" / str(fid)

    def record_path(self, fid: int) -> Path:
        return self.map_dir(fid) / "meta.json"

    def load(self, fid: int) -> dict | None:
        p = self.record_path(fid)
        if not p.exists():
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def new(self, fid: int) -> dict:
        return {"schema_version": SCHEMA_VERSION, "fid": fid, "url": f"{SITE}detail.cfm?fid={fid}",
                "source": "halomaps.org", "created_at": now()}

    def get(self, fid: int) -> dict:
        return self.load(fid) or self.new(fid)

    def save(self, rec: dict) -> None:
        rec["updated_at"] = now()
        p = self.record_path(rec["fid"])
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, p)

    def fids(self) -> list[int]:
        out = []
        for d in (self.root / "maps").iterdir():
            if d.name.isdigit() and (d / "meta.json").exists():
                out.append(int(d.name))
        return sorted(out)

    def records(self) -> list[dict]:
        return [r for r in (self.load(f) for f in self.fids()) if r]

    def stock(self, stock_maps: Path) -> dict[str, set[str]]:
        """The stock tag set, built once from the stock maps' folder. Only
        the 19 shipped multiplayer maps and the UI count: a custom map kept
        in the same folder must not make its own tags stock."""
        p = self.root / "stock_tags.json"
        if not p.exists():
            maps = sorted(str(m) for m in Path(stock_maps).glob("*.map") if m.stem.lower() in STOCK_MAP_NAMES)
            if not maps:
                sys.exit(f"error: no stock maps in {stock_maps} (--stock-maps or HALOMAPS_STOCK_MAPS)")
            cemap.save_stock(str(p), cemap.stock_set(maps), maps)
            log(f"stock tag set: {p} from {len(maps)} maps")
        return cemap.load_stock(str(p))


def select(archive: Archive, fids: list[int] | None) -> list[int]:
    return sorted(set(fids)) if fids else archive.fids()


# ---------------------------------------------------------------------------
# crawl: the listings
# ---------------------------------------------------------------------------

def cmd_crawl(a, archive: Archive, site: Site) -> None:
    sids = a.sid or MULTIPLAYER_SECTIONS
    total = 0
    for sid in sids:
        seen: set[int] = set()
        start, page = 1, 1
        while True:
            url = f"{SITE}index.cfm?sid={sid}&sort=1&Start={start}"
            body = site.get_text(url)
            (archive.root / "listings" / f"sid{sid}_start{start}.html").write_text(body, encoding="utf-8")
            cards = parse_listing(body)
            new = [c for c in cards if c["fid"] not in seen]
            if not new:
                break  # past the end the site serves a page already seen
            for pos, c in enumerate(cards, start):
                rec = archive.get(c["fid"])
                rec["listing"] = {**c, "sid": sid, "section": SECTIONS.get(sid, f"sid {sid}"),
                                  "page": page, "position": pos, "crawled_at": now()}
                if "detail" not in rec:
                    rec["title"] = c["title"]
                    rec["author"] = c["author"]
                    rec["date"] = c["date"]
                    rec["size_text"] = c["size_text"]
                    rec["rating_text"] = c["rating_text"]
                    rec["rating"] = parse_rating(c["rating_text"])
                rec["section"] = {"sid": sid, "name": SECTIONS.get(sid, f"sid {sid}")}
                archive.save(rec)
            seen.update(c["fid"] for c in cards)
            log(f"sid {sid} page {page}: {len(new)} maps (Start={start})")
            if a.pages and page >= a.pages:
                break
            start += PER_PAGE
            page += 1
        log(f"sid {sid} ({SECTIONS.get(sid, '?')}): {len(seen)} maps")
        total += len(seen)
    log(f"crawled {total} listings into {archive.root / 'maps'} ({site.requests} requests)")


# ---------------------------------------------------------------------------
# fetch: the detail pages and screenshots
# ---------------------------------------------------------------------------

def fetch_image(site: Site, archive: Archive, rec: dict, src: str, name: str, delay: float) -> str | None:
    dest_dir = archive.map_dir(rec["fid"]) / "screenshots"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    if dest.exists() and dest.stat().st_size > 0:
        return name
    try:
        data = site.get(urllib.parse.urljoin(SITE, src), referer=rec["url"], delay=delay)
    except Exception as e:  # noqa: BLE001  a missing image is the site's loss, not a stop
        log(f"  screenshot {src}: {f'HTTP {e.code}' if isinstance(e, urllib.error.HTTPError) else e}")
        return None
    dest.write_bytes(data)
    return name


def cmd_fetch(a, archive: Archive, site: Site) -> None:
    done = 0
    for fid in select(archive, a.fid):
        rec = archive.get(fid)
        if "detail" in rec and not a.refresh:
            continue
        if a.limit and done >= a.limit:
            break
        try:
            body = site.get_text(rec["url"])
        except (urllib.error.HTTPError, RuntimeError) as e:
            rec["detail_error"] = f"HTTP {e.code}" if isinstance(e, urllib.error.HTTPError) else str(e)
            archive.save(rec)
            log(f"{fid}: {rec['detail_error']}")
            continue
        archive.map_dir(fid).mkdir(parents=True, exist_ok=True)
        (archive.map_dir(fid) / "page.html").write_text(body, encoding="utf-8")
        d = parse_detail(body)
        if d["form_fid"] not in (None, fid):
            log(f"{fid}: page carries fid {d['form_fid']}")
        rec["detail"] = {k: v for k, v in d.items() if k not in ("screenshots", "user_screenshots", "hash", "form_fid")}
        rec["detail"]["fetched_at"] = now()
        rec.pop("detail_error", None)
        rec["title"] = d["title"] or rec.get("title")
        rec["author"] = d["author"] or rec.get("author")
        rec["date"] = d["date"] or rec.get("date")
        rec["size_text"] = d["size_text"] or rec.get("size_text")
        rec["rating_text"] = d["rating_text"] or rec.get("rating_text")
        rec["rating"] = parse_rating(rec["rating_text"])
        rec["category"] = d["file_category"]
        rec["description"] = d["description"]
        rec["notes"] = d["notes"]
        rec["download"] = {**rec.get("download", {}), "hash": d["hash"]}
        shots = {"official": [], "user": [], "sources": {"official": d["screenshots"], "user": d["user_screenshots"]}}
        if not a.no_screenshots:
            for i, src in enumerate(d["screenshots"], 1):
                name = fetch_image(site, archive, rec, src, f"official_{i:02}_{Path(src).name}", a.image_delay)
                if name:
                    shots["official"].append(name)
            for i, src in enumerate(d["user_screenshots"], 1):
                name = fetch_image(site, archive, rec, src, f"user_{i:02}_{Path(src).name}", a.image_delay)
                if name:
                    shots["user"].append(name)
        rec["screenshots"] = shots
        archive.save(rec)
        done += 1
        log(f"{fid}: {rec['title']} by {rec['author']} ({rec['date']}, rating {rec['rating_text']}, "
            f"{len(d['screenshots'])}+{len(d['user_screenshots'])} screenshots)")
    log(f"fetched {done} pages ({site.requests} requests)")


def cmd_screenshots(a, archive: Archive, site: Site) -> None:
    """The screenshots of fetched pages, for records fetched with
    --no-screenshots (the mirror fetches pages and files first, pictures
    last) or whose images failed."""
    done = 0
    for fid in select(archive, a.fid):
        rec = archive.get(fid)
        shots = rec.get("screenshots") or {}
        sources = shots.get("sources") or {}
        wanted = [(src, f"official_{i:02}_{Path(src).name}", "official") for i, src in enumerate(sources.get("official") or [], 1)]
        wanted += [(src, f"user_{i:02}_{Path(src).name}", "user") for i, src in enumerate(sources.get("user") or [], 1)]
        missing = [(src, name, kind) for src, name, kind in wanted
                   if not (archive.map_dir(fid) / "screenshots" / name).exists()]
        if not missing:
            continue
        if a.limit and done >= a.limit:
            break
        for src, name, kind in missing:
            if fetch_image(site, archive, rec, src, name, a.image_delay) and name not in shots.setdefault(kind, []):
                shots[kind].append(name)
        for kind in ("official", "user"):
            shots[kind] = sorted(set(shots.get(kind) or []))
        rec["screenshots"] = shots
        archive.save(rec)
        done += 1
        log(f"{fid}: {len(missing)} screenshots")
    log(f"screenshots for {done} maps ({site.requests} requests)")


# ---------------------------------------------------------------------------
# download: the files
# ---------------------------------------------------------------------------

def safe_name(name: str) -> str:
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "download.bin"


def cmd_download(a, archive: Archive, site: Site) -> None:
    done = 0
    for fid in select(archive, a.fid):
        rec = archive.get(fid)
        dl = rec.get("download") or {}
        if not dl.get("hash"):
            continue  # not fetched yet
        if dl.get("file_name") and (archive.map_dir(fid) / dl["file_name"]).exists() and not a.redo:
            continue
        if a.limit and done >= a.limit:
            break
        data = urllib.parse.urlencode({"fid": fid, "action": "dl", "hash": dl["hash"], "submit": "download"}).encode()
        started = time.monotonic()
        try:
            fetched = stream_download(a, archive, site, rec, dl, data)
        except Exception as e:  # noqa: BLE001  one bad file must not end the run
            dl["error"] = str(e)[:300]
            rec["download"] = dl
            archive.save(rec)
            log(f"{fid}: {dl['error']}")
            continue
        if not fetched:
            continue
        file_name, ctype, got, digest = fetched
        rec["download"] = {
            "hash": dl["hash"],
            "file_name": file_name,
            "content_type": ctype,
            "size": got,
            "sha256": digest,
            "downloaded_at": now(),
            "seconds": round(time.monotonic() - started, 1),
        }
        rec["size"] = got
        archive.save(rec)
        done += 1
        log(f"{fid}: {file_name} ({got / 1048576:.1f} MB in {rec['download']['seconds']}s)")
    log(f"downloaded {done} files ({site.requests} requests)")


def stream_download(a, archive: Archive, site: Site, rec: dict, dl: dict, data: bytes):
    """One file to disk; None when the site answered with a page, the file is
    over --max-mb, or the stream came up short (the record says which)."""
    fid = rec["fid"]
    try:
        resp = site.open(f"{SITE}detail.cfm", data=data, referer=rec["url"])
    except urllib.error.HTTPError as e:
        dl["error"] = f"HTTP {e.code}"
        rec["download"] = dl
        archive.save(rec)
        log(f"{fid}: HTTP {e.code}")
        return None
    with resp:
        ctype = resp.headers.get("Content-Type", "")
        length = resp.headers.get("Content-Length")
        disposition = resp.headers.get("Content-Disposition", "")
        m = re.search(r'filename\*?="?([^";]+)', disposition)
        file_name = safe_name(urllib.parse.unquote(m.group(1))) if m else None
        if ctype.startswith("text/html") or not file_name:
            body = resp.read(65536)
            (archive.map_dir(fid) / "download_error.html").write_bytes(body)
            dl["error"] = f"no file: {ctype or 'no content type'}"
            rec["download"] = dl
            archive.save(rec)
            log(f"{fid}: the download form answered with a page, not a file")
            return None
        size = int(length) if length else None
        if a.max_mb and size and size > a.max_mb * 1024 * 1024:
            dl["skipped"] = f"{size / 1048576:.1f} MB is over --max-mb {a.max_mb}"
            dl["file_name_announced"] = file_name
            dl["size_announced"] = size
            rec["download"] = dl
            archive.save(rec)
            log(f"{fid}: skipped {file_name} ({size / 1048576:.1f} MB)")
            return None
        dl.pop("skipped", None)
        dest = archive.map_dir(fid) / file_name
        part = dest.with_name(dest.name + ".part")
        digest = hashlib.sha256()
        got = 0
        with open(part, "wb") as f:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                digest.update(chunk)
                got += len(chunk)
    if size is not None and got != size:
        dl["error"] = f"short read: {got} of {size} bytes"
        rec["download"] = dl
        archive.save(rec)
        part.unlink(missing_ok=True)
        log(f"{fid}: {dl['error']}")
        return None
    os.replace(part, dest)
    return file_name, ctype, got, digest.hexdigest()


# ---------------------------------------------------------------------------
# extract: unpack and read the maps
# ---------------------------------------------------------------------------

def is_zip(path: Path) -> bool:
    with open(path, "rb") as f:
        return f.read(4) == b"PK\x03\x04"


def unpack(path: Path, dest: Path) -> tuple[str, list[str]]:
    """Unpack one archive into dest. Zip files go through zipfile (members
    with absolute or parent paths are refused); everything else through
    7-Zip, which also opens self-extracting .exe downloads."""
    dest.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    if is_zip(path):
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                name = info.filename.replace("\\", "/")
                parts = [p for p in name.split("/") if p not in ("", ".")]
                if not parts or ".." in parts or name.startswith("/") or re.match(r"[A-Za-z]:", name):
                    problems.append(f"refused member {info.filename}")
                    continue
                # A member name Windows refuses (a control character in
                # "ReadMe! by \x15partan 8.txt") is written under a tidied one.
                safe = [safe_name(p) for p in parts]
                target = dest.joinpath(*safe)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                if safe != parts:
                    problems.append(f"renamed {info.filename} -> {'/'.join(safe)}")
        return "zip", problems
    if not Path(SEVENZIP).exists():
        raise RuntimeError(f"not a zip and 7-Zip is not at {SEVENZIP} (SEVENZIP=...)")
    r = subprocess.run([SEVENZIP, "x", "-y", f"-o{dest}", str(path)], capture_output=True, text=True, errors="replace")
    if r.returncode > 1:
        raise RuntimeError(f"7z exit {r.returncode}: {(r.stderr or r.stdout).strip()[-400:]}")
    if r.returncode == 1:
        problems.append("7z finished with warnings")
    kind = path.suffix.lower().lstrip(".") or "7z"
    return kind, problems


def scripting(path: Path) -> dict:
    """A cache file's scripts, devices and vehicle types (cescript.py)."""
    try:
        return cescript.read(str(path))
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def cmd_scripts(a, archive: Archive, site: Site | None = None) -> None:
    """Read every unpacked map's scenario for its scripts and devices,
    without the rest of a resurvey: the tag data only, a few MB a map."""
    done = 0
    for fid in select(archive, a.fid):
        rec = archive.load(fid)
        maps = ((rec or {}).get("archive") or {}).get("maps")
        if not maps:
            continue
        changed = False
        for m in maps:
            if m.get("version") is None or (m.get("scripting") and not a.redo):
                continue
            p = archive.map_dir(fid) / "files" / m["file"]
            if p.exists():
                m["scripting"] = scripting(p)
                changed = True
        if changed:
            archive.save(rec)
            done += 1
            if done % 250 == 0:
                log(f"  {done} entries read")
        if a.limit and done >= a.limit:
            break
    log(f"read the scripts of {done} entries")


def resurvey(archive: Archive, rec: dict, stock: dict[str, set[str]]) -> int:
    """Read an entry's unpacked cache files again with the current cemap,
    keeping their digests: for when the survey learns something new."""
    files = archive.map_dir(rec["fid"]) / "files"
    maps = (rec.get("archive") or {}).get("maps")
    if not maps:
        return 0
    fresh = []
    for m in maps:
        p = files / m["file"]
        if m.get("version") is None or not p.exists():
            fresh.append(m)
            continue
        try:
            new = cemap.read_map(str(p), stock=stock, digest=False)
        except Exception as e:  # noqa: BLE001
            fresh.append({"file": m["file"], "size": m.get("size"), "error": str(e)})
            continue
        new["file"] = m["file"]
        new["scripting"] = scripting(p)
        if m.get("sha256"):
            new["sha256"] = m["sha256"]
        fresh.append(new)
    rec["archive"]["maps"] = fresh
    rec["archive"]["surveyed_at"] = now()
    archive.save(rec)
    return len(fresh)


def cmd_extract(a, archive: Archive, site: Site | None = None) -> None:
    stock = archive.stock(a.stock_maps)
    done = 0
    if a.resurvey:
        for fid in select(archive, a.fid):
            rec = archive.get(fid)
            done += 1 if resurvey(archive, rec, stock) else 0
        log(f"surveyed {done} entries again")
        return
    for fid in select(archive, a.fid):
        rec = archive.get(fid)
        dl = rec.get("download") or {}
        src = archive.map_dir(fid) / dl["file_name"] if dl.get("file_name") else None
        if not src or not src.exists():
            continue
        if rec.get("archive") and not rec["archive"].get("error") and not a.redo:
            continue
        if a.limit and done >= a.limit:
            break
        files = archive.map_dir(fid) / "files"
        info: dict = {"file": dl["file_name"], "extracted_at": now()}
        try:
            if files.exists():
                shutil.rmtree(files)
            info["format"], problems = unpack(src, files)
            # One archive inside another: a zip of a rar, a rar of the map
            # and its readme. One level is unpacked beside it.
            nested = []
            for inner in sorted(p for p in files.rglob("*") if p.is_file() and p.suffix.lower() in ARCHIVE_EXTENSIONS):
                if inner.suffix.lower() == ".exe" and not is_zip(inner):
                    continue  # an installer or a tool, not a wrapper
                try:
                    unpack(inner, inner.with_suffix(""))
                    nested.append(str(inner.relative_to(files)))
                except Exception as e:  # noqa: BLE001
                    problems.append(f"{inner.name}: {e}")
            info["nested"] = nested
            info["problems"] = problems
        except Exception as e:  # noqa: BLE001
            info["error"] = str(e)
            rec["archive"] = info
            archive.save(rec)
            log(f"{fid}: {e}")
            continue
        entries = []
        maps = []
        readmes = []
        for p in sorted(q for q in files.rglob("*") if q.is_file()):
            rel = str(p.relative_to(files)).replace("\\", "/")
            entries.append({"name": rel, "size": p.stat().st_size})
            ext = p.suffix.lower()
            if ext in MAP_EXTENSIONS:
                try:
                    m = cemap.read_map(str(p), stock=stock)
                    m["file"] = rel
                    m["scripting"] = scripting(p)
                    maps.append(m)
                except cemap.NotACacheFile:
                    maps.append({"file": rel, "size": p.stat().st_size, "kind": "resource"})
                except Exception as e:  # noqa: BLE001
                    maps.append({"file": rel, "size": p.stat().st_size, "error": str(e)})
            elif ext in README_EXTENSIONS:
                readmes.append(rel)
        info.update({"entry_count": len(entries), "entries": entries, "maps": maps, "readmes": readmes})
        rec["archive"] = info
        archive.save(rec)
        done += 1
        names = ", ".join(f"{m.get('name') or m['file']} ({m.get('type', m.get('kind', '?'))}"
                          f"{', protected' if m.get('protected') else ''})" for m in maps) or "no maps"
        log(f"{fid}: {info['format']}, {len(entries)} files: {names}")
    log(f"extracted {done} archives")


# ---------------------------------------------------------------------------
# catalog: one row per record
# ---------------------------------------------------------------------------

def cache_maps(rec: dict) -> list[dict]:
    """The real cache files an entry holds (not the resource maps)."""
    return [m for m in (rec.get("archive") or {}).get("maps", []) if m.get("version") is not None]


def convertible(rec: dict) -> list[dict]:
    """The maps this tool converts: Custom Edition multiplayer cache files."""
    return [m for m in cache_maps(rec) if m.get("type") == "multiplayer" and m.get("version") == 609]


def priority(rec: dict) -> tuple:
    shots = rec.get("screenshots") or {}
    return (rec.get("rating") or 0.0, len(shots.get("user") or []), rec.get("date") or "")


def conversion_status(rec: dict) -> str | None:
    convs = rec.get("conversions") or []
    if not convs:
        return None
    if all(c.get("status") == "converted" for c in convs):
        return "converted"
    if any(c.get("status") == "converted" for c in convs):
        return "partial"
    return convs[-1].get("status")


def summarize(rec: dict) -> dict:
    maps = cache_maps(rec)
    customs = [m["custom"] for m in maps if m.get("custom")]

    def custom_count(cls: str) -> int:
        return sum(c["counts"].get(cls, 0) for c in customs)

    shots = rec.get("screenshots") or {}
    dl = rec.get("download") or {}
    arc = rec.get("archive") or {}
    return {
        "fid": rec["fid"],
        "title": rec.get("title"),
        "author": rec.get("author"),
        "date": rec.get("date"),
        "rating": rec.get("rating"),
        "rating_text": rec.get("rating_text"),
        "user_screenshots": len(shots.get("user") or []),
        "section": (rec.get("section") or {}).get("name"),
        "category": rec.get("category"),
        "size_text": rec.get("size_text"),
        "size": dl.get("size"),
        "file_name": dl.get("file_name"),
        "fetched": "detail" in rec,
        "downloaded": bool(dl.get("file_name")),
        "extracted": bool(arc.get("maps") is not None),
        "maps": len(maps),
        "map_names": ";".join(m.get("name") or "" for m in maps),
        "map_types": ";".join(sorted({m.get("type") or "" for m in maps})),
        "engines": ";".join(sorted({m.get("engine") or "" for m in maps})),
        "protected": any(m.get("protected") for m in maps),
        "partially_protected": any(m.get("partially_protected") for m in maps),
        "placeholder_paths": sum(m.get("placeholder_paths") or 0 for m in maps),
        "bsps": max((m.get("bsps") or 0 for m in maps), default=0),
        "tags": max((m.get("tag_count") or 0 for m in maps), default=0),
        "custom_total": sum(c["total"] for c in customs),
        "custom_weapons": custom_count("weap"),
        "custom_vehicles": custom_count("vehi"),
        "custom_scenery": custom_count("scen"),
        "custom_bipeds": custom_count("bipd"),
        "custom_equipment": custom_count("eqip"),
        "custom_machines": custom_count("mach"),
        "custom_shaders": sum(custom_count(c) for c in ("senv", "soso", "schi", "scex", "swat", "sgla", "smet", "spla")),
        "convertible": len(convertible(rec)),
        "code": rec.get("code"),
        "conversion": conversion_status(rec),
        "skip": rec.get("skip"),
        "url": rec.get("url"),
    }


SORTS = {
    "rating": lambda r: (r["rating"] or 0, r["user_screenshots"], r["date"] or ""),
    "screenshots": lambda r: (r["user_screenshots"], r["rating"] or 0),
    "date": lambda r: r["date"] or "",
    "size": lambda r: r["size"] or parse_size(r["size_text"]) or 0,
    "name": lambda r: (r["title"] or "").lower(),
    "custom": lambda r: (r["custom_total"], r["rating"] or 0),
    "fid": lambda r: r["fid"],
}


def cmd_catalog(a, archive: Archive, site: Site | None = None) -> None:
    rows = [summarize(r) for r in archive.records()]
    out = {"generated_at": now(), "root": str(archive.root), "count": len(rows),
           "popularity": "rating, then user screenshots, then date (the site has no download counter)",
           "maps": sorted(rows, key=lambda r: r["fid"])}
    with open(archive.root / "catalog.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    if rows:
        with open(archive.root / "catalog.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(sorted(rows, key=lambda r: r["fid"]))
    log(f"catalog: {len(rows)} records -> {archive.root / 'catalog.json'}, catalog.csv")
    key = SORTS[a.sort]
    ordered = sorted(rows, key=key, reverse=a.sort not in ("name", "fid"))
    if a.convertible:
        ordered = [r for r in ordered if r["convertible"] and not r["conversion"]]
    log(f"{'fid':>5}  {'rating':>6} {'shots':>5}  {'date':10}  {'code':4}  {'maps':>4} {'cust':>4}  title")
    for r in ordered[: a.top]:
        flags = "P" if r["protected"] else " "
        log(f"{r['fid']:>5}  {r['rating_text'] or '':>6} {r['user_screenshots']:>5}  {r['date'] or '':10}  "
            f"{r['code'] or '':4}  {r['maps']:>4}{flags}{r['custom_total']:>4}  {r['title']} "
            f"({r['author']}, {r['size_text']}{', ' + r['conversion'] if r['conversion'] else ''})")


# ---------------------------------------------------------------------------
# convert: through tools/level/convert_ce_map.sh
# ---------------------------------------------------------------------------

def taken_codes(archive: Archive) -> set[str]:
    codes = set(RESERVED_CODES)
    extra = archive.root / "reserved_codes.json"
    if extra.exists():
        with open(extra, encoding="utf-8") as f:
            codes.update(c.upper() for c in json.load(f))
    for rec in archive.records():
        for c in rec.get("conversions") or []:
            if c.get("code"):
                codes.add(c["code"].upper())
        if rec.get("code"):
            codes.add(rec["code"].upper())
    return codes


def base36(n: int, width: int) -> str:
    digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = digits[r] + out
    return out.rjust(width, "0")


def propose_code(title: str, fid: int, taken: set[str]) -> str:
    """A three-character [A-Z0-9] codename from the title: its first three
    letters, its initials, then combinations, then a letter and the fid in
    base 36. Never one already taken."""
    words = [w for w in re.findall(r"[A-Za-z0-9]+", title.upper()) if w]
    letters = "".join(words)
    candidates = []
    if len(letters) >= 3:
        candidates.append(letters[:3])
    if len(words) >= 3:
        candidates.append("".join(w[0] for w in words[:3]))
    if len(words) >= 2:
        candidates.append(words[0][0] + words[1][:2])
        candidates.append(words[0][:2] + words[1][0])
        candidates.append(words[0][0] + words[-1][:2])
    consonants = re.sub(r"[AEIOU]", "", letters)
    if len(consonants) >= 3:
        candidates.append(consonants[:3])
    if len(letters) >= 3:
        candidates.append(letters[0] + letters[-2:])
    for c in candidates:
        if len(c) == 3 and c[0].isalpha() and c not in taken:
            return c
    for k in range(1000):
        n = fid + k * 7919
        c = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[(n // 1296) % 26] + base36(n % 1296, 2)
        if c not in taken:
            return c
    raise RuntimeError("no free codename")


def write_readme(rec: dict, m: dict, code: str, path: Path) -> None:
    lines = [f"# {rec.get('title')}", ""]
    lines.append(f"A Halo Custom Edition map by {rec.get('author') or 'an unknown author'}, "
                 f"uploaded to halomaps.org on {rec.get('date') or 'an unknown date'} and converted "
                 f"for Halo: Campaign Evolved by MJOLNIR as `{code}`.")
    lines.append("")
    lines.append(f"Source: {rec.get('url')}")
    if rec.get("rating_text"):
        lines.append(f"halomaps.org user rating: {rec['rating_text']}")
    lines.append(f"Cache file: `{m.get('file')}` ({m.get('name')}, build {m.get('build')})")
    if rec.get("description"):
        lines += ["", "## Description", "", rec["description"]]
    if rec.get("notes"):
        lines += ["", "## The author's file notes", "", rec["notes"]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


LOG_PATTERNS = {
    "init": re.compile(r"^\[init\] map '(.*)' build (\S+) type (\S+)"),
    "tags": re.compile(r"^\[init\] (\d+) tags"),
    "repaired": re.compile(r"^\[init\] protected map repaired: (\d+) classes recovered \((\d+) unknown\), "
                           r"(\d+) names from (\d+) reference maps, (\d+) synthesized"),
    "placements": re.compile(r"^\[placements\] (\d+) entries \((.*?)\), (\d+) player starts, (\d+) netgame flags, (\d+) decals"),
    "dropped": re.compile(r"^\s+dropped\s+(\d+) x (.*)$"),
    "summary": re.compile(r"^(\S+): (\d+) starts, (\d+) vehicles, (\d+) weapons, (\d+) equipment, (\d+) teleporter ends, "
                          r"(\d+) flag stands, (\d+) markers, (\d+) decor \((\d+) lens flares\), (\d+) health packs"),
    "step": re.compile(r"^== (\d)/6 "),
    "coll_error": re.compile(r"^\s+\[coll\] (.*?): Parse error"),
    "pack": re.compile(r"^wrote (\S+\.mjolnir) \((\d+) bytes", re.M),
    "world": re.compile(r"^note: (\S+) has more than one BSP"),
}
ERROR_RE = re.compile(r"\b(error|panicked|Traceback|No such file|not found|failed)\b", re.I)
NOISE_RE = re.compile(r"Parse error: No collision model|\[ResourceMap Debug\]|0 unknown|errors=0", re.I)
# The editor's and the cook's exit lines. Every conversion so far ends its
# sounds import on a handled ensure (no Bink decoder in the editor) and the
# cook's packaging step with BUILD FAILED, with the map's chunk cooked all
# the same; a cook that made no chunk fails the copy after it, and that is
# the error line that counts.
COOK_RE = re.compile(r"^(editor exit \d+|cook exit \d+|BUILD FAILED)")


def parse_convert_log(text: str) -> dict:
    report: dict = {"notes": [], "warnings": [], "dropped": [], "errors": [], "collision_parse_errors": [],
                    "cook": [], "steps_reached": 0, "done": False}
    for line in text.splitlines():
        line = line.rstrip()
        if m := LOG_PATTERNS["init"].match(line):
            report["map"] = {"name": m.group(1), "build": m.group(2), "type": m.group(3)}
        elif m := LOG_PATTERNS["tags"].match(line):
            report["tags"] = int(m.group(1))
        elif m := LOG_PATTERNS["repaired"].match(line):
            keys = ("classes_recovered", "classes_unknown", "names_recovered", "reference_maps", "names_synthesized")
            report["repaired"] = dict(zip(keys, map(int, m.groups())))
        elif m := LOG_PATTERNS["placements"].match(line):
            kinds = dict(kv.split("=") for kv in m.group(2).split(", ") if "=" in kv)
            report["placements"] = {"entries": int(m.group(1)), "kinds": {k: int(v) for k, v in kinds.items()},
                                    "player_starts": int(m.group(3)), "netgame_flags": int(m.group(4)),
                                    "decals": int(m.group(5))}
        elif m := LOG_PATTERNS["dropped"].match(line):
            report["dropped"].append({"count": int(m.group(1)), "what": m.group(2).strip()})
        elif m := LOG_PATTERNS["summary"].match(line):
            keys = ("starts", "vehicles", "weapons", "equipment", "teleporter_ends", "flag_stands", "markers",
                    "decor", "lens_flares", "health_packs")
            report["level"] = {"name": m.group(1), **dict(zip(keys, map(int, m.groups()[1:])))}
        elif m := LOG_PATTERNS["step"].match(line):
            report["steps_reached"] = max(report["steps_reached"], int(m.group(1)))
        elif m := LOG_PATTERNS["coll_error"].match(line):
            if len(report["collision_parse_errors"]) < 50:
                report["collision_parse_errors"].append(m.group(1))
        elif m := LOG_PATTERNS["pack"].match(line):
            report["pack"] = {"file": m.group(1), "bytes": int(m.group(2))}
        elif line.startswith("note:"):
            report["notes"].append(line[5:].strip())
        elif line.startswith("warning:") or line.startswith("  warning:"):
            report["warnings"].append(line.strip()[8:].strip())
        elif "WARN:" in line:  # the exporter's: a bitmap it could not export, a missing bitmaps.map
            report["warnings"].append(line.split("WARN:", 1)[1].strip())
        elif line.startswith("done:"):
            report["done"] = True
        elif COOK_RE.match(line):
            report["cook"].append(line.split(",", 1)[0])
        elif ERROR_RE.search(line) and not NOISE_RE.search(line) and len(report["errors"]) < 40:
            report["errors"].append(line.strip()[:300])
    return report


def pick_maps(rec: dict, wanted: str | None) -> list[dict]:
    maps = convertible(rec)
    if wanted:
        maps = [m for m in maps if m["file"] == wanted or m.get("name") == wanted or Path(m["file"]).name == wanted]
    return maps


def next_candidates(archive: Archive, retry_failed: bool) -> list[dict]:
    out = []
    for rec in archive.records():
        if rec.get("skip") or not convertible(rec):
            continue
        status = conversion_status(rec)
        if status == "converted" or (status and not retry_failed):
            continue
        out.append(rec)
    return sorted(out, key=priority, reverse=True)


def run_convert(a, archive: Archive, rec: dict, m: dict) -> dict:
    taken = taken_codes(archive)
    code = next((c["code"] for c in rec.get("conversions") or [] if c.get("map") == m["file"] and c.get("code")), None)
    code = (a.code or code or propose_code(rec.get("title") or m.get("name") or "", rec["fid"], taken)).upper()
    if a.code and a.code.upper() in taken and code not in {c.get("code") for c in rec.get("conversions") or []}:
        sys.exit(f"error: code {code} is taken")
    out = archive.map_dir(rec["fid"]) / "convert" / code
    out.mkdir(parents=True, exist_ok=True)
    map_path = archive.map_dir(rec["fid"]) / "files" / m["file"]
    stock_dir = Path(a.stock_maps)
    env = dict(os.environ)
    env.setdefault("HCE_PAKS", str(DEFAULT_HCE_PAKS))
    env["TITLE"] = rec.get("title") or m.get("name") or code
    env["SOUNDS_MAP"] = str(stock_dir / "sounds.map")
    env["HALO2UE_RESOURCES"] = str(stock_dir)
    env["HALO2UE_REFERENCE_MAPS"] = str(stock_dir)
    posix = lambda p: str(p).replace("\\", "/")  # noqa: E731
    cmd = ["bash", posix(a.script), posix(map_path), code, posix(out)] + (["--install"] if a.install else [])
    entry = {"map": m["file"], "map_name": m.get("name"), "code": code, "title": env["TITLE"], "out": posix(out),
             "log": posix(out / "convert.log"), "install": bool(a.install), "started_at": now(),
             "command": " ".join(cmd), "status": "running"}
    log(f"== converting {rec['fid']} {env['TITLE']!r} ({m['file']}) as {code} -> {out}")
    if a.dry_run:
        log("  " + " ".join(cmd))
        entry["status"] = "dry-run"
        return entry
    rec["conversions"] = [c for c in rec.get("conversions") or [] if not (c.get("map") == m["file"] and c.get("code") == code)]
    rec["conversions"].append(entry)
    rec["code"] = rec.get("code") or code
    archive.save(rec)
    started = time.monotonic()
    with open(out / "convert.log", "w", encoding="utf-8", errors="replace") as logf:
        proc = subprocess.Popen(cmd, cwd=str(REPO), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", bufsize=1)
        assert proc.stdout is not None
        for line in proc.stdout:
            logf.write(line)
            if re.match(r"^(== |done:|\s+dropped|warning:|note:|error|\[init\] (map|protected)|\[placements\])", line):
                log("  " + line.rstrip())
        code_exit = proc.wait()
    text = (out / "convert.log").read_text(encoding="utf-8", errors="replace")
    report = parse_convert_log(text)
    entry.update({"finished_at": now(), "seconds": round(time.monotonic() - started), "exit_code": code_exit,
                  "report": report, "status": "converted" if code_exit == 0 and report["done"] else "failed"})
    archive.save(rec)
    log(f"== {entry['status']} in {entry['seconds']}s: {len(report['dropped'])} dropped kinds, "
        f"{len(report['warnings'])} warnings, {len(report['errors'])} error lines")
    if entry["status"] == "converted" and a.pack:
        pack_conversion(a, archive, rec, entry)
    return entry


def pack_conversion(a, archive: Archive, rec: dict, entry: dict) -> dict:
    """The map pack of a finished conversion (`mjolnir map pack`), with a
    README from the site's metadata."""
    out = Path(entry["out"])
    code = entry["code"]
    m = next((x for x in cache_maps(rec) if x["file"] == entry["map"]),
             {"file": entry["map"], "name": entry.get("map_name")})
    readme = out / "README.md"
    write_readme(rec, m, code, readme)
    mjolnir = os.environ.get("MJOLNIR") or str(REPO / "target/release/mjolnir")
    pack_file = out / f"{a.slug_prefix}{code.lower()}-{a.version}.mjolnir"
    cmd = [mjolnir, "map", "pack", str(out), "--code", code, "--version", a.version,
           "--name", entry.get("title") or rec.get("title") or code,
           "--summary", (rec.get("description") or "")[:200], "--readme", str(readme), "--out", str(pack_file)]
    if a.sign:
        cmd.append("--sign")
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", cwd=str(REPO))
    with open(out / "convert.log", "a", encoding="utf-8") as logf:
        logf.write("\n== pack\n" + r.stdout + r.stderr)
    pm = LOG_PATTERNS["pack"].search(r.stdout)
    entry["pack"] = {"exit_code": r.returncode, "file": pm.group(1) if pm else None,
                     "bytes": int(pm.group(2)) if pm else None, "version": a.version, "signed": bool(a.sign),
                     "packed_at": now()}
    archive.save(rec)
    log(f"  pack: {'wrote ' + pm.group(1) if pm else 'failed: ' + (r.stderr or r.stdout).strip()[-300:]}")
    return entry["pack"]


def cmd_pack(a, archive: Archive, site: Site | None = None) -> None:
    for fid in a.fid:
        rec = archive.get(fid)
        entries = [c for c in rec.get("conversions") or []
                   if c.get("status") == "converted" and (not a.code or c.get("code") == a.code.upper())]
        if not entries:
            log(f"{fid}: no finished conversion{' as ' + a.code.upper() if a.code else ''}")
            continue
        for entry in entries:
            if not Path(entry["out"]).exists():
                log(f"{fid}: {entry['out']} is gone; convert it again")
                continue
            pack_conversion(a, archive, rec, entry)


def cmd_convert(a, archive: Archive, site: Site | None = None) -> None:
    if not Path(a.script).exists():
        sys.exit(f"error: {a.script} not found")
    stop = archive.root / "convert.stop"
    stop.unlink(missing_ok=True)
    if a.fid:
        targets = [archive.get(f) for f in a.fid]
    else:
        targets = next_candidates(archive, a.retry_failed)
        if not targets:
            sys.exit("nothing to convert: every convertible map is converted, or none is extracted yet")
        if not a.count:
            targets = targets[:1]
    done = 0
    for rec in targets:
        if a.count and done >= a.count:
            break
        if stop.exists():
            log(f"stop file seen: {stop}")
            break
        maps = pick_maps(rec, a.map)
        if not maps:
            log(f"{rec['fid']}: no convertible map{' named ' + a.map if a.map else ''} (multiplayer, Custom Edition)")
            continue
        if not a.all_maps:
            maps = [max(maps, key=lambda m: m.get("size") or 0)]
        for m in maps:
            run_convert(a, archive, rec, m)
        done += 1


# ---------------------------------------------------------------------------
# report: edge cases across the archive
# ---------------------------------------------------------------------------

def scripting_summary(records: list[dict], top: int) -> dict:
    """What the multiplayer maps' scripts call and which devices they
    place, against what this game's script engine has: the order to build
    the script port in."""
    defs = {"functions": [], "globals": []}
    if CONSOLE_DEFS.exists():
        with open(CONSOLE_DEFS, encoding="utf-8") as f:
            defs = json.load(f)
    here_fn = {f["name"]: "stub" if f["stub"] else "live" for f in defs["functions"]}
    here_gl = {g["name"]: "no storage" if g["dead"] else "live" for g in defs["globals"]}
    fn_maps: collections.Counter = collections.Counter()
    fn_calls: collections.Counter = collections.Counter()
    gl_maps: collections.Counter = collections.Counter()
    alone: collections.Counter = collections.Counter()  # the one gap of a map that has one
    custom_types: collections.Counter = collections.Counter()
    plane_maps = 0
    n = scripted = readable = fully_live = devices = volumes = switch_bsp = ai = 0
    script_counts = []
    for rec in records:
        for m in cache_maps(rec):
            sc = m.get("scripting")
            if m.get("type") != "multiplayer" or not sc or sc.get("error"):
                continue
            n += 1
            counts = sc.get("counts", {})
            if counts.get("machines") or counts.get("controls"):
                devices += 1
            if counts.get("trigger volumes"):
                volumes += 1
            if counts.get("encounters"):
                ai += 1
            vt = sc.get("vehicle_types", {})
            own = ((m.get("custom") or {}).get("tags") or {}).get("vehi", [])
            kinds = {vt[v] for v in own if v in vt}
            custom_types.update(vt[v] for v in own if v in vt)
            if "human_plane" in kinds:
                plane_maps += 1
            if not counts.get("scripts"):
                continue
            scripted += 1
            script_counts.append(counts["scripts"])
            if not sc.get("readable"):
                continue
            readable += 1
            fns = sc.get("functions", {})
            if "switch_bsp" in fns:
                switch_bsp += 1
            gaps = set()
            for name, c in fns.items():
                fn_maps[name] += 1
                fn_calls[name] += c
                if here_fn.get(name) != "live":
                    gaps.add(name)
            for name in sc.get("engine_globals", {}):
                gl_maps[name] += 1
                if here_gl.get(name) != "live":
                    gaps.add(name)
            if not gaps:
                fully_live += 1
            elif len(gaps) == 1:
                alone[next(iter(gaps))] += 1
    script_counts.sort()
    status = lambda name: here_fn.get(name, "absent")
    return {
        "multiplayer_maps": n,
        "with_scripts": scripted,
        "readable": readable,
        "every_call_live_here": fully_live,
        "median_scripts": script_counts[len(script_counts) // 2] if script_counts else 0,
        "with_devices": devices,
        "with_trigger_volumes": volumes,
        "with_ai_encounters": ai,
        "switch_bsp": switch_bsp,
        "custom_vehicle_types": dict(custom_types.most_common()),
        "maps_with_custom_plane": plane_maps,
        "functions": [{"name": k, "maps": v, "calls": fn_calls[k], "here": status(k)}
                      for k, v in fn_maps.most_common()],
        "missing": [{"name": k, "maps": v, "calls": fn_calls[k], "here": status(k)}
                    for k, v in fn_maps.most_common() if status(k) != "live"][:top * 2],
        "only_gap": alone.most_common(top),
        "engine_globals": [{"name": k, "maps": v, "here": here_gl.get(k, "absent")}
                           for k, v in gl_maps.most_common(top)],
    }


def scripting_lines(s: dict) -> list[str]:
    if not s["multiplayer_maps"]:
        return []
    pct = lambda k: f"{100 * k / max(s['readable'], 1):.0f}%"
    lines = ["", "## Scripts and devices (multiplayer maps)", "",
             f"{s['multiplayer_maps']} maps read: {s['with_scripts']} carry scripts (median "
             f"{s['median_scripts']} scripts), {s['readable']} of them readable; "
             f"{s['every_call_live_here']} ({pct(s['every_call_live_here'])}) call only functions and globals "
             f"this game runs. {s['with_devices']} place machines or controls, {s['with_trigger_volumes']} "
             f"trigger volumes, {s['with_ai_encounters']} AI encounters; {s['switch_bsp']} switch BSPs.", "",
             f"Custom vehicles by CE type: {s['custom_vehicle_types']} "
             f"({s['maps_with_custom_plane']} maps with a custom human_plane).", "",
             "Called but not live here (maps calling, calls, status):", ""]
    lines += [f"- `{f['name']}`: {f['maps']} maps, {f['calls']} calls ({f['here']})" for f in s["missing"]]
    if s["only_gap"]:
        lines += ["", "The only gap in a map's scripts (maps):", ""]
        lines += [f"- `{name}`: {k}" for name, k in s["only_gap"]]
    lines += ["", "Engine globals set or read (maps, status here):", ""]
    lines += [f"- `{g['name']}`: {g['maps']} ({g['here']})" for g in s["engine_globals"]]
    lines += ["", "Most called functions (maps):", "",
              ", ".join(f"`{f['name']}` {f['maps']}" + ("" if f["here"] == "live" else f" ({f['here']})")
                        for f in s["functions"][:60])]
    return lines


def cmd_report(a, archive: Archive, site: Site | None = None) -> None:
    records = archive.records()
    if a.reparse:
        # The parser learns new lines as the edge cases are studied; the logs
        # are kept, so every conversion's report can be read again.
        for rec in records:
            changed = False
            for c in rec.get("conversions") or []:
                if c.get("log") and Path(c["log"]).exists():
                    c["report"] = parse_convert_log(Path(c["log"]).read_text(encoding="utf-8", errors="replace"))
                    changed = True
            if changed:
                archive.save(rec)
    by_class: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    maps_with: collections.Counter = collections.Counter()
    extracted = protected = partial = multiplayer = 0
    engines: collections.Counter = collections.Counter()
    types: collections.Counter = collections.Counter()
    for rec in records:
        maps = cache_maps(rec)
        if maps:
            extracted += 1
        for m in maps:
            engines[m.get("engine")] += 1
            types[m.get("type")] += 1
            if m.get("protected"):
                protected += 1
            if m.get("partially_protected"):
                partial += 1
            if m.get("type") == "multiplayer":
                multiplayer += 1
            custom = m.get("custom")
            if not custom:
                continue
            for cls, paths in custom["tags"].items():
                maps_with[cls] += 1
                for p in paths:
                    by_class[cls][p] += 1
    dropped: collections.Counter = collections.Counter()
    dropped_maps: collections.Counter = collections.Counter()
    warnings: collections.Counter = collections.Counter()
    notes: collections.Counter = collections.Counter()
    statuses: collections.Counter = collections.Counter()
    failures = []
    for rec in records:
        for c in rec.get("conversions") or []:
            statuses[c.get("status")] += 1
            r = c.get("report") or {}
            for d in r.get("dropped", []):
                dropped[d["what"]] += d["count"]
                dropped_maps[d["what"]] += 1
            for w in r.get("warnings", []):
                warnings[re.sub(r"\d+", "N", w)[:120]] += 1
            for n in r.get("notes", []):
                notes[re.sub(r"\d+", "N", n)[:120]] += 1
            if c.get("status") == "failed":
                failures.append({"fid": rec["fid"], "title": rec.get("title"), "code": c.get("code"),
                                 "steps_reached": r.get("steps_reached"), "last_error": (r.get("errors") or ["?"])[-1]})
    scripts = scripting_summary(records, a.top)
    out = {
        "generated_at": now(),
        "records": len(records),
        "extracted": extracted,
        "maps": {"engines": dict(engines), "types": dict(types), "protected": protected,
                 "partially_protected": partial, "multiplayer": multiplayer},
        "custom": {cls: {"maps": maps_with[cls], "distinct": len(by_class[cls]),
                         "top": by_class[cls].most_common(a.top)} for cls in cemap.LISTED_CLASSES if cls in by_class},
        "conversions": {"statuses": dict(statuses),
                        "dropped": [{"what": w, "placements": n, "maps": dropped_maps[w]} for w, n in dropped.most_common(a.top)],
                        "warnings": warnings.most_common(a.top),
                        "notes": notes.most_common(a.top),
                        "failures": failures},
        "scripting": scripts,
    }
    with open(archive.root / "report.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    lines = [f"# halomaps.org archive report ({out['generated_at']})", "",
             f"{len(records)} records, {extracted} unpacked, {sum(types.values())} cache files "
             f"({multiplayer} multiplayer, {protected} protected, {partial} with some tag names blanked).", "",
             "## Custom tags, by class (maps carrying any, and the tags most maps share)", ""]
    for cls, info in out["custom"].items():
        lines.append(f"- **{cemap.CLASS_NAMES.get(cls, cls)}** (`{cls.strip()}`): {info['maps']} maps, "
                     f"{info['distinct']} distinct tags")
        for path, n in info["top"][: min(a.top, 10)]:
            lines.append(f"  - {n:3} maps: `{path}`")
    lines += scripting_lines(scripts)
    lines += ["", "## Conversions", "", f"statuses: {dict(statuses)}", ""]
    if dropped:
        lines.append("dropped placements (no equivalent in this game, or unmapped):")
        for d in out["conversions"]["dropped"]:
            lines.append(f"- {d['placements']:4} placements in {d['maps']} maps: `{d['what']}`")
        lines.append("")
    if warnings:
        lines.append("warnings:")
        lines += [f"- {n:3} x {w}" for w, n in out["conversions"]["warnings"]]
        lines.append("")
    if failures:
        lines.append("failures:")
        lines += [f"- {f['fid']} {f['title']} ({f['code']}): step {f['steps_reached']}, {f['last_error']}" for f in failures]
    (archive.root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log("\n".join(lines))
    log(f"\nwrote {archive.root / 'report.json'}, report.md")


# ---------------------------------------------------------------------------
# status, show, mirror
# ---------------------------------------------------------------------------

def cmd_status(a, archive: Archive, site: Site | None = None) -> None:
    records = archive.records()
    fetched = sum("detail" in r for r in records)
    downloaded = [r for r in records if (r.get("download") or {}).get("file_name")]
    skipped = sum(bool((r.get("download") or {}).get("skipped")) for r in records)
    errors = sum(bool((r.get("download") or {}).get("error")) for r in records)
    extracted = [r for r in records if (r.get("archive") or {}).get("maps") is not None]
    maps = [m for r in extracted for m in cache_maps(r)]
    conv = collections.Counter(conversion_status(r) for r in records if conversion_status(r))
    log(f"root        {archive.root}")
    log(f"records     {len(records)} (by section: "
        + ", ".join(f"{k}={v}" for k, v in collections.Counter((r.get('section') or {}).get('name') for r in records).items()) + ")")
    log(f"fetched     {fetched}")
    log(f"downloaded  {len(downloaded)} ({sum(r['download']['size'] for r in downloaded) / 2**30:.2f} GB), "
        f"{skipped} skipped, {errors} errors")
    log(f"extracted   {len(extracted)} archives, {len(maps)} cache files "
        f"({sum(m.get('type') == 'multiplayer' for m in maps)} multiplayer, {sum(bool(m.get('protected')) for m in maps)} protected, "
        f"{sum(bool(r.get('archive', {}).get('error')) for r in records)} extraction errors)")
    log(f"converted   {dict(conv)}")
    nxt = next_candidates(archive, False)
    if nxt:
        r = nxt[0]
        log(f"next        {r['fid']} {r.get('title')} (rating {r.get('rating_text')}, "
            f"{len((r.get('screenshots') or {}).get('user') or [])} user screenshots)")


def cmd_show(a, archive: Archive, site: Site | None = None) -> None:
    for fid in a.fid:
        rec = archive.load(fid)
        if not rec:
            log(f"{fid}: no record")
            continue
        if a.json:
            log(json.dumps(rec, indent=1, ensure_ascii=False))
            continue
        s = summarize(rec)
        log(f"{fid}: {s['title']} by {s['author']} ({s['date']}) rating {s['rating_text']}, "
            f"{s['user_screenshots']} user screenshots, {s['section']} / {s['category']}")
        log(f"  {rec.get('description') or ''}")
        log(f"  file {s['file_name']} {s['size']} bytes; maps {s['map_names']} [{s['map_types']}; {s['engines']}]"
            f"{'; PROTECTED' if s['protected'] else ''}; bsps {s['bsps']}; custom {s['custom_total']}")
        for m in cache_maps(rec):
            for cls, paths in ((m.get("custom") or {}).get("tags") or {}).items():
                if cls in ("weap", "vehi", "scen", "bipd", "eqip", "mach", "ctrl"):
                    log(f"    {cemap.CLASS_NAMES.get(cls, cls)}: " + ", ".join(paths[:12]) + (" ..." if len(paths) > 12 else ""))
        for c in rec.get("conversions") or []:
            r = c.get("report") or {}
            log(f"  conversion {c.get('code')}: {c.get('status')} ({c.get('seconds')}s), "
                f"dropped {sum(d['count'] for d in r.get('dropped', []))}, warnings {len(r.get('warnings', []))}")
            for d in r.get("dropped", []):
                log(f"    dropped {d['count']} x {d['what']}")


def cmd_mirror(a, archive: Archive, site: Site) -> None:
    """The pages and files first, the pictures last: the maps are the point,
    and a page's thirty user screenshots take longer than its file."""
    cmd_crawl(a, archive, site)
    a.no_screenshots = True
    cmd_fetch(a, archive, site)
    cmd_download(a, archive, site)
    cmd_extract(a, archive, site)
    cmd_catalog(a, archive, site)
    if not a.skip_screenshots:
        cmd_screenshots(a, archive, site)


# ---------------------------------------------------------------------------

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=f"the archive folder (default {DEFAULT_ROOT})")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between requests (default 1.5)")
    ap.add_argument("--image-delay", type=float, default=0.4, help="seconds between screenshot requests")
    ap.add_argument("--stock-maps", type=Path, default=DEFAULT_STOCK_MAPS,
                    help="the stock CE maps with bitmaps.map and sounds.map beside them (the stock tag set, "
                         "the exporter's resources and the reference maps for protected maps)")
    sub = ap.add_subparsers(dest="command", required=True)

    def common_fetch(p):
        p.add_argument("--fid", type=int, nargs="*", help="only these entries")
        p.add_argument("--limit", type=int, help="stop after this many")

    p = sub.add_parser("crawl", help="read the listings into one record per map")
    p.add_argument("--sid", type=int, nargs="*", help=f"sections to crawl (default {MULTIPLAYER_SECTIONS})")
    p.add_argument("--pages", type=int, help="at most this many pages per section")
    p.set_defaults(func=cmd_crawl)

    p = sub.add_parser("fetch", help="each map's page, metadata and screenshots")
    common_fetch(p)
    p.add_argument("--refresh", action="store_true", help="fetch pages already fetched")
    p.add_argument("--no-screenshots", action="store_true")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("screenshots", help="the screenshots of pages fetched without them")
    common_fetch(p)
    p.set_defaults(func=cmd_screenshots)

    p = sub.add_parser("download", help="the files")
    common_fetch(p)
    p.add_argument("--max-mb", type=float, help="skip files announced larger than this")
    p.add_argument("--redo", action="store_true")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("extract", help="unpack the files and read every .map")
    common_fetch(p)
    p.add_argument("--redo", action="store_true", help="unpack again")
    p.add_argument("--resurvey", action="store_true", help="read the unpacked maps again, without unpacking")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("scripts", help="read each unpacked map's scripts, devices and vehicle types")
    common_fetch(p)
    p.add_argument("--redo", action="store_true", help="read maps already read")
    p.set_defaults(func=cmd_scripts)

    p = sub.add_parser("catalog", help="catalog.json and catalog.csv; print the top entries")
    p.add_argument("--sort", choices=sorted(SORTS), default="rating")
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--convertible", action="store_true", help="only unconverted multiplayer CE maps")
    p.set_defaults(func=cmd_catalog)

    p = sub.add_parser("convert", help="convert one entry's map through convert_ce_map.sh")
    p.add_argument("--fid", type=int, nargs="*", help="these entries; otherwise the best unconverted one")
    p.add_argument("--next", action="store_true", help="(the default when no --fid is given)")
    p.add_argument("--count", type=int, help="convert this many of the best unconverted maps in turn")
    p.add_argument("--retry-failed", action="store_true")
    p.add_argument("--map", help="the .map inside the entry (file or scenario name); default the largest")
    p.add_argument("--all-maps", action="store_true", help="every multiplayer map the entry holds")
    p.add_argument("--code", help="the codename (default: proposed from the title)")
    p.add_argument("--install", action="store_true", help="install into the game (convert_ce_map.sh --install)")
    p.add_argument("--pack", action="store_true", help="then build the map pack (mjolnir map pack)")
    p.add_argument("--version", default="1.0.0", help="the pack's version")
    p.add_argument("--sign", action="store_true", help="sign the pack")
    p.add_argument("--slug-prefix", default="halomaps-", help="the pack file's name prefix")
    p.add_argument("--script", type=Path, default=CONVERT_SCRIPT)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("pack", help="the map pack of a finished conversion (again, or signed)")
    p.add_argument("--fid", type=int, nargs="+", required=True)
    p.add_argument("--code", help="which of the entry's conversions; default every finished one")
    p.add_argument("--version", default="1.0.0")
    p.add_argument("--sign", action="store_true")
    p.add_argument("--slug-prefix", default="halomaps-")
    p.set_defaults(func=cmd_pack)

    p = sub.add_parser("report", help="custom tags and conversion outcomes across the archive")
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--reparse", action="store_true", help="read every conversion's log again first")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("status", help="how far each stage has got")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("show", help="one record")
    p.add_argument("fid", type=int, nargs="+")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("mirror", help="crawl, fetch, download, extract, catalog, then the screenshots")
    p.add_argument("--sid", type=int, nargs="*")
    p.add_argument("--pages", type=int)
    p.add_argument("--fid", type=int, nargs="*")
    p.add_argument("--limit", type=int)
    p.add_argument("--max-mb", type=float)
    p.add_argument("--skip-screenshots", action="store_true", help="leave the pictures for a `screenshots` run")
    p.set_defaults(func=cmd_mirror, refresh=False, redo=False, sort="rating", top=25, convertible=False)

    a = ap.parse_args()
    archive = Archive(a.root)
    site = Site(delay=a.delay)
    a.func(a, archive, site)
    return 0


if __name__ == "__main__":
    sys.exit(main())
