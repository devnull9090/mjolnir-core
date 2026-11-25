"""Find one speaker's clips in a pile of unnamed dialogue (SpeechBrain ECAPA).

  python speaker_filter.py --known <dir of the speaker's clips> <pile dir> \
      [--threshold 0.6] [--copy <dir>] [--max-seconds 20]

The speaker is the mean embedding of up to 60 known clips. Every clip in the
pile scores the cosine to it; scores.tsv in the pile lists them, highest first,
with a histogram on stdout so the gap between this speaker and the rest can be
read before choosing --threshold. With --copy, clips at or above it are copied
there. A known clip set from another game works: the score is a filter, and the
dataset step (transcribe.py, make_dataset.py) and listening come after it.
"""
import argparse
import os
import random
import shutil

import numpy as np
import soundfile as sf
import torch
import torchaudio.functional as F

AUDIO = (".wav", ".ogg", ".flac")


def load(path, limit):
    data, rate = sf.read(path, dtype="float32", always_2d=True, frames=int(limit * 48000))
    mono = torch.from_numpy(np.ascontiguousarray(data.mean(axis=1)))
    return F.resample(mono, rate, 16000) if rate != 16000 else mono


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--known", required=True, nargs="+")
    ap.add_argument("pile")
    ap.add_argument("--threshold", type=float, default=0.6)
    ap.add_argument("--copy")
    ap.add_argument("--max-seconds", type=float, default=20.0)
    a = ap.parse_args()
    from speechbrain.inference.speaker import EncoderClassifier
    from speechbrain.utils.fetching import LocalStrategy
    enc = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb",
                                         savedir=os.path.join(os.environ.get("HF_HOME", "."), "ecapa"),
                                         run_opts={"device": "cuda"}, local_strategy=LocalStrategy.COPY)

    def embed(path):
        audio = load(path, a.max_seconds)
        if len(audio) < 8000:
            return None
        with torch.no_grad():
            e = enc.encode_batch(audio.unsqueeze(0).cuda()).squeeze()
        return torch.nn.functional.normalize(e, dim=0)

    known = [os.path.join(d, f) for d in a.known for f in sorted(os.listdir(d)) if f.lower().endswith(AUDIO)]
    random.Random(3).shuffle(known)
    vecs = [v for v in (embed(p) for p in known[:60]) if v is not None]
    mean = torch.nn.functional.normalize(torch.stack(vecs).mean(0), dim=0)
    pile = sorted(f for f in os.listdir(a.pile) if f.lower().endswith(AUDIO))
    scores = []
    for n, f in enumerate(pile, 1):
        v = embed(os.path.join(a.pile, f))
        if v is not None:
            scores.append((float(v @ mean), f))
        if n % 500 == 0:
            print(f"{n}/{len(pile)}", flush=True)
    scores.sort(reverse=True)
    with open(os.path.join(a.pile, "scores.tsv"), "w", encoding="utf-8") as out:
        out.write("score\tfile\n" + "".join(f"{s:.3f}\t{f}\n" for s, f in scores))
    hist, edges = np.histogram([s for s, _ in scores], bins=np.arange(-0.2, 1.0001, 0.05))
    for h, e in zip(hist, edges):
        print(f"{e:+.2f} {'#' * min(h, 80)} {h}")
    keep = [f for s, f in scores if s >= a.threshold]
    print(f"{len(keep)} of {len(scores)} at or above {a.threshold}")
    if a.copy:
        os.makedirs(a.copy, exist_ok=True)
        for f in keep:
            shutil.copy(os.path.join(a.pile, f), os.path.join(a.copy, f))


if __name__ == "__main__":
    main()
