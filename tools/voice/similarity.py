"""Speaker similarity of generated lines to a real voice (SpeechBrain ECAPA).

  python similarity.py --real <clip dir> [--exclude <ref clip name>] <generated dir> [...]

The real voice is the mean embedding of up to 30 real clips (skipping the
reference clip the model was given, so a model is not rewarded for copying
it); each generated file scores the cosine to that mean. As a yardstick it
also scores 10 held-out real clips the same way. Higher is closer; it is a
filter, not a substitute for listening.
"""
import argparse
import os
import random

import numpy as np
import soundfile as sf
import torch
import torchaudio.functional as F

AUDIO = (".wav", ".ogg", ".flac")


def load(path):
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    mono = torch.from_numpy(np.ascontiguousarray(data.mean(axis=1)))
    return F.resample(mono, rate, 16000) if rate != 16000 else mono


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", required=True)
    ap.add_argument("--exclude", default="")
    ap.add_argument("generated", nargs="+")
    a = ap.parse_args()
    from speechbrain.inference.speaker import EncoderClassifier
    from speechbrain.utils.fetching import LocalStrategy
    enc = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb",
                                         savedir=os.path.join(os.environ.get("HF_HOME", "."), "ecapa"),
                                         run_opts={"device": "cuda"},
                                         local_strategy=LocalStrategy.COPY)  # no symlinks without admin on Windows

    def embed(path):
        with torch.no_grad():
            e = enc.encode_batch(load(path).unsqueeze(0).cuda()).squeeze()
        return torch.nn.functional.normalize(e, dim=0)

    real = sorted(f for f in os.listdir(a.real) if f.lower().endswith(AUDIO) and not (a.exclude and a.exclude in f))
    random.Random(7).shuffle(real)
    pool, held = real[:30], real[30:40]
    mean = torch.nn.functional.normalize(torch.stack([embed(os.path.join(a.real, f)) for f in pool]).mean(0), dim=0)
    yard = [float(embed(os.path.join(a.real, f)) @ mean) for f in held]
    print(f"real held-out clips: mean {np.mean(yard):.3f} (min {min(yard):.3f})")
    for d in a.generated:
        scores = {f: float(embed(os.path.join(d, f)) @ mean) for f in sorted(os.listdir(d)) if f.lower().endswith(AUDIO)}
        print(f"{d}: mean {np.mean(list(scores.values())):.3f}  " + "  ".join(f"{k[:-4]} {v:.2f}" for k, v in scores.items()))


if __name__ == "__main__":
    main()
