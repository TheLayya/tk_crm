import base64
import json
import struct
import zlib
from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy import update

from app.models.card_key import CardKey, CardKeyProject
from app.models.failure_report import FailureReport
from app.models.op_account import EmailAccount
from tests.test_card_keys import grant, headers, project


def png_bytes():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00\xff')) + chunk(b'IEND', b'')


def screenshot():
    return {'name': '兑换失败.png', 'content_type': 'image/png', 'data': base64.b64encode(png_bytes()).decode()}


def claimed_key(client, db, admin, member):
    grant(db, member, 'card_key:view')
    project_id = project(client, admin, [member.username])
    client.post(f'/api/card-keys/{project_id}/import', headers=headers(admin), json={'content': 'failure-test-key'})
    result = client.post(f'/api/card-keys/{project_id}/claim', headers=headers(member))
    assert result.status_code == 200
    return project_id, result.json()['id']


def test_key_failure_images_are_encrypted_deferred_and_authorized(client, db, super_admin, normal_user, other_user):
    project_id, key_id = claimed_key(client, db, super_admin, normal_user)
    grant(db, other_user, 'card_key:view')
    base = f'/api/card-keys/{project_id}/keys/{key_id}'
    response = client.post(base + '/invalid', headers=headers(normal_user), json={'remark': '', 'screenshots': [screenshot(), screenshot()]})
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['status'] == 'invalid' and value['failure_report_count'] == 1 and value['screenshot_count'] == 2
    assert value['history'][-1]['image_count'] == 2
    assert value['history'][-1]['failure_report_id']
    db.expire_all()
    report = db.query(FailureReport).one()
    assert 'screenshots' in inspect(report).unloaded
    raw = db.execute(text('SELECT screenshots FROM failure_reports')).scalar_one()
    assert screenshot()['data'] not in raw and '兑换失败' not in raw
    report_list = client.get(base + '/failure-reports', headers=headers(normal_user))
    assert report_list.status_code == 200 and report_list.headers['cache-control'] == 'no-store'
    metadata = report_list.json()[0]
    assert metadata['kind'] == 'card_key' and metadata['image_count'] == 2
    assert metadata['images'][0]['width'] == metadata['images'][0]['height'] == 1
    assert 'data' not in json.dumps(metadata)
    image_url = '/api' + metadata['images'][0]['url']
    image = client.get(image_url, headers=headers(normal_user))
    assert image.status_code == 200 and image.content == png_bytes()
    assert image.headers['content-type'] == 'image/png' and image.headers['cache-control'] == 'no-store'
    assert image.headers['x-content-type-options'] == 'nosniff'
    assert client.get(image_url, headers=headers(super_admin)).status_code == 200
    assert client.get(image_url, headers=headers(other_user)).status_code == 404
    assert client.get(base + '/failure-reports', headers=headers(other_user)).status_code == 404
    assert client.get(image_url).status_code == 401
    listed = client.get(f'/api/card-keys/{project_id}/keys', headers=headers(super_admin)).json()['items'][0]
    assert (listed['failure_report_count'], listed['screenshot_count']) == (1, 2)
    assert screenshot()['data'] not in json.dumps(listed)


def test_key_failure_requires_image_and_parent_isolation(client, db, super_admin, normal_user):
    project_id, key_id = claimed_key(client, db, super_admin, normal_user)
    base = f'/api/card-keys/{project_id}/keys/{key_id}'
    response = client.post(base + '/invalid', headers=headers(normal_user), json={'remark': '兑换报错'})
    assert response.status_code == 422
    assert db.query(FailureReport).count() == 0
    db.expire_all()
    assert db.get(CardKey, key_id).status == 'claimed'
    response = client.post(base + '/invalid', headers=headers(normal_user), json={'remark': '兑换报错', 'screenshots': [screenshot()]})
    assert response.status_code == 200
    report = db.query(FailureReport).one()
    assert report.image_count == 1 and report.remark == '兑换报错'
    assert client.get(base + f'/failure-reports/{report.id}/screenshots/-1', headers=headers(super_admin)).status_code == 404
    assert client.get(f'/api/card-keys/{project_id + 1}/keys/{key_id}/failure-reports', headers=headers(super_admin)).status_code == 404
    archived = client.delete(f'/api/card-keys/{project_id}', headers=headers(super_admin)).json()
    assert archived['deleted'] is False and archived['archived'] is True
    db.expire_all()
    assert db.query(CardKeyProject).filter_by(id=project_id).first().archived_at is not None
    assert db.query(FailureReport).count() == 1


@pytest.mark.parametrize('payload', [
    {'remark': '  ', 'screenshots': []},
    {'screenshots': [{'name': 'a.svg', 'content_type': 'image/svg+xml', 'data': 'PHN2Zz4='}]},
    {'screenshots': [{'name': 'fake.png', 'content_type': 'image/png', 'data': base64.b64encode(b'not-a-picture').decode()}]},
    {'screenshots': [{'name': 'a.png', 'content_type': 'image/png', 'data': '*'}]},
    {'screenshots': [screenshot()] * 6},
    {'screenshots': [{'name': 'too-large.png', 'content_type': 'image/png', 'data': base64.b64encode(b'x' * (3 * 1024 * 1024 + 1)).decode()}]},
])
def test_invalid_images_leave_card_claim_and_report_unchanged(client, db, super_admin, normal_user, payload):
    project_id, key_id = claimed_key(client, db, super_admin, normal_user)
    response = client.post(f'/api/card-keys/{project_id}/keys/{key_id}/invalid', headers=headers(normal_user), json=payload)
    assert response.status_code == 422, response.text
    db.expire_all()
    assert db.get(CardKey, key_id).status == 'claimed'
    assert db.query(FailureReport).count() == 0


def test_email_failure_summary_scope_and_delete_history(client, db, super_admin, normal_user, other_user):
    grant(db, normal_user, 'card_key:view', 'email:view')
    grant(db, other_user, 'email:view')
    project_id = project(client, super_admin, [normal_user.username])
    from app.models.card_key import CardKeyProject
    db.get(CardKeyProject, project_id).target_platform = 'TikTok'
    email = EmailAccount(email='failed@example.invalid', registrant=normal_user.username, claimed_by=normal_user.username, claimed_platform='TikTok')
    db.add(email)
    db.commit()
    email_id = email.id
    body = {'remark': '验证码失败', 'screenshots': [screenshot()], 'expected_email_id': email_id}
    result = client.post(f'/api/card-keys/{project_id}/email/fail', headers=headers(normal_user), json=body)
    assert result.status_code == 200, result.text
    assert result.json()['failure_report_id'] and result.json()['screenshot_count'] == 1
    row = client.get('/api/emails', headers=headers(normal_user)).json()['items'][0]
    assert (row['failure_report_count'], row['screenshot_count'], row['latest_failure_remark']) == (1, 1, '验证码失败')
    assert row['management_status'] == '废弃'
    path = f'/api/emails/{email_id}/failure-reports'
    reports = client.get(path, headers=headers(normal_user))
    assert reports.status_code == 200 and reports.json()[0]['kind'] == 'email'
    url = '/api' + reports.json()[0]['images'][0]['url']
    assert client.get(url, headers=headers(normal_user)).content == png_bytes()
    assert client.get(path, headers=headers(other_user)).status_code == 404
    assert client.get(url, headers=headers(other_user)).status_code == 404
    assert client.delete(f'/api/emails/{email_id}', headers=headers(super_admin)).status_code == 409
    assert db.query(FailureReport).count() == 1


def test_stale_email_failure_does_not_mark_new_claim(client, db, super_admin, normal_user):
    from app.models.card_key import CardKeyProject
    grant(db, normal_user, 'card_key:view')
    project_id = project(client, super_admin, [normal_user.username])
    db.get(CardKeyProject, project_id).target_platform = 'TikTok'
    row = EmailAccount(email='new-claim@example.invalid', claimed_by=normal_user.username, claimed_platform='TikTok')
    db.add(row)
    db.commit()
    response = client.post(f'/api/card-keys/{project_id}/email/fail', headers=headers(normal_user), json={'remark': '旧邮箱截图', 'expected_email_id': row.id + 1, 'screenshots': [screenshot()]})
    assert response.status_code == 409
    db.expire_all()
    assert db.get(EmailAccount, row.id).claimed_by == normal_user.username
    assert db.query(FailureReport).count() == 0


def test_key_report_and_status_roll_back_on_compare_conflict(client, db, super_admin, normal_user, monkeypatch):
    project_id, key_id = claimed_key(client, db, super_admin, normal_user)
    from app.services.failure_report_store import create_report

    def concurrent_change(session, project, **kwargs):
        report = create_report(session, project, **kwargs)
        session.execute(update(CardKey).where(CardKey.id == key_id).values(history=[{'action': 'concurrent'}]).execution_options(synchronize_session=False))
        return report

    monkeypatch.setattr('app.api.card_keys.create_report', concurrent_change)
    response = client.post(f'/api/card-keys/{project_id}/keys/{key_id}/invalid', headers=headers(normal_user), json={'screenshots': [screenshot()]})
    assert response.status_code == 409
    db.expire_all()
    assert db.get(CardKey, key_id).status == 'claimed'
    assert [event['action'] for event in db.get(CardKey, key_id).history] == ['claim']
    assert db.query(FailureReport).count() == 0


def test_email_report_storage_failure_rolls_back_state(client, db, super_admin, normal_user, monkeypatch):
    from app.models.card_key import CardKeyProject
    grant(db, normal_user, 'card_key:view')
    project_id = project(client, super_admin, [normal_user.username])
    db.get(CardKeyProject, project_id).target_platform = 'TikTok'
    row = EmailAccount(email='atomic-failure@example.invalid', claimed_by=normal_user.username, claimed_platform='TikTok', claimed_at=datetime.utcnow())
    db.add(row)
    db.commit()
    email_id = row.id

    def unavailable(*args, **kwargs):
        raise RuntimeError('synthetic report storage failure')

    monkeypatch.setattr('app.api.card_keys.create_report', unavailable)
    with pytest.raises(RuntimeError, match='synthetic report storage'):
        client.post(f'/api/card-keys/{project_id}/email/fail', headers=headers(normal_user), json={'remark': '测试事务', 'screenshots': [screenshot()]})
    db.expire_all()
    assert db.get(EmailAccount, email_id).management_status == '闲置'
    assert db.get(EmailAccount, email_id).claimed_by == normal_user.username
    assert db.query(FailureReport).count() == 0


def test_failure_report_migration_preserves_old_rows(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / 'alembic.ini'))
    config.set_main_option('script_location', str(backend / 'alembic'))
    config.set_main_option('sqlalchemy.url', 'sqlite:///' + (tmp_path / 'failure-upgrade.db').as_posix())
    command.upgrade(config, '20261015_0025')
    command.upgrade(config, 'head')
    command.check(config)
