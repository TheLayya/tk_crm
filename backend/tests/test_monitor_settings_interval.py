from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.settings import update_settings
from app.models.monitor import MonitorAccount, MonitorSettings, Project
from app.schemas.settings import SettingsUpdate


def test_saving_interval_updates_existing_accounts():
    engine = create_engine("sqlite://")
    for model in (Project, MonitorSettings, MonitorAccount):
        model.__table__.create(engine)
    with Session(engine) as db:
        project = Project(name="interval-test")
        db.add(project)
        db.flush()
        account = MonitorAccount(project_id=project.id, username="interval-test", monitor_interval=86400)
        db.add(account)
        db.commit()
        settings = update_settings(SettingsUpdate(default_interval=18000), db=db)
        db.refresh(account)
        assert settings.default_interval == 18000
        assert account.monitor_interval == 18000
        update_settings(SettingsUpdate(site_name="test"), db=db)
        db.refresh(account)
        assert account.monitor_interval == 18000
    engine.dispose()
