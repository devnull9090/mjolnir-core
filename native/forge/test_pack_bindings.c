// Portable tests: cc -std=c11 -Wall -Wextra -Werror test_pack_bindings.c -o test_pack_bindings
#include "pack_bindings.h"
#include <stdlib.h>

static int checks = 0;
#define CHECK(value) do { checks++; if (!(value)) { \
    fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #value); exit(1); \
} } while (0)

static const char *hash = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
static const char *tag = FORGE_PACK_PREFIX "foundry\\platform_4x4";

static int parse(const char *value, int layout, forge_pack_binding *out) {
    char line[1024];
    if (strlen(value) >= sizeof line) return 0;
    memcpy(line, value, strlen(value) + 1);
    return forge_binding_parse(line, layout, out);
}

static void identity_tests(void) {
    char line[1024];
    forge_pack_binding inventory, layout;
    snprintf(line, sizeof line, "foundry\t1.2.3-beta.4+source.12\t%s\t%s\n", hash, tag);
    CHECK(parse(line, 0, &inventory));
    CHECK(inventory.flat == -1);
    CHECK(!strcmp(inventory.slug, "foundry"));
    CHECK(!strcmp(inventory.version, "1.2.3-beta.4+source.12"));
    CHECK(!strcmp(inventory.sha256, hash));
    CHECK(!strcmp(inventory.tag, tag));

    snprintf(line, sizeof line, "254\t%s\tfoundry\t1.2.3-beta.4+source.12\t%s\r\n", tag, hash);
    CHECK(parse(line, 1, &layout));
    CHECK(layout.flat == 254);
    CHECK(forge_binding_matches(&layout, &inventory, tag));
    CHECK(!forge_binding_matches(&layout, NULL, tag));
    CHECK(!forge_binding_matches(NULL, &inventory, tag));
    CHECK(!forge_binding_matches(&layout, &inventory, NULL));
    CHECK(!forge_binding_matches(&layout, &inventory, FORGE_PACK_PREFIX "foundry\\wall"));
    CHECK(!forge_binding_matches(&layout, &inventory, "objects\\props\\crate"));
    // A later release in the line has other bytes: the hash is diagnostic.
    inventory.sha256[0] = 'f';
    CHECK(forge_binding_matches(&layout, &inventory, tag));
    inventory.sha256[0] = hash[0];
    inventory.version[0] = '2';
    CHECK(!forge_binding_matches(&layout, &inventory, tag));
    inventory.version[0] = '1';
    inventory.tag[strlen(inventory.tag) - 1] = '8';
    CHECK(!forge_binding_matches(&layout, &inventory, tag));
    inventory.tag[strlen(inventory.tag) - 1] = '4';
    CHECK(forge_binding_matches(&layout, &inventory, tag));

    // ^saved, read as Rust semver reads it (the launcher's resolution).
    static const struct { const char *saved, *installed; int ok; } lines[] = {
        { "0.2.0", "0.2.0", 1 }, { "0.2.0", "0.2.7", 1 }, { "0.2.3", "0.2.1", 0 },
        { "0.2.0", "0.3.0", 0 }, { "0.2.0", "1.0.0", 0 }, { "0.0.3", "0.0.4", 0 },
        { "1.2.0", "1.9.1", 1 }, { "1.2.0", "1.10.0", 1 }, { "1.2.5", "1.2.4", 0 },
        { "1.2.0", "2.0.0", 0 }, { "1.2.0", "1.3.0-beta.1", 0 }, { "1.2.0", "1.2.0-rc.1", 0 },
        { "1.2.0-rc.1", "1.2.0-rc.2", 1 }, { "1.2.0-rc.2", "1.2.0-rc.10", 1 },
        { "1.2.0-rc.2", "1.2.0-rc.1", 0 }, { "1.2.0-rc.1", "1.2.0", 1 }, { "1.2.0-rc.1", "1.4.0", 1 },
        { "1.2.0-alpha", "1.2.0-alpha.1", 1 }, { "1.2.0-beta", "1.2.0-alpha", 0 },
        { "1.2.0-alpha.1", "1.2.0-alpha.beta", 1 }, { "1.2.0+one", "1.2.0+two", 1 },
    };
    for (size_t i = 0; i < sizeof lines / sizeof *lines; i++) {
        snprintf(layout.version, sizeof layout.version, "%s", lines[i].saved);
        snprintf(inventory.version, sizeof inventory.version, "%s", lines[i].installed);
        if (forge_binding_matches(&layout, &inventory, tag) != lines[i].ok) {
            fprintf(stderr, "FAIL ^%s against %s\n", lines[i].saved, lines[i].installed);
            exit(1);
        }
        checks++;
    }

    const char *bad_slugs[] = { "", "a", "-a", "_a", "Foundry", "found_ry", "../foundry", "foundry/other" };
    for (size_t i = 0; i < sizeof bad_slugs / sizeof *bad_slugs; i++) {
        snprintf(line, sizeof line, "%s\t1.0.0\t%s\t%s%s\\block", bad_slugs[i], hash, FORGE_PACK_PREFIX, bad_slugs[i]);
        CHECK(!parse(line, 0, &inventory));
    }
    const char *bad_ids[] = { "", "-block", "_block", "Block", "../block", "block\\nested", "block/other", "block.with.dot" };
    for (size_t i = 0; i < sizeof bad_ids / sizeof *bad_ids; i++) {
        snprintf(line, sizeof line, "foundry\t1.0.0\t%s\t%sfoundry\\%s", hash, FORGE_PACK_PREFIX, bad_ids[i]);
        CHECK(!parse(line, 0, &inventory));
    }
    snprintf(line, sizeof line, "foundry\t1.0.0\t%s\t%sother\\block", hash, FORGE_PACK_PREFIX);
    CHECK(!parse(line, 0, &inventory));
    snprintf(line, sizeof line, "foundry\t1.0.0\t%s\tobjects/mjolnir/forge/foundry/block", hash);
    CHECK(!parse(line, 0, &inventory));
    snprintf(line, sizeof line, "foundry\t1.0.0\t%s\t%s", hash + 1, tag);
    CHECK(!parse(line, 0, &inventory));
    snprintf(line, sizeof line, "foundry\t1.0.0\tG%s\t%s", hash + 1, tag);
    CHECK(!parse(line, 0, &inventory));
}

static void version_tests(void) {
    const char *good[] = { "0.0.0", "1.2.3", "12.100.999", "1.0.0-beta.1", "1.0.0-0", "1.0.0--", "1.0.0+00", "1.0.0-rc.2+Build-9" };
    const char *bad[] = { "", "banana", "1", "1.2", "1.2.3.4", "01.2.3", "1.02.3", "1.2.03", "^1.2.3", "=1.2.3", "1.2.3-", "1.2.3-01", "1.2.3-rc..1", "1.2.3-rc.", "1.2.3+", "1.2.3+a..b", "1.2.3+a.", "1.2.3+a_b", "1.2.3 ", "1.2.3-rc+ok+bad" };
    for (size_t i = 0; i < sizeof good / sizeof *good; i++) CHECK(forge_version(good[i]));
    for (size_t i = 0; i < sizeof bad / sizeof *bad; i++) CHECK(!forge_version(bad[i]));
}

static void row_tests(void) {
    char row[1024], mutated[1024];
    forge_pack_binding b;
    snprintf(row, sizeof row, "foundry\t1.0.0\t%s\t%s", hash, tag);
    CHECK(parse(row, 0, &b)); // Last row need not have a newline.
    CHECK(!parse(row, 1, &b));
    CHECK(!parse("", 0, &b));
    CHECK(!parse("\n", 0, &b));
    CHECK(!parse("\tfoundry\t1.0.0\ttag", 0, &b));
    CHECK(!parse("foundry\t\thash\ttag", 0, &b));
    CHECK(!parse("foundry\t1.0.0\thash\t", 0, &b));
    snprintf(mutated, sizeof mutated, "%s\textra", row);
    CHECK(!parse(mutated, 0, &b));
    memcpy(mutated, row, strlen(row) + 1);
    mutated[2] = '\r';
    CHECK(!parse(mutated, 0, &b));
    const char *indices[] = { "-1", "255", "65535", "9999999999999999999", "+1", "1x", " 1", "" };
    for (size_t i = 0; i < sizeof indices / sizeof *indices; i++) {
        snprintf(mutated, sizeof mutated, "%s\t%s\tfoundry\t1.0.0\t%s", indices[i], tag, hash);
        CHECK(!parse(mutated, 1, &b));
    }
    for (int i = 0; i < 255; i++) {
        snprintf(mutated, sizeof mutated, "%d\t%s\tfoundry\t1.0.0\t%s", i, tag, hash);
        CHECK(parse(mutated, 1, &b));
        CHECK(b.flat == i);
    }
    char long_id[66];
    memset(long_id, 'a', sizeof long_id - 1); long_id[sizeof long_id - 1] = 0;
    snprintf(mutated, sizeof mutated, "foundry\t1.0.0\t%s\t%sfoundry\\%s", hash, FORGE_PACK_PREFIX, long_id);
    CHECK(!parse(mutated, 0, &b));
    long_id[64] = 0;
    snprintf(mutated, sizeof mutated, "foundry\t1.0.0\t%s\t%sfoundry\\%s", hash, FORGE_PACK_PREFIX, long_id);
    CHECK(parse(mutated, 0, &b));
}

int main(void) {
    identity_tests();
    version_tests();
    row_tests();
    printf("Forge pack bindings: %d checks passed\n", checks);
    return 0;
}
