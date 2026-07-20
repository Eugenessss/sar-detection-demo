"""
[공용 - 로컬 이미지 저장소]
이미지(original_image/, result_image/)의 원본 저장소는 프로젝트 안의 로컬 폴더다.
(local-mysql 브랜치: AWS 없이 로컬 MySQL + 로컬 폴더만으로 시연하는 버전이라,
 S3 버전과 같은 함수 이름·시그니처를 유지해 호출부는 수정 없이 그대로 쓴다.)

DB의 image_analysis에는 기존처럼 프로젝트 기준 상대경로만 저장되며, 그 경로가
곧 로컬 파일 경로다 (예: "original_image/425-1_개풍군_1_SAR_2026-07-09 100000.tif").

오류 정책 (S3 버전과 동일):
  - upload_bytes: 실패 시 예외를 던진다 — 저장 흐름(이미지 저장 → DB 기록)에서
    먼저 호출되므로, 여기서 실패하면 DB에는 아무것도 남지 않는다.
  - ensure_local: 예외를 던지지 않는다 — 조회 화면은 "이미지 없음"으로 처리하면 된다.
"""
from pathlib import Path
from typing import List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def is_configured() -> bool:
    """로컬 폴더 저장소는 항상 사용 가능하다 (S3 버전과의 호환용)."""
    return True


def upload_bytes(rel_path: str, data: bytes) -> None:
    """메모리의 bytes를 상대경로 위치의 로컬 파일로 저장한다 (폴더가 없으면 만든다)."""
    target = _PROJECT_ROOT / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def list_keys(prefix: str) -> List[str]:
    """prefix(예: "original_image/") 폴더 바로 아래의 파일 목록을 이름순으로 돌려준다.

    S3 버전과 같은 형식("폴더/파일명", 구분자 '/')으로 돌려준다. 하위 폴더는 훑지
    않는다 — DB에 기록되는 경로가 전부 "폴더/파일명" 한 단계라서, 폴더 안에 남아있는
    백업 복사본 등이 선택 목록에 섞이지 않게 하기 위해서다.
    """
    folder = _PROJECT_ROOT / prefix
    if not folder.is_dir():
        return []
    return sorted(
        f"{folder.name}/{p.name}" for p in folder.iterdir() if p.is_file()
    )


def ensure_local(rel_path: str) -> Optional[Path]:
    """상대경로의 로컬 파일 경로를 돌려준다 (없으면 None — 화면에서 '이미지 없음' 처리)."""
    if not rel_path:
        return None
    local = _PROJECT_ROOT / rel_path
    return local if local.is_file() else None
