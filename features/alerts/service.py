"""
[Alerts 도메인 - DB 연동]
alert 테이블의 경보를 판독관이 확인하고, 필요할 때 intel_report 초안을 만드는 함수 모음.
쓰기 작업은 shared.database 규칙대로 begin() 트랜잭션에서 처리한다.
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from sqlalchemy import text

from shared.database import get_engine

_DB = "satellite_intel"

# alert -> change_event -> equipment / image_analysis 순서로 조인해 경보 목록·상세
# 조회(fetch_alerts/fetch_alert_by_id)가 공통으로 쓰는 SELECT. WHERE절만 갈아 끼운다.
_ALERT_SELECT = f"""
    SELECT
      a.alert_id, a.alert_level, a.title, a.message,
      a.alert_status, a.created_at,
      ce.event_type, ce.previous_count, ce.current_count, ce.delta_count,
      e.class_name, e.category, e.threat_level,
      ia.asset_name, ia.region_name, ia.sensor_type, ia.captured_time,
      EXISTS(
        SELECT 1 FROM `{_DB}`.`intel_report` ir
        WHERE ir.alert_id = a.alert_id
      ) AS has_report
    FROM `{_DB}`.`alert` a
    JOIN `{_DB}`.`change_event` ce ON ce.change_id = a.change_id
    JOIN `{_DB}`.`equipment` e ON e.equipment_id = ce.equipment_id
    JOIN `{_DB}`.`image_analysis` ia ON ia.image_id = ce.current_image_id
"""


def fetch_alerts(
    level: Optional[Union[str, Sequence[str]]],
    status: Optional[str],
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """경보 목록을 최신순으로 가져온다. level은 단일 등급 문자열이나 등급 목록(리스트) 둘 다 받는다."""
    where = []
    params: Dict[str, Any] = {"limit": int(limit)}

    if level:
        if isinstance(level, str):
            where.append("a.alert_level = :level")
            params["level"] = level
        else:
            levels = list(level)
            placeholders = ", ".join(f":level{i}" for i in range(len(levels)))
            where.append(f"a.alert_level IN ({placeholders})")
            params.update({f"level{i}": lvl for i, lvl in enumerate(levels)})
    if status:
        where.append("a.alert_status = :status")
        params["status"] = status

    where_sql = "WHERE " + " AND ".join(where) if where else ""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(f"{_ALERT_SELECT} {where_sql} ORDER BY a.alert_id DESC LIMIT :limit"),
            params,
        ).fetchall()
    return [dict(row._mapping) for row in rows]


def fetch_alert_by_id(alert_id: int) -> Optional[Dict[str, Any]]:
    """alert_id 하나에 해당하는 경보를 상세 정보와 함께 조회한다 (없으면 None).

    HQ Desk의 경보 목록에서 행을 눌러 이 페이지로 넘어왔을 때, 그 경보를 표 선택 없이
    바로 보여주는 용도.
    """
    with get_engine().connect() as conn:
        row = conn.execute(
            text(f"{_ALERT_SELECT} WHERE a.alert_id = :alert_id"),
            {"alert_id": alert_id},
        ).fetchone()
    return dict(row._mapping) if row else None


def fetch_report(alert_id: int) -> Optional[Dict[str, Any]]:
    """선택 경보의 최신 보고서를 작성자 이름과 함께 가져온다 (없으면 None)."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                f"SELECT ir.report_id, ir.title, ir.summary, ir.report_status, "
                f"ir.distributed_at, au.user_name, au.role "
                f"FROM `{_DB}`.`intel_report` ir "
                f"JOIN `{_DB}`.`app_user` au ON au.user_id = ir.author_id "
                "WHERE ir.alert_id = :alert_id "
                "ORDER BY ir.report_id DESC LIMIT 1"
            ),
            {"alert_id": alert_id},
        ).fetchone()
    return dict(row._mapping) if row else None


def mark_checked(alert_id: int) -> int:
    """선택 경보를 확인 처리한다."""
    with get_engine().begin() as conn:
        result = conn.execute(
            text(
                f"UPDATE `{_DB}`.`alert` "
                "SET alert_status = 'CHECKED' "
                "WHERE alert_id = :alert_id"
            ),
            {"alert_id": alert_id},
        )
    return int(result.rowcount or 0)


def mark_all_checked() -> int:
    """미확인 경보 전체를 확인 처리한다."""
    with get_engine().begin() as conn:
        result = conn.execute(
            text(
                f"UPDATE `{_DB}`.`alert` "
                "SET alert_status = 'CHECKED' "
                "WHERE alert_status = 'NEW'"
            )
        )
    return int(result.rowcount or 0)


def ensure_report_draft(alert_id: int) -> Tuple[int, bool]:
    """선택 경보에 대한 intel_report 초안을 만들거나 기존 초안을 반환한다."""
    with get_engine().begin() as conn:
        existing = conn.execute(
            text(
                f"SELECT report_id FROM `{_DB}`.`intel_report` "
                "WHERE alert_id = :alert_id "
                "ORDER BY report_id DESC LIMIT 1"
            ),
            {"alert_id": alert_id},
        ).fetchone()
        if existing:
            return int(existing[0]), False

        analyst = conn.execute(
            text(
                f"SELECT user_id FROM `{_DB}`.`app_user` "
                "WHERE role = 'ANALYST' AND is_active = 1 "
                "ORDER BY user_id LIMIT 1"
            )
        ).fetchone()
        if analyst is None:
            raise ValueError("활성 ANALYST 사용자를 찾을 수 없습니다.")

        alert = conn.execute(
            text(
                f"SELECT title, message FROM `{_DB}`.`alert` "
                "WHERE alert_id = :alert_id"
            ),
            {"alert_id": alert_id},
        ).fetchone()
        if alert is None:
            raise ValueError(f"alert_id={alert_id} 경보가 없습니다.")

        result = conn.execute(
            text(
                f"INSERT INTO `{_DB}`.`intel_report` "
                "(alert_id, author_id, title, summary, report_status) "
                "VALUES (:alert_id, :author_id, :title, :summary, 'DRAFT')"
            ),
            {
                "alert_id": alert_id,
                "author_id": int(analyst[0]),
                "title": f"경보 보고: {alert[0]}",
                "summary": alert[1],
            },
        )
    return int(result.lastrowid), True
