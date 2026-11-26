"""Rank several takes of each line, keep the best, and write the game's waves.

  python pick_takes.py <takes dir> --lines <lines file> --voice ai \
      --real <real clip dir> [--exclude <ref clip>] [--keep 3] [--out <picks dir>] \
      [--final <wave dir> --prefix cortana]

<takes dir> holds <name>_t<N>.wav (say_qwen3.py --takes) and the
transcripts.tsv that transcribe.py writes there. A take passes when

  - its transcript has the line's words (case, punctuation, number words and
    UK spellings aside), and
  - its speech (silence trimmed) runs no longer than 1.5 x the median of the
    line's word-perfect takes: a take can say every word and then run on.

Passing takes rank by speaker similarity to the real voice (similarity.py's
measure), except lines whose delivery instruction asks for shouting, which
rank by loudness: similarity to calm clips favours the least-shouted take.
--out copies the best --keep per line as <name>_<rank>.wav for listening.
--final writes each line's best take as <prefix>_<name>.wav, trimmed (60 ms of
silence kept either side) and levelled (speech at -18 dBFS RMS, shouts at
-14, peaks under -1 dBFS), and manifest.tsv beside them: wave, seconds, text.
ranking.tsv in <takes dir> lists every take.
"""
import argparse
import os
import random
import re
import shutil

import numpy as np
import soundfile as sf
import torch
import torchaudio.functional as F

NUMBERS = {"ten": "10", "five": "5", "three": "3", "two": "2", "one": "1", "thirty": "30", "twenty": "20",
           "fuelling": "fueling", "fuelled": "fueled"}  # number words and UK spellings as Whisper writes them


def words(text):
    """The words, as heard: no case, punctuation or apostrophes ("chute's" and
    "chutes" sound the same), number words as digits."""
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower().replace("'", "").replace("’", ""))
    return [NUMBERS.get(w, w) for w in text.split()]


def load(path, rate=16000):
    data, sr = sf.read(path, dtype="float32", always_2d=True)
    mono = torch.from_numpy(np.ascontiguousarray(data.mean(axis=1)))
    return (F.resample(mono, sr, rate) if sr != rate else mono), sr


def speech_span(audio, rate, floor_db=-45.0):
    """First and last sample of speech: 10 ms frames within floor_db of the peak frame."""
    hop = max(1, rate // 100)
    frames = audio[: len(audio) // hop * hop].reshape(-1, hop)
    energy = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    loud = np.nonzero(energy > energy.max() + floor_db)[0]
    if len(loud) == 0:
        return 0, len(audio)
    return loud[0] * hop, min(len(audio), (loud[-1] + 1) * hop)


def loudness(audio, rate):
    """RMS (dBFS) of the loudest 10% of voiced 10 ms frames."""
    hop = max(1, rate // 100)
    frames = audio[: len(audio) // hop * hop].reshape(-1, hop)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    voiced = rms[rms > rms.max() * 0.1]
    return 20 * np.log10(np.percentile(voiced, 90) + 1e-9) if len(voiced) else -99.0


def finish(path, shout):
    """The take trimmed and levelled for the game, at its own rate."""
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    audio = data.mean(axis=1)
    start, end = speech_span(audio, rate)
    pad = int(0.06 * rate)
    audio = audio[max(0, start - pad): min(len(audio), end + pad)]
    hop = max(1, rate // 100)
    frames = audio[: len(audio) // hop * hop].reshape(-1, hop)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    voiced = rms[rms > rms.max() * 0.1]
    level = 20 * np.log10(np.sqrt((voiced ** 2).mean()) + 1e-9)
    audio = audio * 10 ** (((-14.0 if shout else -18.0) - level) / 20)
    peak = np.abs(audio).max()
    if peak > 10 ** (-1 / 20):
        audio = audio * (10 ** (-1 / 20) / peak)
    # 5 ms fades so a trim never clicks.
    fade = min(len(audio) // 2, int(0.005 * rate))
    if fade:
        ramp = np.linspace(0, 1, fade, dtype=np.float32)
        audio[:fade] *= ramp
        audio[-fade:] *= ramp[::-1]
    return audio.astype(np.float32), rate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("takes")
    ap.add_argument("--lines", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--real", required=True)
    ap.add_argument("--exclude", default="")
    ap.add_argument("--keep", type=int, default=3)
    ap.add_argument("--out")
    ap.add_argument("--final")
    ap.add_argument("--prefix")
    a = ap.parse_args()
    if a.final and not a.prefix:
        ap.error("--final needs --prefix")
    expected, shouted = {}, set()
    for row in open(a.lines, encoding="utf-8"):
        if row.startswith("#") or not row.strip():
            continue
        cols = row.rstrip("\n").split("\t")
        if cols[0] == a.voice:
            expected[cols[1]] = cols[2]
            if len(cols) > 3 and "shout" in cols[3].lower():
                shouted.add(cols[1])
    heard = {}
    for row in open(os.path.join(a.takes, "transcripts.tsv"), encoding="utf-8").read().splitlines()[1:]:
        f, seconds, text = row.split("\t")[:3]
        heard[f] = (float(seconds), text)

    from speechbrain.inference.speaker import EncoderClassifier
    from speechbrain.utils.fetching import LocalStrategy
    enc = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb",
                                         savedir=os.path.join(os.environ.get("HF_HOME", "."), "ecapa"),
                                         run_opts={"device": "cuda"}, local_strategy=LocalStrategy.COPY)

    def embed(audio):
        with torch.no_grad():
            e = enc.encode_batch(audio.unsqueeze(0).cuda()).squeeze()
        return torch.nn.functional.normalize(e, dim=0)

    real = sorted(f for f in os.listdir(a.real) if f.lower().endswith((".wav", ".ogg", ".flac"))
                  and not (a.exclude and a.exclude in f))
    random.Random(7).shuffle(real)
    mean = torch.nn.functional.normalize(torch.stack([embed(load(os.path.join(a.real, f))[0]) for f in real[:30]]).mean(0), dim=0)

    takes = {}
    for f in sorted(heard):
        m = re.match(r"(.+)_t(\d+)\.wav$", f)
        if not m or m.group(1) not in expected:
            continue
        audio16, _ = load(os.path.join(a.takes, f))
        span = speech_span(audio16.numpy(), 16000)
        takes.setdefault(m.group(1), []).append({
            "file": f, "take": int(m.group(2)), "heard": heard[f][1],
            "ok": words(heard[f][1]) == words(expected[m.group(1)]),
            "speech": (span[1] - span[0]) / 16000, "sim": float(embed(audio16) @ mean),
            "loud": loudness(audio16.numpy(), 16000)})
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    if a.final:
        os.makedirs(a.final, exist_ok=True)
    rows, manifest = [], []
    for name in sorted(takes):
        group = takes[name]
        perfect = [t["speech"] for t in group if t["ok"]]
        limit = 1.5 * float(np.median(perfect)) if perfect else float("inf")
        for t in group:
            t["pass"] = t["ok"] and t["speech"] <= limit
        key = (lambda t: (not t["pass"], -t["loud"])) if name in shouted else (lambda t: (not t["pass"], -t["sim"]))
        ranked = sorted(group, key=key)
        rows += [(name, t) for t in ranked]
        best = ranked[0]
        print(f"{name}: {sum(t['pass'] for t in group)}/{len(group)} pass, best t{best['take']} "
              f"sim {best['sim']:.3f} loud {best['loud']:.1f} dB {best['speech']:.1f} s"
              + ("" if best["pass"] else "  (NONE PASS)"))
        if a.out:
            for rank, t in enumerate(ranked[: a.keep], 1):
                shutil.copy(os.path.join(a.takes, t["file"]), os.path.join(a.out, f"{name}_{rank}.wav"))
        if a.final and best["pass"]:
            audio, rate = finish(os.path.join(a.takes, best["file"]), name in shouted)
            wave = f"{a.prefix}_{name}"
            sf.write(os.path.join(a.final, wave + ".wav"), audio, rate)
            manifest.append(f"{wave}\t{len(audio) / rate:.2f}\t{expected[name]}")
    with open(os.path.join(a.takes, "ranking.tsv"), "w", encoding="utf-8") as out:
        out.write("name\ttake\tpasses\twords_ok\tsimilarity\tloudness_db\tspeech_s\theard\n")
        for name, t in rows:
            out.write(f"{name}\t{t['take']}\t{int(t['pass'])}\t{int(t['ok'])}\t{t['sim']:.3f}\t{t['loud']:.1f}\t{t['speech']:.2f}\t{t['heard']}\n")
    if a.final:
        path = os.path.join(a.final, "manifest.tsv")
        old = [r for r in open(path, encoding="utf-8").read().splitlines()[1:]] if os.path.exists(path) else []
        mine = {m.split("\t")[0] for m in manifest}
        keep = [r for r in old if r.split("\t")[0] not in mine]
        with open(path, "w", encoding="utf-8") as out:
            out.write("wave\tseconds\ttext\n" + "".join(r + "\n" for r in sorted(keep + manifest)))


if __name__ == "__main__":
    main()
