from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.device import Device
from app.models.op_account import OpAccount
from app.models.proxy_node import ProxyNode
from app.models.team import Role, RolePermission, User, UserRole
from .conftest import auth_headers


@pytest.fixture(autouse=True)
def clean_overview_accounts(db):
    db.query(OpAccount).delete()
    db.commit()
    yield
    db.query(OpAccount).delete()
    db.commit()


def test_overview_empty_and_auth(client, super_admin):
    assert client.get("/api/overview").status_code == 401
    response = client.get("/api/overview", headers=auth_headers(super_admin))
    assert response.status_code == 200
    data = response.json()
    assert data["assets"]["devices"]["total"] == 0
    assert float(data["finance"]["entered_cost"]) == 0
    assert data["device_rows"] == []


def test_shared_node_count_and_money(client, db, super_admin):
    node = ProxyNode(ip="1.2.3.4", port=1080, purchase_price=Decimal("0.20"), purchase_channel="same", expire_date=date.today() - timedelta(days=1), password="secret")
    db.add(node)
    db.flush()
    devices = [Device(name=name, device_type="phone", owner_id=super_admin.id, node_ids=[node.id]) for name in ["one", "two"]]
    db.add_all(devices)
    db.flush()
    db.add(OpAccount(platform="tiktok", account="test", device_id=devices[0].id, node_id=node.id, purchase_price=Decimal("0.10"), purchase_channel="same", password="private"))
    db.commit()
    data = client.get("/api/overview", headers=auth_headers(super_admin)).json()
    assert data["assets"]["devices"]["phone"] == 2
    assert data["assets"]["nodes"]["total"] == 1
    assert float(data["finance"]["entered_cost"]) == 0.30
    assert len(data["finance"]["cost_by_channel"]) == 1
    assert data["finance"]["cost_by_channel"][0]["count"] == 2
    assert data["quality"]["expired_nodes"] == 1
    assert data["quality"]["unbound_devices"] == 0
    assert "secret" not in str(data) and "private" not in str(data)


def test_scope_uses_username_not_real_name(client, db, super_admin):
    user = User(username="worker", real_name="Display", password_hash="unused", is_active=True)
    db.add(user)
    db.flush()
    role = Role(name="overview", data_scope="self")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.add_all([RolePermission(role_id=role.id, permission=perm) for perm in ["device:view", "op_account:view", "proxy_node:view"]])
    db.add_all([Device(name="mine", device_type="phone", owner_id=user.id), Device(name="hidden", device_type="phone", owner_id=super_admin.id)])
    db.add_all([OpAccount(platform="tiktok", account="mine", operator="worker"), OpAccount(platform="tiktok", account="hidden", operator=super_admin.username)])
    db.commit()
    data = client.get("/api/overview", headers=auth_headers(user)).json()
    assert [device["name"] for device in data["device_rows"]] == ["mine"]
    assert data["assets"]["accounts"]["total"] == 1
    db.query(RolePermission).filter(RolePermission.permission == "proxy_node:view").delete()
    db.commit()
    assert client.get("/api/overview", headers=auth_headers(user)).status_code == 403


def test_finance_dates_are_independent_and_inclusive(client, db, super_admin):
    db.add_all([
        OpAccount(platform="tiktok", account="dated", purchase_price=10, purchase_date=date(2026, 10, 1), sale_price=20, sale_date=date(2026, 10, 2), purchase_channel="dated", sale_customer="buyer"),
        OpAccount(platform="tiktok", account="undated", purchase_price=30, sale_price=40),
        ProxyNode(ip="1.2.3.4", port=1080, purchase_price=5, purchase_date=date(2026, 10, 2), sale_price=7),
    ])
    db.commit()
    headers = auth_headers(super_admin)
    first = client.get("/api/overview", params={"date_from": "2026-10-01", "date_to": "2026-10-01"}, headers=headers).json()
    assert first["assets"]["accounts"]["total"] == 2
    assert float(first["finance"]["entered_cost"]) == 10
    assert float(first["finance"]["entered_revenue"]) == 0
    assert first["finance"]["cost_by_channel"][0]["count"] == 1
    assert first["finance"]["missing_cost_dates"] == 1
    assert first["finance"]["missing_revenue_dates"] == 2
    second = client.get("/api/overview", params={"date_from": "2026-10-02", "date_to": "2026-10-02"}, headers=headers).json()
    assert float(second["finance"]["entered_cost"]) == 5
    assert float(second["finance"]["entered_revenue"]) == 20
    assert second["finance"]["revenue_by_customer"][0]["name"] == "buyer"
    all_dates = client.get("/api/overview", headers=headers).json()
    assert float(all_dates["finance"]["entered_cost"]) == 45
    assert float(all_dates["finance"]["entered_revenue"]) == 67
    assert client.get("/api/overview", params={"date_from": "2026-10-02", "date_to": "2026-10-01"}, headers=headers).status_code == 422
