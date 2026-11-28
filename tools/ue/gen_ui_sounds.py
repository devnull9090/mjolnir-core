"""Synthesize MJOLNIR's original Halo-inspired crystalline UI sound cues.

    python tools/ue/gen_ui_sounds.py

Writes 48 kHz 16-bit mono PCM WAV files to unreal/MJOLNIRMaterials/Art/UISounds/.
The UI builder imports them as one-shot ADPCM SoundWaves under
/Game/MJOLNIR/UI/Sounds/SW_MJUI_<Name> and cooks them in chunk 984.
All cues are original procedural synthesis; no game audio is copied.
"""
from __future__ import annotations

import argparse
import math
import random
import struct
import wave
from pathlib import Path

SR = 48000
OUT = Path(__file__).resolve().parents[2] / "unreal/MJOLNIRMaterials/Art/UISounds"


def write_wav(path: Path, samples: list[float]):
    # Apply a short cosine fade-out on the last 6 ms so every clip ends cleanly
    # at zero (no click/pop or UE "DC offset at end" import warning).
    fade = min(len(samples), int(SR * 0.006))
    if fade > 1:
        samples = list(samples)
        for i in range(fade):
            w = 0.5 * (1.0 + math.cos(math.pi * (i + 1) / fade))
            samples[len(samples) - fade + i] *= w
    peak = max((abs(s) for s in samples), default=1.0)
    scale = 0.88 / peak if peak > 0.88 else 1.0
    pcm = bytearray()
    for s in samples:
        v = max(-1.0, min(1.0, s * scale))
        pcm += struct.pack("<h", int(round(v * 32767)))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(bytes(pcm))


def env_ad(t: float, attack: float, decay: float) -> float:
    if t < 0.0:
        return 0.0
    if attack > 0.0 and t < attack:
        return 0.5 - 0.5 * math.cos(math.pi * t / attack)
    return math.exp(-(t - attack) / max(1e-5, decay))


def synth_hover() -> list[float]:
    """Crisp ~38ms translucent glass tick — light enough for rapid list scrolling."""
    n = int(SR * 0.042)
    rng = random.Random(101)
    out = []
    lp = 0.0
    for i in range(n):
        t = i / SR
        # Delicate two-partial crystalline glass ping
        tone = (
            0.55 * math.sin(2 * math.pi * 1760.0 * t) * env_ad(t, 0.0012, 0.009)
            + 0.25 * math.sin(2 * math.pi * 3520.0 * t + 0.4) * env_ad(t, 0.0008, 0.005)
            + 0.12 * math.sin(2 * math.pi * 880.0 * t) * env_ad(t, 0.001, 0.008)
        )
        # Micro transient tap (band-softened)
        raw = rng.uniform(-1.0, 1.0)
        lp = lp * 0.72 + raw * 0.28
        click = lp * 0.14 * env_ad(t, 0.0004, 0.0022)
        out.append((tone + click) * 0.52)
    return out


def synth_select() -> list[float]:
    """Resonant ~145ms Halo crystalline fifth-interval confirm chime (D5 -> A5)."""
    n = int(SR * 0.155)
    out = []
    for i in range(n):
        t = i / SR
        a = (
            0.48 * math.sin(2 * math.pi * 587.33 * t)
            + 0.20 * math.sin(2 * math.pi * 1174.66 * t)
            + 0.08 * math.sin(2 * math.pi * 2349.32 * t)
        ) * env_ad(t, 0.002, 0.036)
        t2 = t - 0.022
        b = 0.0
        if t2 >= 0.0:
            b = (
                0.52 * math.sin(2 * math.pi * 880.0 * t2)
                + 0.22 * math.sin(2 * math.pi * 1760.0 * t2)
                + 0.07 * math.sin(2 * math.pi * 2637.02 * t2)
            ) * env_ad(t2, 0.0025, 0.044)
        out.append((a + b) * 0.65)
    return out


def synth_primary() -> list[float]:
    """Warm resonant ~260ms Spartan-gold ignition chord for START GAME / JOIN."""
    n = int(SR * 0.275)
    out = []
    # D-major9 / fifth open Spartan chord (D3, A3, D4, A4, F#5 subtle shimmer)
    partials = [
        (146.83, 0.34, 0.008, 0.085, 0.000),
        (293.66, 0.36, 0.005, 0.078, 0.000),
        (440.00, 0.26, 0.004, 0.072, 0.014),
        (587.33, 0.28, 0.004, 0.070, 0.022),
        (880.00, 0.18, 0.005, 0.062, 0.034),
        (1174.66, 0.10, 0.005, 0.052, 0.042),
    ]
    for i in range(n):
        t = i / SR
        s = 0.0
        for freq, amp, atk, dec, delay in partials:
            td = t - delay
            if td >= 0.0:
                s += amp * math.sin(2 * math.pi * freq * td) * env_ad(td, atk, dec)
        out.append(s * 0.72)
    return out


def synth_back() -> list[float]:
    """Gentle ~110ms descending hollow tone for BACK / Escape."""
    n = int(SR * 0.115)
    out = []
    phase1, phase2 = 0.0, 0.0
    for i in range(n):
        t = i / SR
        # Smooth downward glide from 640 Hz to 390 Hz
        f1 = 390.0 + 250.0 * math.exp(-t / 0.038)
        f2 = f1 * 1.5
        phase1 += 2 * math.pi * f1 / SR
        phase2 += 2 * math.pi * f2 / SR
        s = (0.62 * math.sin(phase1) + 0.18 * math.sin(phase2)) * env_ad(t, 0.0025, 0.034)
        out.append(s * 0.60)
    return out


def synth_tab() -> list[float]:
    """Crisp ~48ms glass-metallic detent for tab switches, filters, and variants."""
    n = int(SR * 0.052)
    out = []
    for i in range(n):
        t = i / SR
        s = (
            0.55 * math.sin(2 * math.pi * 1318.51 * t) * env_ad(t, 0.001, 0.012)
            + 0.30 * math.sin(2 * math.pi * 1975.53 * t) * env_ad(t, 0.001, 0.009)
            + 0.14 * math.sin(2 * math.pi * 659.25 * t) * env_ad(t, 0.0015, 0.014)
        )
        out.append(s * 0.56)
    return out


def synth_vote() -> list[float]:
    """Clean affirmative ~165ms double-harmonic chime on casting a map vote."""
    n = int(SR * 0.175)
    out = []
    for i in range(n):
        t = i / SR
        a = (
            0.46 * math.sin(2 * math.pi * 659.25 * t)
            + 0.18 * math.sin(2 * math.pi * 1318.51 * t)
        ) * env_ad(t, 0.002, 0.032)
        t2 = t - 0.030
        b = 0.0
        if t2 >= 0.0:
            b = (
                0.50 * math.sin(2 * math.pi * 987.77 * t2)
                + 0.22 * math.sin(2 * math.pi * 1975.53 * t2)
            ) * env_ad(t2, 0.002, 0.048)
        out.append((a + b) * 0.64)
    return out


def synth_tick() -> list[float]:
    """Quiet subtle ~42ms countdown pip for the final 5 seconds of map vote."""
    n = int(SR * 0.045)
    out = []
    for i in range(n):
        t = i / SR
        s = (
            0.65 * math.sin(2 * math.pi * 1046.50 * t)
            + 0.18 * math.sin(2 * math.pi * 2093.00 * t)
        ) * env_ad(t, 0.0015, 0.011)
        out.append(s * 0.42)
    return out


def synth_open() -> list[float]:
    """Airy ~155ms glass-panel entrance breath when pushing a menu screen."""
    n = int(SR * 0.165)
    rng = random.Random(404)
    out = []
    lp1, lp2 = 0.0, 0.0
    phase = 0.0
    for i in range(n):
        t = i / SR
        # Rising soft glass shimmer (440 -> 660 Hz)
        freq = 440.0 + 220.0 * (1.0 - math.exp(-t / 0.055))
        phase += 2 * math.pi * freq / SR
        shimmer = (
            0.35 * math.sin(phase) + 0.14 * math.sin(phase * 2.0)
        ) * env_ad(t, 0.018, 0.046)
        # Soft airy band-shaped breath
        raw = rng.uniform(-1.0, 1.0)
        lp1 = lp1 * 0.86 + raw * 0.14
        lp2 = lp2 * 0.94 + lp1 * 0.06
        air = (lp1 - lp2) * 0.42 * env_ad(t, 0.014, 0.036)
        out.append((shimmer + air) * 0.55)
    return out


SOUNDS = {
    "SW_MJUI_Hover": synth_hover,
    "SW_MJUI_Select": synth_select,
    "SW_MJUI_Primary": synth_primary,
    "SW_MJUI_Back": synth_back,
    "SW_MJUI_Tab": synth_tab,
    "SW_MJUI_Vote": synth_vote,
    "SW_MJUI_Tick": synth_tick,
    "SW_MJUI_Open": synth_open,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name, fn in SOUNDS.items():
        samples = fn()
        dest = args.out / f"{name}.wav"
        write_wav(dest, samples)
        ms = round(len(samples) * 1000 / SR)
        print(f"wrote {dest.relative_to(OUT.parents[3])} ({ms} ms)")


if __name__ == "__main__":
    main()
