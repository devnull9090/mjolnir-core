"""Exercise the real native worker against an isolated fake Discord pipe.

Run through native/lobby/test-discord.ps1 on Windows. No Discord account,
network connection, game process, or actual discord-ipc-* pipe is touched.
"""

import ctypes
from ctypes import wintypes as wt
import json
import os
from pathlib import Path
import queue
import struct
import sys
import tempfile
import threading
import time


k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateNamedPipeW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.DWORD,
                                wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_void_p]
k32.CreateNamedPipeW.restype = wt.HANDLE
k32.ConnectNamedPipe.argtypes = [wt.HANDLE, ctypes.c_void_p]
k32.ConnectNamedPipe.restype = wt.BOOL
k32.ReadFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD,
                        ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
k32.ReadFile.restype = wt.BOOL
k32.WriteFile.argtypes = k32.ReadFile.argtypes
k32.WriteFile.restype = wt.BOOL
k32.DisconnectNamedPipe.argtypes = [wt.HANDLE]
k32.DisconnectNamedPipe.restype = wt.BOOL
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.CloseHandle.restype = wt.BOOL
k32.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
k32.CreateEventW.restype = wt.HANDLE
k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
k32.WaitForSingleObject.restype = wt.DWORD
k32.GetOverlappedResult.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(wt.DWORD), wt.BOOL]
k32.GetOverlappedResult.restype = wt.BOOL
k32.CancelIoEx.argtypes = [wt.HANDLE, ctypes.c_void_p]
k32.CancelIoEx.restype = wt.BOOL
INVALID_HANDLE = ctypes.c_void_p(-1).value


class Overlapped(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                ("Offset", wt.DWORD), ("OffsetHigh", wt.DWORD), ("hEvent", wt.HANDLE)]


class Pipe:
    def __init__(self, name):
        self.handle = k32.CreateNamedPipeW(name, 3 | 0x40000000, 8, 1, 65536, 65536, 0, None)
        if self.handle == INVALID_HANDLE:
            raise ctypes.WinError(ctypes.get_last_error())
        self.frames = queue.Queue()
        self.errors = queue.Queue()
        self.closed = False
        self.thread = threading.Thread(target=self.read_loop, daemon=True)
        self.thread.start()

    def io(self, writing, buffer, size):
        ov = Overlapped()
        ov.hEvent = k32.CreateEventW(None, True, False, None)
        done = wt.DWORD()
        try:
            fn = k32.WriteFile if writing else k32.ReadFile
            ok = fn(self.handle, buffer, size, ctypes.byref(done), ctypes.byref(ov))
            if not ok and ctypes.get_last_error() == 997:
                if k32.WaitForSingleObject(ov.hEvent, 10000) != 0:
                    k32.CancelIoEx(self.handle, ctypes.byref(ov))
                    k32.GetOverlappedResult(self.handle, ctypes.byref(ov), ctypes.byref(done), True)
                    raise TimeoutError("mock pipe I/O timed out")
                ok = k32.GetOverlappedResult(self.handle, ctypes.byref(ov), ctypes.byref(done), False)
            if not ok:
                raise ctypes.WinError(ctypes.get_last_error())
            return done.value
        finally:
            k32.CloseHandle(ov.hEvent)

    def read_exact(self, length):
        data = bytearray()
        while len(data) < length:
            buf = ctypes.create_string_buffer(length - len(data))
            got = self.io(False, buf, len(buf))
            if not got:
                raise EOFError("pipe closed")
            data += buf.raw[:got]
        return bytes(data)

    def read_loop(self):
        try:
            ov = Overlapped()
            ov.hEvent = k32.CreateEventW(None, True, False, None)
            try:
                if not k32.ConnectNamedPipe(self.handle, ctypes.byref(ov)):
                    error = ctypes.get_last_error()
                    if error == 997:
                        if k32.WaitForSingleObject(ov.hEvent, 10000) != 0:
                            k32.CancelIoEx(self.handle, ctypes.byref(ov))
                            done = wt.DWORD()
                            k32.GetOverlappedResult(self.handle, ctypes.byref(ov), ctypes.byref(done), True)
                            raise TimeoutError("mock pipe connection timed out")
                    elif error != 535:
                        raise ctypes.WinError(error)
            finally:
                k32.CloseHandle(ov.hEvent)
            while not self.closed:
                opcode, length = struct.unpack("<II", self.read_exact(8))
                if length > 65536:
                    raise AssertionError("oversized client frame")
                self.frames.put((opcode, self.read_exact(length)))
        except (OSError, EOFError, AssertionError) as exc:
            if not self.closed:
                self.errors.put(exc)

    def send_raw(self, raw, chunk=0):
        width = chunk or len(raw)
        for offset in range(0, len(raw), width):
            part = raw[offset:offset + width]
            assert self.io(True, part, len(part)) == len(part)
            if chunk:
                time.sleep(.005)

    def send(self, body, opcode=1, chunk=0):
        if not isinstance(body, bytes):
            body = json.dumps(body, separators=(",", ":")).encode()
        self.send_raw(struct.pack("<II", opcode, len(body)) + body, chunk)

    def receive(self, timeout=3):
        try:
            return self.frames.get(timeout=timeout)
        except queue.Empty:
            if not self.errors.empty():
                raise self.errors.get()
            raise AssertionError("timed out waiting for native RPC frame") from None

    def command(self, timeout=3):
        opcode, raw = self.receive(timeout)
        assert opcode == 1, (opcode, raw)
        return json.loads(raw)

    def close(self):
        self.closed = True
        k32.DisconnectNamedPipe(self.handle)
        self.thread.join(1)
        k32.CloseHandle(self.handle)


def until(check, message, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(.02)
    raise AssertionError(message)


def main():
    dll = ctypes.CDLL(str(Path(sys.argv[1]).resolve()))
    dll.mjolnir_discord_test_configure.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
    dll.mjolnir_discord_test_configure.restype = ctypes.c_int
    dll.mjolnir_discord_update.argtypes = [ctypes.c_void_p]
    dll.mjolnir_discord_test_stop.restype = ctypes.c_int
    name = rf"\\?\pipe\mjolnir-discord-test-{os.getpid()}"
    activity = {
        "name": "MJOLNIR Core", "type": 0,
        "details": "Blood Gulch | Team Slayer", "state": "12 kills | 4 deaths",
        "party": {"id": "mjolnir:test-lobby", "size": [6, 16]},
        "secrets": {"join": "mjolnir:v1:test-lobby"},
        "supported_platforms": ["desktop"], "instance": True,
    }
    with tempfile.TemporaryDirectory(prefix="mjolnir-discord-") as temp:
        root = Path(temp)
        snapshot = root / "discord_activity.json"
        pending = root / "pending_join.txt"
        state = root / "discord_status.txt"
        assert dll.mjolnir_discord_test_configure(temp + "\\", name)
        pipe = Pipe(name)

        def update(value=activity):
            snapshot.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
            dll.mjolnir_discord_update(None)

        def handshake():
            opcode, raw = pipe.receive()
            assert opcode == 0
            assert json.loads(raw) == {"v": 1, "client_id": "1533237469259104458"}
            pipe.send({"cmd": "DISPATCH", "evt": "READY", "data": {"v": 1}}, chunk=3)
            assert pipe.command()["evt"] == "ACTIVITY_JOIN"

        def current(expected, acknowledge=True):
            value = pipe.command()
            assert value["cmd"] == "SET_ACTIVITY", value
            assert value["args"]["pid"] == os.getpid(), value
            assert value["args"]["activity"] == expected, value
            if acknowledge:
                pipe.send({"cmd": "SET_ACTIVITY", "evt": None, "data": expected, "nonce": value["nonce"]})
            return value

        try:
            update()
            handshake()
            current(activity)
            print("PASS handshake, subscription, game PID, activity name and fields")

            # Repeated unchanged snapshots refresh the stale timer without
            # sending another SET_ACTIVITY, including across the normal interval.
            for _ in range(3):
                update()
                time.sleep(.1)
            assert pipe.frames.empty(), "unchanged activity was republished"
            changed = dict(activity, state="13 kills | 4 deaths")
            update(changed)
            current(changed)
            print("PASS deduplicated heartbeat and changed activity")

            # Non-JSON ping payload is mirrored verbatim, including >4 KiB.
            ping = bytes(range(256)) * 24
            pipe.send(ping, opcode=3)
            assert pipe.receive() == (4, ping)
            update(changed)
            print("PASS binary PING/PONG")

            invalid = ["", "mjolnir:v1:", "mjolnir:v1:../../escape", "mjolnir:v1:x y",
                       "mjolnir:v1:" + "a" * 65, "mjolnir:v1:abc\ncommand", "mjolnir:v2:abc"]
            for secret in invalid:
                pipe.send({"cmd": "DISPATCH", "evt": "ACTIVITY_JOIN", "data": {"secret": secret}})
            pipe.send(b'{"cmd":"DISPATCH","evt":"ACTIVITY_JOIN","data":{"secret":"mjolnir:v1:abc","secret":"bad"}}')
            pipe.send({"cmd": "SET_ACTIVITY", "evt": "ACTIVITY_JOIN", "data": {"secret": "mjolnir:v1:bad-command"}})
            pipe.send({"cmd": "DISPATCH", "evt": "ACTIVITY_JOIN", "data": {"nested": {"secret": "mjolnir:v1:wrong-depth"}}})
            time.sleep(.15)
            assert not pending.exists()
            update(changed)
            pipe.send({"cmd": "DISPATCH", "evt": "ACTIVITY_JOIN", "data": {"secret": "mjolnir:v1:public-123"}}, chunk=2)
            until(pending.exists, "valid join not queued")
            fields = dict(line.split("=", 1) for line in pending.read_text().splitlines())
            assert fields["lobby"] == "public-123"
            assert abs(int(fields["at"]) - time.time()) < 3
            pending.unlink()
            print("PASS malformed/ambiguous joins rejected, chunked valid join queued atomically")

            # A withdrawn public listing replaces the entire activity so an
            # old secret cannot survive when the host changes to private/full.
            private = {key: value for key, value in changed.items() if key not in ("secrets", "party")}
            update(private)
            current(private)
            print("PASS join secret revoked with replacement activity")

            pipe.send({"cmd": "SET_ACTIVITY", "evt": "ERROR", "data": {"code": 4000, "message": "invalid activity"}})
            until(lambda: state.exists() and "SET_ACTIVITY (code 4000)" in state.read_text(), "RPC rejection missing diagnostics")
            pipe.close()
            pipe = Pipe(name)
            update(private)
            handshake()
            current(private)
            print("PASS Discord rejection diagnostics and retry of unchanged activity")

            # No engine updates: an old map/party must not remain advertised.
            current(None)
            print("PASS stale heartbeat clears presence")
            update(activity)
            current(activity)
            (root / "discord_disabled.txt").write_text("disabled\n")
            current(None)
            pipe.send({"cmd": "DISPATCH", "evt": "ACTIVITY_JOIN", "data": {"secret": "mjolnir:v1:disabled"}})
            time.sleep(.15)
            assert not pending.exists()
            (root / "discord_disabled.txt").unlink()
            update(activity)
            current(activity)
            print("PASS opt-out clears presence, ignores joins, and resumes")

            # Malformed/oversized engine snapshots fail closed.
            for raw in ('{"name":"broken"', '{"x":NaN}', '{"x":"' + 'a' * 5000 + '"}'):
                snapshot.write_text(raw)
                dll.mjolnir_discord_update(None)
                current(None)
                update(activity)
                current(activity)
            print("PASS invalid/oversized activity snapshots clear safely")

            # Corrupt transport frames disconnect. A new server receives the
            # handshake/subscription and most recent snapshot again.
            pipe.send_raw(struct.pack("<II", 1, 65537))
            until(lambda: "disconnected" in state.read_text(), "oversized frame did not disconnect")
            pipe.close()
            pipe = Pipe(name)
            update(activity)
            handshake()
            current(activity)
            print("PASS bounded frame validation and reconnect replay")

            # A client can remain connected yet silently lose a command. Keep
            # Lua's heartbeat fresh while withholding the activity ACK: the
            # same unchanged payload must be replayed on a fresh connection.
            stalled = dict(activity, state="14 kills | 4 deaths")
            update(stalled)
            current(stalled, acknowledge=False)
            deadline = time.monotonic() + 3
            while "acknowledgement timed out" not in state.read_text():
                assert time.monotonic() < deadline, "unacknowledged activity never timed out"
                update(stalled)
                time.sleep(.03)
            pipe.close()
            pipe = Pipe(name)
            update(stalled)
            handshake()
            current(stalled)
            print("PASS withheld activity acknowledgement reconnects and replays unchanged activity")

            # Clearing is not held behind the ACK deadline of an older update.
            update(activity)
            current(activity, acknowledge=False)
            update(None)
            current(None)
            print("PASS urgent clear proceeds while an earlier acknowledgement is pending")
        finally:
            assert dll.mjolnir_discord_test_stop(), "worker did not stop"
            pipe.close()
    print("All native Discord RPC tests passed")


if __name__ == "__main__":
    main()
