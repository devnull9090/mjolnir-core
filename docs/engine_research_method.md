# How to research the engine and verify what you find

Part of the [engine reference](engine_reference.md). This is the method behind
its articles: how a question about the simulation gets answered well enough to
build on, and how the answer is written down so the next reader does not have
to repeat the work.

## The rule: two independent sources

A finding goes in an article as fact only when two different kinds of evidence
agree. There are three kinds:

| Kind | Label | What it is good at | How it misleads |
|---|---|---|---|
| The simulation's code | **traced** | Says exactly what is read and what is not. | Easy to misread a field offset or miss a second code path. |
| Shipped tags | **data** | Shows what real, working content looks like, at scale. | Shows what Bungie wrote, not what the engine requires. |
| The running game | **live** | The only proof that something works. | Slow, and a pass does not say why. |

A reading that only fits (one source, or none) is labelled **inferred** and
kept out of designs until tested.

The pathfinding work is the worked example
([AI pathfinding](engine_ai_pathfinding.md)). Shipped data alone suggested that
each instanced-geometry definition has one pathfinding object. The code showed
that the simulation ignores an instance's pathfinding unless a policy byte says
`static`. Going back to the data with that rule explained every number: 16
static instances, 16 objects of their own, and 825 ignored instances that all
point at object 0. Either source alone had led to a wrong design.

## Tracing the code

**Setup.** Ghidra 12 with the simulation DLL analysed, driven headless over MCP
so a session can ask for decompiles and cross-references without the GUI:
[re/ghidra_mcp.md](re/ghidra_mcp.md) has the install and the commands. Start
the headless server from PowerShell, not Git Bash, which rewrites the
`/Program` path argument.

**Finding the code for a subsystem.** The DLL has no symbols. What works:

1. **Start from data you can name.** A tag block has a fixed element size, so
   its readers multiply an index by that size (`* 0x94` for an instance
   element, `* 0x18` for an object ref). Search for the constant near a
   plausible caller.
2. **Start from a script function.** The HaloScript function table maps names
   to handlers ([blam_script.md](blam_script.md)). A function such as
   `ai_place` leads straight into its subsystem. A handler that is the shared
   return-false stub tells you the feature is compiled out.
3. **Start from a constant table.** Small lookup tables (an axis-projection
   table, a flag mask) are rare byte patterns and their cross-references are
   short lists.
4. **Follow the accessor.** Most subsystems fetch their data through one small
   function. Once found, its callers are the whole subsystem. To prove a field
   is never read, check every caller, and every direct user of the table
   behind it.

**Pin the build.** Record the file's size, SHA-256 and PE timestamp with any
address. `config/hce-build.lock.json` lists them for the current build.

**Leave anchors.** For each function worth finding again, write down something
that survives a rebuild: a byte pattern in data it references, a distinctive
constant, or its position in a short caller chain. After a game update, find
the function by its anchor, then re-run the data check before trusting it.

## Measuring shipped data

Write a small example program that reads the block through `blam_tag` and
prints counts and distributions, and keep it in the crate
(`crates/blam-sbsp/examples/pf_stats.rs` is the model). Three habits:

- **Census before design.** Run it over every shipped scenario, not one. Limits
  and rare cases only show at scale (the 16-bit link index was settled by one
  BSP with 59,826 links).
- **Turn assumptions into checks.** If you believe every ring closes, write the
  check and run it on shipped data. A check that fails on Bungie's data is your
  mistake, and a generator's output must pass the same checks.
- **Round-trip before writing.** Before a tool writes a block, make it read
  shipped data and write it back, and compare bytes (`pf_roundtrip.rs`). This
  catches container mistakes (missing child blocks, wrong wrappers) that no
  amount of reasoning about values will.

## Testing in the game

- Use the smallest map that can show the effect, and a control: the same test
  with shipped data in place of ours.
- Read state, do not guess from behaviour: object and AI records can be read
  from the running game ([game_state_reader.md](game_state_reader.md)).
- A crash seconds after an action usually means malformed data was read, not
  wrong values. Check the container before the contents.
- Solo first, then two or three game copies on one PC
  ([multi_instance.md](multi_instance.md)), then two PCs
  ([two_pc_test.md](two_pc_test.md)). Each step finds different faults.

## Writing it down

- One article per subsystem, in the shape the
  [engine reference](engine_reference.md) describes. Facts go in the article;
  the session's story goes in the pull request.
- State behaviour in your own words, with pseudocode of your own. **Decompiler
  output, and code or names from other people's decompilation projects, are
  never committed.** Addresses, sizes, field offsets and measured numbers are
  facts and are fine.
- Say what is not known. Give every open question a way to settle it.
- Label every claim. If you later find an inferred claim was wrong, fix the
  article and note it in its history, so nobody builds on the old reading.
