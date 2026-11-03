# Build your own battleground: modular Forge packs

**Author:** MJOLNIR Core
**Summary:** Build with MJOLNIR's modular Forge kits, Warthog roads, automatic doors, gravity lifts and green teleporters. Tour Crossline, plan a first courtyard, and learn how to contribute your own model pack.
**Tags:** forge, multiplayer, maps
**Image:** /blog-images/forge-building/featured.webp

A floor becomes a courtyard. Add a ramp and it becomes a raised base. Connect two bases with a bridge, put a road underneath, and suddenly there is a map worth arguing over.

That is what we want building in Forge to feel like. The latest MJOLNIR update brings modular construction packs together with better placement controls and pieces that do something: doors that open as you approach, lifts that carry you to another route, and the familiar green glow of a Halo CE teleporter.

Get the latest launcher and mods, then explore the [Forge packs](/forge) and [maps](/maps) on the Hub. The screenshots below come from the game; the labelled studio renders show the actual model geometry with Blender lighting.

## Start with pieces that fit

There are two families of building materials: **Foundry** for structures and **Roadworks** for vehicle routes. Foundry also has a separately namespaced **Wide** kit, so larger construction does not silently change an older map's pieces.

| Kit | Pieces | What it is for |
| --- | ---: | --- |
| Foundry 0.2 | 24 | The original compact blocks, floors, cover, frames and light fixtures |
| Foundry Wide 0.2 | 38 | Larger floors, walls, ramps, junctions, windows, doors, lifts and teleporter housings on a 4 m module |
| Roadworks 0.2 | 10 | Long roads, curves and ramps with open or guarded edges |

The scale comes from driving and walking around the pieces. Earlier roads felt cramped beside a Warthog, so Roadworks now has **16 metres of clear road width**. Wide's new floor is **16 × 16 m**, its broad ramps are **8 m wide**, and its vehicle doorway has an **8 × 5.5 m clear opening**. Those dimensions belong to the models themselves: builders should not have to stretch every piece before it is useful.

![Foundry Wide's 38 actual pieces, with dimensions and matching families. Blender catalogue render; glass and energy materials here are previews.](/blog-images/forge-building/foundry-wide.webp)

[Open the full-size Foundry Wide catalogue](/blog-images/forge-building/foundry-wide.webp) to read every label and dimension.

The kit gives you several ways to solve the same problem. A shallow ramp makes a long approach; a steeper one fits a smaller corner. Full walls close the perimeter, glazed walls preserve a sightline, and T-junctions or crosses let a bridge become a network of routes. The original Foundry lights provide warm, red and blue landmarks.

## Place it, line it up, keep it there

The new controls make a suspended bridge practical to build. Pick up a piece with **V**, choose its physics with **F3**, and drop it where you want it:

- **Normal** uses the object's usual physics.
- **Fixed** holds the placed object in space.
- **Phased** holds it in space and permits overlapping geometry while building.

**F4** cycles a position grid from 0.25 to 4 metres. **F10** selects a rotation snap, and comma/period turn the piece. The HUD keeps the settings visible. **F5** saves the layout; **F6** loads it again, including the object's physics properties.

The grid aligns placement to world coordinates. It does not automatically join road endpoints or detect a nearby edge. For precise construction, use Phased mode, line up the origins, and check the result from Spartan height. Native holding and collision can still affect a final turn.

Our new [Forge building guide](/docs/guides/forge-guide) walks through the controls and a complete first build.

## Give the room another way through

The new utility pieces make a layout more than a collection of solids.

**Automatic doors** pair a frame with a moving panel. Fixed or Phased panels open on approach and close after the path clears. Their visible models and native collision move together. Saving an open door stores its closed starting position, so the next session does not begin with the panel's origin stranded above the frame. Leave clearance overhead and provide another route around a door while testing your map.

![In-game: the large door panel raised above its frame in Crossline, leaving the vehicle-sized opening clear.](/blog-images/forge-building/door.webp)

**Gravity lifts** offer a compact upward route. The lift station has four shallow walk-up ramps, a central launch area and a nearby landing in Crossline. Walk in, rise, then steer toward the gallery. It is a useful alternative to putting another long ramp in every room.

![In-game: the lift's four ground approaches and the adjacent raised landing. The cyan centre marks the launch area.](/blog-images/forge-building/lift.webp)

**Teleporters** have an animated green field based on the CE effect, while the native sender/receiver markers handle travel. The visible housing alone is not a destination: place the markers, give them a matching channel, and test both ends with room to step away from the trigger.

![In-game: Crossline's green teleporter field on a raised base. The two ends were tested for travel in both directions.](/blog-images/forge-building/portal.webp)

**Glass and windows** let players read the next space before entering it. These panes are transparent and solid, which makes them useful for observation corridors and separating routes without hiding them from one another.

![In-game: a cyan glass wall in the utility lane. You can see the arena through it; the pane blocks walking from either side.](/blog-images/forge-building/glass.webp)

## Three ways to put the kit to work

### A first courtyard

Start small: one 16 × 16 m floor, one broad ramp, six wall sections and two low cover pieces. That is ten pieces, with a finished deck 2 m above the ground. The ramp meets the floor, the walls give the space a boundary, and the opening is wide enough to understand at a glance.

![Build plan: ten pieces form a 16 × 16 m raised courtyard, with an 8 m-wide approach ramp. The guide gives the placement recipe.](/blog-images/forge-building/courtyard-plan.svg)

Build this first, walk every join, then add a window, another entrance or an upper route. The [step-by-step guide](/docs/guides/forge-guide#build-a-raised-courtyard) includes a parts list and planning coordinates. A blank **Forge Canvas** provides a 64 × 64 m starting deck; its palette must be baked with the Wide kit before using this particular recipe.

Once the joins work, the same idea grows into something like this:

![Blender assembly study: 31 unchanged Wide pieces form a 32 × 32 m courtyard with a raised gallery, ramp, bridge, door, lift and portal. This is a layout illustration, not an additional playable map; materials use Blender previews.](/blog-images/forge-building/assembly.webp)

### A red-versus-blue arena

**Crossline** is the larger playable showcase: **96 × 160 m**, with raised bases, broad approaches, side galleries and an open ground route for Warthogs. The utility lanes let you try the new pieces without making a door or lift the only way across the arena. Its 9 m perimeter keeps the construction enclosed.

![In-game aerial view of Crossline 0.3, built from the modular kits. The raised routes and the open lower arena occupy different heights.](/blog-images/forge-building/crossline-overview.webp)

![Crossline layout plan derived from its authored placements and routes. Colours distinguish the two bases and the utility areas.](/blog-images/forge-building/crossline-plan.svg)

All twenty new Wide pieces appear in the map, and all 38 are available in its Forge palette. The map includes team-owned base spawns and neutral midfield starts for free-for-all Slayer. That distinction matters: a map can look finished and still give a game type nowhere valid to spawn a player.

### A Warthog circuit

**Roadworks** uses straight sections, 45° and 90° curves, and ramps that rise 4 m over a 48 m run. The curves have a 40 m centreline radius. Guarded versions put barriers outside the clear road width; open versions are useful for intersections, pit entries and places where a builder wants a separate boundary.

![Roadworks' ten actual models, including long straights, curved connections and raised approaches. Blender catalogue render with all pieces shown at the same scale.](/blog-images/forge-building/roadworks.webp)

The **Roadworks Circuit** test map joins them into an approximately 731 m loop with a pit and raised route on a 320 × 320 m recovery deck. Use it as a starting point for driving experiments. The kit supplies the road geometry; race checkpoints and lap timing are separate future work.

## Bring your own pieces

We want community authors to expand the vocabulary: another architectural style, a set of columns and arches, industrial interiors, outdoor cover, or a racing kit with its own character.

You can contribute at two levels. **Model authors** can submit original source geometry, dimensions, collision shapes, previews and a small example layout in a pull request. **Pack authors** can take that work through the full build, test and signing process to produce a `.mjolnir` content archive. A `.blend` file is an authoring source, not something the game can place directly.

The [community pack-authoring guide](/docs/guides/forge-pack-authoring) covers the process:

1. **Design a small, consistent set.** Use real dimensions, stable origins and deliberate join heights. For a kit that fits Wide, start from its 4 m module and test against a Spartan and a Warthog early.
2. **Build both appearance and collision.** A convincing visual mesh needs matching collision and physics. Keep glass solid where intended and keep decorative energy out of the passage.
3. **Give the pack its own identity.** A catalogue supplies names, categories, dimensions and namespaced piece IDs. Optional lights, lifts and doors use bounded data fields rather than scripts supplied by the pack.
4. **Test a small map.** Place, rotate, freeze, save and reload the pieces. Walk the seams, drive the corners, and check that a doorway is actually clear.
5. **Package, sign and submit the release.** The guide includes the build commands and explains the Hub's author-key, upload and validation requirements. Your catalogue gives other builders a way to discover the pieces and see what fits their map.

A map declares its pack dependencies and supported palette when it is baked. The launcher resolves the required releases before play, downloading missing dependencies, and saved Forge layouts record the pack releases they were built with. A pack can be updated later, but an update has to keep every piece that existing maps and layouts use, and the Hub checks that before it publishes one. Downloading another pack does not add arbitrary new entries to an already-baked map's palette. Those boundaries keep a later asset update from quietly changing someone else's level.

## Make a place of your own

Start with a route you want to play: a courtyard with two entrances, a bridge worth fighting over, or a curve you can take at speed. Build its outline, walk or drive it, and add detail once the space feels right.

[Follow the building guide](/docs/guides/forge-guide), [create a pack](/docs/guides/forge-pack-authoring), or browse the [source kits](https://github.com/devnull9090/mjolnir-core/tree/main/forge-packs). A useful first contribution can be one good wall, one reliable ramp, and a place that shows why they belong together.
