// MJOLNIR Blam Console — the native half of mods/MJOLNIRBlamConsole.
//
// Halo Campaign Evolved's simulation DLL still carries the classic Blam
// console: the HS compiler, the function table, `help`, `script_doc`, the
// cheats. Nothing on the Unreal side feeds it text, and the Unreal console
// answers every Blam command with "Command not recognized". This DLL is the
// missing wire.
//
// How it works, and why it is this shape:
//
//   * The Blam engine's shell object owns a queue object at +0x140 whose
//     vtable slot 0 is the drain routine the simulation thread calls once per
//     tick (from the main-loop update). This DLL swaps that one pointer for its
//     own routine, which calls the original and then runs whatever command is
//     waiting. No code is patched, the swap is a single aligned pointer write,
//     and it runs on the thread the engine itself uses for console commands.
//     That matters: compile-and-evaluate reads game state through thread-local
//     storage, so it cannot be called from a foreign thread.
//
//   * The engine's `hs_compile_and_evaluate` survives in the release build with
//     its out-parameters intact (result value and type), a per-type formatter
//     table, the compile-error message and offset globals, and an optional
//     output-buffer global that compile errors are appended to. Together those
//     give a read-back path the stripped `console_printf` no longer provides.
//
//   * UE4SS's Lua loads this DLL with `package.loadlib` and calls the two
//     exports below. The Lua C API is not reachable from here (UE4SS links Lua
//     statically and exports none of it), so the exports take no arguments and
//     the two sides talk through small files next to this DLL, the same way
//     the bridge mod does. The Blam thread never touches a file: `pump`, run
//     from Lua, moves text between the files and an in-memory mailbox.
//
// Every RVA below is specific to one build of HaloSimulation_tag_release.dll.
// `open` refuses to install unless the DLL's PE timestamp matches, so a game
// update degrades to a clear status message rather than a crash. Re-derive
// them with the notes in docs/blam_console.md.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

// ---- Build fingerprint and RVAs: HaloSimulation_tag_release.dll, CU4 ------
#define EXPECTED_TIMESTAMP   0x6a7a740au   // IMAGE_FILE_HEADER.TimeDateStamp
#define RVA_EVALUATE         0x1f8b30      // hs_compile_and_evaluate (inner)
#define RVA_SHELL_PTR        0x2c40028     // the shell object, once created
#define RVA_QUEUE_VTABLE     0x7b0610      // vtable of the queue object at shell+0x140
#define RVA_QUEUE_DRAIN      0xe670        // its slot 0, the per-tick drain
#define RVA_OUT_BUF          0x2c2ef18     // char*: console output capture buffer
#define RVA_OUT_SIZE         0x2c2ef14     // int: its size
#define RVA_ERR_MSG          0x18327f0     // const char*: last compile error
#define RVA_ERR_OFFSET       0x18327f8     // int: its character offset
#define RVA_FORMATTERS       0x81f760      // void (*[])(short type, int value, char*, int)
#define RVA_TYPE_NAMES       0x9aa1c0      // const char*[] value-type names
#define RVA_IN_GAME          0x209a20      // bool game_in_progress(void)
#define RVA_ANCHOR_STRING    0x7f14c0      // "sleep_until"

typedef unsigned char (*evaluate_fn)(uint64_t unused, const char *source, const char *text,
                                     char interactive, uint32_t unused5, int32_t *value_out,
                                     int32_t *type_out);
typedef void (*format_fn)(int16_t type, int32_t value, char *buf, int32_t size);
typedef unsigned char (*in_game_fn)(void);
typedef void (*drain_fn)(void *self);

// ---- State --------------------------------------------------------------------
static uint8_t *g_base;
static evaluate_fn g_evaluate;
static in_game_fn g_in_game;
static drain_fn g_original_drain;
static void **g_vtable_slot;
static char **g_out_buf;
static int32_t *g_out_size;
static const char **g_err_msg;
static int32_t *g_err_offset;
static format_fn *g_formatters;
static const char **g_type_names;

static CRITICAL_SECTION g_lock;
static int g_installed;

// Mailbox. One command in flight at a time is all a console needs.
static char g_pending_text[4096];
static int g_pending_id;
static int g_pending_force;
static int g_has_pending;
static char g_result_text[8192];
static int g_result_id;
static int g_has_result;

// Files, next to this DLL.
static char g_dir[MAX_PATH];
static char g_request_path[MAX_PATH];
static char g_response_path[MAX_PATH];
static char g_status_path[MAX_PATH];
static int g_last_request_id = -1;

// ---- Small helpers --------------------------------------------------------------
static void write_file(const char *path, const char *text) {
    FILE *f = NULL;
    if (fopen_s(&f, path, "wb") == 0 && f) {
        fputs(text, f);
        fclose(f);
    }
}

static void set_status(const char *fmt, ...) {
    char line[1024];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    write_file(g_status_path, line);
}

static void derive_paths(HMODULE self) {
    GetModuleFileNameA(self, g_dir, MAX_PATH);
    char *slash = strrchr(g_dir, '\\');
    if (slash) slash[1] = '\0';
    snprintf(g_request_path, MAX_PATH, "%srequest.txt", g_dir);
    snprintf(g_response_path, MAX_PATH, "%sresponse.txt", g_dir);
    snprintf(g_status_path, MAX_PATH, "%sstatus.txt", g_dir);
}

// ---- The Blam-thread side ------------------------------------------------------

// Run one console line the way the engine's own console would, and describe
// what happened. Runs on the simulation thread, inside the per-tick drain.
static void run_command(const char *text, int force, char *out, size_t out_size) {
    if (!force && !g_in_game()) {
        snprintf(out, out_size, "refused: no game in progress (prefix with ! to force)");
        return;
    }

    // Everything the engine would have printed lands here instead of nowhere.
    char capture[4096];
    capture[0] = '\0';
    char *old_buf = *g_out_buf;
    int32_t old_size = *g_out_size;
    *g_out_buf = capture;
    *g_out_size = (int32_t)sizeof capture;
    *g_err_msg = NULL;
    *g_err_offset = -1;

    int32_t value = -1;
    int32_t type = 0;
    g_evaluate(0, "console_command", text, 1, 0, &value, &type);

    *g_out_buf = old_buf;
    *g_out_size = old_size;

    const char *err = *g_err_msg;
    size_t n = 0;
    if (err && *err) {
        n += (size_t)snprintf(out + n, out_size - n, "error: %s", err);
        if (*g_err_offset >= 0)
            n += (size_t)snprintf(out + n, out_size - n, " (at character %d)", *g_err_offset);
    } else if (type > 4 && g_formatters[type]) {
        char formatted[1024];
        formatted[0] = '\0';
        g_formatters[type]((int16_t)type, value, formatted, (int32_t)sizeof formatted);
        const char *type_name = g_type_names[type] ? g_type_names[type] : "?";
        n += (size_t)snprintf(out + n, out_size - n, "= %s  (%s)", formatted, type_name);
    } else if (type == 4) {
        n += (size_t)snprintf(out + n, out_size - n, "ok");
    } else {
        n += (size_t)snprintf(out + n, out_size - n, "ok (type %d, value %d)", type, value);
    }
    if (capture[0] && n < out_size) {
        // Strip the trailing newline the engine's format adds.
        size_t len = strlen(capture);
        while (len && (capture[len - 1] == '\n' || capture[len - 1] == '\r')) capture[--len] = '\0';
        snprintf(out + n, out_size - n, "\n%s", capture);
    }
}

static void __fastcall hooked_drain(void *self) {
    g_original_drain(self);

    char text[4096];
    int id = 0, force = 0;
    EnterCriticalSection(&g_lock);
    int has = g_has_pending;
    if (has) {
        memcpy(text, g_pending_text, sizeof text);
        id = g_pending_id;
        force = g_pending_force;
        g_has_pending = 0;
    }
    LeaveCriticalSection(&g_lock);
    if (!has) return;

    char result[8192];
    result[0] = '\0';
    run_command(text, force, result, sizeof result);

    EnterCriticalSection(&g_lock);
    memcpy(g_result_text, result, sizeof g_result_text);
    g_result_id = id;
    g_has_result = 1;
    LeaveCriticalSection(&g_lock);
}

// ---- Installation ---------------------------------------------------------------

static int fingerprint_ok(HMODULE sim, char *why, size_t why_size) {
    uint8_t *base = (uint8_t *)sim;
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)base;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + dos->e_lfanew);
    if (nt->FileHeader.TimeDateStamp != EXPECTED_TIMESTAMP) {
        snprintf(why, why_size, "simulation DLL timestamp 0x%08x, expected 0x%08x: the game updated and the offsets need re-deriving",
                 nt->FileHeader.TimeDateStamp, EXPECTED_TIMESTAMP);
        return 0;
    }
    if (strcmp((const char *)(base + RVA_ANCHOR_STRING), "sleep_until") != 0) {
        snprintf(why, why_size, "anchor string not where expected");
        return 0;
    }
    void *slot0 = *(void **)(base + RVA_QUEUE_VTABLE);
    if (slot0 != (void *)(base + RVA_QUEUE_DRAIN) && slot0 != (void *)hooked_drain) {
        snprintf(why, why_size, "queue vtable slot 0 is %p, expected %p", slot0, (void *)(base + RVA_QUEUE_DRAIN));
        return 0;
    }
    return 1;
}

static int install(void) {
    if (g_installed) return 1;
    HMODULE sim = GetModuleHandleA("HaloSimulation_tag_release.dll");
    if (!sim) {
        set_status("error: HaloSimulation_tag_release.dll is not loaded yet");
        return 0;
    }
    char why[512];
    if (!fingerprint_ok(sim, why, sizeof why)) {
        set_status("error: %s", why);
        return 0;
    }
    g_base = (uint8_t *)sim;
    g_evaluate = (evaluate_fn)(g_base + RVA_EVALUATE);
    g_in_game = (in_game_fn)(g_base + RVA_IN_GAME);
    g_vtable_slot = (void **)(g_base + RVA_QUEUE_VTABLE);
    g_out_buf = (char **)(g_base + RVA_OUT_BUF);
    g_out_size = (int32_t *)(g_base + RVA_OUT_SIZE);
    g_err_msg = (const char **)(g_base + RVA_ERR_MSG);
    g_err_offset = (int32_t *)(g_base + RVA_ERR_OFFSET);
    g_formatters = (format_fn *)(g_base + RVA_FORMATTERS);
    g_type_names = (const char **)(g_base + RVA_TYPE_NAMES);

    if (*g_vtable_slot != (void *)hooked_drain) {
        g_original_drain = (drain_fn)(g_base + RVA_QUEUE_DRAIN);
        DWORD old;
        if (!VirtualProtect(g_vtable_slot, sizeof(void *), PAGE_READWRITE, &old)) {
            set_status("error: VirtualProtect failed (%lu)", GetLastError());
            return 0;
        }
        InterlockedExchangePointer(g_vtable_slot, (void *)hooked_drain);
        VirtualProtect(g_vtable_slot, sizeof(void *), old, &old);
    }
    g_installed = 1;
    void *shell = *(void **)(g_base + RVA_SHELL_PTR);
    set_status("ok base=%p shell=%p", (void *)g_base, shell);
    return 1;
}

// ---- Exports, called from Lua through package.loadlib ------------------------------
//
// Both take Lua's `lua_State*` and ignore it, returning 0 results. Lua sees
// them as ordinary functions of no arguments.

__declspec(dllexport) int mjolnir_blam_open(void *L) {
    (void)L;
    install();
    return 0;
}

// Move a new request from request.txt into the mailbox, and a finished result
// from the mailbox into response.txt. Runs on whichever thread Lua calls it
// from; never on the simulation thread.
//
// request.txt:  "<id> <flags>\n<command>"      flags: 1 = run even at the frontend
// response.txt: "<id>\n<text>"
__declspec(dllexport) int mjolnir_blam_pump(void *L) {
    (void)L;
    if (!g_installed && !install()) return 0;

    FILE *f = NULL;
    if (fopen_s(&f, g_request_path, "rb") == 0 && f) {
        char buf[4600];
        size_t n = fread(buf, 1, sizeof buf - 1, f);
        fclose(f);
        buf[n] = '\0';
        int id = -1, flags = 0;
        char *nl = strchr(buf, '\n');
        if (nl && sscanf_s(buf, "%d %d", &id, &flags) >= 1 && id != g_last_request_id) {
            g_last_request_id = id;
            const char *cmd = nl + 1;
            EnterCriticalSection(&g_lock);
            strncpy_s(g_pending_text, sizeof g_pending_text, cmd, _TRUNCATE);
            // The engine's own preprocessor stops at the first newline anyway.
            char *end = strpbrk(g_pending_text, "\r\n");
            if (end) *end = '\0';
            g_pending_id = id;
            g_pending_force = flags & 1;
            g_has_pending = 1;
            LeaveCriticalSection(&g_lock);
        }
    }

    EnterCriticalSection(&g_lock);
    int has = g_has_result;
    int id = g_result_id;
    char text[8192];
    if (has) {
        memcpy(text, g_result_text, sizeof text);
        g_has_result = 0;
    }
    LeaveCriticalSection(&g_lock);
    if (has) {
        char out[8300];
        snprintf(out, sizeof out, "%d\n%s", id, text);
        write_file(g_response_path, out);
    }
    return 0;
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(module);
        InitializeCriticalSection(&g_lock);
        derive_paths(module);
        set_status("loaded, not installed");
    }
    return TRUE;
}
