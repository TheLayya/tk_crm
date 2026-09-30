"""Bulk assignment uses the isolated API test database, never the running CRM."""
import pytest

from app.models.op_account import OpAccount, OpAuditLog
from app.models.team import Role, RolePermission, UserRole
from tests.conftest import auth_headers


URL = "/api/op-accounts/batch-assign"


@pytest.fixture(autouse=True)
def clean_op_accounts(db, clean_tables):
    for model in (OpAuditLog, OpAccount):
        db.query(model).delete()
    db.commit()
    yield
    db.rollback()
    for model in (OpAuditLog, OpAccount):
        db.query(model).delete()
    db.commit()


def grant(db, user, permissions, scope="self"):
    role = Role(name=f"assignment-{user.username}", data_scope=scope)
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.add_all(RolePermission(role_id=role.id, permission=p) for p in permissions)
    db.commit()


def accounts(db, registrant="root"):
    rows = [
        OpAccount(platform="tiktok", account=f"assign-{index}",
                  registrant=registrant, operator="previous", status="正常",
                  sellers='["seller"]', remark="keep", follower_count=419)
        for index in range(3)
    ]
    db.add_all(rows)
    db.commit()
    return rows


def assert_unchanged(db, rows):
    db.expire_all()
    assert [row.operator for row in rows] == ["previous"] * len(rows)
    assert db.query(OpAuditLog).count() == 0


def test_assign_two_accounts_preserves_fields_and_grants_member_visibility(
    client, db, super_admin, other_user
):
    rows = accounts(db)
    grant(db, other_user, ["op_account:view"])
    member_headers = auth_headers(other_user)
    assert client.get("/api/op-accounts", headers=member_headers).json()["total"] == 0

    response = client.post(URL, headers=auth_headers(super_admin), json={
        "ids": [row.id for row in rows[:2]], "operator": other_user.username,
    })
    assert response.status_code == 200, response.text
    assert response.json() == {"updated": 2}
    db.expire_all()
    assert [row.operator for row in rows] == ["bob", "bob", "previous"]
    for row in rows:
        assert (row.registrant, row.status, row.sellers, row.remark, row.follower_count) == (
            "root", "正常", '["seller"]', "keep", 419,
        )
    logs = db.query(OpAuditLog).order_by(OpAuditLog.op_account_id).all()
    assert [(log.op_account_id, log.action, log.field_name, log.old_value,
             log.new_value, log.operator) for log in logs] == [
        (row.id, "update", "operator", "previous", "bob", "root") for row in rows[:2]
    ]
    visible = client.get("/api/op-accounts", headers=member_headers)
    assert visible.status_code == 200, visible.text
    assert {item["id"] for item in visible.json()["items"]} == {row.id for row in rows[:2]}


def test_duplicate_ids_and_repeated_assignment_create_only_actual_change_logs(
    client, db, normal_user, other_user
):
    grant(db, normal_user, ["op_account:edit", "team:member:view"], scope="all")
    rows = accounts(db)
    body = {"ids": [rows[0].id, rows[0].id], "operator": other_user.username}
    response = client.post(URL, headers=auth_headers(normal_user), json=body)
    assert response.status_code == 200, response.text
    assert response.json() == {"updated": 1}
    response = client.post(URL, headers=auth_headers(normal_user), json=body)
    assert response.status_code == 200, response.text
    assert response.json() == {"updated": 0}
    logs = db.query(OpAuditLog).all()
    assert len(logs) == 1
    assert logs[0].operator == normal_user.username


@pytest.mark.parametrize("body", [
    {"ids": [], "operator": "bob"},
    {"ids": [0], "operator": "bob"},
    {"ids": [-1], "operator": "bob"},
    {"ids": [1], "operator": ""},
    {"ids": [1], "operator": "   "},
    {"ids": [1], "operator": None},
    {"ids": [1]},
])
def test_invalid_payload_is_rejected(client, db, super_admin, body):
    rows = accounts(db)
    response = client.post(URL, headers=auth_headers(super_admin), json=body)
    assert response.status_code == 422, response.text
    assert_unchanged(db, rows)


@pytest.mark.parametrize("operator", ["missing-member", "bob"])
def test_missing_or_disabled_member_does_not_modify_accounts(
    client, db, super_admin, other_user, operator
):
    rows = accounts(db)
    other_user.is_active = False
    db.commit()
    response = client.post(URL, headers=auth_headers(super_admin), json={
        "ids": [row.id for row in rows], "operator": operator,
    })
    assert response.status_code == 422, response.text
    assert_unchanged(db, rows)


def test_missing_account_rejects_entire_batch(client, db, super_admin, other_user):
    rows = accounts(db)
    response = client.post(URL, headers=auth_headers(super_admin), json={
        "ids": [rows[0].id, max(row.id for row in rows) + 1],
        "operator": other_user.username,
    })
    assert response.status_code == 404, response.text
    assert_unchanged(db, rows)


@pytest.mark.parametrize("permissions", [[], ["op_account:edit"], ["team:member:view"]])
def test_both_permissions_are_required(client, db, normal_user, other_user, permissions):
    grant(db, normal_user, permissions, scope="all")
    rows = accounts(db, registrant=normal_user.username)
    response = client.post(URL, headers=auth_headers(normal_user), json={
        "ids": [row.id for row in rows], "operator": other_user.username,
    })
    assert response.status_code == 403, response.text
    assert_unchanged(db, rows)


@pytest.mark.parametrize("scope", ["self", "dept"])
def test_one_out_of_scope_account_rejects_entire_batch(
    client, db, normal_user, other_user, scope
):
    grant(db, normal_user, ["op_account:edit", "team:member:view"], scope=scope)
    rows = accounts(db, registrant=normal_user.username)
    rows[1].registrant = other_user.username
    db.commit()
    response = client.post(URL, headers=auth_headers(normal_user), json={
        "ids": [rows[0].id, rows[1].id], "operator": other_user.username,
    })
    assert response.status_code == 403, response.text
    assert_unchanged(db, rows)
