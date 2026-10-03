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
#include <intrin.h>

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
static void track_lobby(void *lobby, const char *how);
static int in_image(const void *p);
static void drop_held_world(const char *why);

/* The exe return addresses on the caller's stack, as " rva rva ...": who asked. */
#define CALLER_STACK (24 * 12 + 1)
static void caller_stack(char *line) {
    void *frames[24];
    USHORT n = RtlCaptureStackBackTrace(1, 24, frames, NULL);
    unsigned char *base = (unsigned char *)GetModuleHandleA(NULL);
    size_t at = 0;
    for (USHORT i = 0; i < n && at + 12 < CALLER_STACK; i++) {
        if (!in_image(frames[i])) continue;
        at += (size_t)snprintf(line + at, CALLER_STACK - at, " %llx", (unsigned long long)((unsigned char *)frames[i] - base));
    }
    line[at] = 0;
}

static long __stdcall hook_create_join_lobby(void *handle, void *creator, void *config, void *join, void *context,
                                            void *lobby) {
    if (config) {
        unsigned *max_members = (unsigned *)config;
        fireteam_log("lobby: maxMemberCount %u -> %u", *max_members, at_least(*max_members, fireteam_size));
        *max_members = at_least(*max_members, fireteam_size);
    }
    /* PFLobbyCreateConfiguration: maxMemberCount, ownerMigrationPolicy,
       accessPolicy, searchPropertyCount (+12), keys (+16), values (+24),
       lobbyPropertyCount (+32), keys (+40), values (+48). */
    if (config) {
        __try {
            const unsigned char *c = (const unsigned char *)config;
            fireteam_log("lobby: create, access policy %u, owner migration %u", *(const unsigned *)(c + 8),
                         *(const unsigned *)(c + 4));
            for (int group = 0; group < 2; group++) {
                unsigned count = *(const unsigned *)(c + 12 + group * 20);
                const char *const *keys = *(const char *const *const *)(c + 16 + group * 24);
                const char *const *values = *(const char *const *const *)(c + 24 + group * 24);
                for (unsigned i = 0; keys && i < count && i < 64; i++)
                    fireteam_log("lobby: create %s property %s = %.200s", group ? "lobby" : "search",
                                 keys[i] ? keys[i] : "?", values && values[i] ? values[i] : "");
            }
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            fireteam_log("lobby: create configuration unreadable");
        }
    }
    long hr = real_create_join_lobby(handle, creator, config, join, context, lobby);
    if (hr >= 0 && lobby) track_lobby(*(void **)lobby, "created");
    return hr;
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

/*
 * The games list (docs/multiplayer_servers.md). Three things the Lua side
 * cannot do itself:
 *
 *   the lobby's connection string  PFLobbyGetConnectionString on the lobby the
 *                                  game created or joined last, tracked by the
 *                                  import hooks
 *   joining by one                 the game's own Steam "join game" handler
 *                                  (GameRichPresenceJoinRequested_t), fed the
 *                                  string on the online thread. A connect
 *                                  string without "SteamConnectIP=" goes to
 *                                  PlayFab whole as CONNECTIONSTRING, the way
 *                                  a Steam invite's does
 *   the hub                        HTTPS on a worker thread, with the key the
 *                                  launcher paired
 *
 * Requests arrive as files, like the others: native\join_request.txt,
 * native\hub_request.txt. Replies: native\lobby_connection.txt,
 * native\join_reply.txt, native\hub_reply_<id>.txt.
 */
typedef long(__stdcall *join_lobby_t)(void *, void *, const char *, void *, void *, void *);
typedef long(__stdcall *lobby_leave_t)(void *, void *, void *);
typedef long(__stdcall *get_connection_string_t)(void *, const char **);
typedef long(__stdcall *get_membership_lock_t)(void *, int *);
typedef long(__stdcall *get_max_members_t)(void *, unsigned *);

static join_lobby_t real_join_lobby;
static lobby_leave_t real_lobby_leave;
static void *volatile current_lobby;

static void track_lobby(void *lobby, const char *how) {
    current_lobby = lobby;
    fireteam_log("lobby: %s %p", how, lobby);
}

/* PFMultiplayerJoinLobby(handle, newMember, connectionString, joinConfiguration,
   asyncContext, lobby). */
static long __stdcall hook_join_lobby(void *handle, void *member, const char *connection, void *config, void *context,
                                     void *lobby) {
    fireteam_log("lobby: joining by a connection string of %u characters",
                 connection ? (unsigned)strlen(connection) : 0u);
    long hr = real_join_lobby(handle, member, connection, config, context, lobby);
    fireteam_log("lobby: PFMultiplayerJoinLobby returned 0x%08lx", (unsigned long)hr);
    if (hr >= 0 && lobby) track_lobby(*(void **)lobby, "joined");
    return hr;
}

/* PFLobbyLeave(lobby, localUser, asyncContext). A match started with the host
   alone leaves the lobby, so nobody can join it (2026-10-02); the call chain
   is logged, as exe RVAs, to find where the game decides that. */
static volatile LONG keep_lobby;
/* Set on the thread running Online Services' LeaveSession (hook_leave_session):
   the leave a solo start asks for. Only that one is refused. The game's own
   leave on the way back to the menu (exe 0x7abf235, the online session
   subsystem) retries without pause when refused: 9,172 times in 7 s. */
static __declspec(thread) int in_leave_session;
#define KEEP_LOBBY_REFUSED ((long)0x80004005) /* E_FAIL */

static long __stdcall hook_lobby_leave(void *lobby, void *user, void *context) {
    /* A public game stays joinable whoever is in it: the leave a solo start
       asks for is refused. The PlayFab session's leave helper (exe 0x6f43a90)
       passes no async context and checks the result at once, so a failure
       comes back to it as "could not leave" rather than a wait that never
       ends. The lobby, its connection string and its listing stay. */
    if (keep_lobby && in_leave_session && lobby && lobby == current_lobby) {
        fireteam_log("lobby: kept %p (the game is public; its leave refused)", lobby);
        return KEEP_LOBBY_REFUSED;
    }
    if (lobby == current_lobby) {
        current_lobby = NULL;
        fireteam_log("lobby: left %p", lobby);
        void *frames[24];
        USHORT n = RtlCaptureStackBackTrace(0, 24, frames, NULL);
        unsigned char *base = (unsigned char *)GetModuleHandleA(NULL);
        char line[24 * 12 + 1];
        size_t at = 0;
        for (USHORT i = 0; i < n && at + 12 < sizeof line; i++) {
            if (!in_image(frames[i])) continue;
            at += (size_t)snprintf(line + at, sizeof line - at, " %llx",
                                   (unsigned long long)((unsigned char *)frames[i] - base));
        }
        line[at] = 0;
        fireteam_log("lobby: left from%s", line);
    }
    return real_lobby_leave(lobby, user, context);
}

/* PFLobbyPostUpdate(lobby, localUser, lobbyUpdate, memberUpdate, asyncContext).
   The host locks its lobby's membership when a match starts, and a join into a
   locked lobby reaches the joiner as "This fireteam is full" (two PCs,
   2026-10-02: lock 0 at the menu, 1 in a match). While the game is public the
   lock is rewritten to unlocked, so players can join a match in progress.
   PFLobbyDataUpdate: newOwner, maxMemberCount, accessPolicy, membershipLock
   (pointers, each optional), then the property arrays; the caller's struct is
   const, so a copy goes to PlayFab. */
typedef long(__stdcall *lobby_post_update_t)(void *, void *, const void *, const void *, void *);

enum { MEMBERSHIP_UNLOCKED = 0, MEMBERSHIP_LOCKED = 1 };
#define LOBBY_UPDATE_LOCK 3 /* membershipLock's index among the four leading pointers */
#define LOBBY_UPDATE_SIZE 80

static lobby_post_update_t real_lobby_post_update;

/* The properties a lobby update carries: search properties (count at +32, keys
   +40, values +48) and lobby properties (+56, +64, +72). Logged to find what a
   joining client reads and gives up on in a match in progress (2026-10-02: it
   leaves a second after joining, without the simulation refusing it). */
static void log_lobby_properties(const unsigned char *update) {
    for (int group = 0; group < 2; group++) {
        unsigned count = *(const unsigned *)(update + 32 + group * 24);
        const char *const *keys = *(const char *const *const *)(update + 40 + group * 24);
        const char *const *values = *(const char *const *const *)(update + 48 + group * 24);
        if (!count || !keys) continue;
        for (unsigned i = 0; i < count && i < 64; i++) {
            const char *v = values ? values[i] : NULL;
            /* The connection string is the lobby's join secret: never logged. */
            if (keys[i] && strcmp(keys[i], "ConnectionString") == 0) v = "<hidden>";
            fireteam_log("lobby: %s property %s = %.200s", group ? "lobby" : "search", keys[i] ? keys[i] : "?",
                         v ? v : "(removed)");
        }
    }
}

/* Unreal's session settings ride in the lobby property "_flags", one bit each
   in FOnlineSessionSettings order: bShouldAdvertise 0, bAllowJoinInProgress 1,
   bIsLANMatch 2, bIsDedicated 3, bUsesStats 4, bAllowInvites 5, bUsesPresence
   6, bAllowJoinViaPresence 7, bAllowJoinViaPresenceFriendsOnly 8, ... The host
   clears join-in-progress a minute after creating the lobby (1507 -> 1505) and
   advertise, invites and join-via-presence when a match starts (-> 1344), and
   a joining client that reads them leaves within a second (2026-10-02). While
   the game is public those four bits stay set. */
#define SESSION_JOIN_FLAGS ((1u << 0) | (1u << 1) | (1u << 5) | (1u << 7))

static long __stdcall hook_lobby_post_update(void *lobby, void *user, const void *update, const void *member,
                                            void *context) {
    if (!update) return real_lobby_post_update(lobby, user, update, member, context);
    __try {
        log_lobby_properties((const unsigned char *)update);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        fireteam_log("lobby: properties unreadable");
    }
    if (!keep_lobby) {
        const unsigned *lock = ((const unsigned *const *)update)[LOBBY_UPDATE_LOCK];
        if (lock) fireteam_log("lobby: membership %s for %p", *lock == MEMBERSHIP_LOCKED ? "locked" : "unlocked", lobby);
        return real_lobby_post_update(lobby, user, update, member, context);
    }

    /* A public game: a copy of the update, with the lock left open and the
       join flags kept on. */
    static const unsigned unlocked = MEMBERSHIP_UNLOCKED;
    __declspec(align(8)) unsigned char copy[LOBBY_UPDATE_SIZE];
    memcpy(copy, update, sizeof copy);
    const unsigned *lock = ((const unsigned *const *)copy)[LOBBY_UPDATE_LOCK];
    if (lock && *lock == MEMBERSHIP_LOCKED) {
        ((const unsigned **)copy)[LOBBY_UPDATE_LOCK] = &unlocked;
        fireteam_log("lobby: membership lock asked for %p, kept open (the game is public)", lobby);
    }
    /* Lobby properties: count +56, keys +64, values +72. */
    unsigned count = *(const unsigned *)(copy + 56);
    const char *const *keys = *(const char *const *const *)(copy + 64);
    const char *const *values = *(const char *const *const *)(copy + 72);
    const char *patched_values[64];
    char flags_text[16];
    if (count && count <= 64 && keys && values) {
        for (unsigned i = 0; i < count; i++) {
            patched_values[i] = values[i];
            if (keys[i] && values[i] && strcmp(keys[i], "_flags") == 0) {
                unsigned flags = (unsigned)strtoul(values[i], NULL, 10);
                unsigned kept = flags | SESSION_JOIN_FLAGS;
                if (kept != flags) {
                    snprintf(flags_text, sizeof flags_text, "%u", kept);
                    patched_values[i] = flags_text;
                    *(const char *const **)(copy + 72) = patched_values;
                    fireteam_log("lobby: _flags %u -> %u (joining stays open: the game is public)", flags, kept);
                }
            }
        }
    }
    return real_lobby_post_update(lobby, user, copy, member, context);
}

/* PFLobbyForceRemoveMember(lobby, targetMember, preventRejoin, asyncContext):
   the host removing someone from its lobby. A player joining a match in
   progress was disconnected (2026-10-02) while the game re-locked its lobby at
   each membership change; this logs any removal and refuses it while the game
   is public. PFEntityKey: { const char *id; const char *type; }. */
typedef long(__stdcall *lobby_force_remove_t)(void *, const void *, unsigned char, void *);

static lobby_force_remove_t real_lobby_force_remove;

static long __stdcall hook_lobby_force_remove(void *lobby, const void *member, unsigned char prevent_rejoin,
                                             void *context) {
    const char *id = member ? *(const char *const *)member : NULL;
    char line[CALLER_STACK];
    caller_stack(line);
    fireteam_log("lobby: remove member %s from %p (prevent rejoin %u)%s, asked from%s", id ? id : "?", lobby,
                 prevent_rejoin, keep_lobby ? ": refused (the game is public)" : "", line);
    if (keep_lobby) return KEEP_LOBBY_REFUSED;
    return real_lobby_force_remove(lobby, member, prevent_rejoin, context);
}

/* PartyStartProcessingStateChanges(handle, &count, &changes): every Party
   event, each change starting with its PartyStateChangeType. Logged, without
   the per-packet ones, to see whether a player joining a match in progress
   ever reaches the host's Party network (2026-10-02: it joins the lobby but
   no connection reaches the game). */
typedef unsigned(__stdcall *party_start_changes_t)(void *, unsigned *, const void *const **);

static party_start_changes_t real_party_start_changes;

static const char *party_change_name(unsigned type) {
    static const char *const names[] = {
        "RegionsChanged", "DestroyLocalUserCompleted", "CreateNewNetworkCompleted", "ConnectToNetworkCompleted",
        "AuthenticateLocalUserCompleted", "NetworkConfigurationMadeAvailable", "NetworkDescriptorChanged",
        "LocalUserRemoved", "RemoveLocalUserCompleted", "LocalUserKicked", "CreateEndpointCompleted",
        "DestroyEndpointCompleted", "EndpointCreated", "EndpointDestroyed", "RemoteDeviceCreated",
        "RemoteDeviceDestroyed", "RemoteDeviceJoinedNetwork", "RemoteDeviceLeftNetwork", "DevicePropertiesChanged",
        "LeaveNetworkCompleted", "NetworkDestroyed", "EndpointMessageReceived", "DataBuffersReturned",
        "EndpointPropertiesChanged", "SynchronizeMessagesBetweenEndpointsCompleted", "CreateInvitationCompleted",
        "RevokeInvitationCompleted", "InvitationCreated", "InvitationDestroyed", "NetworkPropertiesChanged",
        "KickDeviceCompleted", "KickUserCompleted"};
    return type < sizeof names / sizeof *names ? names[type] : "(chat/audio)";
}

static unsigned __stdcall hook_party_start_changes(void *handle, unsigned *count, const void *const **changes) {
    unsigned err = real_party_start_changes(handle, count, changes);
    if (err == 0 && count && changes && *changes) {
        for (unsigned i = 0; i < *count; i++) {
            const unsigned *change = (const unsigned *)(*changes)[i];
            if (!change) continue;
            unsigned type = *change;
            /* Messages and returned buffers come every frame; chat and audio
               (32 and up) are not the join. */
            if (type == 21 || type == 22 || type >= 32) continue;
            fireteam_log("party: %s (%u)", party_change_name(type), type);
        }
    }
    return err;
}

/* --- The simulation's join refusals (diagnosis) ---------------------------

   A player joining a match in progress reaches the host's lobby and Party
   network, then leaves within a second (2026-10-02). The simulation's own
   network session answers its join-request over Party; the refusal is message
   7, "join-refuse" (12 bytes: the session id, then a 6-bit reason). Its send
   routine (sim DLL RVA 0x5318f0 on CU4: gateway, address, type, size, data)
   is hooked inline to log each refusal's reason and the code that sent it.
   The prologue it displaces is 17 bytes of pushes and `sub rsp, 28h`, with
   nothing position-dependent, so the trampoline is a plain copy. */
typedef unsigned long long(__fastcall *sim_send_t)(void *, void *, unsigned, unsigned, const unsigned char *);

static sim_send_t sim_send_trampoline;
static unsigned char *sim_base;

static const unsigned char SIM_SEND[] = {0x40, 0x53, 0x55, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55, 0x41, 0x56, 0x41,
                                         0x57, 0x48, 0x83, 0xEC, 0x28, 0x80, 0x79, 0x28, 0x00, 0x4C, 0x8B, 0xFA};
#define SIM_SEND_STOLEN 17

/* Message names by type (the registration order in the sim DLL, 0x4c3420). */
static const char *sim_message_name(unsigned type) {
    static const char *const names[] = {"connect-request", "connect-refuse", "connect-establish", "connect-closed",
                                        "join-request", "peer-connect", "join-abort", "join-refuse",
                                        "leave-session", "leave-acknowledge", "session-disband"};
    return type < sizeof names / sizeof *names ? names[type] : NULL;
}

static unsigned long long __fastcall hook_sim_send(void *gateway, void *address, unsigned type, unsigned size,
                                                   const unsigned char *data) {
    /* Every message, at most a few per type every 30 s (some go out each tick).
       Joins, aborts and refusals carry the session id first (64 bits); a
       refusal's reason follows at +8. */
    static DWORD window[64];
    static unsigned sent[64];
    if (type < 64 && data) {
        DWORD now = GetTickCount();
        if (now - window[type] > 30000) {
            window[type] = now;
            sent[type] = 0;
        }
        if (sent[type]++ < 6 || type == 4 || type == 6 || type == 7) {
            unsigned char *caller = (unsigned char *)_ReturnAddress();
            const char *name = sim_message_name(type);
            char label[24];
            if (!name) {
                snprintf(label, sizeof label, "type %u", type);
                name = label;
            }
            if ((type == 4 || type == 6 || type == 7 || type == 1) && size >= 8)
                fireteam_log("sim: send %s (size %u) session %016llx%s%u, from sim+%llx", name, size,
                             *(const unsigned long long *)data, size >= 12 ? " reason " : " ",
                             size >= 12 ? *(const unsigned *)(data + 8) : 0u, (unsigned long long)(caller - sim_base));
            else
                fireteam_log("sim: send %s (size %u), from sim+%llx", name, size,
                             (unsigned long long)(caller - sim_base));
        }
    }
    return sim_send_trampoline(gateway, address, type, size, data);
}

static const char *hook_sim_send_routine(void) {
    if (sim_send_trampoline) return "already hooked";
    HMODULE sim = GetModuleHandleA("HaloSimulation_tag_release.dll");
    if (!sim) return "simulation DLL not loaded";
    sim_base = (unsigned char *)sim;
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(sim_base + ((IMAGE_DOS_HEADER *)sim_base)->e_lfanew);
    IMAGE_SECTION_HEADER *s = IMAGE_FIRST_SECTION(nt);
    unsigned char *found = NULL;
    int hits = 0;
    for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; i++, s++) {
        if (!(s->Characteristics & IMAGE_SCN_MEM_EXECUTE)) continue;
        unsigned char *p = sim_base + s->VirtualAddress, *end = p + s->Misc.VirtualSize - sizeof SIM_SEND;
        for (; p <= end; p++)
            if (p[0] == SIM_SEND[0] && memcmp(p, SIM_SEND, sizeof SIM_SEND) == 0) {
                found = p;
                hits++;
            }
    }
    if (hits != 1) {
        static char why[64];
        snprintf(why, sizeof why, "send pattern matched %d times, left alone", hits);
        return why;
    }
    unsigned char *tramp = (unsigned char *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!tramp) return "VirtualAlloc failed";
    /* trampoline: the stolen prologue, then jmp [rip+0] -> found + 17 */
    memcpy(tramp, found, SIM_SEND_STOLEN);
    unsigned char *j = tramp + SIM_SEND_STOLEN;
    j[0] = 0xFF;
    j[1] = 0x25;
    memset(j + 2, 0, 4);
    *(unsigned char **)(j + 6) = found + SIM_SEND_STOLEN;
    sim_send_trampoline = (sim_send_t)tramp;
    DWORD old;
    if (!VirtualProtect(found, SIM_SEND_STOLEN, PAGE_EXECUTE_READWRITE, &old)) return "VirtualProtect failed";
    unsigned char patch[SIM_SEND_STOLEN];
    memset(patch, 0x90, sizeof patch);
    patch[0] = 0xFF;
    patch[1] = 0x25;
    memset(patch + 2, 0, 4);
    *(void **)(patch + 6) = (void *)hook_sim_send;
    memcpy(found, patch, sizeof patch);
    VirtualProtect(found, SIM_SEND_STOLEN, old, &old);
    FlushInstructionCache(GetCurrentProcess(), found, SIM_SEND_STOLEN);
    return "hooked";
}

static void *playfab(const char *name) {
    HMODULE pf = GetModuleHandleA("PlayFabMultiplayerWin.dll");
    return pf ? (void *)GetProcAddress(pf, name) : NULL;
}

/* Writes `text` to native\<name>, whole: a temporary file renamed over it, so
   a poll never reads half a reply. */
static void write_reply(const char *name, const char *text, size_t length) {
    if (!dir[0]) find_dir();
    char path[MAX_PATH], tmp[MAX_PATH];
    snprintf(path, sizeof path, "%s%s", dir, name);
    snprintf(tmp, sizeof tmp, "%s%s.tmp", dir, name);
    FILE *f = fopen(tmp, "wb");
    if (!f) return;
    fwrite(text, 1, length, f);
    fclose(f);
    MoveFileExA(tmp, path, MOVEFILE_REPLACE_EXISTING);
}

/* The current lobby's connection string, membership lock and size, for a host
   to list its game: "ok <string>\nlock <0|1>\nmax <n>\n", or "none <why>\n". */
__declspec(dllexport) int mjolnir_lobby_connection(void *L) {
    (void)L;
    char out[4600];
    void *lobby = current_lobby;
    get_connection_string_t get_connection = (get_connection_string_t)playfab("PFLobbyGetConnectionString");
    get_membership_lock_t get_lock = (get_membership_lock_t)playfab("PFLobbyGetMembershipLock");
    get_max_members_t get_max = (get_max_members_t)playfab("PFLobbyGetMaxMemberCount");
    const char *connection = NULL;
    long hr = 0;
    if (!lobby) {
        snprintf(out, sizeof out, "none no lobby yet\n");
    } else if (!get_connection) {
        snprintf(out, sizeof out, "none PFLobbyGetConnectionString not found\n");
    } else if ((hr = get_connection(lobby, &connection)) < 0 || !connection || !connection[0]) {
        snprintf(out, sizeof out, "none 0x%08lx\n", (unsigned long)hr);
    } else {
        int lock = -1;
        unsigned max = 0;
        if (get_lock) get_lock(lobby, &lock);
        if (get_max) get_max(lobby, &max);
        snprintf(out, sizeof out, "ok %s\nlock %d\nmax %u\n", connection, lock, max);
    }
    write_reply("lobby_connection.txt", out, strlen(out));
    return 0;
}

/* --- Joining: the Steam online subsystem's task manager ------------------- */

#define STEAM_JOIN_REQUESTED 337 /* GameRichPresenceJoinRequested_t */
#define TASK_MANAGER_SPAN 0x800  /* the object is 0x570 bytes on CU4 */

typedef void(__fastcall *online_tick_t)(void *self);
typedef void(__fastcall *steam_handler_t)(void *self, void *data);

/* GameRichPresenceJoinRequested_t: the friend's CSteamID, then the connect
   string. The handler converts it as a C string, so it may run past Steam's
   256 characters. */
struct join_request {
    unsigned long long friend_id;
    char connect[4096];
};

static online_tick_t real_online_tick;
static struct join_request *volatile pending_join;

static int in_image(const void *p) {
    unsigned char *base = (unsigned char *)GetModuleHandleA(NULL);
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    return (const unsigned char *)p >= base && (const unsigned char *)p < base + nt->OptionalHeader.SizeOfImage;
}

/* The task manager's CCallback for GameRichPresenceJoinRequested_t: vtable,
   flags, m_iCallback, then m_pObj (the manager itself) and m_Func. Found by
   those, not by offset (+0x380 on CU4). */
static steam_handler_t join_handler(unsigned char *self) {
    __try {
        for (unsigned off = 0; off + 0x20 <= TASK_MANAGER_SPAN; off += 8) {
            if (*(int *)(self + off + 0xC) != STEAM_JOIN_REQUESTED) continue;
            if (*(void **)(self + off + 0x10) != self) continue;
            void *fn = *(void **)(self + off + 0x18);
            if (in_image(fn) && in_image(*(void **)(self + off))) return (steam_handler_t)fn;
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
    return NULL;
}

static void deliver_join(void *self, struct join_request *req) {
    char reply[128];
    steam_handler_t handler = join_handler((unsigned char *)self);
    if (!handler) {
        snprintf(reply, sizeof reply, "error the Steam join handler was not found\n");
    } else {
        __try {
            handler(self, req);
            snprintf(reply, sizeof reply, "delivered\n");
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            snprintf(reply, sizeof reply, "error the Steam join handler faulted (0x%08lx)\n",
                     (unsigned long)GetExceptionCode());
        }
    }
    fireteam_log("join: %.*s", (int)strcspn(reply, "\n"), reply);
    write_reply("join_reply.txt", reply, strlen(reply));
    free(req);
}

/* FOnlineAsyncTaskManagerSteam::OnlineTick, on the online thread, where Steam's
   own callbacks run. */
static void __fastcall hook_online_tick(void *self) {
    struct join_request *req = (struct join_request *)InterlockedExchangePointer((void *volatile *)&pending_join, NULL);
    if (req) deliver_join(self, req);
    real_online_tick(self);
}

/* The one place `pattern` occurs in the exe's code, or NULL (with the count in *hits). */
static unsigned char *find_code(const unsigned char *pattern, size_t length, int *hits) {
    unsigned char *base = (unsigned char *)GetModuleHandleA(NULL);
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_SECTION_HEADER *s = IMAGE_FIRST_SECTION(nt);
    unsigned char *found = NULL;
    *hits = 0;
    for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; i++, s++) {
        if (!(s->Characteristics & IMAGE_SCN_MEM_EXECUTE)) continue;
        unsigned char *start = base + s->VirtualAddress, *end = start + s->Misc.VirtualSize - length;
        for (unsigned char *p = start; p <= end; p++) {
            if (p[0] == pattern[0] && memcmp(p, pattern, length) == 0) {
                found = p;
                (*hits)++;
            }
        }
    }
    return *hits == 1 ? found : NULL;
}

/* find_code with wildcards: mask byte 0 skips that position. */
static unsigned char *find_code_masked(const unsigned char *pattern, const unsigned char *mask, size_t length,
                                       int *hits) {
    unsigned char *base = (unsigned char *)GetModuleHandleA(NULL);
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_SECTION_HEADER *s = IMAGE_FIRST_SECTION(nt);
    unsigned char *found = NULL;
    *hits = 0;
    for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; i++, s++) {
        if (!(s->Characteristics & IMAGE_SCN_MEM_EXECUTE)) continue;
        unsigned char *start = base + s->VirtualAddress, *end = start + s->Misc.VirtualSize - length;
        for (unsigned char *p = start; p <= end; p++) {
            if (p[0] != pattern[0]) continue;
            size_t k = 1;
            while (k < length && (!mask[k] || p[k] == pattern[k])) k++;
            if (k == length) {
                found = p;
                (*hits)++;
            }
        }
    }
    return *hits == 1 ? found : NULL;
}

/* The one slot in the exe's read-only data that holds `fn`: a vtable entry. */
static void **find_vtable_slot(void *fn, int *hits) {
    unsigned char *base = (unsigned char *)GetModuleHandleA(NULL);
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_SECTION_HEADER *s = IMAGE_FIRST_SECTION(nt);
    void **found = NULL;
    *hits = 0;
    for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; i++, s++) {
        if (s->Characteristics & (IMAGE_SCN_MEM_EXECUTE | IMAGE_SCN_MEM_WRITE)) continue;
        void **p = (void **)(base + s->VirtualAddress), **end = (void **)(base + s->VirtualAddress + s->Misc.VirtualSize);
        for (; p < end; p++) {
            if (*p == fn) {
                found = p;
                (*hits)++;
            }
        }
    }
    return *hits == 1 ? found : NULL;
}

/* Point every read-only-data slot holding `fn` (each vtable of a class that
   inherits it) at `hook`; the count swapped, and in *already those that held
   `hook` before. */
static int swap_vtable_slots(void *fn, void *hook, int *already) {
    unsigned char *base = (unsigned char *)GetModuleHandleA(NULL);
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_SECTION_HEADER *s = IMAGE_FIRST_SECTION(nt);
    int swapped = 0;
    *already = 0;
    for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; i++, s++) {
        if (s->Characteristics & (IMAGE_SCN_MEM_EXECUTE | IMAGE_SCN_MEM_WRITE)) continue;
        void **p = (void **)(base + s->VirtualAddress), **end = (void **)(base + s->VirtualAddress + s->Misc.VirtualSize);
        for (; p < end; p++) {
            if (*p == hook) (*already)++;
            if (*p != fn) continue;
            DWORD old;
            if (!VirtualProtect(p, sizeof *p, PAGE_READWRITE, &old)) continue;
            *p = hook;
            VirtualProtect(p, sizeof *p, old, &old);
            swapped++;
        }
    }
    return swapped;
}

/* OnlineTick's body after its prologue (push rbx; sub rsp, 20h): the subsystem
   at +0x560, then SteamAPI_RunCallbacks when the client is up (exe RVA
   0x6a7b580 on CU4, vtable slot 6 at 0xbc86b00). */
static const unsigned char ONLINE_TICK[] = {0x48, 0x8B, 0x81, 0x60, 0x05, 0x00, 0x00, 0x48, 0x8B, 0xD9, 0x80,
                                            0xB8, 0xE0, 0x00, 0x00, 0x00, 0x00, 0x74, 0x06, 0xFF, 0x15};
static const unsigned char ONLINE_TICK_PROLOGUE[] = {0x40, 0x53, 0x48, 0x83, 0xEC, 0x20};

static const char *hook_online_tick_slot(void) {
    static char why[80];
    int hits;
    unsigned char *body = find_code(ONLINE_TICK, sizeof ONLINE_TICK, &hits);
    if (!body) {
        snprintf(why, sizeof why, "OnlineTick pattern matched %d times, left alone", hits);
        return why;
    }
    unsigned char *fn = body - sizeof ONLINE_TICK_PROLOGUE;
    if (memcmp(fn, ONLINE_TICK_PROLOGUE, sizeof ONLINE_TICK_PROLOGUE) != 0) return "OnlineTick prologue differs, left alone";
    void **slot = find_vtable_slot(fn, &hits);
    if (!slot) {
        void **ours = find_vtable_slot((void *)hook_online_tick, &hits);
        if (ours) return "already hooked";
        snprintf(why, sizeof why, "OnlineTick is in %d vtable slots, left alone", hits);
        return why;
    }
    DWORD old;
    if (!VirtualProtect(slot, sizeof *slot, PAGE_READWRITE, &old)) return "VirtualProtect failed";
    real_online_tick = (online_tick_t)fn;
    *slot = (void *)hook_online_tick;
    VirtualProtect(slot, sizeof *slot, old, &old);
    return "hooked";
}

/* --- Keeping the lobby through a solo start ------------------------------ */

/* A match started with the host alone leaves the PlayFab lobby about a minute
   in: the game's session flow asks Online Services' LeaveSession with
   bDestroySession set, and the OSS adapter's LeaveSession (exe RVA 0x7a592f0
   on CU4, the only pointer to it a vtable slot at 0xc1153b0) calls the
   PlayFab session's DestroySession, which leaves the lobby (2026-10-02).
   FLeaveSession::Params: local account (4 bytes), the session's FName (+4),
   bDestroySession (+0xc). Clearing the flag does not help: the other branch
   unregisters the player and leaves the lobby all the same. So this hook only
   logs; a public game keeps its lobby by refusing PFLobbyLeave itself
   (hook_lobby_leave). The body pattern is the flag's own test. */
typedef void *(__fastcall *leave_session_t)(void *self, void *out, unsigned char *params);

static leave_session_t real_leave_session;

static const unsigned char LEAVE_SESSION[] = {0x41, 0x80, 0x7D, 0x0C, 0x00, 0x4C, 0x89, 0xB4, 0x24, 0x98, 0x01,
                                              0x00, 0x00, 0x4C, 0x89, 0xBC, 0x24, 0x90, 0x01, 0x00, 0x00};
static const unsigned char LEAVE_SESSION_PROLOGUE[] = {0x4C, 0x8B, 0xDC, 0x55, 0x41, 0x54};
#define LEAVE_SESSION_BODY 0x74

/* The Online Services op runner (exe 0x6a2c740) calls LeaveSession through a
   continuation object it keeps in rsi: the queued call's object (+0x18), its
   member function pointer (+0x30, a vcall thunk) and this-adjust (+0x38). The
   thunk names who queued the leave, the code that decides it; a stub in front
   of the hook saves rsi into leave_runner_rsi (2026-10-03). */
static volatile unsigned long long *leave_runner_rsi;

static void log_leave_continuation(void) {
    unsigned char *base = (unsigned char *)GetModuleHandleA(NULL);
    unsigned char *obj = leave_runner_rsi ? (unsigned char *)*leave_runner_rsi : NULL;
    if (!obj) return;
    __try {
        char line[400];
        size_t at = 0;
        for (int k = 0; k < 0x48; k += 8) {
            unsigned char *v = *(unsigned char **)(obj + k);
            if (in_image(v))
                at += (size_t)snprintf(line + at, sizeof line - at, " +%02x=exe+%llx", k, (unsigned long long)(v - base));
            else
                at += (size_t)snprintf(line + at, sizeof line - at, " +%02x=%p", k, (void *)v);
            if (at >= sizeof line - 40) break;
        }
        fireteam_log("session: LeaveSession continuation%s", line);
        unsigned char *pmf = *(unsigned char **)(obj + 0x30);
        if (in_image(pmf))
            fireteam_log("session: its function starts %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x",
                         pmf[0], pmf[1], pmf[2], pmf[3], pmf[4], pmf[5], pmf[6], pmf[7], pmf[8], pmf[9], pmf[10],
                         pmf[11]);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        fireteam_log("session: LeaveSession continuation unreadable");
    }
}

static void *__fastcall hook_leave_session(void *self, void *out, unsigned char *params) {
    if (params) {
        fireteam_log("session: LeaveSession name %u/%u destroy %u", *(unsigned *)(params + 4),
                     *(unsigned *)(params + 8), params[0xc]);
        log_leave_continuation();
    }
    in_leave_session++;
    void *result = real_leave_session(self, out, params);
    in_leave_session--;
    return result;
}

/* The public Online Services LeaveSession (exe 0x69f1910 on CU4) sits at slot
   0x48 of the same vtable whose slot 0x1b0 holds the work it queues (the hook
   above). Whoever calls it decides the leave, and is on the stack here. */
typedef void *(__fastcall *leave_session_public_t)(void *self, void *out, unsigned char *params);
static leave_session_public_t real_leave_session_public;
static const unsigned char LEAVE_SESSION_PUBLIC_PROLOGUE[] = {0x40, 0x55, 0x53, 0x57, 0x41, 0x55, 0x41, 0x56,
                                                              0x48, 0x8D, 0x6C, 0x24, 0xC9};

static void *__fastcall hook_leave_session_public(void *self, void *out, unsigned char *params) {
    char line[CALLER_STACK];
    caller_stack(line);
    drop_held_world("LeaveSession");
    fireteam_log("session: LeaveSession asked (name %u/%u destroy %u) from%s", params ? *(unsigned *)(params + 4) : 0u,
                 params ? *(unsigned *)(params + 8) : 0u, params ? params[0xc] : 0u, line);
    return real_leave_session_public(self, out, params);
}

static const char *hook_leave_session_slot(void) {
    static char why[80];
    int hits;
    unsigned char *body = find_code(LEAVE_SESSION, sizeof LEAVE_SESSION, &hits);
    if (!body) {
        snprintf(why, sizeof why, "LeaveSession pattern matched %d times, left alone", hits);
        return why;
    }
    unsigned char *fn = body - LEAVE_SESSION_BODY;
    if (memcmp(fn, LEAVE_SESSION_PROLOGUE, sizeof LEAVE_SESSION_PROLOGUE) != 0) return "LeaveSession prologue differs, left alone";
    void **slot = find_vtable_slot(fn, &hits);
    if (!slot) {
        if (find_vtable_slot((void *)hook_leave_session, &hits)) return "already hooked";
        snprintf(why, sizeof why, "LeaveSession is in %d vtable slots, left alone", hits);
        return why;
    }
    DWORD old;
    if (!VirtualProtect(slot, sizeof *slot, PAGE_READWRITE, &old)) return "VirtualProtect failed";
    real_leave_session = (leave_session_t)fn;
    /* stub: mov [rip+0x39], rsi ; jmp [rip+0] -> hook_leave_session ; rsi kept at +0x40 */
    unsigned char *stub = (unsigned char *)VirtualAlloc(NULL, 0x80, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!stub) return "VirtualAlloc failed";
    stub[0] = 0x48;
    stub[1] = 0x89;
    stub[2] = 0x35;
    *(int *)(stub + 3) = 0x40 - 7;
    stub[7] = 0xFF;
    stub[8] = 0x25;
    *(int *)(stub + 9) = 0;
    *(void **)(stub + 13) = (void *)hook_leave_session;
    leave_runner_rsi = (volatile unsigned long long *)(stub + 0x40);
    *slot = (void *)stub;
    /* The public entry, 0x1b0 - 0x48 bytes before it in the same vtable. */
    void **pub = slot - (0x1b0 - 0x48) / sizeof(void *);
    if (in_image(*pub) && memcmp(*pub, LEAVE_SESSION_PUBLIC_PROLOGUE, sizeof LEAVE_SESSION_PUBLIC_PROLOGUE) == 0) {
        DWORD old2;
        if (VirtualProtect(pub, sizeof *pub, PAGE_READWRITE, &old2)) {
            real_leave_session_public = (leave_session_public_t)*pub;
            *pub = (void *)hook_leave_session_public;
            VirtualProtect(pub, sizeof *pub, old2, &old2);
            fireteam_log("LeaveSession public entry: hooked");
        }
    } else {
        fireteam_log("LeaveSession public entry: not where expected, left alone");
    }
    VirtualProtect(slot, sizeof *slot, old, &old);
    return "hooked";
}

/* UBlamOnlineSessionSubsystem::SetSessionRunning (exe 0x7abb940 on CU4) runs at
   a match's start. With more than one session member it locks the lobby's
   membership; with one (a host alone) it leaves the session to play offline:
   the LeaveSession that dropped a solo host's lobby and kept anyone from
   joining (2026-10-03). While the game is public the member-count branch is
   made unconditional, so a host alone stays online.
       0x7abba88: cmp eax, 1 / jg +6c (7F 6C) -> jmp +6c (EB 6C) */
static const unsigned char SOLO_SESSION_BRANCH[] = {0x83, 0xF8, 0x01, 0x7F, 0x6C, 0x44, 0x8B, 0x87, 0xE8, 0x02,
                                                    0x00, 0x00, 0x48, 0x8D, 0x55, 0xC8, 0x80, 0xA7, 0x70, 0x02};
static unsigned char *solo_session_branch;

static const char *stay_online_alone(int on) {
    if (!solo_session_branch) {
        unsigned char pattern[sizeof SOLO_SESSION_BRANCH];
        memcpy(pattern, SOLO_SESSION_BRANCH, sizeof pattern);
        int hits;
        solo_session_branch = find_code(pattern, sizeof pattern, &hits);
        if (!solo_session_branch) {
            pattern[3] = 0xEB; /* patched by an earlier load of this DLL */
            solo_session_branch = find_code(pattern, sizeof pattern, &hits);
        }
        if (!solo_session_branch) return "SetSessionRunning branch not found, left alone";
    }
    unsigned char want = on ? 0xEB : 0x7F;
    if (solo_session_branch[3] == want) return on ? "stays online alone" : "as shipped";
    DWORD old;
    if (!VirtualProtect(solo_session_branch + 3, 1, PAGE_EXECUTE_READWRITE, &old)) return "VirtualProtect failed";
    solo_session_branch[3] = want;
    VirtualProtect(solo_session_branch + 3, 1, old, &old);
    FlushInstructionCache(GetCurrentProcess(), solo_session_branch + 3, 1);
    return on ? "stays online alone" : "as shipped";
}

/* --- Joining a match under way ------------------------------------------- */

/* The match's game mode (BP_MeteoriteGameMode, native override at exe 0x7b552b0
   on CU4, vtable slot 0x848) calls AGameModeBase::PreLogin and then, whenever
   that passed, refuses the login with "Cannot join - game is already in
   progress". The joiner's network-failure handler maps the text to a
   rejection and leaves the session: the "Disconnected from host" of every
   join into a running match (2026-10-03). With the refusal skipped, the
   joiner got into the match and crashed: the host's Spartan replicated in,
   and AMeteoritePawn::BeginPlay (exe 0x7b16500) dereferenced the BlamEngine
   module's running game, which a joiner's simulation never started. So the
   refusal stays (the hook logs every login) unless native\join_in_progress.txt
   says "1", an experiment switch for the simulation's own join-in-progress
   work; then, while the game is public, the hook calls the stock PreLogin alone.
   The pattern is the override's prologue up to its call of the stock one. */
struct fstring {
    wchar_t *data;
    int num, max;
};
typedef void(__fastcall *pre_login_t)(void *self, void *options, void *address, void *unique_id, struct fstring *error);
static pre_login_t real_pre_login, stock_pre_login;

static const unsigned char PRE_LOGIN[] = {0x40, 0x53, 0x56, 0x48, 0x83, 0xEC, 0x68, 0x48, 0x8B, 0x9C, 0x24, 0xA0,
                                          0x00, 0x00, 0x00, 0x49, 0x8B, 0xF1, 0x48, 0x89, 0x5C, 0x24, 0x20, 0xE8};
/* After the call: cmp dword [rbx+8], 1 / jg (an error already) ... lea r15, the refusal. */
static const unsigned char PRE_LOGIN_AFTER[] = {0x83, 0x7B, 0x08, 0x01, 0x0F, 0x8F};
#define PRE_LOGIN_REFUSAL_LEA 0x36
static const wchar_t IN_PROGRESS[] = L"Cannot join - game is already in progress";

static volatile LONG join_in_progress;

static void __fastcall hook_pre_login(void *self, void *options, void *address, void *unique_id, struct fstring *error) {
    int open = keep_lobby && join_in_progress;
    (open ? stock_pre_login : real_pre_login)(self, options, address, unique_id, error);
    char text[120] = "accepted";
    if (error && error->num > 1 && error->data) {
        int i = 0;
        for (; i < (int)sizeof text - 1 && error->data[i]; i++) text[i] = error->data[i] < 0x80 ? (char)error->data[i] : '?';
        text[i] = 0;
    }
    fireteam_log("login: PreLogin (%s): %s", open ? "public, join-in-progress experiment" : "as shipped", text);
}

static const char *hook_pre_login_slots(void) {
    static char why[80];
    if (real_pre_login) return "already hooked";
    int hits;
    unsigned char *fn = find_code(PRE_LOGIN, sizeof PRE_LOGIN, &hits);
    if (!fn) {
        snprintf(why, sizeof why, "PreLogin pattern matched %d times, left alone", hits);
        return why;
    }
    unsigned char *after = fn + sizeof PRE_LOGIN + 4;
    if (memcmp(after, PRE_LOGIN_AFTER, sizeof PRE_LOGIN_AFTER) != 0) return "PreLogin body differs, left alone";
    unsigned char *lea = fn + PRE_LOGIN_REFUSAL_LEA;
    if (lea[0] != 0x4C || lea[1] != 0x8D || lea[2] != 0x3D) return "PreLogin refusal not where expected, left alone";
    const wchar_t *refusal = (const wchar_t *)(lea + 7 + *(int *)(lea + 3));
    if (!in_image(refusal) || wcscmp(refusal, IN_PROGRESS) != 0) return "PreLogin refuses something else, left alone";
    /* The stock PreLogin it calls first: the call's rel32 counts from `after`. It
       is in the stock game modes' vtables, so it must be in at least one. */
    unsigned char *stock = after + *(int *)(after - 4);
    int stock_hits;
    find_vtable_slot(stock, &stock_hits);
    if (!in_image(stock) || stock_hits == 0) return "stock PreLogin not found, left alone";
    real_pre_login = (pre_login_t)fn;
    stock_pre_login = (pre_login_t)stock;
    /* Every class that inherits the override has it in its vtable. */
    int already;
    int swapped = swap_vtable_slots(fn, (void *)hook_pre_login, &already);
    if (!swapped) return already ? "already hooked" : "PreLogin is in no vtable, left alone";
    snprintf(why, sizeof why, "hooked in %d vtables", swapped);
    return why;
}

/* --- A joiner's pawn before its Blam game -------------------------------- */

/* AMeteoritePawn::BeginPlay (exe 0x7b16500 on CU4, BP_MeteoritePawn_C vtable
   slot 0x3a0) runs its parent BeginPlay, then binds to two event sources of
   the running Blam game: the BlamEngine module's engine (+0x10), its +0x40 and
   +0x60. A player let into a match under way (join_in_progress.txt) gets the
   host's pawns replicated before its own simulation has a game, both are
   null, and the bind crashed it (2026-10-03). Without a game the hook runs the
   parent BeginPlay alone and logs it, so the joiner lives on to show what its
   simulation does next. The module lookup is the one BeginPlay makes, read
   from its own code. */
typedef void(__fastcall *begin_play_t)(void *self);
typedef void *(__fastcall *module_manager_get_t)(void);
typedef void *(__fastcall *module_get_t)(void *manager, unsigned long long name);

static begin_play_t real_pawn_begin_play, pawn_parent_begin_play;
static module_manager_get_t module_manager_get;
static module_get_t module_get;

static const unsigned char PAWN_BEGIN_PLAY[] = {0x48, 0x89, 0x5C, 0x24, 0x18, 0x55, 0x56, 0x57, 0x41, 0x54,
                                                0x41, 0x55, 0x41, 0x56, 0x41, 0x57, 0x48, 0x8B, 0xEC, 0x48,
                                                0x83, 0xEC, 0x50, 0xB2, 0x01, 0x48, 0x8B, 0xF9};
#define PAWN_PARENT_CALL 0x3b
#define PAWN_MODULE_MANAGER_CALL 0x18b
#define PAWN_GET_MODULE_CALL 0x197
#define PAWN_ENGINE_READS 0x1b7
/* mov r15, [rax+10h] / mov r13, [r15+40h] */
static const unsigned char PAWN_ENGINE_READ_BYTES[] = {0x4C, 0x8B, 0x78, 0x10, 0x4D, 0x8B, 0x6F, 0x40};

static unsigned char *call_target(unsigned char *call) {
    return call[0] == 0xE8 ? call + 5 + *(int *)(call + 1) : NULL;
}

/* The BlamEngine module's engine and the parts of it that exist only while a
   Blam game runs: event sources at +0x40 and +0x60 (the pawn binds them) and
   +0x50 (the local player controller binds it). All NULL when unknown. */
struct blam_game {
    void *engine, *at40, *at50, *at60;
};

static struct blam_game blam_game_now(void) {
    struct blam_game g = {0};
    if (!module_get || !resolve()) return g;
    unsigned long long name = 0;
    fname_ctor(&name, L"BlamEngine", FNAME_ADD, NULL);
    __try {
        unsigned char *module = (unsigned char *)module_get(module_manager_get(), name);
        if (!module) return g;
        unsigned char *e = *(unsigned char **)(module + 0x10);
        g.engine = e;
        if (!e) return g;
        g.at40 = *(void **)(e + 0x40);
        g.at50 = *(void **)(e + 0x50);
        g.at60 = *(void **)(e + 0x60);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        memset(&g, 0, sizeof g);
    }
    return g;
}

static int blam_game_running(const struct blam_game *g) { return g->at40 && g->at50 && g->at60; }

static void __fastcall hook_pawn_begin_play(void *self) {
    struct blam_game g = blam_game_now();
    if (g.at40 && g.at60) {
        real_pawn_begin_play(self);
        return;
    }
    fireteam_log("pawn: BeginPlay %p before the Blam game (engine %p, +40 %p, +60 %p): parent BeginPlay only", self,
                 g.engine, g.at40, g.at60);
    pawn_parent_begin_play(self);
}

/* AMeteoritePawn::BeginPlay, with the module lookup and parent read from its
   code; NULL (and why) when the code is not what this was written against. */
static unsigned char *find_pawn_begin_play(const char **why) {
    static char text[80];
    int hits;
    unsigned char *fn = find_code(PAWN_BEGIN_PLAY, sizeof PAWN_BEGIN_PLAY, &hits);
    if (!fn) {
        snprintf(text, sizeof text, "pawn BeginPlay pattern matched %d times, left alone", hits);
        *why = text;
        return NULL;
    }
    unsigned char *parent = call_target(fn + PAWN_PARENT_CALL);
    unsigned char *manager = call_target(fn + PAWN_MODULE_MANAGER_CALL);
    unsigned char *get = call_target(fn + PAWN_GET_MODULE_CALL);
    if (!parent || !manager || !get || !in_image(parent) || !in_image(manager) || !in_image(get) ||
        memcmp(fn + PAWN_ENGINE_READS, PAWN_ENGINE_READ_BYTES, sizeof PAWN_ENGINE_READ_BYTES) != 0) {
        *why = "pawn BeginPlay body differs, left alone";
        return NULL;
    }
    pawn_parent_begin_play = (begin_play_t)parent;
    module_manager_get = (module_manager_get_t)manager;
    module_get = (module_get_t)get;
    return fn;
}

static const char *hook_pawn_begin_play_slot(void) {
    static char why[80];
    if (real_pawn_begin_play) return "already hooked";
    const char *missing;
    unsigned char *fn = find_pawn_begin_play(&missing);
    if (!fn) return missing;
    int hits;
    void **slot = find_vtable_slot(fn, &hits);
    if (!slot) {
        snprintf(why, sizeof why, "pawn BeginPlay is in %d vtable slots, left alone", hits);
        return why;
    }
    DWORD old;
    if (!VirtualProtect(slot, sizeof *slot, PAGE_READWRITE, &old)) return "VirtualProtect failed";
    real_pawn_begin_play = (begin_play_t)fn;
    *slot = (void *)hook_pawn_begin_play;
    VirtualProtect(slot, sizeof *slot, old, &old);
    return "hooked";
}

/* --- A client's Blam game starts on its travel ----------------------------- */

/* A client's Blam game starts when the host's seamless travel reaches it:
   APlayerController::ClientTravelInternal calls PreClientTravel (vtable
   +0xf60, the game's override at exe 0x7ae84b0 on CU4), which calls
   UGameInstance::NotifyPreClientTravel (0x600a220); the BlamNetworkSession
   subsystem listens, builds the destination URL and queues the simulation's
   start, whose join-request follows the same second (2026-10-03, PC 2's log).
   A joiner into a match under way connects straight into the map and never
   travels, so its Blam game never starts. The hook logs every PreClientTravel;
   the world hold below replays NotifyPreClientTravel for the map it is in. */
typedef void(__fastcall *pre_client_travel_t)(void *pc, struct fstring *url, int travel_type, unsigned char seamless);
typedef void(__fastcall *notify_pre_client_travel_t)(void *game_instance, struct fstring *url, int travel_type,
                                                     unsigned char seamless);
typedef unsigned char *(__fastcall *get_world_t)(void *object);
static pre_client_travel_t real_pre_client_travel;
static notify_pre_client_travel_t notify_pre_client_travel;
static get_world_t actor_get_world;
static int game_instance_offset;

static const unsigned char PRE_CLIENT_TRAVEL[] = {0x40, 0x53, 0x55, 0x56, 0x57, 0x48, 0x83, 0xEC, 0x38, 0x48, 0x8B, 0xEA,
                                                  0xC7, 0x44, 0x24, 0x20, 0xFF, 0xFF, 0xFF, 0xFF, 0x48, 0x8D, 0x54, 0x24,
                                                  0x20, 0x41, 0x0F, 0xB6, 0xF9, 0x41, 0x8B, 0xF0, 0x48, 0x8B, 0xD9};
#define PRE_CLIENT_TRAVEL_GET_WORLD 0x36
#define PRE_CLIENT_TRAVEL_GAME_INSTANCE 0x3b /* mov rcx, [rax+disp32] */
#define PRE_CLIENT_TRAVEL_NOTIFY 0x51

static void fstring_text(const struct fstring *f, char *out, size_t size) {
    size_t i = 0;
    if (f && f->data && f->num > 1)
        for (; i + 1 < size && f->data[i]; i++) out[i] = f->data[i] < 0x80 ? (char)f->data[i] : '?';
    out[i] = 0;
}

static void __fastcall hook_pre_client_travel(void *pc, struct fstring *url, int travel_type, unsigned char seamless) {
    char text[200];
    fstring_text(url, text, sizeof text);
    fireteam_log("travel: PreClientTravel \"%s\" type %d seamless %u", text, travel_type, seamless);
    real_pre_client_travel(pc, url, travel_type, seamless);
}

static const char *hook_pre_client_travel_slots(void) {
    static char why[80];
    if (real_pre_client_travel) return "already hooked";
    int hits;
    unsigned char *fn = find_code(PRE_CLIENT_TRAVEL, sizeof PRE_CLIENT_TRAVEL, &hits);
    if (!fn) {
        snprintf(why, sizeof why, "PreClientTravel pattern matched %d times, left alone", hits);
        return why;
    }
    unsigned char *get_world = call_target(fn + PRE_CLIENT_TRAVEL_GET_WORLD);
    unsigned char *notify = call_target(fn + PRE_CLIENT_TRAVEL_NOTIFY);
    unsigned char *gi = fn + PRE_CLIENT_TRAVEL_GAME_INSTANCE;
    if (!get_world || !notify || !in_image(get_world) || !in_image(notify) || gi[0] != 0x48 || gi[1] != 0x8B ||
        gi[2] != 0x88)
        return "PreClientTravel body differs, left alone";
    actor_get_world = (get_world_t)get_world;
    notify_pre_client_travel = (notify_pre_client_travel_t)notify;
    game_instance_offset = *(int *)(gi + 3);
    real_pre_client_travel = (pre_client_travel_t)fn;
    int already;
    int swapped = swap_vtable_slots(fn, (void *)hook_pre_client_travel, &already);
    if (!swapped) {
        real_pre_client_travel = NULL;
        return already ? "already hooked" : "PreClientTravel is in no vtable, left alone";
    }
    snprintf(why, sizeof why, "hooked in %d vtables", swapped);
    return why;
}

/* UBlamEngineLoadingManagerEngineSubsystem's map-loaded callback (exe 0x7b47fe0
   on CU4). The Blam start registers it on a global map-load delegate, and
   when the map has loaded it starts the subsystem's loading tick, whose last
   step queues shell command 0/2 and lifts the loading screen. A joiner into a
   match under way loaded its map before its Blam game started, so the
   callback never ran and the screen stayed black (2026-10-03). It is found
   at its registration: lea r9, callback / mov r8, rbx / lea rcx, delegate /
   mov rdx, [rax] / mov [rbx+1a0h], rdx. */
typedef void(__fastcall *map_loaded_t)(void *loading_manager);
static map_loaded_t loading_manager_map_loaded;
static const unsigned char MAP_LOADED_SITE[] = {0x4C, 0x8D, 0x0D, 0, 0, 0, 0, 0x4C, 0x8B, 0xC3, 0x48, 0x8D, 0x0D, 0, 0, 0, 0,
                                                0x48, 0x8B, 0x10, 0x48, 0x89, 0x93, 0xA0, 0x01, 0x00, 0x00};
static const unsigned char MAP_LOADED_MASK[] = {1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0,
                                                1, 1, 1, 1, 1, 1, 1, 1, 1, 1};
/* push rbx/rbp/rsi/rdi; sub rsp, 48h; mov rdx, [rcx+1a8h] (its delegate handle) */
static const unsigned char MAP_LOADED_PROLOGUE[] = {0x40, 0x53, 0x55, 0x56, 0x57, 0x48, 0x83, 0xEC,
                                                    0x48, 0x48, 0x8B, 0x91, 0xA8, 0x01, 0x00, 0x00};

static const char *find_map_loaded(void) {
    static char why[80];
    int hits;
    unsigned char *site = find_code_masked(MAP_LOADED_SITE, MAP_LOADED_MASK, sizeof MAP_LOADED_SITE, &hits);
    if (!site) {
        snprintf(why, sizeof why, "map-loaded registration matched %d times", hits);
        return why;
    }
    unsigned char *fn = site + 7 + *(int *)(site + 3);
    if (!in_image(fn) || memcmp(fn, MAP_LOADED_PROLOGUE, sizeof MAP_LOADED_PROLOGUE) != 0)
        return "map-loaded callback differs";
    loading_manager_map_loaded = (map_loaded_t)fn;
    return "found";
}

/* The world's name is "Frontend": the menu, which never has a Blam game. */
static int world_is_frontend(unsigned char *world) {
    if (!world || !resolve()) return 0;
    unsigned long long frontend = 0;
    fname_ctor(&frontend, L"Frontend", FNAME_ADD, NULL);
    __try {
        return *(unsigned long long *)(world + 0x18) == frontend;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

/* --- A joiner's world before its Blam game ------------------------------- */

/* A client's world begins play when the GameState's bReplicatedHasBegunPlay
   arrives: AGameStateBase::OnRep_ReplicatedHasBegunPlay (exe 0x6055a30) calls
   AWorldSettings::NotifyBeginPlay (0x687d700, vtable +0x778), which runs
   BeginPlay on every actor. In a normal start the Blam game is up by then; a
   joiner into a match under way gets there first, and the pawn and player
   controller BeginPlays bind to Blam game objects that do not exist yet
   (2026-10-03, two crashes). While a FIND GAMES join is armed
   (mjolnir_stay_online), the first NotifyBeginPlay without a running Blam game
   is held, and mjolnir_jip_tick (once a second, from games.lua, on the game
   thread) lets it through once the game runs, or after JIP_HOLD_MS. */
typedef void(__fastcall *shell_command_t)(void *iface, char subtype, void *data);
static shell_command_t real_shell_command0, real_shell_object_command, real_shell_command3;
static void *volatile shell_iface;
typedef void(__fastcall *notify_begin_play_t)(void *world_settings);
static notify_begin_play_t real_notify_begin_play;
static void *volatile held_world_settings;
static DWORD held_since;
static volatile LONG jip_armed;
#define JIP_HOLD_MS 120000
#define JIP_NUDGE_MS 5000

/* AWorldSettings::NotifyBeginPlay's body after GetWorld: mov r15, rax / test
   byte [rax+13dh], 1 (the world's bBegunPlay) / jne. */
static const unsigned char NOTIFY_BEGIN_PLAY_BODY[] = {0x4C, 0x8B, 0xF8, 0xF6, 0x80, 0x3D, 0x01,
                                                       0x00, 0x00, 0x01, 0x0F, 0x85};
static const unsigned char NOTIFY_BEGIN_PLAY_PROLOGUE[] = {0x40, 0x55, 0x41, 0x57, 0x48, 0x8D, 0x6C, 0x24,
                                                           0xB1, 0x48, 0x81, 0xEC, 0xA8, 0x00, 0x00, 0x00};
#define NOTIFY_BEGIN_PLAY_BODY_AT 0x23

static void log_blam_game(const char *what, const struct blam_game *g) {
    fireteam_log("%s (engine %p, +40 %p, +50 %p, +60 %p)", what, g->engine, g->at40, g->at50, g->at60);
}

/* native\jip_held.txt exists while a world is held; games.lua then writes
   native\jip_map.txt, the held world's package path. */
static void held_flag(int on) {
    if (!dir[0]) find_dir();
    char path[MAX_PATH];
    snprintf(path, sizeof path, "%sjip_held.txt", dir);
    if (on) {
        FILE *f = fopen(path, "w");
        if (f) fclose(f);
    } else {
        remove(path);
        snprintf(path, sizeof path, "%sjip_map.txt", dir);
        remove(path);
    }
}

static void __fastcall hook_notify_begin_play(void *world_settings) {
    /* A world that begins play replaces any held one, which is gone or going
       (2026-10-03: a held lobby world was released after the match started,
       and crashed). */
    void *stale = InterlockedExchangePointer(&held_world_settings, NULL);
    if (stale && stale != world_settings) {
        held_flag(0);
        fireteam_log("world: a new world began; the held one is dropped");
    }
    if (jip_armed) {
        unsigned char *world = actor_get_world ? actor_get_world(world_settings) : NULL;
        if (world_is_frontend(world)) {
            /* The host's menu, on a lobby join: stay armed for its match. */
            real_notify_begin_play(world_settings);
            return;
        }
        InterlockedExchange(&jip_armed, 0);
        struct blam_game g = blam_game_now();
        if (!blam_game_running(&g)) {
            held_since = GetTickCount();
            held_world_settings = world_settings;
            held_flag(1);
            log_blam_game("world: begin play held until the Blam game runs", &g);
            return;
        }
        log_blam_game("world: begin play with the Blam game running", &g);
    }
    real_notify_begin_play(world_settings);
}

static const char *hook_notify_begin_play_slots(void) {
    static char why[80];
    if (real_notify_begin_play) return "already hooked";
    int hits;
    unsigned char *body = find_code(NOTIFY_BEGIN_PLAY_BODY, sizeof NOTIFY_BEGIN_PLAY_BODY, &hits);
    if (!body) {
        snprintf(why, sizeof why, "NotifyBeginPlay pattern matched %d times, left alone", hits);
        return why;
    }
    unsigned char *fn = body - NOTIFY_BEGIN_PLAY_BODY_AT;
    if (memcmp(fn, NOTIFY_BEGIN_PLAY_PROLOGUE, sizeof NOTIFY_BEGIN_PLAY_PROLOGUE) != 0)
        return "NotifyBeginPlay prologue differs, left alone";
    real_notify_begin_play = (notify_begin_play_t)fn;
    int already;
    int swapped = swap_vtable_slots(fn, (void *)hook_notify_begin_play, &already);
    if (!swapped) {
        real_notify_begin_play = NULL;
        return already ? "already hooked" : "NotifyBeginPlay is in no vtable, left alone";
    }
    snprintf(why, sizeof why, "hooked in %d vtables", swapped);
    return why;
}

/* The game left the session: a held world is going away, never release it. */
static void drop_held_world(const char *why) {
    if (InterlockedExchangePointer(&held_world_settings, NULL)) {
        held_flag(0);
        fireteam_log("world: held begin play dropped (%s)", why);
    }
}

/* Once a second from games.lua, on the game thread. */
/* After a held world is released: the loading manager's mode (+0xd8) and
   state (+0xd9; its tick queues command 0/2 at 6), and the GameState's
   experience component (CurrentExperience at +0xa8; its three bWaiting...
   bits at +0x118, which the tick's state 4 waits to see all set), logged on
   change for WATCH_MS. A joiner sat in state 1, mode 1, flags 00 (2026-10-03):
   the Blam start subscribes the manager to an engine event that sets mode 2
   (0x7b4a450 on CU4), which never came. Experiments, each logged: after
   NUDGE_MS in state 1 / mode 1, set mode 2 as that event would; after
   NUDGE_MS in state 4 without the three bits, set them. */
static unsigned char *watch_manager, *watch_experience;
static DWORD watch_until;
#define WATCH_MS 90000
#define NUDGE_MS 5000

typedef void(__fastcall *set_mode_t)(void *loading_manager);
static set_mode_t loading_manager_set_mode2;
/* lea rcx, [r13+48h] / mov r8, rbx / lea r9, set-mode-2 / lea rdx, [rbp+38h] / call */
static const unsigned char SET_MODE2_SITE[] = {0x49, 0x8D, 0x4D, 0x48, 0x4C, 0x8B, 0xC3, 0x4C, 0x8D, 0x0D,
                                               0,    0,    0,    0,    0x48, 0x8D, 0x55, 0x38, 0xE8};
static const unsigned char SET_MODE2_MASK[] = {1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 1};
/* mov eax, 2 / xchg [rcx+0d8h], al / ret */
static const unsigned char SET_MODE2_BODY[] = {0xB8, 0x02, 0x00, 0x00, 0x00, 0x86, 0x81, 0xD8, 0x00, 0x00, 0x00, 0xC3};

static set_mode_t find_set_mode2(void) {
    int hits;
    unsigned char *site = find_code_masked(SET_MODE2_SITE, SET_MODE2_MASK, sizeof SET_MODE2_SITE, &hits);
    if (!site) return NULL;
    unsigned char *fn = site + 7 + 7 + *(int *)(site + 10);
    if (!in_image(fn) || memcmp(fn, SET_MODE2_BODY, sizeof SET_MODE2_BODY) != 0) return NULL;
    return (set_mode_t)fn;
}

/* The simulation's two network sessions (sim 0x2c3cea0 on CU4: a pointer to
   them, 0x5b9e8 bytes apart), read from its network tick: imul rcx, rbx,
   5b9e8h / add rcx, [rip+sessions]. Per peer (0x128 apart), the properties a
   host compares (2026-10-03, PC 1's view of a joiner: +0x10c 3 not 4,
   +0x118 unset, +0x164 0 not 3). */
static unsigned char **sim_sessions;

static void find_sim_sessions(void) {
    static int tried;
    if (tried) return;
    tried = 1;
    unsigned char *base = (unsigned char *)GetModuleHandleA("HaloSimulation_tag_release.dll");
    if (!base) return;
    static const unsigned char SESSIONS[] = {0x48, 0x69, 0xCB, 0xE8, 0xB9, 0x05, 0x00, 0x48, 0x03, 0x0D};
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_SECTION_HEADER *sec = IMAGE_FIRST_SECTION(nt);
    unsigned char *found = NULL;
    int hits = 0;
    for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; i++, sec++) {
        if (!(sec->Characteristics & IMAGE_SCN_MEM_EXECUTE)) continue;
        unsigned char *p = base + sec->VirtualAddress, *end = p + sec->Misc.VirtualSize - sizeof SESSIONS - 4;
        for (; p <= end; p++)
            if (p[0] == 0x48 && memcmp(p, SESSIONS, sizeof SESSIONS) == 0) {
                found = p;
                hits++;
            }
    }
    if (hits == 1) sim_sessions = (unsigned char **)(found + 14 + *(int *)(found + 10));
    fireteam_log("world: simulation sessions %s", hits == 1 ? "found" : "not found");
}

/* "[session] life <state> mask <m> | peer: map <+10c> inst <+118> start <+164> f <+174> ..." for both sessions */
static void sim_session_line(char *line, size_t size) {
    size_t at = 0;
    line[0] = 0;
    find_sim_sessions();
    if (!sim_sessions) return;
    __try {
        for (int si = 0; si < 2 && at + 64 < size; si++) {
            unsigned char *s = *sim_sessions + si * 0x5b9e8;
            unsigned mask = *(unsigned *)(s + 0x5c);
            at += (size_t)snprintf(line + at, size - at, "%s[%d] life %d mask %x hdr40 %d %d %d", si ? " " : "", si,
                                   *(int *)(s + 0x5b460), mask, *(int *)(s + 0x40), *(int *)(s + 0x44),
                                   *(int *)(s + 0x48));
            for (int i = 0; i < 17 && at + 64 < size; i++) {
                if (!(mask & (1u << i))) continue;
                unsigned char *peer = s + i * 0x128;
                at += (size_t)snprintf(line + at, size - at, " | %d: map %u inst %llx start %u f %u", i,
                                       *(unsigned *)(peer + 0x10c), *(unsigned long long *)(peer + 0x118),
                                       *(unsigned *)(peer + 0x164), *(unsigned *)(peer + 0x174));
            }
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        snprintf(line, size, "unreadable");
    }
}

/* Experiment: a joiner's own peer entry never says what the host's does
   (map status 3 not 4, no game instance, start status 0), so the host never
   spawns it. Copy those three from the host's entry into the local one (the
   session's local peer index is at +0x40) and see what the simulation does
   with it. Once per session; logged. */
static void adopt_host_peer_properties(void) {
    static int adopted;
    static DWORD mismatch_since;
    if (adopted || !sim_sessions) return;
    __try {
        for (int si = 0; si < 2; si++) {
            unsigned char *s = *sim_sessions + si * 0x5b9e8;
            unsigned mask = *(unsigned *)(s + 0x5c);
            if (!mask) continue;
            /* The joining machine's entry carries +0x174 = 1 in both machines'
               views (2026-10-03); the session's +0x40 is not it on a client. */
            int local = -1;
            for (int i = 0; i < 17; i++)
                if ((mask & (1u << i)) && *(unsigned *)(s + i * 0x128 + 0x174) == 1) local = i;
            if (local < 0) continue;
            unsigned char *mine = s + local * 0x128, *host = NULL;
            for (int i = 0; i < 17; i++)
                if (i != local && (mask & (1u << i)) && *(unsigned *)(s + i * 0x128 + 0x10c) == 4) host = s + i * 0x128;
            if (!host || *(unsigned *)(mine + 0x10c) == 4) {
                mismatch_since = 0;
                return;
            }
            DWORD now = GetTickCount();
            if (!mismatch_since) mismatch_since = now;
            if (now - mismatch_since < NUDGE_MS) return;
            adopted = 1;
            fireteam_log("world: session %d local peer %d still map %u; adopting the host's map status, game instance and start status",
                         si, local, *(unsigned *)(mine + 0x10c));
            *(unsigned *)(mine + 0x10c) = *(unsigned *)(host + 0x10c);
            *(unsigned long long *)(mine + 0x118) = *(unsigned long long *)(host + 0x118);
            *(unsigned *)(mine + 0x164) = *(unsigned *)(host + 0x164);
            return;
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        adopted = 1;
        fireteam_log("world: adopting the host's peer properties failed (unreadable)");
    }
}

/* A client asks the host to take new peer properties through the session's
   properties object (vtable sim 0x8c1d10 on CU4, its [+0x18] the session):
   slot +0x48 (sim 0x528c30) copies the 0x110-byte block into the pending
   request and marks it for sending when this machine is an established
   client. A joiner's properties never change from "map 3", so nothing ever
   asks; this asks with the block from its own peer entry (+0x10), which the
   adoption above has brought to the host's map status and game instance.
   Found by its code (prologue / call / body, the call displacements masked)
   and the one read-only slot that holds it. */
typedef void(__fastcall *request_properties_t)(void *properties_object, const void *properties);

static unsigned char *find_in_module(unsigned char *base, const unsigned char *pattern, const unsigned char *mask,
                                     size_t length, int executable, int *hits) {
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_SECTION_HEADER *sec = IMAGE_FIRST_SECTION(nt);
    unsigned char *found = NULL;
    *hits = 0;
    for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; i++, sec++) {
        int exec = (sec->Characteristics & IMAGE_SCN_MEM_EXECUTE) != 0;
        if (exec != executable || (!executable && (sec->Characteristics & IMAGE_SCN_MEM_WRITE))) continue;
        unsigned char *p = base + sec->VirtualAddress, *end = p + sec->Misc.VirtualSize - length;
        for (; p <= end; p++) {
            size_t k = 0;
            for (; k < length; k++)
                if ((!mask || mask[k]) && p[k] != pattern[k]) break;
            if (k == length) {
                found = p;
                (*hits)++;
            }
        }
    }
    return *hits == 1 ? found : NULL;
}

static const unsigned char REQUEST_PROPERTIES[] = {
    0x40, 0x53, 0x48, 0x83, 0xEC, 0x20, 0x4C, 0x8B, 0xDA, 0x48, 0x8B, 0xD9, 0xE8, 0, 0, 0, 0,
    0x48, 0x8B, 0xCB, 0x84, 0xC0, 0x74, 0x12, 0x48, 0x8B, 0x03, 0x49, 0x8B, 0xD3, 0x48, 0x83, 0xC4,
    0x20, 0x5B, 0x48, 0xFF, 0xA0, 0xA0, 0x00, 0x00, 0x00, 0xE8, 0, 0, 0, 0, 0x84, 0xC0, 0x0F, 0x84,
    0xD5, 0x00, 0x00, 0x00, 0xC4, 0xC1, 0x7C, 0x10, 0x03, 0x48, 0x8D, 0x93, 0x98, 0x01, 0x00, 0x00};
static const unsigned char REQUEST_PROPERTIES_MASK[] = {
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1};

__declspec(dllexport) int mjolnir_sim_push_properties(void *L) {
    (void)L;
    if (!dir[0]) find_dir();
    unsigned char *sim = (unsigned char *)GetModuleHandleA("HaloSimulation_tag_release.dll");
    if (!sim) {
        fireteam_log("props: no simulation DLL");
        return 0;
    }
    int hits;
    unsigned char *fn = find_in_module(sim, REQUEST_PROPERTIES, REQUEST_PROPERTIES_MASK, sizeof REQUEST_PROPERTIES, 1, &hits);
    if (!fn) {
        fireteam_log("props: request-properties code matched %d times", hits);
        return 0;
    }
    void *fn_value = fn;
    unsigned char *slot = find_in_module(sim, (const unsigned char *)&fn_value, NULL, sizeof fn_value, 0, &hits);
    if (!slot) {
        fireteam_log("props: request-properties is in %d read-only slots", hits);
        return 0;
    }
    void *vtable = slot - 0x48;
    find_sim_sessions();
    if (!sim_sessions) {
        fireteam_log("props: no simulation sessions");
        return 0;
    }
    __try {
        for (int si = 0; si < 2; si++) {
            unsigned char *s = *sim_sessions + si * 0x5b9e8;
            unsigned mask = *(unsigned *)(s + 0x5c);
            if (!mask) continue;
            int local = -1;
            unsigned char *host = NULL;
            for (int i = 0; i < 17; i++) {
                if (!(mask & (1u << i))) continue;
                if (*(unsigned *)(s + i * 0x128 + 0x174) == 1) local = i;
                else if (*(unsigned *)(s + i * 0x128 + 0x10c) == 4) host = s + i * 0x128;
            }
            if (local < 0 || !host) continue;
            unsigned char *mine = s + local * 0x128;
            *(unsigned *)(mine + 0x10c) = *(unsigned *)(host + 0x10c);
            *(unsigned long long *)(mine + 0x118) = *(unsigned long long *)(host + 0x118);
            *(unsigned *)(mine + 0x164) = *(unsigned *)(host + 0x164);
            unsigned char properties[0x110];
            memcpy(properties, mine + 0x10, sizeof properties);
            int asked = 0;
            for (unsigned char *q = s; q < s + 0x5b9e8; q += 8) {
                if (*(void **)q != vtable || *(unsigned char **)(q + 0x18) != s) continue;
                fireteam_log("props: session %d local peer %d: asking %p (session +%llx) to send map %u inst %llx start %u",
                             si, local, (void *)q, (unsigned long long)(q - s), *(unsigned *)(mine + 0x10c),
                             *(unsigned long long *)(mine + 0x118), *(unsigned *)(mine + 0x164));
                ((request_properties_t)fn)(q, properties);
                fireteam_log("props: flags now %02x", q[0x80]);
                asked++;
            }
            if (!asked) {
                fireteam_log("props: session %d (%p) has no properties object inside it; searching wider", si, (void *)s);
                /* The simulation's writable sections, and a window around the
                   session array. */
                IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(sim + ((IMAGE_DOS_HEADER *)sim)->e_lfanew);
                IMAGE_SECTION_HEADER *sec = IMAGE_FIRST_SECTION(nt);
                int shown = 0;
                for (unsigned k = 0; k < nt->FileHeader.NumberOfSections; k++, sec++) {
                    if (!(sec->Characteristics & IMAGE_SCN_MEM_WRITE)) continue;
                    for (unsigned char *q = sim + sec->VirtualAddress; q + 0x20 <= sim + sec->VirtualAddress + sec->Misc.VirtualSize; q += 8) {
                        if (*(void **)q != vtable || shown >= 12) continue;
                        shown++;
                        fireteam_log("props: object %p (sim+%llx) +18 %p +20 %p", (void *)q, (unsigned long long)(q - sim),
                                     *(void **)(q + 0x18), *(void **)(q + 0x20));
                        if (*(unsigned char **)(q + 0x18) == s) {
                            fireteam_log("props: it belongs to session %d; asking it", si);
                            ((request_properties_t)fn)(q, properties);
                            fireteam_log("props: flags now %02x", q[0x80]);
                        }
                    }
                }
                if (!shown) fireteam_log("props: no object with that vtable in the simulation's data");
                /* Heap objects the session points to. */
                int pointed = 0;
                for (unsigned char *q = s; q < s + 0x5b9e8 && pointed < 12; q += 8) {
                    unsigned char *target = *(unsigned char **)q;
                    if ((unsigned long long)target < 0x10000 || ((unsigned long long)target & 7)) continue;
                    MEMORY_BASIC_INFORMATION info;
                    if (!VirtualQuery(target, &info, sizeof info) || info.State != MEM_COMMIT ||
                        (info.Protect & (PAGE_NOACCESS | PAGE_GUARD)))
                        continue;
                    if (*(void **)target != vtable) continue;
                    pointed++;
                    fireteam_log("props: session +%llx points to object %p, its +18 %p", (unsigned long long)(q - s),
                                 (void *)target, *(void **)(target + 0x18));
                    if (*(unsigned char **)(target + 0x18) == s && pointed == 1) {
                        fireteam_log("props: asking it");
                        ((request_properties_t)fn)(target, properties);
                        fireteam_log("props: flags now %02x", target[0x80]);
                    }
                }
                if (!pointed) fireteam_log("props: the session points to no object with that vtable");
                /* Any word in the session that points into the vtable's neighbourhood. */
                int nearby = 0;
                for (unsigned char *q = s; q < s + 0x5b9e8 && nearby < 16; q += 8) {
                    unsigned char *v = *(unsigned char **)q;
                    if (v >= (unsigned char *)vtable - 0x50 && v <= (unsigned char *)vtable + 0x50) {
                        nearby++;
                        fireteam_log("props: session +%llx holds vtable%+lld; its +18 %p", (unsigned long long)(q - s),
                                     (long long)(v - (unsigned char *)vtable), *(void **)(q + 0x18));
                    }
                }
            }
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        fireteam_log("props: failed (exception %08lx)", GetExceptionCode());
    }
    return 0;
}

/* A client's peer properties are rebuilt from simulation globals (sim
   0x4b7db0 on CU4): the map status (0xca2824, 4 = loaded), its progress
   (0xca2828) and the game instance (0xca2ef0). A normal start sets them while
   loading the game; a joiner's say 3 and nothing, so the host never counts it
   as in the game. Found where the builder reads them: mov eax, [map] / mov
   [rsp+0d4h], eax / mov eax, [progress] / mov [rsp+0d8h], eax / mov rax,
   [instance] / mov [rsp+0e0h], rax. This sets them as the host's peer entry
   has them (experiment; logged). */
static const unsigned char GAME_GLOBALS[] = {0x8B, 0x05, 0, 0, 0, 0, 0x89, 0x84, 0x24, 0xD4, 0x00, 0x00, 0x00,
                                             0x8B, 0x05, 0, 0, 0, 0, 0x89, 0x84, 0x24, 0xD8, 0x00, 0x00, 0x00,
                                             0x48, 0x8B, 0x05, 0, 0, 0, 0, 0x48, 0x89, 0x84, 0x24, 0xE0, 0x00, 0x00, 0x00};
static const unsigned char GAME_GLOBALS_MASK[] = {1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1,
                                                  1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1,
                                                  1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1};

__declspec(dllexport) int mjolnir_sim_adopt_game(void *L) {
    (void)L;
    if (!dir[0]) find_dir();
    unsigned char *sim = (unsigned char *)GetModuleHandleA("HaloSimulation_tag_release.dll");
    if (!sim) return 0;
    int hits;
    unsigned char *at = find_in_module(sim, GAME_GLOBALS, GAME_GLOBALS_MASK, sizeof GAME_GLOBALS, 1, &hits);
    if (!at) {
        fireteam_log("game: globals code matched %d times", hits);
        return 0;
    }
    unsigned *map_status = (unsigned *)(at + 6 + *(int *)(at + 2));
    unsigned *progress = (unsigned *)(at + 13 + 6 + *(int *)(at + 15));
    unsigned long long *instance = (unsigned long long *)(at + 26 + 7 + *(int *)(at + 29));
    find_sim_sessions();
    unsigned long long host_instance = 0;
    unsigned host_map = 0;
    __try {
        for (int si = 0; si < 2 && sim_sessions && !host_instance; si++) {
            unsigned char *s = *sim_sessions + si * 0x5b9e8;
            unsigned mask = *(unsigned *)(s + 0x5c);
            for (int i = 0; i < 17; i++)
                if ((mask & (1u << i)) && *(unsigned *)(s + i * 0x128 + 0x174) == 0 &&
                    *(unsigned *)(s + i * 0x128 + 0x10c) == 4) {
                    host_instance = *(unsigned long long *)(s + i * 0x128 + 0x118);
                    host_map = *(unsigned *)(s + i * 0x128 + 0x10c);
                }
        }
        fireteam_log("game: map status %u progress %u instance %llx; the host's map %u instance %llx", *map_status,
                     *progress, *instance, host_map, host_instance);
        if (host_instance) {
            *map_status = host_map;
            *progress = 100;
            *instance = host_instance;
            fireteam_log("game: now map status %u progress %u instance %llx", *map_status, *progress, *instance);
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        fireteam_log("game: failed (exception %08lx)", GetExceptionCode());
    }
    return 0;
}

/* Undo adopt_host_peer_properties: put the joiner's own entry back to what
   it last told the host, so the properties builder sees a change to send. */
__declspec(dllexport) int mjolnir_sim_restore_own_entry(void *L) {
    (void)L;
    if (!dir[0]) find_dir();
    find_sim_sessions();
    __try {
        for (int si = 0; si < 2 && sim_sessions; si++) {
            unsigned char *s = *sim_sessions + si * 0x5b9e8;
            unsigned mask = *(unsigned *)(s + 0x5c);
            for (int i = 0; i < 17; i++)
                if ((mask & (1u << i)) && *(unsigned *)(s + i * 0x128 + 0x174) == 1) {
                    unsigned char *mine = s + i * 0x128;
                    *(unsigned *)(mine + 0x10c) = 3;
                    *(unsigned long long *)(mine + 0x118) = ~0ull;
                    *(unsigned *)(mine + 0x164) = 0;
                    fireteam_log("game: session %d peer %d entry restored to map 3, no instance", si, i);
                }
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        fireteam_log("game: restore failed");
    }
    return 0;
}

static void watch_loading(void) {
    static int last_mode = -1, last_state = -1, last_flags = -1;
    static void *last_experience = (void *)1;
    static DWORD state_since;
    static int mode_pushed, flags_pushed;
    if (!watch_until || (long)(GetTickCount() - watch_until) > 0) return;
    int mode = -1, state = -1, flags = -1;
    void *experience = NULL;
    __try {
        if (watch_manager) {
            mode = watch_manager[0xd8];
            state = watch_manager[0xd9];
        }
        if (watch_experience) {
            flags = watch_experience[0x118];
            experience = *(void **)(watch_experience + 0xa8);
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        watch_until = 0;
        fireteam_log("world: loading watch stopped (unreadable)");
        return;
    }
    DWORD now = GetTickCount();
    if (state != last_state || mode != last_mode) state_since = now;
    if (mode != last_mode || state != last_state || flags != last_flags || experience != last_experience) {
        last_mode = mode;
        last_state = state;
        last_flags = flags;
        last_experience = experience;
        fireteam_log("world: loading manager mode %d state %d, experience %p flags %02x", mode, state, experience,
                     flags);
    }
    static char last_session[600];
    char session[600];
    sim_session_line(session, sizeof session);
    if (strcmp(session, last_session) != 0) {
        snprintf(last_session, sizeof last_session, "%s", session);
        fireteam_log("world: simulation session %s", session);
    }
    if (state == 0 && mode == 2) adopt_host_peer_properties();
    if (state == 1 && mode == 1 && now - state_since > NUDGE_MS && !mode_pushed) {
        mode_pushed = 1;
        if (!loading_manager_set_mode2) loading_manager_set_mode2 = find_set_mode2();
        if (loading_manager_set_mode2) {
            fireteam_log("world: loading manager waited %lu ms in mode 1; setting mode 2", (unsigned long)(now - state_since));
            loading_manager_set_mode2(watch_manager);
        } else {
            fireteam_log("world: loading manager's set-mode-2 not found");
        }
    }
    if (state == 4 && flags >= 0 && (flags & 7) != 7 && now - state_since > NUDGE_MS && !flags_pushed) {
        flags_pushed = 1;
        fireteam_log("world: loading manager waited %lu ms for the experience; setting its three bits",
                     (unsigned long)(now - state_since));
        __try {
            watch_experience[0x118] = (unsigned char)((flags | 7) & ~0x10);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            fireteam_log("world: experience flags unwritable");
        }
    }
}

__declspec(dllexport) int mjolnir_jip_tick(void *L) {
    (void)L;
    watch_loading();
    void *ws = held_world_settings;
    if (!ws) return 0;
    struct blam_game g = blam_game_now();
    static struct blam_game last;
    if (memcmp(&g, &last, sizeof g) != 0) {
        log_blam_game("world: Blam game parts now", &g);
        last = g;
    }
    DWORD waited = GetTickCount() - held_since;
    /* The joiner never travelled, so replay the travel's notification for the
       map it is in, once games.lua has said which map that is. */
    static void *replayed;
    if (!blam_game_running(&g) && waited > JIP_NUDGE_MS && replayed != ws) {
        char map[260] = "", manager_line[64] = "", experience_line[64] = "";
        char path[MAX_PATH];
        snprintf(path, sizeof path, "%sjip_map.txt", dir);
        FILE *f = fopen(path, "r");
        if (f) {
            if (!fgets(map, sizeof map, f)) map[0] = 0;
            if (!fgets(manager_line, sizeof manager_line, f)) manager_line[0] = 0;
            if (!fgets(experience_line, sizeof experience_line, f)) experience_line[0] = 0;
            fclose(f);
        }
        map[strcspn(map, "\r\n")] = 0;
        unsigned long long manager = _strtoui64(manager_line, NULL, 16);
        watch_manager = (unsigned char *)(uintptr_t)manager;
        watch_experience = (unsigned char *)(uintptr_t)_strtoui64(experience_line, NULL, 16);
        unsigned char *world = actor_get_world ? actor_get_world(ws) : NULL;
        void *gi = world && game_instance_offset ? *(void **)(world + game_instance_offset) : NULL;
        if (map[0] && gi && notify_pre_client_travel) {
            replayed = ws;
            wchar_t wide[260];
            int n = 0;
            for (; map[n] && n < 259; n++) wide[n] = (unsigned char)map[n];
            wide[n] = 0;
            struct fstring url = {wide, n + 1, n + 1};
            fireteam_log("world: no Blam game %lu ms in; replaying NotifyPreClientTravel \"%s\" (relative, seamless)",
                         (unsigned long)waited, map);
            notify_pre_client_travel(gi, &url, 2, 1);
            /* Its map has long loaded: run the loading manager's map-loaded
               step the Blam start just registered for. */
            if (!loading_manager_map_loaded) fireteam_log("world: map-loaded callback: %s", find_map_loaded());
            void **mgr = (void **)(uintptr_t)manager;
            if (mgr && loading_manager_map_loaded && in_image(*mgr)) {
                fireteam_log("world: running the loading manager's map-loaded step (%p)", (void *)mgr);
                loading_manager_map_loaded(mgr);
            } else {
                fireteam_log("world: no loading manager to run the map-loaded step on (%p)", (void *)mgr);
            }
        } else if (waited > JIP_NUDGE_MS + 10000 && replayed != ws) {
            replayed = ws;
            fireteam_log("world: cannot replay the travel (map \"%s\", game instance %p)", map, gi);
        }
    }
    if (!blam_game_running(&g) && waited < JIP_HOLD_MS) return 0;
    if (InterlockedCompareExchangePointer(&held_world_settings, NULL, ws) != ws) return 0;
    held_flag(0);
    watch_until = GetTickCount() + WATCH_MS;
    fireteam_log("world: begin play released after %lu ms (%s)", (unsigned long)waited,
                 blam_game_running(&g) ? "the Blam game runs" : "no Blam game, gave up waiting");
    real_notify_begin_play(ws);
    return 0;
}

/* Logs the Blam game's parts now (a diagnostic; game thread only). */
__declspec(dllexport) int mjolnir_blam_state(void *L) {
    (void)L;
    if (!dir[0]) find_dir();
    const char *why = NULL;
    if (!module_get && !find_pawn_begin_play(&why)) {
        fireteam_log("blam: %s", why);
        return 0;
    }
    struct blam_game g = blam_game_now();
    log_blam_game("blam: now", &g);
    char session[600];
    sim_session_line(session, sizeof session);
    fireteam_log("blam: simulation session %s", session);
    return 0;
}

/* --- The Blam shell's command queue ---------------------------------------- */

/* The simulation DLL's one export, CreateBlamEngineShell, builds the shell the
   exe drives the Blam engine through. Its second interface (shell +0x140,
   vtable 0x7b0610 in the DLL on CU4) queues commands for the network tick
   (slot 0, sim 0xe670): slot +0x08 queues type 0 (sim 0xe140: (iface,
   subtype, data), data only for subtype 0xb), slot +0x10 builds object
   commands (sim 0xe2a0), slot +0x20 queues type 3 (sim 0xe510). Command 0/0
   resets the session flow to state 1 and pulls the target session from the
   exe (sim 0xf4b0); the flow then queues the simulation's join (sim
   0x4f14e0), which sends join-request. A joiner into a match under way never
   sent one (2026-10-03): these hooks log every command the exe queues, with
   the exe frames that queued it, and mjolnir_sim_command queues one by hand. */

static void log_shell_command(const char *what, void *iface, char subtype) {
    shell_iface = iface;
    static char last_what[16];
    static int last_subtype = -1000;
    static DWORD last_at;
    DWORD now = GetTickCount();
    if (strcmp(last_what, what) == 0 && last_subtype == subtype && now - last_at < 2000) return;
    snprintf(last_what, sizeof last_what, "%s", what);
    last_subtype = subtype;
    last_at = now;
    char line[CALLER_STACK];
    caller_stack(line);
    fireteam_log("shell: %s %d from%s", what, subtype, line);
}

static void __fastcall hook_shell_command0(void *iface, char subtype, void *data) {
    log_shell_command("command 0", iface, subtype);
    real_shell_command0(iface, subtype, data);
}

static void __fastcall hook_shell_object_command(void *iface, char subtype, void *data) {
    log_shell_command("object", iface, subtype);
    real_shell_object_command(iface, subtype, data);
}

static void __fastcall hook_shell_command3(void *iface, char subtype, void *data) {
    log_shell_command("command 3", iface, subtype);
    real_shell_command3(iface, subtype, data);
}

/* `fn` holds "mov byte [rax+10h], type" within its first 0x200 bytes. */
static int queues_type(const unsigned char *fn, unsigned char type) {
    const unsigned char want[] = {0xC6, 0x40, 0x10, type};
    for (int i = 0; i < 0x200; i++)
        if (memcmp(fn + i, want, sizeof want) == 0) return 1;
    return 0;
}

static const char *hook_shell_commands(void) {
    if (real_shell_command0) return "already hooked";
    HMODULE sim = GetModuleHandleA("HaloSimulation_tag_release.dll");
    if (!sim) return "the simulation DLL is not loaded";
    unsigned char *create = (unsigned char *)GetProcAddress(sim, "CreateBlamEngineShell");
    if (!create) return "CreateBlamEngineShell not exported";
    /* lea rax, [vtable] ... mov [rbx+140h], rax */
    static const unsigned char STORE[] = {0x48, 0x89, 0x83, 0x40, 0x01, 0x00, 0x00};
    unsigned char *store = NULL, *lea = NULL;
    for (int i = 0; i < 0x180 && !store; i++)
        if (memcmp(create + i, STORE, sizeof STORE) == 0) store = create + i;
    for (unsigned char *q = store ? store - 3 : NULL; q && q > create && !lea; q--)
        if (q[0] == 0x48 && q[1] == 0x8D && q[2] == 0x05) lea = q;
    if (!lea) return "shell interface not found, left alone";
    void **vtable = (void **)(lea + 7 + *(int *)(lea + 3));
    unsigned char *cmd0 = (unsigned char *)vtable[1], *obj = (unsigned char *)vtable[2],
                  *cmd3 = (unsigned char *)vtable[4];
    if (!queues_type(cmd0, 0) || !queues_type(cmd3, 3)) return "shell command methods differ, left alone";
    DWORD old;
    if (!VirtualProtect(vtable, 5 * sizeof *vtable, PAGE_READWRITE, &old)) return "VirtualProtect failed";
    real_shell_command0 = (shell_command_t)cmd0;
    real_shell_object_command = (shell_command_t)obj;
    real_shell_command3 = (shell_command_t)cmd3;
    vtable[1] = (void *)hook_shell_command0;
    vtable[2] = (void *)hook_shell_object_command;
    vtable[4] = (void *)hook_shell_command3;
    VirtualProtect(vtable, 5 * sizeof *vtable, old, &old);
    return "hooked";
}

/* native\sim_command.txt: "0 <subtype>" queues that type-0 command on the
   shell (never 11, which carries data). A test lever for a joiner's
   simulation that never starts its join. */
__declspec(dllexport) int mjolnir_sim_command(void *L) {
    (void)L;
    if (!dir[0]) find_dir();
    char path[MAX_PATH];
    snprintf(path, sizeof path, "%ssim_command.txt", dir);
    FILE *f = fopen(path, "r");
    int type = -1, subtype = -1;
    if (f) {
        if (fscanf(f, "%d %d", &type, &subtype) != 2) type = -1;
        fclose(f);
    }
    void *iface = shell_iface;
    if (type != 0 || subtype < 0 || subtype > 16 || subtype == 11 || !iface || !real_shell_command0) {
        fireteam_log("shell: no command queued (type %d subtype %d, shell %p)", type, subtype, iface);
        return 0;
    }
    fireteam_log("shell: queueing command 0 %d by hand", subtype);
    real_shell_command0(iface, (char)subtype, NULL);
    return 0;
}

/* native\stay_online.txt: "1" before joining a public game from FIND GAMES
   (games.lua), "2" when that game is in a match. A joiner landing in a
   session that is already running took the same one-member branch and left
   within a second; it gets the branch patch
   alone, without keep_lobby's refusals (a refused leave on a normal quit
   retries without pause). */
__declspec(dllexport) int mjolnir_stay_online(void *L) {
    (void)L;
    if (!dir[0]) find_dir();
    char path[MAX_PATH];
    snprintf(path, sizeof path, "%sstay_online.txt", dir);
    FILE *f = fopen(path, "r");
    int value = 0;
    if (f) {
        if (fscanf(f, "%d", &value) != 1) value = 0;
        fclose(f);
    }
    fireteam_log("session: alone, stay online: %s", stay_online_alone(value || keep_lobby));
    /* 2: the game joined is in a match; its world's begin play waits for the
       Blam game. 1: a lobby join, whose host's menu world never has one. */
    InterlockedExchange(&jip_armed, value ? 1 : 0);
    if (value) fireteam_log("world: a match world that begins before its Blam game will wait for it");
    return 0;
}

/* native\keep_lobby.txt: "1" while the host's game is public (games.lua), so the
   game cannot leave its lobby (a match started alone would); "0" otherwise. */
__declspec(dllexport) int mjolnir_keep_lobby(void *L) {
    (void)L;
    if (!dir[0]) find_dir();
    char path[MAX_PATH];
    snprintf(path, sizeof path, "%skeep_lobby.txt", dir);
    FILE *f = fopen(path, "r");
    int value = 0;
    if (f) {
        if (fscanf(f, "%d", &value) != 1) value = 0;
        fclose(f);
    }
    InterlockedExchange(&keep_lobby, value ? 1 : 0);
    snprintf(path, sizeof path, "%sjoin_in_progress.txt", dir);
    f = fopen(path, "r");
    int jip = 0;
    if (f) {
        if (fscanf(f, "%d", &jip) != 1) jip = 0;
        fclose(f);
    }
    InterlockedExchange(&join_in_progress, jip ? 1 : 0);
    if (jip) fireteam_log("login: join-in-progress experiment on");
    fireteam_log("lobby: keep while public: %s; a host alone: %s", value ? "yes" : "no", stay_online_alone(value));
    if (value) fireteam_log("PreLogin (joins into a public match under way): %s", hook_pre_login_slots());
    return 0;
}

/* native\join_request.txt: "<connection string> [<host SteamID64>]". The join
   goes out on the next online tick; native\join_reply.txt says how it went. */
__declspec(dllexport) int mjolnir_join(void *L) {
    (void)L;
    if (!dir[0]) find_dir();
    char path[MAX_PATH];
    snprintf(path, sizeof path, "%sjoin_reply.txt", dir);
    remove(path);
    snprintf(path, sizeof path, "%sjoin_request.txt", dir);
    const char *problem = NULL;
    struct join_request *req = (struct join_request *)calloc(1, sizeof *req);
    FILE *f = fopen(path, "r");
    if (!req) {
        problem = "out of memory";
    } else if (!real_online_tick) {
        problem = "the online tick is not hooked";
    } else if (!f) {
        problem = "no request";
    } else if (fscanf(f, "%4095s %llu", req->connect, &req->friend_id) < 1 || !req->connect[0]) {
        problem = "no connection string in the request";
    }
    if (f) fclose(f);
    if (problem) {
        char reply[96];
        snprintf(reply, sizeof reply, "error %s\n", problem);
        write_reply("join_reply.txt", reply, strlen(reply));
        free(req);
        return 0;
    }
    fireteam_log("join: queued, %u characters", (unsigned)strlen(req->connect));
    free(InterlockedExchangePointer((void *volatile *)&pending_join, req));
    return 0;
}

/* --- The hub ------------------------------------------------------------- */

#include <winhttp.h>
#pragma comment(lib, "winhttp.lib")

#define HUB_DEFAULT L"https://mjolnircore.com/api/v1"

struct hub_call {
    char id[40];
    char method[8];
    char path[1024];
    char *body;
};

/* The key the launcher paired, from its hub_auth.json, or "". */
static void launcher_key(char *key, size_t size) {
    key[0] = 0;
    char path[MAX_PATH];
    const char *appdata = getenv("APPDATA");
    if (!appdata) return;
    snprintf(path, sizeof path, "%s\\com.devnull9090.mjolnir-launcher\\hub_auth.json", appdata);
    FILE *f = fopen(path, "rb");
    if (!f) return;
    char text[8192];
    size_t n = fread(text, 1, sizeof text - 1, f);
    fclose(f);
    text[n] = 0;
    char *at = strstr(text, "\"key\"");
    if (!at || !(at = strchr(at + 5, '"'))) return;
    at++;
    size_t i = 0;
    while (at[i] && at[i] != '"' && i + 1 < size) {
        key[i] = at[i];
        i++;
    }
    key[i] = 0;
}

static void hub_reply(const struct hub_call *call, unsigned status, const char *body, size_t length) {
    char name[64], head[32];
    snprintf(name, sizeof name, "hub_reply_%s.txt", call->id);
    int h = snprintf(head, sizeof head, "%u\n", status);
    char *text = (char *)malloc((size_t)h + length);
    if (!text) return;
    memcpy(text, head, (size_t)h);
    memcpy(text + h, body, length);
    write_reply(name, text, (size_t)h + length);
    free(text);
}

static void hub_error(const struct hub_call *call, const char *what) {
    char body[160];
    int n = snprintf(body, sizeof body, "{\"error\":\"%s (%lu)\"}", what, GetLastError());
    hub_reply(call, 0, body, (size_t)n);
}

static DWORD WINAPI hub_worker(LPVOID arg) {
    struct hub_call *call = (struct hub_call *)arg;
    wchar_t base[512], url[2048], wmethod[8];
    const char *override = getenv("MJOLNIR_HUB_URL");
    if (!override || MultiByteToWideChar(CP_UTF8, 0, override, -1, base, 512) <= 0) wcscpy(base, HUB_DEFAULT);
    wchar_t wpath[1024];
    MultiByteToWideChar(CP_UTF8, 0, call->path, -1, wpath, 1024);
    MultiByteToWideChar(CP_UTF8, 0, call->method, -1, wmethod, 8);
    _snwprintf(url, 2048, L"%s%s", base, wpath);
    url[2047] = 0;

    URL_COMPONENTS parts;
    wchar_t host[256], object[2048];
    memset(&parts, 0, sizeof parts);
    parts.dwStructSize = sizeof parts;
    parts.lpszHostName = host;
    parts.dwHostNameLength = 256;
    parts.lpszUrlPath = object;
    parts.dwUrlPathLength = 2048;
    parts.dwExtraInfoLength = (DWORD)-1;
    HINTERNET session = NULL, connection = NULL, request = NULL;
    if (!WinHttpCrackUrl(url, 0, 0, &parts)) {
        hub_error(call, "bad hub URL");
        goto done;
    }
    if (parts.lpszExtraInfo && parts.dwExtraInfoLength) wcsncat(object, parts.lpszExtraInfo, parts.dwExtraInfoLength);

    session = WinHttpOpen(L"MJOLNIR-Lobby/1", WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY, WINHTTP_NO_PROXY_NAME,
                          WINHTTP_NO_PROXY_BYPASS, 0);
    if (!session) {
        hub_error(call, "WinHttpOpen failed");
        goto done;
    }
    WinHttpSetTimeouts(session, 5000, 5000, 10000, 15000);
    connection = WinHttpConnect(session, host, parts.nPort, 0);
    request = connection ? WinHttpOpenRequest(connection, wmethod, object, NULL, WINHTTP_NO_REFERER,
                                              WINHTTP_DEFAULT_ACCEPT_TYPES,
                                              parts.nScheme == INTERNET_SCHEME_HTTPS ? WINHTTP_FLAG_SECURE : 0)
                         : NULL;
    if (!request) {
        hub_error(call, "cannot reach the hub");
        goto done;
    }
    char key[256];
    wchar_t headers[512];
    launcher_key(key, sizeof key);
    if (key[0])
        _snwprintf(headers, 512, L"Content-Type: application/json\r\nAuthorization: Bearer %S\r\n", key);
    else
        _snwprintf(headers, 512, L"Content-Type: application/json\r\n");
    headers[511] = 0;
    SecureZeroMemory(key, sizeof key);
    DWORD length = call->body ? (DWORD)strlen(call->body) : 0;
    BOOL sent = WinHttpSendRequest(request, headers, (DWORD)-1L, length ? call->body : WINHTTP_NO_REQUEST_DATA,
                                   length, length, 0);
    SecureZeroMemory(headers, sizeof headers);
    if (!sent || !WinHttpReceiveResponse(request, NULL)) {
        hub_error(call, "the hub did not answer");
        goto done;
    }
    DWORD status = 0, size = sizeof status;
    WinHttpQueryHeaders(request, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX,
                        &status, &size, WINHTTP_NO_HEADER_INDEX);
    char *body = NULL;
    size_t total = 0;
    for (;;) {
        DWORD available = 0, got = 0;
        if (!WinHttpQueryDataAvailable(request, &available) || available == 0) break;
        char *grown = (char *)realloc(body, total + available);
        if (!grown) break;
        body = grown;
        if (!WinHttpReadData(request, body + total, available, &got) || got == 0) break;
        total += got;
    }
    hub_reply(call, status, body ? body : "", total);
    free(body);
done:
    if (request) WinHttpCloseHandle(request);
    if (connection) WinHttpCloseHandle(connection);
    if (session) WinHttpCloseHandle(session);
    free(call->body);
    free(call);
    return 0;
}

/* native\hub_request.txt: "<id> <METHOD> <path below /api/v1>", then the JSON
   body, if any, on the lines after. The call runs on its own thread; the
   reply lands in native\hub_reply_<id>.txt as "<status>\n<body>", status 0
   when the hub could not be reached. */
__declspec(dllexport) int mjolnir_hub_call(void *L) {
    (void)L;
    if (!dir[0]) find_dir();
    char path[MAX_PATH];
    snprintf(path, sizeof path, "%shub_request.txt", dir);
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    struct hub_call *call = (struct hub_call *)calloc(1, sizeof *call);
    char line[1200];
    if (!call || !fgets(line, sizeof line, f) ||
        sscanf(line, "%39s %7s %1023s", call->id, call->method, call->path) != 3) {
        fclose(f);
        free(call);
        return 0;
    }
    /* The id names a file beside this DLL. */
    for (const char *c = call->id; *c; c++) {
        if (!((*c >= '0' && *c <= '9') || (*c >= 'a' && *c <= 'z') || (*c >= 'A' && *c <= 'Z'))) {
            fclose(f);
            free(call);
            return 0;
        }
    }
    /* The path names an API route, never another host. */
    if (call->path[0] != '/' || call->path[1] == '/' || strstr(call->path, "://")) {
        fclose(f);
        hub_error(call, "the path must be below the hub API");
        free(call);
        return 0;
    }
    long start = ftell(f);
    fseek(f, 0, SEEK_END);
    long end = ftell(f);
    if (end > start) {
        call->body = (char *)calloc(1, (size_t)(end - start) + 1);
        fseek(f, start, SEEK_SET);
        if (call->body) fread(call->body, 1, (size_t)(end - start), f);
    }
    fclose(f);
    HANDLE thread = CreateThread(NULL, 0, hub_worker, call, 0, NULL);
    if (thread) {
        CloseHandle(thread);
    } else {
        hub_error(call, "cannot start a thread");
        free(call->body);
        free(call);
    }
    return 0;
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
    fireteam_log("PFMultiplayerJoinLobby: %s", swap_import("PlayFabMultiplayerWin.dll", "PFMultiplayerJoinLobby",
                                                            (void *)hook_join_lobby, (void **)&real_join_lobby));
    fireteam_log("PFLobbyLeave: %s", swap_import("PlayFabMultiplayerWin.dll", "PFLobbyLeave", (void *)hook_lobby_leave,
                                                 (void **)&real_lobby_leave));
    fireteam_log("PFLobbyPostUpdate: %s", swap_import("PlayFabMultiplayerWin.dll", "PFLobbyPostUpdate",
                                                      (void *)hook_lobby_post_update, (void **)&real_lobby_post_update));
    fireteam_log("simulation send (join refusals): %s", hook_sim_send_routine());
    fireteam_log("PartyStartProcessingStateChanges: %s",
                 swap_import("PartyWin.dll", "PartyStartProcessingStateChanges", (void *)hook_party_start_changes,
                             (void **)&real_party_start_changes));
    fireteam_log("PFLobbyForceRemoveMember: %s",
                 swap_import("PlayFabMultiplayerWin.dll", "PFLobbyForceRemoveMember", (void *)hook_lobby_force_remove,
                             (void **)&real_lobby_force_remove));
    fireteam_log("OnlineTick (joins by connection string): %s", hook_online_tick_slot());
    fireteam_log("LeaveSession (solo starts keep a public lobby): %s", hook_leave_session_slot());
    fireteam_log("PreLogin (joins into a public match under way): %s", hook_pre_login_slots());
    fireteam_log("pawn BeginPlay (a joiner before its Blam game): %s", hook_pawn_begin_play_slot());
    fireteam_log("world NotifyBeginPlay (held for a joiner's Blam game): %s", hook_notify_begin_play_slots());
    fireteam_log("Blam shell commands (logged with their callers): %s", hook_shell_commands());
    fireteam_log("PreClientTravel (a client's Blam start): %s", hook_pre_client_travel_slots());
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
