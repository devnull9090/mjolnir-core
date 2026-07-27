# Getting Started: Editing Halo Campaign Evolved Tags

A practical guide to reading and changing Blam tags, with the `mjolnir` command line
and the MJOLNIR Tag Editor.

For *why* any of this works — the container format, the self-describing layout section, and
the evidence behind every rule — see [`tag_body_format.md`](tag_body_format.md). This page is
about using it.

---

## Before you start

**Read this first.** Two things are true and easy to miss:

1. **Nothing here modifies your game.** Every tool reads the installed containers read-only.
   An edit produces a *new file*; it does not touch the installation.
2. **Nothing here reaches the game yet.** Halo Campaign Evolved loads tags from UE5 IoStore
   containers (`.utoc`/`.ucas`), and writing those is not implemented. You can edit a tag and
   export it, but there is currently no supported way to make the game load the result. If
   that is what you are here for, this is not ready for you yet.

Extracted and edited tags are **copyrighted game content**. Keep them local. The repository
ignores `*.ubulk` and `tagdump/` for this reason, and only ever publishes *schema* — field
names, types, offsets — never values.

### What you need

- Halo Campaign Evolved installed (Steam).
- An `oo2core_9_win64.dll` from any local Unreal Engine install. UE 5.5+ links Oodle
  statically, so the game ships no separate copy.

```powershell
$env:HCE_PAKS = "C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved\Meteorite\Content\Paks"
$env:OODLE    = "C:\Program Files\Epic Games\UE_5.6\Engine\Binaries\DotNET\AutomationTool\oo2core_9_win64.dll"
```

Both tools read those two paths. The editor also auto-detects them on first run.

---

## Part 1: the command line

```powershell
cargo build --release -p blam-cli
# the binary lands at target/release/mjolnir
```

### Finding your way around

Start wide, then narrow.

```powershell
mjolnir groups                      # all 101 groups, with counts
mjolnir list --group weapon         # every weapon tag
mjolnir list --group weapon --limit 5
```

Group names are the long ones — `weapon`, `scenario_structure_bsp`, `model_animation_graph`
— not the four-CCs.

### Looking at a tag

```powershell
mjolnir values --group weapon --tag SMG
```

That prints the tag's fields with their **actual values**: enums resolved to option names,
bitfields to the names of the bits that are set, tag references as `path (group)`, colours as
hex.

Useful flags:

| Flag | What it does |
|---|---|
| `--tag <substring>` | Pick a tag by part of its path. Without it you get the first in the group. |
| `--depth N` | How deep to print. Start at `1` for a big tag. |
| `--elements N` | How many block elements to show. Default 4. |
| `--all` | Include fields whose value is empty or zero. |

**Tip.** Big tags are enormous — `scenario` has tens of thousands of fields. Start with
`--depth 1` and work down, or pipe through `findstr` / `grep`:

```powershell
mjolnir values --group model --depth 1 | findstr "tag reference"
```

### Changing a field

```powershell
mjolnir set --group camera_track --field "control points[3].position" --value "(1.5, 2.5, 3.5)"
```

```
  field    control points[3].position  [real vector 3d]
  before   (-3.522356, 0.00095, 1.838378)
  after    (1.5, 2.5, 3.5)
  changed  12 byte(s) at 0x345..=0x350, inside the field at 0x345..0x351
  contained within the field: true
  re-read  (1.5, 2.5, 3.5)  (walk exact: true)

  dry run; pass --out <file> to write the patched tag
```

**It is a dry run unless you pass `--out`.** Read the report before writing anything. The
last line is the important one: the patched bytes were parsed again from scratch and the
value read back out of them, so it is telling you what the *file* says, not what the command
intended.

```powershell
mjolnir set --group camera_track --field "control points[3].position" `
  --value "(1.5, 2.5, 3.5)" --out my-camera_track.ubulk
```

### Field paths

A path is what you saw in `mjolnir values`, joined with dots, with `[n]` for block and array
elements:

```
bounding radius                        a field on the root
unit.object.bounding radius            through inlined structs
control points[3].position             into element 3 of a block
item.object.functions[0].export name   both
```

The editor shows the same path when you hover a field name, so you can find one in the UI and
script it on the command line.

### Writing values

Give values in the same form `mjolnir values` shows them. The quotes and brackets are
optional.

| Type | Example |
|---|---|
| integer | `--value 12` |
| real | `--value 9.25` |
| vector, bounds, colour triple | `--value "(1.5, 2.5, 3.5)"` or `--value "1.5 2.5 3.5"` |
| enum | `--value large` (by name) or `--value 3` |
| bitfield | `--value "weapon can headshot \| allows binoculars"`, or `none`, or `0x280` |
| block index | `--value 3`, or `none` for unset |
| colour | `--value "#d72a2a"` or `--value "#ffd72a2a"` |
| string | `--value "assault rifle"` |
| string id | `--value flashlight_intensity` |
| tag reference | `--value "coll:fx\holograms\hologram_01"`, or `none` |

Option names are checked against **that field's** options. Setting `secondary flags` to
`"allows binoculars"` is refused, because that option belongs to `flags` — which is a useful
guard against editing the field next to the one you meant.

### Two kinds of edit

Most fields are **fixed width**: the new value goes over the old bytes and the file is
otherwise identical. The report tells you exactly which bytes moved.

A `string id` or `tag reference` keeps its value in a trailing section, so changing it
**resizes the tag**. Those take a different path: the data section is serialised again with
the new value in place. The report says so, and shows the new file size:

```
  file     21193 bytes -> 21214 bytes (the value resizes its section)
  re-read  fx\holograms\a_longer_name (coll)
  walk     1554 of 1554 bytes consumed
```

Setting one of these to the value it already has reproduces the file **byte for byte**, which
is how you can tell the rebuild itself is not disturbing anything.

### Checking your work

These run over your whole installation and are how the format claims are backed up. They are
also a good sanity check that your paths are right:

```powershell
mjolnir validate --all      # structural invariants, all 12,290 tags
mjolnir roundtrip --all     # read every tag, write it back, compare bytes
mjolnir recode --all        # decode and re-encode every field, compare bytes
```

`validate --all` takes a few minutes and reads ~5.6 GB. `roundtrip` and `recode` are slower
still. None of them writes anything.

### Digging into the format

```powershell
mjolnir fields --group weapon          # the field list, with offsets and sizes
mjolnir layout --group weapon --tables # type, block and struct tables
mjolnir sections                       # the tgly tables and the blay preamble
mjolnir data --group weapon --trace    # the value walk, section by section
mjolnir defs                           # export the whole schema corpus as JSON
```

`--trace` is the one to reach for when a tag will not read: it prints the walk as it happens
and stops at the failure, naming the field path.

---

## Part 2: the tag editor

```powershell
cd apps/tag-editor
pnpm install
pnpm tauri dev
```

On first run it looks for your installation and the Oodle DLL. If it cannot find them, point
it at the two paths above.

### Getting around

- **Left column**: tag groups, with how many tags each holds.
- **Middle column**: tags in the selected group, showing the tag name with its directory
  beside it. The search box searches every group at once.
- **Right pane**: the selected tag's fields and values.

The header tells you whether the values are trustworthy:

- **values exact** — the walk consumed the whole data payload. What you see is complete.
- **values partial** — something did not add up; treat the values with suspicion.
- If a tag cannot be read at all, the pane says so and shows the field path where the walk
  stopped, rather than pretending.

### Reading

Structs are expanded by default; blocks and arrays start collapsed when they are long. A
block header shows how many elements it really has. Very large blocks show only the first 64
— the header says `first 64 shown` when that happens, so a partial list is never mistaken for
the whole thing.

Hovering a value shows it in full, along with its field path.

### Editing

Click a value, type a new one, press **Enter**. **Escape** cancels.

Edited fields are marked with a dot and highlighted, and each gets an **undo** next to it.
A bar at the top of the pane counts the pending edits and reports what the last one did:

```
control points[3].position: (-3.522356, 0.00095, 1.838378) → (1.5, 2.5, 3.5) (12 bytes changed)
```

Values go in the same form the CLI takes — see the table above. Enums and bitfields are
written by name, tag references as `group:path`.

An edit is applied to a copy, the result re-parsed from scratch and re-walked, and only
recorded if that works. A value that does not fit is rejected and the field is left alone,
with the reason shown.

### Saving

There is no save button, and that is not an oversight. The game's containers are read-only,
so there is nowhere to save to. **Export patched tag…** writes the tag with your edits to a
file you choose.

Until IoStore writing exists, that file is for inspection, diffing and archiving — not for
loading into the game.

---

## Tips

**Diff two tags.** `mjolnir values` output is plain text, so:

```powershell
mjolnir values --group weapon --tag SMG --all > smg.txt
mjolnir values --group weapon --tag magnum --all > magnum.txt
fc smg.txt magnum.txt
```

**Find which tags reference another.** Tag references print as `path (group)`, so:

```powershell
mjolnir values --group model --depth 1 | findstr "hologram"
```

**Work out a field path.** Run `mjolnir values` with a small `--depth`, find the field, then
build the path from the names on the way down. Or hover it in the editor.

**Start with a small group.** `camera_track` is the smallest and decodes completely — a good
place to see the whole shape of a tag at once. `collision_damage`, `camo` and
`breakable_surface` are also small.

**When a tag will not read.** Nine `scenario` tags do not, and are documented. For anything
else, `mjolnir data --group <g> --trace` will name the field where the walk stopped, which is
usually enough to see what is going on.

---

## What is not supported yet

Being explicit, so you do not go hunting:

- **Loading edits into the game.** Writing IoStore containers is not implemented. This is the
  blocker between an edit and seeing it in Halo. What it would take is written up in
  [`iostore_packaging.md`](iostore_packaging.md).
- **Adding or removing block elements.** You can change values, not counts.
- **Editing `data` fields.** Their inline structure is not yet interpreted.
- **Nine `scenario` tags** whose values do not read, all failing on the same field slot. See
  [`tag_body_format.md`](tag_body_format.md) for the detail.
