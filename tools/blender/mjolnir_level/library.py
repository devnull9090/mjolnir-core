# The shipped-mesh library: place correctly-sized proxies for the game's
# ~12k static meshes from a `mjolnir mesh list` catalog.
#
# A proxy is a plain box scaled to the mesh's local AABB with the UE object
# path stored in its MJOLNIR properties — the exporter emits it as decor, and
# the game shows the real mesh. The catalog is a one-time dump:
#
#   mjolnir mesh list --paks <Paks> --out mesh-catalog.json

import json

import bpy


def _load_catalog(path):
    with open(bpy.path.abspath(path), encoding="utf-8") as f:
        return json.load(f)


class MJOLNIR_OT_place_mesh(bpy.types.Operator):
    """Place a proxy box for a shipped mesh from the catalog"""

    bl_idname = "mjolnir.place_mesh"
    bl_label = "Place shipped mesh…"
    bl_options = {"REGISTER", "UNDO"}

    query: bpy.props.StringProperty(
        name="Search", description="Substring of the mesh path", default=""
    )

    def execute(self, context):
        s = context.scene.mjolnir
        if not s.catalog_path:
            self.report({"ERROR"}, "set the mesh catalog path first (mjolnir mesh list --out …)")
            return {"CANCELLED"}
        try:
            rows = _load_catalog(s.catalog_path)
        except Exception as e:  # noqa: BLE001 — surfaced to the user as-is
            self.report({"ERROR"}, f"catalog: {e}")
            return {"CANCELLED"}

        q = self.query.lower()
        matches = [r for r in rows if q in r["path"].lower() and r.get("min")]
        if not matches:
            self.report({"WARNING"}, f"no catalog mesh matches {self.query!r}")
            return {"CANCELLED"}
        row = matches[0]
        if len(matches) > 1:
            self.report({"INFO"}, f"{len(matches)} matches; placed the first: {row['path']}")

        # AABB in UE cm -> proxy dimensions in Blender meters. The proxy's
        # origin matches the mesh's local origin so the exported transform is
        # the actor transform, not the box centre.
        mn, mx = row["min"], row["max"]
        size = [max((mx[i] - mn[i]) / 100.0, 0.01) for i in range(3)]
        centre = [(mx[i] + mn[i]) / 200.0 for i in range(3)]

        mesh = bpy.data.meshes.new("proxy")
        obj = bpy.data.objects.new(row["path"].rsplit(".", 1)[-1], mesh)
        context.collection.objects.link(obj)

        import bmesh

        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        # Blender local = UE local with Y negated (both cm→m scaled).
        for v in bm.verts:
            v.co.x = v.co.x * size[0] + centre[0]
            v.co.y = v.co.y * size[1] - centre[1]
            v.co.z = v.co.z * size[2] + centre[2]
        bm.to_mesh(mesh)
        bm.free()
        obj.display_type = "WIRE"

        obj.mjolnir.kind = "DECOR"
        obj.mjolnir.mesh_path = row["path"]
        context.view_layer.objects.active = obj
        obj.select_set(True)
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
