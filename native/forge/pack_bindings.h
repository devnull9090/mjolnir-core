// Data-only pack identities shared by the launcher and saved Forge layouts.
// This parser deliberately has no game or Windows dependencies.
#ifndef MJOLNIR_PACK_BINDINGS_H
#define MJOLNIR_PACK_BINDINGS_H
#include <stdio.h>
#include <string.h>

#define FORGE_PACK_PREFIX "objects\\mjolnir\\forge\\"
typedef struct {
    char slug[65], version[97], sha256[65], tag[224];
    int flat;
} forge_pack_binding;

static int forge_alpha_digit(char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
}

static int forge_token(const char *s, int block) {
    size_t len = strlen(s);
    if (len < (block ? 1u : 2u) || len > 64 || !((*s >= 'a' && *s <= 'z') || (*s >= '0' && *s <= '9'))) return 0;
    for (; *s; s++)
        if (!((*s >= 'a' && *s <= 'z') || (*s >= '0' && *s <= '9') || *s == '-'
              || (block && *s == '_'))) return 0;
    return 1;
}

// Exact SemVer identity (including prerelease and build metadata), not a range.
static int forge_version(const char *s) {
    for (int part = 0; part < 3; part++) {
        const char *start = s;
        if (*s < '0' || *s > '9') return 0;
        while (*s >= '0' && *s <= '9') s++;
        if (*start == '0' && s - start > 1) return 0;
        if (part < 2 && *s++ != '.') return 0;
    }
    if (*s == '-') {
        s++;
        for (;;) {
            const char *start = s;
            int numeric = 1;
            while (forge_alpha_digit(*s) || *s == '-') {
                if (*s < '0' || *s > '9') numeric = 0;
                s++;
            }
            if (s == start || (numeric && *start == '0' && s - start > 1)) return 0;
            if (*s != '.') break;
            s++;
        }
    }
    if (*s == '+') {
        s++;
        for (;;) {
            const char *start = s;
            while (forge_alpha_digit(*s) || *s == '-') s++;
            if (s == start) return 0;
            if (*s != '.') break;
            s++;
        }
    }
    return *s == 0;
}

static int forge_binding_valid(const forge_pack_binding *b) {
    char prefix[100];
    if (!forge_token(b->slug, 0) || !forge_version(b->version) || strlen(b->sha256) != 64) return 0;
    for (int i = 0; i < 64; i++)
        if (!((b->sha256[i] >= '0' && b->sha256[i] <= '9') || (b->sha256[i] >= 'a' && b->sha256[i] <= 'f'))) return 0;
    snprintf(prefix, sizeof prefix, FORGE_PACK_PREFIX "%s\\", b->slug);
    if (strncmp(b->tag, prefix, strlen(prefix))) return 0;
    return forge_token(b->tag + strlen(prefix), 1);
}

// Used before a layout's palette index creates an object. An installed pack
// with the same name alone is not sufficient: its exact bytes and tag matter.
static int forge_binding_matches(const forge_pack_binding *required,
                                 const forge_pack_binding *installed, const char *palette_tag) {
    return required && installed && palette_tag
        && forge_binding_valid(required) && forge_binding_valid(installed)
        && !strcmp(required->tag, palette_tag) && !strcmp(installed->tag, palette_tag)
        && !strcmp(required->slug, installed->slug)
        && !strcmp(required->version, installed->version)
        && !strcmp(required->sha256, installed->sha256);
}

// Split exactly n tab-separated fields, rejecting overlong/empty rows.
static int forge_fields(char *line, char **fields, int n) {
    size_t len = strlen(line);
    while (len && (line[len - 1] == '\n' || line[len - 1] == '\r')) line[--len] = 0;
    if (!len) return 0;
    fields[0] = line;
    int count = 1;
    for (char *p = line; *p; p++) {
        if (*p == '\t') {
            if (count == n) return 0;
            *p = 0;
            fields[count++] = p + 1;
        } else if ((unsigned char)*p < 32) return 0;
    }
    if (count != n) return 0;
    for (int i = 0; i < n; i++) if (!*fields[i]) return 0;
    return 1;
}

static int forge_binding_parse(char *line, int layout, forge_pack_binding *b) {
    char *f[5];
    if (!forge_fields(line, f, layout ? 5 : 4)) return 0;
    const char *slug = f[0], *version = f[1], *hash = f[2], *tag = f[3];
    b->flat = -1;
    if (layout) {
        b->flat = 0;
        for (const char *p = f[0]; *p; p++) {
            if (*p < '0' || *p > '9' || b->flat > 25) return 0;
            b->flat = b->flat * 10 + *p - '0';
        }
        if (b->flat > 254) return 0;
        tag = f[1]; slug = f[2]; version = f[3]; hash = f[4];
    }
    if (strlen(slug) >= sizeof b->slug || strlen(version) >= sizeof b->version
        || strlen(hash) >= sizeof b->sha256 || strlen(tag) >= sizeof b->tag) return 0;
    memcpy(b->slug, slug, strlen(slug) + 1);
    memcpy(b->version, version, strlen(version) + 1);
    memcpy(b->sha256, hash, strlen(hash) + 1);
    memcpy(b->tag, tag, strlen(tag) + 1);
    return forge_binding_valid(b);
}
#endif
