"""
[공용 - S3 이미지 저장소]
이미지(original_image/, result_image/)의 원본 저장소는 S3 버킷이다.
저장 시 로컬 파일 없이 메모리에서 바로 업로드하고(upload_bytes), 조회 시에는
로컬 폴더를 다운로드 캐시로 쓴다(ensure_local — 없으면 내려받아 저장 후 재사용).
DB의 image_analysis에는 기존처럼 상대경로만 저장되며, 그 경로가 곧 S3 키다.

접속 정보는 .env에서 읽는다 (shared/database.py와 같은 방식):
  AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY  (boto3가 환경변수에서 자동으로 읽음)
  AWS_S3_BUCKET  = 버킷 이름
  AWS_REGION     = 버킷 리전 (예: ap-northeast-2)

오류 정책:
  - upload_bytes: 실패·미설정 시 예외를 던진다 — S3가 유일한 저장소라서, 업로드
    실패를 조용히 넘기면 DB에만 행이 남는 유령 이미지가 생기기 때문.
  - ensure_local: 예외를 던지지 않는다 — 조회 화면은 "이미지 없음"으로 처리하면 된다.
"""
import logging
import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")

log = logging.getLogger(__name__)

_BUCKET = os.getenv("AWS_S3_BUCKET", "").strip()
_REGION = os.getenv("AWS_REGION", "").strip()

_client = None  # boto3 클라이언트는 처음 쓸 때 한 번만 만들어 재사용


def is_configured() -> bool:
    """S3 연동이 켜져 있는지 (.env에 AWS_S3_BUCKET이 있는지)."""
    return bool(_BUCKET)


def _get_client():
    global _client
    if _client is None:
        import boto3  # 미설정 환경에서 boto3 없이도 앱이 뜨도록 지연 임포트

        _client = boto3.client("s3", region_name=_REGION or None)
    return _client


def _to_key(rel_path: str) -> str:
    """윈도우 경로 구분자가 섞여 들어와도 S3 키는 항상 '/'를 쓴다."""
    return str(rel_path).replace("\\", "/")


def upload_bytes(rel_path: str, data: bytes) -> None:
    """메모리의 bytes를 상대경로를 키로 버킷에 올린다 (로컬 파일 저장 없음).

    S3가 유일한 이미지 저장소이므로, 미설정이거나 업로드가 실패하면 예외를 던진다.
    저장 흐름(이미지 업로드 → DB 기록)에서 먼저 호출되므로, 여기서 실패하면
    DB에는 아무것도 남지 않는다.
    """
    if not is_configured():
        raise RuntimeError(
            "S3가 설정되지 않았습니다. .env에 AWS_S3_BUCKET / AWS_REGION / "
            "AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY를 추가하세요."
        )
    _get_client().put_object(Bucket=_BUCKET, Key=_to_key(rel_path), Body=data)


def list_keys(prefix: str) -> List[str]:
    """prefix(예: "original_image/") 아래의 객체 키 목록을 이름순으로 돌려준다.

    화면의 선택 목록에 쓰이므로 실패 시 예외를 그대로 올린다 — 호출부가
    "목록 조회 실패"로 보여주고, 폴더가 비었으면 빈 목록이 온다.
    """
    if not is_configured():
        return []
    keys: List[str] = []
    paginator = _get_client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_BUCKET, Prefix=_to_key(prefix)):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
    return sorted(keys)


def ensure_local(rel_path: str) -> Optional[Path]:
    """상대경로의 파일을 로컬에서 찾고, 없으면 S3에서 내려받아 로컬 경로를 돌려준다.

    로컬에도 S3에도 없으면(또는 S3 미설정이면) None. 내려받은 파일은 원래 위치에
    저장되므로 다음 조회부터는 로컬 캐시로 바로 쓴다.
    """
    if not rel_path:
        return None
    local = _PROJECT_ROOT / rel_path
    if local.is_file():
        return local
    if not is_configured():
        return None
    try:
        local.parent.mkdir(parents=True, exist_ok=True)
        _get_client().download_file(_BUCKET, _to_key(rel_path), str(local))
    except Exception as exc:
        # 객체가 없는 것도 여기로 온다 — 조회 화면에서는 "없음"으로 처리하면 된다.
        log.info("S3에서 받지 못함 (%s): %s", rel_path, exc)
        return None
    return local if local.is_file() else None
