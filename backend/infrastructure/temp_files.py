import os
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from fastapi import UploadFile


async def save_upload_to_temp(upload: UploadFile, suffix: Optional[str] = None) -> Path:
    file_suffix = suffix or Path(upload.filename or "").suffix or ".tmp"
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_suffix) as tmp:
        tmp.write(await upload.read())
        return Path(tmp.name)


def cleanup_paths(paths: Iterable[Optional[Path]]) -> None:
    for path in paths:
        if path is None:
            continue
        try:
            os.unlink(path)
        except OSError:
            pass
