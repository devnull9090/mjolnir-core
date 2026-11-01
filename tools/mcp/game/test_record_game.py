"""Tests for the recorder's crop and safety checks; never captures a desktop."""
import ctypes
from ctypes import wintypes
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import record_game as record


class FakeUser32:
    def __init__(self):
        self.foreground = 42
        self.visible = True
        self.iconic = False
        self.x, self.y, self.width, self.height = -1280, 20, 1280, 720

    def IsWindow(self, hwnd): return hwnd == 42
    def IsWindowVisible(self, hwnd): return self.visible
    def IsIconic(self, hwnd): return self.iconic
    def GetForegroundWindow(self): return self.foreground
    def GetClientRect(self, hwnd, ptr):
        rect = ctypes.cast(ptr, ctypes.POINTER(wintypes.RECT)).contents
        rect.left, rect.top, rect.right, rect.bottom = 0, 0, self.width, self.height
        return True
    def ClientToScreen(self, hwnd, ptr):
        point = ctypes.cast(ptr, ctypes.POINTER(wintypes.POINT)).contents
        point.x, point.y = self.x, self.y
        return True
    def GetSystemMetrics(self, metric):
        return {76: -1920, 77: 0, 78: 5760, 79: 2160}[metric]


class RecordingSafety(unittest.TestCase):
    def test_uses_physical_client_rectangle_with_negative_monitor_offset(self):
        self.assertEqual(record.client_rectangle(FakeUser32(), 42), (-1280, 20, 1280, 720))

    def test_refuses_background_or_minimized_window(self):
        user = FakeUser32()
        user.foreground = 99
        with self.assertRaisesRegex(RuntimeError, "not foreground"):
            record.client_rectangle(user, 42)
        user.foreground, user.iconic = 42, True
        with self.assertRaisesRegex(RuntimeError, "minimized"):
            record.client_rectangle(user, 42)

    def test_refuses_odd_size_or_offscreen_rectangle(self):
        user = FakeUser32()
        user.width = 1279
        with self.assertRaisesRegex(RuntimeError, "even dimensions"):
            record.client_rectangle(user, 42)
        user.width, user.x = 1280, -2000
        with self.assertRaisesRegex(RuntimeError, "outside"):
            record.client_rectangle(user, 42)

    def test_capture_command_is_local_silent_cursor_free_and_never_overwrites(self):
        args = record.command("ffmpeg.exe", (-1280, 20, 1280, 720), 60, 8,
                              "h264_nvenc", Path("preview.partial.mp4"))
        self.assertEqual(args[args.index("-offset_x") + 1], "-1280")
        self.assertEqual(args[args.index("-offset_y") + 1], "20")
        self.assertEqual(args[args.index("-video_size") + 1], "1280x720")
        self.assertEqual(args[args.index("-i") + 1], "desktop")
        self.assertEqual(args[args.index("-draw_mouse") + 1], "0")
        self.assertEqual(args.count("-i"), 1)
        self.assertIn("-an", args)
        self.assertIn("-n", args)
        self.assertNotIn("-y", args)

    def test_synthetic_recording_waits_for_first_frame_and_publishes_mp4(self):
        try:
            executable = record.ffmpeg_path(None)
        except RuntimeError:
            self.skipTest("FFmpeg is not installed in video-deps or PATH")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "synthetic.mp4"
            ready = Path(directory) / "ready.json"
            original = record.command

            def synthetic(exe, rectangle, fps, duration, encoder, partial):
                args = original(exe, rectangle, fps, duration, encoder, partial)
                start = args.index("-f")
                end = args.index("desktop") + 1
                args[start:end] = ["-re", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30"]
                return args

            result = io.StringIO()
            with mock.patch.object(record, "win32", return_value=(None, None, None)), \
                 mock.patch.object(record, "find_game", return_value=(42, 123)), \
                 mock.patch.object(record, "client_rectangle", return_value=(0, 0, 320, 180)), \
                 mock.patch.object(record, "command", side_effect=synthetic), \
                 mock.patch.object(record.sys, "argv", ["record_game.py", str(output), "--duration", "1", "--fps", "30", "--ffmpeg", executable, "--ready-file", str(ready)]), \
                 redirect_stdout(result):
                record.main()
            self.assertTrue(ready.is_file())
            self.assertGreater(output.stat().st_size, 0)
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ["ready.json", "synthetic.mp4"])
            report = json.loads(result.getvalue().splitlines()[-1])
            self.assertGreater(report["frames_encoded"], 0)
            self.assertGreater(report["media_duration_s"], 0)

    def test_focus_loss_stops_recording_without_publishing_final_file(self):
        try:
            executable = record.ffmpeg_path(None)
        except RuntimeError:
            self.skipTest("FFmpeg is not installed in video-deps or PATH")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "interrupted.mp4"
            original = record.command
            calls = 0

            def synthetic(exe, rectangle, fps, duration, encoder, partial):
                args = original(exe, rectangle, fps, duration, encoder, partial)
                args[args.index("-f"):args.index("desktop") + 1] = [
                    "-re", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30"]
                return args

            def focus_loss(*_):
                nonlocal calls
                calls += 1
                if calls > 10:
                    raise RuntimeError("Game window is not foreground")
                return (0, 0, 320, 180)

            with mock.patch.object(record, "win32", return_value=(None, None, None)), \
                 mock.patch.object(record, "find_game", return_value=(42, 123)), \
                 mock.patch.object(record, "client_rectangle", side_effect=focus_loss), \
                 mock.patch.object(record, "command", side_effect=synthetic), \
                 mock.patch.object(record.sys, "argv", ["record_game.py", str(output), "--duration", "5", "--fps", "30", "--ffmpeg", executable]), \
                 redirect_stdout(io.StringIO()), \
                 self.assertRaisesRegex(RuntimeError, "not foreground"):
                record.main()
            self.assertFalse(output.exists())
            self.assertEqual(len(list(Path(directory).glob("interrupted.partial-*.mp4"))), 1)


if __name__ == "__main__":
    unittest.main()
