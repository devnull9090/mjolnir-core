# Homebrew tap

This directory makes the repository a [Homebrew](https://brew.sh) tap. A tap is
a git repository, so publishing to it is a commit rather than a submission to
anyone — the same arrangement as [`bucket/`](../bucket) for Scoop.

```bash
brew tap devnull9090/core https://github.com/devnull9090/mjolnir-core
brew install mjolnir
brew upgrade mjolnir
```

Works on macOS and on Linux (Homebrew runs on both). The formula serves the
universal binary to macOS — one file for Intel and Apple Silicon — and the
statically linked binary to Linux.

`mjolnir.rb` is written by `.github/workflows/release-cli.yml` on every `cli-v*`
tag, pinned to that release's SHA-256, so an install either gets the exact bytes
CI built or fails. It is not hand-edited, and it does not exist until the first
CLI release has been tagged.

`HomebrewFormula/` rather than `Formula/` because brew looks in both, and this
repository is a great deal more than a tap.
