"""Whole-result table queries preserve asset scope and count before pagination."""
import hashlib
import json
from datetime import datetime

import pytest

from app.models.card_key import CardKey, CardKeyProject
from app.models.device import Device, DeviceLog
from app.models.op_account import EmailAccount, EmailAccountRelation, OpAccount
from app.models.proxy_node import ProxyNode
from app.models.team import Department, LoginLog, OperationLog, Role, RolePermission, User, UserRole
from tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def cleanup_linked_accounts(db, clean_tables):
    yield
    db.rollback()
    db.query(EmailAccountRelation).delete()
    db.query(OpAccount).delete()
    db.commit()


def grant(db, user, *permissions):
    role = Role(name=f"table-query-{user.username}", data_scope="self")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.add_all(RolePermission(role_id=role.id, permission=name) for name in permissions)
    db.commit()


def get(client, user, path, **params):
    if "table_filters" in params:
        params["table_filters"] = json.dumps(params["table_filters"], ensure_ascii=False)
    response = client.get(path, params=params, headers=auth_headers(user))
    assert response.status_code == 200, response.text
    return response.json()


def test_email_derived_sort_filters_and_totals(client, db, super_admin):
    devices = [Device(name=name, device_type="phone", owner_id=super_admin.id) for name in ("Zulu", "Alpha")]
    node = ProxyNode(ip="10.70.0.1", port=1080, protocol="socks5", status="idle")
    db.add_all([*devices, node])
    db.flush()
    emails = [EmailAccount(email=f"table-{index}@example.com", device_id=device.id, node_id=node.id,
                           purchase_price=index + 1, purchase_date=datetime(2026, 10, 6).date())
              for index, device in enumerate(devices)]
    db.add_all(emails)
    db.flush()
    for index in range(3):
        account = OpAccount(platform="tiktok", account=f"email-table-{index}")
        db.add(account)
        db.flush()
        db.add(EmailAccountRelation(email_id=emails[index > 0].id, op_account_id=account.id))
    db.commit()
    first = get(client, super_admin, "/api/emails", sort_by="current_relation_count", sort_order="desc", limit=1)
    second = get(client, super_admin, "/api/emails", sort_by="current_relation_count", sort_order="desc", skip=1, limit=1)
    assert first["total"] == second["total"] == 2
    assert first["items"][0]["id"] == emails[1].id
    assert first["items"][0]["current_relation_count"] == 2
    assert second["items"][0]["id"] == emails[0].id
    filtered = get(client, super_admin, "/api/emails", sort_by="device_name", table_filters={
        "node_ip": {"type": "text", "value": ":1080"},
        "device_name": {"type": "text", "value": "alp"},
        "purchase_price": {"type": "number", "min": 2},
        "purchase_date": {"type": "date", "value": "2026-10-06"},
    })
    assert filtered["total"] == 1 and filtered["items"][0]["id"] == emails[1].id


def test_email_scope_and_invalid_filter_fields(client, db, normal_user, other_user):
    grant(db, normal_user, "email:view")
    db.add_all([EmailAccount(email="own-table@example.com", registrant=normal_user.username),
                EmailAccount(email="foreign-table@example.com", registrant=other_user.username)])
    db.commit()
    assert get(client, normal_user, "/api/emails", table_filters={
        "email": {"type": "text", "value": "foreign"}})["total"] == 0
    for params in ({"sort_by": "password"}, {"sort_order": "sideways"},
                   {"table_filters": '{"purchase_price":{"type":"number","min":"NaN"}}'},
                   {"table_filters": '{"gmail_checked_at":{"type":"date","min":"broken"}}'}):
        response = client.get("/api/emails", params=params, headers=auth_headers(normal_user))
        assert response.status_code == 422, response.text


def test_device_derived_fields_sort_before_page_and_keep_owner_scope(client, db, normal_user, other_user, super_admin):
    node = ProxyNode(ip="10.80.0.1", port=8800, protocol="socks5", status="idle")
    db.add(node)
    db.flush()
    devices = [Device(name="Zulu", device_type="phone", owner_id=normal_user.id, node_ids=[node.id]),
               Device(name="Alpha", device_type="phone", owner_id=normal_user.id),
               Device(name="Hidden", device_type="phone", owner_id=other_user.id)]
    db.add_all(devices)
    db.flush()
    db.add_all([OpAccount(platform="tiktok", account="zulu-account", nickname="Zed", device_id=devices[0].id),
                OpAccount(platform="tiktok", account="alpha-account", nickname="Ace", device_id=devices[1].id)])
    db.commit()
    page = get(client, normal_user, "/api/devices", sort_by="accounts", skip=1, limit=1)
    assert page["total"] == 2 and page["items"][0]["id"] == devices[0].id
    selected = get(client, normal_user, "/api/devices", table_filters={
        "accounts": {"type": "text", "value": "ACE"}, "owner_name": {"type": "text", "value": "Alice"}})
    assert selected["total"] == 1 and selected["items"][0]["id"] == devices[1].id
    by_node = get(client, normal_user, "/api/devices", sort_by="node_count", sort_order="desc", limit=1,
                  table_filters={"node_ip": {"type": "text", "value": ":8800"}})
    assert by_node["total"] == 1 and by_node["items"][0]["node_count"] == 1
    assert get(client, normal_user, "/api/devices", table_filters={
        "name": {"type": "text", "value": "Hidden"}})["total"] == 0


def test_node_derived_queries_include_multiple_nodes_and_scope_linked_assets(client, db, normal_user, other_user):
    grant(db, normal_user, "proxy_node:view")
    nodes = [ProxyNode(ip=f"10.90.0.{index}", port=1080, protocol="socks5", status="idle",
                       created_by=normal_user.username) for index in (1, 2, 3)]
    db.add_all(nodes)
    db.flush()
    devices = [Device(name="Visible phone", device_type="phone", owner_id=normal_user.id,
                      node_id=nodes[0].id, node_ids=[nodes[0].id, nodes[1].id]),
               Device(name="Foreign phone", device_type="phone", owner_id=other_user.id,
                      node_ids=[nodes[0].id]),
               Device(name="Legacy phone", device_type="phone", owner_id=normal_user.id, node_id=nodes[2].id)]
    db.add_all(devices)
    db.flush()
    db.add_all([OpAccount(platform="tiktok", account="visible-1", node_id=nodes[0].id,
                          device_id=devices[0].id),
                OpAccount(platform="tiktok", account="visible-2", node_id=nodes[1].id,
                          registrant=normal_user.username),
                OpAccount(platform="tiktok", account="visible-3", node_id=nodes[1].id,
                          registrant=normal_user.username),
                OpAccount(platform="tiktok", account="foreign", node_id=nodes[0].id,
                          registrant=other_user.username)])
    db.commit()
    page = get(client, normal_user, "/api/proxy-nodes", sort_by="account_count", sort_order="desc", limit=1)
    assert page["total"] == 3 and page["items"][0]["id"] == nodes[1].id
    assert page["items"][0]["account_count"] == 2
    assert get(client, normal_user, "/api/proxy-nodes", table_filters={
        "devices": {"type": "text", "value": "Visible phone"}})["total"] == 2
    assert get(client, normal_user, "/api/proxy-nodes", table_filters={
        "devices": {"type": "text", "value": "Foreign phone"}})["total"] == 0
    assert get(client, normal_user, "/api/proxy-nodes", table_filters={
        "accounts": {"type": "text", "value": "foreign"}})["total"] == 0
    assert get(client, normal_user, "/api/proxy-nodes", table_filters={
        "device_name": {"type": "text", "value": "Legacy"}})["items"][0]["id"] == nodes[2].id
    assert client.get("/api/proxy-nodes", headers=auth_headers(normal_user), params={"sort_by": "password"}).status_code == 422


def test_member_department_roles_and_log_date_filters(client, db, super_admin):
    depts = [Department(name=name) for name in ("Zulu", "Alpha")]
    role = Role(name="Data reviewer", data_scope="self")
    db.add_all([*depts, role])
    db.flush()
    users = [User(username=f"table-user-{index}", real_name=f"Member {index}", password_hash="hash",
                  department_id=dept.id) for index, dept in enumerate(depts)]
    db.add_all(users)
    db.flush()
    db.add_all(UserRole(user_id=user.id, role_id=role.id) for user in users)
    db.add_all([LoginLog(username="zulu", result="success", created_at=datetime(2026, 10, 6, 12)),
                LoginLog(username="alpha", result="success", created_at=datetime(2026, 10, 6, 23)),
                LoginLog(username="next", result="success", created_at=datetime(2026, 10, 7)),
                OperationLog(username="actor", module="节点管理", action="UPDATE", result="failed",
                             summary="sorting fixture", created_at=datetime(2026, 10, 6))])
    db.commit()
    page = get(client, super_admin, "/api/team/member", sort_by="department_name", page=2, size=1,
               table_filters={"roles": {"type": "text", "value": "reviewer"}})
    assert page["total"] == 2 and page["items"][0]["id"] == users[0].id
    log_page = get(client, super_admin, "/api/team/log/login", sort_by="username", page=2, size=1,
                   table_filters={"created_at": {"type": "date", "value": "2026-10-06"}})
    assert log_page["total"] == 2 and log_page["items"][0]["username"] == "zulu"
    operation = get(client, super_admin, "/api/team/log/operation", table_filters={
        "summary": {"type": "text", "value": "fixture"}, "result": {"type": "enum", "value": ["failed"]}})
    assert operation["total"] == 1
    bad_boolean = client.get("/api/team/member", params={
        "table_filters": '{"is_active":{"type":"enum","value":["yes"]}}'}, headers=auth_headers(super_admin))
    assert bad_boolean.status_code == 422


def test_card_content_sort_and_filter_decrypt_before_pagination_keep_claim_scope(client, db, normal_user, super_admin):
    grant(db, normal_user, "card_key:view")
    project = CardKeyProject(name="Table keys", member_usernames="__all__", created_by=super_admin.username)
    db.add(project)
    db.flush()
    for content, claimed_by in (("zulu code", normal_user.username), ("alpha code", normal_user.username),
                                ("foreign code", super_admin.username)):
        db.add(CardKey(project_id=project.id, content=content, fingerprint=hashlib.sha256(content.encode()).hexdigest(),
                       created_by=super_admin.username, claimed_by=claimed_by, status="claimed"))
    db.commit()
    page = get(client, normal_user, f"/api/card-keys/{project.id}/keys", sort_by="content", page=2, page_size=1,
               table_filters={"content": {"type": "text", "value": "CODE"}})
    assert page["total"] == 2 and page["items"][0]["content"] == "zulu code"
    assert get(client, normal_user, f"/api/card-keys/{project.id}/keys", table_filters={
        "content": {"type": "text", "value": "foreign"}})["total"] == 0


def test_asset_logs_filter_displayed_summary_and_keep_authorization(client, db, normal_user, other_user, super_admin):
    device = Device(name="History phone", device_type="phone", owner_id=normal_user.id)
    node = ProxyNode(ip="10.110.0.1", port=1080, protocol="socks5", status="idle", created_by=normal_user.username)
    db.add_all([device, node])
    db.flush()
    db.add_all([DeviceLog(device_id=device.id, user_id=normal_user.id, username=normal_user.username,
                          action="CREATE", changes='{"name":{"new":"History phone"},"device_type":{"new":"phone"}}'),
                DeviceLog(device_id=device.id, user_id=normal_user.id, username=normal_user.username, action="UPDATE"),
                OperationLog(username=normal_user.username, module="节点管理", action="UPDATE", result="success",
                             summary=f"UPDATE /api/proxy-nodes/{node.id}")])
    db.commit()
    logs = get(client, normal_user, f"/api/devices/{device.id}/logs", table_filters={
        "summary": {"type": "text", "value": "History phone"}})
    assert logs["total"] == 1 and logs["items"][0]["action"] == "CREATE"
    hidden = client.get(f"/api/devices/{device.id}/logs", params={"sort_by": "summary"}, headers=auth_headers(other_user))
    assert hidden.status_code == 403
    node_logs = get(client, super_admin, f"/api/proxy-nodes/{node.id}/logs", table_filters={
        "summary": {"type": "text", "value": "修改节点资料"}})
    assert node_logs["total"] == 1 and node_logs["items"][0]["summary"] == "修改节点资料"
