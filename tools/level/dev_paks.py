"""Local builds in the game's Paks that take precedence over hub content.

A tool that puts a container into Paks by hand goes through `mjolnir dev
install`, which names the copy `pakchunk<N>-MJOLNIRDEV-<name>_<v>_P`, loads it
above every hub container and every earlier local build, and renames its
shader library to its own chunk number N (crates/ue-iostore/src/paks.rs,
docs/chunk_numbering.md). A plain `_P` copy loses to the hub copy of the same
thing, silently; `mjolnir dev list` names every one that does.

A local build shadows the hub copy; it cannot delete it. A package the hub
copy has and the build does not still loads from the hub.
"""
import glob
import os


def install_command(cli, paks, container, name):
    """The command that installs `container` (its path without an extension)
    as the local build `name`, replacing an earlier build of that name."""
    return [str(cli), "dev", "install", str(container), "--name", name, "--paks", str(paks)]


def remove_command(cli, paks, name):
    return [str(cli), "dev", "remove", name, "--paks", str(paks)]


def hub_container_pattern(paks, slug, index):
    """The launcher's copy of container `index` of hub mod `slug`, under any
    chunk number and either name the launcher has used:
    `…-<index>_<v>_P` (load order by suffix) or `…-<index>_P` (before)."""
    return os.path.join(str(paks), f"pakchunk*-MJOLNIRHUB-{slug}-{index}_*P.utoc")


def hub_containers(paks, slug, index):
    """Paths without extension of the launcher's copies of that container."""
    return [f[:-len(".utoc")] for f in glob.glob(hub_container_pattern(paks, slug, index))]
