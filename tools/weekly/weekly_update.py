"""Gather what shipped since the last weekly update, and check a finished draft.

The weekly post on mjolnircore.com/blog is written by a person or an agent, but
its raw material should not be remembered: this script reads it from the
repository, so nothing that shipped depends on someone recalling it. It uses no
network beyond `gh`, and it decides nothing about what is worth telling players.
The run book is `.claude/skills/weekly-update/SKILL.md`.

Usage:
    python tools/weekly/weekly_update.py gather [--since YYYY-MM-DD] [--out digest.md]
    python tools/weekly/weekly_update.py check blog/YYYY-MM-DD-slug.md

`gather` starts from the newest post tagged `weekly-update` unless told
otherwise, and from seven days ago if there is none. `check` fails on a dead
site link, a missing image, a long summary, or a long X post.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BLOG = REPO / "blog"
CHANGELOG = REPO / "changelog"
DOCS_JSON = REPO / "hub" / "src" / "generated" / "docs.json"
PUBLIC = REPO / "hub" / "public"

GITHUB_BLOB = "https://github.com/devnull9090/mjolnir-core/blob/main"

POST_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-([a-z0-9-]+)\.md$")
SUMMARY_MAX = 300
X_MAX = 280
X_URL_LENGTH = 23  # X counts every link as this many characters
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".svg", ".gif")


def run(*args: str) -> str:
    done = subprocess.run(
        args, cwd=REPO, capture_output=True, encoding="utf-8", errors="replace", check=True
    )
    return done.stdout


def meta_value(text: str, label: str) -> str | None:
    """Reads a `**Label:** value` line, the format posts and changelogs share."""
    match = re.search(rf"^\*\*{label}:\*\*\s*(.+?)\s*$", text, re.MULTILINE)
    return match.group(1) if match else None


def newest_weekly_date(blog_dir: Path = BLOG) -> str | None:
    """The date of the newest post tagged `weekly-update`, or None."""
    newest = None
    for path in blog_dir.glob("*.md"):
        match = POST_NAME.match(path.name)
        if not match:
            continue
        tags = meta_value(path.read_text(encoding="utf-8"), "Tags") or ""
        if "weekly-update" in (tag.strip() for tag in tags.split(",")):
            newest = max(newest or "", match.group(1))
    return newest


def doc_urls(docs: dict) -> dict[str, str]:
    """Maps `docs/x.md` to the page the hub serves it on."""
    urls = {}
    for kind, route in (("notes", "/docs/notes"), ("guides", "/docs/guides")):
        for page in docs.get(kind, []):
            source = page.get("sourcePath", "")
            tail = source.split("/docs/")[-1].removeprefix("docs/")
            urls[f"docs/{tail}"] = f"{route}/{page['slug']}"
    return urls


def x_length(text: str) -> int:
    """Length as X counts it: every URL costs the same, whatever its length."""
    return len(re.sub(r"https?://\S+", "x" * X_URL_LENGTH, text.strip()))


def load_docs() -> dict:
    return json.loads(DOCS_JSON.read_text(encoding="utf-8"))


def changed_files(since: str, *paths: str, status: str = "AM") -> list[tuple[str, str]]:
    """(status, path) for files touched since a date; a file added counts as new."""
    out = run(
        "git", "log", f"--since={since}", "--name-status", "--format=",
        f"--diff-filter={status}", "--", *paths,
    )
    seen: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            seen[parts[-1]] = "A" if parts[0] == "A" or seen.get(parts[-1]) == "A" else "M"
    return sorted((state, path) for path, state in seen.items())


def releases(since: str) -> list[dict]:
    products = json.loads((CHANGELOG / "products.json").read_text(encoding="utf-8"))["products"]
    prefixes = {p["tagPrefix"]: p for p in products}
    out = run(
        "git", "tag", "--sort=-creatordate",
        "--format=%(creatordate:short) %(refname:short)",
    )
    found = []
    for line in out.splitlines():
        date, _, tag = line.partition(" ")
        if date < since:
            continue
        for prefix, product in prefixes.items():
            if not tag.startswith(prefix):
                continue
            version = tag.removeprefix(prefix)
            entry = CHANGELOG / product["id"] / f"{version}.md"
            text = entry.read_text(encoding="utf-8") if entry.exists() else ""
            title = text.splitlines()[0].lstrip("# ").strip() if text else ""
            found.append({
                "date": date, "tag": tag, "product": product["name"], "title": title,
                "summary": meta_value(text, "Summary") or "",
                "url": f"/changelog/{product['id']}/{version}",
            })
    return found


def merged_prs(since: str) -> list[dict]:
    out = run(
        "gh", "pr", "list", "--state", "merged", "--limit", "300",
        "--search", f"merged:>={since}",
        "--json", "number,title,mergedAt,mergeCommit,url",
    )
    return sorted(json.loads(out), key=lambda pr: pr["mergedAt"])


def tagged_commits() -> set[str]:
    return set(run("git", "rev-list", "--tags").split())


def gather(since: str) -> str:
    urls = doc_urls(load_docs())
    lines = [f"# Weekly digest since {since}", ""]

    lines += ["## Releases", ""]
    tagged = releases(since)
    for rel in tagged:
        lines.append(f"- {rel['date']} `{rel['tag']}` {rel['title']} ({rel['url']})")
        if rel["summary"]:
            lines.append(f"  - {rel['summary']}")
    if not tagged:
        lines.append("None.")

    lines += ["", "## Merged pull requests", ""]
    try:
        prs = merged_prs(since)
    except (OSError, subprocess.CalledProcessError) as error:
        prs = []
        lines.append(f"Could not read pull requests from gh: {error}")
    reachable = tagged_commits()
    for pr in prs:
        oid = (pr.get("mergeCommit") or {}).get("oid", "")
        flag = "" if oid in reachable else " **[in no tag yet]**"
        lines.append(f"- #{pr['number']} {pr['mergedAt'][:10]} {pr['title']}{flag}")
    lines += [
        "",
        "A PR marked **[in no tag yet]** has reached no release. Hub pages deploy on",
        "merge, so only those can go in the post; anything else waits for its tag.",
        "An unmarked PR is only behind some tag, which may be another product's:",
        "check the release that carries it, and remember maps ship on the hub, not in tags.",
    ]

    lines += ["", "## Documentation", ""]
    for state, path in changed_files(since, "docs"):
        if not path.endswith(".md"):
            continue
        word = "new" if state == "A" else "updated"
        lines.append(f"- {word}: {urls.get(path) or f'{GITHUB_BLOB}/{path}'}")

    lines += ["", "## Blog posts already covering this period", ""]
    for path in sorted(BLOG.glob("*.md")):
        match = POST_NAME.match(path.name)
        if match and match.group(1) >= since:
            lines.append(f"- /blog/{match.group(2)} ({match.group(1)})")

    lines += ["", "## Forge packs and maps touched", ""]
    areas = sorted({
        "/".join(path.split("/")[:2])
        for _, path in changed_files(since, "forge-packs", "forge-maps", "levels")
    })
    lines += [f"- {area}" for area in areas] or ["None."]

    lines += ["", "## Images added to the site", ""]
    images = [
        path for _, path in changed_files(since, "hub/public", status="A")
        if path.lower().endswith(IMAGE_SUFFIXES)
    ]
    lines += [f"- {path.removeprefix('hub/public')}" for path in images] or ["None."]
    return "\n".join(lines) + "\n"


def check(post: Path) -> list[str]:
    """Everything wrong with a finished draft. Empty means it can go to review."""
    problems = []
    text = post.read_text(encoding="utf-8")
    match = POST_NAME.match(post.name)
    if not match:
        return [f"{post.name}: file name must be YYYY-MM-DD-slug.md"]
    slug = match.group(2)

    summary = meta_value(text, "Summary")
    if not summary:
        problems.append("no **Summary:** line")
    elif len(summary) > SUMMARY_MAX:
        problems.append(f"summary is {len(summary)} characters, limit {SUMMARY_MAX}")
    if "weekly-update" not in (meta_value(text, "Tags") or ""):
        problems.append("missing the weekly-update tag")

    pages = set(doc_urls(load_docs()).values())
    slugs = {m.group(2) for p in BLOG.glob("*.md") if (m := POST_NAME.match(p.name))}
    targets = re.findall(r"\]\((/[^)\s]+)", text)
    image = meta_value(text, "Image")
    if image:
        targets.append(image)
    else:
        problems.append("no **Image:** line")
    for target in targets:
        for path in target.split("&labels=")[0].split("?before="):
            path = path.split("#")[0].split("?")[0]
            if path.startswith(("/docs/guides/", "/docs/notes/")) and path not in pages:
                problems.append(f"dead doc link: {path}")
            elif path.startswith("/blog/") and path.count("/") == 2 and path[6:] not in slugs:
                problems.append(f"dead blog link: {path}")
            elif path.lower().endswith(IMAGE_SUFFIXES) and not (PUBLIC / path.lstrip("/")).exists():
                problems.append(f"missing image: {path}")

    social = post.parent / "social" / f"{slug}.x.txt"
    if not social.exists():
        problems.append(f"no X post at blog/social/{social.name}")
    else:
        body = social.read_text(encoding="utf-8")
        if x_length(body) > X_MAX:
            problems.append(f"X post is {x_length(body)} characters, limit {X_MAX}")
        if f"mjolnircore.com/blog/{slug}" not in body:
            problems.append("X post does not link the post")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    gather_cmd = commands.add_parser("gather", help="print what shipped in the window")
    gather_cmd.add_argument("--since", help="start date, YYYY-MM-DD")
    gather_cmd.add_argument("--out", type=Path, help="write here instead of stdout")
    check_cmd = commands.add_parser("check", help="check a finished draft")
    check_cmd.add_argument("post", type=Path)
    args = parser.parse_args()

    if args.command == "check":
        problems = check(args.post)
        for problem in problems:
            print(f"{args.post.name}: {problem}", file=sys.stderr)
        print("ok" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0

    since = args.since or newest_weekly_date()
    if since is None:
        since = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    digest = gather(since)
    if args.out:
        args.out.write_text(digest, encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
