"""Real monitor service paths with deterministic network fixtures and isolated stores."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.models.monitor import MonitorAccount, MonitorHistory, MonitorProxy, MonitorSettings, Project
from app.models.video import Video, VideoStats
from app.services import monitor_service


@pytest.fixture(autouse=True)
def clean_monitor_data(db):
    def clean():
        db.rollback()
        for model in (VideoStats, Video, MonitorHistory, MonitorAccount, Project, MonitorSettings):
            db.query(model).delete()
        db.commit()
    clean()
    yield
    clean()


def make_accounts(db, names):
    project = Project(name="resilience")
    db.add(project)
    db.flush()
    accounts = [MonitorAccount(project_id=project.id, username=name, use_proxy=False, sec_uid="fixture-sec") for name in names]
    db.add_all(accounts)
    db.commit()
    return accounts


def test_scheduler_isolates_each_database_session(db, session_factory, monkeypatch):
    make_accounts(db, ["a", "b"])
    db.add(MonitorSettings(max_concurrent_checks=2))
    db.commit()
    seen = []

    async def check(worker_db, account):
        seen.append(worker_db)
        assert worker_db is not db
        await asyncio.sleep(0)
        if account.username == "a":
            worker_db.rollback()
        else:
            account.follower_count = 123
            worker_db.commit()

    monkeypatch.setattr(monitor_service, "check_account", check)
    asyncio.run(monitor_service.run_scheduled_checks(session_factory))
    assert len(seen) == 2 and seen[0] is not seen[1]
    db.expire_all()
    assert db.query(MonitorAccount).filter_by(username="b").one().follower_count == 123


def test_video_write_failure_keeps_profile_and_other_valid_video(db, monkeypatch):
    account = make_accounts(db, ["savepoints"])[0]
    profile = AsyncMock(return_value={"success": True, "data": {"follower_count": 42, "sec_uid": "fixture-sec"}})
    videos = AsyncMock(return_value={"success": True, "data": [
        {"video_id": "valid-one", "play_count": 10},
        {"video_id": "invalid", "published_at": "invalid-number"},
        {"video_id": "valid-two", "play_count": 20},
    ]})
    monkeypatch.setattr(monitor_service.scraper_service, "fetch_user_info", profile)
    monkeypatch.setattr(monitor_service.scraper_service, "fetch_user_videos", videos)
    history = asyncio.run(monitor_service.check_account(db, account))
    db.expire_all()
    assert db.get(MonitorAccount, account.id).follower_count == 42
    assert {row.video_id for row in db.query(Video)} == {"valid-one", "valid-two"}
    assert db.query(MonitorHistory).one().id == history.id
    assert history.error_message.startswith("VIDEO_COLLECTION_FAILED:")


def test_duplicate_monitor_is_busy_and_cancel_releases_ownership(db, monkeypatch):
    account = make_accounts(db, ["ownership"])[0]
    entered = asyncio.Event()
    release = asyncio.Event()

    async def profile(*args, **kwargs):
        entered.set()
        await release.wait()
        return {"success": True, "data": {"follower_count": 5}}

    monkeypatch.setattr(monitor_service.scraper_service, "fetch_user_info", profile)
    account.enable_video_monitoring = False
    db.commit()

    async def exercise():
        first = asyncio.create_task(monitor_service.check_account(db, account))
        await entered.wait()
        with pytest.raises(HTTPException) as exc:
            await monitor_service.check_account(db, account)
        assert exc.value.status_code == 409
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        await monitor_service.check_account(db, account)

    asyncio.run(exercise())
    assert db.query(MonitorHistory).count() == 1


def test_random_proxy_can_failover_but_explicit_binding_stays(db, monkeypatch):
    account = make_accounts(db, ["proxy-budget"])[0]
    proxies = [MonitorProxy(name=name, proxy_type="socks5", host="127.0.0.1", port=port) for name, port in [("first", 1101), ("second", 1102)]]
    db.add_all(proxies)
    account.use_proxy = True
    account.enable_video_monitoring = False
    db.add(MonitorSettings(request_timeout=12))
    db.commit()
    monkeypatch.setattr("random.choice", lambda choices: choices[0])
    profile = AsyncMock(side_effect=[
        {"success": False, "error": "PROXY_ERROR", "error_code": "proxy_error", "retryable": True},
        {"success": True, "data": {"follower_count": 9}},
    ])
    monkeypatch.setattr(monitor_service.scraper_service, "fetch_user_info", profile)
    asyncio.run(monitor_service.check_account(db, account))
    assert [call.kwargs["proxy"].id for call in profile.await_args_list] == [proxies[0].id, proxies[1].id]
    assert all(call.kwargs["timeout"] == 12 for call in profile.await_args_list)
    account.proxy_id = proxies[0].id
    db.commit()
    profile.reset_mock()
    profile.side_effect = None
    profile.return_value = {"success": False, "error_code": "proxy_error", "error": "PROXY_ERROR", "retryable": True}
    asyncio.run(monitor_service.check_account(db, account))
    profile.assert_awaited_once()
    db.query(MonitorProxy).delete()
    db.commit()


def test_identity_edit_during_profile_discards_old_result(db, session_factory, monkeypatch):
    account = make_accounts(db, ["old-identity"])[0]

    async def profile(*args, **kwargs):
        with session_factory() as edit_db:
            current = edit_db.get(MonitorAccount, account.id)
            current.username = "new-identity"
            edit_db.commit()
        return {"success": True, "data": {"nickname": "Old profile", "follower_count": 100}}

    monkeypatch.setattr(monitor_service.scraper_service, "fetch_user_info", profile)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(monitor_service.check_account(db, account))
    assert exc.value.status_code == 409
    db.expire_all()
    assert db.get(MonitorAccount, account.id).username == "new-identity"
    assert db.get(MonitorAccount, account.id).nickname is None
    assert db.query(MonitorHistory).count() == 0
