"""Execute the loader's delayed sky-capture helper without a game process."""
from pathlib import Path
import unittest


class SkyRecaptureTest(unittest.TestCase):
    def setUp(self):
        try:
            from lupa import LuaRuntime
        except ImportError:
            self.skipTest('optional lupa is required to execute the loader helper offline')
        self.lua = LuaRuntime()
        source = (Path(__file__).resolve().parents[2] /
                  'mods/MJOLNIRLevelLoader/Scripts/main.lua').read_text(encoding='utf-8')
        # Also catches Lua's chunk-local limit without executing the full mod.
        self.lua.compile(source)
        start = source.index('function Current.recaptureSkyAfterDecor(')
        helper = source[start:source.index('local function spawnDecor(', start)]
        clear_start = source.index('local function clearActors()')
        clear_actors = source[clear_start:source.index('\n--------------------------------------------------------------------------------', clear_start)]
        self.lua.execute('''
            Current = {}; pending = {}; logs = {}; captures = 0
            function object(address, name)
                return {valid=true, address=address, name=name,
                        IsValid=function(self) return self.valid end,
                        GetAddress=function(self) return self.address end,
                        GetFullName=function(self) return self.name end,
                        K2_DestroyActor=function(self) self.valid = false end}
            end
            world = object(1, 'World TST'); activeWorld = world
            component = object(3, 'SkyLightComponent TST.sky.LightComponent0')
            component.RecaptureSky = function(self) captures = captures + 1 end
            sky = object(2, 'SkyLight TST.sky'); sky.LightComponent = component
            Current.world = world; Current.actors = {__sky=sky}
            Current.level = {environment={skylight={recapture_after_load=true}}}
            getWorld = function() return activeWorld end
            Log = function(message) logs[#logs+1] = message end
            ExecuteInGameThreadWithDelay = function(ms, callback)
                pending[#pending+1] = {ms=ms, callback=callback}
            end
        ''')
        self.lua.execute(helper)
        # Execute the actual lifecycle used by reload; expose its local only
        # inside this test chunk, rather than manually resetting capture state.
        self.lua.execute(clear_actors + '\nclearActorsForTest = clearActors')

    def test_opt_in_schedules_once_after_decor(self):
        self.lua.execute('''
            assert(Current.recaptureSkyAfterDecor(world))
            assert(#pending == 1 and pending[1].ms == 500 and captures == 0)
            assert(not Current.recaptureSkyAfterDecor(world))
            pending[1].callback()
            assert(captures == 1 and Current.skyRecapture.complete)
            assert(not Current.recaptureSkyAfterDecor(world))
            assert(#pending == 1)
        ''')

    def test_other_maps_remain_unchanged(self):
        for value in ('nil', 'false', '1', "'true'"):
            with self.subTest(value=value):
                self.lua.execute(f'''
                    Current.level.environment.skylight.recapture_after_load = {value}
                    assert(not Current.recaptureSkyAfterDecor(world))
                    assert(#pending == 0 and captures == 0)
                ''')

    def test_world_travel_skips_stale_callback(self):
        self.lua.execute('''
            assert(Current.recaptureSkyAfterDecor(world))
            activeWorld = object(10, 'World OtherMap')
            pending[1].callback()
            assert(captures == 0)
        ''')

    def test_reload_in_same_world_skips_old_request(self):
        self.lua.execute('''
            assert(Current.recaptureSkyAfterDecor(world))
            clearActorsForTest()
            assert(not sky.valid and Current.skyRecapture == nil)
            Current.level = {environment={skylight={recapture_after_load=true}}}
            sky = object(20, 'SkyLight TST.reloadedsky')
            component = object(21, 'SkyLightComponent TST.reloadedsky.LightComponent0')
            component.RecaptureSky = function(self) captures = captures + 1 end
            sky.LightComponent = component
            Current.actors.__sky = sky
            pending[1].callback()
            assert(captures == 0)
            assert(Current.recaptureSkyAfterDecor(world))
            pending[2].callback()
            assert(captures == 1)
        ''')

    def test_reload_after_completed_capture_allows_new_capture(self):
        self.lua.execute('''
            assert(Current.recaptureSkyAfterDecor(world))
            pending[1].callback()
            assert(captures == 1 and Current.skyRecapture.complete)
            clearActorsForTest()
            sky = object(20, 'SkyLight TST.reloadedsky')
            component = object(21, 'SkyLightComponent TST.reloadedsky.LightComponent0')
            component.RecaptureSky = function(self) captures = captures + 1 end
            sky.LightComponent = component
            Current.actors.__sky = sky
            assert(Current.recaptureSkyAfterDecor(world))
            pending[2].callback()
            assert(captures == 2)
        ''')

    def test_replaced_actor_and_destroyed_component_are_not_touched(self):
        self.lua.execute('''
            assert(Current.recaptureSkyAfterDecor(world))
            Current.actors.__sky = object(20, 'SkyLight TST.newsky')
            pending[1].callback()
            assert(captures == 0)
            Current.actors.__sky = sky; Current.skyRecapture = nil
            assert(Current.recaptureSkyAfterDecor(world))
            component.valid = false
            pending[2].callback()
            assert(captures == 0)
        ''')

    def test_same_actor_name_with_different_identity_is_rejected(self):
        self.lua.execute('''
            assert(Current.recaptureSkyAfterDecor(world))
            sky.address = 99
            pending[1].callback()
            assert(captures == 0)
        ''')


if __name__ == '__main__':
    unittest.main()
