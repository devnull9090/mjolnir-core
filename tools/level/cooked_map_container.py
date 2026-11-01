"""Resolve map cooks without breaking UE shader-library mount names."""
import json
from pathlib import Path


def cooked_map_container(conversion, code):
    conversion = Path(conversion)
    spec_path = conversion / "materials.spec.json"
    chunk = 985
    if spec_path.is_file():
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        if spec.get("authored_surfaces"):
            chunk = int(spec["chunk"])
            if chunk <= 0:
                raise ValueError("Authored materials need a positive cook chunk")
    return conversion / f"pakchunk{chunk}-MJOLNIRCOOK-{code}_P"
