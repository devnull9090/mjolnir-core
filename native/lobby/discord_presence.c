/* Discord Rich Presence over the documented local RPC pipe.
 * https://docs.discord.com/developers/topics/rpc
 *
 * This translation unit deliberately has no UE/Steam or Discord SDK dependency.
 * Lua writes discord_activity.json, then calls mjolnir_discord_update on the
 * game thread. Only a bounded file read and a memory copy happen there; a
 * worker owns all pipe I/O. The enclosing lobby DLL is pinned for process life.
 * Join callbacks are data, never commands: the only output is the existing
 * pending_join.txt queue, consumed and checked by the game's normal join flow.
 */
#define _CRT_SECURE_NO_WARNINGS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#include <time.h>

#define DISCORD_APP_ID "1533237469259104458"
#define ACTIVITY_CAP 4096
#define FRAME_CAP 65536
#define PATH_CAP 32768
#ifdef MJOLNIR_DISCORD_TEST
#define UPDATE_MS 150
#define URGENT_MS 40
#define STALE_MS 700
#define RETRY_MS 100
#define ACK_MS 500
#else
#define UPDATE_MS 15000
#define URGENT_MS 4000
#define STALE_MS 15000
#define RETRY_MS 1000
#define ACK_MS 10000
#endif

/* Small strict JSON reader. Tokens retain hierarchy, so text in another field
 * cannot impersonate an event or secret. No allocation or substring matching
 * against untrusted JSON, and no escape decoding into the join identifier. */
typedef struct { int start, end, next; char type; } json_token;
typedef struct {
    const char *text;
    int length, at, count;
    json_token tokens[1024];
} json_doc;

static void json_space(json_doc *d) {
    while (d->at < d->length && (d->text[d->at] == ' ' || d->text[d->at] == '\t' ||
           d->text[d->at] == '\r' || d->text[d->at] == '\n')) ++d->at;
}
static int json_hex(char c) {
    return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
}
static int json_value(json_doc *d, int depth) {
    int token, start;
    char c;
    json_space(d);
    if (depth > 32 || d->at >= d->length || d->count >= 1024) return -1;
    token = d->count++;
    start = d->at;
    c = d->text[d->at++];
    d->tokens[token].start = start;
    d->tokens[token].type = c;
    if (c == '"') {
        int ended = 0;
        while (d->at < d->length) {
            unsigned char ch = (unsigned char)d->text[d->at++];
            if (ch == '"') { ended = 1; break; }
            if (ch < 0x20) return -1;
            if (ch == '\\') {
                if (d->at >= d->length) return -1;
                ch = (unsigned char)d->text[d->at++];
                if (ch == 'u') {
                    for (int i = 0; i < 4; ++i)
                        if (d->at >= d->length || !json_hex(d->text[d->at++])) return -1;
                } else if (!strchr("\"\\/bfnrt", ch)) return -1;
            }
        }
        if (!ended) return -1;
    } else if (c == '{' || c == '[') {
        char end = c == '{' ? '}' : ']';
        json_space(d);
        if (d->at < d->length && d->text[d->at] == end) ++d->at;
        else for (;;) {
            if (c == '{') {
                json_space(d);
                if (d->at >= d->length || d->text[d->at] != '"' || json_value(d, depth + 1) < 0) return -1;
                json_space(d);
                if (d->at >= d->length || d->text[d->at++] != ':') return -1;
            }
            if (json_value(d, depth + 1) < 0) return -1;
            json_space(d);
            if (d->at >= d->length) return -1;
            if (d->text[d->at] == end) { ++d->at; break; }
            if (d->text[d->at++] != ',') return -1;
        }
    } else if (c == 't' || c == 'f' || c == 'n') {
        const char *word = c == 't' ? "true" : c == 'f' ? "false" : "null";
        int length = (int)strlen(word);
        if (d->length - start < length || memcmp(d->text + start, word, (size_t)length)) return -1;
        d->at = start + length;
    } else {
        d->at = start;
        if (d->text[d->at] == '-') ++d->at;
        if (d->at >= d->length) return -1;
        if (d->text[d->at] == '0') ++d->at;
        else {
            if (d->text[d->at] < '1' || d->text[d->at] > '9') return -1;
            while (d->at < d->length && d->text[d->at] >= '0' && d->text[d->at] <= '9') ++d->at;
        }
        if (d->at < d->length && d->text[d->at] == '.') {
            int digits = ++d->at;
            while (d->at < d->length && d->text[d->at] >= '0' && d->text[d->at] <= '9') ++d->at;
            if (d->at == digits) return -1;
        }
        if (d->at < d->length && (d->text[d->at] == 'e' || d->text[d->at] == 'E')) {
            int digits;
            ++d->at;
            if (d->at < d->length && (d->text[d->at] == '+' || d->text[d->at] == '-')) ++d->at;
            digits = d->at;
            while (d->at < d->length && d->text[d->at] >= '0' && d->text[d->at] <= '9') ++d->at;
            if (d->at == digits) return -1;
        }
    }
    d->tokens[token].end = d->at;
    d->tokens[token].next = d->count;
    return token;
}
static int json_parse(json_doc *d, const char *text, int length) {
    d->text = text; d->length = length; d->at = 0; d->count = 0;
    if (json_value(d, 0) < 0) return 0;
    json_space(d);
    return d->at == length;
}
static int json_string_is(const json_doc *d, int t, const char *value) {
    size_t length = strlen(value);
    return t >= 0 && d->tokens[t].type == '"' &&
        d->tokens[t].end - d->tokens[t].start == (int)length + 2 &&
        !memcmp(d->text + d->tokens[t].start + 1, value, length);
}
static int json_field(const json_doc *d, int object, const char *key) {
    int found = -1;
    if (object < 0 || d->tokens[object].type != '{') return -1;
    for (int t = object + 1; t < d->tokens[object].next;) {
        int value = t + 1;
        if (json_string_is(d, t, key)) {
            if (found >= 0) return -1; /* Ambiguous duplicate fields are refused. */
            found = value;
        }
        t = d->tokens[value].next;
    }
    return found;
}
static int join_id(const json_doc *d, int t, char out[65]) {
    static const char prefix[] = "mjolnir:v1:";
    const char *value;
    int length;
    if (t < 0 || d->tokens[t].type != '"') return 0;
    value = d->text + d->tokens[t].start + 1;
    length = d->tokens[t].end - d->tokens[t].start - 2;
    if (length <= (int)sizeof prefix - 1 || length > 64 + (int)sizeof prefix - 1 ||
        memcmp(value, prefix, sizeof prefix - 1)) return 0;
    value += sizeof prefix - 1;
    length -= (int)sizeof prefix - 1;
    for (int i = 0; i < length; ++i) {
        char c = value[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '-')) return 0;
    }
    memcpy(out, value, (size_t)length); out[length] = 0;
    return 1;
}

static INIT_ONCE initialized = INIT_ONCE_STATIC_INIT;
static SRWLOCK snapshot_lock = SRWLOCK_INIT;
static wchar_t activity_path[PATH_CAP], disabled_path[PATH_CAP], status_path[PATH_CAP];
static wchar_t join_path[PATH_CAP], join_tmp_path[PATH_CAP];
static char activity_snapshot[ACTIVITY_CAP] = "null";
static ULONGLONG snapshot_at;
static HANDLE wake_event, worker_thread;
static volatile LONG stopping;
#ifdef MJOLNIR_DISCORD_TEST
static wchar_t test_directory[PATH_CAP], test_pipe[256];
#endif

static BOOL CALLBACK initialize(PINIT_ONCE once, PVOID parameter, PVOID *context) {
    wchar_t directory[PATH_CAP];
    HMODULE self;
    DWORD length;
    wchar_t *slash;
    (void)once; (void)parameter; (void)context;
#ifdef MJOLNIR_DISCORD_TEST
    if (test_directory[0]) wcscpy(directory, test_directory);
    else
#endif
    {
        if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                (LPCWSTR)&initialize, &self)) return FALSE;
        length = GetModuleFileNameW(self, directory, PATH_CAP);
        if (!length || length >= PATH_CAP - 64) return FALSE;
        slash = wcsrchr(directory, L'\\');
        if (!slash) return FALSE;
        slash[1] = 0;
    }
    if (wcslen(directory) >= PATH_CAP - 64) return FALSE;
    swprintf(activity_path, PATH_CAP, L"%lsdiscord_activity.json", directory);
    swprintf(disabled_path, PATH_CAP, L"%lsdiscord_disabled.txt", directory);
    swprintf(status_path, PATH_CAP, L"%lsdiscord_status.txt", directory);
    swprintf(join_path, PATH_CAP, L"%lspending_join.txt", directory);
    swprintf(join_tmp_path, PATH_CAP, L"%lspending_join.discord.tmp", directory);
    wake_event = CreateEventW(NULL, FALSE, FALSE, NULL);
    return wake_event != NULL;
}
static int disabled(void) { return GetFileAttributesW(disabled_path) != INVALID_FILE_ATTRIBUTES; }

/* Status changes only: no account details, raw activity, or join values. */
static void status(const char *message) {
    static char previous[128];
    FILE *f;
    if (!strcmp(previous, message)) return;
    f = _wfopen(status_path, L"wb");
    if (f) { fprintf(f, "%s\n", message); fclose(f); }
    strncpy(previous, message, sizeof previous - 1);
    previous[sizeof previous - 1] = 0;
}
static void queue_join(const char *id) {
    FILE *f;
    int ok;
    if (disabled()) return;
    f = _wfopen(join_tmp_path, L"wb");
    if (!f) { status("join queue write failed"); return; }
    ok = fprintf(f, "lobby=%s\nat=%lld\n", id, (long long)time(NULL)) > 0;
    if (fclose(f)) ok = 0;
    if (!ok || !MoveFileExW(join_tmp_path, join_path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
        DeleteFileW(join_tmp_path);
        status("join queue write failed");
    } else status("join queued for game menu");
}

/* Every read/write is overlapped and bounded. A stalled or absent Discord
 * client never blocks the engine, and a stalled pipe is reconnected. */
static int pipe_io(HANDLE pipe, int writing, void *data, DWORD size, DWORD *done) {
    OVERLAPPED ov;
    BOOL ok;
    memset(&ov, 0, sizeof ov);
    ov.hEvent = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!ov.hEvent) return 0;
    ok = writing ? WriteFile(pipe, data, size, done, &ov) : ReadFile(pipe, data, size, done, &ov);
    if (!ok && GetLastError() == ERROR_IO_PENDING) {
        if (WaitForSingleObject(ov.hEvent, 1000) != WAIT_OBJECT_0) {
            CancelIoEx(pipe, &ov);
            /* The OVERLAPPED must remain alive until cancellation completes. */
            GetOverlappedResult(pipe, &ov, done, TRUE);
            CloseHandle(ov.hEvent);
            return 0;
        }
        ok = GetOverlappedResult(pipe, &ov, done, FALSE);
    }
    CloseHandle(ov.hEvent);
    return ok != FALSE;
}
static int send_frame(HANDLE pipe, uint32_t opcode, const void *body, uint32_t length) {
    unsigned char header[8];
    const unsigned char *bytes = (const unsigned char *)body;
    DWORD sent = 0, offset = 0;
    if (length > FRAME_CAP) return 0;
    memcpy(header, &opcode, 4); memcpy(header + 4, &length, 4);
    while (offset < sizeof header) {
        if (!pipe_io(pipe, 1, header + offset, (DWORD)sizeof header - offset, &sent) || !sent) return 0;
        offset += sent;
    }
    offset = 0;
    while (offset < length) {
        if (!pipe_io(pipe, 1, (void *)(bytes + offset), length - offset, &sent) || !sent) return 0;
        offset += sent;
    }
    return 1;
}
static int send_text(HANDLE pipe, const char *body) { return send_frame(pipe, 1, body, (uint32_t)strlen(body)); }
static HANDLE connect_pipe(void) {
    wchar_t path[256];
    for (int n = 0; n < 10; ++n) {
#ifdef MJOLNIR_DISCORD_TEST
        if (n || !test_pipe[0]) break;
        wcscpy(path, test_pipe);
#else
        swprintf(path, 256, L"\\\\?\\pipe\\discord-ipc-%d", n);
#endif
        HANDLE pipe = CreateFileW(path, GENERIC_READ | GENERIC_WRITE, 0, NULL, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, NULL);
        if (pipe != INVALID_HANDLE_VALUE) return pipe;
    }
    return INVALID_HANDLE_VALUE;
}

static int handle_frame(HANDLE pipe, uint32_t opcode, const char *body, uint32_t length,
                        int *ready, const char *pending_nonce, int *accepted) {
    json_doc d;
    if (opcode == 2) return 0;
    if (opcode == 3) return send_frame(pipe, 4, body, length);
    if (opcode == 4) return 1;
    if (opcode != 1 || !json_parse(&d, body, (int)length) || d.tokens[0].type != '{') return 0;
    if (json_string_is(&d, json_field(&d, 0, "evt"), "ERROR")) {
        int command = json_field(&d, 0, "cmd");
        int code = json_field(&d, json_field(&d, 0, "data"), "code");
        char message[128], number[16] = "unknown";
        if (code >= 0 && d.tokens[code].type >= '0' && d.tokens[code].type <= '9') {
            int size = d.tokens[code].end - d.tokens[code].start;
            if (size > 0 && size < (int)sizeof number) {
                memcpy(number, body + d.tokens[code].start, (size_t)size); number[size] = 0;
            }
        }
        snprintf(message, sizeof message, "Discord rejected %s (code %s)",
            json_string_is(&d, command, "SET_ACTIVITY") ? "SET_ACTIVITY" :
            json_string_is(&d, command, "SUBSCRIBE") ? "ACTIVITY_JOIN subscription" : "RPC request", number);
        status(message);
        /* Disconnect clears any previously accepted presence. Replay after
         * bounded backoff even when the current snapshot never changes. */
        return -1;
    }
    if (pending_nonce[0] && json_string_is(&d, json_field(&d, 0, "cmd"), "SET_ACTIVITY") &&
        json_string_is(&d, json_field(&d, 0, "nonce"), pending_nonce)) *accepted = 1;
    if (!json_string_is(&d, json_field(&d, 0, "cmd"), "DISPATCH")) return 1;
    if (json_string_is(&d, json_field(&d, 0, "evt"), "READY")) {
        if (*ready) return 0;
        *ready = 1;
        status("connected");
        return send_text(pipe, "{\"cmd\":\"SUBSCRIBE\",\"evt\":\"ACTIVITY_JOIN\",\"args\":{},\"nonce\":\"mjolnir-join\"}");
    }
    if (*ready && json_string_is(&d, json_field(&d, 0, "evt"), "ACTIVITY_JOIN")) {
        char id[65];
        int data = json_field(&d, 0, "data");
        if (join_id(&d, json_field(&d, data, "secret"), id)) queue_join(id);
        else status("ignored malformed join invitation");
    }
    return 1;
}
static int receive_frames(HANDLE pipe, unsigned char *buffer, DWORD *used,
                          int *ready, const char *pending_nonce, int *accepted) {
    DWORD available = 0, got = 0;
    if (!PeekNamedPipe(pipe, NULL, 0, NULL, &available, NULL)) return 0;
    if (!available) return 1;
    if (available > FRAME_CAP + 8 - *used) available = FRAME_CAP + 8 - *used;
    if (!available || !pipe_io(pipe, 0, buffer + *used, available, &got) || !got) return 0;
    *used += got;
    while (*used >= 8) {
        uint32_t opcode, length;
        memcpy(&opcode, buffer, 4); memcpy(&length, buffer + 4, 4);
        if (length > FRAME_CAP) return 0;
        if (*used < length + 8) break;
        int handled = handle_frame(pipe, opcode, (const char *)buffer + 8, length, ready, pending_nonce, accepted);
        if (handled <= 0) return handled;
        *used -= length + 8;
        memmove(buffer, buffer + length + 8, *used);
    }
    return 1;
}
static void activity_join(const char *activity, char out[65]) {
    json_doc d;
    out[0] = 0;
    if (json_parse(&d, activity, (int)strlen(activity)))
        join_id(&d, json_field(&d, json_field(&d, 0, "secrets"), "join"), out);
}

static DWORD WINAPI worker(void *parameter) {
    static const char handshake[] = "{\"v\":1,\"client_id\":\"" DISCORD_APP_ID "\"}";
    unsigned char *input = (unsigned char *)HeapAlloc(GetProcessHeap(), 0, FRAME_CAP + 8);
    HANDLE pipe = INVALID_HANDLE_VALUE;
    ULONGLONG retry_at = 0, connected_at = 0, last_send = 0, incomplete_at = 0, pending_at = 0;
    unsigned retry_ms = RETRY_MS, nonce = 0;
    DWORD used = 0;
    int ready = 0;
    char sent[ACTIVITY_CAP] = "", sent_join[65] = "";
    char pending_nonce[40] = "";
    (void)parameter;
    if (!input) { status("worker allocation failed"); return 0; }
    while (!InterlockedCompareExchange(&stopping, 0, 0)) {
        ULONGLONG now = GetTickCount64(), refreshed;
        char wanted[ACTIVITY_CAP], wanted_join[65];
        int preserve_error = 0;
        int off = disabled();
        AcquireSRWLockShared(&snapshot_lock);
        memcpy(wanted, activity_snapshot, sizeof wanted);
        refreshed = snapshot_at;
        ReleaseSRWLockShared(&snapshot_lock);
        if (off || !refreshed || now - refreshed > STALE_MS) strcpy(wanted, "null");
        activity_join(wanted, wanted_join);
        if (pipe == INVALID_HANDLE_VALUE && now >= retry_at) {
            pipe = connect_pipe();
            retry_at = now + retry_ms;
            if (retry_ms < 15000) retry_ms = retry_ms * 2 > 15000 ? 15000 : retry_ms * 2;
            if (pipe != INVALID_HANDLE_VALUE) {
                used = 0; ready = 0; sent[0] = 0; sent_join[0] = 0;
                pending_nonce[0] = 0;
                connected_at = now; last_send = 0; incomplete_at = 0; pending_at = 0;
                if (!send_frame(pipe, 0, handshake, (uint32_t)strlen(handshake))) goto disconnected;
            } else status(off ? "disabled" : "waiting for Discord desktop");
        }
        if (pipe != INVALID_HANDLE_VALUE) {
            int accepted = 0;
            int received = receive_frames(pipe, input, &used, &ready, pending_nonce, &accepted);
            if (received <= 0) { preserve_error = received < 0; goto disconnected; }
            if (!ready && now - connected_at > 10000) goto disconnected;
            if (accepted) {
                pending_at = 0; pending_nonce[0] = 0;
                retry_ms = RETRY_MS;
                status(off ? "disabled" : !strcmp(wanted, "null") ? "presence cleared" : "connected");
            }
            if (pending_at && now - pending_at >= ACK_MS) {
                status("Discord activity acknowledgement timed out; retrying");
                preserve_error = 1;
                goto disconnected;
            }
            if (!used) incomplete_at = 0;
            else if (!incomplete_at) incomplete_at = now;
            else if (now - incomplete_at > 10000) goto disconnected;
            if (ready) {
                int urgent = !strcmp(wanted, "null") || (sent_join[0] && strcmp(sent_join, wanted_join));
                if (strcmp(sent, wanted) && (!last_send || now - last_send >= (unsigned)(urgent ? URGENT_MS : UPDATE_MS))) {
                    char command[ACTIVITY_CAP + 256];
                    snprintf(pending_nonce, sizeof pending_nonce, "mjolnir-%u", ++nonce);
                    int length = snprintf(command, sizeof command,
                        "{\"cmd\":\"SET_ACTIVITY\",\"args\":{\"pid\":%lu,\"activity\":%s},\"nonce\":\"%s\"}",
                        GetCurrentProcessId(), wanted, pending_nonce);
                    if (length < 0 || length >= (int)sizeof command || !send_text(pipe, command)) goto disconnected;
                    strcpy(sent, wanted); strcpy(sent_join, wanted_join); last_send = now;
                    /* New urgent clears/revocations may pass a pending update,
                     * but cannot postpone a stalled client's deadline forever. */
                    if (!pending_at) pending_at = now;
                    if (off) status("disabled");
                    else if (!strcmp(wanted, "null")) status("presence cleared");
                }
            }
        }
        WaitForSingleObject(wake_event, 100);
        continue;
disconnected:
        CloseHandle(pipe); pipe = INVALID_HANDLE_VALUE;
        ready = 0; used = 0;
        retry_at = GetTickCount64() + retry_ms;
        if (!preserve_error) status("disconnected; retrying");
        WaitForSingleObject(wake_event, 100);
    }
    if (pipe != INVALID_HANDLE_VALUE) CloseHandle(pipe);
    HeapFree(GetProcessHeap(), 0, input);
    return 0;
}

/* Exported like the other lobby native functions: no Lua C API, no results. */
__declspec(dllexport) int mjolnir_discord_update(void *L) {
    char snapshot[ACTIVITY_CAP];
    json_doc d;
    FILE *f;
    size_t length = 0;
    int valid = 0;
    (void)L;
    if (!InitOnceExecuteOnce(&initialized, initialize, NULL, NULL)) return 0;
    f = _wfopen(activity_path, L"rb");
    if (f) {
        length = fread(snapshot, 1, sizeof snapshot - 1, f);
        valid = !ferror(f) && fgetc(f) == EOF;
        fclose(f);
    }
    snapshot[length] = 0;
    valid = valid && json_parse(&d, snapshot, (int)length) &&
        (d.tokens[0].type == '{' || (d.tokens[0].type == 'n' && d.tokens[0].end - d.tokens[0].start == 4));
    if (!valid) strcpy(snapshot, "null");
    AcquireSRWLockExclusive(&snapshot_lock);
    strcpy(activity_snapshot, snapshot);
    snapshot_at = GetTickCount64();
    if (!worker_thread) worker_thread = CreateThread(NULL, 0, worker, NULL, 0, NULL);
    ReleaseSRWLockExclusive(&snapshot_lock);
    SetEvent(wake_event);
    return 0;
}

#ifdef MJOLNIR_DISCORD_TEST
/* Test build only. It cannot reach a user's Discord pipe. */
__declspec(dllexport) int mjolnir_discord_test_configure(const wchar_t *directory, const wchar_t *pipe) {
    if (worker_thread || wcslen(directory) >= PATH_CAP - 64 || wcslen(pipe) >= 256) return 0;
    wcscpy(test_directory, directory); wcscpy(test_pipe, pipe);
    return 1;
}
__declspec(dllexport) int mjolnir_discord_test_stop(void) {
    InterlockedExchange(&stopping, 1);
    if (wake_event) SetEvent(wake_event);
    if (worker_thread && WaitForSingleObject(worker_thread, 5000) != WAIT_OBJECT_0) return 0;
    if (worker_thread) CloseHandle(worker_thread);
    if (wake_event) CloseHandle(wake_event);
    worker_thread = NULL; wake_event = NULL;
    return 1;
}
#endif
