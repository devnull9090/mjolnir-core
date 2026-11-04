#!/usr/bin/env python3
"""Turn a Custom Edition map's scripts into HSC the CU4 engine accepts.

    ce_translate.py <map> <out.hsc> [--tags <staging tags.json>] [--report report.json]
                    [--staging <staging dir>]

The engine compiles a scenario's source text at load, one script failing on
its own, so the product is text (docs/re/ce_map_scripts.md). The script comes
from the map's own syntax data, as a tree that keeps each literal's type, and
goes through these passes:

1. Normalise: script names without spaces, global initialisers folded.
2. Host: CE had no way to ask whether a machine is the host, so maps probe for
   it. Scripts run on the host alone here, so the flag becomes `true`.
3. Sync: CE 1.0 could not replicate a device, so a map's host drives a vehicle
   onto a biped and every machine acts on the death. The check and sync script
   pair around a control becomes one rule, and any other signal biped a boolean.
4. Create and destroy: scenery and unanimated machines a script creates and
   destroys are parked and brought home by position instead
   (tools/level/ce_machines.py), and `*_containing` expands over object names.
5. Functions: the rename, drop and seat-label table below; tag literals go
   through ce_tag_paths.json.
6. Names: only machines, controls, trigger volumes and cutscene flags reach
   the bake. A statement naming anything else is dropped, since a name no
   placement claims costs the whole script.
7. Registrars for string id literals the game has not registered.

The report says what to carry (it feeds tools/level/ce_promote.py,
ce_machines.py and add_devices.py) and every thing left out, with why.
"""
import argparse
import collections
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ce_hs  # noqa: E402
import ce_scenario  # noqa: E402
from ce_hs import Call, Lit  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))

# CE's name for a function CU4 has under another.
RENAMES = {
    "show_hud": "chud_show",
    "hud_show_motion_sensor": "chud_show_motion_sensor",
    "hud_show_shield": "chud_show_shield",
    "hud_show_health": "chud_show_shield",
    "hud_show_crosshair": "chud_show_crosshair",
    "object_pvs_set_camera": "pvs_set_camera",
    "object_pvs_set_object": "pvs_set_object",
    "show_hud_help_text": "hud_show_training_text",
    "hud_set_help_text": "hud_set_training_text",
    "vehicle_test_seat_list": "vehicle_test_seat_unit_list",
}
# Dropped with nothing in their place: saves, prediction, the camera a converted
# map's cleared cutscene blocks would drive, and the one BSP switch.
DROPS = {"game_save_totally_unsafe", "game_save", "game_save_no_timeout", "game_save_cancel", "rasterizer_decals_flush",
         "objects_predict", "switch_bsp", "object_pvs_activate", "camera_control", "camera_set",
         "cinematic_start", "cinematic_stop", "cinematic_show_letterbox", "cinematic_set_title",
         "cinematic_screen_effect_start", "cinematic_screen_effect_stop", "object_pvs_clear"}
DROP_SUFFIX = ("_predict",)
# CE seat labels with a CU4 name a shipped script uses. Any other label takes
# CU4's "", any seat, which CE's "" also means.
SEATS = {"w-passenger": "warthog_p"}
# Value types whose literals name a tag.
TAG_TYPES = {"sound", "effect", "damage", "looping_sound", "animation_graph", "actor_variant", "damage_effect",
             "object_definition"}
OBJECT_TYPES = {"object", "unit", "vehicle", "weapon", "device", "scenery", "object_name", "unit_name", "vehicle_name",
                "weapon_name", "device_name", "scenery_name"}
# Scenario blocks a converted map does not carry.
DEAD_TYPES = {"ai", "ai_command_list", "starting_profile", "conversation", "navpoint", "hud_message",
              "cutscene_recording", "cutscene_camera_point", "cutscene_title"}
QUOTED = TAG_TYPES | {"string", "string_id", "unit_seat_mapping"}
GLOBAL_TYPES = {"boolean", "real", "short", "long", "string", "object", "unit", "vehicle", "weapon", "device",
                "object_list"}
HOST_NAME = re.compile(r"(^|_)(is_?)?(server|host)(_|$)", re.I)
HOST_OBJECT = re.compile(r"(^|_)(server|host)(_|$)", re.I)
TRUE, FALSE = Lit("true", "boolean"), Lit("false", "boolean")
# Spawned onto a biped: how far (wu) a crusher or its flag can be from it.
SIGNAL_REACH = 3.0


class Script:
    def __init__(self, name, kind, returns, body):
        self.name, self.kind, self.returns, self.body = name, kind, returns, body


def walk(e):
    yield e
    if isinstance(e, Call):
        for a in e.args:
            yield from walk(a)


def is_true(e):
    return isinstance(e, Lit) and e.text == "true"


def is_false(e):
    return isinstance(e, Lit) and e.text == "false"


def is_call(e, *names):
    return isinstance(e, Call) and (not names or e.fn in names)


def is_boolean(e):
    """A condition: a flag, or a call that answers yes or no."""
    if isinstance(e, Lit):
        return e.is_global and e.vtype == "boolean"
    return e.vtype == "boolean" or e.fn in ("<", ">", "<=", ">=", "=", "!=", "and", "or", "not")


def number(e):
    if isinstance(e, Lit) and e.vtype in ("real", "short", "long"):
        try:
            return float(e.text)
        except ValueError:
            return None
    return None


def statements(body):
    """A list of statements with nested `begin`s flattened."""
    out = []
    for s in body:
        if is_call(s, "begin"):
            out += statements(s.args)
        elif s is not None:
            out.append(s)
    return out


def block(items):
    items = statements(items)
    if not items:
        return None
    return items[0] if len(items) == 1 else Call("begin", items)


def fold(e):
    """Constant conditions and arithmetic, bottom up. Removes dead branches."""
    if not isinstance(e, Call):
        return e
    e = Call(e.fn, [fold(a) for a in e.args], e.vtype, e.script)
    if e.fn in ("*", "+", "-", "/") and e.args and all(number(a) is not None for a in e.args):
        v = [number(a) for a in e.args]
        try:
            r = {"*": math.prod(v), "+": sum(v), "-": v[0] - sum(v[1:]), "/": v[0] / (math.prod(v[1:]) or 1)}[e.fn]
        except IndexError:
            return e
        return Lit(repr(r), "real")
    if e.fn == "=" and len(e.args) == 2:
        a, b = e.args
        for x, y in ((a, b), (b, a)):
            if is_true(y) and (is_true(x) or is_false(x)):
                return x
            if is_false(y) and (is_true(x) or is_false(x)):
                return TRUE if is_false(x) else FALSE
            if is_true(y) and (is_boolean(x)):
                return x
            if is_false(y) and (is_boolean(x)):
                return Call("not", [x], "boolean")
        if number(a) is not None and number(b) is not None:
            return TRUE if number(a) == number(b) else FALSE
    if e.fn == "not" and e.args:
        if is_true(e.args[0]):
            return FALSE
        if is_false(e.args[0]):
            return TRUE
    if e.fn in ("and", "or"):
        stop, skip = (is_false, is_true) if e.fn == "and" else (is_true, is_false)
        if any(stop(a) for a in e.args):
            return e.args[[stop(a) for a in e.args].index(True)]
        kept = [a for a in e.args if not skip(a)]
        if not kept:
            return TRUE if e.fn == "and" else FALSE
        return kept[0] if len(kept) == 1 else Call(e.fn, kept, e.vtype)
    if e.fn == "if" and e.args:
        cond = e.args[0]
        then = e.args[1] if len(e.args) > 1 else None
        other = e.args[2] if len(e.args) > 2 else None
        if isinstance(other, Lit) and other.text in ("", "none"):
            other = None
        if is_true(cond):
            return then if then is not None else Call("begin", [])
        if is_false(cond):
            return other if other is not None else Call("begin", [])
        return Call("if", [cond, then] + ([other] if other is not None else []), e.vtype)
    return e


class Translator:
    def __init__(self, path, tags=None, staging=None):
        m, s, syntax, strings, scripts, globs, info = ce_hs.load(path)
        self.scenario = ce_scenario.Scenario(path, tags)
        self.objects = self.scenario.named_objects()
        self.names = [n for n in info["object_names"] if n]
        self.volumes = {v["name"]: v for v in self.scenario.trigger_volumes()}
        self.flags = {f["name"]: f for f in self.scenario.cutscene_flags()}
        self.groups = {g["name"] for g in self.scenario.device_groups()}
        self.console = {f["name"]: f for f in json.load(open(os.path.join(REPO, "defs", "hce", "console.json")))["functions"]}
        self.engine_globals = {g["name"] for g in json.load(open(os.path.join(REPO, "defs", "hce", "console.json")))["globals"]}
        self.tag_paths = json.load(open(os.path.join(HERE, "ce_tag_paths.json"), encoding="utf-8"))["paths"]
        self.string_ids = {x[1] for x in json.load(open(os.path.join(REPO, "defs", "hce", "string-ids.json")))["ids"]}
        self.notes = collections.defaultdict(collections.Counter)
        self.dropped = {}
        self.rules = []
        self.startup = []
        self.promote = set()
        self.staging = staging
        self.globals, self.scripts = [], []
        if not syntax:
            return
        read = ce_hs.tree_reader(syntax, strings)
        names = {}
        for name, (st, rt, root) in scripts:
            clean = re.sub(r"[^A-Za-z0-9_]", "_", name)
            # A protector's names can be empty or bare numbers, which the
            # compiler reads as no name at all.
            names[name] = clean if re.match(r"[A-Za-z_]", clean) else f"script_{clean or len(names)}"
        taken = collections.Counter(names.values())
        for old, new in list(names.items()):
            # Protectors reuse a name once its punctuation goes.
            if taken[new] > 1:
                names[old] = f"{new}_{list(names).index(old)}"
        self.script_names = names
        for name, t, init in globs:
            self.globals.append([name, ce_hs.TYPES[t] if t < len(ce_hs.TYPES) else str(t), read(init)])
        kinds = {g[0]: g[1] for g in self.globals}
        for name, (st, rt, root) in scripts:
            try:
                body = read(root)
            except IndexError:
                # A protector's scrambled node: the script cannot be read.
                self.dropped[names[name]] = "unreadable"
                continue
            for e in walk(body) if body is not None else ():
                if isinstance(e, Lit) and e.is_global:
                    e.vtype = kinds.get(e.text, e.vtype)
            self.scripts.append(Script(names[name], ce_hs.SCRIPT_TYPES[st] if st < 5 else "static",
                                       ce_hs.TYPES[rt] if rt < len(ce_hs.TYPES) else "void",
                                       statements([body]) if body is not None else []))

    # ---- helpers ----
    def note(self, kind, what):
        self.notes[kind][what] += 1

    def each(self, f):
        """Rewrite every expression bottom up; `f` gets a Call or Lit."""
        def go(e):
            if isinstance(e, Call):
                e = Call(e.fn, [go(a) for a in e.args], e.vtype, e.script)
            return f(e)
        for s in self.scripts:
            s.body = [go(x) for x in s.body]
        for g in self.globals:
            g[2] = go(g[2]) if g[2] is not None else None

    def fold_all(self):
        for s in self.scripts:
            s.body = statements([fold(x) for x in s.body])
        for g in self.globals:
            g[2] = fold(g[2]) if g[2] is not None else None

    def reads(self):
        """How many times each global is read, `set` targets aside."""
        n = collections.Counter()

        def go(e):
            if is_call(e, "set"):
                for a in e.args[1:]:
                    go(a)
            elif isinstance(e, Call):
                for a in e.args:
                    go(a)
            elif e.is_global:
                n[e.text] += 1
        for s in self.scripts:
            for x in s.body:
                go(x)
        return n

    # ---- 1. normalise ----
    def normalise(self):
        def f(e):
            if isinstance(e, Call) and e.script:
                e.fn = self.script_names.get(e.fn, e.fn)
            elif isinstance(e, Lit) and e.vtype == "script":
                e.text = self.script_names.get(e.text, e.text)
            elif isinstance(e, Lit) and not e.is_global:
                # Names are case-blind to the engine, and CE's compiler kept
                # what the script typed, not what the block holds.
                e.text = spelled.get(e.text.lower(), e.text)
            return e
        spelled = {n.lower(): n for n in [*self.objects, *self.volumes, *self.flags, *self.groups]}
        self.each(f)
        self.fold_all()

    # ---- 2. host ----
    def host_flags(self):
        """Boolean globals that mean "this machine is the host"."""
        probe = set()
        for s in self.scripts:
            for x in s.body:
                for e in walk(x):
                    if is_call(e, "if") and is_call(e.args[0], ">=", ">") and is_call(e.args[0].args[0], "unit_get_health") \
                            and (number(e.args[0].args[1]) or 0) <= 0:
                        for y in walk(e.args[1]):
                            if is_call(y, "set") and is_true(y.args[1]):
                                probe.add(y.args[0].text)
        named = {g[0] for g in self.globals if g[1] == "boolean" and HOST_NAME.search(g[0])}
        return named | probe

    def host(self):
        def probe(e):
            # A biped kept to tell the host from a client reads as alive.
            t = self.health_test(e)
            if t and HOST_OBJECT.search(t[0]):
                return FALSE if t[1] else TRUE
            return e
        self.each(probe)
        self.fold_all()
        flags = self.host_flags()
        if not flags:
            return
        self.note("host", " ".join(sorted(flags)))

        def f(e):
            if isinstance(e, Lit) and e.is_global and e.text in flags:
                return TRUE
            return e
        for s in self.scripts:
            s.body = [self.without_sets(x, flags) for x in s.body]
        self.each(f)
        self.globals = [g for g in self.globals if g[0] not in flags]
        self.fold_all()

    def without_sets(self, e, names):
        if is_call(e, "set") and e.args[0].text in names:
            return Call("begin", [])
        if isinstance(e, Call):
            return Call(e.fn, [self.without_sets(a, names) for a in e.args], e.vtype, e.script)
        return e

    # ---- 3. sync ----
    def biped_for(self, name, position):
        """The signal biped `position` lands on, by distance, then by name."""
        bipeds = {k: v for k, v in self.objects.items() if v["kind"] == "biped"}
        if not bipeds:
            return None
        near = min(bipeds, key=lambda k: math.dist(bipeds[k]["position"], position))
        if math.dist(bipeds[near]["position"], position) <= SIGNAL_REACH:
            return near
        for old, new in (("_flag", "_biped"), ("crush_", "check_")):
            if name.replace(old, new) in bipeds:
                return name.replace(old, new)
        return None

    def target_of(self, e):
        """The biped a statement crushes: a teleport onto a flag over one, or a
        vehicle created where it stands."""
        if is_call(e, "object_teleport") and len(e.args) == 2 and isinstance(e.args[1], Lit):
            f = self.flags.get(e.args[1].text)
            o = self.objects.get(e.args[0].text) if isinstance(e.args[0], Lit) else None
            if f and o and o["kind"] == "vehicle":
                return self.biped_for(e.args[1].text, f["position"])
        if is_call(e, "object_create", "object_create_anew") and isinstance(e.args[0], Lit):
            o = self.objects.get(e.args[0].text)
            if o and o["kind"] == "vehicle":
                return self.biped_for(e.args[0].text, o["position"])
        return None

    def health_test(self, e):
        """A condition on a signal biped: (biped, whether it asks for dead)."""
        if not is_call(e, "<", "<=", "=", "!=", ">", ">=") or len(e.args) != 2 or not is_call(e.args[0], "unit_get_health") \
                or not isinstance(e.args[0].args[0], Lit):
            return None
        n, v = e.args[0].args[0].text, number(e.args[1])
        if self.objects.get(n, {}).get("kind") != "biped" or v is None:
            return None
        if (e.fn in ("<", "<=") and 0 <= v <= 1) or (e.fn == "!=" and v == 1) or (e.fn == "=" and v == 0):
            return n, True
        if (e.fn == ">" and v == 0) or (e.fn == "=" and v == 1):
            return n, False
        return None

    def death_of(self, e):
        """The biped a condition waits on the death of."""
        t = self.health_test(e)
        return t[0] if t and t[1] else None

    def control_rules(self):
        """A check script (the control's position sends a crusher to one of two
        flags) and the sync script behind it become one rule."""
        by_name = {s.name: s for s in self.scripts}
        syncs = {}
        for s in self.scripts:
            for x in s.body:
                if is_call(x, "if") and self.death_of(x.args[0]):
                    syncs.setdefault(self.death_of(x.args[0]), []).append((s, x))
        gone = set()
        for s in list(self.scripts):
            body = [x for x in s.body if not is_call(x, "sleep")]
            if s.kind != "continuous" or len(body) != 1 or not is_call(body[0], "if") or len(body[0].args) != 3:
                continue
            cond, then, other = body[0].args
            control = self.position_test(cond)
            if control is None:
                continue
            open_b = [self.target_of(y) for y in walk(then) if self.target_of(y)]
            closed_b = [self.target_of(y) for y in walk(other) if self.target_of(y)]
            if len(open_b) != 1 or len(closed_b) != 1 or open_b[0] not in syncs or closed_b[0] not in syncs:
                continue
            moves = {}
            for label, biped in (("on", open_b[0]), ("off", closed_b[0])):
                for sync, branch in syncs[biped]:
                    for y in walk(branch.args[1]):
                        if is_call(y, "device_set_position", "device_set_position_immediate"):
                            moves[label] = y
                    gone.add(sync.name)
            if len(moves) != 2 or moves["on"].args[0].text != moves["off"].args[0].text:
                continue
            machine = moves["on"].args[0]
            stem = re.sub(r"_machine$", "", machine.text)
            rule = Call("if", [cond, Call("device_set_position", [machine, moves["on"].args[1]]),
                               Call("device_set_position", [machine, moves["off"].args[1]])])
            gone.add(s.name)
            self.rules.append(Script(f"{stem}_rule", "continuous", "void", [rule, Call("sleep", [Lit("15", "short")])]))
            self.note("rule", stem)
            # At rest with the control off: a machine whose off position is 1
            # starts there, where the sync's first run would have put it.
            if number(moves["off"].args[1]) == 1.0:
                self.startup.append(Call("device_set_position_immediate", [machine, Lit("1.0", "real")]))
        self.scripts = [s for s in self.scripts if s.name not in gone] + self.rules
        for name in gone:
            self.dropped[name] = "replaced by a device rule"
        del by_name

    def position_test(self, cond):
        if is_call(cond, "=") and is_call(cond.args[0], "device_get_position") and number(cond.args[1]) == 1.0:
            return cond.args[0].args[0].text
        return None

    def signals(self):
        """Every other biped whose death means something becomes a boolean."""
        read = set()
        for s in self.scripts:
            for x in s.body:
                for e in walk(x):
                    t = self.health_test(e)
                    if t:
                        read.add(t[0])
        if not read:
            return
        made = set()

        def f(e):
            t = self.health_test(e)
            if t:
                made.add(t[0])
                flag = Lit(f"sig_{t[0]}", "boolean", True)
                return flag if t[1] else Call("not", [flag], "boolean")
            b = self.target_of(e)
            if b in read:
                made.add(b)
                return Call("set", [Lit(f"sig_{b}", "global", True), TRUE])
            if is_call(e, "object_create", "object_create_anew") and isinstance(e.args[0], Lit) and e.args[0].text in read:
                return Call("set", [Lit(f"sig_{e.args[0].text}", "global", True), FALSE])
            return e
        self.each(f)
        for b in sorted(made):
            # A biped not placed yet has no health, which reads as dead.
            self.globals.append([f"sig_{b}", "boolean", TRUE if self.objects[b]["not_placed"] & 1 else FALSE])
            self.note("signal", b)
        # A wait straight after the signal that ends it is over at once.
        for s in self.scripts:
            s.body = self.drop_met_waits(s.body)

    def drop_met_waits(self, body):
        out = []
        for x in statements(body):
            if is_call(x, "sleep_until") and isinstance(x.args[0], Lit) and x.args[0].is_global and out and is_call(out[-1], "set") \
                    and out[-1].args[0].text == x.args[0].text and is_true(out[-1].args[1]):
                continue
            if isinstance(x, Call) and x.fn in ("if", "begin"):
                x = Call(x.fn, [a if i == 0 and x.fn == "if" else block(self.drop_met_waits([a])) or Call("begin", [])
                                for i, a in enumerate(x.args)], x.vtype)
            out.append(x)
        return out

    def unreachable(self):
        """Dormant and static scripts nothing wakes or calls, from the scripts
        that run by themselves."""
        by_name = {s.name: s for s in self.scripts}
        seen, work = set(), [s for s in self.scripts if s.kind in ("startup", "continuous")]
        while work:
            s = work.pop()
            if s.name in seen:
                continue
            seen.add(s.name)
            for x in s.body:
                for e in walk(x):
                    name = e.fn if isinstance(e, Call) and e.script else e.text if isinstance(e, Lit) and e.vtype == "script" else None
                    if name in by_name:
                        work.append(by_name[name])
        for s in self.scripts:
            if s.name not in seen:
                self.dropped[s.name] = "never runs"
        self.scripts = [s for s in self.scripts if s.name in seen]

    # ---- 4. create and destroy ----
    def containing(self):
        """`*_containing` over the object names that hold its text."""
        def stmt(e):
            if isinstance(e, Call) and e.fn in ("object_create_containing", "object_create_anew_containing",
                                                "object_destroy_containing"):
                fn = e.fn.replace("_containing", "")
                text = e.args[0].text
                return Call("begin", [Call(fn, [Lit(n, "object_name")]) for n in self.names if text in n])
            return e
        self.each(stmt)
        self.fold_all()

    def animated(self, name):
        o = self.objects.get(name)
        if not o or o["kind"] != "machine":
            return False
        m = self.scenario.machines()[o["index"]]
        return m["datum"] is not None and self.scenario.device_tag(m["datum"])["animated"]

    def parked(self):
        """Scenery and unanimated machines a script creates or destroys."""
        moved = set()
        for s in self.scripts:
            for x in s.body:
                for e in walk(x):
                    if is_call(e, "object_create", "object_create_anew", "object_destroy") and isinstance(e.args[0], Lit):
                        o = self.objects.get(e.args[0].text)
                        if o and (o["kind"] == "scenery" or (o["kind"] == "machine" and not self.animated(e.args[0].text))):
                            moved.add(e.args[0].text)

        def f(e):
            if is_call(e, "object_create", "object_create_anew", "object_destroy") and isinstance(e.args[0], Lit) \
                    and e.args[0].text in moved:
                to = "0.0" if e.fn == "object_destroy" else "1.0"
                return Call("device_set_position_immediate", [Lit(e.args[0].text, "device"), Lit(to, "real")])
            return e
        self.each(f)
        for name in sorted(moved):
            o = self.objects[name]
            if o["kind"] == "scenery":
                self.promote.add(name)
                if not o["not_placed"] & 1:
                    self.startup.append(Call("device_set_position_immediate", [Lit(name, "device"), Lit("1.0", "real")]))

    # ---- 5. functions and tags ----
    def functions(self):
        def f(e):
            if isinstance(e, Lit):
                if e.vtype in TAG_TYPES and e.text not in ("", "none"):
                    path = self.tag_paths.get(e.text.lower())
                    if path:
                        return Lit(path, e.vtype)
                return e
            if e.script:
                return e
            if e.fn == "structure_bsp_index":
                return Lit("0", "short")
            if e.fn in RENAMES:
                e = Call(RENAMES[e.fn], e.args, e.vtype)
            # CU4 added an argument to each of these.
            if e.fn == "device_group_set" and len(e.args) == 2:
                e = Call("device_group_set_immediate", e.args, e.vtype)
            if e.fn == "unit_exit_vehicle" and len(e.args) == 1:
                e = Call(e.fn, e.args + [Lit("0", "short")], e.vtype)
            if e.fn in ("vehicle_test_seat_unit_list", "vehicle_unload", "vehicle_test_seat_unit", "vehicle_test_seat",
                        "unit_test_seat"):
                e = Call(e.fn, [self.seat(a) for a in e.args], e.vtype)
            return e
        self.each(f)

    def seat(self, a):
        if isinstance(a, Lit) and a.vtype == "string":
            return Lit(SEATS.get(a.text, ""), "unit_seat_mapping")
        return a

    # ---- 6. names ----
    def why_dead(self, e, scripts):
        """Why an expression cannot stay, or None."""
        for x in walk(e):
            if isinstance(x, Call):
                if x.script:
                    if x.fn not in scripts:
                        return ("dropped script", x.fn)
                    continue
                if x.fn in DROPS or x.fn.endswith(DROP_SUFFIX):
                    return ("dropped function", x.fn)
                f = self.console.get(x.fn)
                if f is None:
                    return ("no such function", x.fn)
                if f["stub"]:
                    return ("stubbed function", x.fn)
                params = f.get("parameters")
                if params and len(params) != len(x.args) and x.fn not in FLEXIBLE:
                    return ("argument count", x.fn)
            else:
                t = x.text
                if x.is_global or t in ("", "none"):
                    continue
                if x.vtype in DEAD_TYPES:
                    return ("not carried: " + x.vtype, t)
                if x.vtype in TAG_TYPES and t not in self.tag_paths.values():
                    return ("no CU4 tag: " + x.vtype, t)
                if x.vtype == "trigger_volume" and t not in self.volumes:
                    return ("no such volume", t)
                if x.vtype == "cutscene_flag" and t not in self.flags:
                    return ("no such flag", t)
                if x.vtype == "device_group" and t not in self.groups:
                    return ("no such group", t)
                if x.vtype == "script" and t not in scripts:
                    return ("dropped script", t)
                if x.vtype in OBJECT_TYPES and t in self.names:
                    o = self.objects.get(t)
                    if t in self.promote:
                        continue
                    if o is None:
                        return ("object never placed", t)
                    if o["kind"] not in ("machine", "control"):
                        return ("not carried: " + o["kind"], t)
        return None

    def prune(self, e, scripts):
        """`e` with its dead parts gone, or None."""
        if not isinstance(e, Call):
            return None if isinstance(e, Lit) and not e.is_global and e.text in ("", "none") else e
        if e.fn in ("begin", "begin_random"):
            kept = [y for y in (self.prune(a, scripts) for a in e.args) if y is not None]
            return (block(kept) if e.fn == "begin" else Call(e.fn, kept, e.vtype)) if kept else None
        if e.fn == "if":
            dead = self.why_dead(e.args[0], scripts)
            if dead:
                self.note(dead[0], dead[1])
                return None
            then = self.prune(e.args[1], scripts) if len(e.args) > 1 else None
            other = self.prune(e.args[2], scripts) if len(e.args) > 2 else None
            if then is None and other is None:
                return None
            if then is None:
                return Call("if", [Call("not", [e.args[0]], "boolean"), other], e.vtype)
            return Call("if", [e.args[0], then] + ([other] if other is not None else []), e.vtype)
        dead = self.why_dead(e, scripts)
        if dead:
            self.note(dead[0], dead[1])
            return None
        return e

    def no_op(self, s):
        return all(self.pure(x) for x in s.body)

    def pure(self, e):
        """A statement with no effect of its own, so a script of nothing else
        goes: waits, sleeps."""
        if is_call(e, "if"):
            return all(self.pure(a) for a in e.args[1:])
        if is_call(e, "begin"):
            return all(self.pure(a) for a in e.args)
        return is_call(e, "sleep", "sleep_until", "sleep_forever") or isinstance(e, Lit)

    def constants(self):
        """A boolean global nothing sets is its initial value."""
        initial = {g[0]: g[2] for g in self.globals if g[1] == "boolean" and (is_true(g[2]) or is_false(g[2]))}
        for s in self.scripts:
            for x in s.body:
                for e in walk(x):
                    if is_call(e, "set") and e.args[0].text in initial:
                        v = e.args[1]
                        if not (isinstance(v, Lit) and v.text == initial[e.args[0].text].text):
                            del initial[e.args[0].text]
        fixed = initial
        if fixed:
            for s in self.scripts:
                s.body = [self.without_sets(x, set(fixed)) for x in s.body]
            self.each(lambda e: fixed[e.text] if isinstance(e, Lit) and e.is_global and e.text in fixed else e)
            self.globals = [g for g in self.globals if g[0] not in fixed]
            self.fold_all()

    def dead_stores(self):
        self.constants()
        reads = self.reads()
        unread = {g[0] for g in self.globals if not reads[g[0]]}
        if unread:
            for s in self.scripts:
                s.body = statements([self.without_sets(x, unread) for x in s.body])
            self.globals = [g for g in self.globals if g[0] not in unread]
            self.fold_all()
        return bool(unread)

    def closure(self):
        """Prune to a fixed point: a dropped script takes its callers' calls
        with it, and a store nothing reads goes with what it read."""
        for _ in range(20):
            before = self.text()
            names = {s.name for s in self.scripts}
            for s in self.scripts:
                s.body = statements([self.prune(x, names) for x in s.body])
            self.fold_all()
            self.dead_stores()
            kept = []
            for s in self.scripts:
                if s.kind != "static" and self.no_op(s):
                    self.dropped.setdefault(s.name, "nothing left to do")
                else:
                    kept.append(s)
            self.scripts = kept
            self.globals = [g for g in self.globals if g[1] in GLOBAL_TYPES and (g[2] is None or not self.why_dead(g[2], names))]
            if self.text() == before:
                break

    # ---- 7. registrars ----
    def registrars(self):
        need = set()
        for s in self.scripts:
            for x in s.body:
                for e in walk(x):
                    if isinstance(e, Lit) and e.vtype == "string_id" and e.text and e.text not in self.string_ids:
                        need.add(e.text)
        have = {s.name for s in self.scripts}
        return sorted(need - have)

    # ---- output ----
    def show(self, e, pad="    "):
        if isinstance(e, Lit):
            if e.vtype in QUOTED or (" " in e.text):
                return '"%s"' % e.text
            return e.text or "none"
        parts = [e.fn] + [self.show(a, pad + "    ") for a in e.args]
        flat = "(" + " ".join(parts) + ")"
        if len(flat) + len(pad) <= 100 and "\n" not in flat:
            return flat
        return "(" + parts[0] + "".join("\n" + pad + "    " + p for p in parts[1:]) + ")"

    def text(self):
        out = []
        for name, t, init in self.globals:
            if t in ("short", "long") and number(init) is not None:
                init = Lit(str(int(number(init))), t)
            out.append(f"(global {t} {name} {self.show(init) if init is not None else default_of(t)})")
        for s in self.scripts:
            head = f"script {s.kind} {s.returns} {s.name}" if s.kind in ("static", "stub") else f"script {s.kind} {s.name}"
            out.append("\n(" + head + "".join("\n    " + self.show(x) for x in s.body) + ")")
        return "\n".join(out) + "\n"

    def carried(self):
        words = collections.defaultdict(set)
        for s in self.scripts:
            for x in s.body:
                for e in walk(x):
                    if not isinstance(e, Lit) or e.is_global:
                        continue
                    if e.vtype == "trigger_volume":
                        words["volumes"].add(e.text)
                    elif e.vtype == "cutscene_flag":
                        words["flags"].add(e.text)
                    elif e.vtype == "device_group":
                        words["device_groups"].add(e.text)
                    elif e.text in self.objects:
                        k = self.objects[e.text]["kind"]
                        words[{"machine": "machines", "control": "controls"}.get(k, "promoted")].add(e.text)
        return {k: sorted(v) for k, v in words.items()}

    def run(self):
        if not self.scripts:
            return
        self.normalise()
        self.host()
        self.containing()
        self.control_rules()
        self.signals()
        self.dead_stores()
        self.unreachable()
        self.parked()
        self.functions()
        if self.startup:
            self.scripts.insert(0, Script("devices_start", "startup", "void", self.startup))
        self.closure()
        for name in self.registrars():
            self.scripts.append(Script(name, "static", "void", [Call("sleep", [Lit("0", "short")])]))
            self.note("registrar", name)

    def compile_names(self):
        """What `mjolnir compile --names` needs: the scenario this script will
        meet, with the names the report carries."""
        c = self.carried()
        return {"object names": c.get("machines", []) + c.get("controls", []) + c.get("promoted", []),
                "trigger volumes": c.get("volumes", []), "cutscene flags": c.get("flags", []),
                "device groups": c.get("device_groups", [])}

    def report(self):
        return {"names": self.compile_names(), "carry": self.carried(), "promote": sorted(self.promote), "scripts": [s.name for s in self.scripts],
                "dropped_scripts": self.dropped,
                "notes": {k: dict(v.most_common()) for k, v in sorted(self.notes.items())}}


FLEXIBLE = {"begin", "begin_random", "if", "cond", "set", "and", "or", "+", "-", "*", "/", "=", "!=", "<", ">", "<=", ">=",
            "min", "max", "sleep", "sleep_until", "wake", "print", "inspect", "not", "sleep_forever"}


def default_of(t):
    return {"boolean": "false", "real": "0.0", "short": "0", "long": "0", "string": '""'}.get(t, "none")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("map")
    ap.add_argument("out")
    ap.add_argument("--tags", help="the staging's tags.json, for protected maps")
    ap.add_argument("--staging")
    ap.add_argument("--report")
    a = ap.parse_args()
    t = Translator(a.map, a.tags, a.staging)
    t.run()
    head = f"; {os.path.basename(a.map)}, by tools/ce_scripts/ce_translate.py\n\n"
    open(a.out, "w", encoding="utf-8").write(head + t.text())
    report = t.report()
    if a.report:
        json.dump(report, open(a.report, "w", encoding="utf-8"), indent=1)
    print(f"{len(t.scripts)} script(s), {len(t.dropped)} dropped, carry: "
          + ", ".join(f"{len(v)} {k}" for k, v in report["carry"].items()))


if __name__ == "__main__":
    main()
