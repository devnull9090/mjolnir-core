/* lua_channel.h against test_lua_channel_fake.cpp, a stand-in for UE4SS's
 * RC::LuaMadeSimple::Lua built from the same C++ declarations, so the
 * mangled names and the member-call ABI are MSVC's own. The functions below
 * are written the way a lobby DLL export would be.
 *
 *     test_lua_channel.exe <fake_ue4ss.dll>
 */
#include "lua_channel.h"
#include <math.h>
#include <stdio.h>

typedef void lua_State;
enum { K_NONE = -1, K_NIL = 0, K_BOOL = 1, K_NUM = 3, K_STR = 4, K_TAB = 5, K_INT = 13 };

static lua_State *(*fake_new)(void);
static void (*fake_free)(lua_State *);
static size_t (*fake_lua_size)(void), (*fake_table_size)(void);
static int (*fake_constructed)(void), (*fake_destroyed)(void);
static void (*fake_push_int)(lua_State *, long long);
static void (*fake_push_num)(lua_State *, double);
static void (*fake_push_str)(lua_State *, const char *);
static void (*fake_push_bool)(lua_State *, int);
static void (*fake_push_nil)(lua_State *);
static void (*fake_push_table)(lua_State *);
static int (*fake_top)(lua_State *);
static int (*fake_kind)(lua_State *, int);
static long long (*fake_int)(lua_State *, int);
static double (*fake_num)(lua_State *, int);
static int (*fake_bool)(lua_State *, int);
static const char *(*fake_str)(lua_State *, int, size_t *);
static void (*fake_pop)(lua_State *, int);
static void (*fake_get)(lua_State *, int, const char *, long long);
static int (*fake_table_count)(lua_State *, int);

static int failures;
#define CHECK(cond)                                                                                                    \
    do {                                                                                                               \
        if (!(cond)) {                                                                                                 \
            fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                                           \
            failures++;                                                                                                \
        }                                                                                                              \
    } while (0)

/* (integer, number, string, bool) -> integer + 1, number * 2, string .. "!",
   not bool; the stack size after each take in sizes[]. */
static int sizes[5];
static int echo(void *L) {
    lc_frame f;
    if (!lc_begin(&f, L)) return 0;
    sizes[0] = lc_top(&f);
    long long i = lc_take_integer(&f, 1, -1);
    sizes[1] = lc_top(&f);
    double d = lc_take_number(&f, 1, -1.0);
    sizes[2] = lc_top(&f);
    char s[16];
    int text = lc_take_string(&f, 1, s, sizeof s - 1, NULL);
    sizes[3] = lc_top(&f);
    int b = lc_take_bool(&f, 1);
    sizes[4] = lc_top(&f);
    lc_push_integer(&f, i + 1);
    lc_push_number(&f, d * 2);
    if (text) {
        size_t n = strlen(s);
        s[n] = '!';
        lc_push_string(&f, s, n + 1);
    } else {
        lc_push_nil(&f);
    }
    lc_push_bool(&f, !b);
    lc_end(&f);
    return 4;
}

/* Three players as a list of tables, then one packed record. */
typedef struct {
    int index, team;
    float x, y, z;
} roster_player;
static int roster(void *L) {
    lc_frame f;
    if (!lc_begin(&f, L)) return 0;
    roster_player p[3] = {{0, 1, 1.5f, -2.0f, 3.0f}, {4, 0, -7.25f, 8.0f, 0.5f}, {9, 1, 0, 0, 0}};
    lc_push_table(&f, 3, 0);
    for (int i = 0; i < 3; i++) {
        lc_push_integer(&f, i + 1);
        lc_push_table(&f, 0, 5);
        lc_field_integer(&f, "index", p[i].index);
        lc_field_integer(&f, "team", p[i].team);
        lc_field_number(&f, "x", p[i].x);
        lc_field_bool(&f, "alive", i != 2);
        lc_field_text(&f, "name", i ? "b" : "a");
        lc_set(&f);
    }
    lc_push_string(&f, (const char *)p, sizeof p);
    lc_end(&f);
    return 2;
}

static void test_resolve(HMODULE fake) {
    lc.resolved = 0;
    CHECK(!lc_resolve(NULL));
    CHECK(lc_missing && !strcmp(lc_missing, "the module"));
    lc.resolved = 0;
    CHECK(!lc_resolve(GetModuleHandleA("kernel32.dll")));
    CHECK(lc_missing && strstr(lc_missing, "??0Lua@LuaMadeSimple@RC@@"));
    lc_frame f;
    CHECK(!lc_begin(&f, (void *)&f)); /* unresolved: nothing is called */
    lc.resolved = 0;
    lc_missing = NULL;
    CHECK(lc_resolve(fake));
    CHECK(!lc_missing);
    CHECK(lc_resolve(NULL)); /* the first answer stands */
    CHECK(!lc_begin(&f, NULL));
}

static void test_sizes(void) {
    CHECK(fake_lua_size() == 0xa8); /* the real one's, from its constructor */
    CHECK(fake_lua_size() <= LC_LUA_SIZE);
    CHECK(fake_table_size() <= LC_TABLE_SIZE);
}
_Static_assert(sizeof(lc_string_view) == 16, "std::string_view is a pointer and a size");

static void test_echo(void) {
    lua_State *L = fake_new();
    fake_push_int(L, 41);
    fake_push_num(L, 1.25);
    fake_push_str(L, "hi");
    fake_push_bool(L, 0);
    CHECK(echo(L) == 4);
    CHECK(sizes[0] == 4 && sizes[1] == 3 && sizes[2] == 2 && sizes[3] == 1 && sizes[4] == 0);
    CHECK(fake_top(L) == 4);
    CHECK(fake_kind(L, 1) == K_INT && fake_int(L, 1) == 42);
    CHECK(fake_kind(L, 2) == K_NUM && fake_num(L, 2) == 2.5);
    size_t n = 0;
    CHECK(fake_kind(L, 3) == K_STR && !strcmp(fake_str(L, 3, &n), "hi!") && n == 3);
    CHECK(fake_kind(L, 4) == K_BOOL && fake_bool(L, 4) == 1);
    fake_free(L);
}

/* Left-out arguments are no values at all: nothing may be removed (the fake
   aborts on an index past the top, where the real one would remove a value
   that is there). */
static void test_missing(void) {
    lua_State *L = fake_new();
    fake_push_int(L, 7);
    CHECK(echo(L) == 4);
    CHECK(sizes[0] == 1 && sizes[1] == 0 && sizes[4] == 0);
    CHECK(fake_int(L, 1) == 8 && fake_num(L, 2) == -2.0 && fake_kind(L, 3) == K_NIL && fake_bool(L, 4) == 1);
    fake_free(L);
    L = fake_new();
    CHECK(echo(L) == 4);
    CHECK(fake_int(L, 1) == 0 && fake_top(L) == 4);
    fake_free(L);
}

/* A wrong type still takes exactly one value, so the next argument stays at
   index 1; get_string never sees a number or a table. */
static void test_wrong_types(void) {
    lua_State *L = fake_new();
    fake_push_str(L, "x");
    fake_push_table(L);
    fake_push_int(L, 5);
    fake_push_nil(L);
    CHECK(echo(L) == 4);
    CHECK(sizes[0] == 4 && sizes[1] == 3 && sizes[2] == 2 && sizes[3] == 1 && sizes[4] == 0);
    CHECK(fake_int(L, 1) == 0);      /* -1 + 1 */
    CHECK(fake_num(L, 2) == -2.0);   /* fallback * 2 */
    CHECK(fake_kind(L, 3) == K_NIL); /* 5 is a number, not a string */
    CHECK(fake_bool(L, 4) == 1);     /* nil is false */
    fake_free(L);

    /* Numbers to integers: an integral float, a cut one, one out of range, and
       a numeric string (lua_isnumber says yes; get_number converts). */
    L = fake_new();
    fake_push_num(L, 2.0);
    fake_push_num(L, -2.75);
    fake_push_num(L, 1e30);
    fake_push_str(L, "12");
    lc_frame f;
    CHECK(lc_begin(&f, L));
    CHECK(lc_take_integer(&f, 1, 99) == 2);
    CHECK(lc_take_integer(&f, 1, 99) == -2);
    CHECK(lc_take_integer(&f, 1, 99) == 99);
    CHECK(lc_take_integer(&f, 1, 99) == 12);
    CHECK(lc_top(&f) == 0);
    CHECK(lc_take_integer(&f, 1, 99) == 99);
    lc_end(&f);
    fake_free(L);
}

static void test_strings(void) {
    lua_State *L = fake_new();
    fake_push_str(L, "a long string that does not fit");
    fake_push_str(L, "");
    fake_push_str(L, "last");
    lc_frame f;
    CHECK(lc_begin(&f, L));
    char buf[8];
    size_t length = 0;
    CHECK(lc_take_string(&f, 1, buf, sizeof buf, &length));
    CHECK(!strcmp(buf, "a long ") && length == 31);
    CHECK(lc_take_string(&f, 1, buf, sizeof buf, &length));
    CHECK(buf[0] == 0 && length == 0);
    /* From the top instead of the bottom. */
    CHECK(lc_take_string(&f, -1, buf, sizeof buf, NULL));
    CHECK(!strcmp(buf, "last"));
    CHECK(!lc_take_string(&f, 1, buf, sizeof buf, &length));
    CHECK(buf[0] == 0 && length == 0);
    lc_end(&f);
    fake_free(L);
}

static void test_tables(void) {
    lua_State *L = fake_new();
    CHECK(roster(L) == 2);
    CHECK(fake_top(L) == 2);
    CHECK(fake_kind(L, 1) == K_TAB && fake_table_count(L, 1) == 3);
    fake_get(L, 1, NULL, 2);
    CHECK(fake_kind(L, -1) == K_TAB && fake_table_count(L, -1) == 5);
    fake_get(L, -1, "index", 0);
    CHECK(fake_kind(L, -1) == K_INT && fake_int(L, -1) == 4);
    fake_pop(L, 1);
    fake_get(L, -1, "x", 0);
    CHECK(fake_kind(L, -1) == K_NUM && fake_num(L, -1) == -7.25);
    fake_pop(L, 1);
    fake_get(L, -1, "name", 0);
    CHECK(fake_kind(L, -1) == K_STR && !strcmp(fake_str(L, -1, NULL), "b"));
    fake_pop(L, 2);
    fake_get(L, 1, NULL, 3);
    fake_get(L, -1, "alive", 0);
    CHECK(fake_kind(L, -1) == K_BOOL && fake_bool(L, -1) == 0);
    fake_pop(L, 2);
    /* The packed record keeps its NULs and every byte. */
    size_t n = 0;
    const char *blob = fake_str(L, 2, &n);
    CHECK(n == 3 * sizeof(roster_player));
    roster_player back[3];
    memcpy(back, blob, sizeof back);
    CHECK(back[1].index == 4 && back[1].x == -7.25f && back[2].z == 0.0f);
    fake_free(L);
}

#define BIND(name) (*(FARPROC *)&name = GetProcAddress(fake, #name), name != NULL)

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: test_lua_channel <fake_ue4ss.dll>\n");
        return 2;
    }
    HMODULE fake = LoadLibraryA(argv[1]);
    if (!fake) {
        fprintf(stderr, "cannot load %s (%lu)\n", argv[1], GetLastError());
        return 2;
    }
    if (!(BIND(fake_new) && BIND(fake_free) && BIND(fake_lua_size) && BIND(fake_table_size) && BIND(fake_constructed)
          && BIND(fake_destroyed) && BIND(fake_push_int) && BIND(fake_push_num) && BIND(fake_push_str)
          && BIND(fake_push_bool) && BIND(fake_push_nil) && BIND(fake_push_table) && BIND(fake_top) && BIND(fake_kind)
          && BIND(fake_int) && BIND(fake_num) && BIND(fake_bool) && BIND(fake_str) && BIND(fake_pop) && BIND(fake_get)
          && BIND(fake_table_count))) {
        fprintf(stderr, "the fake is missing a helper\n");
        return 2;
    }
    test_resolve(fake);
    if (lc.resolved != 1) {
        fprintf(stderr, "FAIL: lua_channel.h names an export the fake does not have: %s\n",
                lc_missing ? lc_missing : "?");
        return 1;
    }
    test_sizes();
    test_echo();
    test_missing();
    test_wrong_types();
    test_strings();
    test_tables();
    /* Every lc_begin had its lc_end (the fake's own helpers build and drop
       their own Lua objects too). */
    CHECK(fake_constructed() > 0 && fake_constructed() == fake_destroyed());
    if (failures) {
        fprintf(stderr, "%d check(s) failed\n", failures);
        return 1;
    }
    printf("lua channel: all checks passed\n");
    return 0;
}
