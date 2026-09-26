"""Install the local anime-character matte used by the Sopia thumbnail template."""

from __future__ import annotations

import argparse
import hashlib
import tempfile
import urllib.request
from pathlib import Path


MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-anime.onnx"
EXPECTED_MD5 = "6f184e756bb3bd901c8849220a83e38e"
DEFAULT_STORAGE_ROOT = Path(__file__).resolve().parents[1] / "storage"


def _md5(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - only verifies the upstream published artifact checksum
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install(storage_root: Path) -> Path:
    destination = storage_root / "models" / "isnet-anime.onnx"
    if destination.is_file() and _md5(destination) == EXPECTED_MD5:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".download", delete=False) as temporary:
        download = Path(temporary.name)
    try:
        urllib.request.urlretrieve(MODEL_URL, download)
        if _md5(download) != EXPECTED_MD5:
            raise ValueError("anime thumbnail model checksum did not match")
        download.replace(destination)
    finally:
        download.unlink(missing_ok=True)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-root", type=Path, default=DEFAULT_STORAGE_ROOT)
    args = parser.parse_args()
    print(f"Installed: {install(args.storage_root)}")
