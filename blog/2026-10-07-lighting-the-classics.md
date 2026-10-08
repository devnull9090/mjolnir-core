# Lighting the classics: teaching Unreal Engine to light Halo CE's maps

**Author:** MJOLNIR Core
**Summary:** The nineteen classic maps are lit by Unreal Engine while still looking like Halo CE, and since 1.3.0 their lightmaps are baked by our own solver at up to eight times Halo CE's resolution. Crisp shadows, lit bases, headlights on the road. Here is how we got there.
**Tags:** multiplayer, maps, lighting

![Blood Gulch, lit by Unreal Engine with Halo CE's colours](/blog-images/lighting-the-classics/blood-gulch.jpg)

*Updated 2026-10-08 for classic maps 1.3.0, CE runtime 1.4.0 and mods
0.18.0. The maps' lightmaps are now computed by a baker of our own instead of
being read out of Halo CE's. That is the first section below; the rest of the
post is the 1.2.0 story it builds on.*

When the classic maps came to Halo Campaign Evolved
[in the alpha](/blog/classic-multiplayer-alpha), they looked like Halo CE
because, in a sense, they *were* Halo CE: every surface carried the light
Bungie baked into it in 2001, painted on like a photograph. That made them
faithful, and it also made them deaf. Campaign Evolved runs on Unreal Engine 5,
which has real lights and real shadows, and none of it could reach the
ground. Switch on a Warthog's headlights and the road stayed dark, while every
player and vehicle in the beam turned glowing white.

The 1.2.0 maps changed that: they keep Halo CE's colours and its soft shade,
but the light on them comes from Unreal Engine. The 1.3.0 maps go one step
further and replace Bungie's lightmaps with ones we bake ourselves. Here's the
difference between the alpha and now, from the same spots:

![Timberland, alpha and now](/blog-images/lighting-the-classics/timberland-alpha-vs-now.jpg)

![Battle Creek, alpha and now](/blog-images/lighting-the-classics/battle-creek-alpha-vs-now.jpg)

![Death Island, alpha and now](/blog-images/lighting-the-classics/death-island-alpha-vs-now.jpg)

## Baking the light ourselves

Halo CE's lightmaps were computed once, in 2001, by a tool in Bungie's
editing kit, and stored in the map files at the resolution a 2001 PC could
afford: a whole base shares a 256-pixel page, so one texel of light covers a
metre of wall. Everything we did in 1.2.0 had to work from those pages. Unreal
drew its own sharp sun shadow on the ground, but the lightmap underneath still
carried Halo CE's blurry copy of the same shadow, and on a Blood Gulch base
roof you could see both: a soft, stepped blob inside a crisp edge.

![A pillar's shadow on a Blood Gulch base roof, 1.2.0 and 1.3.0](/blog-images/lighting-the-classics/blood-gulch-roof-shadow.jpg)

The only real fix was to compute the light again, at a resolution of our
choosing. So we wrote a radiosity solver that does what Bungie's tool did.
The algorithm was recovered by reading the tool's own code: the sky's sun and
fill lights as small grids of directional lights, the ambient light per
cluster, every surface cut into patches that shoot their light at every patch
they can see, patches that split themselves where the light changes quickly,
and shadow rays traced through the map's collision model. The constants are
the tool's own. We know we got it right because at Halo CE's own resolution
our pages match Bungie's texel for texel, to within about 3 percent on most
maps.

Ours runs on every core and is quick: a map that took Bungie's tool three and
a half minutes takes three seconds, which is what lets us run it at up to
eight times the resolution. Blood Gulch, Danger Canyon and Death Island are
solved at eight times, Hang 'Em High and Gephyrophobia at four. The sun and
the sky's fill are evaluated again at every single texel, so a shadow's edge
lands exactly where the geometry puts it.

![Part of a Death Island lightmap page: Halo CE's, and ours at eight times the size](/blog-images/lighting-the-classics/lightmap-resolution.jpg)

With our own pages we could also stop guessing about the sun. The solver
writes two extra pages beside each lightmap: how much of the sun reaches each
texel, and the light the texel holds *without* the sun, which is Halo CE's
ambient, sky fill and bounce. The maps draw that second page as their glow,
and Unreal's sun, shadowed by the invisible copy of the level described
below, draws every sun shadow by itself. The one-metre sun mask of 1.2.0 is
gone, and with it the soft fade along every shadow.

### Rocks that were half dark

Placed objects (boulders, trees, Covenant crates) are lit differently from
the ground in Halo CE: the game samples the lightmap under the object and
shades the whole object with that. In 1.2.0 our materials lit them with
Unreal's sun as well, and the invisible level copy cast shadows across them,
so a rock under a tree came out half dark and the tree's own boughs shadowed
each other in ways Halo CE never drew. The 1.3.0 materials light scenery
exactly the way Halo CE does and leave Unreal's sun off it.

![Danger Canyon's rocks and trees, before and after](/blog-images/lighting-the-classics/danger-canyon-scenery.jpg)

### Lighting the inside of a base

Our first solves left Death Island's bases almost black. The strips of red
and blue light along the pillars are surfaces that emit light in Halo CE, and
in the solver they are supposed to shoot it at the walls. They never did. The
solver stops when the average unshot light across the map drops below a
threshold, and on an island the size of Death Island that average was met
before thirty square metres of strip ever got their turn. Now every emitting
surface shoots first, and the bases glow as they should.

![Inside a Death Island base, 1.2.0 and 1.3.0](/blog-images/lighting-the-classics/death-island-interior.jpg)

Along the way we built the map's placed light fixtures into the solver,
twenty of them on Death Island, only to find that Halo CE's own lightmaps
carry none of their light: the walls beside each fixture are no brighter
than the walls elsewhere. Bungie's tool read those lights and, as far as its
output shows, ignored them. So do we, by default.

Two smaller things fell out of the same comparison. Halo CE lights its sea
floors with a constant colour rather than a solve, so ours do too, and the
water's surface no longer blocks the sun on the way down: a rendered surface
that has no collision, like water or a light strip, is not in a ray's way.

### Gephyrophobia's deck

![Gephyrophobia's deck, 1.2.0 and 1.3.0](/blog-images/lighting-the-classics/gephyrophobia-deck.jpg)

Gephyrophobia's deck was blue-purple in 1.2.0. It should not have been. The
level loader handed Unreal the sun's colour in the wrong colour space, which
kept half the red and green out of every sun on every map. On a near-white
sun nobody noticed; under Gephyrophobia's dusk it tinted the whole bridge.
Fixed in the 0.18.0 mods.

Some of what follows came in last week's 1.1.0 maps (shading baked into
corners, Halo CE's own glass and water, and rocks that had been drawn black),
and the rest came with 1.2.0. It gets technical in places, but you don't need
to know anything about graphics to follow it.

## Why headlights turned everything white

The first clue was in the numbers. A camera in a game works like a real one:
it has an exposure, which decides how much light makes a white pixel. The
campaign sets it the way a real camera would in daylight. The converted maps
didn't. They ran at an exposure meant for a dim room, with a sun of about
8 lux, roughly a living room at dusk. The maps still looked bright, because
the exposure was cranked up to match.

That's fine until something brings its own light. A Warthog's headlights are
modelled on real ones, spot lights of about 32,000 candela. Next to an 8-lux
sun at living-room exposure, they were blindingly bright, so anything they
touched blew out to white.

The fix is to keep the picture and change the units. The level loader now
multiplies the sun and the sky by 256 and turns the camera's exposure down by
the same amount (eight stops). On screen the map looks exactly as it did, but
next to the sun the headlights are no longer hundreds of times too bright.

## Teaching the ground to listen

That stopped the glare, but the ground still ignored the headlights. To see
why, you have to know how a Halo CE map is lit.

In 2001 there was no way to light a whole level in real time, so Halo CE
precomputed it. Its lightmaps record, for every patch of every surface, how
much light lands there: sun, sky, the glow of a lamp, light bouncing off a
nearby wall. The alpha drew each surface as "the texture times its lightmap",
glowing with its own light like a backlit photo. An emissive surface doesn't
react to anything, which is exactly why Unreal's lights slid off it.

Unreal-lit terrain splits that photograph back into parts:

- **The surface itself.** The base colour is what the surface would look like
  in Halo CE's sunlight, and Halo CE's bump maps now feed Unreal's surface
  normals. Every rock and panel has real relief that any light can catch.
- **The sun, from Unreal.** Unreal's sun now lights that surface directly,
  the same way it lights players and vehicles.
- **Everything else, from Halo CE.** Whatever the lightmap has that Unreal's
  sun can't explain (sky light, bounce, coloured lamps) is added back as a
  glow, so the total still matches Halo CE. Since 1.3.0 that glow is a page
  of its own from our solver rather than a guess made from the finished
  lightmap.

Put those back together and the map looks like Halo CE with nothing switched
on. When a headlight, or any other light the game makes, adds light, it now
has a surface to land on:

![Timberland at dusk: a Warthog's headlights before and after](/blog-images/lighting-the-classics/timberland-headlights.jpg)

On the left, the same build with the new lighting switched off: the beam
never reaches the grass, and the Warthog and Ghost glow as if lit from inside.
On the right, the headlights light the grass ahead, and the Warthog and Ghost
are shaded like the dusk around them.

![The headlight beam on the grass, closer](/blog-images/lighting-the-classics/timberland-headlights-detail.jpg)

## Shadows from a level you can't see

For the ground to receive shadows, something has to cast them. Every map now
loads an invisible copy of itself whose only job is to cast shadows. It casts
from both sides of every surface. A one-sided version let the sun shine
through the back of Blood Gulch's cliffs onto the ground in front of them.

That ghost level caused the most baffling bug of the week. Gun scopes and
Warthog windshields started flashing as you moved. It looked like a lighting
problem, but the cause was reflections: the invisible copy sits exactly on top
of the real ground, and Unreal's reflections could see it. We counted frames
of the ammo display: 7 in 16 flashed with the copy present, none without it.
Telling Unreal that the copy is invisible to reflections, ray tracing and
bounced light fixed it.

## Keeping Halo CE's shade

*This is how 1.2.0 did it. The 1.3.0 maps no longer need a sun mask, because
the solver's own pages say exactly where the sun reaches.*

Halo CE's shadows are soft and wide. Its lightmaps were computed at a coarse
resolution and blurred, so the shade under Blood Gulch's bases spreads metres
from the walls. Unreal's shadows are sharp and exact. Let Unreal's sun decide
where shade falls and a lot of Halo CE's character disappears: a passage Halo
CE kept dim comes out sunny.

So every 1.2.0 map carried a **sun mask**: a map of the level, one metre
square per cell, saying how much of Halo CE's sun reached each spot. It was
traced from Halo CE's own lightmap when the map was converted, and Unreal's
sun was filtered through it. Where Halo CE was in shade, the sun stayed off,
for the ground and for anyone standing there. A one-metre grid draws its own
stair-step pattern along shadow edges, so the mask was blended over
neighbouring cells, which turned the steps into a soft fade like Halo CE's.
That fade is what you see on the left of the roof picture above, and it is
why the sun mask had to go once we could solve the light ourselves.

## Corners, and the trouble with triangles

The other thing that makes a place feel solid is darkness where surfaces meet:
the foot of a wall, the inside of a doorway, the gap under a ledge. That's
called ambient occlusion. Halo CE's lightmaps are too coarse to have much of
it, so since 1.1.0 our converter traces it itself, firing rays from every
patch of every surface to see how much of the sky is blocked.

![A Blood Gulch base: the wall's foot and pillars, before and after](/blog-images/lighting-the-classics/blood-gulch-base-detail.jpg)

An early version of the new bake drew Blood Gulch's cliffs as a mesh of dark
triangles. Halo
CE's cliffs are made of large flat facets, and the gentle fold between two
facets blocks a little sky right at the crease. Multiplied in, every fold
became a visible line. The fix was a curve that ignores light occlusion
entirely and only darkens real corners. We also tried smoothing the result,
which washed out the corners people actually notice, so we took it out again.

## The bugs along the way

A few smaller fixes made the difference between "interesting" and "done":

- **Colours read twice.** Some of the textures the loader builds at runtime
  were being colour-corrected on the way in, as if they were photos. A mid-grey
  value of 128 came back as 55, so every early test was too dark, and we spent
  a while tuning around a bug.
- **A softer sun leaked light.** Unreal can soften shadows by making the sun
  wider, and a 3-degree sun did soften the cliffs. It also let light leak
  through thin geometry, which drew bright lines on shaded ground and a halo
  around your gun as you walked. The sun is back to its real size.
- **Black slivers.** At first, wall bases had thin black outlines, exactly
  where Unreal's sharp shadow edge and the converter's coarser shading grid
  disagreed slightly. The materials now look a little way around
  each spot before deciding it's in shade.
- **Gephyrophobia's teleporters.** These aren't lighting, but they shipped in
  the same update. The game only sends you through a teleporter if a Spartan
  fits at the other end. Gephyrophobia's landing spots sat so close to the
  sides of their pads that a Spartan didn't fit, so every pad refused to send.
  The converter now moves cramped landing spots back towards the middle of
  their pads.

To find these quickly, the materials gained a debug view that shows one
lighting layer at a time on screen: the ambient occlusion, the sun mask, Halo
CE's original lightmap and Unreal's part. Most of the bugs above were spotted
in it before anyone guessed at a fix. The solver has its own: run at Halo CE's
resolution it scores every page against Bungie's, and most of the 1.3.0
findings above started as a number that was too high.

## More from the alpha to now

![Prisoner, alpha and now](/blog-images/lighting-the-classics/prisoner-alpha-vs-now.jpg)

![Ice Fields, alpha and now](/blog-images/lighting-the-classics/ice-fields-alpha-vs-now.jpg)

![Hang 'Em High, alpha and now](/blog-images/lighting-the-classics/hang-em-high-alpha-vs-now.jpg)

![Danger Canyon, alpha and now](/blog-images/lighting-the-classics/danger-canyon-alpha-vs-now.jpg)

![Blood Gulch, alpha and now](/blog-images/lighting-the-classics/blood-gulch-alpha-vs-now.jpg)

## Still rough

- Death Island's base interiors are a little darker than Halo CE's.
- The 1.3.0 map packs are larger: lightmaps at eight times the resolution
  cost a few megabytes per map, and more video memory.
- Players standing in deep shade can still look a little brighter than Halo CE
  would draw them, because Unreal's sky light reaches them there.

## Getting it

Open the launcher and, on the **Multiplayer** page, press **Install
multiplayer** again. It fetches the 1.3.0 maps, the 1.4.0 runtime they need and
the 0.18.0 mods. Everyone in your fireteam needs the update, so the maps
match. Then go stand on a Blood Gulch base roof at noon, or walk into a
Death Island base.
