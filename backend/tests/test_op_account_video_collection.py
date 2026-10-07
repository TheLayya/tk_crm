import asyncio
import io
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import httpx
import openpyxl

from app.models.monitor import MonitorAccount, MonitorHistory, MonitorSettings, Project
from app.models.op_account import OpAccount, OpAuditLog, OpCollectTask
from app.models.team import Department, Role, RolePermission, UserRole
from app.models.video import OpAccountVideo, Video, VideoStats
from app.services import op_account_service, op_collector_service, video_service
from app.services.account_summary_service import enrich_monitor_summaries
from app.services.scraper_service import scraper_service
from app.schemas.op_account import OpAccountUpdate
from tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def clean_video_accounts(db, clean_tables):
    def clean():
        db.rollback()
        for model in (OpAccountVideo, OpAuditLog, OpCollectTask, OpAccount, VideoStats, Video,
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
    profile.assert_awaited_once_with("Standalone", proxy=None, timeout=30)
    fetch.assert_awaited_once_with("sec-123", proxy=None, max_count=7, timeout=30)
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
        "success": True, "data": [],
    })
    assert asyncio.run(op_collector_service.collect_account(db, account, None))
    fetch.assert_awaited_once_with("sec-123", proxy=None, max_count=20, timeout=30)
    assert account.video_collected_at is not None
    enrich_monitor_summaries(db, [account], normal_user)
    assert account.yesterday_video_count == 0
    assert account.yesterday_video_plays == []
    account.video_collected_at = datetime.utcnow() - timedelta(days=2)
    enrich_monitor_summaries(db, [account], normal_user)
    assert account.yesterday_video_count is None


def test_zero_profile_count_still_collects_videos_and_stays_pending_until_complete(
    db, session_factory, monkeypatch
):
    account = OpAccount(platform="tiktok", account="profile-zero", collect_status="success")
    db.add(account)
    db.commit()
    profile, fetch = fake_scraper(monkeypatch, count=0)
    profile_result = profile.return_value
    video_result = fetch.return_value

    async def check_profile(*args, **kwargs):
        with session_factory() as check_db:
            assert check_db.get(OpAccount, account.id).collect_status == "pending"
        return profile_result

    async def check_videos(*args, **kwargs):
        with session_factory() as check_db:
            stored = check_db.get(OpAccount, account.id)
            assert stored.collect_status == "pending"
            assert stored.last_collected_at is not None
        return video_result

    profile.side_effect = check_profile
    fetch.side_effect = check_videos
    assert asyncio.run(op_collector_service.collect_account(db, account, None))
    fetch.assert_awaited_once_with("sec-123", proxy=None, max_count=20, timeout=30)
    assert db.query(OpAccountVideo).one().account_id == account.id
    assert account.collect_status == "success"


@pytest.mark.parametrize("entry", ["create", "csv", "xlsx"])
def test_new_account_and_manual_collection_always_collect_profile_and_videos(
    client, db, session_factory, super_admin, monkeypatch, entry
):
    monkeypatch.setattr(op_account_service, "SessionLocal", session_factory)
    monkeypatch.setattr(op_collector_service, "select_proxy", lambda session: None)
    profile, fetch = fake_scraper(monkeypatch)
    headers = auth_headers(super_admin)
    name = f"new-{entry}"
    if entry == "create":
        response = client.post("/api/op-accounts", headers=headers, json={
            "platform": "tiktok", "account": name,
        })
        assert response.status_code == 201, response.text
    else:
        content = f"platform,account\ntiktok,{name}\n".encode()
        mime = "text/csv"
        if entry == "xlsx":
            workbook = openpyxl.Workbook()
            workbook.active.append(["platform", "account"])
            workbook.active.append(["tiktok", name])
            output = io.BytesIO()
            workbook.save(output)
            content = output.getvalue()
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        response = client.post("/api/op-accounts/import", headers=headers,
                               files={"file": (f"accounts.{entry}", content, mime)})
        assert response.status_code == 200, response.text
        task = db.get(OpCollectTask, response.json()["task_id"])
        assert (task.completed, task.success, task.failed) == (1, 1, 0)
    account = db.query(OpAccount).filter_by(account=name).one()
    assert account.collect_status == "success"
    assert account.video_collected_at is not None
    assert db.query(OpAccountVideo).one().play_count == 100
    profile.assert_awaited_once()
    fetch.assert_awaited_once()

    # A recent successful automatic task must not suppress a manual collection.
    profile.return_value["data"]["nickname"] = "Manual refresh"
    fetch.return_value["data"][0]["play_count"] = 321
    response = client.post("/api/op-accounts/collect", headers=headers,
                           json={"account_ids": [account.id]})
    assert response.status_code == 200, response.text
    task = db.get(OpCollectTask, response.json()["task_id"])
    assert (task.completed, task.success, task.failed) == (1, 1, 0)
    db.expire_all()
    assert account.nickname == "Manual refresh"
    assert db.query(OpAccountVideo).one().play_count == 321
    assert profile.await_count == fetch.await_count == 2


@pytest.mark.parametrize("failure", ["network", "persistence", "empty"])
def test_video_failure_retains_profile_and_previous_video_data(db, monkeypatch, failure):
    collected_at = datetime.utcnow() - timedelta(days=2)
    account = OpAccount(platform="tiktok", account="failed", nickname="Old",
                        video_collected_at=collected_at)
    db.add(account)
    db.flush()
    db.add(OpAccountVideo(account_id=account.id, video_id="existing", play_count=7))
    db.commit()
    response = ({"success": False, "data": None, "error": "No videos returned"}
                if failure == "network" else {"success": True, "data": []}
                if failure == "empty" else {"success": True, "data": [
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


@pytest.mark.parametrize("error", ["ACCOUNT_NOT_FOUND: renamed", "VERIFICATION_REQUIRED: blocked", "Timeout"])
@pytest.mark.parametrize("video_success", [True, False])
def test_profile_failure_still_attempts_cached_video_identity_and_preserves_reason(
    db, monkeypatch, error, video_success
):
    old_profile_time = datetime.utcnow() - timedelta(days=2)
    account = OpAccount(platform="tiktok", account="cached", platform_sec_uid="valid-cached-sec",
                        nickname="Old", last_collected_at=old_profile_time, video_count=1)
    db.add(account)
    db.flush()
    db.add(OpAccountVideo(account_id=account.id, video_id="123", play_count=7))
    db.commit()
    profile, fetch = fake_scraper(monkeypatch)
    profile.return_value = {"success": False, "data": None, "error": error}
    if not video_success:
        fetch.return_value = {"success": False, "data": None, "error": "Video timeout"}
    assert not asyncio.run(op_collector_service.collect_account(db, account, None))
    fetch.assert_awaited_once_with("valid-cached-sec", proxy=None, max_count=20, timeout=30)
    assert account.collect_status == "failed"
    assert account.collect_error.startswith(error)
    assert account.nickname == "Old"
    assert account.last_collected_at == old_profile_time
    assert db.query(OpAccountVideo).one().play_count == (100 if video_success else 7)
    assert (account.video_collected_at is not None) is video_success
    assert ("VIDEO_COLLECTION_FAILED:" in account.collect_error) is not video_success


def test_empty_profile_exception_cannot_be_reported_as_success(db, monkeypatch):
    account = OpAccount(platform="tiktok", account="empty-exception", platform_sec_uid="cached-sec")
    db.add(account)
    db.commit()
    profile, fetch = fake_scraper(monkeypatch)
    profile.side_effect = RuntimeError()
    assert not asyncio.run(op_collector_service.collect_account(db, account, None))
    fetch.assert_awaited_once()
    assert account.collect_status == "failed"
    assert account.collect_error == "RuntimeError"


@pytest.mark.parametrize("update", [OpAccountUpdate(account="renamed"), OpAccountUpdate(platform="youtube")])
def test_identity_edit_invalidates_cached_uid_before_profile_failure(db, monkeypatch, update):
    account = OpAccount(platform="tiktok", account="old-identity", platform_user_id="old-id",
                        platform_sec_uid="old-sec", collect_status="success",
                        last_collected_at=datetime.utcnow(), video_collected_at=datetime.utcnow())
    db.add(account)
    db.flush()
    db.add(OpAccountVideo(account_id=account.id, video_id="history", play_count=7))
    db.commit()
    account = op_account_service.update_op_account(db, account.id, update)
    assert account.platform_user_id is account.platform_sec_uid is None
    assert account.last_collected_at is account.video_collected_at is None
    assert account.collect_status == "pending"
    assert db.query(OpAccountVideo).one().video_id == "history"
    profile, fetch = fake_scraper(monkeypatch)
    profile.return_value = {"success": False, "data": None, "error": "Timeout"}
    assert not asyncio.run(op_collector_service.collect_account(db, account, None))
    fetch.assert_not_awaited()


def test_nonidentity_edit_preserves_cached_uid(db):
    account = OpAccount(platform="tiktok", account="unchanged", platform_sec_uid="valid-sec")
    db.add(account)
    db.commit()
    op_account_service.update_op_account(db, account.id, OpAccountUpdate(account="unchanged", remark="note"))
    assert account.platform_sec_uid == "valid-sec"


@pytest.mark.parametrize("stage", ["profile", "videos", "video-error"])
def test_identity_edit_during_request_abandons_old_collection(
    db, session_factory, monkeypatch, stage
):
    account = OpAccount(platform="tiktok", account="old-request", platform_sec_uid="old-sec")
    db.add(account)
    db.commit()
    profile, fetch = fake_scraper(monkeypatch)
    result = profile.return_value if stage == "profile" else fetch.return_value

    async def rename_during_request(*args, **kwargs):
        with session_factory() as edit_db:
            op_account_service.update_op_account(edit_db, account.id, OpAccountUpdate(account="renamed"))
        if stage == "video-error":
            raise RuntimeError("Old request failed")
        return result

    (profile if stage == "profile" else fetch).side_effect = rename_during_request
    assert not asyncio.run(op_collector_service.collect_account(db, account, None))
    db.refresh(account)
    assert account.account == "renamed"
    assert account.platform_sec_uid is None
    assert account.collect_status == "pending"
    assert account.collect_error is None
    assert account.last_collected_at is None
    assert account.video_collected_at is None
    assert db.query(OpAccountVideo).count() == 0


@pytest.mark.parametrize("initial,last_collected,expected_previous", [
    (None, None, None), (100, None, None),
    (100, datetime.utcnow() - timedelta(hours=1), 100),
])
def test_profile_collection_tracks_only_valid_follower_baselines(
    db, monkeypatch, initial, last_collected, expected_previous
):
    account = OpAccount(platform="tiktok", account="follower-baseline", follower_count=initial,
                        last_collected_at=last_collected)
    db.add(account)
    db.commit()
    profile, fetch = fake_scraper(monkeypatch)
    profile.return_value["data"]["follower_count"] = 120
    assert asyncio.run(op_collector_service.collect_account(db, account, None))
    assert account.follower_count == 120
    assert account.previous_follower_count == expected_previous

    profile.return_value["data"]["follower_count"] = None
    assert asyncio.run(op_collector_service.collect_account(db, account, None))
    assert account.follower_count == 120
    assert account.previous_follower_count == expected_previous
    del profile.return_value["data"]["follower_count"]
    assert asyncio.run(op_collector_service.collect_account(db, account, None))
    assert account.follower_count == 120
    assert account.previous_follower_count == expected_previous

    profile.return_value["data"]["follower_count"] = 90
    fetch.return_value = {"success": False, "data": None, "error": "Video timeout"}
    assert not asyncio.run(op_collector_service.collect_account(db, account, None))
    assert account.follower_count == 90
    assert account.previous_follower_count == 120
    op_account_service.update_op_account(db, account.id, OpAccountUpdate(account="new-name"))
    assert account.follower_count is account.previous_follower_count is None


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
    fake_scraper(monkeypatch, count=0, videos={"success": True, "data": []})
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
