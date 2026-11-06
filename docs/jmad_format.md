# model_animation_graph frames

**Status:** 2026-11-05, build CU4. Everything marked measured holds on all 178
shipped graphs (8,354 members). The code is `crates/blam-jmad`; `mjolnir jmad`
is its command line. Nothing written by this crate has run in the game yet,
apart from the layout it shares with `tools/level/h2_machines.py`.

## Where the frames are

The tag's own layout covers the graph down to `tag resource groups`. Each
element holds a reference count and a `tag_resource`, a pageable resource
whose section body the layout does not describe. The body is:

```
tgdt   12 bytes: member count, then 8 bytes that differ per group
tgst   version word = size
  tgbl count, flags 0
    count x 100 byte member records
    count x tgst (version word = size)
      tgst   empty
      tgda   the member's data blob
```

Rebuilding this from its parts reproduces every shipped body (measured).
`definitions.animations[].shared animation data[0]` names a member by
`resource_group` and `resource_group_member`.

## The member record

| Offset | Size | Holds |
|---:|---:|---|
| 0 | 4 | `animation_index` (0 in every member) |
| 4 | 4 | `animation_checksum`; carried, meaning unknown |
| 8 | 2 | frame count |
| 10 | 1 | node count |
| 11 | 1 | movement kind, equal to the shared element's `frame info type` (measured) |
| 12 | 68 | seventeen segment sizes |
| 80 | 4 | blob size: the sum of the seventeen (measured) |
| 84 | 16 | `0x10`, `-1`, 0, 0 in every member (measured) |

## Segments

The blob is the seventeen segments back to back. The tag definitions name
the sizes, but the first six names do not fit what the bytes hold, so this
table goes by content.

| # | Members | Holds | Size |
|---:|---:|---|---|
| 0 | 8354 | static pose, codec 1 | see below |
| 1 | 8354 | animated frames: codec 3 (3193), 9 (5141), 8 (20) | see below |
| 2 | 8354 | static node flags | 12 x words |
| 3 | 8354 | animated node flags | 12 x words |
| 4 | 2684 | root movement | per frame: 8, 12, 16, 24 bytes for kind 1, 2, 3, 4 |
| 5 | 8248 | a 12 byte value a frame; zero in what we write | 12 x frames |
| 6 | 8351 | animated frames again, uncompressed, codec 2 | see below |
| 7 | 1471 | blend screen table (the Warthog's steering and acceleration have one) | varies |
| 8 | 13 | not decoded; opens with a small number | varies |
| 9 | 770 | IK chain effector transforms: rotation, translation and scale tracks for each chain, reached by a chain row's `effector transform data index` | varies |
| 10 | 770 | IK chain effector weights, by `effector weight data index` | varies |
| 13 | 7433 | object-space frames | 4 + 32 x nodes x frames |
| 14 | 9 | not decoded | varies |
| 15 | 7433 | object-space node mask | 32 |
| 16 | 389 | not decoded | varies |

Segments 11 and 12 never occur. Three members have no segment 6: one frame, nothing animated.

`words` is `ceil(nodes / 32)`. A flag segment is three bit vectors of that
length: rotation, translation, scale. Node `i` is bit `i % 32` of word
`i / 32`. A node is never both static and animated in one channel, and a node
in neither stays at its default (measured). Values appear in node order.

## Codecs

Every codec block opens with:

| Offset | Size | Holds |
|---:|---:|---|
| 0 | 1 | codec |
| 1 | 3 | rotating, translating and scaling node counts |
| 4 | 8 | two floats, unknown use: 0, 0 on codecs 1 and 2; 0 to 7.4, then 0.5 to 1.0 on codec 3; 0, 1 on codec 8 |
| 12 | 4 | offset of the translations |
| 16 | 4 | offset of the scales |
| 20 | 12 | bytes per node of rotations, translations, scales |

| Codec | Rotation | Translation | Scale | Strides | Round trip |
|---:|---|---|---|---|---|
| 1 | 4 x i16 | 3 x f32 | f32 | 0, one value a node | decoded, exact |
| 2 | 4 x f32 | 3 x f32 | f32 | 16f, 12f, 4f | decoded, exact |
| 3 | 4 x i16 | 3 x f32 | f32 | 8f, 12f, 4f | decoded, exact |
| 8 | as codec 2 | | | | decoded, exact |
| 9 | curves | | | | carried as bytes |

`f` is the frame count. Frames are node-major: all of the first node's
rotations, then the next node's. An i16 component is the float x 32767.

Codec 9 opens with the same four count bytes, then a table of track offsets
and a `WANG` tag. It is not decoded: every member that uses it also has
segment 6, which is what a rewrite reads. Rewritten members use codec 3.

Shipped codec 3 rotations sit within one step of `round(raw x 32767)`, and two
members store the opposite sign of the same rotation. The writer rounds to
nearest, so re-encoding a shipped member from its raw copy is close but not
identical. Reading a member and writing it back is identical, because the
decoder keeps the integers.

## Object-space frames

Segment 13 opens with u16 node count and u16 frame count, then 32 bytes a
frame, node-major: rotation, position, scale. The mask's bits are the nodes
that have any flag set in segment 2 or 3 (measured), so a node left out of the
animation is left out here too.

- Base animations: forward kinematics of the local frames over the skeleton,
  to within 6e-4 (measured, all shipped base animations). The rotation can have
  either sign.
- Overlays: not forward kinematics of the stored frames. On the Warthog entry
  `f` of a turning node matches frame `f - 1`, and entry 0 holds a rest pose
  that is neither the defaults nor frame 0. How it is derived is unknown.

The writer keeps stored frames for nodes that survive a rewrite, and uses
forward kinematics for anything new, for nodes an edit touches and those below
them, and for all of an animation whose frame count changes. For a new overlay that is a guess, though
`h2_machines.py` does the same with `device:position`, an overlay, and it works
in game.

## Node references

Changing the node list touches:

- `definitions.skeleton nodes` and `additional node data`: same count, same
  order. The string id is in the element's wrapper; its four inline bytes are 0.
  `additional node data` holds each node's bind pose in object space: on the
  Warthog, 117 of 118 rows match `SK_Warthog_01`'s bones through the Y flip and
  304.8 cm per unit (measured). The rewrite treats a spec's pose as a local, so
  `ce_vehicle_nodes.default_sets` puts the object-space values on afterwards.
- `first child` and `next sibling`. Shipped graphs order siblings three ways
  (107 fall by index, 33 do neither, 38 are ambiguous), so the rewrite keeps
  the donor's order. New nodes go last.
- `definitions.node usage`: rows for dropped nodes go.
- `object-space parent nodes` per animation: rows for dropped nodes go.
- `run time data` left and right arm bit vectors.
- `shared animation data` node count, and the member's. All must match the
  skeleton: the model's load silently clears a graph ref if any animation's
  node count, or any node's parent or child, disagrees with the skeleton tag.

A rewrite that changes the node list refuses a graph that uses `node masks`,
`ik chains`, the inheritance lists, `foot tracking`, `object space offset nodes`,
`forward-invert kinetic anchor nodes`, or member segments 8 to 12, 14 or 16,
because those hold node references it does not translate. Vehicle graphs use none
of them; bipeds do.

On the same nodes, an edit carries those segments as bytes, which is safe because
the tag's `ik chain events` rows stay as they are and index into them. On the
Spartan, all 277 chains hold the same tracks: zero translation, scale 1 and a
rotation track that differs only in its frame byte and one byte more (measured).
So segment 9 holds no pose of its own, but it does hold the frame count, and
segment 10's size varies by animation, not with the chain count. An edit that
changes the frames of a member holding these segments is refused.

Segment 7 is carried unchanged. It was not checked for node indices.

## Rewriting a graph

```
mjolnir jmad info warthog.model_animation_graph --nodes
mjolnir jmad roundtrip <directory of extracted graphs>
mjolnir jmad rewrite warthog.model_animation_graph --spec spec.json --out new.jmad
mjolnir jmad diff warthog.model_animation_graph new.jmad
mjolnir jmad frames new.jmad --animation any:idle --out frames.json
mjolnir new-tag --group model_animation_graph --from <donor> --to <tag> --payload new.jmad ...
```

`diff` names every member that changed and which of its segments, then says
whether the tag around the resources did. `frames` writes the skeleton and the
decoded local frames of the animations named, as JSON.

To replace a shipped graph instead, use `mjolnir pack --payload`. It writes only
the `.utoc` and `.ucas`, and a pair with no `.pak` beside it never mounts, so
add a stub (`ue_iostore::pak::stub_for`, or a copy of a shipped one).

A spec, with every top-level key optional:

```json
{
  "keep": ["pedestal", "root", "chassis"],
  "nodes": [
    { "name": "handlebar", "parent": "chassis", "translation": [0.5, 0, 0.25] },
    { "name": "frame", "parent": "root", "from": "body" }
  ],
  "animations": [
    { "name": "any:idle", "frames": 3,
      "nodes": { "handlebar": { "rotation": [[0, 0, 0, 1], [0, 0, 0.38, 0.92], [0, 0, 0.71, 0.71]] } } }
  ],
  "reencode": true
}
```

- `keep` names donor nodes; each hangs from its nearest kept ancestor and takes
  on the motion of any node between. `nodes` adds to that list: a node with
  `from` continues a donor node, and one without is new. With neither key the
  skeleton stays as it is.
- `rotation`, `translation` and `scale` take one value, held still, or a list
  of one a frame.
- An animation listed changes only the nodes it names. If `frames` differs from
  the donor's, the rest hold their first frame, and segments 4, 5 and 7 go. A
  member with chain data must keep its frame count.
- Animations not listed are carried across, re-encoded if the node list changed.
- `reencode` writes every member afresh in codecs 1, 2 and 3.

Every animation is rewritten, since one left at the old node count loses the
whole graph. `node list checksum`, `frame_ID1`, `frame_ID2`,
`animation_checksum` and `production checksum` are carried from the donor, and
new nodes get zero. The load does not compare the node list checksum.

## A graph that inherits

```
mjolnir jmad child full.jmad --parent 'objects\characters\spartans\spartans' \
    --animation ghost_d:idle --animation ghost_d:grip --out child.jmad
```

The load rebuilds inheritance: it merges the parent's rows into a graph by label
at every level (mode, weapon class, weapon type, set, actions, overlay animations,
death and damage, transitions, vehicle suspension, function overlays), and a row
the graph has itself wins. Overlay groups and IK sets are found at run time, by
walking up the parent chain from a row that has none. A graph with a parent that
changes a few animations therefore need only hold those animations. Cutting
`content.modes` from a graph with a parent is proven in game, and so are a cut mode
playing and a child row replacing a parent row that has an overlay group.

`jmad child` writes that graph from a full one:

- `animations` holds the animations named, in pool order. Their frames, events and
  `ik chain events` are unchanged. `parent animation` and `next animation` follow
  an animation that stayed, and otherwise clear, as `blend screen` does; the command
  lists what it cleared.
- Each kept animation keeps the row it is named for, by labels with `any` left out:
  `warthog_p`, `rifle`, `any`, `any`, `idle` is `warthog_p:rifle:idle`. A row that
  plays the same animation under another name is listed and left to the parent, so
  it plays the parent's frames. An animation named for no row keeps every row that
  plays it. An animation no action or overlay row plays is refused, as is a kept
  weapon class with `ranged actions` or `sync actions groups`, whose rows hold
  indices this does not translate.
- Above those rows, only the elements on the way to them stay. `overlay group` and
  `ik set` go to none at all five levels. Each kept mode, class and set keeps the
  lists the merge does not fill in (`mode ik`, `foot defaults`, `weapon ik`,
  `velocity boundaries`).
- `tag resource groups` holds only the groups in use, renumbered, and each only the
  members in use. A group's member count is in three places, which agree on all
  178 shipped graphs (measured): its `reference_count`, the first word of its `tgdt`,
  and its member block. The other two words of `tgdt` are carried. `--whole-groups`
  keeps every member of a group in use, for a test that rules the cut out.
- Emptied: `blend screens`, `NEW blend screens`, `NEW function overlays`,
  `overlay groups`, `ik data`, `ik sets`, `ik chains`, `vehicle suspension`,
  `function overlays` and the run time lists. Unchanged: the skeleton and everything
  else the kept rows and animations index, including `gaits`, `gait groups`, sound
  and effect references, `node masks` and `functions`.
- `inheritance flags` is 0, and a graph whose private flags have 0x40 set is refused,
  since the load does not compile it.

On the Spartan, three animations take the graph from 111,037,420 bytes to 526,650.

### A mode under a new label

```
mjolnir jmad child full.jmad --parent 'objects\characters\spartans\spartans' \
    --mode ghost_d=mongoose_d --mode warthog_p=mongoose_p \
    --animation ghost_d:idle --animation ghost_d:grip --animation warthog_p:rifle:idle \
    --out child.jmad
```

None of this has run in game yet: a child that owns overlay groups, a renamed mode
merging the parent's rows, and the IK walk from a new label come from reading the load.

Editing `ghost_d:idle` where it stands changes every Ghost on the map. `--mode
DONOR=NEW` carries all of the donor's rows under `NEW` instead, and the donor's label
leaves the child, so the parent's rows stand for it.

- `--animation` still names what was edited. An animation a renamed mode plays stays
  in that mode; one outside keeps its own row, as above. Every other row of the mode
  plays the same pool entry it did, so a row that borrows an edited animation in the
  mode plays the edit. The pool's names do not change: they are what `--animation`
  matches, and the load matches them to the `imported events` tag for frame events.
- A row cannot play the parent's pool, because the load discards rows with a graph
  index. So the child's pool takes every animation the mode plays, with its members.
- The game finds a row's overlay group by the labels the row stands at: in the graph,
  then up the parent chain, then with `any` for each label in turn. It reads the group
  from the graph it found it in. Under a new label the parent's group is out of reach,
  so a kept mode keeps its `overlay group` fields, and the child keeps those groups, the
  `NEW blend screens` they list and those screens' animations, renumbered. Their names
  stay the donor's. A group's owner reads it as it would its own, so nothing here
  depends on inheritance.
- A row of the parent's at `NEW` merges in by label as ever, so the Spartan's
  `mongoose_d:throw_grenade` joins the child's `mongoose_d`. Where both have a row, the
  child's wins.
- A renamed mode is refused if it has an `ik set` at any level, a group with function
  overlays, a blend screen into another graph, rows in `death and damage` or
  `transitions`, or a weapon class with `ranged actions` or `sync actions groups`.
  None of these carry over yet. `ghost_d` and `warthog_p` have none of them: the only
  IK set is on `alert`, `combat` and `crouch`, reached through the walk's last step,
  mode `combat` with the row's other labels, which does not depend on the seat's label.
- `ik chains` stay empty, since the load copies the parent's into a child with none,
  and each animation's `ik chain events` index them as they did.

`ghost_d` and `warthog_p` under new labels take the Spartan child to 9,524,299 bytes:
80 animations, 43 resource groups, 16 overlay groups and 28 blend screens. `ghost_d`
is 0.96 MB of that alone, and `warthog_p`, with six weapon classes, 8.6 MB.

## Checks

`mjolnir jmad roundtrip` decodes every member, requires each file back byte
for byte, and requires encode, decode, encode to be stable. The tests in
`crates/blam-jmad/tests/corpus.rs` run the same over `JMAD_CORPUS`, along with
the rules marked measured above and the Warthog rewrites.

## Unknown

- Whether the game reads segment 1, segment 6 or both, and what uses segment 13.
- The two codec header floats and the 8 bytes in `tgdt`.
- Whether a node name the game has never registered works here. Such names work
  in scenario fields; a jmad has not been tried.
- Segment 5's meaning, and everything in segments 7, 8, 14 and 16, and how the
  game reads segments 9 and 10 beyond the rows that index them.
