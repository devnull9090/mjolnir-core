"""Transcribe a folder of voice clips with faster-whisper (large-v3, GPU).

  python transcribe.py <clip dir> [--model large-v3] [--out transcripts.tsv]

Writes <clip dir>/transcripts.tsv: file, seconds, text, avg_logprob,
no_speech_prob. An initial prompt carries Halo words so names come out
spelled the way the games spell them. Run it in a voice environment
(D:/hce-voice/envs/...), not the system Python.
"""
import argparse
import os
import sys

PROMPT = ("Halo. Cortana, Master Chief, the Covenant, the Flood, Spartan, Pelican, Warthog, Banshee, "
          "Elite, Grunt, Jackal, Hunter, Guilty Spark, Keyes, the Pillar of Autumn, the Index.")
AUDIO = (".wav", ".ogg", ".flac", ".mp3")


def load16k(path):
    """Mono float32 at 16 kHz, decoded with libsndfile (Ogg Vorbis and WAV);
    faster-whisper's own PyAV path breaks on current PyAV releases."""
    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio.functional as F
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    mono = torch.from_numpy(np.ascontiguousarray(data.mean(axis=1)))
    return F.resample(mono, rate, 16000).numpy() if rate != 16000 else mono.numpy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--out", default="transcripts.tsv")
    a = ap.parse_args()
    # ctranslate2 needs CUDA 12's cuBLAS (pip nvidia-cublas-cu12) and cuDNN
    # (its own wheel); put their folders on the DLL search path first.
    import torch
    if hasattr(os, "add_dll_directory"):
        site = os.path.dirname(os.path.dirname(torch.__file__))
        for d in (os.path.join(os.path.dirname(torch.__file__), "lib"), os.path.join(site, "nvidia", "cublas", "bin")):
            if os.path.isdir(d):
                os.add_dll_directory(d)
    from faster_whisper import WhisperModel
    model = WhisperModel(a.model, device="cuda", compute_type="float16")
    files = sorted(f for f in os.listdir(a.folder) if f.lower().endswith(AUDIO))
    rows = []
    for n, name in enumerate(files, 1):
        audio = load16k(os.path.join(a.folder, name))
        segments, info = model.transcribe(audio, language="en", beam_size=5,
                                          initial_prompt=PROMPT, condition_on_previous_text=False)
        segments = list(segments)
        text = " ".join(s.text.strip() for s in segments).strip()
        logprob = min((s.avg_logprob for s in segments), default=-9.0)
        no_speech = max((s.no_speech_prob for s in segments), default=1.0)
        rows.append(f"{name}\t{info.duration:.2f}\t{text}\t{logprob:.3f}\t{no_speech:.3f}")
        if n % 25 == 0:
            print(f"{n}/{len(files)}", file=sys.stderr)
    out = os.path.join(a.folder, a.out)
    with open(out, "w", encoding="utf-8") as f:
        f.write("file\tseconds\ttext\tavg_logprob\tno_speech_prob\n" + "\n".join(rows) + "\n")
    print(f"{len(rows)} transcribed -> {out}")


if __name__ == "__main__":
    main()
