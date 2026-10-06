from datetime import datetime, timedelta

import pytest

from app.models.monitor import MonitorAccount, MonitorHistory, Project
from app.models.op_account import OpAccount
from app.models.video import OpAccountVideo
from app.schemas.op_account import OpAccountUpdate
from app.services.account_summary_service import enrich_monitor_summaries
from app.services.op_account_service import update_op_account


@pytest.fixture(autouse=True)
def clean_follower_accounts(db, clean_tables):
    yield
    db.rollback()
    for model in (OpAccountVideo, MonitorHistory, MonitorAccount, OpAccount, Project):
        db.query(model).delete()
    db.commit()


def test_operator_account_summary_uses_own_profile_delta(db, super_admin):
    account = OpAccount(
        platform="tiktok",
        account="own-delta",
        follower_count=125,
        previous_follower_count=100,
    )
    db.add(account)
    db.commit()

    enrich_monitor_summaries(db, [account], super_admin)

    assert account.followers_change == 25


def test_operator_account_summary_does_not_invent_first_profile_delta(db, super_admin):
    account = OpAccount(platform="tiktok", account="first-profile", follower_count=125)
    db.add(account)
    db.commit()

    enrich_monitor_summaries(db, [account], super_admin)

    assert account.followers_change is None


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [(0, 0, 0), (90, 100, -10), (None, 100, None)],
)
def test_operator_account_summary_handles_zero_negative_and_unknown_counts(
    db, super_admin, current, previous, expected
):
    account = OpAccount(
        platform="tiktok",
        account=f"counts-{current}",
        follower_count=current,
        previous_follower_count=previous,
    )
    db.add(account)
    db.commit()

    enrich_monitor_summaries(db, [account], super_admin)

    assert account.followers_change == expected


def test_monitor_delta_remains_fallback_when_own_baseline_is_unknown(db, super_admin):
    project = Project(name="fallback-project", created_by=super_admin.username)
    db.add(project)
    db.flush()
    monitor = MonitorAccount(username="fallback", project_id=project.id)
    account = OpAccount(platform="tiktok", account="@fallback", follower_count=125)
    db.add_all([monitor, account])
    db.flush()
    db.add_all([
        MonitorHistory(
            account_id=monitor.id,
            follower_count=100,
            check_status="success",
            checked_at=datetime(2026, 10, 1, 0, 0),
        ),
        MonitorHistory(
            account_id=monitor.id,
            follower_count=110,
            check_status="success",
            checked_at=datetime(2026, 10, 2, 0, 0),
        ),
    ])
    db.commit()

    enrich_monitor_summaries(db, [account], super_admin)

    assert account.followers_change == 10


def test_own_delta_takes_priority_over_monitor_history(db, super_admin):
    project = Project(name="own-priority-project", created_by=super_admin.username)
    db.add(project)
    db.flush()
    monitor = MonitorAccount(username="priority", project_id=project.id)
    account = OpAccount(
        platform="tiktok",
        account="@priority",
        follower_count=125,
        previous_follower_count=120,
    )
    db.add_all([monitor, account])
    db.flush()
    db.add_all([
        MonitorHistory(
            account_id=monitor.id,
            follower_count=100,
            check_status="success",
            checked_at=datetime(2026, 10, 1, 0, 0),
        ),
        MonitorHistory(
            account_id=monitor.id,
            follower_count=110,
            check_status="success",
            checked_at=datetime(2026, 10, 2, 0, 0),
        ),
    ])
    db.commit()

    enrich_monitor_summaries(db, [account], super_admin)

    assert account.followers_change == 5


def test_identity_edit_retains_videos_but_excludes_old_identity_summary(db, super_admin):
    account = OpAccount(
        platform="tiktok",
        account="old-summary",
        follower_count=125,
        previous_follower_count=120,
        video_collected_at=datetime.utcnow(),
    )
    db.add(account)
    db.flush()
    db.add(OpAccountVideo(
        account_id=account.id,
        video_id="old-video",
        play_count=10,
        published_at=datetime.utcnow() - timedelta(days=1),
    ))
    db.commit()
    enrich_monitor_summaries(db, [account], super_admin)
    assert account.yesterday_video_count == 1

    update_op_account(db, account.id, OpAccountUpdate(account="new-summary"))
    enrich_monitor_summaries(db, [account], super_admin)

    assert db.query(OpAccountVideo).filter_by(account_id=account.id).count() == 1
    assert account.followers_change is None
    assert account.yesterday_video_count is None
    assert account.yesterday_video_plays is None
