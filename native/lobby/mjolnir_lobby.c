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
    fireteam_log("lobby: remove member %s from %p (prevent rejoin %u)%s", id ? id : "?", lobby, prevent_rejoin,
                 keep_lobby ? ": refused (the game is public)" : "");
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

static void *__fastcall hook_leave_session(void *self, void *out, unsigned char *params) {
    if (params) {
        fireteam_log("session: LeaveSession name %u/%u destroy %u", *(unsigned *)(params + 4),
                     *(unsigned *)(params + 8), params[0xc]);
    }
    in_leave_session++;
    void *result = real_leave_session(self, out, params);
    in_leave_session--;
    return result;
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
    *slot = (void *)hook_leave_session;
    VirtualProtect(slot, sizeof *slot, old, &old);
    return "hooked";
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
    fireteam_log("lobby: keep while public: %s", value ? "yes" : "no");
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
