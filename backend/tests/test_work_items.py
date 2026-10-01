from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.core.security import create_access_token


def auth_headers(user):
    token = create_access_token({
        "sub": str(user.id),
        "username": user.username,
        "is_super_admin": user.is_super_admin,
    })
    return {"Authorization": f"Bearer {token}"}


def test_memo_crud_and_encryption(client, db, super_admin):
    headers = auth_headers(super_admin)
    data = {"title": " VPS 续费 ", "category": "VPS续费", "content": "ssh 密码:secret123", "reminder_users": ["root"]}
    response = client.post('/api/work-items', json=data, headers=headers)
    assert response.status_code == 201
    item = response.json()
    assert item['title'] == 'VPS 续费'
    assert item['category'] == 'VPS续费'
    assert 'VPS续费' in client.get('/api/work-items/categories', headers=headers).json()
    assert client.get('/api/work-items?category=VPS续费', headers=headers).json()['total'] == 1
    assert client.get('/api/work-items?category=采购渠道', headers=headers).json()['total'] == 0
    assert db.execute(text('SELECT content FROM work_items')).scalar() != data['content']
    assert client.get('/api/work-items?keyword=secret123', headers=headers).json()['total'] == 1
    assert client.put(f"/api/work-items/{item['id']}", json={**data, 'is_done': True}, headers=headers).status_code == 200
    assert client.get('/api/work-items', headers=headers).json()['total'] == 0
    assert client.get('/api/work-items?status=done', headers=headers).json()['total'] == 1
    assert client.delete(f"/api/work-items/{item['id']}", headers=headers).status_code == 204


def test_reminder_summary_and_timezone(client, super_admin, other_user):
    headers = auth_headers(super_admin)
    now = datetime.now(timezone.utc)
    for title, names, delta in [('过期', ['root'], -1), ('即将', ['root'], 1), ('别人的', ['bob'], -1)]:
        response = client.post('/api/work-items', json={
            'title': title, 'reminder_users': names,
            'remind_at': (now + timedelta(days=delta)).astimezone(timezone(timedelta(hours=8))).isoformat(),
        }, headers=headers)
        assert response.status_code == 201
        assert response.json()['remind_at'].endswith('Z')
    summary = client.get('/api/work-items/summary', headers=headers).json()
    assert summary['overdue'] == 1
    assert summary['due_soon'] == 1
    assert summary['pending'] == 2
    assert summary['due'][0]['title'] == '过期'
    assert client.get('/api/work-items?mine=true', headers=headers).json()['total'] == 2


def test_permissions_and_validation(client, super_admin, normal_user):
    assert client.get('/api/work-items', headers=auth_headers(normal_user)).status_code == 403
    headers = auth_headers(super_admin)
    assert client.post('/api/work-items', json={'title': '  '}, headers=headers).status_code == 422
    assert client.post('/api/work-items', json={'title': '任务', 'reminder_users': ['missing']}, headers=headers).status_code == 400
    assert client.get('/api/work-items/members', headers=headers).status_code == 200
    assert client.delete('/api/work-items/999', headers=headers).status_code == 404
    assert client.post('/api/work-items', json={'title': '任务', 'category': '自定义'}, headers=headers).status_code == 422


def test_all_members_reminder(client, db, super_admin, normal_user):
    from app.models.team import RolePermission, UserRole

    role_id = db.query(UserRole).filter(UserRole.user_id == normal_user.id).first().role_id
    db.add(RolePermission(role_id=role_id, permission='work_item:view'))
    db.commit()
    headers = auth_headers(super_admin)
    response = client.post('/api/work-items', json={
        'title': '全员到期提醒', 'reminder_users': ['__all__', 'root'],
        'remind_at': (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    }, headers=headers)
    assert response.status_code == 201
    item = response.json()
    assert item['reminder_users'] == ['__all__']
    assert item['reminder_all'] is True
    member_headers = auth_headers(normal_user)
    assert client.get('/api/work-items?mine=true', headers=member_headers).json()['total'] == 1
    summary = client.get('/api/work-items/summary', headers=member_headers).json()
    assert summary['overdue'] == 1
    assert summary['due'][0]['id'] == item['id']
    assert client.put(f"/api/work-items/{item['id']}", json={
        'title': item['title'], 'reminder_users': ['__all__'], 'is_done': True,
    }, headers=headers).status_code == 200
    assert client.get('/api/work-items/summary', headers=member_headers).json()['due'] == []


def test_admin_manages_categories_without_breaking_used_values(client, super_admin, normal_user):
    admin_headers = auth_headers(super_admin)
    member_headers = auth_headers(normal_user)
    assert client.put('/api/work-items/categories', json={
        'categories': ['采购', '其他'],
    }, headers=member_headers).status_code == 403
    assert client.put('/api/work-items/categories', json={
        'categories': ['采购', '其他'],
    }, headers=admin_headers).status_code == 200
    assert client.get('/api/work-items/categories', headers=admin_headers).json() == ['采购', '其他']
    created = client.post('/api/work-items', json={
        'title': '供应商', 'category': '采购',
    }, headers=admin_headers)
    assert created.status_code == 201
    assert client.put('/api/work-items/categories', json={
        'categories': ['其他'],
    }, headers=admin_headers).status_code == 400
    assert client.put('/api/work-items/categories', json={
        'categories': ['采购', '其他', '采购'],
    }, headers=admin_headers).status_code == 422
