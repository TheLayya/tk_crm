from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.api.card_keys import claim_key, consume_key, release_key, import_keys, ImportBody
from app.api.card_keys import _totp_code
from app.core.security import create_access_token
from app.models.card_key import CardKey, CardKeyProject
from app.models.op_account import EmailAccount
from app.models.team import Role, RolePermission, User, UserRole


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
    grant(db, normal_user, 'card_key:view')
    response = client.post('/api/card-keys', headers=headers(super_admin), json={
        'name': '邮箱注册', 'members': [normal_user.username], 'target_platform': 'TikTok'})
    assert response.status_code == 201
    project_id = response.json()['id']
    db.add_all([
        EmailAccount(email='registered@gmail.com', platform_tags='["tiktok"]'),
        EmailAccount(email='locked@gmail.com', management_status='锁定'),
        EmailAccount(email='available@gmail.com', password='secret', totp_secret='TESTKEY'),
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
    result = client.post(path + '/complete', headers=member_headers, json={'platform': 'TikTok'})
    assert result.status_code == 200, result.text
    assert result.json()['platform_tags'] == ['TikTok']
    assert result.json()['claimed_by'] is None
    assert client.get(path, headers=member_headers).json() is None
    assert client.post(path + '/claim', headers=member_headers).status_code == 409
    filtered = client.get('/api/emails?platform=tiktok', headers=headers(super_admin)).json()
    assert filtered['total'] == 2
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
    assert result == {'added': 3, 'duplicates': 1}
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
