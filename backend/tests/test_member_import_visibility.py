import csv
import io

import openpyxl
import pytest

from app.models.op_account import OpAccount, OpAuditLog
from app.models.proxy_node import ProxyNode
from app.models.team import Role, RolePermission, UserRole

from .conftest import auth_headers


@pytest.fixture(autouse=True)
def clean_import_accounts(db, clean_tables):
    for model in (OpAuditLog, OpAccount):
        db.query(model).delete()
    db.commit()
    yield
    db.rollback()
    for model in (OpAuditLog, OpAccount):
        db.query(model).delete()
    db.commit()


def grant(db, user, *permissions):
    role = Role(name=f"member-import-{user.username}", data_scope="self")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.add_all(RolePermission(role_id=role.id, permission=permission) for permission in permissions)
    db.commit()


def account_upload(extension, rows):
    headers = ["account", "platform", "registrant"]
    if extension == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return output.getvalue().encode("utf-8"), "text/csv"

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def node_row(index):
    return {
        "ip": f"10.42.0.{index}",
        "port": 1080 + index,
        "country": "US",
        "protocol": "socks5",
        "purchase_date": "2026-10-01",
        "purchase_price": "12.50",
        "purchase_channel": "member-import",
        "expire_date": "2027-10-01",
        "status": "idle",
    }


def node_upload(extension, row):
    headers = list(row)
    if extension == "csv":
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerow(row)
        return output.getvalue().encode("utf-8"), "text/csv"

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(headers)
    sheet.append([row[key] for key in headers])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_member_account_import_owns_rows_and_audit(
    client, db, normal_user, other_user, extension
):
    grant(db, normal_user, "op_account:view", "op_account:import")
    rows = [
        [f"member-{extension}-blank", "youtube", ""],
        [f"member-{extension}-foreign", "youtube", other_user.username],
    ]
    payload, content_type = account_upload(extension, rows)
    response = client.post(
        "/api/op-accounts/import",
        headers=auth_headers(normal_user),
        files={"file": (f"accounts.{extension}", payload, content_type)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["success"] == 2

    accounts = db.query(OpAccount).filter(OpAccount.account.like(f"member-{extension}-%")).all()
    assert len(accounts) == 2
    assert {account.registrant for account in accounts} == {normal_user.username}
    logs = db.query(OpAuditLog).filter(OpAuditLog.op_account_id.in_([account.id for account in accounts])).all()
    assert logs
    assert {log.operator for log in logs} == {normal_user.username}

    visible = client.get("/api/op-accounts", headers=auth_headers(normal_user))
    assert visible.status_code == 200, visible.text
    assert {item["id"] for item in visible.json()["items"]} == {account.id for account in accounts}


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_super_admin_account_import_preserves_explicit_registrant(
    client, db, super_admin, other_user, extension
):
    payload, content_type = account_upload(
        extension, [[f"admin-{extension}-foreign", "youtube", other_user.username]]
    )
    response = client.post(
        "/api/op-accounts/import",
        headers=auth_headers(super_admin),
        files={"file": (f"accounts.{extension}", payload, content_type)},
    )
    assert response.status_code == 200, response.text
    account = db.query(OpAccount).filter_by(account=f"admin-{extension}-foreign").one()
    assert account.registrant == other_user.username
    logs = db.query(OpAuditLog).filter(OpAuditLog.op_account_id == account.id).all()
    assert logs
    assert {log.operator for log in logs} == {super_admin.username}


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_member_nodes_are_owned_scoped_and_manageable(
    client, db, normal_user, other_user, extension
):
    permissions = ("proxy_node:view", "proxy_node:manage")
    grant(db, normal_user, *permissions)
    grant(db, other_user, *permissions)
    member_headers = auth_headers(normal_user)
    other_headers = auth_headers(other_user)

    direct = client.post(
        "/api/proxy-nodes",
        headers=member_headers,
        json={**node_row(1), "ip": "10.42.1.1", "port": 1101},
    )
    assert direct.status_code == 201, direct.text
    direct_id = direct.json()["id"]
    assert db.get(ProxyNode, direct_id).created_by == normal_user.username

    payload, content_type = node_upload(extension, node_row(2))
    imported = client.post(
        "/api/proxy-nodes/import",
        headers=member_headers,
        files={"file": (f"nodes.{extension}", payload, content_type)},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["success_count"] == 1
    imported_row = db.query(ProxyNode).filter_by(ip="10.42.0.2").one()
    assert imported_row.created_by == normal_user.username
    node_ids = {direct_id, imported_row.id}

    listing = client.get("/api/proxy-nodes", headers=member_headers)
    assert listing.status_code == 200, listing.text
    assert {item["id"] for item in listing.json()["items"]} == node_ids
    stats = client.get("/api/proxy-nodes/stats", headers=member_headers)
    assert stats.status_code == 200, stats.text
    assert stats.json()["total"] == 2
    exported = client.get("/api/proxy-nodes/export", headers=member_headers)
    assert exported.status_code == 200, exported.text
    export_text = exported.content.decode("utf-8-sig")
    assert "10.42.1.1" in export_text and "10.42.0.2" in export_text

    updated = client.patch(
        "/api/proxy-nodes/batch/status",
        headers=member_headers,
        json={"node_ids": sorted(node_ids), "status": "active"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["updated"] == 2

    other_listing = client.get("/api/proxy-nodes", headers=other_headers)
    assert other_listing.status_code == 200, other_listing.text
    assert other_listing.json()["total"] == 0
    for node_id in node_ids:
        denied = client.get(f"/api/proxy-nodes/{node_id}", headers=other_headers)
        assert denied.status_code == 403, denied.text
    denied_batch = client.patch(
        "/api/proxy-nodes/batch/status",
        headers=other_headers,
        json={"node_ids": sorted(node_ids), "status": "idle"},
    )
    assert denied_batch.status_code == 403, denied_batch.text


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/{id}", None),
    ("PATCH", "/{id}", {"remark": "unauthorized"}),
    ("DELETE", "/{id}", None),
    ("POST", "/{id}/test", None),
    ("GET", "/{id}/logs", None),
    ("GET", "/{id}/association-history", None),
    ("PUT", "/{id}/relation", {}),
    ("PATCH", "/batch/status", {"status": "active"}),
    ("DELETE", "/batch", {}),
    ("POST", "/batch/test", {}),
])
def test_member_cannot_access_or_modify_other_members_node(
    client, db, normal_user, other_user, monkeypatch, method, path, body
):
    grant(db, normal_user, "proxy_node:view", "proxy_node:manage")
    grant(db, other_user, "proxy_node:view", "proxy_node:manage")
    owner_response = client.post(
        "/api/proxy-nodes", headers=auth_headers(other_user), json=node_row(3)
    )
    assert owner_response.status_code == 201, owner_response.text
    node_id = owner_response.json()["id"]

    async def fake_test(node):
        return {"success": True, "latency_ms": 1}

    monkeypatch.setattr("app.services.proxy_node_test_service._do_test", fake_test)
    if path.startswith("/batch"):
        body = {**body, "node_ids": [node_id]}
    response = client.request(
        method,
        "/api/proxy-nodes" + path.format(id=node_id),
        headers=auth_headers(normal_user),
        json=body,
    )
    assert response.status_code == 403, response.text
    db.expire_all()
    node = db.get(ProxyNode, node_id)
    assert node is not None
    assert node.status == "idle"
    assert node.remark is None
    assert node.last_test_at is None


def test_member_batch_delete_owns_standalone_nodes(client, db, normal_user):
    grant(db, normal_user, "proxy_node:view", "proxy_node:manage")
    member_headers = auth_headers(normal_user)
    response = client.post("/api/proxy-nodes", headers=member_headers, json=node_row(4))
    assert response.status_code == 201, response.text
    node_id = response.json()["id"]
    deleted = client.request(
        "DELETE", "/api/proxy-nodes/batch", headers=member_headers, json={"node_ids": [node_id]}
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": 1}
    db.expire_all()
    assert db.get(ProxyNode, node_id) is None
