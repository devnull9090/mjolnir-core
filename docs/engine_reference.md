# Engine reference

A knowledge base on how the game's simulation works: what each subsystem does,
which tag fields drive it, where its code lives in the simulation DLL, and how
we know. It is written for two readers: a person who wants to understand or
change something, and an AI agent that has to get a fact right without
rediscovering it.

The game is Halo: Campaign Evolved. Its rules run in a **Blam simulation**
(`HaloSimulation_tag_release.dll`, a descendant of the Reach engine that reads
Halo 1 content), and Unreal Engine draws the result. Most "how does the game
decide X" questions are questions about the simulation and the tags it reads.

## How to read an article

Every article follows the same shape, so a fact is always in the same place:

1. **Header table**: the subsystem, its tag data, its code, our code and tools,
   and its status.
2. **The idea in one paragraph.**
3. **The tag data**: blocks, fields, sizes, limits, and what shipped maps
   actually put there.
4. **How the simulation uses it**: a build pin, a code map (address, role,
   evidence), and the behaviour as pseudocode in our own words.
5. **What a writer must get right**: the rules a tool has to follow.
6. **Our implementation and how to run it.**
7. **Open questions**, each with why it matters and how to settle it.
8. **History.**

Every claim carries an evidence label:

| Label | Meaning |
|---|---|
| **traced** | Read from the simulation's code in a disassembler. |
| **data** | Measured on shipped tags, with a tool anyone can run again. |
| **live** | Seen in the running game. |
| **inferred** | Fits everything else, but has not been tested on its own. |

Addresses are **RVAs in one named build**. Add the image base (`0x180000000`)
for Ghidra. An address without a build is worth nothing, because the game
updates; each article's build pin says which file it means, and
[build_lock.md](build_lock.md) says which build is current.

[How to research and verify](engine_research_method.md) has the method: the
Ghidra setup, how to anchor a function so it can be found again, how to census
shipped data, and what may and may not be committed.

## Articles

Written to the standard above:

| Article | Covers |
|---|---|
| [AI pathfinding](engine_ai_pathfinding.md) | Sectors, links, refs and hints; how a ground contact becomes a sector; the instance policy gate; the pathfinding generator. |

## The rest of what we know, by subsystem

These are older notes. They are accurate about what they measured, but they are
working logs rather than reference articles: some carry superseded turns, and
their addresses are for the build named at their top. Each is a candidate for
rewriting to the standard. The one-line summaries below were written from each
note's opening, not from a full read.

### The simulation itself

| Doc | Covers |
|---|---|
| [halosimulation_tag_release.md](halosimulation_tag_release.md) | The DLL: its one export, the shell object and its interface tables (CU2 addresses). |
| [game_state_reader.md](game_state_reader.md) | The object and player tables in memory, and reading them from outside. |
| [tag_table_and_string_ids.md](tag_table_and_string_ids.md) | How the simulation indexes loaded tags and string ids. |
| [live_tag_locating.md](live_tag_locating.md), [guobjectarray_reader.md](guobjectarray_reader.md) | Finding a loaded tag's data in the running game. |
| [blam_console.md](blam_console.md) | The simulation's console and how commands reach it. |
| [blam_script.md](blam_script.md) | HaloScript: the function table, compiled script data, what runs. |
| [re/ce_map_scripts.md](re/ce_map_scripts.md) | Custom Edition map scripts on this engine. |

### Level geometry and collision

| Doc | Covers |
|---|---|
| [re/collision_bsp/README.md](re/collision_bsp/README.md) | How the simulation resolves collision BSP data at runtime, and why a resized collision table crashes it. |
| [ce_terrain_collision.md](ce_terrain_collision.md) | Halo CE terrain as this engine's collision. |
| [heightfield_collision.md](heightfield_collision.md) | Master heightfields for large terrain and the collision prototype built from them. |
| [ce_native_support.md](ce_native_support.md) | Which CE tag data the engine reads natively. |
| [new_scenario_loading.md](new_scenario_loading.md) | What a brand-new scenario needs before the game will start it. |

### AI

| Doc | Covers |
|---|---|
| [engine_ai_pathfinding.md](engine_ai_pathfinding.md) | Where an AI can walk (the reference article). |
| [re/ai_in_multiplayer.md](re/ai_in_multiplayer.md) | Why `ai_place` does nothing in a multiplayer game, and how AI is made to run there. |
| [bots.md](bots.md) | Squads, firing positions and characters generated for converted maps. |
| [pwr_ai_feasibility.md](pwr_ai_feasibility.md) | Covenant AI on a 2 km map: budgets, dropships, objectives. |

### Game rules and multiplayer

| Doc | Covers |
|---|---|
| [re/megalo_engine.md](re/megalo_engine.md), [re/reach_game_engine.md](re/reach_game_engine.md) | The Megalo rules engine inside the simulation and how the host drives it. |
| [re/megalo_variant_format.md](re/megalo_variant_format.md), [re/variant_network_safety.md](re/variant_network_safety.md) | The game variant bitstream, and what is safe to send to clients. |
| [game_modes.md](game_modes.md), [custom_game_types.md](custom_game_types.md) | Which modes run, and writing new ones. |
| [re/forge_engine.md](re/forge_engine.md), [re/map_variant_format.md](re/map_variant_format.md) | Forge in the simulation and the map variant format. |
| [re/medals.md](re/medals.md), [re/restored_cheats.md](re/restored_cheats.md), [re/lift_push.md](re/lift_push.md), [re/client_sound_roles.md](re/client_sound_roles.md) | Smaller mechanisms, each traced once. |

### Tags and files

| Doc | Covers |
|---|---|
| [tag_data_pipeline.md](tag_data_pipeline.md) | Where tag data lives in the game's packages. |
| [tag_body_format.md](tag_body_format.md) | The layout section that describes a tag's blocks and fields. |
| [jmad_format.md](jmad_format.md) | Animation graph frames. |
| [iostore_packaging.md](iostore_packaging.md) | Getting an edited tag back into the game. |
| [wwise_audio_format.md](wwise_audio_format.md) | Where the audio lives. |

## Facts that keep coming up

| Fact | Label | Source |
|---|---|---|
| One world unit is 3.048 m. Unreal's coordinates are world units x 304.8 with y negated. | data | `crates/blam-cli/src/level_navmesh.rs` |
| Pathfinding link and vertex indices are unsigned 16-bit, `0xFFFF` for none. | data | [AI pathfinding](engine_ai_pathfinding.md) |
| A tag-data address inside the simulation is a 32-bit value `x`; the pointer is `segment_table[x >> 28] + x * 4`, with the segment table at RVA `0x2c2ccc0` (CU4). | traced | seen in every pathfinding reader |
| An `instanced geometry instances` element is 148 bytes; its definition index is the short at `+0x34`, its pathfinding policy the byte at `+0x7c`. | traced, data | [AI pathfinding](engine_ai_pathfinding.md) |
| `generate_pathfinding` is a stub, so the shipped simulation cannot regenerate pathfinding. The release build points 425 script functions at one shared return-false handler. | traced | [AI pathfinding](engine_ai_pathfinding.md), [re/restored_cheats.md](re/restored_cheats.md) |
| AI is not placed in a multiplayer game by the stock script functions. | traced, live | [re/ai_in_multiplayer.md](re/ai_in_multiplayer.md) |

## Adding an article

1. Name it `engine_<subsystem>.md` in `docs/` and list it under the `engine`
   section of `docs/site.json`, or the docs sync fails.
2. Follow the eight-part shape above. Start from
   [AI pathfinding](engine_ai_pathfinding.md).
3. Put a label on every claim, and a build pin above every address.
4. Give each open question a way to settle it. An article that says what is
   not known is worth more than one that reads as finished.
5. Add a row to the article table here, and move the old note's row out of the
   "rest of what we know" tables once the article replaces it.

## For AI agents

- Start here, then read the one article for the subsystem you are changing.
  The header table tells you which crate and which tools to open.
- Trust the labels. **traced** and **data** claims can be built on. Treat
  **inferred** as a hypothesis and test it before a design depends on it.
- Before using an address, check the article's build pin against
  `config/hce-build.lock.json`. If they differ, use the article's "finding it
  again" anchors instead of the address.
- When you learn something new, put it in the article, with its label, not
  only in a commit message or a session note.
- Decompiler output never goes in the repository. Describe behaviour in your
  own words and pseudocode ([how to research](engine_research_method.md)).
