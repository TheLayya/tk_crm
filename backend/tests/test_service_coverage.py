"""Behavioral checks for monitor collection and account transfer workflows."""
import asyncio
import csv
import io
import threading
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import openpyxl
import pytest
from fastapi import HTTPException

from app.models.monitor import (
    MonitorAccount, MonitorHistory, MonitorProxy, MonitorSettings, Project, ProjectMember,
)
from app.models.video import Video, VideoStats
from app.schemas.account import AccountCreate, AccountUpdate, BatchActionRequest
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.schemas.settings import SettingsUpdate
from app.services import import_export_service, monitor_service, project_service, video_service


@pytest.fixture(autouse=True)
def isolated_monitor_tables(db, clean_tables, monkeypatch):
    """The shared fixture omits these tables; never start real collection threads."""
    def clean():
        db.rollback()
        for model in (VideoStats, Video, MonitorHistory, MonitorAccount, ProjectMember,
                      Project, MonitorProxy, MonitorSettings):
            db.query(model).delete()
        db.commit()

    clean()
    original_start = threading.Thread.start

    def start(thread):
        if getattr(thread._target, "__name__", "") != "_trigger_first_check":
            original_start(thread)

    monkeypatch.setattr(threading.Thread, "start", start)
    yield
    clean()


def account_row(db, name="collector", **values):
    project = Project(name=f"project-{name}", created_by="alice")
    db.add(project)
    db.flush()
    account = MonitorAccount(project_id=project.id, username=name, **values)
    db.add(account)
    db.commit()
    return account


def test_first_check_runs_with_its_own_isolated_session(db, session_factory, monkeypatch):
    project = Project(name="first-check")
    db.add(project)
    db.commit()
    factory = Mock(side_effect=session_factory)
    monkeypatch.setattr("app.core.database.SessionLocal", factory)
    original_start = threading.Thread.start

    def start(thread):
        if getattr(thread._target, "__name__", "") == "_trigger_first_check":
            thread.run()
        else:
            original_start(thread)

    monkeypatch.setattr(threading.Thread, "start", start)
    profile = AsyncMock(return_value={"success": True, "data": {
        "nickname": "First result", "sec_uid": "first-sec", "follower_count": 12,
    }})
    videos = AsyncMock(return_value={"success": True, "data": [
        {"video_id": "first-video", "play_count": 31},
    ]})
    monkeypatch.setattr(monitor_service.scraper_service, "fetch_user_info", profile)
    monkeypatch.setattr(monitor_service.scraper_service, "fetch_user_videos", videos)
    account = monitor_service.create_account(db, AccountCreate(
        project_id=project.id, username="first", use_proxy=False,
    ))
    db.refresh(account)
    assert factory.call_count == 1
    assert account.nickname == "First result"
    assert account.monitor_interval == 3600
    assert account.follower_count == 12
    assert db.query(MonitorHistory).one().check_status == "success"
    assert db.query(Video).one().play_count == 31
    videos.assert_awaited_once_with("first-sec", proxy=None, max_count=20, timeout=30)


@pytest.mark.parametrize("proxy_mode", ["disabled", "assigned", "random", "empty"])
def test_collection_updates_profile_and_existing_videos(db, monkeypatch, proxy_mode):
    account = account_row(db, use_proxy=proxy_mode != "disabled", sec_uid="sec-old")
    proxy = None
    if proxy_mode in {"assigned", "random"}:
        proxy = MonitorProxy(name="test", proxy_type="socks5", host="127.0.0.1", port=1080)
        db.add(proxy)
        db.commit()
        if proxy_mode == "assigned":
            account.proxy_id = proxy.id
            db.commit()
    profile = AsyncMock(return_value={"success": True, "data": {
        "nickname": "Collected", "tiktok_id": "user-id", "sec_uid": "sec-new",
        "avatar_url": "https://test/avatar", "bio": "Profile", "follower_count": 23,
        "following_count": 4, "like_count": 54, "video_count": 2, "region": "US",
        "account_created_at": datetime(2020, 1, 2),
    }})
    fetch = AsyncMock(return_value={"success": True, "data": [{
        "video_id": "existing", "title": "Updated", "cover_url": "https://test/cover",
        "play_count": 44, "like_count": 8, "comment_count": 3, "share_count": 2,
        "published_at": 1700000000,
    }, {"video_id": "new", "play_count": 12}]})
    db.add(Video(account_id=account.id, video_id="existing", title="Old", play_count=1))
    db.add(MonitorSettings(default_video_count=7))
    db.commit()
    monkeypatch.setattr(monitor_service.scraper_service, "fetch_user_info", profile)
    monkeypatch.setattr(monitor_service.scraper_service, "fetch_user_videos", fetch)
    history = asyncio.run(monitor_service.check_account(db, account))
    profile.assert_awaited_once_with("collector", proxy=proxy, timeout=30)
    fetch.assert_awaited_once_with("sec-new", proxy=proxy, max_count=7, timeout=30)
    assert (account.nickname, account.tiktok_id, account.region) == ("Collected", "user-id", "US")
    assert (history.follower_count, history.following_count, history.like_count, history.video_count) == (23, 4, 54, 2)
    assert history.check_status == "success" and history.error_message is None
    assert account.last_checked_at == history.checked_at
    assert account.account_created_at == datetime(2020, 1, 2)
    saved = {video.video_id: video for video in db.query(Video).all()}
    assert set(saved) == {"existing", "new"}
    assert (saved["existing"].title, saved["existing"].play_count) == ("Updated", 44)
    assert saved["existing"].published_at == datetime.utcfromtimestamp(1700000000)
    assert saved["new"].published_at is None


@pytest.mark.parametrize("video_result", [
    {"success": False, "error": "temporarily unavailable"}, RuntimeError("video outage"),
])
def test_video_outage_does_not_discard_successful_profile(db, monkeypatch, video_result):
    account = account_row(db, use_proxy=False, sec_uid="sec", follower_count=9)
    profile = AsyncMock(return_value={"success": True, "data": {"follower_count": 20}})
    fetch = AsyncMock()
    if isinstance(video_result, Exception):
        fetch.side_effect = video_result
    else:
        fetch.return_value = video_result
    monkeypatch.setattr(monitor_service.scraper_service, "fetch_user_info", profile)
    monkeypatch.setattr(monitor_service.scraper_service, "fetch_user_videos", fetch)
    history = asyncio.run(monitor_service.check_account(db, account))
    assert history.check_status == "success"
    assert history.follower_count == account.follower_count == 20
    assert db.query(Video).count() == 0
    fetch.assert_awaited_once()


def test_failed_profile_preserves_stats_and_records_bounded_error(db, monkeypatch):
    account = account_row(db, use_proxy=False, follower_count=15, like_count=40)
    profile = AsyncMock(return_value={"success": False, "error": "failure-" + "x" * 700})
    fetch = AsyncMock()
    monkeypatch.setattr(monitor_service.scraper_service, "fetch_user_info", profile)
    monkeypatch.setattr(monitor_service.scraper_service, "fetch_user_videos", fetch)
    history = asyncio.run(monitor_service.trigger_check(db, account.id))
    assert history.check_status == "failed"
    assert history.error_message.startswith("failure-") and len(history.error_message) == 500
    assert (account.follower_count, account.like_count) == (15, 40)
    assert history.follower_count == 15 and history.like_count == 40
    assert account.last_checked_at is not None
    fetch.assert_not_awaited()
    assert asyncio.run(monitor_service.trigger_check(db, 999999)) is None


def test_video_collection_snapshots_each_refresh_and_handles_absent_id(db, monkeypatch):
    account = account_row(db, use_proxy=False)
    fetch = AsyncMock(return_value={"success": True, "data": [
        {"video_id": "snapshot", "play_count": 5, "published_at": "invalid"},
        {"title": "No video id"},
    ]})
    monkeypatch.setattr(video_service.scraper_service, "fetch_user_videos", fetch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(video_service.fetch_and_save_videos(db, account))
    assert exc.value.status_code == 422
    fetch.assert_not_awaited()
    account.sec_uid = "sec"
    db.commit()
    assert asyncio.run(video_service.fetch_and_save_videos(db, account)) == 1
    saved = db.query(Video).one()
    assert saved.published_at is None
    fetch.return_value["data"][0]["play_count"] = 50
    assert asyncio.run(video_service.fetch_and_save_videos(db, account)) == 0
    assert db.query(Video).one().play_count == 50
    assert [row.play_count for row in video_service.get_video_stats(db, saved.id)] == [5, 50]
    fetch.return_value = {"success": False, "error": "offline"}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(video_service.fetch_and_save_videos(db, account))
    assert exc.value.status_code == 502
    assert db.query(VideoStats).count() == 2


def test_scheduler_only_checks_due_active_accounts_and_limits_concurrency(db, session_factory, monkeypatch):
    project = Project(name="scheduled")
    db.add(project)
    db.flush()
    now = datetime.utcnow()
    accounts = [MonitorAccount(project_id=project.id, username=name, **values) for name, values in [
        ("new", {}), ("due", {"last_checked_at": now - timedelta(hours=2)}),
        ("broken", {}), ("recent", {"last_checked_at": now}),
        ("inactive", {"is_active": False}),
    ]]
    db.add_all(accounts + [MonitorSettings(max_concurrent_checks=1)])
    db.commit()
    visited, succeeded, in_flight, peak = [], [], 0, 0

    async def check(session, account):
        nonlocal in_flight, peak
        visited.append(account.username)
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1
        if account.username == "broken":
            raise RuntimeError("one account failed")
        succeeded.append(account.username)

    monkeypatch.setattr(monitor_service, "check_account", check)
    asyncio.run(monitor_service.run_scheduled_checks(session_factory))
    assert set(visited) == {"new", "due", "broken"}
    assert set(succeeded) == {"new", "due"}
    assert peak == 1
    for account in accounts:
        account.is_active = False
    db.commit()
    visited.clear()
    asyncio.run(monitor_service.run_scheduled_checks(session_factory))
    assert visited == []


def test_registered_scheduler_job_uses_supplied_database_factory(monkeypatch):
    scheduler = Mock()
    factory = Mock()
    run = AsyncMock()
    monkeypatch.setattr(monitor_service, "run_scheduled_checks", run)
    monitor_service.register_scheduler_jobs(scheduler, factory)
    job = scheduler.add_job.call_args.args[0]
    assert scheduler.add_job.call_args.kwargs == {
        "trigger": "interval", "minutes": 1, "id": "scheduled_monitor_checks",
        "replace_existing": True, "max_instances": 1,
    }
    asyncio.run(job())
    run.assert_awaited_once_with(factory)


def test_project_membership_scope_and_transfer_delete_guard(db):
    owned = project_service.create_project(db, ProjectCreate(name="owned"), "alice")
    invited = project_service.create_project(db, ProjectCreate(name="invited"), "bob")
    foreign = project_service.create_project(db, ProjectCreate(name="foreign"), "carol")
    project_service.set_project_members(db, invited.id, ["alice", "alice", "bob"])
    assert set(project_service.get_project_members(db, invited.id)) == {"alice", "bob"}
    assert set(project_service.get_visible_project_ids(db, "alice", "self")) == {owned.id, invited.id}
    assert set(project_service.get_visible_project_ids(db, "alice", "dept", ["alice", "carol"])) == {owned.id, foreign.id}
    assert project_service.get_visible_project_ids(db, "alice", "dept") == [owned.id]
    assert project_service.get_visible_project_ids(db, "alice", "all") is None
    account = monitor_service.create_account(db, AccountCreate(project_id=owned.id, username="member"))
    assert project_service.get_project(db, owned.id).account_count == 1
    assert {row.id for row in project_service.get_projects(db, allowed_ids=[owned.id])} == {owned.id}
    with pytest.raises(ValueError, match="already exists"):
        project_service.create_project(db, ProjectCreate(name="owned"))
    with pytest.raises(ValueError, match="already exists"):
        project_service.update_project(db, owned.id, ProjectUpdate(name="foreign"))
    updated = project_service.update_project(db, owned.id, ProjectUpdate(description="changed"))
    assert updated.description == "changed" and updated.account_count == 1
    with pytest.raises(ValueError, match="Cannot delete"):
        project_service.delete_project(db, owned.id)
    assert monitor_service.update_account(db, account.id, AccountUpdate(nickname="updated")).nickname == "updated"
    assert monitor_service.update_account(db, 99999, AccountUpdate(nickname="missing")) is None
    assert project_service.update_project(db, 99999, ProjectUpdate(name="missing")) is None
    assert monitor_service.delete_account(db, account.id)
    project_service.delete_project(db, owned.id)
    assert project_service.get_project(db, owned.id) is None
    with pytest.raises(LookupError, match="not found"):
        project_service.delete_project(db, owned.id)


def test_import_text_duplicate_results_and_batch_transfer(db):
    source = Project(name="import-source")
    target = Project(name="import-target")
    db.add_all([source, target])
    db.commit()
    result = asyncio.run(import_export_service.import_accounts_from_text(
        db, source.id, " @first\n\nsecond\nfirst\n", 600,
    ))
    assert (result.total, result.success, result.duplicates, result.failed) == (3, 2, 1, 0)
    assert [row.status for row in result.results] == ["success", "success", "duplicate"]
    accounts = db.query(MonitorAccount).all()
    ids = [row.id for row in accounts]
    assert {row.monitor_interval for row in accounts} == {600}
    for action, expected in [("disable", False), ("enable", True)]:
        result = asyncio.run(import_export_service.batch_action(db, BatchActionRequest(account_ids=ids, action=action)))
        assert result == {"affected": 2}
        assert all(row.is_active == expected for row in accounts)
    moved = asyncio.run(import_export_service.batch_action(db, BatchActionRequest(
        account_ids=ids, action="move", target_project_id=target.id,
    )))
    assert moved == {"affected": 2} and {row.project_id for row in accounts} == {target.id}
    assert asyncio.run(import_export_service.batch_action(db, BatchActionRequest(account_ids=[], action="enable"))) == {"affected": 0}
    assert asyncio.run(import_export_service.batch_action(db, BatchActionRequest(account_ids=[99999], action="delete"))) == {"affected": 0}
    with pytest.raises(ValueError, match="target_project_id"):
        asyncio.run(import_export_service.batch_action(db, BatchActionRequest(account_ids=ids, action="move")))
    with pytest.raises(LookupError, match="not found"):
        asyncio.run(import_export_service.batch_action(db, BatchActionRequest(account_ids=ids, action="move", target_project_id=99999)))
    with pytest.raises(ValueError, match="Unknown action"):
        asyncio.run(import_export_service.batch_action(db, BatchActionRequest(account_ids=ids, action="unexpected")))
    assert asyncio.run(import_export_service.batch_action(db, BatchActionRequest(account_ids=ids, action="delete"))) == {"affected": 2}
    assert db.query(MonitorAccount).count() == 0


def test_import_failure_results_preserve_reason_and_other_rows(db, monkeypatch):
    original = import_export_service.create_account
    project = Project(name="failed-import")
    db.add(project)
    db.commit()

    def create(session, data):
        if data.username == "invalid":
            raise ValueError("invalid account")
        if data.username == "outage":
            raise RuntimeError("x" * 300)
        return original(session, data)

    monkeypatch.setattr(import_export_service, "create_account", create)
    result = asyncio.run(import_export_service.import_accounts_from_text(db, project.id, "valid\ninvalid\noutage"))
    assert (result.success, result.failed) == (1, 2)
    assert result.results[1].reason == "invalid account"
    assert len(result.results[2].reason) == 200
    assert db.query(MonitorAccount).one().username == "valid"


def test_csv_and_excel_export_include_24h_deltas_and_no_history_marker(db):
    account = account_row(db, "export", nickname="昵称", sec_uid="s" * 60,
                          bio="b" * 110, follower_count=20, following_count=3,
                          like_count=30, video_count=2, monitor_interval=600,
                          account_created_at=datetime(2020, 1, 2))
    empty = MonitorAccount(project_id=account.project_id, username="no-history", use_proxy=False,
                           enable_video_monitoring=False)
    db.add_all([empty, MonitorHistory(account_id=account.id, follower_count=10, following_count=5,
                                    like_count=30, video_count=1, check_status="success",
                                    checked_at=datetime.utcnow() - timedelta(hours=25)),
                MonitorHistory(account_id=account.id, follower_count=1000, check_status="failed",
                               checked_at=datetime.utcnow() - timedelta(hours=24, minutes=10))])
    db.commit()
    rows = list(csv.DictReader(io.StringIO(import_export_service.export_accounts_csv(db, account.project_id))))
    assert [row["username"] for row in rows] == ["export", "no-history"]
    assert (rows[0]["follower_count_24h"], rows[0]["follower_change_24h"],
            rows[0]["following_change_24h"], rows[0]["like_change_24h"]) == ("10", "+10", "-2", "0")
    assert rows[0]["account_created_at"] == "2020-01-02 00:00:00"
    assert rows[1]["nickname"] == "" and rows[1]["follower_change_24h"] == "-"
    workbook = openpyxl.load_workbook(io.BytesIO(import_export_service.export_accounts_excel(db)), data_only=True)
    try:
        sheet = workbook.active
        headers = [cell.value for cell in sheet[1]]
        first = dict(zip(headers, [cell.value for cell in sheet[2]]))
        second = dict(zip(headers, [cell.value for cell in sheet[3]]))
        assert first["用户名"] == "export" and first["24h粉丝变化"] == "+10"
        assert first["24h关注变化"] == "-2" and first["24h点赞变化"] == "0"
        assert first["监控间隔(分钟)"] == 10
        assert first["Sec UID"] == "s" * 50 + "..."
        assert first["简介"] == "b" * 100 + "..."
        assert second["24h前粉丝数"] == "-" and second["视频监控"] == "否"
        assert sheet[1][0].font.bold is True
    finally:
        workbook.close()


def test_file_parsers_reject_bad_headers_and_skip_blank_values():
    assert import_export_service._extract_usernames_from_csv(
        b" UserName ,other\n@alice,1\nusername,2\n,3\nbob,4\n",
    ) == ["alice", "bob"]
    for payload, reason in [(b"", "empty"), (b"account\nalice\n", "username")]:
        with pytest.raises(ValueError, match=reason):
            import_export_service._extract_usernames_from_csv(payload)
    for rows, expected in [([['USERNAME'], ['@alice'], [None], ['None'], ['bob']], ['alice', 'bob']),
                           ([], "empty"), ([['account'], ['alice']], "username")]:
        workbook = openpyxl.Workbook()
        for row in rows:
            workbook.active.append(row)
        output = io.BytesIO()
        workbook.save(output)
        workbook.close()
        if isinstance(expected, list):
            assert import_export_service._extract_usernames_from_excel(output.getvalue()) == expected
        else:
            with pytest.raises(ValueError, match=expected):
                import_export_service._extract_usernames_from_excel(output.getvalue())


def test_settings_update_preserves_unspecified_values(db):
    defaults = monitor_service.get_settings(db)
    assert (defaults.default_interval, defaults.max_concurrent_checks) == (3600, 5)
    updated = monitor_service.update_settings(db, SettingsUpdate(default_interval=600, site_name="Team"))
    assert updated.id == defaults.id
    assert (updated.default_interval, updated.site_name, updated.max_concurrent_checks) == (600, "Team", 5)
