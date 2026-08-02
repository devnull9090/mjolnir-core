# Experimental signatures — not shipped

These AOB signatures belong to the FName injector track in this directory
(`fname_trampoline.c`, "MJOLNIR FName Injector v3"), **not** to the runtime
that ships today.

`FName_Constructor.lua` here matches a `MJOL`/`NIR!` marker that
`fname_trampoline.c` emits as multi-byte NOP operands at the start of its
injected trampoline. The trampoline registers itself in the PE exception
table via `RtlAddFunctionTable`, and the signature finds it by that marker.

Nothing builds `native/`. No workflow references it, so the trampoline is
never injected, so these signatures cannot resolve against a stock game
binary. They lived in `signatures/` until 2026-08-01, where they were one
edit to `scripts/build-modpack.ps1` away from shipping and breaking every
install — the build only avoided it by overwriting them with upstream's
copies immediately after copying them in.

They are kept because the injector work is real and worth resuming. They are
moved here so that a build can only pick them up deliberately.

The signatures that actually ship live in `/signatures`. See that directory's
README for the rule about RIP-relative displacements.
