// A stand-in for UE4SS.dll's RC::LuaMadeSimple::Lua, for test_lua_channel.c.
//
// The class is declared the way UE4SS declares it, so MSVC mangles and calls
// its members exactly as it does in the real DLL: if lua_channel.h names an
// export wrongly, GetProcAddress fails, and if it passes `this`, a hidden
// return pointer, a double or a bool in the wrong place, the values come out
// wrong. Behind it is a small stack with the real wrapper's semantics, as
// read from UE4SS 3.0.1-exp-d0107f63 (docs/lua_native_audit.md): get_* read
// the value at an index and remove it, unchecked; is_* only look. Where the
// real one would corrupt Lua's stack or dereference NULL (an index past the
// top, get_string on a table) this one aborts, so the test fails loudly.
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

struct lua_State;

namespace fake {
enum Kind { None = -1, Nil = 0, Bool = 1, Num = 3, Str = 4, Tab = 5, Int = 13 };
struct Value {
    Kind kind = Nil;
    bool b = false;
    int64_t i = 0;
    double n = 0;
    std::string s;
    int table = -1;
};
struct State {
    std::vector<Value> stack;
    std::vector<std::vector<std::pair<Value, Value>>> tables;
};
static int constructed, destroyed;

static State *of(lua_State *L) {
    return reinterpret_cast<State *>(L);
}
static void die(const char *why) {
    std::fprintf(stderr, "fake UE4SS: %s\n", why);
    std::fflush(stderr);
    std::abort();
}
// The stack slot for a Lua index; aborts past the top, as the real one
// would silently remove the wrong value.
static size_t slot(State *s, int index) {
    int top = (int)s->stack.size();
    int at = index > 0 ? index : top + index + 1;
    if (index == 0 || at < 1 || at > top) die("index past the top");
    return (size_t)(at - 1);
}
static Value &at(State *s, int index) {
    return s->stack[slot(s, index)];
}
static void remove(State *s, int index) {
    s->stack.erase(s->stack.begin() + (ptrdiff_t)slot(s, index));
}
static bool to_number(const Value &v, double *out) {
    if (v.kind == Int) return *out = (double)v.i, true;
    if (v.kind == Num) return *out = v.n, true;
    if (v.kind == Str) {
        char *end = nullptr;
        double d = std::strtod(v.s.c_str(), &end);
        if (end && end != v.s.c_str() && !*end) return *out = d, true;
    }
    return false;
}
static bool same_key(const Value &a, const Value &b) {
    if (a.kind != b.kind) return false;
    if (a.kind == Str) return a.s == b.s;
    if (a.kind == Int) return a.i == b.i;
    return false;
}
} // namespace fake

namespace RC::LuaMadeSimple {
class __declspec(dllexport) Lua {
  public:
    class __declspec(dllexport) Table {
      public:
        Lua *m_lua;
        unsigned char m_rest[0x62];
        auto fuse_pair() -> void;
    };

    lua_State *m_lua_state;
    unsigned char m_rest[0xa0];

    Lua(lua_State *lua_state);
    ~Lua();
    auto get_stack_size() const -> int32_t;
    auto is_nil(int32_t force_index = 1) const -> bool;
    auto is_bool(int32_t force_index = 1) const -> bool;
    auto is_number(int32_t force_index = 1) const -> bool;
    auto is_integer(int32_t force_index = 1) const -> bool;
    auto is_string(int32_t force_index = 1) const -> bool;
    auto is_table(int32_t force_index = 1) const -> bool;
    auto get_integer(int32_t force_index = 1) const -> int64_t;
    auto get_number(int32_t force_index = 1) const -> double;
    auto get_bool(int32_t force_index = 1) const -> bool;
    auto get_string(int32_t force_index = 1) const -> std::string_view;
    auto discard_value(int32_t force_index = -1) const -> void;
    auto set_integer(int64_t value) const -> void;
    auto set_number(double value) const -> void;
    auto set_bool(bool value) const -> void;
    auto set_string(const char *value, size_t size) const -> void;
    auto set_nil() const -> void;
    auto prepare_new_table(int32_t array_size = 0, int32_t record_size = 0) const -> Table;

  private:
    auto state() const -> fake::State * {
        return fake::of(m_lua_state);
    }
};

Lua::Lua(lua_State *lua_state) : m_lua_state(lua_state) {
    std::memset(m_rest, 0, sizeof m_rest);
    fake::constructed++;
}
Lua::~Lua() {
    fake::destroyed++;
}
auto Lua::get_stack_size() const -> int32_t {
    return (int32_t)state()->stack.size();
}
static auto kind_at(fake::State *s, int32_t index) -> int {
    int top = (int)s->stack.size();
    int at = index > 0 ? index : top + index + 1;
    return index == 0 || at < 1 || at > top ? fake::None : s->stack[(size_t)at - 1].kind;
}
auto Lua::is_nil(int32_t i) const -> bool {
    return kind_at(state(), i) == fake::Nil;
}
auto Lua::is_bool(int32_t i) const -> bool {
    return kind_at(state(), i) == fake::Bool;
}
auto Lua::is_number(int32_t i) const -> bool {
    int k = kind_at(state(), i);
    double d;
    return k == fake::Int || k == fake::Num || (k == fake::Str && fake::to_number(fake::at(state(), i), &d));
}
auto Lua::is_integer(int32_t i) const -> bool {
    return kind_at(state(), i) == fake::Int;
}
auto Lua::is_string(int32_t i) const -> bool {
    return kind_at(state(), i) == fake::Str;
}
auto Lua::is_table(int32_t i) const -> bool {
    return kind_at(state(), i) == fake::Tab;
}
auto Lua::get_integer(int32_t i) const -> int64_t {
    fake::Value &v = fake::at(state(), i);
    double d = 0;
    int64_t r = v.kind == fake::Int ? v.i : fake::to_number(v, &d) && d == std::floor(d) ? (int64_t)d : 0;
    fake::remove(state(), i);
    return r;
}
auto Lua::get_number(int32_t i) const -> double {
    double d = 0;
    if (!fake::to_number(fake::at(state(), i), &d)) d = 0;
    fake::remove(state(), i);
    return d;
}
auto Lua::get_bool(int32_t i) const -> bool {
    fake::Value &v = fake::at(state(), i);
    bool r = !(v.kind == fake::Nil || (v.kind == fake::Bool && !v.b));
    fake::remove(state(), i);
    return r;
}
// The real one returns a view of Lua's own string after removing it; this
// one keeps removed strings alive until the state is freed, which is what
// "nothing collects it before the next allocation" amounts to.
static std::vector<std::string> removed_strings;
auto Lua::get_string(int32_t i) const -> std::string_view {
    fake::Value &v = fake::at(state(), i);
    if (v.kind != fake::Str) fake::die("get_string on a value that is not a string (strlen(NULL) in the real one)");
    removed_strings.push_back(v.s);
    fake::remove(state(), i);
    return removed_strings.back();
}
auto Lua::discard_value(int32_t i) const -> void {
    fake::remove(state(), i);
}
auto Lua::set_integer(int64_t value) const -> void {
    fake::Value v;
    v.kind = fake::Int;
    v.i = value;
    state()->stack.push_back(v);
}
auto Lua::set_number(double value) const -> void {
    fake::Value v;
    v.kind = fake::Num;
    v.n = value;
    state()->stack.push_back(v);
}
auto Lua::set_bool(bool value) const -> void {
    fake::Value v;
    v.kind = fake::Bool;
    v.b = value;
    state()->stack.push_back(v);
}
auto Lua::set_string(const char *value, size_t size) const -> void {
    fake::Value v;
    v.kind = fake::Str;
    v.s.assign(value, size);
    state()->stack.push_back(v);
}
auto Lua::set_nil() const -> void {
    state()->stack.push_back(fake::Value{});
}
auto Lua::prepare_new_table(int32_t, int32_t) const -> Table {
    fake::Value v;
    v.kind = fake::Tab;
    v.table = (int)state()->tables.size();
    state()->tables.emplace_back();
    state()->stack.push_back(v);
    Table t;
    t.m_lua = const_cast<Lua *>(this);
    std::memset(t.m_rest, 0, sizeof t.m_rest);
    return t;
}
// lua_settable(L, -3).
auto Lua::Table::fuse_pair() -> void {
    fake::State *s = fake::of(m_lua->m_lua_state);
    fake::Value &t = fake::at(s, -3);
    if (t.kind != fake::Tab) fake::die("fuse_pair without a table at -3");
    fake::Value key = fake::at(s, -2), value = fake::at(s, -1);
    auto &fields = s->tables[(size_t)t.table];
    bool replaced = false;
    for (auto &field : fields)
        if (fake::same_key(field.first, key)) field.second = value, replaced = true;
    if (!replaced) fields.emplace_back(key, value);
    s->stack.resize(s->stack.size() - 2);
}
} // namespace RC::LuaMadeSimple

// What the test drives and inspects the fake with.
extern "C" {
__declspec(dllexport) lua_State *fake_new(void) {
    return reinterpret_cast<lua_State *>(new fake::State());
}
__declspec(dllexport) void fake_free(lua_State *L) {
    delete fake::of(L);
}
__declspec(dllexport) size_t fake_lua_size(void) {
    return sizeof(RC::LuaMadeSimple::Lua);
}
__declspec(dllexport) size_t fake_table_size(void) {
    return sizeof(RC::LuaMadeSimple::Lua::Table);
}
__declspec(dllexport) int fake_constructed(void) {
    return fake::constructed;
}
__declspec(dllexport) int fake_destroyed(void) {
    return fake::destroyed;
}
__declspec(dllexport) void fake_push_int(lua_State *L, int64_t v) {
    RC::LuaMadeSimple::Lua(L).set_integer(v);
}
__declspec(dllexport) void fake_push_num(lua_State *L, double v) {
    RC::LuaMadeSimple::Lua(L).set_number(v);
}
__declspec(dllexport) void fake_push_str(lua_State *L, const char *v) {
    RC::LuaMadeSimple::Lua(L).set_string(v, std::strlen(v));
}
__declspec(dllexport) void fake_push_bool(lua_State *L, int v) {
    RC::LuaMadeSimple::Lua(L).set_bool(v != 0);
}
__declspec(dllexport) void fake_push_nil(lua_State *L) {
    RC::LuaMadeSimple::Lua(L).set_nil();
}
__declspec(dllexport) void fake_push_table(lua_State *L) {
    RC::LuaMadeSimple::Lua(L).prepare_new_table();
}
__declspec(dllexport) int fake_top(lua_State *L) {
    return (int)fake::of(L)->stack.size();
}
__declspec(dllexport) int fake_kind(lua_State *L, int index) {
    return RC::LuaMadeSimple::kind_at(fake::of(L), index);
}
__declspec(dllexport) int64_t fake_int(lua_State *L, int index) {
    return fake::at(fake::of(L), index).i;
}
__declspec(dllexport) double fake_num(lua_State *L, int index) {
    return fake::at(fake::of(L), index).n;
}
__declspec(dllexport) int fake_bool(lua_State *L, int index) {
    return fake::at(fake::of(L), index).b;
}
__declspec(dllexport) const char *fake_str(lua_State *L, int index, size_t *length) {
    fake::Value &v = fake::at(fake::of(L), index);
    if (length) *length = v.s.size();
    return v.s.c_str();
}
__declspec(dllexport) void fake_pop(lua_State *L, int n) {
    fake::State *s = fake::of(L);
    s->stack.resize(s->stack.size() - (size_t)n);
}
// Pushes t[key] (a string key) or t[i] (key NULL) of the table at `index`;
// nil when it is not there.
__declspec(dllexport) void fake_get(lua_State *L, int index, const char *key, int64_t i) {
    fake::State *s = fake::of(L);
    fake::Value &t = fake::at(s, index);
    if (t.kind != fake::Tab) fake::die("fake_get on a value that is not a table");
    fake::Value want;
    if (key) want.kind = fake::Str, want.s = key;
    else want.kind = fake::Int, want.i = i;
    fake::Value found;
    for (auto &field : s->tables[(size_t)t.table])
        if (fake::same_key(field.first, want)) found = field.second;
    s->stack.push_back(found);
}
__declspec(dllexport) int fake_table_count(lua_State *L, int index) {
    fake::State *s = fake::of(L);
    fake::Value &t = fake::at(s, index);
    return t.kind == fake::Tab ? (int)s->tables[(size_t)t.table].size() : -1;
}
}
