"""Copy owned TST images into a new authoring bundle without overwriting files."""
import hashlib
from pathlib import Path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def copy_owned_image(source, source_root, output_root):
    """Return a Blender-relative path inside output_root for one owned image."""
    source = Path(source)
    source_root = Path(source_root).resolve(strict=True)
    output_root = Path(output_root).resolve(strict=True)
    if source.is_symlink():
        raise ValueError(f'Owned texture cannot be a link: {source}')
    source = source.resolve(strict=True)
    allowed = (source_root / 'art' / 'textures').resolve(strict=True)
    if not source.is_file() or not source.is_relative_to(allowed):
        raise ValueError(f'Texture is not inside the owned TST texture folder: {source}')
    relative = source.relative_to(source_root)
    target = output_root / relative
    if not target.resolve().is_relative_to(output_root) or target.is_symlink():
        raise ValueError(f'Bundle texture path escapes the output: {target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    source_hash = digest(source)
    if target.exists():
        # One image can be used by several materials. A different existing
        # file is never replaced, even when its name matches.
        if not target.is_file() or digest(target) != source_hash:
            raise FileExistsError(f'Existing bundle texture differs: {target}')
    else:
        with source.open('rb') as src, target.open('xb') as dst:
            for block in iter(lambda: src.read(1024 * 1024), b''):
                dst.write(block)
    if digest(source) != source_hash or digest(target) != source_hash:
        raise RuntimeError(f'Texture changed during bundling: {source}')
    return '//' + relative.as_posix()
