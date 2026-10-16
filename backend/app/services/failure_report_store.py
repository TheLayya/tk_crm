import base64
import json
from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from fastapi import HTTPException
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session, undefer

from app.models.card_key import CardKey, CardKeyProject
from app.models.failure_report import FailureReport


def create_report(db: Session, project: CardKeyProject, *, username: str, remark: str,
                  screenshots: list[dict[str, str | int]], key_id: int | None = None,
                  email_id: int | None = None, now: datetime | None = None) -> FailureReport:
    images = screenshots
    metadata = [{name: value for name, value in image.items() if name != "data"} for image in images]
    key = db.get(CardKey, key_id) if key_id is not None else None
    row = FailureReport(project_id=project.id, key_id=key_id, email_id=email_id,
                        kind="card_key" if key_id is not None else "email",
                        project_name=project.name, platform=project.target_platform or "",
                        batch_name=key.batch.name if key and key.batch else None,
                        batch_no=key.batch.batch_no if key and key.batch else None,
                        remark=remark, username=username, created_at=now or datetime.utcnow(),
                        image_count=len(images), image_metadata=metadata,
                        screenshots=json.dumps(images, ensure_ascii=False, separators=(",", ":")))
    db.add(row)
    db.flush()
    return row


def report_metadata(row: FailureReport, base: str) -> dict[str, object]:
    return {"id": row.id, "remark": row.remark, "username": row.username,
            "created_at": row.created_at.isoformat() + "Z", "project_name": row.project_name,
            "batch_name": row.batch_name, "batch_no": row.batch_no,
            "platform": row.platform, "kind": row.kind, "image_count": row.image_count,
            "images": [{**metadata, "url": f"{base}/{row.id}/screenshots/{index}"}
                       for index, metadata in enumerate(row.image_metadata or [])]}


def image_response(db: Session, report_id: int, index: int, *, key_id: int | None = None,
                   email_id: int | None = None) -> Response:
    query = db.query(FailureReport).options(undefer(FailureReport.screenshots)).filter(FailureReport.id == report_id)
    query = query.filter(FailureReport.key_id == key_id) if key_id is not None else query.filter(FailureReport.email_id == email_id)
    row = query.first()
    if not row or index < 0 or index >= row.image_count:
        raise HTTPException(404, "售后截图不存在")
    try:
        images = json.loads(row.screenshots)
        image = images[index]
        content = base64.b64decode(image["data"], validate=True)
        content_type = image["content_type"]
        if content_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError("invalid stored type")
    except (ValueError, KeyError, TypeError, IndexError):
        raise HTTPException(409, "售后截图记录异常，请联系管理员") from None
    return Response(content=content, media_type=content_type,
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"})


def failure_summaries(db: Session, parent: Literal["key", "email"], ids: Iterable[int]) -> dict[int, dict[str, object]]:
    values = list(ids)
    if not values:
        return {}
    column = FailureReport.key_id if parent == "key" else FailureReport.email_id
    counts = db.query(column, func.count(FailureReport.id), func.sum(FailureReport.image_count)).filter(column.in_(values)).group_by(column).all()
    result = {parent_id: {"failure_report_count": count, "screenshot_count": images or 0, "latest_failure_remark": ""}
              for parent_id, count, images in counts}
    rows = db.query(column, FailureReport.remark).filter(column.in_(values)).order_by(FailureReport.created_at.desc(), FailureReport.id.desc()).all()
    seen = set()
    for parent_id, remark in rows:
        if parent_id not in seen:
            result[parent_id]["latest_failure_remark"] = remark
            seen.add(parent_id)
    return result


def empty_summary() -> dict[str, object]:
    return {"failure_report_count": 0, "screenshot_count": 0, "latest_failure_remark": ""}
