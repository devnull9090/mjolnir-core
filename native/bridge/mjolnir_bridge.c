/* MJOLNIR Bridge's named pipe (mods/MJOLNIRBridge/Scripts/main.lua).
 *
 * The bridge used to be files only: a tool wrote request.txt, the mod polled
 * it every 100 ms and wrote response.txt, which the tool polled in turn. That
 * is two disk round trips and a poll on each side per call, one caller at a
 * time, and on a PC with Windows Defender's real-time scan every read of a
 * file just rewritten waits for the scan.
 *
 * This DLL serves \\.\pipe\mjolnir-bridge-<pid> on a thread of its own. A
 * client connects, writes one message in the bridge's wire format and reads
 * one back. The thread keeps the request until Lua takes it
 * (mjolnir_bridge_take, from the bridge's async loop), and writes back what
 * Lua hands it (mjolnir_bridge_reply, from the game thread). Lua never waits
 * on the pipe and the pipe never waits on Lua's thread.
 *
 * The pipe is local only (PIPE_REJECT_REMOTE_CLIENTS) and keeps the default
 * security: the user running the game may write to it, other users may not.
 * One client is served at a time; one connecting meanwhile waits its turn on
 * the next instance, and any after that get ERROR_PIPE_BUSY, which clients
 * wait out.
 *
 * The module pins itself: the server thread runs its code for the life of the
 * process, and a UE4SS mod reload closes the Lua state that loaded it.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../lobby/lua_channel.h"

#define REQUEST_CAP (8u << 20)      /* a request bigger than this is refused */
#define READ_WAIT_MS 5000           /* a client that connects and sends nothing */
#define WRITE_WAIT_MS 5000
#define REPLY_WAIT_MS (10 * 60 * 1000)
#define INSTANCES 4                 /* the one being served and the next */

static SRWLOCK lock = SRWLOCK_INIT;
static char *request;               /* the request waiting for Lua, or NULL */
static size_t request_length;
static LONG request_serial;         /* the client being served now */
static char *reply;                 /* Lua's answer to request_serial */
static size_t reply_length;
static HANDLE reply_event;
static char pipe_name[64];
static INIT_ONCE started = INIT_ONCE_STATIC_INIT;
static int listening;

/* Whether `n` bytes of `buf` hold a whole message: the header lines, "--",
   then "bytes" bytes of body. Sets *total to the message's length. */
static int message_complete(const char *buf, size_t n, size_t *total) {
    const char *end = buf + n;
    const char *sep = NULL;
    for (const char *p = buf; p + 4 <= end; p++)
        if (p[0] == '\n' && p[1] == '-' && p[2] == '-' && p[3] == '\n') {
            sep = p;
            break;
        }
    if (!sep) return 0;
    size_t want = 0;
    for (const char *p = buf; p < sep; p++) {
        if (p == buf || p[-1] == '\n') {
            if ((size_t)(sep - p) > 6 && memcmp(p, "bytes ", 6) == 0) want = (size_t)_strtoui64(p + 6, NULL, 10);
        }
    }
    size_t head = (size_t)(sep - buf) + 4;
    if (want > REQUEST_CAP) return -1;
    *total = head + want;
    return n >= head + want;
}

/* One overlapped read or write that gives up after `wait_ms`. */
static int pipe_io(HANDLE pipe, int writing, void *data, DWORD size, DWORD *done, DWORD wait_ms) {
    OVERLAPPED ov;
    memset(&ov, 0, sizeof ov);
    ov.hEvent = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!ov.hEvent) return 0;
    BOOL ok = writing ? WriteFile(pipe, data, size, done, &ov) : ReadFile(pipe, data, size, done, &ov);
    if (!ok && GetLastError() == ERROR_IO_PENDING) {
        if (WaitForSingleObject(ov.hEvent, wait_ms) != WAIT_OBJECT_0) {
            CancelIoEx(pipe, &ov);
            GetOverlappedResult(pipe, &ov, done, TRUE);
            CloseHandle(ov.hEvent);
            return 0;
        }
        ok = GetOverlappedResult(pipe, &ov, done, FALSE);
    }
    CloseHandle(ov.hEvent);
    return ok != FALSE;
}

/* Whether the client is still there (it closes the pipe when it gives up). */
static int client_alive(HANDLE pipe) {
    DWORD available = 0;
    return PeekNamedPipe(pipe, NULL, 0, NULL, &available, NULL) != FALSE;
}

static void serve_client(HANDLE pipe) {
    size_t cap = 65536, n = 0, total = 0;
    char *buf = (char *)malloc(cap);
    if (!buf) return;
    int complete = 0;
    while (!complete) {
        if (n == cap) {
            if (cap >= REQUEST_CAP + 4096) break;
            char *bigger = (char *)realloc(buf, cap * 2);
            if (!bigger) break;
            buf = bigger;
            cap *= 2;
        }
        DWORD got = 0;
        if (!pipe_io(pipe, 0, buf + n, (DWORD)(cap - n), &got, READ_WAIT_MS) || !got) break;
        n += got;
        complete = message_complete(buf, n, &total);
        if (complete < 0) break;
    }
    if (complete != 1) {
        free(buf);
        return;
    }

    /* Hand it to Lua: a new serial, so a late reply to an earlier client is
       never sent to this one. */
    AcquireSRWLockExclusive(&lock);
    LONG serial = ++request_serial;
    free(request);
    request = buf;
    request_length = total;
    free(reply);
    reply = NULL;
    ReleaseSRWLockExclusive(&lock);

    char *answer = NULL;
    size_t answer_length = 0;
    ULONGLONG deadline = GetTickCount64() + REPLY_WAIT_MS;
    while (!answer && GetTickCount64() < deadline) {
        WaitForSingleObject(reply_event, 250);
        AcquireSRWLockExclusive(&lock);
        if (reply && request_serial == serial) {
            answer = reply;
            answer_length = reply_length;
            reply = NULL;
        }
        ReleaseSRWLockExclusive(&lock);
        if (!answer && !client_alive(pipe)) break;
    }
    /* Nobody took it (the client left, or Lua never answered): drop it. */
    AcquireSRWLockExclusive(&lock);
    if (request_serial == serial) {
        free(request);
        request = NULL;
        request_serial++;
    }
    ReleaseSRWLockExclusive(&lock);
    if (!answer) return;

    size_t sent = 0;
    while (sent < answer_length) {
        DWORD wrote = 0;
        DWORD chunk = answer_length - sent > 65536 ? 65536 : (DWORD)(answer_length - sent);
        if (!pipe_io(pipe, 1, answer + sent, chunk, &wrote, WRITE_WAIT_MS) || !wrote) break;
        sent += wrote;
    }
    free(answer);
}

/* A pipe instance to wait on. The first is made with
   FILE_FLAG_FIRST_PIPE_INSTANCE, so nothing else can have taken the name. */
static HANDLE make_instance(void) {
    static int made;
    DWORD open = PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED | (made ? 0 : FILE_FLAG_FIRST_PIPE_INSTANCE);
    HANDLE pipe = CreateNamedPipeA(pipe_name, open,
                                   PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
                                   INSTANCES, 65536, 65536, 0, NULL);
    if (pipe != INVALID_HANDLE_VALUE) made = 1;
    return pipe;
}

/* Waits for a client on `pipe`; 1 once one is connected. */
static int await_client(HANDLE pipe) {
    OVERLAPPED ov;
    memset(&ov, 0, sizeof ov);
    ov.hEvent = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!ov.hEvent) return 0;
    int connected = 0;
    if (ConnectNamedPipe(pipe, &ov)) {
        connected = 1;
    } else {
        DWORD e = GetLastError();
        if (e == ERROR_PIPE_CONNECTED) {
            connected = 1;
        } else if (e == ERROR_IO_PENDING) {
            DWORD unused = 0;
            WaitForSingleObject(ov.hEvent, INFINITE);
            connected = GetOverlappedResult(pipe, &ov, &unused, FALSE) != FALSE;
        }
    }
    CloseHandle(ov.hEvent);
    return connected;
}

/* Clients one at a time, but never a moment with no instance to connect to:
   the next one is made as soon as a client takes the current one, so a
   caller arriving meanwhile connects and waits its turn instead of finding
   no pipe (and falling back to the files, 2026-11-25). */
static DWORD WINAPI server(LPVOID arg) {
    (void)arg;
    HANDLE pipe = make_instance();
    for (;;) {
        if (pipe == INVALID_HANDLE_VALUE) {
            Sleep(1000);
            pipe = make_instance();
            continue;
        }
        if (!await_client(pipe)) {
            CloseHandle(pipe);
            pipe = make_instance();
            continue;
        }
        HANDLE next = make_instance();
        serve_client(pipe);
        FlushFileBuffers(pipe);
        DisconnectNamedPipe(pipe);
        CloseHandle(pipe);
        pipe = next;
    }
}

static BOOL CALLBACK start(PINIT_ONCE once, PVOID parameter, PVOID *context) {
    (void)once; (void)parameter; (void)context;
    snprintf(pipe_name, sizeof pipe_name, "\\\\.\\pipe\\mjolnir-bridge-%lu", GetCurrentProcessId());
    reply_event = CreateEventW(NULL, FALSE, FALSE, NULL);
    if (!reply_event) return TRUE;
    HANDLE thread = CreateThread(NULL, 0, server, NULL, 0, NULL);
    if (!thread) return TRUE;
    CloseHandle(thread);
    listening = 1;
    return TRUE;
}

/* Lua: mjolnir_bridge_listen() -> the pipe's name ("\\.\pipe\mjolnir-bridge-
   <pid>"), or nil if it could not start. Starts the server once; a reloaded
   mod gets the same pipe. */
__declspec(dllexport) int mjolnir_bridge_listen(void *L) {
    lc_frame f;
    if (!lc_begin(&f, L)) return 0;
    InitOnceExecuteOnce(&started, start, NULL, NULL);
    if (listening) lc_push_text(&f, pipe_name); else lc_push_nil(&f);
    lc_end(&f);
    return 1;
}

/* Lua: mjolnir_bridge_take() -> the waiting request and its serial, or nil.
   The pointer is taken under the lock and pushed after it is released: a Lua
   error inside a push never returns here. */
__declspec(dllexport) int mjolnir_bridge_take(void *L) {
    lc_frame f;
    if (!lc_begin(&f, L)) return 0;
    AcquireSRWLockExclusive(&lock);
    char *text = request;
    size_t length = request_length;
    LONG serial = request_serial;
    request = NULL;
    ReleaseSRWLockExclusive(&lock);
    if (text) {
        lc_push_string(&f, text, length);
        lc_push_integer(&f, serial);
    } else {
        lc_push_nil(&f);
        lc_push_nil(&f);
    }
    free(text);
    lc_end(&f);
    return 2;
}

/* Lua: mjolnir_bridge_reply(serial, message) -> true if that client is still
   waiting for it; false and true when the message did not fit the buffer,
   which has grown to fit it: send it again. */
#define REPLY_CAP (64u << 20)
__declspec(dllexport) int mjolnir_bridge_reply(void *L) {
    static char *buffer;
    static size_t buffer_cap;
    lc_frame f;
    if (!lc_begin(&f, L)) return 0;
    LONG serial = (LONG)lc_take_integer(&f, 1, 0);
    size_t length = 0;
    if (!buffer) {
        buffer_cap = 1u << 20;
        buffer = (char *)malloc(buffer_cap);
    }
    /* lc_take_string removes the value as it copies it, so a message longer
       than the buffer cannot be read again in this call. */
    int ok = buffer && lc_take_string(&f, 1, buffer, buffer_cap, &length);
    if (ok && length >= buffer_cap) {
        int grown = 0;
        if (length < REPLY_CAP) {
            char *bigger = (char *)realloc(buffer, length + 1);
            if (bigger) {
                buffer = bigger;
                buffer_cap = length + 1;
                grown = 1;
            }
        }
        lc_push_bool(&f, 0);
        lc_push_bool(&f, grown);
        lc_end(&f);
        return 2;
    }
    int kept = 0;
    if (ok) {
        char *copy = (char *)malloc(length ? length : 1);
        if (copy) {
            memcpy(copy, buffer, length);
            AcquireSRWLockExclusive(&lock);
            if (request_serial == serial) {
                free(reply);
                reply = copy;
                reply_length = length;
                kept = 1;
                copy = NULL;
            }
            ReleaseSRWLockExclusive(&lock);
            free(copy);
            if (kept) SetEvent(reply_event);
        }
    }
    lc_push_bool(&f, kept);
    lc_end(&f);
    return 1;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        HMODULE pinned;
        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN, (LPCWSTR)h, &pinned);
    }
    return TRUE;
}
