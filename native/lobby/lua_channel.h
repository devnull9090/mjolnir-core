/* Arguments and return values between Lua and a native function, with no
 * files (docs/lua_native_audit.md, "The Lua-to-native channel").
 *
 * UE4SS exports no lua_* C API, but it does export its C++ wrapper
 * RC::LuaMadeSimple::Lua, and package.loadlib already hands an export the
 * caller's lua_State*. This header calls that wrapper from C. Checked against
 * the pinned UE4SS build (runtime/ue4ss.lock.json, 3.0.1-exp-d0107f63), by
 * disassembly and in game (2026-11-09):
 *
 *  - The Lua object is 0xa8 bytes: lua_State* at +0, a std::vector at +8, an
 *    optional at +0x38 (engaged flag +0x98) and a self pointer at +0xa0. No
 *    vtable. LC_LUA_SIZE leaves room for a bigger one; it is built in place
 *    and never moved.
 *  - Every get_* reads the value at an index and then REMOVES it
 *    (lua_to*, then lua_rotate(idx, -1) and lua_settop(-2)). None of them
 *    checks the type: get_integer gives 0 for a string or a non-integral
 *    number, and get_string on anything but a string or number dereferences
 *    NULL. On an index past the top they remove a value that is there.
 *    lc_take_* below check the index and the type first and remove exactly
 *    the one value, so arguments read in order from index 1.
 *  - get_string's view points into a string that the removal just
 *    unanchored. Nothing can collect it until the next call that allocates
 *    (a push, a table), so lc_take_string copies it at once.
 *  - set_* are lua_push*; prepare_new_table is lua_createtable and fills a
 *    Table whose first field is the Lua object; fuse_pair is
 *    lua_settable(L, -3).
 *  - A Lua error raised inside a native function longjmps (UE4SS builds Lua
 *    as C) straight back to the caller's pcall: the rest of the native
 *    function never runs, __finally blocks do, __except filters do not. So
 *    nothing here raises, and a native function must not either. Report a
 *    bad argument as a nil and a reason.
 *
 * The names below are MSVC-mangled member functions: `this` in rcx, and a
 * class returned by value (string_view, Table) through a hidden pointer in
 * rdx, after `this`. They are pinned to the UE4SS build like the AOB
 * signatures are: a UE4SS bump re-runs lc_resolve against the new DLL
 * (lc_missing names the first export that is gone) and test-lua-channel.ps1.
 *
 * Use, inside an export called from Lua:
 *
 *     lc_frame f;
 *     if (!lc_begin(&f, L)) return 0;
 *     long long n = lc_take_integer(&f, 1, 0);       // argument 1
 *     char name[64];
 *     int ok = lc_take_string(&f, 1, name, sizeof name, NULL);  // argument 2
 *     lc_push_integer(&f, n + 1);
 *     lc_end(&f);
 *     return 1;                                       // one result
 */
#pragma once
#include <windows.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Inline so that a file using a few of them builds clean at /W4 /WX. */
#define LC_API static __inline

#define LC_LUA_SIZE 0x100   /* RC::LuaMadeSimple::Lua: 0xa8 bytes on d0107f63 */
#define LC_TABLE_SIZE 0x80  /* Lua::Table: 0x6a bytes on d0107f63 */

/* std::string_view as MSVC lays it out. */
typedef struct {
    const char *data;
    size_t size;
} lc_string_view;

typedef void *(*lc_ctor_fn)(void *self, void *L);
typedef void (*lc_dtor_fn)(void *self);
typedef int (*lc_size_fn)(const void *self);
typedef unsigned char (*lc_is_fn)(const void *self, int index);
typedef long long (*lc_get_integer_fn)(const void *self, int index);
typedef double (*lc_get_number_fn)(const void *self, int index);
typedef unsigned char (*lc_get_bool_fn)(const void *self, int index);
typedef lc_string_view *(*lc_get_string_fn)(const void *self, lc_string_view *out, int index);
typedef void (*lc_discard_fn)(const void *self, int index);
typedef void (*lc_set_integer_fn)(const void *self, long long value);
typedef void (*lc_set_number_fn)(const void *self, double value);
typedef void (*lc_set_bool_fn)(const void *self, unsigned char value);
typedef void (*lc_set_string_fn)(const void *self, const char *data, size_t size);
typedef void (*lc_set_nil_fn)(const void *self);
typedef void *(*lc_new_table_fn)(const void *self, void *table_out, int array_size, int record_size);
typedef void (*lc_fuse_pair_fn)(void *table);

static struct {
    int resolved; /* 1 found, -1 a name is missing */
    lc_ctor_fn ctor;
    lc_dtor_fn dtor;
    lc_size_fn stack_size;
    lc_is_fn is_nil, is_bool, is_number, is_integer, is_string, is_table;
    lc_get_integer_fn get_integer;
    lc_get_number_fn get_number;
    lc_get_bool_fn get_bool;
    lc_get_string_fn get_string;
    lc_discard_fn discard;
    lc_set_integer_fn set_integer;
    lc_set_number_fn set_number;
    lc_set_bool_fn set_bool;
    lc_set_string_fn set_string;
    lc_set_nil_fn set_nil;
    lc_new_table_fn new_table;
    lc_fuse_pair_fn fuse_pair;
} lc;

/* The first export lc_resolve could not find, or NULL. */
static const char *lc_missing;

#define LC_NAME(field, mangled) {(void **)&lc.field, mangled}
static const struct {
    void **slot;
    const char *name;
} LC_EXPORTS[] = {
    LC_NAME(ctor, "??0Lua@LuaMadeSimple@RC@@QEAA@PEAUlua_State@@@Z"),
    LC_NAME(dtor, "??1Lua@LuaMadeSimple@RC@@QEAA@XZ"),
    LC_NAME(stack_size, "?get_stack_size@Lua@LuaMadeSimple@RC@@QEBAHXZ"),
    LC_NAME(is_nil, "?is_nil@Lua@LuaMadeSimple@RC@@QEBA_NH@Z"),
    LC_NAME(is_bool, "?is_bool@Lua@LuaMadeSimple@RC@@QEBA_NH@Z"),
    LC_NAME(is_number, "?is_number@Lua@LuaMadeSimple@RC@@QEBA_NH@Z"),
    LC_NAME(is_integer, "?is_integer@Lua@LuaMadeSimple@RC@@QEBA_NH@Z"),
    LC_NAME(is_string, "?is_string@Lua@LuaMadeSimple@RC@@QEBA_NH@Z"),
    LC_NAME(is_table, "?is_table@Lua@LuaMadeSimple@RC@@QEBA_NH@Z"),
    LC_NAME(get_integer, "?get_integer@Lua@LuaMadeSimple@RC@@QEBA_JH@Z"),
    LC_NAME(get_number, "?get_number@Lua@LuaMadeSimple@RC@@QEBANH@Z"),
    LC_NAME(get_bool, "?get_bool@Lua@LuaMadeSimple@RC@@QEBA_NH@Z"),
    LC_NAME(get_string, "?get_string@Lua@LuaMadeSimple@RC@@QEBA?AV?$basic_string_view@DU?$char_traits@D@std@@@std@@H@Z"),
    LC_NAME(discard, "?discard_value@Lua@LuaMadeSimple@RC@@QEBAXH@Z"),
    LC_NAME(set_integer, "?set_integer@Lua@LuaMadeSimple@RC@@QEBAX_J@Z"),
    LC_NAME(set_number, "?set_number@Lua@LuaMadeSimple@RC@@QEBAXN@Z"),
    LC_NAME(set_bool, "?set_bool@Lua@LuaMadeSimple@RC@@QEBAX_N@Z"),
    LC_NAME(set_string, "?set_string@Lua@LuaMadeSimple@RC@@QEBAXPEBD_K@Z"),
    LC_NAME(set_nil, "?set_nil@Lua@LuaMadeSimple@RC@@QEBAXXZ"),
    LC_NAME(new_table, "?prepare_new_table@Lua@LuaMadeSimple@RC@@QEBA?AVTable@123@HH@Z"),
    LC_NAME(fuse_pair, "?fuse_pair@Table@Lua@LuaMadeSimple@RC@@QEAAXXZ"),
};
#undef LC_NAME

/* Finds every export in `module` (UE4SS.dll in game). Once: a later call
   returns the first answer. 1 when all are there. */
LC_API int lc_resolve(HMODULE module) {
    if (lc.resolved) return lc.resolved > 0;
    lc.resolved = -1;
    if (!module) {
        lc_missing = "the module";
        return 0;
    }
    for (size_t i = 0; i < sizeof LC_EXPORTS / sizeof LC_EXPORTS[0]; i++) {
        FARPROC p = GetProcAddress(module, LC_EXPORTS[i].name);
        if (!p) {
            lc_missing = LC_EXPORTS[i].name;
            return 0;
        }
        memcpy(LC_EXPORTS[i].slot, &p, sizeof p);
    }
    lc.resolved = 1;
    return 1;
}

/* One call's wrapper around the caller's lua_State. */
typedef struct {
    __declspec(align(16)) unsigned char lua[LC_LUA_SIZE];
    __declspec(align(16)) unsigned char table[LC_TABLE_SIZE];
} lc_frame;

/* Builds the wrapper for L, resolving UE4SS.dll's exports on first use.
   0 when they are not there: return without touching L. */
LC_API int lc_begin(lc_frame *f, void *L) {
    if (!lc.resolved) lc_resolve(GetModuleHandleA("UE4SS.dll"));
    if (lc.resolved < 0 || !L) return 0;
    memset(f, 0, sizeof *f);
    lc.ctor(f->lua, L);
    return 1;
}

LC_API void lc_end(lc_frame *f) {
    lc.dtor(f->lua);
}

/* How many values are on the stack: the arguments, at the start of a call. */
LC_API int lc_top(lc_frame *f) {
    return lc.stack_size(f->lua);
}

LC_API int lc_is_nil(lc_frame *f, int index) {
    return lc.is_nil(f->lua, index) != 0;
}
LC_API int lc_is_bool(lc_frame *f, int index) {
    return lc.is_bool(f->lua, index) != 0;
}
/* A number, or a string that converts to one (lua_isnumber). */
LC_API int lc_is_number(lc_frame *f, int index) {
    return lc.is_number(f->lua, index) != 0;
}
/* An integer subtype only (lua_isinteger): 2.0 is a number, not an integer. */
LC_API int lc_is_integer(lc_frame *f, int index) {
    return lc.is_integer(f->lua, index) != 0;
}
/* A string, not a number (type LUA_TSTRING). */
LC_API int lc_is_string(lc_frame *f, int index) {
    return lc.is_string(f->lua, index) != 0;
}
LC_API int lc_is_table(lc_frame *f, int index) {
    return lc.is_table(f->lua, index) != 0;
}

/* Whether `index` names a value on the stack. get_* and discard_value on an
   index past the top would remove a value that is there (lua_rotate does not
   check in a release build), so every take asks this first. */
LC_API int lc_present(lc_frame *f, int index) {
    int top = lc.stack_size(f->lua);
    return index > 0 ? index <= top : index < 0 && -index <= top;
}

/* Removes the value at `index` whatever it is; nothing when there is none. */
LC_API void lc_drop(lc_frame *f, int index) {
    if (lc_present(f, index)) lc.discard(f->lua, index);
}

/* The value at `index` as an integer, removed; `fallback` (and still removed)
   when it is not a number. A float is truncated toward zero. An argument the
   caller left out is no value at all: `fallback`, and nothing is removed. */
LC_API long long lc_take_integer(lc_frame *f, int index, long long fallback) {
    if (!lc_present(f, index)) return fallback;
    if (lc.is_integer(f->lua, index)) return lc.get_integer(f->lua, index);
    if (lc.is_number(f->lua, index)) {
        double d = lc.get_number(f->lua, index);
        return d == d && d > -9.2e18 && d < 9.2e18 ? (long long)d : fallback;
    }
    lc.discard(f->lua, index);
    return fallback;
}

/* The value at `index` as a number, removed; `fallback` when it is not one. */
LC_API double lc_take_number(lc_frame *f, int index, double fallback) {
    if (!lc_present(f, index)) return fallback;
    if (lc.is_number(f->lua, index)) return lc.get_number(f->lua, index);
    lc.discard(f->lua, index);
    return fallback;
}

/* The value at `index` as Lua's truth (only nil and false are false),
   removed. A missing argument is false. */
LC_API int lc_take_bool(lc_frame *f, int index) {
    if (!lc_present(f, index)) return 0;
    return lc.get_bool(f->lua, index) != 0;
}

/* Copies the string at `index` into buf (NUL-terminated, cut to cap - 1
   bytes) and removes it. 1 for a string, with its whole length in *length
   when asked; 0 for anything else, which is removed too and leaves buf "". */
LC_API int lc_take_string(lc_frame *f, int index, char *buf, size_t cap, size_t *length) {
    if (cap) buf[0] = 0;
    if (length) *length = 0;
    if (!lc_present(f, index)) return 0;
    if (!lc.is_string(f->lua, index)) {
        lc.discard(f->lua, index);
        return 0;
    }
    lc_string_view view = {0};
    lc.get_string(f->lua, &view, index);
    if (length) *length = view.size;
    if (cap) {
        size_t n = view.size < cap - 1 ? view.size : cap - 1;
        if (n && view.data) memcpy(buf, view.data, n);
        buf[n] = 0;
    }
    return 1;
}

LC_API void lc_push_integer(lc_frame *f, long long value) {
    lc.set_integer(f->lua, value);
}
LC_API void lc_push_number(lc_frame *f, double value) {
    lc.set_number(f->lua, value);
}
LC_API void lc_push_bool(lc_frame *f, int value) {
    lc.set_bool(f->lua, (unsigned char)(value != 0));
}
/* Any bytes, NULs included: Lua's string.unpack reads a packed record. */
LC_API void lc_push_string(lc_frame *f, const char *data, size_t size) {
    lc.set_string(f->lua, data, size);
}
LC_API void lc_push_text(lc_frame *f, const char *text) {
    lc.set_string(f->lua, text, strlen(text));
}
LC_API void lc_push_nil(lc_frame *f) {
    lc.set_nil(f->lua);
}

/* Pushes a new table, room made for `array_size` list items and
   `record_size` named fields. */
LC_API void lc_push_table(lc_frame *f, int array_size, int record_size) {
    lc.new_table(f->lua, f->table, array_size, record_size);
}

/* t[k] = v, with the table at -3, the key at -2 and the value on top (both
   popped). The setters below push the pair for you. */
LC_API void lc_set(lc_frame *f) {
    lc.fuse_pair(f->table);
}

LC_API void lc_field_integer(lc_frame *f, const char *key, long long value) {
    lc_push_text(f, key);
    lc_push_integer(f, value);
    lc_set(f);
}
LC_API void lc_field_number(lc_frame *f, const char *key, double value) {
    lc_push_text(f, key);
    lc_push_number(f, value);
    lc_set(f);
}
LC_API void lc_field_bool(lc_frame *f, const char *key, int value) {
    lc_push_text(f, key);
    lc_push_bool(f, value);
    lc_set(f);
}
LC_API void lc_field_text(lc_frame *f, const char *key, const char *value) {
    lc_push_text(f, key);
    lc_push_text(f, value);
    lc_set(f);
}

/* A list item: lc_push_integer(f, i), push or build the value (a nested
   lc_push_table and its fields), then lc_set(f). */
