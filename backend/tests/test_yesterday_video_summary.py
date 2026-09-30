from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.video import Video
from app.services.video_service import get_yesterday_video_counts, get_yesterday_video_plays


def test_yesterday_video_counts_beijing_boundaries_and_unknown():
    engine = create_engine("sqlite://")
    Video.__table__.create(engine)
    now = datetime(2026, 9, 30, 2, tzinfo=timezone.utc)
    with Session(engine) as db:
        for index, published in enumerate([
            datetime(2026, 9, 28, 15, 59, 59),
            datetime(2026, 9, 28, 16),
            datetime(2026, 9, 29, 15, 59, 59),
            datetime(2026, 9, 29, 16),
        ]):
            db.add(Video(account_id=1, video_id=str(index), published_at=published, play_count=[999, 100, 30000, 888][index], updated_at=datetime(2026, 9, 30)))
        db.add(Video(account_id=2, video_id="old", published_at=datetime(2026, 9, 1), updated_at=datetime(2026, 9, 28)))
        db.add(Video(account_id=3, video_id="fresh", published_at=datetime(2026, 9, 1), updated_at=datetime(2026, 9, 30)))
        db.add(Video(account_id=4, video_id="unknown-date", updated_at=datetime(2026, 9, 30)))
        db.commit()
        counts = get_yesterday_video_counts(db, [1, 2, 3, 4, 5], now)
        assert counts[1] == 2
        assert counts[2] is None
        assert counts[3] == 0
        assert counts.get(4) is None
        assert counts.get(5) is None
        assert get_yesterday_video_counts(db, [], now) == {}
        plays = get_yesterday_video_plays(db, [1, 2, 3, 4, 5], now)
        assert plays == {1: [30000, 100]}
        assert get_yesterday_video_plays(db, [], now) == {}
    engine.dispose()
