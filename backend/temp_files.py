"""
[공용 - 임시 파일 처리]
업로드된 이미지를 잠깐 디스크에 저장했다가, 추론이 끝나면 지우는 도우미 파일.
모델은 파일 경로가 필요하기 때문에 메모리에 들어온 업로드를 임시 파일로 떨궈준다.
특정 도메인에 묶이지 않는 공용 기능이라 backend/ 바로 아래에 둔다.
"""
import os
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from fastapi import UploadFile


async def save_upload_to_temp(upload: UploadFile, suffix: Optional[str] = None) -> Path:
    """업로드된 파일을 임시 폴더에 저장하고 그 경로를 돌려준다."""
    file_suffix = suffix or Path(upload.filename or "").suffix or ".tmp"
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_suffix) as tmp:
        tmp.write(await upload.read())
        return Path(tmp.name)


def cleanup_paths(paths: Iterable[Optional[Path]]) -> None:
    """넘겨받은 임시 파일들을 지운다 (이미 없거나 실패해도 조용히 넘어감)."""
    for path in paths:
        if path is None:
            continue
        try:
            os.unlink(path)
        except OSError:
            pass
