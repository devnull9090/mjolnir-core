"""Build a single-speaker training set from exported clips and their transcripts.

  python make_dataset.py <clip dir> <out dir> --ref <ref clip name> [--holdout 12]

Reads <clip dir>/transcripts.tsv (transcribe.py). Keeps clips of 1-15 s (--min-seconds lowers the 1) that
Whisper heard confidently (avg_logprob > -0.6, no_speech < 0.3). A line that
ships twice with the same words (Campaign Evolved has many: one dry, one
through the ship's intercom) keeps the copy with more energy above 4 kHz, the
dry one. Writes 24 kHz mono WAVs to <out dir>/wavs, the reference to
<out dir>/ref.wav, and
  train_raw.jsonl    {audio, text, ref_audio} (Qwen3-TTS finetuning format)
  holdout.tsv        file, text: lines kept out of training, for evaluation
  gptsovits.list     wav|speaker|EN|text (GPT-SoVITS training list)
"""
import argparse
import json
import os
import random
import re

import numpy as np
import soundfile as sf
import torch
import torchaudio.functional as F

RATE = 24000


def load(path):
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    mono = torch.from_numpy(np.ascontiguousarray(data.mean(axis=1)))
    return F.resample(mono, rate, RATE).numpy() if rate != RATE else mono.numpy()


def brightness(audio):
    spec = np.abs(np.fft.rfft(audio)) ** 2
    freqs = np.fft.rfftfreq(len(audio), 1 / RATE)
    return spec[freqs > 4000].sum() / max(spec.sum(), 1e-9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips")
    ap.add_argument("out")
    ap.add_argument("--ref", required=True)
    ap.add_argument("--speaker", default="cortana")
    ap.add_argument("--holdout", type=int, default=12)
    ap.add_argument("--min-seconds", type=float, default=1.0, help="announcer calls run 0.6-1 s")
    a = ap.parse_args()
    rows = []
    for line in open(os.path.join(a.clips, "transcripts.tsv"), encoding="utf-8").read().splitlines()[1:]:
        name, seconds, text, logprob, no_speech = line.split("\t")
        if a.min_seconds <= float(seconds) <= 15.0 and float(logprob) > -0.6 and float(no_speech) < 0.3 and text:
            rows.append((name, text))
    groups = {}
    for name, text in rows:
        groups.setdefault(re.sub(r"\W+", " ", text.lower()).strip(), []).append((name, text))
    os.makedirs(os.path.join(a.out, "wavs"), exist_ok=True)
    kept = []
    for items in groups.values():
        audios = [(load(os.path.join(a.clips, n)), n, t) for n, t in items]
        audio, name, text = max(audios, key=lambda x: brightness(x[0]))
        dest = os.path.join(a.out, "wavs", os.path.splitext(name)[0] + ".wav")
        sf.write(dest, audio, RATE)
        kept.append((dest, text, name))
    ref = os.path.join(a.out, "ref.wav")
    sf.write(ref, load(os.path.join(a.clips, a.ref)), RATE)
    kept.sort()
    random.Random(11).shuffle(kept)
    held = [k for k in kept if k[2] != a.ref][: a.holdout]
    train = [k for k in kept if k not in held]
    with open(os.path.join(a.out, "train_raw.jsonl"), "w", encoding="utf-8") as f:
        for dest, text, _ in train:
            f.write(json.dumps({"audio": dest, "text": text, "ref_audio": ref}) + "\n")
    with open(os.path.join(a.out, "gptsovits.list"), "w", encoding="utf-8") as f:
        for dest, text, _ in train:
            f.write(f"{dest}|{a.speaker}|EN|{text}\n")
    with open(os.path.join(a.out, "holdout.tsv"), "w", encoding="utf-8") as f:
        for dest, text, _ in held:
            f.write(f"{dest}\t{text}\n")
    minutes = sum(len(sf.read(d)[0]) for d, _, _ in train) / RATE / 60
    print(f"{len(rows)} usable, {len(kept)} after duplicates; {len(train)} train ({minutes:.1f} min), {len(held)} held out")


if __name__ == "__main__":
    main()
