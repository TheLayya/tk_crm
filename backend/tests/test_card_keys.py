from concurrent.futures import ThreadPoolExecutor
import base64
import struct
import zlib
from datetime import datetime
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.api.card_keys import claim_key, consume_key, release_key, import_keys, ImportBody, fail_email, EmailFailureBody
from app.api.card_keys import _totp_code
from app.core.security import create_access_token
from app.models.card_key import CardKey, CardKeyBatch, CardKeyEmailUsage, CardKeyProject
from app.models.failure_report import FailureReport
from app.models.op_account import EmailAccount, EmailAccountRelation, OpAccount
from app.models.team import Role, RolePermission, User, UserRole


def failure_screenshot():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00\xff')) + chunk(b'IEND', b'')
    return {'name': 'failure.png', 'content_type': 'image/png', 'data': base64.b64encode(png).decode()}


def test_batch_import_filter_and_duplicate_ownership(client, db, super_admin):
    admin_headers = headers(super_admin)
    first_project = project(client, super_admin, ['__all__'])
    base = f'/api/card-keys/{first_project}'
    first = client.post(base + '/import', headers=admin_headers, json={
        'content': 'first\nsecond\nfirst', 'batch_name': '10月采购', 'remark': '供应商 A'}).json()
    assert (first['added'], first['duplicates']) == (2, 1)
    batch = first['batch']
    assert batch['name'] == '10月采购'
    assert batch['remark'] == '供应商 A'
    assert batch['status'] == 'active'
    assert batch['total'] == batch['available'] == 2
    assert batch['can_delete'] is True
    second = client.post(base + '/import', headers=admin_headers, json={
        'content': 'second\nthird'}).json()
    assert second['batch']['name'] == second['batch']['batch_no']
    assert second['batch']['id'] != batch['id']
    assert (second['added'], second['duplicates']) == (1, 1)
    items = client.get(base + f"/keys?batch_id={batch['id']}", headers=admin_headers).json()
    assert items['total'] == 2
    assert all(item['batch_name'] == '10月采购' and item['batch_remark'] == '供应商 A' for item in items['items'])
    assert db.query(CardKey).filter_by(project_id=first_project, batch_id=batch['id']).count() == 2
    other_project = project(client, super_admin, ['__all__'])
    duplicate = client.post(f'/api/card-keys/{other_project}/import', headers=admin_headers, json={
        'content': 'first'}).json()
    assert duplicate['added'] == 0 and duplicate['duplicates'] == 1
    assert db.query(CardKey).filter_by(project_id=first_project, batch_id=batch['id']).count() == 2
    assert client.get(base + '/batches', headers=admin_headers).json()[0]['id'] == second['batch']['id']


def test_batch_claim_pause_and_existing_pending(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view')
    admin_headers, member_headers = headers(super_admin), headers(normal_user)
    project_id = project(client, super_admin, ['alice'])
    base = f'/api/card-keys/{project_id}'
    batch_ids = [client.post(base + '/import', headers=admin_headers, json={
        'content': f'{name}-one\n{name}-two', 'batch_name': name}).json()['batch']['id'] for name in ['A', 'B']]
    first, second = batch_ids
    paused = client.put(base + f'/batches/{first}', headers=admin_headers,
                        json={'status': 'paused', 'pause_reason': '供应商排查'}).json()
    assert paused['pause_reason'] == '供应商排查'
    assert client.get('/api/card-keys', headers=member_headers).json()[0]['available'] == 2
    assert client.post(base + f'/claim?batch_id={first}', headers=member_headers).status_code == 409
    claimed = client.post(base + f'/claim?batch_id={second}', headers=member_headers).json()
    assert claimed['batch_id'] == second
    assert client.post(base + f'/claim?batch_id={first}', headers=member_headers).status_code == 409
    assert client.put(base + f'/batches/{second}', headers=admin_headers,
                      json={'status': 'paused', 'pause_reason': '临时停发'}).status_code == 200
    assert client.post(base + '/claim', headers=member_headers).json()['id'] == claimed['id']
    assert client.post(base + f'/claim?batch_id={second}', headers=member_headers).json()['id'] == claimed['id']
    assert client.post(base + f"/keys/{claimed['id']}/consume", headers=member_headers).status_code == 200
    assert client.post(base + '/claim', headers=member_headers).status_code == 409
    resumed = client.put(base + f'/batches/{first}', headers=admin_headers, json={'status': 'active'}).json()
    assert resumed['pause_reason'] == ''
    assert client.post(base + '/claim', headers=member_headers).json()['batch_id'] == first
    assert client.put(base + f'/batches/{first}', headers=member_headers, json={'status': 'paused'}).status_code == 403


def test_batch_delete_unused_and_archive_used_keys(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view')
    admin_headers, member_headers = headers(super_admin), headers(normal_user)
    project_id = project(client, super_admin, ['alice'])
    base = f'/api/card-keys/{project_id}'
    unused = client.post(base + '/import', headers=admin_headers, json={'content': 'unused'}).json()['batch']['id']
    assert client.delete(base + f'/batches/{unused}', headers=member_headers).status_code == 403
    deleted = client.delete(base + f'/batches/{unused}', headers=admin_headers).json()
    assert deleted['deleted'] is True and deleted['deleted_keys'] == 1
    assert db.get(CardKeyBatch, unused) is None
    used = client.post(base + '/import', headers=admin_headers, json={'content': 'unused\nretained'}).json()['batch']['id']
    claimed = client.post(base + f'/claim?batch_id={used}', headers=member_headers).json()
    assert client.post(base + f"/keys/{claimed['id']}/release", headers=member_headers).status_code == 200
    assert client.get(base + '/batches', headers=admin_headers).json()[0]['can_delete'] is False
    archived = client.delete(base + f'/batches/{used}', headers=admin_headers).json()
    assert archived['deleted'] is False and archived['archived'] is True
    assert db.query(CardKey).filter_by(batch_id=used).count() == 2
    assert client.get(base + '/batches', headers=admin_headers).json() == []
    history = client.get(base + '/batches?include_archived=true', headers=admin_headers).json()[0]
    assert history['status'] == 'archived'
    assert history['history'][-1]['action'] == 'archive'
    assert client.get(base + f'/keys?batch_id={used}', headers=admin_headers).json()['total'] == 2
    assert client.post(base + f'/claim?batch_id={used}', headers=member_headers).status_code == 409
    assert client.put(base + f'/batches/{used}', headers=admin_headers, json={'status': 'active'}).status_code == 409
    project_result = client.delete(base, headers=admin_headers).json()
    assert project_result['deleted'] is False and project_result['archived'] is True
    assert db.get(CardKeyProject, project_id).archived_at is not None
    assert client.get('/api/card-keys', headers=admin_headers).json() == []
    listed = client.get('/api/card-keys?include_archived=true', headers=admin_headers).json()
    assert listed[0]['archived'] is True and listed[0]['archived_by'] == 'root'


def test_batch_legacy_unbatched_and_member_scope(client, db, super_admin, normal_user, other_user):
    import hashlib
    grant(db, normal_user, 'card_key:view')
    grant(db, other_user, 'card_key:view')
    admin_headers, member_headers = headers(super_admin), headers(normal_user)
    project_id = project(client, super_admin, ['alice'])
    base = f'/api/card-keys/{project_id}'
    legacy = CardKey(project_id=project_id, content='legacy-key', fingerprint=hashlib.sha256(b'legacy-key').hexdigest(), created_by='root')
    db.add(legacy)
    db.commit()
    batch = client.post(base + '/import', headers=admin_headers, json={'content': 'new-key'}).json()['batch']
    assert client.get(base + '/keys?batch_id=0', headers=admin_headers).json()['total'] == 1
    assert client.get(base + '/batches', headers=member_headers).json()[0]['id'] == 0
    assert client.get(base + '/batches', headers=headers(other_user)).status_code == 403
    result = client.post(base + '/claim?batch_id=0', headers=member_headers).json()
    assert result['batch_id'] is None and result['batch_name'] == '历史未分批'
    assert client.post(base + f"/claim?batch_id={batch['id']}", headers=member_headers).status_code == 409
    assert client.put(base, headers=admin_headers, json={'name': '移除成员', 'members': ['root']}).status_code == 200
    remaining = client.get(base + '/batches', headers=member_headers)
    assert remaining.status_code == 200 and [row['id'] for row in remaining.json()] == [0]
    assert client.post(base + '/claim', headers=member_headers).status_code == 403
    assert client.post(base + f"/keys/{result['id']}/release", headers=member_headers).status_code == 200


def test_stale_claim_after_batch_pause_is_rejected(tmp_path):
    from app.api.card_keys import BatchBody, update_batch
    engine = create_engine(f"sqlite:///{tmp_path / 'pause-race.db'}", connect_args={'timeout': 15})
    CardKeyProject.__table__.create(engine)
    CardKeyBatch.__table__.create(engine)
    CardKey.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    user = User(username='root', is_super_admin=True)
    with sessions() as session:
        item = CardKeyProject(name='暂停竞态', member_usernames='root', created_by='root')
        session.add(item)
        session.commit()
        project_id = item.id
        batch_id = import_keys(project_id, ImportBody(content='pause-key'), session, user)['batch']['id']

    class PausedSession(Session):
        def execute(self, statement, *args, **kwargs):
            if getattr(statement, 'is_update', False):
                with sessions() as current:
                    update_batch(project_id, batch_id, BatchBody(status='paused', pause_reason='排查'), current, user)
            return super().execute(statement, *args, **kwargs)

    with PausedSession(bind=engine) as stale:
        try:
            claim_key(project_id, stale, user)
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError('Claim must check batch status again in the write statement')
    with sessions() as session:
        assert session.query(CardKey).one().status == 'available'
        assert session.get(CardKeyBatch, batch_id).status == 'paused'
    engine.dispose()


@pytest.mark.parametrize('scope,claim_first', [('batch', True), ('project', True), ('batch', False), ('project', False)])
def test_delete_and_claim_preserve_flow_history(tmp_path, scope, claim_first):
    from app.api.card_keys import delete_batch, delete_project
    engine = create_engine(f"sqlite:///{tmp_path / (scope + str(claim_first) + '.db')}", connect_args={'timeout': 15})
    for table in (CardKeyProject.__table__, CardKeyBatch.__table__, CardKey.__table__, CardKeyEmailUsage.__table__, EmailAccount.__table__, FailureReport.__table__):
        table.create(engine)
    sessions = sessionmaker(bind=engine)
    user = User(username='root', is_super_admin=True)
    with sessions() as session:
        item = CardKeyProject(name='删除竞态', member_usernames='root', created_by='root')
        session.add(item)
        session.commit()
        project_id = item.id
        batch_id = import_keys(project_id, ImportBody(content='delete-race'), session, user)['batch']['id']

    def remove(session):
        return delete_batch(project_id, batch_id, session, user) if scope == 'batch' else delete_project(project_id, session, user)

    class RacingSession(Session):
        def execute(self, statement, *args, **kwargs):
            if getattr(statement, 'is_update', False):
                with sessions() as current:
                    if claim_first:
                        claim_key(project_id, current, user)
                    else:
                        remove(current)
            return super().execute(statement, *args, **kwargs)

    with RacingSession(bind=engine) as stale:
        if claim_first:
            assert remove(stale)['archived'] is True
        else:
            with pytest.raises(HTTPException) as exc:
                claim_key(project_id, stale, user)
            assert exc.value.status_code == 409
    with sessions() as session:
        if claim_first:
            key = session.query(CardKey).one()
            assert key.status == 'claimed'
            assert [event['action'] for event in key.history] == ['claim']
            assert session.get(CardKeyBatch, batch_id).status == ('archived' if scope == 'batch' else 'active')
            if scope == 'project':
                assert session.get(CardKeyProject, project_id).archived_at is not None
        else:
            assert session.query(CardKey).count() == 0
            assert session.get(CardKeyBatch, batch_id) is None
    engine.dispose()


def headers(user):
    return {"Authorization": "Bearer " + create_access_token({
        "sub": str(user.id), "username": user.username, "is_super_admin": user.is_super_admin})}


def grant(db, user, *permissions):
    assignment = db.query(UserRole).filter(UserRole.user_id == user.id).first()
    if assignment:
        role_id = assignment.role_id
    else:
        role = Role(name=f'card-key-{user.username}', data_scope='self')
        db.add(role)
        db.flush()
        role_id = role.id
        db.add(UserRole(user_id=user.id, role_id=role_id))
    for permission in permissions:
        db.add(RolePermission(role_id=role_id, permission=permission))
    db.commit()


def project(client, admin, members):
    response = client.post('/api/card-keys', headers=headers(admin), json={
        'name': ' 团队任务 ', 'description': '一行一份', 'members': members})
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_totp_standard_vector_and_invalid_secrets(monkeypatch):
    monkeypatch.setattr('app.api.card_keys.time.time', lambda: 59)
    assert _totp_code('GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ') == ('287082', 1)
    for secret in (None, '', '---', 'invalid!'):
        assert _totp_code(secret) == (None, None)


def test_claimed_email_totp_access(client, db, super_admin, normal_user, monkeypatch):
    grant(db, normal_user, 'card_key:view')
    project_id = project(client, super_admin, ['__all__'])
    db.query(CardKeyProject).filter_by(id=project_id).update({'target_platform': 'TikTok'})
    email = EmailAccount(email='totp@gmail.com', claimed_by=normal_user.username,
                         claimed_platform='TikTok', totp_secret='GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ')
    db.add(email)
    db.commit()
    monkeypatch.setattr('app.api.card_keys.time.time', lambda: 59)
    path = f'/api/card-keys/{project_id}/email/totp'
    result = client.get(path, headers=headers(normal_user))
    assert result.status_code == 200, result.text
    assert result.json() == {'code': '287082', 'remaining': 1}
    assert result.headers['cache-control'] == 'no-store'
    assert client.get(path, headers=headers(super_admin)).status_code == 404
    email.totp_secret = 'invalid!'
    db.commit()
    assert client.get(path, headers=headers(normal_user)).status_code == 422


def test_project_email_claim_complete_and_reuse(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view', 'op_account:create')
    response = client.post('/api/card-keys', headers=headers(super_admin), json={
        'name': '邮箱注册', 'members': [normal_user.username], 'target_platform': 'TikTok'})
    assert response.status_code == 201
    project_id = response.json()['id']
    db.add_all([
        EmailAccount(email='registered@gmail.com', platform_tags='["tiktok"]'),
        EmailAccount(email='locked@gmail.com', management_status='锁定'),
        EmailAccount(email='available@gmail.com', password='secret', totp_secret='TESTKEY', allow_card_key_claim=True),
    ])
    db.commit()
    path = f'/api/card-keys/{project_id}/email'
    member_headers = headers(normal_user)
    claimed = client.post(path + '/claim', headers=member_headers)
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()['email'] == 'available@gmail.com'
    assert claimed.json()['password'] == 'secret'
    assert client.post(path + '/claim', headers=member_headers).json()['id'] == claimed.json()['id']
    assert client.get(path, headers=member_headers).json()['id'] == claimed.json()['id']
    assert client.post(path + '/claim', headers=headers(super_admin)).status_code == 409
    assert client.post(path + '/complete', headers=member_headers, json={'platform': 'wrong'}).status_code == 422
    assert client.post(path + '/complete', headers=member_headers, json={'platform': ' '}).status_code == 422
    result = client.post(path + '/complete', headers=member_headers, json={
        'platform': 'TikTok', 'account': '@created-user', 'password': 'account-password'})
    assert result.status_code == 200, result.text
    assert result.json()['platform_tags'] == ['TikTok']
    assert result.json()['claimed_by'] is None
    account = db.get(OpAccount, result.json()['op_account_id'])
    assert account.platform == 'tiktok'
    assert account.account == 'created-user'
    assert account.password == 'account-password'
    assert account.email == 'available@gmail.com'
    assert account.operator == normal_user.username
    assert db.query(EmailAccountRelation).filter_by(email_id=claimed.json()['id'], op_account_id=account.id).count() == 1
    assert db.query(CardKeyEmailUsage).filter_by(project_id=project_id, username=normal_user.username).count() == 1
    stats = client.get('/api/card-keys', headers=member_headers).json()[0]
    assert stats['emails_completed'] == 1
    assert stats['member_stats'][0]['emails_completed'] == 1
    assert client.get(path, headers=member_headers).json() is None
    assert client.post(path + '/claim', headers=member_headers).status_code == 409
    filtered = client.get('/api/emails?platform=tiktok', headers=headers(super_admin)).json()
    assert filtered['total'] == 2
    completed_email = next(item for item in filtered['items'] if item['email'] == 'available@gmail.com')
    assert completed_email['operator'] == normal_user.username
    assert completed_email['platform_tags'] == ['TikTok']
    assert completed_email['platform_registrants'] == {'TikTok': normal_user.username}
    db.query(EmailAccount).filter_by(email='registered@gmail.com').update({'management_status': '锁定'})
    db.commit()
    changed = client.put(f'/api/card-keys/{project_id}', headers=headers(super_admin), json={
        'name': '邮箱注册', 'members': [normal_user.username], 'target_platform': 'Instagram'})
    assert changed.status_code == 200
    reused = client.post(path + '/claim', headers=member_headers)
    assert reused.status_code == 200
    assert reused.json()['id'] == claimed.json()['id']
    assert client.post(path + '/release', headers=member_headers).status_code == 200
    assert client.get(path, headers=member_headers).json() is None
    db.expire_all()
    assert db.query(EmailAccount).filter_by(email='available@gmail.com').one().platform_tags == '["TikTok"]'


def test_project_email_claim_ignores_legacy_gmail_check_columns(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view')
    response = client.post('/api/card-keys', headers=headers(super_admin), json={
        'name': '领取不依赖历史检测', 'members': [normal_user.username], 'target_platform': 'TikTok'})
    project_id = response.json()['id']
    db.add(EmailAccount(email='legacy-blocked@gmail.com', gmail_check_status='封禁', allow_card_key_claim=True))
    db.commit()
    result = client.post(f'/api/card-keys/{project_id}/email/claim', headers=headers(normal_user))
    assert result.status_code == 200, result.text
    assert result.json()['email'] == 'legacy-blocked@gmail.com'


def test_project_email_claim_failure_discards_email_with_remark(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view')
    project_id = project(client, super_admin, [normal_user.username])
    db.query(CardKeyProject).filter_by(id=project_id).update({'target_platform': 'TikTok'})
    db.add(EmailAccount(email='failed-registration@gmail.com', password='secret', allow_card_key_claim=True))
    db.commit()
    headers_ = headers(normal_user)
    path = f'/api/card-keys/{project_id}/email'
    claimed = client.post(path + '/claim', headers=headers_)
    assert claimed.status_code == 200

    failed = client.post(path + '/fail', headers=headers_, json={'remark': '收不到注册验证码', 'screenshots': [failure_screenshot()]})
    assert failed.status_code == 200, failed.text
    assert failed.json()['management_status'] == '废弃'
    assert failed.json()['remark'] == '收不到注册验证码'
    assert client.get(path, headers=headers_).json() is None
    assert client.post(path + '/claim', headers=headers_).status_code == 409
    email = db.query(EmailAccount).filter_by(email='failed-registration@gmail.com').one()
    assert email.management_status == '废弃'
    assert email.claimed_by is None
    assert email.claimed_platform is None
    assert email.remark == '收不到注册验证码'


def test_project_email_claim_failure_requires_screenshot(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view')
    project_id = project(client, super_admin, [normal_user.username])
    db.query(CardKeyProject).filter_by(id=project_id).update({'target_platform': 'TikTok'})
    db.add(EmailAccount(email='blank-failure@gmail.com', allow_card_key_claim=True))
    db.commit()
    path = f'/api/card-keys/{project_id}/email'
    headers_ = headers(normal_user)
    assert client.post(path + '/claim', headers=headers_).status_code == 200
    response = client.post(path + '/fail', headers=headers_, json={'remark': '没有截图的反馈'})
    assert response.status_code == 422
    email = db.query(EmailAccount).filter_by(email='blank-failure@gmail.com').one()
    assert email.management_status == '闲置'
    assert email.claimed_by == normal_user.username


def test_stale_email_failure_cannot_discard_new_claim(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'stale-email-failure.db'}", connect_args={'timeout': 15})
    CardKeyProject.__table__.create(engine)
    EmailAccount.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    user = User(username='alice', is_super_admin=True)
    with sessions() as session:
        project_row = CardKeyProject(name='邮箱竞态', target_platform='TikTok', member_usernames='alice', created_by='root')
        email = EmailAccount(email='stale-failure@gmail.com', claimed_by='alice',
                             claimed_platform='TikTok')
        session.add_all([project_row, email])
        session.commit()
        project_id, email_id = project_row.id, email.id

    class StaleSession(Session):
        def execute(self, statement, *args, **kwargs):
            if getattr(statement, 'is_update', False):
                with sessions() as current:
                    current.query(EmailAccount).filter_by(id=email_id).update(
                        {'claimed_by': 'bob', 'claimed_at': datetime.utcnow()})
                    current.commit()
            return super().execute(statement, *args, **kwargs)

    with StaleSession(bind=engine) as stale:
        try:
            fail_email(project_id, EmailFailureBody.model_validate({'remark': '旧请求', 'screenshots': [failure_screenshot()]}), stale, user)
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError('A stale failure must not overwrite a newer claim')
    with sessions() as session:
        email = session.get(EmailAccount, email_id)
        assert email.management_status == '闲置'
        assert email.claimed_by == 'bob'
    engine.dispose()


def test_card_key_search_and_invalid_after_sales_note(client, db, super_admin):
    project_id = project(client, super_admin, ['__all__'])
    base = f'/api/card-keys/{project_id}'
    client.post(base + '/import', headers=headers(super_admin), json={'content': 'supplier-order-abc\nother-key'})
    found = client.get(base + '/keys?keyword=ABC', headers=headers(super_admin))
    assert found.status_code == 200
    assert found.json()['total'] == 1
    assert found.json()['items'][0]['content'] == 'supplier-order-abc'
    invalid = client.post(base + f"/keys/{found.json()['items'][0]['id']}/invalid", headers=headers(super_admin), json={'remark': '兑换失败，已提交上游售后', 'screenshots': [failure_screenshot()]})
    assert invalid.status_code == 200, invalid.text
    assert invalid.json()['status'] == 'invalid'
    assert invalid.json()['remark'] == '兑换失败，已提交上游售后'
    assert invalid.json()['history'][-1]['action'] == 'invalid'
    assert client.get(base + '/keys?status=available', headers=headers(super_admin)).json()['total'] == 1
    assert client.get(base + '/keys?status=invalid', headers=headers(super_admin)).json()['total'] == 1


def test_email_platform_tags_create_and_update(client, super_admin):
    auth = headers(super_admin)
    response = client.post('/api/emails', headers=auth, json={
        'email': 'tags@gmail.com', 'purchase_channel': '供应商', 'purchase_price': 0,
        'platform_tags': [' TikTok ', 'TikTok', 'Instagram']})
    assert response.status_code == 200, response.text
    assert response.json()['platform_tags'] == ['TikTok', 'Instagram']
    email_id = response.json()['id']
    response = client.put(f'/api/emails/{email_id}', headers=auth, json={'platform_tags': ['YouTube']})
    assert response.status_code == 200
    assert response.json()['platform_tags'] == ['YouTube']


def test_import_counts_deduplication_and_encryption(client, db, super_admin):
    project_id = project(client, super_admin, ['root'])
    path = f'/api/card-keys/{project_id}/import'
    result = client.post(path, headers=headers(super_admin), json={'content': ' key-A \n\nhttps://example.test/key-B\nkey-A\nkey-C'}).json()
    assert result['added'] == 3 and result['duplicates'] == 1
    assert result['batch']['total'] == 3
    assert client.post(path, headers=headers(super_admin), json={'content': 'key-A'}).json()['duplicates'] == 1
    another = project(client, super_admin, ['root'])
    assert client.post(f'/api/card-keys/{another}/import', headers=headers(super_admin), json={'content': 'key-A'}).json()['duplicates'] == 1
    stored = db.execute(text('SELECT content FROM card_keys ORDER BY id')).scalars().all()
    assert all(value not in ['key-A', 'key-C', 'https://example.test/key-B'] for value in stored)
    stats = client.get('/api/card-keys', headers=headers(super_admin)).json()
    selected = next(value for value in stats if value['id'] == project_id)
    assert selected['available'] == 3 and selected['total'] == 3
    assert client.post(path, headers=headers(super_admin), json={'content': ' \n '}).status_code == 422


def test_import_operation_log_does_not_store_card_key_content(client, db, super_admin):
    from app.models.team import OperationLog

    project_id = project(client, super_admin, ['root'])
    secret = 'sensitive-card-key-should-not-be-logged'
    response = client.post(f'/api/card-keys/{project_id}/import', headers=headers(super_admin),
                           json={'content': secret})
    assert response.status_code == 200
    logs = db.query(OperationLog).filter(OperationLog.module == '卡密管理').all()
    assert any(log.action == 'IMPORT' and log.result == 'success' for log in logs)
    assert all(secret not in f'{log.summary} {log.error}' for log in logs)


def test_claim_recovery_consumption_permissions_and_archive(client, db, super_admin, normal_user, other_user):
    grant(db, normal_user, 'card_key:view')
    admin_headers, member_headers, outsider_headers = headers(super_admin), headers(normal_user), headers(other_user)
    project_id = project(client, super_admin, ['alice'])
    base = f'/api/card-keys/{project_id}'
    client.post(base + '/import', headers=admin_headers, json={'content': 'one\ntwo'})
    assert client.get(base + '/keys', headers=member_headers).json()['items'] == []
    assert client.get('/api/card-keys', headers=outsider_headers).status_code == 403
    assert client.post(base + '/import', headers=member_headers, json={'content': 'three'}).status_code == 403
    claimed = client.post(base + '/claim', headers=member_headers).json()
    assert claimed['content'] == 'one'
    assert claimed['claimed_at'].endswith('Z')
    assert client.post(base + '/claim', headers=member_headers).json()['id'] == claimed['id']
    assert db.query(CardKey).filter(CardKey.status == 'claimed').count() == 1
    restored = client.get(base + '/keys?mine=true&status=claimed', headers=member_headers).json()
    assert restored['items'][0]['content'] == 'one'
    endpoint = base + f"/keys/{claimed['id']}/consume"
    assert client.post(endpoint, headers=member_headers).status_code == 200
    assert client.post(endpoint, headers=member_headers).status_code == 200
    assert client.post(base + '/claim', headers=member_headers).json()['content'] == 'two'
    client.put(base, headers=admin_headers, json={'name': '团队任务', 'members': ['root'], 'is_active': False})
    assert client.post(base + '/claim', headers=member_headers).status_code == 403
    assert client.get(base + '/keys', headers=member_headers).json()['total'] == 2
    assert client.post(base + '/import', headers=admin_headers, json={'content': 'three'}).status_code == 409
    assert client.post(base + '/claim', headers=admin_headers).status_code == 409
    own = client.get(base + '/keys?status=claimed', headers=member_headers).json()['items'][0]
    assert client.post(base + f"/keys/{own['id']}/consume", headers=member_headers).status_code == 200
    assert client.get(base + '/keys?mine=true&status=claimed', headers=member_headers).json()['total'] == 0
    assert client.get('/api/card-keys', headers=member_headers).json()[0]['can_claim'] is False


def test_assignment_isolation_manager_and_pagination(client, db, super_admin, normal_user, other_user):
    grant(db, normal_user, 'card_key:view', 'card_key:manage')
    project_id = project(client, super_admin, ['bob'])
    base = f'/api/card-keys/{project_id}'
    client.post(base + '/import', headers=headers(super_admin), json={'content': 'first\nsecond\nthird'})
    response = client.get(base + '/keys?page=2&page_size=1', headers=headers(normal_user)).json()
    assert response['total'] == 3 and response['items'][0]['content'] == 'second'
    assert client.post(base + '/claim', headers=headers(normal_user)).status_code == 200
    db.query(RolePermission).filter(RolePermission.permission == 'card_key:manage').delete()
    db.commit()
    hidden = project(client, super_admin, ['bob'])
    assert client.get(f'/api/card-keys/{hidden}/keys', headers=headers(normal_user)).status_code == 403
    assert client.post(f'/api/card-keys/{hidden}/claim', headers=headers(normal_user)).status_code == 403
    assert client.post('/api/card-keys', headers=headers(super_admin), json={'name': ' ', 'members': ['root']}).status_code == 422
    assert client.post('/api/card-keys', headers=headers(super_admin), json={'name': 'name', 'members': []}).status_code == 422


def test_all_members_assignment(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view')
    response = client.post('/api/card-keys', headers=headers(super_admin), json={
        'name': '全员任务', 'members': ['__all__']})
    assert response.status_code == 201
    assert response.json()['members'] == ['__all__']
    assert client.get('/api/card-keys', headers=headers(normal_user)).json()[0]['can_claim'] is True
    project_id = response.json()['id']
    client.post(f'/api/card-keys/{project_id}/import', headers=headers(super_admin), json={'content': 'all-key'})
    assert client.post(f'/api/card-keys/{project_id}/claim', headers=headers(normal_user)).json()['content'] == 'all-key'


def test_role_create_update_accept_new_permissions(client, db, super_admin, normal_user):
    permissions = ['card_key:view', 'card_key:manage', 'work_item:view', 'work_item:manage']
    admin_headers = headers(super_admin)
    response = client.post('/api/team/role', headers=admin_headers, json={
        'name': '新模块权限', 'permissions': permissions})
    assert response.status_code == 201, response.text
    role_id = response.json()['id']
    response = client.put(f'/api/team/role/{role_id}', headers=admin_headers, json={
        'permissions': permissions})
    assert response.status_code == 200, response.text
    saved = next(role for role in client.get('/api/team/role', headers=admin_headers).json() if role['id'] == role_id)
    assert set(saved['permissions']) == set(permissions)
    assert client.put(f'/api/team/role/{role_id}', headers=admin_headers, json={
        'permissions': ['card_key:manage', 'work_item:manage']}).status_code == 200
    db.add(UserRole(user_id=normal_user.id, role_id=role_id))
    db.commit()
    member_headers = headers(normal_user)
    assert client.get('/api/card-keys', headers=member_headers).status_code == 200
    assert client.get('/api/card-keys/members', headers=member_headers).status_code == 200
    assert client.get('/api/work-items', headers=member_headers).status_code == 200
    assert client.post(f'/api/team/role', headers=admin_headers, json={
        'name': '非法权限', 'permissions': ['card_key:fake']}).status_code == 422
    assert client.put(f'/api/team/role/{role_id}', headers=admin_headers, json={
        'permissions': ['work_item:fake']}).status_code == 422
    saved = next(role for role in client.get('/api/team/role', headers=admin_headers).json() if role['id'] == role_id)
    assert set(saved['permissions']) == {'card_key:manage', 'work_item:manage'}
    assert client.get('/api/card-keys', headers=member_headers).status_code == 200
    assert client.get('/api/work-items', headers=member_headers).status_code == 200
    assert client.put(f'/api/team/role/{role_id}', headers=admin_headers, json={
        'permissions': []}).status_code == 200
    assert client.get('/api/card-keys', headers=member_headers).status_code == 403
    assert client.get('/api/work-items', headers=member_headers).status_code == 403


def test_view_permission_cannot_manage_card_keys_or_work_items(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view', 'work_item:view')
    member_headers = headers(normal_user)
    assert client.post('/api/card-keys', headers=member_headers, json={'name': '越权项目'}).status_code == 403
    assert client.post('/api/work-items', headers=member_headers, json={'title': '越权备忘'}).status_code == 403
    project_id = project(client, super_admin, ['alice'])
    assert client.put(f'/api/card-keys/{project_id}', headers=member_headers, json={
        'name': '越权修改', 'members': ['alice'], 'is_active': False}).status_code == 403
    assert client.post(f'/api/card-keys/{project_id}/import', headers=member_headers,
                       json={'content': 'unauthorized-key'}).status_code == 403
    created = client.post('/api/work-items', headers=headers(super_admin), json={'title': '保留备忘'})
    assert created.status_code == 201
    item_id = created.json()['id']
    assert client.put(f'/api/work-items/{item_id}', headers=member_headers,
                      json={'title': '越权修改', 'is_done': True}).status_code == 403
    assert client.delete(f'/api/work-items/{item_id}', headers=member_headers).status_code == 403
    assert db.get(CardKeyProject, project_id).is_active is True
    assert db.query(CardKey).filter(CardKey.project_id == project_id).count() == 0
    items = client.get('/api/work-items', headers=member_headers).json()['items']
    assert next(item for item in items if item['id'] == item_id)['title'] == '保留备忘'


def test_release_returns_unused_key_and_preserves_history(client, db, super_admin, normal_user, other_user):
    grant(db, normal_user, 'card_key:view')
    grant(db, other_user, 'card_key:view')
    project_id = project(client, super_admin, ['alice', 'bob'])
    base = f'/api/card-keys/{project_id}'
    client.post(base + '/import', headers=headers(super_admin), json={'content': 'return-me'})
    claimed = client.post(base + '/claim', headers=headers(normal_user)).json()
    endpoint = base + f"/keys/{claimed['id']}"
    assert client.post(endpoint + '/release', headers=headers(normal_user)).json()['status'] == 'available'
    assert client.get(base + '/keys?status=available', headers=headers(super_admin)).json()['total'] == 1
    assert client.post(base + '/claim', headers=headers(other_user)).json()['content'] == 'return-me'
    history = db.get(CardKey, claimed['id']).history
    assert [event['action'] for event in history] == ['claim', 'release', 'claim']
    assert client.post(endpoint + '/release', headers=headers(normal_user)).status_code == 403
    assert client.post(endpoint + '/consume', headers=headers(other_user)).status_code == 200
    assert client.post(endpoint + '/release', headers=headers(other_user)).status_code == 409


def test_removed_member_can_return_claimed_key_but_cannot_claim_again(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view')
    admin_headers = headers(super_admin)
    member_headers = headers(normal_user)
    project_id = project(client, super_admin, ['alice'])
    base = f'/api/card-keys/{project_id}'
    client.post(base + '/import', headers=admin_headers, json={'content': 'return-after-removal'})
    response = client.post(base + '/claim', headers=member_headers)
    assert response.status_code == 200, response.text
    claimed = response.json()

    assert client.put(base, headers=admin_headers, json={
        'name': '已调整成员', 'members': ['root'], 'is_active': True,
    }).status_code == 200
    assert client.post(base + '/claim', headers=member_headers).status_code == 403
    assert client.post(base + f"/keys/{claimed['id']}/release", headers=member_headers).json()['status'] == 'available'
    assert client.get(base + '/keys?mine=true&status=claimed', headers=member_headers).status_code == 403
    returned = client.get(base + '/keys?status=available', headers=admin_headers).json()
    assert returned['total'] == 1
    assert [event['action'] for event in returned['items'][0]['history']] == ['claim', 'release']


def test_release_and_consume_race_has_one_winner(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'returns.db'}", connect_args={'check_same_thread': False, 'timeout': 15})
    CardKeyProject.__table__.create(engine)
    CardKeyBatch.__table__.create(engine)
    CardKey.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    user = User(username='root', is_super_admin=True)
    with sessions() as session:
        item = CardKeyProject(name='归还竞态', member_usernames='root', created_by='root')
        session.add(item)
        session.commit()
        project_id = item.id
        import_keys(project_id, ImportBody(content='race-key'), session, user)
        key_id = claim_key(project_id, session, user)['id']
    barrier = Barrier(2)

    class RacingSession(Session):
        def execute(self, statement, *args, **kwargs):
            if getattr(statement, 'is_update', False):
                barrier.wait(timeout=10)
            return super().execute(statement, *args, **kwargs)

    racing_sessions = sessionmaker(bind=engine, class_=RacingSession)

    def transition(action):
        with racing_sessions() as session:
            try:
                action(project_id, key_id, session, user)
                return 200
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(transition, [release_key, consume_key]))
    assert sorted(results) == [200, 409]
    with sessions() as session:
        key = session.get(CardKey, key_id)
        assert key.status in ('available', 'consumed')
        assert key.pending_owner is None
        assert [event['action'] for event in key.history] in (['claim', 'release'], ['claim', 'consume'])
    engine.dispose()


def test_stale_claim_cannot_erase_release_history(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'stale-claim.db'}", connect_args={'timeout': 15})
    CardKeyProject.__table__.create(engine)
    CardKeyBatch.__table__.create(engine)
    CardKey.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    user = User(username='root', is_super_admin=True)
    with sessions() as session:
        item = CardKeyProject(name='旧请求', member_usernames='root', created_by='root')
        session.add(item)
        session.commit()
        project_id = item.id
        import_keys(project_id, ImportBody(content='stale-key'), session, user)

    class StaleSession(Session):
        def execute(self, statement, *args, **kwargs):
            if getattr(statement, 'is_update', False):
                with sessions() as current:
                    claimed = claim_key(project_id, current, user)
                    release_key(project_id, claimed['id'], current, user)
            return super().execute(statement, *args, **kwargs)

    with StaleSession(bind=engine) as stale:
        try:
            claim_key(project_id, stale, user)
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError('A stale claim must not overwrite intervening history')
    with sessions() as session:
        key = session.query(CardKey).one()
        assert key.status == 'available'
        assert [event['action'] for event in key.history] == ['claim', 'release']
        recovered = claim_key(project_id, session, user)
        assert [event['action'] for event in recovered['history']] == ['claim', 'release', 'claim']
    engine.dispose()


def test_concurrent_claims_and_imports(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'claims.db'}", connect_args={'check_same_thread': False, 'timeout': 15})
    CardKeyProject.__table__.create(engine)
    CardKeyBatch.__table__.create(engine)
    CardKey.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        item = CardKeyProject(name='并发测试', member_usernames='first,second', created_by='root')
        session.add(item)
        session.commit()
        project_id = item.id
        import_keys(project_id, ImportBody(content='single'), session, User(username='root', is_super_admin=True))
    barrier = Barrier(2)

    def claim(username):
        with sessions() as session:
            barrier.wait()
            try:
                return claim_key(project_id, session, User(username=username, is_super_admin=True))['id']
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(claim, ['first', 'second']))
    assert sum(value == 409 for value in results) == 1
    with sessions() as session:
        assert session.query(CardKey).filter(CardKey.status == 'claimed').count() == 1
        import_keys(project_id, ImportBody(content='same-user-one\nsame-user-two'), session, User(username='root', is_super_admin=True))
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(claim, ['same', 'same']))
    with sessions() as session:
        assert session.query(CardKey).filter(CardKey.pending_owner == 'same').count() == 1
        pending = session.query(CardKey).filter(CardKey.pending_owner == 'same').one()
        assert all(value in (409, pending.id) for value in results)
    barrier = Barrier(2)

    def concurrent_import(_):
        with sessions() as session:
            barrier.wait()
            return import_keys(project_id, ImportBody(content='duplicate'), session, User(username='root', is_super_admin=True))

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(concurrent_import, range(2)))
    assert sum(value['added'] for value in results) == 1
    assert sum(value['duplicates'] for value in results) == 1
    engine.dispose()


def test_card_key_email_claim_requires_switch_and_updates_stats(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view')
    item = CardKeyProject(name='邮箱开关', target_platform='TikTok', member_usernames='alice', created_by='root')
    db.add(item)
    db.flush()
    emails = [
        EmailAccount(email='switch-disabled@gmail.com', allow_card_key_claim=False),
        EmailAccount(email='switch-eligible@gmail.com', allow_card_key_claim=True),
        EmailAccount(email='switch-tagged@gmail.com', allow_card_key_claim=True, platform_tags='["TikTok"]'),
        EmailAccount(email='switch-used@gmail.com', allow_card_key_claim=True, management_status='使用中'),
        EmailAccount(email='switch-claimed@gmail.com', allow_card_key_claim=True, claimed_by='bob', claimed_platform='TikTok'),
    ]
    db.add_all(emails)
    db.commit()
    base = f'/api/card-keys/{item.id}'
    stats = next(project for project in client.get('/api/card-keys', headers=headers(super_admin)).json()
                 if project['id'] == item.id)
    assert stats['email_available'] == 1
    assert stats['email_claimed'] == 1
    claimed = client.post(base + '/email/claim', headers=headers(normal_user))
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()['email'] == 'switch-eligible@gmail.com'
    assert client.post(base + '/email/release', headers=headers(normal_user)).status_code == 200
    admin_headers = headers(super_admin)
    assert client.post('/api/emails/batch-claim-availability', headers=admin_headers,
                       json={'email_ids': [emails[1].id], 'allow_card_key_claim': False}).status_code == 200
    assert client.post('/api/emails/batch-claim-availability', headers=admin_headers,
                       json={'email_ids': [emails[0].id], 'allow_card_key_claim': True}).status_code == 200
    stats = next(project for project in client.get('/api/card-keys', headers=headers(super_admin)).json()
                 if project['id'] == item.id)
    assert stats['email_available'] == 1
    claimed = client.post(base + '/email/claim', headers=headers(normal_user))
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()['email'] == 'switch-disabled@gmail.com'
    client.post(base + '/email/release', headers=headers(normal_user))
    assert client.post('/api/emails/batch-claim-availability', headers=admin_headers,
                       json={'email_ids': [emails[0].id], 'allow_card_key_claim': False}).status_code == 200
    assert client.post(base + '/email/claim', headers=headers(normal_user)).status_code == 409


def test_project_delete_hard_deletes_clean_project_despite_unrelated_claimed_email(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view')
    item = CardKeyProject(name='干净项目', target_platform='TikTok', member_usernames='alice', created_by='root')
    db.add(item)
    db.flush()
    project_id = item.id
    db.add(EmailAccount(email='unrelated-claimed@gmail.com', claimed_by='bob', claimed_platform='TikTok'))
    db.commit()
    base = f'/api/card-keys/{project_id}'
    client.post(base + '/import', headers=headers(super_admin), json={'content': 'clean-key'})
    assert client.delete(base, headers=headers(normal_user)).status_code == 403
    result = client.delete(base, headers=headers(super_admin)).json()
    assert result == {'deleted': True, 'archived': False, 'id': project_id}
    db.expire_all()
    assert db.query(CardKeyProject).filter_by(id=project_id).first() is None
    assert db.query(CardKey).filter_by(project_id=project_id).count() == 0
    assert db.query(CardKeyBatch).filter_by(project_id=project_id).count() == 0


def test_project_delete_archives_history_and_preserves_records(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view')
    item = CardKeyProject(name='历史项目', target_platform='TikTok', member_usernames='alice', created_by='root')
    db.add(item)
    db.commit()
    base = f'/api/card-keys/{item.id}'
    client.post(base + '/import', headers=headers(super_admin), json={'content': 'history-key'})
    claimed = client.post(base + '/claim', headers=headers(normal_user)).json()
    assert client.post(base + f"/keys/{claimed['id']}/release", headers=headers(normal_user)).status_code == 200
    result = client.delete(base, headers=headers(super_admin)).json()
    assert result['deleted'] is False and result['archived'] is True
    db.expire_all()
    archived = db.get(CardKeyProject, item.id)
    assert archived.archived_at is not None and archived.archived_by == 'root' and archived.is_active is False
    assert db.query(CardKey).filter_by(project_id=item.id).count() == 1
    assert db.query(CardKeyBatch).filter_by(project_id=item.id).count() == 1
    assert client.get('/api/card-keys', headers=headers(super_admin)).json() == []
    listed = client.get('/api/card-keys?include_archived=true', headers=headers(super_admin)).json()
    assert listed[0]['archived'] is True and listed[0]['archived_by'] == 'root' and listed[0]['can_claim'] is False
    assert client.post(base + '/import', headers=headers(super_admin), json={'content': 'blocked'}).status_code == 409
    assert client.post(base + '/claim', headers=headers(normal_user)).status_code == 409
    assert client.put(base, headers=headers(super_admin), json={'name': '改名', 'members': ['alice']}).status_code == 409
    assert client.delete(base, headers=headers(super_admin)).json()['archived'] is True


@pytest.mark.parametrize('history_kind', ['usage', 'failure'])
def test_project_delete_archives_email_usage_and_failure_history(client, db, super_admin, history_kind):
    item = CardKeyProject(name=f'历史-{history_kind}', target_platform='TikTok', member_usernames='alice', created_by='root')
    email = EmailAccount(email=f'history-{history_kind}@gmail.com')
    db.add_all([item, email])
    db.flush()
    if history_kind == 'usage':
        db.add(CardKeyEmailUsage(project_id=item.id, email_id=email.id, username='alice', platform='TikTok'))
    else:
        db.add(FailureReport(project_id=item.id, email_id=email.id, kind='email', project_name=item.name,
                             platform='TikTok', username='alice', screenshots='[]'))
    db.commit()
    result = client.delete(f'/api/card-keys/{item.id}', headers=headers(super_admin)).json()
    assert result['deleted'] is False and result['archived'] is True
    db.expire_all()
    assert db.get(CardKeyProject, item.id).archived_at is not None


def test_card_key_email_claim_requires_explicit_admin_switch(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view')
    item = CardKeyProject(name='默认不可领', target_platform='TikTok', member_usernames='alice', created_by='root')
    db.add(item)
    db.flush()
    email = EmailAccount(email='default-disabled@gmail.com')
    db.add(email)
    db.commit()
    assert email.allow_card_key_claim is False
    base = f'/api/card-keys/{item.id}'
    stats = next(project for project in client.get('/api/card-keys', headers=headers(super_admin)).json()
                 if project['id'] == item.id)
    assert stats['email_available'] == 0
    assert client.post(base + '/email/claim', headers=headers(normal_user)).status_code == 409
    assert client.post('/api/emails/batch-claim-availability', headers=headers(super_admin),
                       json={'email_ids': [email.id], 'allow_card_key_claim': True}).status_code == 200
    stats = next(project for project in client.get('/api/card-keys', headers=headers(super_admin)).json()
                 if project['id'] == item.id)
    assert stats['email_available'] == 1
    claimed = client.post(base + '/email/claim', headers=headers(normal_user))
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()['email'] == 'default-disabled@gmail.com'


def test_complete_email_backfills_ck_for_unsupported_platform(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view')
    project = client.post('/api/card-keys', headers=headers(super_admin), json={
        'name': '自定义平台完成', 'members': [normal_user.username], 'target_platform': 'CustomFlow'})
    project_id = project.json()['id']
    email = EmailAccount(email='custom-ck@example.invalid', password='secret', allow_card_key_claim=True)
    db.add(email)
    db.commit()
    email_id = email.id
    member_headers = headers(normal_user)
    assert client.post(f'/api/card-keys/{project_id}/email/claim', headers=member_headers).status_code == 200
    ck = 'Cookie: __Secure-1PSID=fixture-psid; SID=fixture-sid; OSID=fixture-osid'
    response = client.post(f'/api/card-keys/{project_id}/email/complete', headers=member_headers,
                           json={'platform': 'CustomFlow', 'ck': ck})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['ck'] == ck
    assert body['op_account_id'] is None
    assert body['platform_tags'] == ['CustomFlow']
    assert body['claimed_by'] is None
    db.expire_all()
    stored = db.get(EmailAccount, email_id)
    assert stored.ck == ck
    raw = db.execute(text('SELECT ck FROM email_accounts WHERE id=:id'), {'id': email_id}).scalar_one()
    assert raw != ck and ck not in raw


def test_complete_email_backfills_ck_and_creates_op_account(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view', 'op_account:create')
    project = client.post('/api/card-keys', headers=headers(super_admin), json={
        'name': '支持平台完成', 'members': [normal_user.username], 'target_platform': 'TikTok'})
    project_id = project.json()['id']
    email = EmailAccount(email='supported-ck@example.invalid', allow_card_key_claim=True)
    db.add(email)
    db.commit()
    email_id = email.id
    member_headers = headers(normal_user)
    assert client.post(f'/api/card-keys/{project_id}/email/claim', headers=member_headers).status_code == 200
    ck = 'Cookie: __Secure-1PSID=fixture-psid; SID=fixture-sid; OSID=fixture-osid'
    response = client.post(f'/api/card-keys/{project_id}/email/complete', headers=member_headers,
                           json={'platform': 'TikTok', 'account': 'new-tiktok-user',
                                 'password': 'account-password', 'ck': ck})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['ck'] == ck and body['op_account'] == 'new-tiktok-user'
    db.expire_all()
    assert db.get(EmailAccount, email_id).ck == ck
    assert db.query(OpAccount).filter_by(platform='tiktok', account='new-tiktok-user').count() == 1
    assert db.query(EmailAccountRelation).filter_by(email_id=email_id).count() == 1


def test_complete_email_ck_none_preserves_and_empty_clears(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view')
    project = client.post('/api/card-keys', headers=headers(super_admin), json={
        'name': 'CK 保留清空', 'members': [normal_user.username], 'target_platform': 'CustomFlow'})
    project_id = project.json()['id']
    keep = EmailAccount(email='keep-ck@example.invalid', ck='existing-ck', allow_card_key_claim=True)
    clear = EmailAccount(email='clear-ck@example.invalid', ck='clear-me', allow_card_key_claim=True)
    db.add_all([keep, clear])
    db.commit()
    keep_id, clear_id = keep.id, clear.id
    member_headers = headers(normal_user)
    path = f'/api/card-keys/{project_id}/email'
    assert client.post(path + '/claim', headers=member_headers).json()['id'] == keep_id
    preserved = client.post(path + '/complete', headers=member_headers, json={'platform': 'CustomFlow'})
    assert preserved.status_code == 200, preserved.text
    assert preserved.json()['ck'] == 'existing-ck'
    assert client.post(path + '/claim', headers=member_headers).json()['id'] == clear_id
    cleared = client.post(path + '/complete', headers=member_headers, json={'platform': 'CustomFlow', 'ck': ''})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()['ck'] is None
    db.expire_all()
    assert db.get(EmailAccount, keep_id).ck == 'existing-ck'
    assert db.get(EmailAccount, clear_id).ck is None


def test_complete_email_supported_platform_requires_op_account_permission(client, db, super_admin, normal_user):
    grant(db, normal_user, 'card_key:view')
    project = client.post('/api/card-keys', headers=headers(super_admin), json={
        'name': '无建号权限', 'members': [normal_user.username], 'target_platform': 'TikTok'})
    project_id = project.json()['id']
    email = EmailAccount(email='no-account-permission@example.invalid', allow_card_key_claim=True)
    db.add(email)
    db.commit()
    email_id = email.id
    member_headers = headers(normal_user)
    assert client.post(f'/api/card-keys/{project_id}/email/claim', headers=member_headers).status_code == 200
    response = client.post(f'/api/card-keys/{project_id}/email/complete', headers=member_headers,
                           json={'platform': 'TikTok', 'account': 'should-not-create', 'ck': 'fixture-cookie'})
    assert response.status_code == 403
    db.expire_all()
    stored = db.get(EmailAccount, email_id)
    assert stored.claimed_by == normal_user.username and stored.ck is None
    assert db.query(OpAccount).filter_by(account='should-not-create').count() == 0
