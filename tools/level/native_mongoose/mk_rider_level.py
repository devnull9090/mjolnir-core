"""nmg_rider.level.json: the NMG level with the stock player rows, row 0's unit swapped."""
import json
import sys

N = sys.argv[1]
UNIT = sys.argv[2] if len(sys.argv) > 2 else r"bipd:objects\mjolnir\nmg\spartan"
d = json.load(open(N + "/nmg.level.json", encoding="utf-8"))
IN = r"snd!:sound\game_sfx\ui\binoculars\binocs_in_click"
OUT = r"snd!:sound\game_sfx\ui\binoculars\binocs_out_click"
d["blam"]["player_representations"] = [
    {"chud reference": r"chdt:ui\chud\spartan",
     "first person hands": r"hlmt:objects\characters\spartans_fp\spartans_fp",
     "first person body": r"hlmt:objects\characters\spartans\fp_body\fp_body",
     "third person unit": UNIT,
     "intrinsic primary equipment": r"eqip:objects\equipment\sprint\sprint_intrinsic",
     "intrinsic secondary equipment": r"eqip:objects\equipment\flashlight\flashlight",
     "binoculars zoom in sound": IN, "binoculars zoom out sounds": OUT,
     "faction": "unsc", "player information": "0"},
    {"chud reference": r"chdt:ui\chud\elite",
     "first person hands": r"mode:objects\characters\elite\fp\fp",
     "first person body": r"mode:objects\characters\elite\fp_body\fp_body",
     "third person unit": r"bipd:objects\characters\elite\elite",
     "third person variant": "mp",
     "binoculars zoom in sound": IN, "binoculars zoom out sounds": OUT,
     "player information": "1"},
    {"chud reference": r"chdt:ui\chud\monitor",
     "third person unit": r"bipd:objects\characters\monitor\monitor_editor",
     "player information": "0"},
]
json.dump(d, open(N + "/nmg_rider.level.json", "w", encoding="utf-8"), indent=1)
