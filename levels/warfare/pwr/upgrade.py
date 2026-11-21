"""Run the established remaster pipeline with PWR's private configuration.

python levels/warfare/pwr/upgrade.py --stages land,foliage,swap,collision
python levels/warfare/pwr/upgrade.py --stages editor,cook,bake,assemble

No shared map configuration is changed. Installation is a separate explicit stage.
"""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
sys.path.insert(0, str(REPO / "tools/level"))
import upgrade_ce_map

if __name__ == "__main__":
    wrapper = argparse.ArgumentParser(add_help=False)
    wrapper.add_argument("--config", type=Path, default=ROOT / "upgrade.json")
    options, arguments = wrapper.parse_known_args()
    upgrade_ce_map.CONFIG = str(options.config.resolve())
    if not any(arg == "--work" or arg.startswith("--work=") for arg in arguments):
        if options.config.resolve() != (ROOT / "upgrade.json").resolve():
            wrapper.error("A custom --config requires an explicit --work directory")
        arguments += ["--work", "C:/haloce/ce_conversions/warfare/PWR/expansion/world-v3/upgrade"]
    sys.argv = [sys.argv[0], "PWR"] + arguments
    upgrade_ce_map.main()
