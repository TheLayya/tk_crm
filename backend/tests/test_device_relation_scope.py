from app.models.op_account import OpAccount
from app.models.proxy_node import ProxyNode
from app.models.team import Role, RolePermission, UserRole

from .conftest import auth_headers


def _grant(db, user, *permissions, scope="self"):
    role = Role(name=f"relation-{user.username}", data_scope=scope)
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.add_all(RolePermission(role_id=role.id, permission=permission) for permission in permissions)
    db.commit()


def test_member_can_associate_account_in_own_scope(client, db, normal_user, super_admin):
    _grant(db, normal_user, "device:view", "device:manage", "op_account:view", "proxy_node:view")
    node = ProxyNode(ip="10.99.0.1", port=1080, country="US", status="idle", protocol="socks5", created_by=normal_user.username)
    account = OpAccount(platform="tiktok", account="alice-owned", registrant=normal_user.username)
    db.add_all([node, account])
    db.commit()

    device = client.post(
        "/api/devices",
        json={"name": "Alice phone", "device_type": "phone"},
        headers=auth_headers(normal_user),
    )
    assert device.status_code == 201, device.text
    response = client.put(
        f"/api/devices/{device.json()['id']}/relations",
        json={"account_ids": [account.id], "node_ids": [node.id]},
        headers=auth_headers(normal_user),
    )
    assert response.status_code == 200, response.text
    db.refresh(account)
    assert account.device_id == device.json()["id"]
    assert account.node_id == node.id


def test_member_can_associate_same_department_account_and_device(client, db, normal_user, other_user):
    from app.models.team import Department

    department = Department(name="运营部")
    db.add(department)
    db.flush()
    normal_user.department_id = department.id
    other_user.department_id = department.id
    db.commit()
    _grant(db, normal_user, "device:view", "device:manage", "op_account:view", "proxy_node:view", "proxy_node:manage", scope="dept")
    db.add(OpAccount(platform="tiktok", account="dept-owned", registrant=other_user.username))
    db.commit()
    account = db.query(OpAccount).filter_by(account="dept-owned").one()
    node = ProxyNode(ip="10.99.0.2", port=1080, country="US", status="idle", protocol="socks5", created_by=other_user.username)
    db.add(node)
    db.commit()
    device = client.post(
        "/api/devices", json={"name": "Dept phone", "device_type": "phone"}, headers=auth_headers(normal_user)
    )
    assert device.status_code == 201, device.text
    response = client.put(
        f"/api/proxy-nodes/{node.id}/relation",
        json={"device_id": device.json()["id"], "account_id": account.id},
        headers=auth_headers(normal_user),
    )
    assert response.status_code == 200, response.text
