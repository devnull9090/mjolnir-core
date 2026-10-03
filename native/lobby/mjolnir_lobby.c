/*
 * MJOLNIR Lobby, native half.
 *
 * UI: gives a widget made from Lua a click handler. UE4SS's Lua cannot bind
 * a dynamic delegate, and a CommonUI button reports a click only through its
 * OnButtonBaseClicked delegate: the click path is native, so hooking the
 * button's own functions sees nothing (docs/multiplayer_menu.md). This binds
 * that delegate to a function the Lua side can hook, through the engine's own
 * FMulticastDelegateProperty::AddDelegate, which UE4SS exports along with the
 * FName and FWeakObjectPtr constructors it needs.
 *
 * Lua has no C API here (UE4SS does not export it), so requests arrive as a
 * file: package.loadlib(dll, "mjolnir_lobby_bind") reads native\lobby_request.txt,
 * one binding per line,
 *
 *     <widget address> <delegate property> <target address> <target function>
 *
 * addresses in decimal (UObject:GetAddress()), and writes one result line per
 * request to native\lobby_reply.txt. It runs on the game thread, inside the
 * Lua call that asked for it.
 */
#define _CRT_SECURE_NO_WARNINGS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

typedef void *(__fastcall *fname_ctor_t)(void *self, const wchar_t *name, int find_type, void *unused);
typedef void *(__fastcall *fweak_ctor_t)(void *self, const void *object);
typedef void *(__fastcall *get_property_t)(void *object, const wchar_t *name);
typedef void(__fastcall *add_delegate_t)(const void *property, void *delegate_by_ref, void *parent, void *value);

static fname_ctor_t fname_ctor;
static fweak_ctor_t fweak_ctor;
static get_property_t get_property;
static add_delegate_t add_delegate;
static char dir[MAX_PATH];

enum { FNAME_ADD = 1 };

/* The directory this DLL sits in, with a trailing backslash. */
static void find_dir(void) {
    HMODULE self = NULL;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)&find_dir, &self);
    GetModuleFileNameA(self, dir, sizeof dir);
    char *slash = strrchr(dir, '\\');
    if (slash) slash[1] = 0;
}

static int resolve(void) {
    if (add_delegate) return 1;
    HMODULE ue4ss = GetModuleHandleA("UE4SS.dll");
    if (!ue4ss) return 0;
    fname_ctor = (fname_ctor_t)GetProcAddress(ue4ss, "??0FName@Unreal@RC@@QEAA@PEB_WW4EFindName@12@PEAX@Z");
    fweak_ctor = (fweak_ctor_t)GetProcAddress(ue4ss, "??0FWeakObjectPtr@Unreal@RC@@QEAA@PEBVUObject@12@@Z");
    get_property = (get_property_t)GetProcAddress(ue4ss, "?GetPropertyByNameInChain@UObject@Unreal@RC@@QEAAPEAVFProperty@23@PEB_W@Z");
    add_delegate = (add_delegate_t)GetProcAddress(
        ue4ss, "?AddDelegate@FMulticastDelegateProperty@Unreal@RC@@QEBAXV?$TScriptDelegate@UFWeakObjectPtr@Unreal@RC@@@23@PEAVUObject@23@PEAX@Z");
    return fname_ctor && fweak_ctor && get_property && add_delegate;
}

/* One binding; returns a short status for the reply file. */
static const char *bind_one(unsigned long long widget, const char *property, unsigned long long target,
                            const char *function) {
    wchar_t wprop[128], wfunc[128];
    if (!widget || !target) return "null object";
    if (MultiByteToWideChar(CP_UTF8, 0, property, -1, wprop, 128) <= 0) return "bad property name";
    if (MultiByteToWideChar(CP_UTF8, 0, function, -1, wfunc, 128) <= 0) return "bad function name";
    void *prop = get_property((void *)widget, wprop);
    if (!prop) return "no such property";
    /* TScriptDelegate<FWeakObjectPtr>: the object (index, serial) then the
       function's FName (comparison index, number), 16 bytes. Passed by value
       in the C++ signature, which the x64 ABI turns into a pointer to a copy. */
    __declspec(align(8)) unsigned char delegate[16];
    memset(delegate, 0, sizeof delegate);
    fweak_ctor(delegate, (const void *)target);
    fname_ctor(delegate + 8, wfunc, FNAME_ADD, NULL);
    __declspec(align(8)) unsigned char copy[16];
    memcpy(copy, delegate, sizeof copy);
    add_delegate(prop, copy, (void *)widget, NULL);
    return "ok";
}

/*
 * The fireteam cap (docs/fireteam_join_and_cap.md). A co-op fireteam stops at
 * four in three places this can reach from inside the process:
 *
 *   PlayFab lobby   the host asks for maxMemberCount 4, the first field of the
 *                   PFLobbyCreateConfiguration it passes PFMultiplayerCreateAndJoinLobby
 *   PlayFab Party   the network is created with the ini's MaxUserCount 4 and
 *                   MaxDeviceCount 4 (PartyNetworkConfiguration, PartyCreateNewNetwork)
 *   Steam presence  the session made after a PlayFab join is given
 *                   NumPublicConnections = NumPrivateConnections = 4, literals
 *
 * The two PlayFab calls go through the exe's import table, so an IAT slot found
 * by import name swaps each for a wrapper that raises the numbers on the way
 * past (the method tools/pe/lobby_size_hook.py proved from outside). The
 * literals are found by a byte pattern, never a fixed address, and refused if
 * it does not match exactly once. The Unreal GameSession's MaxPlayers is raised
 * from Lua (MJOLNIRLobby). The simulation holds 16 players.
 *
 * package.loadlib(dll, "mjolnir_fireteam_open") reads the size from
 * native\fireteam_request.txt (default 16) and logs to native\fireteam.log.
 * Installing twice is harmless.
 */
#define FIRETEAM_DEFAULT 16
#define FIRETEAM_MAX 32

typedef long(__stdcall *create_join_lobby_t)(void *, void *, void *, void *, void *, void *);
typedef long(__stdcall *create_network_t)(void *, void *, void *, unsigned, void *, void *, void *, void *, void *);

static create_join_lobby_t real_create_join_lobby;
static create_network_t real_create_network;
static unsigned fireteam_size = FIRETEAM_DEFAULT;

static void fireteam_log(const char *fmt, ...) {
    if (!dir[0]) find_dir();
    char path[MAX_PATH];
    snprintf(path, sizeof path, "%sfireteam.log", dir);
    FILE *f = fopen(path, "a");
    if (!f) return;
    SYSTEMTIME t;
    GetLocalTime(&t);
    fprintf(f, "%02d:%02d:%02d ", t.wHour, t.wMinute, t.wSecond);
    va_list args;
    va_start(args, fmt);
    vfprintf(f, fmt, args);
    va_end(args);
    fputc('\n', f);
    fclose(f);
}

static unsigned at_least(unsigned value, unsigned floor) { return value < floor ? floor : value; }

/* PFMultiplayerCreateAndJoinLobby(handle, creator, createConfiguration,
   joinConfiguration, asyncContext, lobby). The configuration is the caller's;
   its first field is maxMemberCount. */
static long __stdcall hook_create_join_lobby(void *handle, void *creator, void *config, void *join, void *context,
                                            void *lobby) {
    if (config) {
        unsigned *max_members = (unsigned *)config;
        fireteam_log("lobby: maxMemberCount %u -> %u", *max_members, at_least(*max_members, fireteam_size));
        *max_members = at_least(*max_members, fireteam_size);
    }
    return real_create_join_lobby(handle, creator, config, join, context, lobby);
}

/* PartyCreateNewNetwork(handle, localUser, networkConfiguration, regionCount,
   regionList, initialInvitationConfiguration, asyncIdentifier,
   networkDescriptor, appliedInitialInvitationIdentifier). PartyNetworkConfiguration:
   maxUserCount, maxDeviceCount, maxUsersPerDeviceCount, maxDevicesPerUserCount,
   maxEndpointsPerDeviceCount, directPeerConnectivityOptions (uint32 each). The
   ini ships 4, 4, 2, 1, 3; the log line confirms the order on a real call. */
static long __stdcall hook_create_network(void *handle, void *user, void *config, unsigned region_count, void *regions,
                                          void *invitation, void *context, void *descriptor, void *applied) {
    if (config) {
        unsigned *c = (unsigned *)config;
        fireteam_log("party: users %u devices %u users/device %u devices/user %u endpoints/device %u (options %u)", c[0],
                     c[1], c[2], c[3], c[4], c[5]);
        c[0] = at_least(c[0], fireteam_size);
        c[1] = at_least(c[1], fireteam_size);
        /* The per-device limits stay as shipped: raising users/device to 4 and
           endpoints/device to 5 made every remote join time out, guests or not. */
        fireteam_log("party: users %u devices %u", c[0], c[1]);
    }
    return real_create_network(handle, user, config, region_count, regions, invitation, context, descriptor, applied);
}

/* The exe's import address table slot for `name` from `dll`, or NULL. */
static void **iat_slot(const char *dll, const char *name) {
    unsigned char *base = (unsigned char *)GetModuleHandleA(NULL);
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_DATA_DIRECTORY imports = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!imports.VirtualAddress) return NULL;
    for (IMAGE_IMPORT_DESCRIPTOR *d = (IMAGE_IMPORT_DESCRIPTOR *)(base + imports.VirtualAddress); d->Name; d++) {
        if (_stricmp((const char *)(base + d->Name), dll) != 0) continue;
        IMAGE_THUNK_DATA64 *names =
            (IMAGE_THUNK_DATA64 *)(base + (d->OriginalFirstThunk ? d->OriginalFirstThunk : d->FirstThunk));
        IMAGE_THUNK_DATA64 *slots = (IMAGE_THUNK_DATA64 *)(base + d->FirstThunk);
        for (; names->u1.AddressOfData; names++, slots++) {
            if (IMAGE_SNAP_BY_ORDINAL64(names->u1.Ordinal)) continue;
            IMAGE_IMPORT_BY_NAME *by_name = (IMAGE_IMPORT_BY_NAME *)(base + names->u1.AddressOfData);
            if (strcmp((const char *)by_name->Name, name) == 0) return (void **)&slots->u1.Function;
        }
    }
    return NULL;
}

/* Point an IAT slot at `hook`, keeping the original once. */
static const char *swap_import(const char *dll, const char *name, void *hook, void **original) {
    void **slot = iat_slot(dll, name);
    if (!slot) return "import not found";
    if (*slot == hook) return "already hooked";
    DWORD old;
    if (!VirtualProtect(slot, sizeof *slot, PAGE_READWRITE, &old)) return "VirtualProtect failed";
    *original = *slot;
    *slot = hook;
    VirtualProtect(slot, sizeof *slot, old, &old);
    return "hooked";
}

/* The presence session's literals: mov dword [rbp-58h], 4 / mov dword [rbp-54h], 4,
   then the flag stores that follow them (exe RVA 0x6f2007b on CU4). */
static const unsigned char PRESENCE[] = {0xC7, 0x45, 0xA8, 0x04, 0x00, 0x00, 0x00, 0xC7, 0x45, 0xAC, 0x04, 0x00,
                                         0x00, 0x00, 0xC6, 0x45, 0xBA, 0x01, 0x66, 0xC7, 0x45, 0xB7, 0x01, 0x01};

static const char *patch_presence(void) {
    unsigned char *base = (unsigned char *)GetModuleHandleA(NULL);
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_SECTION_HEADER *s = IMAGE_FIRST_SECTION(nt);
    unsigned char *found = NULL;
    int hits = 0;
    for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; i++, s++) {
        if (!(s->Characteristics & IMAGE_SCN_MEM_EXECUTE)) continue;
        unsigned char *start = base + s->VirtualAddress, *end = start + s->Misc.VirtualSize - sizeof PRESENCE;
        for (unsigned char *p = start; p <= end; p++) {
            if (p[0] != PRESENCE[0] || p[3] == 0) continue;
            /* Match with either the shipped 4s or an earlier patch in the immediates. */
            if (memcmp(p, PRESENCE, 3) || memcmp(p + 4, PRESENCE + 4, 6) || memcmp(p + 11, PRESENCE + 11, sizeof PRESENCE - 11))
                continue;
            found = p;
            hits++;
        }
    }
    if (hits != 1) {
        static char why[64];
        snprintf(why, sizeof why, "pattern matched %d times, left alone", hits);
        return why;
    }
    if (found[3] == fireteam_size && found[10] == fireteam_size) return "already patched";
    DWORD old;
    if (!VirtualProtect(found, sizeof PRESENCE, PAGE_EXECUTE_READWRITE, &old)) return "VirtualProtect failed";
    found[3] = (unsigned char)fireteam_size;
    found[10] = (unsigned char)fireteam_size;
    VirtualProtect(found, sizeof PRESENCE, old, &old);
    FlushInstructionCache(GetCurrentProcess(), found, sizeof PRESENCE);
    return "patched";
}

__declspec(dllexport) int mjolnir_fireteam_open(void *L) {
    (void)L;
    if (!dir[0]) find_dir();
    char path[MAX_PATH];
    snprintf(path, sizeof path, "%sfireteam_request.txt", dir);
    FILE *req = fopen(path, "r");
    if (req) {
        unsigned size = 0;
        if (fscanf(req, "%u", &size) == 1 && size >= 4 && size <= FIRETEAM_MAX) fireteam_size = size;
        fclose(req);
    }
    fireteam_log("fireteam size %u", fireteam_size);
    fireteam_log("PFMultiplayerCreateAndJoinLobby: %s",
                 swap_import("PlayFabMultiplayerWin.dll", "PFMultiplayerCreateAndJoinLobby",
                             (void *)hook_create_join_lobby, (void **)&real_create_join_lobby));
    fireteam_log("PartyCreateNewNetwork: %s", swap_import("PartyWin.dll", "PartyCreateNewNetwork",
                                                          (void *)hook_create_network, (void **)&real_create_network));
    fireteam_log("presence session literals: %s", patch_presence());
    return 0;
}

__declspec(dllexport) int mjolnir_lobby_bind(void *L) {
    (void)L;
    if (!dir[0]) find_dir();
    char path[MAX_PATH], reply_path[MAX_PATH];
    snprintf(path, sizeof path, "%slobby_request.txt", dir);
    snprintf(reply_path, sizeof reply_path, "%slobby_reply.txt", dir);
    FILE *reply = fopen(reply_path, "w");
    if (!reply) return 0;
    if (!resolve()) {
        fprintf(reply, "error UE4SS exports not found\n");
        fclose(reply);
        return 0;
    }
    FILE *req = fopen(path, "r");
    if (!req) {
        fprintf(reply, "error no request\n");
        fclose(reply);
        return 0;
    }
    char line[512];
    while (fgets(line, sizeof line, req)) {
        unsigned long long widget = 0, target = 0;
        char property[128] = {0}, function[128] = {0};
        if (sscanf(line, "%llu %127s %llu %127s", &widget, property, &target, function) != 4) continue;
        fprintf(reply, "%s %llu %s\n", bind_one(widget, property, target, function), widget, function);
    }
    fclose(req);
    fclose(reply);
    return 0;
}
