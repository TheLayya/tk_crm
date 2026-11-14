from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_claim_policy_and_project_archive_migration(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    database_url = "sqlite:///" + (tmp_path / "claim-policy.db").as_posix()
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "20261114_0027")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("""INSERT INTO email_accounts
                (id, email, management_status, registrant, created_at, updated_at)
                VALUES (1, 'legacy-claim@example.invalid', '闲置', 'root', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""))
            connection.execute(text("""INSERT INTO card_key_projects
                (id, name, member_usernames, is_active, created_by, created_at, updated_at)
                VALUES (1, 'legacy-project', 'root', 1, 'root', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""))
        command.upgrade(config, "head")
        columns = {item["name"] for item in inspect(engine).get_columns("email_accounts")}
        assert "allow_card_key_claim" in columns
        project_columns = {item["name"] for item in inspect(engine).get_columns("card_key_projects")}
        assert {"archived_at", "archived_by"} <= project_columns
        with engine.connect() as connection:
            assert connection.execute(text(
                "SELECT allow_card_key_claim FROM email_accounts WHERE id=1")).scalar_one() == 0
            row = connection.execute(text(
                "SELECT archived_at, archived_by FROM card_key_projects WHERE id=1")).one()
            assert tuple(row) == (None, None)
            assert connection.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        command.check(config)
        command.downgrade(config, "20261114_0027")
        assert "allow_card_key_claim" not in {item["name"] for item in inspect(engine).get_columns("email_accounts")}
        assert "archived_at" not in {item["name"] for item in inspect(engine).get_columns("card_key_projects")}
        command.upgrade(config, "head")
        command.check(config)
    finally:
        engine.dispose()


def test_0030_resets_emails_enabled_by_the_old_true_default(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    database_url = "sqlite:///" + (tmp_path / "claim-default-off.db").as_posix()
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "20261114_0029")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("""INSERT INTO email_accounts
                (id, email, management_status, registrant, allow_card_key_claim, created_at, updated_at)
                VALUES (1, 'old-one@example.invalid', '闲置', 'root', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                       (2, 'old-two@example.invalid', '闲置', 'root', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""))
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.execute(text(
                "SELECT allow_card_key_claim FROM email_accounts ORDER BY id")).scalars().all() == [0, 0]
        command.check(config)
    finally:
        engine.dispose()
