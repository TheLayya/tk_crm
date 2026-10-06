import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.monitor import MonitorSettings
from app.models.op_account import OpAccount
from app.services import op_account_service, op_collector_service


def test_scheduled_collection_filters_due_accounts_and_uses_settings(monkeypatch):
    engine = create_engine("sqlite://")
    MonitorSettings.__table__.create(engine)
    OpAccount.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    now = datetime.utcnow()
    with factory() as db:
        db.add(MonitorSettings(id=1, default_interval=18000))
        for name, platform, status, collected, collect_status, updated in [
            ("new", "tiktok", "正常", None, "pending", now),
            ("due", "tiktok", "自用", now - timedelta(hours=6), "success", now),
            ("fresh", "tiktok", "正常", now - timedelta(hours=2), "success", now),
            ("sold", "tiktok", "已售", None, "pending", now),
            ("banned", "tiktok", "封禁", None, "pending", now),
            ("other", "youtube", "正常", None, "pending", now),
            ("failed", "tiktok", "正常", None, "failed", now),
            ("retry", "tiktok", "正常", None, "failed", now - timedelta(hours=6)),
        ]:
            db.add(OpAccount(account=name, platform=platform, status=status,
                             last_collected_at=collected, video_collected_at=now if name == "fresh" else None,
                             collect_status=collect_status, updated_at=updated))
        db.commit()
    collected_names = []

    async def collect(db, account, proxy):
        collected_names.append(account.account)
        account.last_collected_at = now
        account.video_collected_at = now
        account.collect_status = "success"
        db.commit()
        return True

    monkeypatch.setattr(op_collector_service, "collect_account", collect)
    monkeypatch.setattr(op_collector_service, "select_proxy", lambda db: None)
    asyncio.run(op_account_service.run_scheduled_collections(factory))
    assert set(collected_names) == {"new", "due", "retry"}
    asyncio.run(op_account_service.run_scheduled_collections(factory))
    assert len(collected_names) == 3
    engine.dispose()


def test_registers_non_overlapping_scheduler_job():
    scheduler = Mock()
    op_account_service.register_scheduler_job(scheduler, Mock())
    options = scheduler.add_job.call_args.kwargs
    assert options["id"] == "scheduled_op_account_collections"
    assert options["minutes"] == 1
    assert options["max_instances"] == 1
    assert options["replace_existing"] is True
