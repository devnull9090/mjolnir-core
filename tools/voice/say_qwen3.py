"""Speak tools/voice/lines.txt with Qwen3-TTS (Base, zero-shot voice clone).

  D:/hce-voice/envs/qwen3/Scripts/python.exe tools/voice/say_qwen3.py \
      --voice ai --ref <clip.wav> --ref-text "<what the clip says>" --out <dir> \
      [--model Qwen/Qwen3-TTS-12Hz-1.7B-Base]

A fine-tuned checkpoint speaks as its named speaker instead (no reference).
It renders with language "Auto": the finetuning layout has no language token
before the speaker slot, so naming a language would move the speaker embedding
off the position it was trained at.

  ... say_qwen3.py --voice ai --model <out>/checkpoint-epoch-3 --speaker cortana --out <dir>

The model downloads from Hugging Face on first use. Writes <out>/<name>.wav.
"""
import argparse
import os
import time

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

HERE = os.path.dirname(os.path.abspath(__file__))


def lines(voice, path):
    """(name, text, instruct) for each of the voice's rows: voice<TAB>name<TAB>text,
    and optionally <TAB>a delivery instruction (fine-tuned speakers only)."""
    for row in open(path, encoding="utf-8"):
        if row.startswith("#") or not row.strip():
            continue
        cols = row.rstrip("\n").split("\t")
        if cols[0] == voice:
            yield cols[1], cols[2], (cols[3] if len(cols) > 3 and cols[3] else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", required=True)
    ap.add_argument("--ref")
    ap.add_argument("--ref-text")
    ap.add_argument("--speaker", help="a fine-tuned checkpoint's speaker name")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="Qwen/Qwen3-TTS-12Hz-1.7B-Base")
    ap.add_argument("--lines", default=os.path.join(HERE, "lines.txt"), help="voice<TAB>name<TAB>text file")
    ap.add_argument("--only", nargs="*", help="render just these line names")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--takes", type=int, default=1, help="renders per line, made in one batch")
    ap.add_argument("--text", help="speak this one line (named --name) instead of the lines file")
    ap.add_argument("--name", default="line")
    ap.add_argument("--instruct", help="style instruction for a fine-tuned speaker, e.g. 'Shouting, panicked'")
    ap.add_argument("--max-seconds", type=float, default=20.0, help="stop a take that runs on (12.5 frames/s)")
    a = ap.parse_args()
    started = time.perf_counter()
    model = Qwen3TTSModel.from_pretrained(a.model, device_map="cuda:0", dtype=torch.bfloat16, attn_implementation="sdpa")
    prompt = None if a.speaker else model.create_voice_clone_prompt(ref_audio=a.ref, ref_text=a.ref_text)
    os.makedirs(a.out, exist_ok=True)
    cap = int(a.max_seconds * 12.5)
    print(f"model loaded in {time.perf_counter() - started:.1f} s")
    todo = [(a.name, a.text, a.instruct)] if a.text else lines(a.voice, a.lines)
    for name, text, instruct in todo:
        if a.only and name not in a.only:
            continue
        instruct = a.instruct or instruct
        # Every take of a line in one batch: the samples differ, and the GPU
        # works on them together (about 2 s of compute per second of audio
        # one at a time).
        torch.manual_seed(a.seed)
        t0 = time.perf_counter()
        n = a.takes
        # A batch runs until its longest take stops, so a take that runs on
        # is cut near what the words need (about 9 characters a second).
        cap = int(min(a.max_seconds, len(text) / 9 + 3) * 12.5)
        if a.speaker:
            wavs, sr = model.generate_custom_voice(text=[text] * n, language=["Auto"] * n, speaker=[a.speaker] * n,
                                                   instruct=[instruct or ""] * n, max_new_tokens=cap)
        else:
            wavs, sr = model.generate_voice_clone(text=[text] * n, language=["English"] * n,
                                                  voice_clone_prompt=prompt, max_new_tokens=cap)
        for take, wav in enumerate(wavs):
            stem = name if n == 1 else f"{name}_t{take}"
            sf.write(os.path.join(a.out, f"{stem}.wav"), wav, sr)
        print(f"{name}: {n} take(s), {sum(len(w) for w in wavs) / sr:.1f} s of audio in {time.perf_counter() - t0:.1f} s"
              + (f"  [{instruct}]" if instruct else ""))


if __name__ == "__main__":
    main()
