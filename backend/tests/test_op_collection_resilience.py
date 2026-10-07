import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.monitor import MonitorProxy, MonitorSettings
from app.models.op_account import OpAccount, OpAuditLog, OpCollectTask
from app.models.video import OpAccountVideo
from app.schemas.op_account import OpAccountUpdate
from app.services import op_account_service, op_collector_service


@pytest.fixture(autouse=True)
def clean_accounts(db):
    def clean():
        db.rollback()
        for model in (OpAccountVideo, OpAuditLog, OpCollectTask, OpAccount, MonitorProxy, MonitorSettings):
            db.query(model).delete()
        db.commit()
    clean()
    yield
    clean()


def account_with_scraper(db, monkeypatch, **values):
    account = OpAccount(platform="tiktok", account="resilient", **values)
    db.add(account)
    db.commit()
    profile = AsyncMock(return_value={"success": True, "data": {"sec_uid": "sec", "video_count": 0}})
    videos = AsyncMock(return_value={"success": True, "data": []})
    monkeypatch.setattr(op_collector_service.scraper_service, "fetch_user_info", profile)
    monkeypatch.setattr(op_collector_service.scraper_service, "fetch_user_videos", videos)
    return account, profile, videos


@pytest.fixture
def thread_db(tmp_path):
    # Separate connections exercise the real threaded runner; StaticPool shares a DBAPI connection.
    engine = create_engine("sqlite:///" + (tmp_path / "threads.db").as_posix())
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        yield db, factory
    engine.dispose()


def test_cross_thread_manual_and_scheduler_share_one_result_and_complete_tasks(thread_db, monkeypatch):
    db, session_factory = thread_db
    account, profile, videos = account_with_scraper(db, monkeypatch)
    entered, release = Event(), Event()

    async def slow_profile(*args, **kwargs):
        entered.set()
        await asyncio.to_thread(release.wait, 5)
        return {"success": True, "data": {"sec_uid": "sec", "video_count": 0}}

    profile.side_effect = slow_profile
    monkeypatch.setattr(op_account_service, "SessionLocal", session_factory)
    monkeypatch.setattr(op_collector_service, "select_proxy", lambda session: None)
    for name in ("owner", "waiter"):
        db.add(OpCollectTask(id=name, total=1, status="running"))
    db.commit()
    shared = Mock(wraps=op_collector_service.asyncio.wrap_future)
    monkeypatch.setattr(op_collector_service.asyncio, "wrap_future", shared)
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(op_account_service.run_collect_task, "owner", [account.id])
        assert entered.wait(5)
        waiter = pool.submit(op_account_service.run_collect_task, "waiter", [account.id])
        # The second task reaches the shared Future before releasing the request.
        for _ in range(500):
            if shared.call_count:
                break
            Event().wait(0.01)
        assert shared.call_count == 1
        release.set()
        owner.result(5)
        waiter.result(5)
    db.expire_all()
    assert profile.await_count == videos.await_count == 1
    assert account.collect_status == "success"
    for name in ("owner", "waiter"):
        task = db.get(OpCollectTask, name)
        assert (task.status, task.completed, task.success, task.failed) == ("completed", 1, 1, 0)
    # Running an already-completed task again must not re-fetch or over-count.
    op_account_service.run_collect_task("waiter", [account.id, account.id])
    assert profile.await_count == 1
    assert not op_collector_service._collection_results


def test_waiter_cancellation_cannot_cancel_owner_and_owner_cancel_releases_guard(db, session_factory, monkeypatch):
    account, profile, _ = account_with_scraper(db, monkeypatch)

    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        async def slow(*args, **kwargs):
            entered.set()
            await release.wait()
            return {"success": True, "data": {"sec_uid": "sec", "video_count": 0}}
        profile.side_effect = slow
        owner = asyncio.create_task(op_collector_service.collect_account(db, account))
        await entered.wait()
        with session_factory() as other_db:
            duplicate = asyncio.create_task(op_collector_service.collect_account(other_db, other_db.get(OpAccount, account.id)))
            await asyncio.sleep(0)
            duplicate.cancel()
            with pytest.raises(asyncio.CancelledError):
                await duplicate
            release.set()
            assert await owner
        entered.clear()
        release.clear()
        interrupted = asyncio.create_task(op_collector_service.collect_account(db, account))
        await entered.wait()
        interrupted.cancel()
        with pytest.raises(asyncio.CancelledError):
            await interrupted
        assert account.collect_status == "failed"
        assert account.collect_error.startswith("COLLECTION_INTERRUPTED:")
        assert account.next_attempt_at is not None
        assert not op_collector_service._collection_results
        profile.side_effect = None
        assert await op_collector_service.collect_account(db, account)
    asyncio.run(run())


def test_failed_final_commit_is_not_shared_as_success(db, session_factory, monkeypatch):
    account, profile, _ = account_with_scraper(db, monkeypatch)
    original_commit = db.commit
    commits = 0
    def fail_final_commit():
        nonlocal commits
        commits += 1
        if commits == 5:
            raise RuntimeError("Final schedule write failed")
        original_commit()
    monkeypatch.setattr(db, "commit", fail_final_commit)

    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        async def slow(*args, **kwargs):
            entered.set()
            await release.wait()
            return {"success": True, "data": {"sec_uid": "sec", "video_count": 0}}
        profile.side_effect = slow
        owner = asyncio.create_task(op_collector_service.collect_account(db, account))
        await entered.wait()
        with session_factory() as waiter_db:
            waiter = asyncio.create_task(op_collector_service.collect_account(waiter_db, waiter_db.get(OpAccount, account.id)))
            await asyncio.sleep(0)
            release.set()
            with pytest.raises(RuntimeError, match="Final schedule write failed"):
                await owner
            assert await waiter is False
    asyncio.run(run())
    assert account.collect_status == "failed"
    assert account.collect_error.startswith("COLLECTION_INTERRUPTED:")
    assert not op_collector_service._collection_results


def test_profile_and_video_failover_share_two_proxy_budget_and_use_timeout(db, monkeypatch):
    account, profile, videos = account_with_scraper(db, monkeypatch)
    db.add(MonitorSettings(id=1, request_timeout=9))
    proxies = [MonitorProxy(name=str(i), proxy_type="socks5", host="test.invalid", port=1080) for i in range(3)]
    db.add_all(proxies)
    db.commit()
    profile.side_effect = [
        {"success": False, "error": "PROXY_ERROR: protocol", "error_code": "proxy_error", "retryable": True},
        {"success": True, "data": {"sec_uid": "sec", "video_count": 1}},
    ]
    videos.return_value = {"success": False, "error": "TIMEOUT: videos", "error_code": "timeout", "retryable": True}
    select = Mock(return_value=proxies[1])
    monkeypatch.setattr(op_collector_service, "select_proxy", select)
    assert not asyncio.run(op_collector_service.collect_account(db, account, proxies[0]))
    assert [call.kwargs["proxy"].id for call in profile.await_args_list] == [proxies[0].id, proxies[1].id]
    assert videos.await_args.kwargs == {"proxy": proxies[1], "max_count": 20, "timeout": 9}
    assert all(call.kwargs["timeout"] == 9 for call in profile.await_args_list)
    select.assert_called_once()
    assert account.last_collected_at is not None
    assert account.collect_status == "failed"
    assert 299 <= (account.next_attempt_at - account.last_attempt_at).total_seconds() <= 302


@pytest.mark.parametrize("error", ["ACCOUNT_NOT_FOUND: gone", "VERIFICATION_REQUIRED: captcha", "TikTok 主页 HTTP 200 未获取数据"])
def test_permanent_profile_failures_do_not_rotate_or_schedule_short_retry(db, monkeypatch, error):
    account, profile, videos = account_with_scraper(db, monkeypatch, platform_sec_uid="cached")
    proxy = MonitorProxy(name="first", proxy_type="socks5", host="test.invalid", port=1080)
    db.add(proxy)
    db.commit()
    profile.return_value = {"success": False, "error": error}
    select = Mock()
    monkeypatch.setattr(op_collector_service, "select_proxy", select)
    assert not asyncio.run(op_collector_service.collect_account(db, account, proxy))
    select.assert_not_called()
    videos.assert_awaited_once()
    assert (account.next_attempt_at - account.last_attempt_at).total_seconds() >= 14400


def test_short_retry_budget_persists_then_reopens_only_after_normal_interval(db, session_factory, monkeypatch):
    account, profile, _ = account_with_scraper(db, monkeypatch)
    profile.return_value = {"success": False, "error": "TIMEOUT: profile"}
    clock = datetime(2026, 10, 7, 8)
    class Clock:
        @staticmethod
        def utcnow():
            return clock
    monkeypatch.setattr(op_collector_service, "datetime", Clock)
    monkeypatch.setattr(op_account_service, "datetime", Clock)
    monkeypatch.setattr(op_collector_service, "select_proxy", lambda session: None)
    assert not asyncio.run(op_collector_service.collect_account(db, account))
    for expected_count, expected_delay in [(0, 300), (1, 900), (2, 1800), (3, 14400)]:
        db.refresh(account)
        assert account.collect_retry_count == expected_count
        assert account.next_attempt_at == clock + timedelta(seconds=expected_delay)
        # An unrelated manual edit cannot change the retry clock.
        op_account_service.update_op_account(db, account.id, OpAccountUpdate(remark="edited"))
        clock = account.next_attempt_at - timedelta(seconds=1)
        before = profile.await_count
        asyncio.run(op_account_service.run_scheduled_collections(session_factory))
        assert profile.await_count == before
        clock += timedelta(seconds=1)
        asyncio.run(op_account_service.run_scheduled_collections(session_factory))
        assert profile.await_count == before + 1
    db.refresh(account)
    assert account.collect_retry_count == 0
    assert account.next_attempt_at == clock + timedelta(seconds=300)


def test_startup_recovery_preserves_new_accounts_and_counts_interrupted_task(db, monkeypatch):
    startup = datetime(2026, 10, 7, 8)
    old = OpAccount(platform="tiktok", account="interrupted", collect_status="pending",
                    last_attempt_at=startup - timedelta(minutes=2), collect_retry_count=1)
    new = OpAccount(platform="tiktok", account="new", collect_status="pending")
    later = OpAccount(platform="tiktok", account="future", collect_status="pending", last_attempt_at=startup + timedelta(seconds=1))
    task = OpCollectTask(id="interrupted", total=4, completed=1, success=1, failed=0, created_at=startup)
    db.add_all([old, new, later, task])
    db.commit()
    op_account_service.recover_interrupted_collections(db, startup)
    assert (task.status, task.completed, task.success, task.failed) == ("failed", 4, 1, 3)
    assert old.collect_status == "failed"
    assert old.collect_error.startswith("COLLECTION_INTERRUPTED:")
    assert old.next_attempt_at == startup + timedelta(seconds=900)
    assert new.collect_status == later.collect_status == "pending"
    op_account_service.recover_interrupted_collections(db, startup)
    assert task.failed == 3


def test_partial_video_response_retains_last_complete_snapshot(db, monkeypatch):
    timestamp = datetime.utcnow() - timedelta(days=1)
    account, _, videos = account_with_scraper(db, monkeypatch, video_collected_at=timestamp)
    db.add(OpAccountVideo(account_id=account.id, video_id="old", play_count=11))
    db.commit()
    videos.return_value = {"success": True, "partial": True, "data": [{"video_id": "new", "play_count": 22}],
                           "error": "PARTIAL: page two HTTP 503", "error_code": "partial_result", "retryable": True}
    assert not asyncio.run(op_collector_service.collect_account(db, account))
    assert account.video_collected_at == timestamp
    assert [(video.video_id, video.play_count) for video in db.query(OpAccountVideo).all()] == [("old", 11)]
    assert account.collect_status == "failed"
