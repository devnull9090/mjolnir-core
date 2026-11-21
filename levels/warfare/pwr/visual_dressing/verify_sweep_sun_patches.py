"""Measure the bounded sunlight patches in the cooked PWR level by exact actor ownership."""

import hashlib
import json
import math
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/iostore"))
from zen_class import load_name_batch

PREFIX = "PWR_SweepSunPatch"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fallback(text, default=None):
    if text is None:
        if default is None:
            raise ValueError("Required cooked light property was not serialized")
        return default
    return float(text.split()[0])


def vec(text):
    return [float(x.split()[0]) for x in text.split(",")]


def srgb(c):
    return round(
        255 * (c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055)
    )


def table(data):
    names, _ = load_name_batch(data, 52)
    start, end = struct.unpack_from("<II", data, 32)
    rows = []
    for offset in range(start, end, 72):
        base, n, outer = struct.unpack_from("<IIQ", data, offset + 16)
        name = names[base & 0x3FFFFFFF] + ("_" + str(n - 1) if n else "")
        rows.append((name, outer))
    return rows


def verify(art, world_path, scratch):
    art, world_path, scratch = Path(art), Path(world_path), Path(scratch)
    folder = art / "light"
    path = folder / "bend-sun-patches.json"
    spec = json.loads(path.read_text())
    ed = json.loads((folder / "editor-sun-patches-reopened.json").read_text())
    if (
        ed["spec_sha256"] != digest(path)
        or digest(folder / "spot-pilot.json") != spec["pilot_spec_sha256"]
    ):
        raise ValueError("Different pilot or editor sun patch source")
    pilot = json.loads((folder / "spot-pilot.json").read_text())
    gain = pilot["variants"][spec["selected_pilot"]]
    witness_path = ROOT / spec["pilot_witness_path"]
    if digest(witness_path) != spec["pilot_witness_sha256"]:
        raise ValueError("Native pilot evidence changed")
    witness = json.loads(witness_path.read_text())["states"][spec["selected_pilot"]]
    actual_captures = {key: v["sha256"] for key, v in witness["captures"].items()}
    if actual_captures != spec["pilot_capture_sha256"] or witness["gain"] != gain:
        raise ValueError("Selected native frames or gain differ")
    tested = {row["name"]: row for row in pilot["spots"]}
    expected = {r["name"]: r for r in spec["spots"]}
    if set(expected) != set(tested):
        raise ValueError("Selected pilot actor inventory differs")
    for name, row in expected.items():
        for key, value in tested[name].items():
            if row[key] != (value * gain if key == "intensity" else value):
                raise ValueError(f"{name} {key} differs from tested state")
    origin = {r["name"]: r for r in ed["spots"]}
    raw = world_path.read_bytes()
    rows = table(raw)
    owners = {
        name: i for i, (name, outer) in enumerate(rows) if name.startswith(PREFIX)
    }
    if set(owners) != set(expected) or set(origin) != set(expected):
        raise ValueError(
            f"Cooked sunlight roster {list(owners)} differs from matched pilot"
        )
    proofs = []
    for name, idx in owners.items():
        row = expected[name]
        m = []
        for child, (n, parent) in enumerate(rows):
            if parent != idx:
                continue
            cmd = [
                ROOT / "target/release/examples/props_dump.exe",
                ROOT / "out/pwr/world-art/foliage-r2/cooked-proof/world-paks",
                ROOT / "defs/ue/Meteorite-2607-CU3.usmap",
                world_path,
                str(child),
            ]
            text = subprocess.run(
                cmd, capture_output=True, check=True, text=True
            ).stdout
            if " SpotLightComponent " not in text.splitlines()[0]:
                continue
            p = dict(
                v.strip().split(" = ", 1) for v in text.splitlines()[1:] if " = " in v
            )
            for prop, k in [
                ("Intensity", "intensity"),
                ("InnerConeAngle", "inner_degrees"),
                ("OuterConeAngle", "outer_degrees"),
                ("AttenuationRadius", "radius_cm"),
                ("LightFalloffExponent", "falloff_exponent"),
                ("SpecularScale", "specular_scale"),
                ("SourceRadius", "source_radius_cm"),
            ]:
                if abs(fallback(p.get(prop)) - row[k]) > 0.05:
                    raise ValueError(f"{name} {prop} differs: {p.get(prop)}")
            col = list(reversed([srgb(c) for c in row["color_linear"]]))
            actual = [int(c) for c in p["LightColor"].split(",")[:3]]
            if max(abs(a - b) for a, b in zip(col, actual)) > 1:
                raise ValueError("Cooked sunlight tint changed: " + name)
            if (
                math.dist(vec(p["RelativeLocation"]), row["location_cm"]) > 0.15
                or math.dist(vec(p["RelativeRotation"]), row["rotation_deg"]) > 0.11
            ):
                raise ValueError(
                    f"{name} native pose differs: {p.get('RelativeRotation')}"
                )
            if (
                p.get("bUseInverseSquaredFalloff") != "false"
                or p.get("CastShadows") != "false"
                or p.get("LightingChannels.bChannel0", "true") != "true"
                or p.get("LightingChannels.bChannel1") != "true"
                or p.get("LightingChannels.bChannel2", "false") != "false"
                or fallback(p.get("IntensityUnits"), 0) != row["intensity_units"]
                or p.get("bAffectTranslucentLighting", "true") != "true"
                or fallback(p.get("VolumetricScatteringIntensity"), 1.0) != 1
                or fallback(p.get("Mobility")) != 2
            ):
                raise ValueError(f"{name} native lighting channels or volume changed")
            m.append({"actor": name, "component": n, "export": child, "properties": p})
        if len(m) != 1:
            raise ValueError(f"Expected exactly one native spot component for {name}")
        proofs.extend(m)
    result = {
        "spec_sha256": digest(path),
        "world_sha256": hashlib.sha256(raw).hexdigest(),
        "selected_pilot": spec["selected_pilot"],
        "actor_count": len(proofs),
        "spots": proofs,
    }
    (folder / "cooked-sun-patches.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
