"""
[공용 - 변화 분석과 경보 생성]
저장된 detection_result를 이전 영상과 비교해 change_event를 만들고,
equipment.threat_level 기반 SQL 규칙으로 alert 테이블에 경보를 적재한다.
SAR/EO 같은 탐지 화면이 공통으로 부를 수 있도록 shared 아래에 둔다.

기존 분석 로그는 지우지 않는다(append-only). 같은 이미지를 다시 분석하면
마지막 로그와 수량이 달라진 장비만 '[수정]' 표시가 붙은 새 로그로 추가되고,
경보는 아직 발행되지 않은 이벤트에 대해서만 생성된다.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from shared.database import get_engine

_DB = "satellite_intel"


@dataclass
class ChangeAnalysisOutcome:
    """한 image_id에 대한 변화 분석 결과."""
    image_id: int
    previous_image_id: Optional[int]
    events_created: int                    # 이번 실행에서 새로 추가된 change_event 수
    alerts_created: List[Dict[str, Any]]   # 이번 실행에서 새로 발행된 경보 목록
    replaced_previous_analysis: bool       # 기존 분석 로그가 있는 상태의 수정 기록인지


def analyze_image_change(image_id: int) -> ChangeAnalysisOutcome:
    """현재 image_id의 탐지 결과를 직전 영상과 비교하고 경보를 생성한다.

    기존 로그는 지우지 않고, 마지막 로그와 수량이 달라진 장비만 새 로그로 추가한다.
    """
    with get_engine().begin() as conn:
        current = _fetch_image(conn, image_id)
        if current is None:
            raise ValueError(f"image_analysis에 image_id={image_id} 행이 없습니다.")

        previous_id = _fetch_previous_image_id(conn, current)
        if previous_id is None:
            return ChangeAnalysisOutcome(
                image_id=image_id,
                previous_image_id=None,
                events_created=0,
                alerts_created=[],
                replaced_previous_analysis=False,
            )

        # 기존 로그가 이미 있으면 이번 실행은 '수정 기록' 추가다.
        replaced_previous_analysis = bool(
            conn.execute(
                text(
                    f"SELECT EXISTS(SELECT 1 FROM `{_DB}`.`change_event` "
                    "WHERE current_image_id = :image_id)"
                ),
                {"image_id": image_id},
            ).scalar_one()
        )
        # 이번 실행에서 새로 발행된 경보만 골라내기 위한 기준점(직전 최대 alert_id).
        last_alert_id = int(
            conn.execute(
                text(f"SELECT COALESCE(MAX(alert_id), 0) FROM `{_DB}`.`alert`")
            ).scalar_one()
        )

        events_created = _insert_change_events(conn, previous_id, image_id)
        _insert_alerts(conn, image_id)
        alerts_created = _fetch_alerts_for_image(conn, image_id, last_alert_id)

    return ChangeAnalysisOutcome(
        image_id=image_id,
        previous_image_id=previous_id,
        events_created=int(events_created),
        alerts_created=alerts_created,
        replaced_previous_analysis=replaced_previous_analysis,
    )


def _fetch_image(conn, image_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        text(
            f"SELECT asset_name, region_name, captured_time "
            f"FROM `{_DB}`.`image_analysis` WHERE image_id = :image_id"
        ),
        {"image_id": image_id},
    ).fetchone()
    return dict(row._mapping) if row else None


def _fetch_previous_image_id(conn, current: Dict[str, Any]) -> Optional[int]:
    row = conn.execute(
        text(
            f"SELECT image_id FROM `{_DB}`.`image_analysis` "
            "WHERE asset_name = :asset_name "
            "AND region_name = :region_name "
            "AND captured_time < :captured_time "
            "ORDER BY captured_time DESC, image_id DESC LIMIT 1"
        ),
        {
            "asset_name": current["asset_name"],
            "region_name": current["region_name"],
            "captured_time": current["captured_time"],
        },
    ).fetchone()
    return int(row[0]) if row else None


def _insert_change_events(conn, previous_image_id: int, current_image_id: int) -> int:
    # 기존 로그는 지우지 않는다. 같은 (이전, 현재, 장비) 조합의 '마지막 로그'와
    # 수량이 달라진 경우에만 새 로그를 추가한다 (수정 기록은 summary에 [수정] 표시).
    result = conn.execute(
        text(
            f"""
            INSERT INTO `{_DB}`.`change_event`
              (previous_image_id, current_image_id, equipment_id, event_type,
               previous_count, current_count, delta_count, summary)
            SELECT
              :previous_image_id,
              :current_image_id,
              ids.equipment_id,
              CASE
                WHEN COALESCE(prev.detected_count, 0) = 0
                     AND COALESCE(curr.detected_count, 0) > 0 THEN 'NEW'
                WHEN COALESCE(prev.detected_count, 0) > 0
                     AND COALESCE(curr.detected_count, 0) = 0 THEN 'DISAPPEARED'
                WHEN COALESCE(curr.detected_count, 0) > COALESCE(prev.detected_count, 0)
                     THEN 'INCREASED'
                ELSE 'DECREASED'
              END,
              COALESCE(prev.detected_count, 0),
              COALESCE(curr.detected_count, 0),
              COALESCE(curr.detected_count, 0) - COALESCE(prev.detected_count, 0),
              CONCAT(
                CASE WHEN last_log.equipment_id IS NULL THEN '' ELSE '[수정] ' END,
                e.class_name, ' 장비 수량 변화 감지 (',
                COALESCE(prev.detected_count, 0), ' -> ',
                COALESCE(curr.detected_count, 0), ')'
              )
            FROM (
              SELECT equipment_id FROM `{_DB}`.`detection_result`
              WHERE image_id = :previous_image_id
              UNION
              SELECT equipment_id FROM `{_DB}`.`detection_result`
              WHERE image_id = :current_image_id
            ) ids
            LEFT JOIN `{_DB}`.`detection_result` prev
              ON prev.image_id = :previous_image_id
             AND prev.equipment_id = ids.equipment_id
            LEFT JOIN `{_DB}`.`detection_result` curr
              ON curr.image_id = :current_image_id
             AND curr.equipment_id = ids.equipment_id
            JOIN `{_DB}`.`equipment` e
              ON e.equipment_id = ids.equipment_id
            LEFT JOIN (
              SELECT ce.equipment_id, ce.previous_count, ce.current_count
              FROM `{_DB}`.`change_event` ce
              JOIN (
                SELECT equipment_id, MAX(change_id) AS max_change_id
                FROM `{_DB}`.`change_event`
                WHERE previous_image_id = :previous_image_id
                  AND current_image_id = :current_image_id
                GROUP BY equipment_id
              ) latest ON latest.max_change_id = ce.change_id
            ) last_log
              ON last_log.equipment_id = ids.equipment_id
            WHERE COALESCE(prev.detected_count, 0) <> COALESCE(curr.detected_count, 0)
              AND (
                last_log.equipment_id IS NULL
                OR last_log.previous_count <> COALESCE(prev.detected_count, 0)
                OR last_log.current_count <> COALESCE(curr.detected_count, 0)
              )
            """
        ),
        {
            "previous_image_id": previous_image_id,
            "current_image_id": current_image_id,
        },
    )
    return int(result.rowcount or 0)


def _insert_alerts(conn, image_id: int) -> None:
    conn.execute(
        text(
            f"""
            INSERT INTO `{_DB}`.`alert`
              (change_id, alert_level, title, message, alert_status, created_at)
            SELECT
              ce.change_id,
              CASE
                WHEN e.threat_level = 1 THEN 'URGENT'
                WHEN e.threat_level = 2 AND ABS(ce.delta_count) >= 10 THEN 'IMPORTANT'
                WHEN e.threat_level = 3 AND ce.delta_count >= 20 THEN 'NOTICE'
              END AS alert_level,
              CONCAT(
                CASE
                  WHEN e.threat_level = 1 THEN '[긴급] '
                  WHEN e.threat_level = 2 THEN '[중요] '
                  ELSE '[특이] '
                END,
                e.class_name, ' 표적 수량 변화'
              ) AS title,
              CONCAT(
                ia.region_name, ' / ', ia.asset_name, ' - ',
                e.class_name, ' 수량 변화: ',
                ce.previous_count, '대 -> ', ce.current_count, '대',
                ' (변화량 ', ce.delta_count, '대, 이벤트 ', ce.event_type, ')'
              ) AS message,
              'NEW',
              NOW()
            FROM `{_DB}`.`change_event` ce
            JOIN `{_DB}`.`equipment` e
              ON ce.equipment_id = e.equipment_id
            JOIN `{_DB}`.`image_analysis` ia
              ON ce.current_image_id = ia.image_id
            WHERE ce.current_image_id = :image_id
              AND (
                e.threat_level = 1
                OR (e.threat_level = 2 AND ABS(ce.delta_count) >= 10)
                OR (e.threat_level = 3 AND ce.delta_count >= 20)
              )
              AND NOT EXISTS (
                SELECT 1 FROM `{_DB}`.`alert` a
                WHERE a.change_id = ce.change_id
              )
            """
        ),
        {"image_id": image_id},
    )


def _fetch_alerts_for_image(conn, image_id: int, after_alert_id: int) -> List[Dict[str, Any]]:
    """이번 실행에서 새로 발행된 경보(alert_id가 기준점 이후인 것)만 돌려준다."""
    rows = conn.execute(
        text(
            f"""
            SELECT a.alert_level, a.title
            FROM `{_DB}`.`alert` a
            JOIN `{_DB}`.`change_event` ce
              ON ce.change_id = a.change_id
            WHERE ce.current_image_id = :image_id
              AND a.alert_id > :after_alert_id
            ORDER BY a.alert_id
            """
        ),
        {"image_id": image_id, "after_alert_id": after_alert_id},
    ).fetchall()
    return [dict(row._mapping) for row in rows]
