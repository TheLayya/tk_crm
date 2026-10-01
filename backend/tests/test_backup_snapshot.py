import asyncio
import io
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from contextlib import closing
import zipfile

import pytest

from app.services import backup_service as module


@pytest.mark.parametrize('download', [True, False])
def test_backup_includes_committed_wal_data(tmp_path, monkeypatch, download):
    source = tmp_path / 'monitor.db'
    original = sqlite3.connect(source)
    try:
        original.execute('PRAGMA journal_mode=WAL')
        original.execute('PRAGMA wal_autocheckpoint=0')
        original.execute('CREATE TABLE snapshot_test (content TEXT)')
        original.execute('CREATE TABLE projects (id INTEGER PRIMARY KEY)')
        original.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
        original.execute('CREATE TABLE monitor_accounts (id INTEGER PRIMARY KEY)')
        original.execute("INSERT INTO snapshot_test VALUES ('committed-in-wal')")
        original.commit()
        assert source.with_name('monitor.db-wal').stat().st_size > 0
        monkeypatch.setattr(module, 'settings', SimpleNamespace(DATABASE_URL='sqlite:///' + str(source)))
        monkeypatch.setattr(module.tempfile, 'tempdir', str(tmp_path))
        captured = []

        async def send_backup(**arguments):
            captured.append(arguments['file_path'].read_bytes())

        monkeypatch.setattr(module, 'send_telegram', send_backup)
        database = Mock()
        database.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            telegram_enabled=True, telegram_bot_token='test', telegram_chat_id='test', email_enabled=False,
        )
        service = module.BackupService()
        service._lock = asyncio.Lock()
        result = asyncio.run(service.run_backup_download(database) if download else service.run_backup(database))
        assert result is not None
        assert len(captured) == 1
        if download:
            assert result[1] == captured[0]
        restored = tmp_path / 'restored.db'
        with zipfile.ZipFile(io.BytesIO(captured[0])) as archive:
            assert archive.namelist() == ['monitor.db']
            restored.write_bytes(archive.read('monitor.db'))
        with closing(sqlite3.connect(restored)) as snapshot:
            assert snapshot.execute('PRAGMA integrity_check').fetchone() == ('ok',)
            assert snapshot.execute('SELECT content FROM snapshot_test').fetchall() == [('committed-in-wal',)]
        assert original.execute('SELECT content FROM snapshot_test').fetchone() == ('committed-in-wal',)
        assert not list(tmp_path.glob('tiktok_monitor_backup_*'))
    finally:
        original.close()


@pytest.mark.parametrize('download', [True, False])
def test_corrupt_database_backup_cleans_up_without_notification(tmp_path, monkeypatch, download):
    source = tmp_path / 'monitor.db'
    source.write_bytes(b'not-a-sqlite-database')
    monkeypatch.setattr(module, 'settings', SimpleNamespace(DATABASE_URL='sqlite:///' + str(source)))
    monkeypatch.setattr(module.tempfile, 'tempdir', str(tmp_path))
    notifications = []

    async def notify(**arguments):
        notifications.append(arguments)

    monkeypatch.setattr(module, 'send_telegram', notify)
    database = Mock()
    database.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        telegram_enabled=True, telegram_bot_token='test', telegram_chat_id='test', email_enabled=False,
    )
    service = module.BackupService()
    service._lock = asyncio.Lock()
    with pytest.raises(sqlite3.DatabaseError):
        asyncio.run(service.run_backup_download(database) if download else service.run_backup(database))
    assert notifications == []
    assert not service.is_running()
    assert not list(tmp_path.glob('tiktok_monitor_backup_*'))
    assert source.read_bytes() == b'not-a-sqlite-database'


def _zip_payload(database_bytes):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w') as archive:
        archive.writestr('monitor.db', database_bytes)
    return payload.getvalue()


def test_restore_rejects_corrupt_database_before_pre_restore_backup(tmp_path, monkeypatch):
    source = tmp_path / 'monitor.db'
    source.write_bytes(b'current-database')
    monkeypatch.setattr(module, 'settings', SimpleNamespace(DATABASE_URL='sqlite:///' + str(source)))
    monkeypatch.setattr(module.tempfile, 'tempdir', str(tmp_path))
    pre_backup = AsyncMock()
    monkeypatch.setattr(module.backup_service, 'run_backup', pre_backup)
    service = module.RestoreService()
    service._lock = asyncio.Lock()
    with pytest.raises(module.InvalidDatabaseBackupError):
        asyncio.run(service.run_restore(_zip_payload(b'not-sqlite'), 'broken.zip', Mock()))
    pre_backup.assert_not_called()
    assert source.read_bytes() == b'current-database'
    assert not list(tmp_path.glob('tiktok_monitor_restore_*'))


@pytest.mark.parametrize('failure', [None, RuntimeError('backup failure')])
def test_restore_stops_when_pre_restore_backup_fails(tmp_path, monkeypatch, failure):
    source = tmp_path / 'monitor.db'
    with closing(sqlite3.connect(source)) as connection, connection:
        connection.execute('CREATE TABLE snapshot_test (content TEXT)')
        connection.execute('CREATE TABLE projects (id INTEGER PRIMARY KEY)')
        connection.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
        connection.execute('CREATE TABLE monitor_accounts (id INTEGER PRIMARY KEY)')
        connection.execute("INSERT INTO snapshot_test VALUES ('current')")
    candidate = tmp_path / 'candidate.db'
    with closing(sqlite3.connect(candidate)) as connection, connection:
        connection.execute('CREATE TABLE snapshot_test (content TEXT)')
        connection.execute('CREATE TABLE projects (id INTEGER PRIMARY KEY)')
        connection.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
        connection.execute('CREATE TABLE monitor_accounts (id INTEGER PRIMARY KEY)')
        connection.execute("INSERT INTO snapshot_test VALUES ('candidate')")
    monkeypatch.setattr(module, 'settings', SimpleNamespace(DATABASE_URL='sqlite:///' + str(source)))
    monkeypatch.setattr(module.tempfile, 'tempdir', str(tmp_path))
    pre_backup = AsyncMock(return_value=None, side_effect=failure)
    monkeypatch.setattr(module.backup_service, 'run_backup', pre_backup)
    service = module.RestoreService()
    service._lock = asyncio.Lock()
    with pytest.raises(module.RestoreIOError, match='恢复前备份失败'):
        asyncio.run(service.run_restore(_zip_payload(candidate.read_bytes()), 'candidate.zip', Mock()))
    pre_backup.assert_awaited_once()
    with closing(sqlite3.connect(source)) as connection:
        assert connection.execute('SELECT content FROM snapshot_test').fetchone() == ('current',)
    assert not list(tmp_path.glob('tiktok_monitor_restore_*'))


def test_restore_rejects_healthy_non_crm_sqlite_database(tmp_path, monkeypatch):
    source = tmp_path / 'monitor.db'
    with closing(sqlite3.connect(source)) as connection:
        connection.execute('CREATE TABLE arbitrary (id INTEGER PRIMARY KEY)')
    monkeypatch.setattr(module, 'settings', SimpleNamespace(DATABASE_URL='sqlite:///' + str(source)))
    service = module.RestoreService()
    service._lock = asyncio.Lock()
    with pytest.raises(module.InvalidDatabaseBackupError, match='不是本系统数据库'):
        asyncio.run(service.run_restore(_zip_payload(source.read_bytes()), 'other.zip', Mock()))


def test_restore_snapshot_keeps_live_wal_connection_consistent(tmp_path):
    source = tmp_path / 'candidate.db'
    destination = tmp_path / 'monitor.db'
    with closing(sqlite3.connect(source)) as connection, connection:
        connection.execute('CREATE TABLE snapshot_test (content TEXT)')
        connection.execute("INSERT INTO snapshot_test VALUES ('candidate')")
    live_connection = sqlite3.connect(destination)
    live_connection.execute('PRAGMA journal_mode=WAL')
    live_connection.execute('PRAGMA wal_autocheckpoint=0')
    live_connection.execute('CREATE TABLE snapshot_test (content TEXT)')
    live_connection.execute("INSERT INTO snapshot_test VALUES ('current')")
    live_connection.commit()
    try:
        assert destination.with_name('monitor.db-wal').exists()
        module._replace_database_snapshot(source, destination)
        assert live_connection.execute('SELECT content FROM snapshot_test').fetchone() == ('candidate',)
        with closing(sqlite3.connect(destination)) as restored:
            assert restored.execute('SELECT content FROM snapshot_test').fetchone() == ('candidate',)
    finally:
        live_connection.close()
    with closing(sqlite3.connect(destination)) as reopened:
        assert reopened.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert reopened.execute('SELECT content FROM snapshot_test').fetchone() == ('candidate',)


def test_restore_success_runs_pre_backup_and_returns_result(tmp_path, monkeypatch):
    source = tmp_path / 'monitor.db'
    candidate = tmp_path / 'candidate.db'
    for path, value in ((source, 'current'), (candidate, 'candidate')):
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute('CREATE TABLE snapshot_test (content TEXT)')
            connection.execute('CREATE TABLE projects (id INTEGER PRIMARY KEY)')
            connection.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
            connection.execute('CREATE TABLE monitor_accounts (id INTEGER PRIMARY KEY)')
            connection.execute('INSERT INTO snapshot_test VALUES (?)', (value,))
    monkeypatch.setattr(module, 'settings', SimpleNamespace(DATABASE_URL='sqlite:///' + str(source)))
    monkeypatch.setattr(module.tempfile, 'tempdir', str(tmp_path))
    pre_backup = AsyncMock(return_value=module.BackupResult('pre.zip', 10, module.datetime.utcnow()))
    monkeypatch.setattr(module.backup_service, 'run_backup', pre_backup)
    service = module.RestoreService()
    service._lock = asyncio.Lock()
    result = asyncio.run(service.run_restore(_zip_payload(candidate.read_bytes()), 'candidate.zip', Mock()))
    assert result.filename == 'candidate.zip'
    assert result.restart_required is True
    assert result.pre_restore_backup.filename == 'pre.zip'
    pre_backup.assert_awaited_once()
    with closing(sqlite3.connect(source)) as connection:
        assert connection.execute('SELECT content FROM snapshot_test').fetchone() == ('candidate',)
    assert not list(tmp_path.glob('tiktok_monitor_restore_*'))
