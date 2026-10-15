"""Upgrade keeps historical card ownership, encrypted payload and flow records."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


def test_card_batch_upgrade_keeps_legacy_cards_and_constraints(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / 'alembic.ini'))
    config.set_main_option('script_location', str(backend / 'alembic'))
    database_url = 'sqlite:///' + (tmp_path / 'card-batch-upgrade.db').as_posix()
    config.set_main_option('sqlalchemy.url', database_url)
    command.upgrade(config, '20261007_0024')
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("""INSERT INTO card_key_projects
                (id, name, member_usernames, is_active, created_by, created_at, updated_at)
                VALUES (1, 'Historical project', ',member,', 1, 'admin', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""))
            connection.execute(text("""INSERT INTO card_keys
                (id, project_id, content, fingerprint, pending_owner, status, claimed_by,
                 claimed_at, consumed_at, history, remark, created_by, created_at)
                VALUES (1, 1, 'encrypted-fixture-unchanged', :fingerprint, 'member', 'claimed',
                 'member', '2026-10-01 01:02:03', NULL, :history, 'Original note', 'admin', CURRENT_TIMESTAMP)"""),
                               {'fingerprint': 'a' * 64, 'history': '[{"action":"claim","username":"member"}]'})
            before = connection.execute(text('SELECT * FROM card_keys WHERE id=1')).mappings().one()
            snapshot = dict(before)
        command.upgrade(config, 'head')
        inspector = inspect(engine)
        assert 'card_key_batches' in inspector.get_table_names()
        assert 'batch_id' in {column['name'] for column in inspector.get_columns('card_keys')}
        with engine.connect() as connection:
            after = dict(connection.execute(text('SELECT * FROM card_keys WHERE id=1')).mappings().one())
            assert after.pop('batch_id') is None
            assert after == snapshot
            assert connection.execute(text('PRAGMA integrity_check')).scalar_one() == 'ok'
            assert connection.execute(text('PRAGMA foreign_key_check')).all() == []
            assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == ScriptDirectory.from_config(config).get_current_head()
        constraints = {tuple(item['column_names']) for item in inspector.get_unique_constraints('card_keys')}
        assert {('fingerprint',), ('project_id', 'pending_owner')} <= constraints
        command.upgrade(config, 'head')
        command.check(config)
    finally:
        engine.dispose()
