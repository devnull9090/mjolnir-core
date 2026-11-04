"""Record the foreground game's client rectangle to a silent local MP4.

Uses FFmpeg gdigrab's *desktop* source because PrintWindow / window-DC capture
does not reliably include this game's D3D12 scene.  The caller must keep the
game in front and leave its window fixed. See docs/game_automation.md.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
GAME_EXE = "halocampaignevolved.exe"


def ffmpeg_path(explicit: str | None) -> str:
    if explicit:
        path = Path(explicit).resolve(strict=True)
        if not path.is_file():
            raise ValueError("--ffmpeg must name an executable file")
        return str(path)
    local = ROOT / ".dream-loop" / "video-deps" / "imageio_ffmpeg" / "binaries"
    choices = list(local.glob("ffmpeg-win-*.exe")) if local.is_dir() else []
    if len(choices) == 1:
        return str(choices[0])
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    raise RuntimeError("FFmpeg not found; install imageio-ffmpeg into .dream-loop/video-deps or pass --ffmpeg")


def win32():
    if sys.platform != "win32":
        raise RuntimeError("Foreground client-area capture requires Windows")
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    # Same per-monitor pixel coordinates and UnrealWindow selection used by
    # capture.ps1. Do not focus, restore, or alter the user's windows.
    try:
        user.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        if not user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4)):
            user.SetProcessDPIAware()
    except AttributeError:
        user.SetProcessDPIAware()
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback, wintypes.LPARAM]
    user.EnumWindows.restype = wintypes.BOOL
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetForegroundWindow.restype = wintypes.HWND
    user.IsWindow.argtypes = [wintypes.HWND]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsIconic.argtypes = [wintypes.HWND]
    user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user.GetSystemMetrics.argtypes = [ctypes.c_int]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    return user, kernel, callback


def find_game(user, kernel, callback):
    matches = []

    @callback
    def visit(hwnd, _):
        class_name = ctypes.create_unicode_buffer(256)
        if not user.GetClassNameW(hwnd, class_name, len(class_name)) or class_name.value != "UnrealWindow":
            return True
        if not user.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return True
        try:
            path = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(path))
            if kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length)):
                if Path(path.value).name.casefold() == GAME_EXE:
                    matches.append((hwnd, pid.value))
        finally:
            kernel.CloseHandle(handle)
        return True

    if not user.EnumWindows(visit, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one visible {GAME_EXE} UnrealWindow, found {len(matches)}")
    return matches[0]


def client_rectangle(user, hwnd):
    if not user.IsWindow(hwnd) or not user.IsWindowVisible(hwnd) or user.IsIconic(hwnd):
        raise RuntimeError("Game window is hidden, minimized, or closed")
    if user.GetForegroundWindow() != hwnd:
        raise RuntimeError("Game window is not foreground; bring it to the front before recording")
    rect = wintypes.RECT()
    origin = wintypes.POINT(0, 0)
    if not user.GetClientRect(hwnd, ctypes.byref(rect)) or not user.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise ctypes.WinError(ctypes.get_last_error())
    width, height = rect.right - rect.left, rect.bottom - rect.top
    x, y = origin.x, origin.y
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise RuntimeError(f"Client area must have positive even dimensions for H.264: {width}x{height}")
    left, top = user.GetSystemMetrics(76), user.GetSystemMetrics(77)
    right, bottom = left + user.GetSystemMetrics(78), top + user.GetSystemMetrics(79)
    if x < left or y < top or x + width > right or y + height > bottom:
        raise RuntimeError("Game client extends outside the visible virtual desktop")
    return x, y, width, height


def command(executable, rectangle, fps, duration, encoder, partial):
    x, y, width, height = rectangle
    options = ["-preset", "p4", "-rc", "vbr", "-cq", "19", "-b:v", "0"] if encoder == "h264_nvenc" else ["-preset", "medium", "-crf", "18"]
    return [executable, "-hide_banner", "-loglevel", "error", "-nostats", "-stats_period", "0.25",
            "-f", "gdigrab", "-framerate", str(fps), "-draw_mouse", "0", "-offset_x", str(x),
            "-offset_y", str(y), "-video_size", f"{width}x{height}", "-i", "desktop",
            "-an", "-c:v", encoder, *options, "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-t", str(duration), "-progress", "pipe:1", "-n", str(partial)]


def stop(proc):
    if proc.poll() is not None:
        return
    try:
        proc.stdin.write(b"q\n")
        proc.stdin.flush()
        proc.wait(timeout=10)
    except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
        proc.kill()
        proc.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New MP4 path; existing files are never overwritten")
    parser.add_argument("--duration", type=float, default=10, help="Duration in seconds, >0 and <=3600")
    parser.add_argument("--fps", type=int, default=60, help="Requested capture rate, 1–120")
    parser.add_argument("--encoder", choices=("libx264", "h264_nvenc"), default="libx264")
    parser.add_argument("--ffmpeg", help="Explicit FFmpeg executable; otherwise local video-deps or PATH")
    parser.add_argument("--ready-file", type=Path, help="Create this new JSON file after the first encoded frame")
    parser.add_argument("--start-delay", type=float, default=0, help="Seconds to switch to the game before capture, 0–30")
    args = parser.parse_args()
    if not 0 < args.duration <= 3600 or not 1 <= args.fps <= 120 or not 0 <= args.start_delay <= 30:
        parser.error("duration must be >0 and <=3600; fps 1–120; start-delay 0–30")
    output = args.output.resolve()
    if output.suffix.lower() != ".mp4" or output.exists():
        parser.error("output must be a new .mp4 file")
    if not output.parent.is_dir():
        parser.error("output directory must already exist")
    ready = args.ready_file.resolve() if args.ready_file else None
    if ready and (ready.exists() or not ready.parent.is_dir() or ready == output):
        parser.error("ready file must be new and have an existing parent directory")
    executable = ffmpeg_path(args.ffmpeg)
    if args.start_delay:
        print(f"Switch to the game; recording starts in {args.start_delay:g} seconds.", flush=True)
        time.sleep(args.start_delay)
    user, kernel, callback = win32()
    hwnd, pid = find_game(user, kernel, callback)
    rectangle = client_rectangle(user, hwnd)
    partial = output.with_name(output.stem + ".partial-" + uuid.uuid4().hex + ".mp4")
    log_path = partial.with_suffix(".log")
    started = time.monotonic()
    first_frame = threading.Event()
    errors = []
    progress = {"frames": 0, "out_time_us": 0}
    with log_path.open("x", encoding="utf-8") as log:
        proc = subprocess.Popen(command(executable, rectangle, args.fps, args.duration, args.encoder, partial),
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

        def read_progress():
            for line in iter(proc.stdout.readline, b""):
                if line.startswith(b"frame="):
                    try:
                        progress["frames"] = int(line.partition(b"=")[2])
                        if progress["frames"] > 0 and not first_frame.is_set():
                            if ready:
                                with ready.open("x", encoding="utf-8") as file:
                                    json.dump({"pid": pid, "client": rectangle, "fps": args.fps}, file)
                            first_frame.set()
                            print("VIDEO_READY", flush=True)
                    except (ValueError, OSError) as exc:
                        errors.append(f"Could not write readiness signal: {exc}")
                        return
                elif line.startswith(b"out_time_us="):
                    try:
                        progress["out_time_us"] = int(line.partition(b"=")[2])
                    except ValueError:
                        pass

        thread = threading.Thread(target=read_progress, daemon=True)
        thread.start()
        reason = None
        try:
            while proc.poll() is None:
                try:
                    current = client_rectangle(user, hwnd)
                    if current != rectangle:
                        raise RuntimeError("Game client moved or changed size during recording")
                    if errors:
                        raise RuntimeError(errors[0])
                    if not first_frame.is_set() and time.monotonic() - started > 15:
                        raise RuntimeError("FFmpeg did not encode a frame within 15 seconds")
                except (RuntimeError, OSError) as exc:
                    reason = str(exc)
                    stop(proc)
                    break
                time.sleep(.05)
        except KeyboardInterrupt:
            reason = "Recording interrupted"
            stop(proc)
        thread.join(timeout=2)
        proc.stdin.close()
        proc.stdout.close()
        if reason or proc.returncode != 0 or not first_frame.is_set():
            raise RuntimeError(f"{reason or 'FFmpeg failed'}; partial clip: {partial}; diagnostics: {log_path}")
    # Verify the container can actually decode a frame before publishing it.
    check = subprocess.run([executable, "-v", "error", "-i", str(partial), "-frames:v", "1", "-f", "null", "-"],
                           capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if check.returncode != 0 or not partial.is_file() or partial.stat().st_size == 0:
        raise RuntimeError(f"Recorded clip could not be decoded; partial clip: {partial}; diagnostics: {log_path}")
    os.rename(partial, output)  # On Windows this fails if output appeared concurrently.
    log_path.unlink()
    print(json.dumps({"ok": True, "output": str(output), "fps_requested": args.fps,
                      "duration_requested_s": args.duration, "client": rectangle, "encoder": args.encoder,
                      "frames_encoded": progress["frames"], "media_duration_s": progress["out_time_us"] / 1_000_000,
                      "audio": False, "cursor": False, "capture": "visible desktop pixels"}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"record_game: {exc}", file=sys.stderr)
        sys.exit(1)
