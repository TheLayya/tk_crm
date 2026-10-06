import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import httpx

from app.models.monitor import MonitorAccount, MonitorHistory, MonitorSettings, Project
from app.models.op_account import OpAccount, OpAuditLog
from app.models.team import Department, Role, RolePermission, UserRole
from app.models.video import OpAccountVideo, Video, VideoStats
from app.services import op_account_service, op_collector_service, video_service
from app.services.account_summary_service import enrich_monitor_summaries
from app.services.scraper_service import scraper_service
from tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def clean_video_accounts(db, clean_tables):
    def clean():
        db.rollback()
        for model in (OpAccountVideo, OpAuditLog, OpAccount, VideoStats, Video,
                      MonitorHistory, MonitorAccount, Project, MonitorSettings):
            db.query(model).delete()
        db.commit()
    clean()
    yield
    clean()


def grant(db, user, scope="self"):
    role = Role(name=f"video-{scope}", data_scope=scope)
    db.add(role)
    db.flush()
    db.add(RolePermission(role_id=role.id, permission="op_account:view"))
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()


def fake_scraper(monkeypatch, count=2, videos=None):
    profile = AsyncMock(return_value={"success": True, "data": {
        "sec_uid": "sec-123", "nickname": "Collected", "video_count": count,
    }})
    fetch = AsyncMock(return_value=videos or {"success": True, "data": [{
        "video_id": "123", "play_count": 100,
        "published_at": int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp()),
    }]})
    monkeypatch.setattr(op_collector_service.scraper_service, "fetch_user_info", profile)
    monkeypatch.setattr(op_collector_service.scraper_service, "fetch_user_videos", fetch)
    return profile, fetch


def test_scheduler_collects_videos_without_monitor_and_updates_in_place(
    db, session_factory, normal_user, monkeypatch
):
    grant(db, normal_user)
    account = OpAccount(platform="tiktok", account="@Standalone", registrant=normal_user.username,
                        collect_status="success", last_collected_at=datetime.utcnow())
    db.add_all([account, MonitorSettings(id=1, default_video_count=7)])
    db.commit()
    profile, fetch = fake_scraper(monkeypatch)
    monkeypatch.setattr(op_collector_service, "select_proxy", lambda session: None)
    asyncio.run(op_account_service.run_scheduled_collections(session_factory))
    db.refresh(account)
    assert account.collect_status == "success"
    assert account.video_collected_at is not None
    assert db.query(MonitorAccount).count() == 0
    profile.assert_awaited_once_with("Standalone", proxy=None)
    fetch.assert_awaited_once_with("sec-123", proxy=None, max_count=7)
    assert db.query(OpAccountVideo).one().play_count == 100
    fetch.return_value["data"][0]["play_count"] = 999
    assert asyncio.run(op_collector_service.collect_account(db, account, None))
    assert db.query(OpAccountVideo).count() == 1
    assert db.query(OpAccountVideo).one().play_count == 999
    enrich_monitor_summaries(db, [account], normal_user)
    assert account.monitor_account_id is None
    assert account.video_source == "op"
    assert account.yesterday_video_count == 1
    assert account.yesterday_video_plays == [999]


def test_zero_video_profile_records_successful_empty_collection(db, normal_user, monkeypatch):
    account = OpAccount(platform="tiktok", account="empty")
    db.add(account)
    db.commit()
    _, fetch = fake_scraper(monkeypatch, count=0, videos={
        "success": False, "data": None, "error": "No videos returned",
    })
    assert asyncio.run(op_collector_service.collect_account(db, account, None))
    fetch.assert_not_awaited()
    assert account.video_collected_at is not None
    enrich_monitor_summaries(db, [account], normal_user)
    assert account.yesterday_video_count == 0
    assert account.yesterday_video_plays == []
    account.video_collected_at = datetime.utcnow() - timedelta(days=2)
    enrich_monitor_summaries(db, [account], normal_user)
    assert account.yesterday_video_count is None


@pytest.mark.parametrize("failure", ["network", "persistence"])
def test_video_failure_retains_profile_and_previous_video_data(db, monkeypatch, failure):
    collected_at = datetime.utcnow() - timedelta(days=2)
    account = OpAccount(platform="tiktok", account="failed", nickname="Old",
                        video_collected_at=collected_at)
    db.add(account)
    db.flush()
    db.add(OpAccountVideo(account_id=account.id, video_id="existing", play_count=7))
    db.commit()
    response = ({"success": False, "data": None, "error": "No videos returned"}
                if failure == "network" else {"success": True, "data": [
                    {"video_id": "new-good", "play_count": 1},
                    {"video_id": "new-invalid", "play_count": None},
                ]})
    fake_scraper(monkeypatch, videos=response)
    if failure == "persistence":
        def fail_persistence(session, account_id, items, model):
            session.add_all([model(account_id=account_id, video_id="duplicate") for _ in range(2)])
            session.flush()
        monkeypatch.setattr(op_collector_service, "save_video_items", fail_persistence)
    assert not asyncio.run(op_collector_service.collect_account(db, account, None))
    db.refresh(account)
    assert account.nickname == "Collected"
    assert account.last_collected_at is not None
    assert account.collect_status == "failed"
    assert account.collect_error.startswith("VIDEO_COLLECTION_FAILED:")
    assert account.video_collected_at == collected_at
    assert [(v.video_id, v.play_count) for v in db.query(OpAccountVideo).all()] == [("existing", 7)]


def test_case_prefix_accounts_do_not_overwrite_each_other(db, monkeypatch):
    first = OpAccount(platform="tiktok", account="@SameName")
    second = OpAccount(platform="tiktok", account="samename")
    db.add_all([first, second])
    db.commit()
    fake_scraper(monkeypatch)
    for account in (first, second):
        assert asyncio.run(op_collector_service.collect_account(db, account, None))
    assert {v.account_id for v in db.query(OpAccountVideo).all()} == {first.id, second.id}
    db.delete(first)
    db.commit()
    assert db.query(OpAccountVideo).one().account_id == second.id


@pytest.mark.parametrize("scope", ["self", "dept", "all"])
def test_operator_video_api_enforces_scope_and_paginates(client, db, normal_user, other_user, scope):
    grant(db, normal_user, scope)
    mine = OpAccount(platform="tiktok", account="mine", operator=normal_user.username)
    foreign = OpAccount(platform="tiktok", account="foreign", registrant=other_user.username)
    db.add_all([mine, foreign])
    db.flush()
    for index in range(3):
        db.add(OpAccountVideo(account_id=mine.id, video_id=str(index)))
    db.add(OpAccountVideo(account_id=foreign.id, video_id="foreign-video"))
    db.commit()
    headers = auth_headers(normal_user)
    response = client.get(f"/api/op-accounts/{mine.id}/videos", params={"skip": 1, "limit": 1}, headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["account_id"] == mine.id
    expected = 200 if scope == "all" else 403
    assert client.get(f"/api/op-accounts/{foreign.id}/videos", headers=headers).status_code == expected
    if scope == "dept":
        department = Department(name="video-team")
        db.add(department)
        db.flush()
        normal_user.department_id = other_user.department_id = department.id
        db.commit()
        assert client.get(f"/api/op-accounts/{foreign.id}/videos", headers=headers).status_code == 200
    assert client.get("/api/op-accounts/999999/videos", headers=headers).status_code == 404
    assert client.get(f"/api/op-accounts/{mine.id}/videos").status_code == 401


def test_own_summary_takes_priority_and_legacy_monitor_fallback_remains_scoped(db, super_admin, normal_user):
    project = Project(name="legacy-monitor", created_by=super_admin.username)
    db.add(project)
    db.flush()
    monitor = MonitorAccount(username="legacy", project_id=project.id)
    account = OpAccount(platform="tiktok", account="@legacy", registrant=normal_user.username)
    db.add_all([monitor, account])
    db.flush()
    db.add(Video(account_id=monitor.id, video_id="legacy-video", published_at=datetime.utcnow() - timedelta(days=1)))
    db.commit()
    enrich_monitor_summaries(db, [account], super_admin)
    assert account.video_source == "monitor"
    assert account.yesterday_video_count == 1
    enrich_monitor_summaries(db, [account], normal_user)
    assert account.video_source == "op"
    assert account.yesterday_video_count is None
    account.video_collected_at = datetime.utcnow()
    enrich_monitor_summaries(db, [account], super_admin)
    assert account.video_source == "op"
    assert account.yesterday_video_count == 0
    db.add(OpAccountVideo(account_id=account.id, video_id="undated"))
    db.commit()
    enrich_monitor_summaries(db, [account], super_admin)
    assert account.yesterday_video_count is None


def test_successful_empty_fetch_refreshes_old_dated_rows_but_keeps_unknown_dates(db, normal_user, monkeypatch):
    account = OpAccount(platform="tiktok", account="old-videos")
    db.add(account)
    db.flush()
    db.add(OpAccountVideo(account_id=account.id, video_id="old", published_at=datetime.utcnow() - timedelta(days=10),
                          updated_at=datetime.utcnow() - timedelta(days=3)))
    db.commit()
    fake_scraper(monkeypatch, videos={"success": True, "data": []})
    assert asyncio.run(op_collector_service.collect_account(db, account, None))
    enrich_monitor_summaries(db, [account], normal_user)
    assert account.yesterday_video_count == 0
    assert account.yesterday_video_plays == []


@pytest.mark.parametrize("payload,success", [
    ({"statusCode": 0, "itemList": []}, True),
    ({"statusCode": 10204, "itemList": []}, False),
    ({"itemList": []}, False),
])
def test_scraper_distinguishes_normal_empty_list_from_restriction(monkeypatch, payload, success):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    def client(**kwargs):
        kwargs.pop("proxies", None)
        return real_client(transport=transport, **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    result = asyncio.run(scraper_service.fetch_user_videos("empty-sec"))
    assert result["success"] is success
    assert result["data"] == ([] if success else None)


def test_existing_monitor_saver_keeps_stats_snapshots(db):
    project = Project(name="monitor-save")
    db.add(project)
    db.flush()
    monitor = MonitorAccount(username="save", project_id=project.id)
    db.add(monitor)
    db.flush()
    assert video_service.save_video_items(db, monitor.id, [{"video_id": "snapshot", "play_count": 9}]) == 1
    db.commit()
    assert db.query(Video).one().play_count == 9
    assert db.query(VideoStats).one().play_count == 9
