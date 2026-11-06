/*
 * Offline test of mjolnir_test_input.c, run by build.ps1 -Test. It never touches
 * a running game: the slot is found and swapped in a private mapping of the exe
 * on disk, and the merge is checked against a stand-in for ReadInput.
 *
 *     test_test_input.exe <path to HaloCampaignEvolved.exe>
 */
#include "mjolnir_test_input.c"

static int failures;
#define CHECK(cond)                                         \
    do {                                                    \
        if (!(cond)) {                                      \
            printf("FAIL line %d: %s\n", __LINE__, #cond);  \
            failures++;                                     \
        }                                                   \
    } while (0)

/* As the real method leaves a block for a game in the background. */
static char __fastcall stand_in(void *source, unsigned user, unsigned char *block) {
    (void)source;
    (void)user;
    memset(block, 0, 0x134);
    return 1;
}

/* The file protocol, through the real worker, in a temporary folder. */
static void worker_round_trip(void) {
    char status[256] = "", ack[192] = "", command[MAX_PATH + 16], temporary[MAX_PATH + 16];
    GetTempPathA(sizeof dir, dir);
    strncat(dir, "mjolnir_test_input\\", sizeof dir - strlen(dir) - 1);
    CreateDirectoryA(dir, NULL);
    path_of(command, sizeof command, "input_cmd.txt");
    path_of(temporary, sizeof temporary, "input_status.txt");
    DeleteFileA(temporary);

    void *before = *slot;
    mjolnir_test_input_enable(NULL);
    mjolnir_test_input_enable(NULL); /* a second call leaves the worker alone */
    for (int i = 0; i < 500 && !status[0]; i++) {
        FILE *f = fopen(temporary, "rb");
        if (f) {
            status[fread(status, 1, sizeof status - 1, f)] = 0;
            fclose(f);
        }
        if (!status[0]) Sleep(10);
    }
    CHECK(strncmp(status, "ok slot 0x", 10) == 0);
    CHECK(*slot == (void *)read_input_hook);

    path_of(temporary, sizeof temporary, "input_ack.txt");
    DeleteFileA(temporary);
    FILE *f = fopen(command, "wb");
    fputs("id 41\nkey 87 1\noff\n", f);
    fclose(f);
    for (int i = 0; i < 500 && !ack[0]; i++) {
        FILE *a = fopen(temporary, "rb");
        if (a) {
            ack[fread(ack, 1, sizeof ack - 1, a)] = 0;
            fclose(a);
        }
        if (!ack[0]) Sleep(10);
    }
    CHECK(strncmp(ack, "id 41 ok reads 0 delivered 0", 28) == 0);
    for (int i = 0; i < 500 && running; i++) Sleep(10);
    CHECK(!running);
    CHECK(*slot == before);
    CHECK(key_down[87] == 0); /* `off` lets everything go */
}

static void run(const char *text) {
    char script[512], ack[192];
    strcpy(script, text);
    run_script(script, ack, sizeof ack);
    CHECK(strstr(ack, " ok ") != NULL);
}

int main(int argc, char **argv) {
    unsigned char block[0x134];

    if (argc > 1) {
        const unsigned char *base = (const unsigned char *)LoadLibraryExA(argv[1], NULL, DONT_RESOLVE_DLL_REFERENCES);
        CHECK(base != NULL);
        char why[160] = "";
        const int found = base && resolve(base, why, sizeof why);
        if (!found) printf("resolve: %s\n", why);
        CHECK(found);
        if (found) {
            printf("slot 0x%llx method 0x%llx\n", (unsigned long long)((const unsigned char *)slot - base),
                   (unsigned long long)((const unsigned char *)original - base));
            void *before = *slot;
            CHECK(before == (void *)original);
            CHECK(write_slot((void *)read_input_hook));
            CHECK(*slot == (void *)read_input_hook);
            CHECK(write_slot(before));
            CHECK(*slot == before);
            worker_round_trip();
        }
    }

    original = stand_in;

    /* Nothing of ours: the block is left as ReadInput made it. */
    read_input_hook(NULL, 0, block);
    CHECK(block[BLOCK_DEVICE] == 0);
    CHECK(reads == 1 && delivered == 0);

    /* A held key stays down, on keyboard and mouse, until it is released. */
    run("id 1\nkey 87 1\n");
    read_input_hook(NULL, 0, block);
    CHECK(block[BLOCK_KEYS + 87] == 1);
    CHECK(block[BLOCK_DEVICE] == DEVICE_KEYBOARD_MOUSE);
    read_input_hook(NULL, 0, block);
    CHECK(block[BLOCK_KEYS + 87] == 1);
    run("id 2\nkey 87 0\n");
    read_input_hook(NULL, 0, block);
    CHECK(block[BLOCK_KEYS + 87] == 0);

    /* A press that ends between two reads is seen once. */
    run("id 3\nkey 69 1\nkey 69 0\nbutton 1 1\nbutton 1 0\n");
    read_input_hook(NULL, 0, block);
    CHECK(block[BLOCK_KEYS + 69] == 1);
    CHECK(*(unsigned *)(block + BLOCK_BUTTONS) == 1);
    read_input_hook(NULL, 0, block);
    CHECK(block[BLOCK_KEYS + 69] == 0);
    CHECK(*(unsigned *)(block + BLOCK_BUTTONS) == 0);

    /* Look adds up between reads and is spent by the next one. */
    run("id 4\nlook 100 -40\nlook 20 0\n");
    read_input_hook(NULL, 0, block);
    CHECK(*(float *)(block + BLOCK_LOOK_X) == 120 * LOOK_PER_COUNT);
    CHECK(*(float *)(block + BLOCK_LOOK_Y) == -40 * LOOK_PER_COUNT);
    read_input_hook(NULL, 0, block);
    CHECK(*(float *)(block + BLOCK_LOOK_X) == 0);

    /* Only the first user. */
    run("id 5\nkey 87 1\n");
    read_input_hook(NULL, 1, block);
    CHECK(block[BLOCK_KEYS + 87] == 0);
    run("id 6\nrelease\n");
    read_input_hook(NULL, 0, block);
    read_input_hook(NULL, 0, block);
    CHECK(block[BLOCK_KEYS + 87] == 0);

    /* A bad line stops the script and says so; `off` is reported to the worker. */
    char ack[192], bad[] = "id 7\nkey 999 1\nkey 65 1\n", off[] = "id 8\noff\n";
    CHECK(run_script(bad, ack, sizeof ack) == 0);
    CHECK(strncmp(ack, "id 7 error", 10) == 0);
    CHECK(key_down[65] == 0);
    CHECK(run_script(off, ack, sizeof ack) == 1);

    printf(failures ? "%d failed\n" : "all passed\n", failures);
    return failures != 0;
}
