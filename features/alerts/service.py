"""
[Alerts 도메인 - DB 연동]
alert 테이블의 경보를 판독관이 확인하고, 필요할 때 intel_report 초안을 만드는 함수 모음.
쓰기 작업은 shared.database 규칙대로 begin() 트랜잭션에서 처리한다.
"""
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from shared.database import get_engine

_DB = "satellite_intel"


def fetch_alerts(level: Optional[str], status: Optional[str], limit: int = 100) -> List[Dict[str, Any]]:
    """경보 목록을 최신순으로 가져온다."""
    where = []
    params: Dict[str, Any] = {"limit": int(limit)}

    if level:
        where.append("a.alert_level = :level")
        params["level"] = level
    if status:
        where.append("a.alert_status = :status")
        params["status"] = status

    where_sql = "WHERE " + " AND ".join(where) if where else ""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                f"""
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
                {where_sql}
                ORDER BY a.alert_id DESC
                LIMIT :limit
                """
            ),
            params,
        ).fetchall()
    return [dict(row._mapping) for row in rows]


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
