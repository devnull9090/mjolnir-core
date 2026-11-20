-- Private rehearsal probe. Samples the actual imported Fluid Flux textures
-- bound to the upper surface. The transient scratch target is released even
-- on a failed check. No source, simulation or level actor is spawned.
local world = mj.world()
local surface
for _, actor in ipairs(FindAllOf("BP_FluxSurface_River_C") or {}) do
    if actor:IsValid() and not actor:IsActorBeingDestroyed()
            and actor:GetFullName():find("PersistentLevel", 1, true) then
        assert(not surface, "Multiple river surfaces")
        surface = actor
    end
end
assert(surface, "Missing river surface")
local state = surface.SimulationState
assert(state and state:IsValid(), "Missing imported Flux state")
assert(state.CaptureOffset == 8350 and state.Resolution.X == 1024 and state.Resolution.Y == 1024,
       "Unexpected upper state layout")

-- Integer texels at their actual centres. Expected values are native FP16
-- channel samples in cm, with stored velocities in their original units.
-- Each row lists label, pixel X and Y, height R, velocity R G B, ground R.
local probes = {
    {"pool",     389, 109, 5888, .06463623, .07165527, 550.5,    15808},
    {"feeder",   346,  30, 6196, .06750488, .30639648,  58,      15008},
    {"sill",     442, 188, 5888, 2.6113281, 5.0820313, 108.1875, 15368},
    {"outflow",  460, 210, 5760, .90673828, 1.4677734, 213.125,  15600},
    {"dry_bank", 309, 106, 6204, 0,         0,           0,      14416},
    {"spring_hill", 323, 3, 6348, 0,        0,           0,      14736},
}
local maps = {
    {"HeightWetMap",         {{"R", 4, 4}}},
    {"VelocityDepthFoamMap", {{"R", 5, .02}, {"G", 6, .02}, {"B", 7, 1}}},
    {"GroundMap",            {{"R", 8, 8}}},
}
local render = StaticFindObject("/Script/Engine.Default__KismetRenderingLibrary")
assert(render and render:IsValid(), "Missing rendering library")
local rt = render:CreateRenderTarget2D(world, 1024, 1024, 6, {R=0,G=0,B=0,A=0}, false, false)
assert(rt and rt:IsValid(), "Failed to create linear RGBA16F readback target")
local ok, message = pcall(function()
    for _, map in ipairs(maps) do
        local texture = state[map[1]]
        assert(texture and texture:IsValid() and texture.SRGB == false, "Missing linear " .. map[1])
        local canvas, size, context = {}, {}, {}
        render:BeginDrawCanvasToRenderTarget(world, rt, canvas, size, context)
        assert(canvas.Canvas and canvas.Canvas:IsValid(), "No readback canvas for " .. map[1])
        -- The installed bridge can return Size alongside Canvas and the draw
        -- context in the second table. End the draw against the actual target.
        local finish = context.RenderTarget and context or size.RenderTarget and size or {RenderTarget=rt}
        local drawn, err = pcall(function()
            canvas.Canvas:K2_DrawTexture(texture, {X=0,Y=0}, {X=1024,Y=1024}, {X=0,Y=0},
                                        {X=1,Y=1}, {R=1,G=1,B=1,A=1}, 0, 0, {X=0,Y=0})
        end)
        render:EndDrawCanvasToRenderTarget(world, finish)
        assert(drawn, tostring(err))
        for _, p in ipairs(probes) do
            local pixel = render:ReadRenderTargetRawPixel(world, rt, p[2], p[3], false)
            print(string.format("HEADWATER_TEXEL %s %s x=%d y=%d rgba=%.6f %.6f %.6f %.6f",
                                p[1], map[1], p[2], p[3], pixel.R, pixel.G, pixel.B, pixel.A))
            for _, channel in ipairs(map[2]) do
                local actual, expected = pixel[channel[1]], p[channel[2]]
                assert(math.abs(actual - expected) <= channel[3],
                       string.format("%s %s.%s measured %.5f expected %.5f",
                                     p[1], map[1], channel[1], actual, expected))
            end
        end
    end
end)
render:ReleaseRenderTarget2D(rt)
assert(ok, tostring(message))
print("HEADWATER_TEXEL_ACCEPTANCE PASS")
