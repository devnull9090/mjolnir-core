"""Design an original voice from a written description (Qwen3-TTS VoiceDesign).

  D:/hce-voice/envs/qwen3/Scripts/python.exe tools/voice/design_voice.py \
      --persona ai --out <dir> [--takes 8]

No recording of anyone is used: the VoiceDesign model makes a new voice from
the persona's description below. Each take is one candidate reference, a
neutral sentence in that voice, written as <dir>/<persona>_<n>.wav beside
<dir>/design.json (description, sentence, seeds), so a chosen voice can be
made again. Pick a candidate with distinct.py (it must be measurably unlike
the performer whose role inspired it) and by listening, then render every
line from it with say_qwen3.py --ref (the Base model clones the designed
voice, which keeps it the same from line to line).

The descriptions name qualities, never a person: the voices are inspired by
the series' characters, not imitations of their actors (credited as such on
the hub's credits page).
"""
import argparse
import json
import os

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

PERSONAS = {
    # Warfare's AI companion: speaks to the player during the drop and the fight.
    "ai": {
        "description": (
            "A woman in her early thirties with a calm, quick-witted voice: precise, clear diction, "
            "a warm and slightly bright mid-range tone, confident and a little dry, like a tactical "
            "adviser talking a soldier through a mission over a radio. Neutral American accent. "
            "Clean, close studio recording."
        ),
        "sentence": (
            "Stay low and keep moving. The landing zone is two hundred metres east of you, "
            "and I'll tell you the moment anything changes."
        ),
    },
    # The match announcer: names the game, the zones and the result.
    "announcer": {
        "description": (
            "A man in his forties with a deep, resonant, commanding voice: an arena announcer "
            "who speaks slowly and emphatically, every word weighted and dramatic, with a slight "
            "gravelly edge. Neutral American accent. Clean, close studio recording."
        ),
        "sentence": "Welcome to the arena. Three zones. Two teams. Only one side walks away the winner.",
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", required=True, choices=sorted(PERSONAS))
    ap.add_argument("--out", required=True)
    ap.add_argument("--takes", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7000)
    ap.add_argument("--model", default="Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
    a = ap.parse_args()
    p = PERSONAS[a.persona]
    model = Qwen3TTSModel.from_pretrained(a.model, device_map="cuda:0", dtype=torch.bfloat16, attn_implementation="sdpa")
    os.makedirs(a.out, exist_ok=True)
    seeds = []
    for n in range(a.takes):
        seed = a.seed + n
        torch.manual_seed(seed)
        wavs, rate = model.generate_voice_design(text=p["sentence"], instruct=p["description"], language="English",
                                                 max_new_tokens=int(25 * 12.5))
        path = os.path.join(a.out, f"{a.persona}_{n}.wav")
        sf.write(path, wavs[0], rate)
        seeds.append({"file": os.path.basename(path), "seed": seed, "seconds": round(len(wavs[0]) / rate, 2)})
        print(f"{path}: {seeds[-1]['seconds']} s")
    with open(os.path.join(a.out, "design.json"), "w", encoding="utf-8") as f:
        json.dump({"persona": a.persona, "model": a.model, "description": p["description"],
                   "sentence": p["sentence"], "takes": seeds}, f, indent=1)


if __name__ == "__main__":
    main()
