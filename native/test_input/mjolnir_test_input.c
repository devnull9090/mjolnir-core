/*
 * MJOLNIR test input: drive the player from inside the game process.
 *
 * Automated tests need keys, mouse buttons and mouse look that reach the player
 * as real input does, without touching the desktop's mouse, keyboard or focus,
 * and with the game in the background. SendInput does neither (tools/mcp/game/
 * input.ps1). This is for tests only: nothing loads it unless a test does, CI
 * does not build it, and it is not in any release.
 *
 * Where input meets the simulation. Each frame the simulation's input_update
 * asks the host for an input source and calls its second virtual method once
 * per local user, passing a 0x134-byte block to fill:
 *
 *     +0x000  u32    device: 0 gamepad, 1 keyboard and mouse
 *     +0x004  u8     key state, indexed by Windows virtual key
 *     +0x104  f32    look x, f32 look y: mouse counts * 0.2618, since last read
 *     +0x11c  u32    mouse buttons: 1 left, 2 middle, 4 right, 8 and 16 thumb
 *     ...            wheel, gamepad state
 *
 * The simulation reads the keyboard from user 0's block only. Everything the
 * player does comes through here. The method (ReadInput below) is in the exe,
 * and it empties the keys and look unless the local player's viewport has focus
 * (a flag the game thread sets each tick), so nothing posted to the window can
 * work in the background: it would be cleared here. This hook runs after that
 * and adds our state to the block, so focus does not matter and the player's
 * own devices are not involved. While the game is in the background the real
 * devices are cleared by that same check, so they cannot disturb a test.
 *
 * How it hooks. ReadInput is found by a byte pattern in the exe's .text, refused
 * unless it matches exactly once. The pattern covers the block's size and the
 * offsets the method clears, so an update that moves them fails here rather
 * than writing to the wrong place. Its one vtable slot is then found in .rdata
 * and swapped. No code is patched, no RVA is baked in. After a game update run
 * native/test_input/build.ps1 -Test; if the pattern no longer matches, find the
 * method again from the simulation's input_update.
 *
 * Lua has no C API here (UE4SS does not export it), so the one export takes no
 * arguments. package.loadlib(dll, "mjolnir_test_input_enable")() starts a worker
 * thread and returns at once: the worker finds the slot, swaps it, and writes
 * the result to input_status.txt in ue4ss\mjolnir-bridge:
 *
 *     ok slot <rva> method <rva>
 *     error <why>
 *
 * It then runs scripts from input_cmd.txt in the same folder. The writer renames
 * a complete file into place; the worker reads it, deletes it, runs it and
 * renames input_ack.txt into place when the script has finished:
 *
 *     id <n>                  first line, echoed in the ack
 *     key <vk> <1|0>          key down or up
 *     button <mask> <1|0>     mouse buttons down or up
 *     look <dx> <dy>          mouse counts, applied at the next read
 *     wait <ms>
 *     release                 everything up
 *     off                     everything up, slot restored, worker stops
 *
 *     id <n> ok reads <n> delivered <n>
 *     id <n> error <why>
 *
 * reads counts the simulation's calls for user 0 since the hook went in, and
 * delivered the calls that carried something of ours, so a caller can tell a
 * simulation that is not running from one that took the input. A key pressed
 * and released between two reads is still delivered once.
 */
#define _CRT_SECURE_NO_WARNINGS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* The input source's ReadInput from its first instruction through the clearing
   of the block when the viewport has no focus. CU4, RVA 0x7b29220. -1 is a
   wildcard: RIP displacements, call targets and the one long jump. */
static const short pattern[] = {
    0x48, 0x8B, 0xC4, 0x48, 0x89, 0x58, 0x20, 0x55, 0x56, 0x57, 0x48, 0x81, 0xEC, 0xF0, 0x03, 0x00,
    0x00, 0xC5, 0xF8, 0x29, 0x70, 0xD8, 0x48, 0x8D, 0x69, 0x08, 0x8B, 0xDA, 0x48, 0x8B, 0xF9, 0x49,
    0x8B, 0xF0, 0xC5, 0xF8, 0x29, 0x78, 0xC8, 0x48, 0x8B, 0xCD, 0xC5, 0x78, 0x29, 0x40, 0xB8, 0xFF,
    0x15, -1,   -1,   -1,   -1,   0x33, 0xD2, 0x48, 0x8D, 0x8C, 0x24, 0x40, 0x01, 0x00, 0x00, 0x41,
    0xB8, 0x34, 0x01, 0x00, 0x00, 0xE8, -1,   -1,   -1,   -1,   0x48, 0x8D, 0x43, 0x04, 0x48, 0x03,
    0xC0, 0x48, 0x8B, 0x1C, 0xC7, 0x48, 0x85, 0xDB, 0x0F, 0x84, -1,   -1,   -1,   -1,   0x48, 0x8D,
    0x7B, 0x18, 0x48, 0x8B, 0xCF, 0xFF, 0x15, -1,   -1,   -1,   -1,   0x80, 0xBB, 0x74, 0x01, 0x00,
    0x00, 0x00, 0x75, 0x2F, 0x48, 0x8D, 0x4B, 0x44, 0x33, 0xD2, 0x41, 0xB8, 0x00, 0x01, 0x00, 0x00,
    0xE8, -1,   -1,   -1,   -1,   0xC5, 0xF9, 0xEF, 0xC0, 0xC5, 0xF8, 0x11, 0x83, 0x44, 0x01, 0x00,
    0x00, 0xC5, 0xF8, 0x11, 0x83, 0x50, 0x01, 0x00, 0x00, 0xC7, 0x83, 0x58, 0x01, 0x00, 0x00, 0x00,
    0x00, 0xF0, 0x42,
};

enum {
    BLOCK_DEVICE = 0x000,
    BLOCK_KEYS = 0x004,
    BLOCK_LOOK_X = 0x104,
    BLOCK_LOOK_Y = 0x108,
    BLOCK_BUTTONS = 0x11c,
    DEVICE_KEYBOARD_MOUSE = 1,
    BUTTONS_ALL = 0x1f,
};

/* What the game itself multiplies a raw mouse count by. */
static const float LOOK_PER_COUNT = 0.2617994f;

typedef char(__fastcall *read_input_t)(void *source, unsigned user, unsigned char *block);

static read_input_t original;
static void **slot;
static const unsigned char *image;

/* Written by the worker, read on the simulation's thread. */
static volatile char key_down[256], key_seen[256];
static volatile LONG buttons_down, buttons_seen;
static volatile LONG look_x, look_y;
static volatile LONG reads, delivered;

static volatile LONG running;
static char dir[MAX_PATH];

static void clear_input(void) {
    for (int vk = 0; vk < 256; vk++) key_down[vk] = key_seen[vk] = 0;
    InterlockedExchange(&buttons_down, 0);
    InterlockedExchange(&buttons_seen, 0);
    InterlockedExchange(&look_x, 0);
    InterlockedExchange(&look_y, 0);
}

/* Add our state to a block ReadInput has filled. Nonzero if there was any. */
static int merge(unsigned char *block) {
    int any = 0;
    for (int vk = 0; vk < 256; vk++) {
        if (key_down[vk] | key_seen[vk]) {
            block[BLOCK_KEYS + vk] = 1;
            key_seen[vk] = 0;
            any = 1;
        }
    }
    const LONG buttons = buttons_down | InterlockedExchange(&buttons_seen, 0);
    if (buttons) {
        *(unsigned *)(block + BLOCK_BUTTONS) |= (unsigned)buttons;
        any = 1;
    }
    const LONG dx = InterlockedExchange(&look_x, 0), dy = InterlockedExchange(&look_y, 0);
    if (dx || dy) {
        *(float *)(block + BLOCK_LOOK_X) += (float)dx * LOOK_PER_COUNT;
        *(float *)(block + BLOCK_LOOK_Y) += (float)dy * LOOK_PER_COUNT;
        any = 1;
    }
    if (any) *(unsigned *)(block + BLOCK_DEVICE) = DEVICE_KEYBOARD_MOUSE;
    return any;
}

static char __fastcall read_input_hook(void *source, unsigned user, unsigned char *block) {
    const char result = original(source, user, block);
    if (user == 0) {
        InterlockedIncrement(&reads);
        if (merge(block)) InterlockedIncrement(&delivered);
    }
    return result;
}

static int matches(const unsigned char *p) {
    for (size_t i = 0; i < sizeof pattern / sizeof pattern[0]; i++)
        if (pattern[i] >= 0 && p[i] != (unsigned char)pattern[i]) return 0;
    return 1;
}

/* Find ReadInput and its vtable slot in a mapped image. Nonzero on success. */
static int resolve(const unsigned char *base, char *why, size_t why_size) {
    const IMAGE_DOS_HEADER *dos = (const IMAGE_DOS_HEADER *)base;
    const IMAGE_NT_HEADERS64 *nt = (const IMAGE_NT_HEADERS64 *)(base + dos->e_lfanew);
    const IMAGE_SECTION_HEADER *sec = IMAGE_FIRST_SECTION(nt);
    const unsigned char *text = NULL, *rdata = NULL;
    size_t text_size = 0, rdata_size = 0;
    for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; i++) {
        if (memcmp(sec[i].Name, ".text", 6) == 0) {
            text = base + sec[i].VirtualAddress;
            text_size = sec[i].Misc.VirtualSize;
        }
        if (memcmp(sec[i].Name, ".rdata", 7) == 0) {
            rdata = base + sec[i].VirtualAddress;
            rdata_size = sec[i].Misc.VirtualSize;
        }
    }
    const size_t n = sizeof pattern / sizeof pattern[0];
    if (!text || !rdata || text_size < n) {
        snprintf(why, why_size, "no .text or .rdata section");
        return 0;
    }
    const unsigned char *found = NULL;
    int count = 0;
    for (const unsigned char *p = text, *end = text + text_size - n; p <= end; p++) {
        if (p[0] == 0x48 && p[1] == 0x8B && p[2] == 0xC4 && matches(p)) {
            found = p;
            if (++count > 1) break;
        }
    }
    if (count != 1) {
        snprintf(why, why_size, "ReadInput %s (game updated?)", count ? "matched twice" : "not found");
        return 0;
    }
    void **pointer = NULL;
    count = 0;
    const void *const *table = (const void *const *)(((size_t)rdata + 7) & ~(size_t)7);
    const size_t entries = (rdata_size - 8) / sizeof(void *);
    for (size_t i = 0; i < entries; i++) {
        if (table[i] == found) {
            pointer = (void **)&table[i];
            count++;
        }
    }
    if (count != 1) {
        snprintf(why, why_size, "%d vtable slots hold ReadInput", count);
        return 0;
    }
    image = base;
    original = (read_input_t)found;
    slot = pointer;
    return 1;
}

static int write_slot(void *value) {
    DWORD protection;
    if (!VirtualProtect(slot, sizeof *slot, PAGE_READWRITE, &protection)) return 0;
    InterlockedExchangePointer(slot, value);
    VirtualProtect(slot, sizeof *slot, protection, &protection);
    return 1;
}

static void find_dir(void) {
    HMODULE self = NULL;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)&find_dir, &self);
    GetModuleFileNameA(self, dir, sizeof dir);
    /* <ue4ss>\Mods\MJOLNIRBridge\native\this.dll -> <ue4ss>\mjolnir-bridge\ */
    for (int up = 0; up < 4; up++) {
        char *slash = strrchr(dir, '\\');
        if (slash) *slash = 0;
    }
    strncat(dir, "\\mjolnir-bridge\\", sizeof dir - strlen(dir) - 1);
}

static void path_of(char *out, size_t size, const char *name) {
    snprintf(out, size, "%s%s", dir, name);
}

/* Whole file or nothing: a reader must never see half of it. */
static void publish(const char *name, const char *text) {
    char temporary[MAX_PATH + 16], final[MAX_PATH + 16];
    path_of(temporary, sizeof temporary, "input_write.tmp");
    path_of(final, sizeof final, name);
    FILE *f = fopen(temporary, "wb");
    if (!f) return;
    fputs(text, f);
    fclose(f);
    MoveFileExA(temporary, final, MOVEFILE_REPLACE_EXISTING);
}

/* Run a script. Writes the ack line; returns nonzero if it ended with `off`. */
static int run_script(char *script, char *ack, size_t ack_size) {
    long id = -1;
    char error[96] = "";
    int off = 0;
    for (char *line = strtok(script, "\r\n"); line && !error[0]; line = strtok(NULL, "\r\n")) {
        char word[16];
        long a = 0, b = 0;
        const int fields = sscanf(line, "%15s %ld %ld", word, &a, &b);
        if (fields < 1) continue;
        if (strcmp(word, "id") == 0 && fields == 2) {
            id = a;
        } else if (strcmp(word, "key") == 0 && fields == 3 && a > 0 && a < 256) {
            if (b) key_seen[a] = 1;
            key_down[a] = b != 0;
        } else if (strcmp(word, "button") == 0 && fields == 3 && a > 0 && (a & ~BUTTONS_ALL) == 0) {
            if (b) {
                InterlockedOr(&buttons_seen, a);
                InterlockedOr(&buttons_down, a);
            } else {
                InterlockedAnd(&buttons_down, ~a);
            }
        } else if (strcmp(word, "look") == 0 && fields == 3) {
            InterlockedExchangeAdd(&look_x, a);
            InterlockedExchangeAdd(&look_y, b);
        } else if (strcmp(word, "wait") == 0 && fields == 2 && a >= 0) {
            Sleep((DWORD)a);
        } else if (strcmp(word, "release") == 0) {
            clear_input();
        } else if (strcmp(word, "off") == 0) {
            off = 1;
        } else {
            snprintf(error, sizeof error, "bad line: %.60s", line);
        }
    }
    if (error[0])
        snprintf(ack, ack_size, "id %ld error %s\n", id, error);
    else
        snprintf(ack, ack_size, "id %ld ok reads %ld delivered %ld\n", id, reads, delivered);
    return off;
}

static DWORD WINAPI worker(void *unused) {
    (void)unused;
    char command[MAX_PATH + 16], status[256], why[160] = "";
    if (!dir[0]) find_dir();
    path_of(command, sizeof command, "input_cmd.txt");
    DeleteFileA(command); /* a script left by a run that never got here */

    if (!slot && !resolve((const unsigned char *)GetModuleHandleW(NULL), why, sizeof why)) {
        snprintf(status, sizeof status, "error %s\n", why);
        publish("input_status.txt", status);
        InterlockedExchange(&running, 0);
        return 0;
    }
    if (!write_slot((void *)read_input_hook)) {
        publish("input_status.txt", "error VirtualProtect refused the vtable slot\n");
        InterlockedExchange(&running, 0);
        return 0;
    }
    snprintf(status, sizeof status, "ok slot 0x%llx method 0x%llx\n",
             (unsigned long long)((const unsigned char *)slot - image),
             (unsigned long long)((const unsigned char *)original - image));
    publish("input_status.txt", status);

    for (int stop = 0; !stop;) {
        Sleep(2);
        if (GetFileAttributesA(command) == INVALID_FILE_ATTRIBUTES) continue;
        char script[8192];
        size_t size = 0;
        FILE *f = fopen(command, "rb");
        if (f) {
            size = fread(script, 1, sizeof script - 1, f);
            fclose(f);
        }
        script[size] = 0;
        DeleteFileA(command);
        char ack[192];
        stop = run_script(script, ack, sizeof ack);
        if (stop) {
            clear_input();
            write_slot((void *)original);
        }
        publish("input_ack.txt", ack);
    }
    InterlockedExchange(&running, 0);
    return 0;
}

/* Safe to call again: a worker already running is left alone. */
__declspec(dllexport) int mjolnir_test_input_enable(void *L) {
    (void)L;
    if (InterlockedCompareExchange(&running, 1, 0) != 0) return 0;
    /* The hook and the worker must outlive the Lua state that loaded this. */
    HMODULE pinned;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN, (LPCSTR)&worker, &pinned);
    HANDLE thread = CreateThread(NULL, 0, worker, NULL, 0, NULL);
    if (thread)
        CloseHandle(thread);
    else
        InterlockedExchange(&running, 0);
    return 0;
}
