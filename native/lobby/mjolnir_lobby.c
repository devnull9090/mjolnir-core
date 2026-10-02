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
