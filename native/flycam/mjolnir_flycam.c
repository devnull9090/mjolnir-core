/*
 * MJOLNIR FlyCam input lock: keep the player still while the camera flies.
 *
 * The player in this game is a unit in the Blam simulation, which reads its
 * own copy of the keyboard and mouse. Nothing at the Unreal layer stops it:
 * DisableInput, SetIgnoreMoveInput and a paused world all leave WASD moving
 * the player, and UI-only input mode (what the chat box uses) would also stop
 * the Unreal key reads the camera itself flies on. So the lock sits where the
 * simulation takes input, and nowhere else.
 *
 * Each frame the simulation's input_update asks the host for an input source
 * and calls its second virtual method, ReadInput, once per local user with a
 * 0x134-byte block to fill (device at +0, key states from +4, mouse look at
 * +0x104, buttons at +0x11c, wheel and gamepad state after). ReadInput starts
 * from an all-zero block, so zero is "nothing pressed" for every field. While
 * locked, the hook below calls the method and then zeroes everything but the
 * device: the player stands still, and Unreal's own PlayerInput, which FlyCam
 * reads for WASD and mouse look, is untouched because it is a separate copy.
 *
 * The method is found by the same byte pattern as native/test_input (refused
 * unless it matches exactly once) and its one vtable slot in .rdata is swapped
 * only while the lock is on. Swapping only while locked lets mjolnir_test_input
 * (tests only, never released) find the untouched slot when it loads later.
 * If test_input already holds the slot, the lock finds the slot by its pointer
 * into that DLL and wraps it, so injected test keys are blanked as well. On
 * unlock the slot is restored only if it still holds this hook. No code is
 * patched and no RVA is baked in; after a game update the pattern either
 * matches or the lock reports why and FlyCam carries on without it.
 *
 * Lua has no C API here (UE4SS does not export it), so the exports take no
 * arguments and return nothing to Lua. Each writes one line to
 * flycam_status.txt beside the DLL, which the Lua side reads:
 *
 *     ok locked slot <rva> method <rva> over <exe|test_input>
 *     ok unlocked
 *     error <why>
 *
 * mjolnir_flycam_beat (no status) is called every frame while FlyCam is on;
 * without a beat for 3 s the lock stops blanking by itself.
 */
#define _CRT_SECURE_NO_WARNINGS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>

/* ReadInput from its first instruction through the clearing of the block when
   the viewport has no focus. CU4, RVA 0x7b29220. -1 is a wildcard: RIP
   displacements, call targets and the one long jump. Keep in step with
   native/test_input/mjolnir_test_input.c. */
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

enum { BLOCK_SIZE = 0x134, BLOCK_AFTER_DEVICE = 4, DEADMAN_MS = 3000 };

typedef char(__fastcall *read_input_t)(void *source, unsigned user, unsigned char *block);

static const unsigned char *image;
static read_input_t method;            /* the exe's ReadInput */
static void **slot;                    /* its vtable slot */
static volatile read_input_t chained;  /* what the slot held when the lock went on */
static volatile LONG locked;
static volatile LONGLONG heartbeat;   /* GetTickCount64 of the last mjolnir_flycam_beat */
static int resolved;                   /* 1 found, -1 failed */
static char resolve_error[160];
static char dir[MAX_PATH];

static char __fastcall read_input_hook(void *source, unsigned user, unsigned char *block) {
    const read_input_t next = chained ? chained : method;
    const char result = next(source, user, block);
    /* A deadman: FlyCam's per-frame tick beats. If the beats stop (a Lua
       error, a tick hook that died with its level), the lock lapses by itself
       rather than leave the player frozen in the next match. */
    if (locked && block && GetTickCount64() - (ULONGLONG)heartbeat < DEADMAN_MS) memset(block + BLOCK_AFTER_DEVICE, 0, BLOCK_SIZE - BLOCK_AFTER_DEVICE);
    return result;
}

static int matches(const unsigned char *p) {
    for (size_t i = 0; i < sizeof pattern / sizeof pattern[0]; i++)
        if (pattern[i] >= 0 && p[i] != (unsigned char)pattern[i]) return 0;
    return 1;
}

static void section(const unsigned char *base, const char *name, const unsigned char **start, size_t *size) {
    const IMAGE_DOS_HEADER *dos = (const IMAGE_DOS_HEADER *)base;
    const IMAGE_NT_HEADERS64 *nt = (const IMAGE_NT_HEADERS64 *)(base + dos->e_lfanew);
    const IMAGE_SECTION_HEADER *sec = IMAGE_FIRST_SECTION(nt);
    for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; i++) {
        if (strncmp((const char *)sec[i].Name, name, IMAGE_SIZEOF_SHORT_NAME) == 0) {
            *start = base + sec[i].VirtualAddress;
            *size = sec[i].Misc.VirtualSize;
            return;
        }
    }
    *start = NULL;
    *size = 0;
}

/* The slots in .rdata holding a pointer in [low, high). */
static int find_slots(const unsigned char *rdata, size_t rdata_size, const void *low, const void *high,
                      void ***first) {
    int count = 0;
    void **table = (void **)(((size_t)rdata + 7) & ~(size_t)7);
    const size_t entries = (rdata_size - 8) / sizeof(void *);
    for (size_t i = 0; i < entries; i++) {
        if (table[i] >= low && table[i] < high) {
            if (!count) *first = &table[i];
            count++;
        }
    }
    return count;
}

/* Find ReadInput and its slot, once. */
static int resolve(void) {
    if (resolved) return resolved > 0;
    resolved = -1;
    const unsigned char *base = (const unsigned char *)GetModuleHandleW(NULL);
    const unsigned char *text, *rdata;
    size_t text_size, rdata_size;
    section(base, ".text", &text, &text_size);
    section(base, ".rdata", &rdata, &rdata_size);
    const size_t n = sizeof pattern / sizeof pattern[0];
    if (!text || !rdata || text_size < n) {
        snprintf(resolve_error, sizeof resolve_error, "no .text or .rdata section");
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
        snprintf(resolve_error, sizeof resolve_error, "ReadInput %s (game updated?)",
                 count ? "matched twice" : "not found");
        return 0;
    }
    void **pointer = NULL;
    count = find_slots(rdata, rdata_size, found, found + 1, &pointer);
    if (count == 0) {
        /* mjolnir_test_input may hold the slot: its hook is the only pointer
           from the exe's .rdata into that DLL. */
        HMODULE test = GetModuleHandleA("mjolnir_test_input.dll");
        if (test) {
            const IMAGE_DOS_HEADER *dos = (const IMAGE_DOS_HEADER *)test;
            const IMAGE_NT_HEADERS64 *nt = (const IMAGE_NT_HEADERS64 *)((const unsigned char *)test + dos->e_lfanew);
            const unsigned char *low = (const unsigned char *)test;
            count = find_slots(rdata, rdata_size, low, low + nt->OptionalHeader.SizeOfImage, &pointer);
        }
    }
    if (count != 1) {
        snprintf(resolve_error, sizeof resolve_error, "%d vtable slots hold ReadInput", count);
        return 0;
    }
    image = base;
    method = (read_input_t)found;
    slot = pointer;
    resolved = 1;
    return 1;
}

static int write_slot(void *value) {
    DWORD protection;
    if (!VirtualProtect(slot, sizeof *slot, PAGE_READWRITE, &protection)) return 0;
    InterlockedExchangePointer(slot, value);
    VirtualProtect(slot, sizeof *slot, protection, &protection);
    return 1;
}

static void status(const char *text) {
    if (!dir[0]) {
        HMODULE self = NULL;
        GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCSTR)&status, &self);
        GetModuleFileNameA(self, dir, sizeof dir);
        char *slash = strrchr(dir, '\\');
        if (slash) slash[1] = 0;
    }
    char temporary[MAX_PATH + 32], final[MAX_PATH + 32];
    snprintf(temporary, sizeof temporary, "%sflycam_status.tmp", dir);
    snprintf(final, sizeof final, "%sflycam_status.txt", dir);
    FILE *f = fopen(temporary, "wb");
    if (!f) return;
    fputs(text, f);
    fputc('\n', f);
    fclose(f);
    MoveFileExA(temporary, final, MOVEFILE_REPLACE_EXISTING);
}

/* Lock the player's input. Safe to call again while locked. */
__declspec(dllexport) int mjolnir_flycam_lock(void *L) {
    (void)L;
    /* The hook must outlive the Lua state that loaded this DLL. */
    HMODULE pinned;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
                       (LPCSTR)&read_input_hook, &pinned);
    if (!resolve()) {
        char text[200];
        snprintf(text, sizeof text, "error %s", resolve_error);
        status(text);
        return 0;
    }
    void *current = *slot;
    if (current != (void *)read_input_hook) {
        chained = (read_input_t)current;
        if (!write_slot((void *)read_input_hook)) {
            status("error VirtualProtect refused the vtable slot");
            return 0;
        }
    }
    InterlockedExchange64(&heartbeat, (LONGLONG)GetTickCount64());
    InterlockedExchange(&locked, 1);
    char text[200];
    snprintf(text, sizeof text, "ok locked slot 0x%llx method 0x%llx over %s",
             (unsigned long long)((const unsigned char *)slot - image),
             (unsigned long long)((const unsigned char *)method - image),
             chained == method ? "exe" : "test_input");
    status(text);
    return 0;
}

/* Keep the lock alive: called every frame while FlyCam is on. */
__declspec(dllexport) int mjolnir_flycam_beat(void *L) {
    (void)L;
    InterlockedExchange64(&heartbeat, (LONGLONG)GetTickCount64());
    return 0;
}

/* Give the player their input back. */
__declspec(dllexport) int mjolnir_flycam_unlock(void *L) {
    (void)L;
    InterlockedExchange(&locked, 0);
    if (resolved > 0 && *slot == (void *)read_input_hook && chained) {
        /* The hook stays callable (the DLL is pinned), so a read already
           inside it finishes normally. */
        write_slot((void *)chained);
    }
    status("ok unlocked");
    return 0;
}
