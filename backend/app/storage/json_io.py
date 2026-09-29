import json
import os
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4


_replace_lock = Lock()


def write_json_atomic(
    path: Path,
    payload: Any,
    *,
    indent: int | None = 2,
    separators: tuple[str, str] | None = None,
    allow_nan: bool = True,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        tmp.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=indent,
                separators=separators,
                allow_nan=allow_nan,
            )
            + "\n",
            encoding="utf-8",
        )
        with _replace_lock:
            os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path
