"""Cookie credentials round-trip encrypted and obey existing email access rules."""
import json

import pytest
from sqlalchemy import text

from app.models.op_account import EmailAccount
from app.models.team import OperationLog, Role, RolePermission, UserRole
from tests.conftest import auth_headers


def test_email_ck_round_trip_preserves_long_original_text_and_notes(client, db, super_admin):
    headers = auth_headers(super_admin)
    ck = '  [\n' + json.dumps({"name": "SID", "value": "fixture" * 2000}) + '\n]  '
    response = client.post("/api/emails", headers=headers, json={
        "email": "ck@example.invalid", "ck": ck, "remark": "Independent note",
        "purchase_channel": "Fixture", "purchase_price": 0,
    })
    assert response.status_code == 200, response.text
    created = response.json()
    email_id = created["id"]
    assert created["ck"] == ck
    assert created["remark"] == "Independent note"
    stored = db.execute(text("SELECT ck FROM email_accounts WHERE id=:id"), {"id": email_id}).scalar_one()
    assert stored != ck and "fixture" not in stored
    db.expire_all()
    assert db.get(EmailAccount, email_id).ck == ck
    listed = client.get("/api/emails", headers=headers).json()["items"][0]
    assert listed["ck"] == ck

    # An unrelated edit must not erase the newly stored credential.
    response = client.put(f"/api/emails/{email_id}", headers=headers, json={"country": "France"})
    assert response.status_code == 200 and response.json()["ck"] == ck
    replacement = "__Secure-1PSID=fixture-psid; SID=fixture-sid; OSID=fixture-osid"
    response = client.put(f"/api/emails/{email_id}", headers=headers, json={"ck": replacement})
    assert response.status_code == 200 and response.json()["ck"] == replacement
    assert response.json()["remark"] == "Independent note"
    assert replacement not in str([log.summary for log in db.query(OperationLog).all()])


@pytest.mark.parametrize("empty", [None, ""])
def test_email_ck_can_be_cleared_without_touching_other_credentials(client, db, super_admin, empty):
    row = EmailAccount(email="clear-ck@example.invalid", ck="fixture-cookie", password="fixture-password",
                       totp_secret="fixture-totp", remark="Keep note", registrant="root")
    db.add(row)
    db.commit()
    response = client.put(f"/api/emails/{row.id}", headers=auth_headers(super_admin), json={"ck": empty})
    assert response.status_code == 200, response.text
    assert response.json()["ck"] == empty
    db.refresh(row)
    assert (row.ck, row.password, row.totp_secret, row.remark) == (empty, "fixture-password", "fixture-totp", "Keep note")


@pytest.mark.parametrize("params", [
    {"sort_by": "ck"},
    {"table_filters": json.dumps({"ck": {"type": "text", "value": "fixture"}})},
])
def test_email_ck_is_excluded_from_table_queries(client, super_admin, params):
    response = client.get("/api/emails", headers=auth_headers(super_admin), params=params)
    assert response.status_code == 422


def test_email_ck_requires_existing_email_permissions_and_scope(client, db, normal_user):
    own = EmailAccount(email="own-ck@example.invalid", registrant=normal_user.username, ck="own-fixture")
    hidden = EmailAccount(email="hidden-ck@example.invalid", registrant="root", ck="hidden-fixture")
    db.add_all([own, hidden])
    db.commit()
    headers = auth_headers(normal_user)
    path = f"/api/emails/{own.id}"
    assert client.get("/api/emails").status_code == 401
    assert client.get("/api/emails", headers=headers).status_code == 403
    assert client.put(path, headers=headers, json={"ck": "unauthorized"}).status_code == 403

    role = Role(name="ck-reader", data_scope="self")
    db.add(role)
    db.flush()
    db.add_all([UserRole(user_id=normal_user.id, role_id=role.id),
                RolePermission(role_id=role.id, permission="email:view")])
    db.commit()
    response = client.get("/api/emails", headers=headers)
    assert response.status_code == 200
    assert [(row["id"], row["ck"]) for row in response.json()["items"]] == [(own.id, "own-fixture")]
    assert "hidden-fixture" not in response.text
    assert client.put(path, headers=headers, json={"ck": "unauthorized"}).status_code == 403

    db.add(RolePermission(role_id=role.id, permission="email:manage"))
    db.commit()
    assert client.put(f"/api/emails/{hidden.id}", headers=headers, json={"ck": "unauthorized"}).status_code == 404
    response = client.put(path, headers=headers, json={"ck": "updated-fixture"})
    assert response.status_code == 200 and response.json()["ck"] == "updated-fixture"
    db.refresh(hidden)
    assert hidden.ck == "hidden-fixture"
