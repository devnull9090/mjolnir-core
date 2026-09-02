# Scoop bucket

This directory is a [Scoop](https://scoop.sh) bucket. Scoop reads manifests
straight out of a git repository, so publishing to it is a commit rather than a
submission to anyone.

```powershell
scoop bucket add mjolnir https://github.com/devnull9090/mjolnir-core
scoop install mjolnir
scoop update mjolnir
```

`mjolnir.json` is written by `.github/workflows/release-cli.yml` on every
`cli-v*` tag: it pins that release's download URL and its SHA-256, so an install
either gets the exact bytes CI built or fails. It is not hand-edited, and it does
not exist until the first CLI release has been tagged.

`checkver` and `autoupdate` in the manifest are for Scoop's own excavator bot.
They are a convenience for anyone who forks the bucket; this repository does not
rely on them, because a manifest whose hash is written by a bot that may never
run is a manifest that can advertise a build nobody verified.
