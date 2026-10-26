MJOLNIR Core — Discord Activity Assets

Upload mjolnir-core-background.png into Activity Assets > Background.
Upload mjolnir-core-cover.png into Activity Assets > Cover Art.
Both files are 1024x576 PNGs (16:9), below the portal's 10MB limit.
The background keeps its central area clear for Discord's UI.

These are Activity shelf/grid assets, separate from Rich Presence Art Assets.
Uploading them does not change the rich presence configuration or app name.
No video preview is included: this repository contains screenshots, not footage.

Source: activity.html. Render using Node and the hub's Puppeteer dependency:
  node assets/discord/render.mjs
The Windows render uses the locally installed Bahnschrift font.
The optional first argument selects a hub checkout with installed dependencies.

Original assets reused without redrawing their content:
  hub/public/logo-transparent.png
  hub/public/blog-images/ce-maps-remastered/blood-gulch-overview.jpg
  hub/public/blog-images/ce-maps-remastered/sidewinder-ring.jpg
Layout/palette follow blog/featured/ce-maps-remastered.html.
Screenshot provenance: blog/2026-10-17-ce-maps-remastered.md.
