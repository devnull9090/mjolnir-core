"""Refresh PWR v5 compiled-seam probes after foliage/rock collision compilation.

Builds and checks a staged scenario first. Only --apply replaces the isolated
converted scenario; never bakes, installs, launches, or calls the game/editor.
Use a new --out directory for every collision revision to retain prior evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_WORLD = Path("C:/haloce/ce_conversions/warfare/PWR/expansion/world-v5")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def verify_terrain_tail(receipt, architecture_contract=None):
    if architecture_contract is not None:
        # An explicit reviewed replacement contract is required; the default
        # foliage/terrain refresh still rejects every changed architecture tail.
        from bases_v1.runtime_collision import verify_contract
        return verify_contract(architecture_contract, receipt)
    require(receipt.get("triangles") == 135836
            and receipt.get("trailing_architecture_surfaces") == 8336
            and receipt.get("total_extra_surfaces") == 144172,
            "This v5 refresh requires unchanged 135836 terrain + 3776 architecture + 4560 details")
    require(sha(receipt["file"]) == receipt["sha256"], "Terrain extra differs from its export receipt")


def replace_verified(target, staged, original_sha, gate, inputs):
    """Atomic publish after the full gate; never clobber a concurrent edit."""
    require(gate.get("layout3_permitted") is True and gate.get("terrain_contract_compatible") is True
            and gate.get("protocol") == 20569 and gate.get("layout_revision") == 3,
            "Full native contract did not authorize this staged scenario")
    require(all(sha(name) == digest for name, digest in inputs.items()), "A collision/probe input changed during verification")
    require(sha(target) == original_sha, "Converted scenario changed during verification; refusing to replace it")
    target, staged = Path(target), Path(staged)
    temporary = target.with_name(target.name + ".native-refresh.tmp")
    require(not temporary.exists(), "A prior native-refresh temporary file exists; inspect it before retrying")
    # Both paths are beside the isolated converted scenario, on the same volume.
    with temporary.open("xb") as stream:
        stream.write(staged.read_bytes())
    try:
        require(sha(target) == original_sha, "Converted scenario changed before atomic replacement")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def envelope(receipt, layout):
    pieces = receipt["pieces"]
    result = {"corridor_half_width_m": 25,
              "note": "Conservative piece-AABB audit margin, not a measured Pelican wingspan.",
              "maximum_static_m": max(p["bounds_wu"]["max"][2] * 3.048 for p in pieces), "routes": {}}
    for team, route in layout["flights_m"].items():
        lo = [min(route["start"][i], route["end"][i]) - 25 for i in range(2)]
        hi = [max(route["start"][i], route["end"][i]) + 25 for i in range(2)]
        selected = [p for p in pieces if all(p["bounds_wu"]["max"][i] * 3.048 >= lo[i]
                    and p["bounds_wu"]["min"][i] * 3.048 <= hi[i] for i in range(2))]
        maximum = max((p["bounds_wu"]["max"][2] * 3.048 for p in selected), default=None)
        altitude = min(route["start"][2], route["end"][2])
        result["routes"][team] = {"pieces": len(selected), "flight_altitude_m": altitude,
                                  "maximum_static_m": maximum,
                                  "clearance_m": None if maximum is None else altitude - maximum}
    return result


def refresh(world, runtime, layout, proof, out, apply=False, vehicle_spawn_policy=None, architecture_contract=None,
            additional_probe_plan=None):
    world, runtime, layout, proof, out = (Path(p).resolve() for p in (world, runtime, layout, proof, out))
    # This runner is deliberately scoped to isolated authored-map build output.
    require(world.is_relative_to(DEFAULT_WORLD.parent.resolve()), "World must be under the isolated PWR expansion directory")
    require(out.is_relative_to((REPO / "out/pwr").resolve()), "Evidence output must stay under this worktree's out/pwr")
    require(not out.exists(), "--out must be a new directory; prior acceptance evidence is never overwritten")
    level = world / "converted/pwr.level.json"
    receipt = world / "upgrade/PWR/native-collision-receipt.json"
    ordered = world / "source-build/terrain-collision-extra.ordered.npz"
    terrain_receipt = world / "source-build/terrain-collision-extra.receipt.json"
    compiled = read(receipt)
    tail = read(terrain_receipt)
    replacement = verify_terrain_tail(tail, architecture_contract)
    if replacement is not None:
        require(compiled['source_surfaces'] == replacement['counts']['expected_global'],
                'Compiled collision count differs from the explicit base replacement contract')
    named_inputs = [runtime, layout, proof, receipt, ordered, terrain_receipt, Path(tail["file"]),
                    Path(compiled["output"]), Path(compiled["source_manifest"]),
                    Path(compiled["source_manifest"]).with_suffix(".bin")]
    if vehicle_spawn_policy is not None:
        vehicle_spawn_policy = Path(vehicle_spawn_policy).resolve()
        from vehicle_spawn_policy import load_policy
        load_policy(vehicle_spawn_policy)
        named_inputs.append(vehicle_spawn_policy)
    if replacement is not None:
        named_inputs.append(Path(architecture_contract).resolve())
        named_inputs.extend(Path(replacement[key]['path']) for key in
            ('source','source_blend','placement_plan','handoff','baseline_extra','output_extra','ordered','audit'))
    extra_probe_inputs = {}
    if additional_probe_plan is not None:
        require(replacement is not None, 'Additional base probes require an explicit architecture contract')
        additional_probe_plan = Path(additional_probe_plan).resolve()
        from bases_v1.prepare_base_probe import verify_plan
        extra_probe_inputs = verify_plan(additional_probe_plan)
        additional = read(additional_probe_plan)
        provenance = additional['provenance']
        require(provenance['receipt_sha256'] == sha(receipt)
                and provenance['compiled_tag_sha256'] == compiled['output_sha256'],
                'Additional base probes belong to another compiled world')
        require(read(provenance['architecture_proof_path'])['contract_sha256'] == sha(architecture_contract),
                'Additional base probes belong to another architecture contract')
        named_inputs.append(additional_probe_plan)
    inputs = {str(p): sha(p) for p in named_inputs}
    require(all(sha(name) == digest for name, digest in extra_probe_inputs.items()),
            'An additional base probe input changed after validation')
    inputs.update(extra_probe_inputs)
    original_sha = sha(level)
    out.mkdir(parents=True)
    original = out / "pwr.level.before-probes.json"
    staged = out / "pwr.level.verified.json"
    shutil.copyfile(level, original)
    shutil.copyfile(level, staged)
    plan = out / "terrain-probe-plan.json"
    contract = out / "native-contract.json"
    commands = []

    def run(arguments):
        command = [sys.executable, *map(str, arguments)]
        commands.append(command)
        result = subprocess.run(command, cwd=REPO, text=True, capture_output=True)
        with (out / "commands.log").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(command) + "\n" + result.stdout + result.stderr + "\n")
        require(result.returncode == 0, "Preflight command failed; see " + str(out / "commands.log"))

    architecture_proof = None
    if replacement is not None:
        architecture_proof = out / "compiled-base-collision-proof.json"
        run([HERE / "bases_v1/runtime_collision.py", "compiled", architecture_contract,
             receipt, "--out", architecture_proof])

    probe_tool = REPO / "native/lobby/prepare_terrain_probe.py"
    run([probe_tool, "build", "--master", runtime, "--layout", layout, "--receipt", receipt,
         "--ordered", ordered, "--terrain-receipt", terrain_receipt, "--collision-proof", proof, "--out", plan])
    run([probe_tool, "patch", plan, staged])
    first_patch_sha = sha(staged)
    run([probe_tool, "patch", plan, staged])
    require(sha(staged) == first_patch_sha, "Probe flag patch is not idempotent")
    if additional_probe_plan is not None:
        base_probe_tool = HERE / "bases_v1/prepare_base_probe.py"
        run([base_probe_tool, "patch", additional_probe_plan, staged])
        base_patch_sha = sha(staged)
        run([base_probe_tool, "patch", additional_probe_plan, staged])
        require(sha(staged) == base_patch_sha, 'Additional base probe patch is not idempotent')
    contract_args = [HERE / "check_native_contract.py", "--runtime", runtime, "--layout", layout,
                     "--level", staged, "--collision-receipt", receipt, "--probe-plan", plan, "--out", contract]
    if vehicle_spawn_policy is not None:
        contract_args += ["--vehicle-spawn-policy", vehicle_spawn_policy]
    run(contract_args)
    gate = read(contract)
    require(gate.get("layout3_permitted") is True, "Full contract gate did not pass")
    require(all(sha(name) == digest for name, digest in inputs.items()), "Input changed during verification")
    require(sha(level) == original_sha, "Converted scenario changed during verification")
    write(out / "flight-envelope.json", envelope(compiled, read(layout)))
    if apply:
        replace_verified(level, staged, original_sha, gate, inputs)
    report = {"schema": "pwr-native-probe-refresh-v1", "success": True, "applied": apply,
              "level": str(level), "original_level_sha256": original_sha,
              "verified_level_sha256": sha(staged), "probe_plan": str(plan), "probe_plan_sha256": sha(plan),
              "contract": str(contract), "contract_sha256": sha(contract), "inputs": inputs,
              "commands": commands, "live_acceptance_required": True,
              "next": "Bake from converted scenario, assemble, install with recovery receipt, then rerun native acceptance."
                      if apply else "Verified staged copy only. Rerun with --apply and a new --out directory to publish flags."}
    if architecture_proof is not None:
        report.update(architecture_proof=str(architecture_proof),
                      architecture_proof_sha256=sha(architecture_proof))
    if additional_probe_plan is not None:
        report.update(additional_probe_plan=str(additional_probe_plan),
                      additional_probe_plan_sha256=sha(additional_probe_plan))
    write(out / "refresh.receipt.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, default=DEFAULT_WORLD)
    parser.add_argument("--runtime", type=Path, default=HERE / "terrain/runtime-v5/runtime-master.json")
    parser.add_argument("--layout", type=Path, default=REPO / "out/pwr/world-v5/layout.json")
    parser.add_argument("--proof", type=Path, default=REPO / "out/pwr/world-v5/collision-runtime-final/collision-report.json")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Replace only isolated converted/pwr.level.json after every gate passes")
    parser.add_argument("--vehicle-spawn-policy", type=Path, help="Explicit reviewed vehicle-origin correction policy")
    parser.add_argument("--architecture-contract", type=Path,
                        help="Explicit hash-checked replacement-base contract; omitted preserves legacy architecture unchanged")
    parser.add_argument("--additional-probe-plan", type=Path,
                        help="Separate reviewed native base-floor/roof probe plan; keeps existing terrain probes")
    args = parser.parse_args()
    report = refresh(args.world, args.runtime, args.layout, args.proof, args.out, args.apply,
                     args.vehicle_spawn_policy, args.architecture_contract, args.additional_probe_plan)
    print(json.dumps({key: report[key] for key in ("success", "applied", "probe_plan", "contract", "next")}, indent=2))


if __name__ == "__main__":
    main()
