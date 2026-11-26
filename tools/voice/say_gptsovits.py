"""Speak tools/voice/lines.txt with GPT-SoVITS, zero-shot from one reference clip
(or with fine-tuned weights).

Run from the GPT-SoVITS checkout with its environment:

  cd D:/hce-voice/models/GPT-SoVITS
  D:/hce-voice/envs/gptsovits/Scripts/python.exe <repo>/tools/voice/say_gptsovits.py \
      --voice ai --ref <clip.wav> --ref-text "<what the clip says>" --out <dir> \
      [--version v2ProPlus] [--gpt <s1 ckpt>] [--sovits <s2 pth>]

Writes <out>/<name>.wav for each line of that voice.
"""
import argparse
import os
import sys

import soundfile as sf
import torch
import torchaudio


def _load(path, *args, **kwargs):
    """torchaudio.load without TorchCodec (no Windows CUDA wheel): channels-first
    float32 and the rate, as torchaudio returns them."""
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    return torch.from_numpy(data.T.copy()), rate


torchaudio.load = _load
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "GPT_SoVITS"))
from TTS_infer_pack.TTS import TTS, TTS_Config  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def lines(voice):
    for row in open(os.path.join(HERE, "lines.txt"), encoding="utf-8"):
        if row.startswith("#") or not row.strip():
            continue
        v, name, text = row.rstrip("\n").split("\t")
        if v == voice:
            yield name, text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--ref-text", required=True)
    ap.add_argument("--aux", nargs="*", default=[], help="more reference clips, for timbre")
    ap.add_argument("--out", required=True)
    ap.add_argument("--version", default="v2ProPlus")
    ap.add_argument("--gpt")
    ap.add_argument("--sovits")
    a = ap.parse_args()
    # The version's default paths, on the GPU; a dict so nothing is written
    # back to the checkout's tts_infer.yaml.
    custom = dict(TTS_Config.default_configs[a.version], device="cuda", is_half=True)
    if a.gpt:
        custom["t2s_weights_path"] = a.gpt
    if a.sovits:
        custom["vits_weights_path"] = a.sovits
    tts = TTS({"custom": custom})
    os.makedirs(a.out, exist_ok=True)
    for name, text in lines(a.voice):
        result = tts.run({
            "text": text, "text_lang": "en", "ref_audio_path": a.ref, "aux_ref_audio_paths": a.aux,
            "prompt_text": a.ref_text, "prompt_lang": "en", "top_k": 15, "top_p": 1.0, "temperature": 1.0,
            "text_split_method": "cut5", "batch_size": 1, "speed_factor": 1.0, "seed": 1234,
            "return_fragment": False, "parallel_infer": False, "repetition_penalty": 1.35,
        })
        sr, audio = next(iter(result))
        sf.write(os.path.join(a.out, f"{name}.wav"), audio, sr)
        print(f"{name}: {len(audio) / sr:.1f} s")


if __name__ == "__main__":
    main()
