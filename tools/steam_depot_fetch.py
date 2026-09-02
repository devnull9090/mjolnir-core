"""Fetch an older Halo Campaign Evolved build from Steam's depot history.

Steam patches in place, but its CDN keeps the old depot manifests around for a
while — so a build we never snapshotted is not necessarily lost. This wraps
DepotDownloader (https://github.com/SteamRE/DepotDownloader) to pull one
historical manifest into a directory laid out exactly like an install, then
optionally ingests it straight into the snapshot store, where
`game_snapshot.py materialize` and `mjolnir tagdiff` can use it like any build
we caught live.

Login is interactive and stays between the user and Steam: `--qr` shows a QR
code to scan with the Steam Mobile app (no password typed anywhere), or
`--username` makes DepotDownloader prompt for the password itself. Either way
`-remember-password` is passed, so later runs reuse the stored token.

Manifest IDs come from SteamDB (steamdb.info/depot/2806051/manifests/) —
`--list` prints the ones known at the time of writing. One honest caveat: since
2021 Steam grants manifest *request codes* per manifest, and codes for old
manifests are not guaranteed forever. If Steam refuses ("manifest request code
was denied"), that build is out of reach through official channels and no flag
here will change it — which is exactly why every build from CU4 on gets
snapshotted the day it lands.

Usage:
    python tools/steam_depot_fetch.py --list
    python tools/steam_depot_fetch.py 457322918737678760 --name cu3 --qr --store D:/hce-snapshots
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

APP = "2806050"
CONTENT_DEPOT = "2806051"
DLC_DEPOT = "4192200"
# The DigitalExtras depot has shipped exactly one manifest since launch, so
# every historical build pairs with it unchanged.
DLC_MANIFEST = "7241924470348670959"

# Every depot 2806051 manifest SteamDB has seen as of 2026-08-19 — all three
# are downloaded, snapshotted and confirmed by their exe version stamps. The
# CU numbering predates the Steam release: the launch/preload build is stamped
# CU2, and no older manifest exists, so there is no Steam "CU1".
KNOWN_MANIFESTS = [
    ("5851394981381786761", "shipped 2026-08-17", "CU4 (2026.08.11.1121610.2)"),
    ("457322918737678760", "shipped 2026-07-29", "CU3 (2026.07.25.1112544.4)"),
    ("8153709523381701809", "launch/preload 2026-07-23", "CU2 (2026.06.26.1097863.1)"),
]

DEFAULT_TOOL = Path("D:/hce-depots/DepotDownloader/DepotDownloader.exe")
DEFAULT_OUT_ROOT = Path("D:/hce-depots")


def run_depotdownloader(tool: Path, args: list[str]) -> int:
    """Run DepotDownloader with stdio inherited, so login prompts and the QR
    code reach the terminal untouched."""
    cmd = [str(tool), *args]
    print(f"# {' '.join(cmd)}", file=sys.stderr)
    return subprocess.run(cmd).returncode


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("manifest", nargs="?", help="content depot manifest ID (see --list)")
    ap.add_argument("--list", action="store_true", help="print known manifest IDs and exit")
    ap.add_argument("--name", help="directory name under the out root; defaults to the manifest ID")
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT, help="where builds land")
    ap.add_argument("--tool", type=Path, default=DEFAULT_TOOL, help="DepotDownloader.exe path")
    ap.add_argument("--qr", action="store_true", help="log in by QR code (Steam Mobile app)")
    ap.add_argument("--username", help="log in by username; DepotDownloader prompts for the password")
    ap.add_argument("--skip-dlc", action="store_true", help="content depot only, no DigitalExtras")
    ap.add_argument("--store", type=Path, help="after download, snapshot the build into this store")
    args = ap.parse_args()

    if args.list:
        print(f"app {APP}, content depot {CONTENT_DEPOT}, dlc depot {DLC_DEPOT}")
        for manifest, seen, guess in KNOWN_MANIFESTS:
            print(f"  {manifest:>22}  {seen}  {guess}")
        print("current list: https://steamdb.info/depot/2806051/manifests/")
        return 0

    if not args.manifest:
        ap.error("a manifest ID is required (or --list)")
    if not args.qr and not args.username:
        ap.error("pick a login: --qr (Steam Mobile app) or --username <steam user>")
    if not args.tool.is_file():
        sys.exit(
            f"error: {args.tool} not found — unzip the DepotDownloader release there, "
            "or pass --tool"
        )

    out = args.out_root / (args.name or args.manifest)
    login = ["-qr"] if args.qr else ["-username", args.username]
    common = [*login, "-remember-password", "-app", APP, "-dir", str(out)]

    code = run_depotdownloader(
        args.tool, [*common, "-depot", CONTENT_DEPOT, "-manifest", args.manifest]
    )
    if code != 0:
        sys.exit(
            f"error: content depot download failed (exit {code}). If the message names a "
            "denied manifest request code, Steam no longer serves this manifest."
        )
    if not args.skip_dlc:
        code = run_depotdownloader(
            args.tool, [*common, "-depot", DLC_DEPOT, "-manifest", DLC_MANIFEST]
        )
        if code != 0:
            sys.exit(f"error: DigitalExtras depot download failed (exit {code})")

    print(f"# downloaded to {out}")
    if args.store:
        # Same interpreter, same tools directory; the snapshot reads the build
        # version out of the downloaded exe, so the store names it correctly
        # whatever --name said.
        snapshot = Path(__file__).resolve().parent / "game_snapshot.py"
        code = subprocess.run(
            [sys.executable, str(snapshot), "--store", str(args.store), "snapshot", str(out)]
        ).returncode
        if code != 0:
            sys.exit(f"error: snapshot ingest failed (exit {code})")
        print(f"# snapshotted into {args.store}; the depot directory is now redundant")
        print(f"#   python tools/game_snapshot.py --store {args.store} list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
