# Lighting the classics: teaching Unreal Engine to light Halo CE's maps

**Author:** MJOLNIR Core
**Summary:** The nineteen classic maps are now lit by Unreal Engine while still looking like Halo CE. Warthog headlights light the road, vehicles cast shadows, and Blood Gulch's corners have depth. Here is how we got there.
**Tags:** multiplayer, maps, lighting

![Blood Gulch, lit by Unreal Engine with Halo CE's colours](/blog-images/lighting-the-classics/blood-gulch.jpg)

When the classic maps came to Halo Campaign Evolved
[five days ago](/blog/classic-multiplayer-alpha), they looked like Halo CE
because, in a sense, they *were* Halo CE: every surface carried the light
Bungie baked into it in 2001, painted on like a photograph. That made them
faithful, and it also made them deaf. Campaign Evolved runs on Unreal Engine 5,
which has real lights and real shadows, and none of it could reach the
ground. Switch on a Warthog's headlights and the road stayed dark, while every
player and vehicle in the beam turned glowing white.

Today's update (classic maps 1.2.0, CE runtime 1.3.0 and mods 0.17.0) changes
that. The maps keep Halo CE's colours and its soft shade, but the light on them
now comes from Unreal Engine. Here's the difference between the alpha and now,
from the same spots:

![Timberland, alpha and now](/blog-images/lighting-the-classics/timberland-alpha-vs-now.jpg)

![Battle Creek, alpha and now](/blog-images/lighting-the-classics/battle-creek-alpha-vs-now.jpg)

![Death Island, alpha and now](/blog-images/lighting-the-classics/death-island-alpha-vs-now.jpg)

Some of that came in last week's 1.1.0 maps (shading baked into corners,
Halo CE's own glass and water, and rocks that had been drawn black), and the
rest is new today. The rest of this post is the story of the new part: what
was wrong, and the handful of fixes it took. It gets technical in places, but
you don't need to know anything about graphics to follow it.

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
- **Everything else, from Halo CE.** Whatever Halo CE's lightmap has that
  Unreal's sun can't explain (sky light, bounce, coloured lamps) is added back
  as a glow, so the total still matches Halo CE.

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

Halo CE's shadows are soft and wide. Its lightmaps were computed at a coarse
resolution and blurred, so the shade under Blood Gulch's bases spreads metres
from the walls. Unreal's shadows are sharp and exact. Let Unreal's sun decide
where shade falls and a lot of Halo CE's character disappears: a passage Halo
CE kept dim comes out sunny.

So every map now carries a **sun mask**: a map of the level, one metre square
per cell, saying how much of Halo CE's sun reached each spot. It's traced from
Halo CE's own lightmap when the map is converted, and Unreal's sun is filtered
through it. Where Halo CE was in shade, the sun stays off, for the ground and
for anyone standing there. A one-metre grid draws its own stair-step pattern
along shadow edges, so the mask is blended over neighbouring cells, which
turns the steps into a soft fade like Halo CE's.

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
in it before anyone guessed at a fix.

## More from the alpha to now

![Prisoner, alpha and now](/blog-images/lighting-the-classics/prisoner-alpha-vs-now.jpg)

![Ice Fields, alpha and now](/blog-images/lighting-the-classics/ice-fields-alpha-vs-now.jpg)

![Hang 'Em High, alpha and now](/blog-images/lighting-the-classics/hang-em-high-alpha-vs-now.jpg)

![Danger Canyon, alpha and now](/blog-images/lighting-the-classics/danger-canyon-alpha-vs-now.jpg)

![Blood Gulch, alpha and now](/blog-images/lighting-the-classics/blood-gulch-alpha-vs-now.jpg)

## Still rough

- Some cliff shadows have harder edges than Halo CE's.
- Players standing in deep shade can still look a little brighter than Halo CE
  would draw them, because Unreal's sky light reaches them there.

## Getting it

Open the launcher and, on the **Multiplayer** page, press **Install
multiplayer** again. It fetches the 1.2.0 maps, the 1.3.0 runtime they need and
the 0.17.0 mods. Everyone in your fireteam needs the update, so the maps
match. Then go find a Warthog
and wait for dusk on Timberland.
