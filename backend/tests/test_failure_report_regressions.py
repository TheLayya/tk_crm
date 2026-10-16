import base64
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.models.failure_report import FailureReport
from app.models.team import OperationLog
from app.services.encryption_service import _get_encryption_service
from tests.test_card_keys import headers
from tests.test_failure_reports import claimed_key, png_bytes, screenshot


def test_remark_changes_and_backups_preserve_failure_images(client, db, super_admin, normal_user, engine, tmp_path):
    project_id, key_id = claimed_key(client, db, super_admin, normal_user)
    base = f'/api/card-keys/{project_id}/keys/{key_id}'
    response = client.post(base + '/invalid', headers=headers(normal_user), json={
        'remark': '上游兑换提示失败', 'screenshots': [screenshot()],
    })
    assert response.status_code == 200, response.text
    report_id = response.json()['history'][-1]['failure_report_id']
    updated = client.put(base + '/remark', headers=headers(normal_user), json={'remark': '已向供应商申请补发'})
    assert updated.status_code == 200
    report = client.get(base + '/failure-reports', headers=headers(normal_user)).json()[0]
    assert report['remark'] == '上游兑换提示失败'
    assert client.get('/api' + report['images'][0]['url'], headers=headers(normal_user)).content == png_bytes()
    raw = db.execute(text('SELECT screenshots FROM failure_reports WHERE id=:id'), {'id': report_id}).scalar_one()
    assert screenshot()['data'] not in raw
    audit = db.query(OperationLog).filter_by(action='REPORT_FAILURE').one()
    assert audit.result == 'success'
    assert screenshot()['data'] not in json.dumps([audit.summary, audit.error])
    db.commit()
    target = tmp_path / 'backup.db'
    connection = engine.raw_connection()
    try:
        with sqlite3.connect(target) as backup:
            connection.driver_connection.backup(backup)
    finally:
        connection.close()
    with sqlite3.connect(target) as restored:
        retained = restored.execute('SELECT screenshots FROM failure_reports WHERE id=?', (report_id,)).fetchone()[0]
        assert retained == raw
        decoded = json.loads(_get_encryption_service().decrypt(retained))
        assert base64.b64decode(decoded[0]['data']) == png_bytes()
    assert db.query(FailureReport).count() == 1


def test_upgrade_from_0025_preserves_existing_ciphertext(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / 'alembic.ini'))
    config.set_main_option('script_location', str(backend / 'alembic'))
    url = 'sqlite:///' + (tmp_path / 'old-data.db').as_posix()
    config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, '20261015_0025')
    database = create_engine(url)
    cipher = _get_encryption_service().encrypt('synthetic-existing-email-password')
    with database.begin() as connection:
        connection.execute(text('INSERT INTO email_accounts (id,email,password,management_status,created_at,updated_at) '
                                'VALUES (1,:email,:password,:status,:created,:updated)'), {
            'email': 'migration-fixture@example.invalid', 'password': cipher, 'status': '废弃',
            'created': datetime(2026, 10, 15), 'updated': datetime(2026, 10, 15),
        })
    command.upgrade(config, 'head')
    with database.connect() as connection:
        row = connection.execute(text('SELECT email,password,management_status FROM email_accounts WHERE id=1')).one()
        assert tuple(row) == ('migration-fixture@example.invalid', cipher, '废弃')
        assert connection.execute(text('SELECT COUNT(*) FROM failure_reports')).scalar_one() == 0
        assert connection.execute(text('PRAGMA integrity_check')).scalar_one() == 'ok'
    command.check(config)
    database.dispose()
