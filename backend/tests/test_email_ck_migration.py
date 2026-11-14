"""The additive CK migration leaves historical notes and credentials untouched."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_email_ck_upgrade_keeps_legacy_rows_and_downgrade(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    database_url = "sqlite:///" + (tmp_path / "email-ck.db").as_posix()
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "20261016_0026")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("""INSERT INTO email_accounts
                (id, email, password, totp_secret, remark, management_status, registrant, created_at, updated_at)
                VALUES (1, 'legacy-ck@example.invalid', 'encrypted-password-fixture', 'encrypted-totp-fixture',
                        'Original Cookie note', '闲置', 'root', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""))
            before = dict(connection.execute(text("SELECT * FROM email_accounts WHERE id=1")).mappings().one())
        command.upgrade(config, "head")
        column = next(item for item in inspect(engine).get_columns("email_accounts") if item["name"] == "ck")
        assert column["nullable"] is True
        with engine.connect() as connection:
            after = dict(connection.execute(text("SELECT * FROM email_accounts WHERE id=1")).mappings().one())
            assert after.pop("ck") is None
            assert after.pop("allow_card_key_claim") == 0
            assert after == before
            assert connection.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        command.check(config)
        command.downgrade(config, "20261016_0026")
        assert "ck" not in {item["name"] for item in inspect(engine).get_columns("email_accounts")}
        with engine.connect() as connection:
            assert dict(connection.execute(text("SELECT * FROM email_accounts WHERE id=1")).mappings().one()) == before
        command.upgrade(config, "head")
        command.check(config)
    finally:
        engine.dispose()
