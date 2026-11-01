"""Execute the loader's placed-light settings without a game process."""
from pathlib import Path
import unittest


class PlacedLightsTest(unittest.TestCase):
    def setUp(self):
        try:
            from lupa import LuaRuntime
        except ImportError:
            self.skipTest('optional lupa is required to execute the loader helper offline')
        self.lua = LuaRuntime()
        source = (Path(__file__).resolve().parents[2] /
                  'mods/MJOLNIRLevelLoader/Scripts/main.lua').read_text(encoding='utf-8')
        self.lua.compile(source)
        start = source.index('function Placed.lights(world)')
        helper = source[start:source.index('function Placed.decals(world)', start)]
        self.lua.execute('''
            Current = {actors={}, level={canvas={origin={10,20,30}}}}
            Placed = {}; MOBILITY_MOVABLE = 2
            findObject = function(path) return {} end
            lightScale = function() return 8192 end
            Log = function(message) end
            world = {SpawnActor=function(self, cls, position, rotation)
                local component = {
                    SetIntensity=function(self, v) self.intensity = v end,
                    SetAttenuationRadius=function(self, v) self.radius = v end,
                    SetLightColor=function(self, v) self.colour = v end,
                    SetCastShadows=function(self, v) self.shadows = v end,
                    SetSourceRadius=function(self, v) self.source_radius = v end,
                    SetSpecularScale=function(self, v) self.specular_scale = v end}
                return {LightComponent=component, position=position,
                        IsValid=function() return true end}
            end}
        ''')
        self.lua.execute(helper)

    def test_existing_light_defaults_are_preserved(self):
        self.lua.execute('''
            Current.level.lights = {{pos={1,2,3}, intensity=1.2, radius=900, falloff=2}}
            Placed.lights(world)
            local actor = Current.actors.__light_1
            local c = actor.LightComponent
            assert(c.source_radius == 8 and c.specular_scale == nil)
            assert(c.intensity == 1.2 * 8192 and c.radius == 900)
            assert(c.LightFalloffExponent == 2 and c.IntensityUnits == 0)
            assert(c.shadows and actor.position.X == 11 and actor.position.Z == 33)
        ''')

    def test_authored_emitter_controls_are_applied_without_light_scale(self):
        self.lua.execute('''
            Current.level.lights = {{pos={0,0,0}, intensity=3,
                source_radius=30, specular_scale=0.25}}
            Placed.lights(world)
            local c = Current.actors.__light_1.LightComponent
            assert(c.source_radius == 30 and c.specular_scale == 0.25)
            assert(c.intensity == 3 * 8192 and c.IntensityUnits == 1)
        ''')

    def test_specular_bounds_and_nonnegative_radius(self):
        self.lua.execute('''
            Current.level.lights = {
                {pos={0,0,0}, source_radius=-2, specular_scale=-1},
                {pos={0,0,0}, source_radius=0, specular_scale=4}}
            Placed.lights(world)
            local first = Current.actors.__light_1.LightComponent
            local second = Current.actors.__light_2.LightComponent
            assert(first.source_radius == 0 and first.specular_scale == 0)
            assert(second.source_radius == 0 and second.specular_scale == 1)
        ''')

    def test_invalid_optional_controls_keep_defaults(self):
        self.lua.execute('''
            Current.level.lights = {{pos={0,0,0},
                source_radius='bad', specular_scale='bad'}}
            Placed.lights(world)
            local c = Current.actors.__light_1.LightComponent
            assert(c.source_radius == 8 and c.specular_scale == nil)
        ''')


if __name__ == '__main__':
    unittest.main()
