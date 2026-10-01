import pytest
from sqlalchemy import text
from app.models.op_account import EmailAccount, EmailAccountRelation, EmailAssetRelation, OpAccount
from app.models.team import Role, RolePermission, UserRole
from tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def clean_email_accounts(db, clean_tables):
    yield
    db.rollback()
    db.query(EmailAssetRelation).delete()
    db.query(EmailAccountRelation).delete()
    db.query(EmailAccount).delete()
    db.query(OpAccount).filter(OpAccount.account.in_(["tiktok-user", "second-user"])).delete()
    db.commit()


def make_account(db, account="tiktok-user"):
    row = OpAccount(platform="tiktok", account=account, registrant="root", status="正常")
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize("delimiter", ["|", "----", ":"])
@pytest.mark.parametrize("registration", [None, "2024", "2024-03-02 12:30:45"])
def test_email_import_delimiters(client, db, super_admin, delimiter, registration):
    fields = ["format@gmail.com", "test-password", "recovery@example.com", "TESTKEY"]
    if registration:
        fields.extend([registration, "Sri Lanka"])
    response = client.post("/api/emails/import", headers=auth_headers(super_admin), json={"text": delimiter.join(fields), "purchase_channel": " 供应商 ", "purchase_price": "3.50"})
    assert response.status_code == 200, response.text
    assert response.json()["success"] == 1
    email = db.query(EmailAccount).one()
    assert email.password == "test-password"
    assert email.purchase_channel == "供应商"
    assert str(email.purchase_price) == "3.50"
    assert email.country == ("Sri Lanka" if registration else None)
    assert email.account_created_year == (2024 if registration == "2024" else None)
    if registration and registration != "2024":
        assert email.account_created_at.isoformat() == "2024-03-02T12:30:45"


def test_email_import_mixed_delimiters(client, super_admin):
    response = client.post("/api/emails/import", headers=auth_headers(super_admin), json={"text": "\n".join([
        "pipe@gmail.com|password|recovery@example.com|KEY|2024|Sri Lanka",
        "dash@gmail.com----password----recovery@example.com----KEY",
        'colon@gmail.com:"password:with:colon":recovery@example.com:KEY:2020:France',
    ]), "purchase_channel": "供应商", "purchase_price": "3.50"})
    assert response.json()["success"] == 3, response.text


def test_email_create_import_and_secret_round_trip(client, db, super_admin):
    headers = auth_headers(super_admin)
    created = client.post("/api/emails", headers=headers, json={
        "email": "MailUser@Gmail.com", "password": "secret", "totp_secret": "totp",
        "account_created_year": 2021, "country": "Singapore",
        "purchase_channel": "供应商", "purchase_price": "3.50",
    })
    assert created.status_code == 200, created.text
    assert created.json()["email"] == "mailuser@gmail.com"
    email = db.query(EmailAccount).one()
    assert email.password == "secret"
    assert email.totp_secret == "totp"
    stored = db.execute(text("SELECT password, totp_secret FROM email_accounts WHERE id=:id"), {"id": email.id}).one()
    assert stored.password != "secret"
    assert stored.totp_secret != "totp"
    assert client.put(f"/api/emails/{email.id}", headers=headers, json={"country": "France"}).status_code == 200
    db.refresh(email)
    assert email.password == "secret"

    imported = client.post("/api/emails/import", headers=headers, json={
        "text": "second@gmail.com----p----recovery@example.com----key\nthird@example.com:p:r:k:2022:France",
        "purchase_channel": "供应商", "purchase_price": "3.50"
    })
    assert imported.status_code == 200, imported.text
    assert imported.json()["success"] == 2
    assert all(row.get("_id") for row in imported.json()["rows"] if row["_result"] == "success")
    assert db.query(EmailAccount).count() == 3


@pytest.mark.parametrize("endpoint", ["/api/emails", "/api/emails/import"])
@pytest.mark.parametrize("trade", [
    {}, {"purchase_price": "3.50"}, {"purchase_channel": "供应商"},
    {"purchase_channel": " ", "purchase_price": "3.50"},
    {"purchase_channel": "供应商", "purchase_price": None},
    {"purchase_channel": "供应商", "purchase_price": -1},
    {"purchase_channel": "供应商", "purchase_price": "无效"},
    {"purchase_channel": "供应商", "purchase_price": "NaN"},
    {"purchase_channel": "供应商", "purchase_price": "Infinity"},
])
def test_email_create_and_import_require_purchase_fields(client, db, super_admin, trade, endpoint):
    payload = {"email": "missing-trade@gmail.com"} if endpoint == "/api/emails" else {"text": "missing-trade@gmail.com|password|recovery@example.com|KEY"}
    response = client.post(endpoint, headers=auth_headers(super_admin), json={**payload, **trade})
    assert response.status_code == 422, response.text
    assert db.query(EmailAccount).count() == 0


def test_email_import_accepts_explicit_zero_cost(client, db, super_admin):
    response = client.post("/api/emails/import", headers=auth_headers(super_admin), json={
        "text": "free@gmail.com|password|recovery@example.com|KEY",
        "purchase_channel": "自注册", "purchase_price": 0,
    })
    assert response.status_code == 200, response.text
    assert response.json()["success"] == 1
    assert db.query(EmailAccount).one().purchase_price == 0


def test_email_create_accepts_zero_cost_and_keeps_legacy_editing(client, db, super_admin):
    headers = auth_headers(super_admin)
    response = client.post("/api/emails", headers=headers, json={
        "email": "free-new@gmail.com", "purchase_channel": " 自注册 ", "purchase_price": 0,
    })
    assert response.status_code == 200, response.text
    assert response.json()["purchase_channel"] == "自注册"
    assert db.query(EmailAccount).one().purchase_price == 0
    legacy = EmailAccount(email="legacy@gmail.com", registrant="root")
    db.add(legacy)
    db.commit()
    response = client.put(f"/api/emails/{legacy.id}", headers=headers, json={"remark": "更新备注"})
    assert response.status_code == 200, response.text
    assert response.json()["purchase_price"] is None


def test_email_sale_status_requires_sale_details(client, db, super_admin):
    headers = auth_headers(super_admin)
    base = {"email": "sold@gmail.com", "purchase_channel": "供应商", "purchase_price": 0,
            "management_status": "已出售"}
    response = client.post("/api/emails", headers=headers, json=base)
    assert response.status_code == 422
    response = client.post("/api/emails", headers=headers, json={**base, "sale_customer": "客户",
        "sale_price": 8, "sale_date": "2026-10-01", "sellers": ["root"]})
    assert response.status_code == 200, response.text
    assert response.json()["management_status"] == "已出售"
    email_id = response.json()["id"]
    assert client.put(f"/api/emails/{email_id}", headers=headers, json={"remark": "已交付"}).status_code == 200
    for missing in ({"sale_customer": " "}, {"sale_price": None}, {"sale_date": None}, {"sellers": []}):
        assert client.put(f"/api/emails/{email_id}", headers=headers, json=missing).status_code == 422
    account = make_account(db)
    assert client.post(f"/api/emails/{email_id}/relations", headers=headers, json={"op_account_id": account.id}).status_code == 409
    reverted = client.put(f"/api/emails/{email_id}", headers=headers, json={"management_status": "闲置"})
    assert reverted.status_code == 200, reverted.text
    assert reverted.json()["sale_customer"] == "客户"
    assert reverted.json()["sellers"] == ["root"]


@pytest.mark.parametrize("missing", [{"sale_customer": " "}, {"sale_price": None}, {"sale_date": None}, {"sellers": []}])
def test_email_transition_to_sold_requires_details(client, db, super_admin, missing):
    headers = auth_headers(super_admin)
    email = EmailAccount(email="transition@gmail.com", registrant="root")
    db.add(email)
    db.commit()
    sale = {"management_status": "已出售", "sale_customer": "客户", "sale_price": 0,
            "sale_date": "2026-10-01", "sellers": ["root"]}
    response = client.put(f"/api/emails/{email.id}", headers=headers, json={**sale, **missing})
    assert response.status_code == 422, response.text
    db.refresh(email)
    assert email.management_status == "闲置"
    response = client.put(f"/api/emails/{email.id}", headers=headers, json=sale)
    assert response.status_code == 200, response.text


def test_email_relation_keeps_history_and_prevents_duplicate(client, db, super_admin):
    headers = auth_headers(super_admin)
    email = EmailAccount(email="resource@gmail.com", registrant="root")
    account = make_account(db)
    db.add(email)
    db.commit()

    url = f"/api/emails/{email.id}/relations"
    assert client.post(url, headers=headers, json={"op_account_id": account.id}).status_code == 200
    assert client.post(url, headers=headers, json={"op_account_id": account.id}).status_code == 409
    relation = db.query(EmailAccountRelation).one()
    assert client.delete(f"{url}/{relation.id}", headers=headers).status_code == 200
    history = client.get(url, headers=headers)
    assert history.status_code == 200
    assert history.json()[0]["unbound_at"] is not None
    assert history.json()[0]["unbound_by"] == "root"
    assert client.post(url, headers=headers, json={"op_account_id": account.id}).status_code == 200
    assert len(client.get(url, headers=headers).json()) == 2
    assert client.get(f"/api/emails/for-account/{account.id}", headers=headers).json()[0]["email"] == email.email
    listed = client.get("/api/emails", headers=headers).json()
    assert listed["items"][0]["current_relation_count"] == 1
    assert client.delete(f"/api/op-accounts/{account.id}", headers=headers).status_code == 409


def test_email_delete_rejects_relation_history(client, db, super_admin):
    headers = auth_headers(super_admin)
    email = EmailAccount(email="resource2@gmail.com", registrant="root")
    account = make_account(db, "second-user")
    db.add(email)
    db.commit()
    relation = EmailAccountRelation(email_id=email.id, op_account_id=account.id, operator="root")
    db.add(relation)
    db.commit()
    response = client.delete(f"/api/emails/{email.id}", headers=headers)
    assert response.status_code == 409


def test_email_scope_and_check_require_consent(client, db, normal_user, monkeypatch):
    role = Role(name="email-manager", data_scope="self")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=normal_user.id, role_id=role.id))
    for permission in ("email:view", "email:manage", "email:check"):
        db.add(RolePermission(role_id=role.id, permission=permission))
    hidden = EmailAccount(email="hidden@gmail.com", registrant="root")
    db.add(hidden)
    db.commit()
    headers = auth_headers(normal_user)
    assert client.get("/api/emails", headers=headers).json()["total"] == 0
    assert client.put(f"/api/emails/{hidden.id}", headers=headers, json={"country": "France"}).status_code == 404
    monkeypatch.setattr("app.api.emails.check_gmail_accounts", lambda emails: pytest.fail("unexpected transmission"))
    assert client.post("/api/emails/check", headers=headers, json={"account_ids": [hidden.id], "consent": True}).status_code == 404
    assert client.post("/api/emails/check", headers=headers, json={"account_ids": [hidden.id], "consent": False}).status_code == 422


def test_email_probe_does_not_override_management_status(client, db, super_admin, monkeypatch):
    email = EmailAccount(email="probe@gmail.com", registrant="root", management_status="锁定")
    db.add(email)
    db.commit()
    monkeypatch.setattr("app.api.emails.check_gmail_accounts", lambda emails: [{"email": emails[0], "status": "Disabled"}])
    response = client.post("/api/emails/check", headers=auth_headers(super_admin), json={"account_ids": [email.id], "consent": True})
    assert response.status_code == 200, response.text
    db.refresh(email)
    assert (email.gmail_check_status, email.management_status) == ("封禁", "锁定")


def test_email_trade_and_shared_assets(client, db, super_admin, make_node):
    from app.models.device import Device
    device = Device(name="测试手机", device_type="phone", owner_id=super_admin.id)
    db.add(device)
    db.commit()
    node = make_node()
    headers = auth_headers(super_admin)
    payload = {"email": "asset-one@gmail.com", "device_id": device.id, "node_id": node.id,
               "purchase_channel": "供应商", "purchase_price": "3.50", "purchase_date": "2026-10-01",
               "sale_customer": "客户", "sale_price": "8.00", "sale_date": "2026-10-01", "sellers": ["root"]}
    response = client.post("/api/emails", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    email_id = response.json()["id"]
    assert response.json()["device_name"] == "测试手机"
    assert response.json()["purchase_price"] == "3.50"
    assert response.json()["sellers"] == ["root"]
    assert client.post("/api/emails", headers=headers, json=payload).status_code == 409
    payload["email"] = "asset-two@gmail.com"
    assert client.post("/api/emails", headers=headers, json=payload).status_code == 200
    url = f"/api/emails/{email_id}"
    assert client.put(url, headers=headers, json={"device_id": None, "node_id": None}).status_code == 200
    history = client.get(url + "/asset-history", headers=headers).json()
    assert len(history) == 2
    assert all(row["unbound_at"] and row["unbound_by"] == "root" for row in history)
    assert client.delete(url, headers=headers).status_code == 409
    assert client.put(url, headers=headers, json={"purchase_price": -1}).status_code == 422


def test_email_asset_scope(client, db, normal_user, super_admin):
    from app.models.device import Device
    role = Role(name="email-assets", data_scope="self")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=normal_user.id, role_id=role.id))
    db.add(RolePermission(role_id=role.id, permission="email:manage"))
    device = Device(name="他人手机", device_type="phone", owner_id=super_admin.id)
    db.add(device)
    db.commit()
    response = client.post("/api/emails", headers=auth_headers(normal_user),
                           json={"email": "scoped@gmail.com", "device_id": device.id,
                                 "purchase_channel": "供应商", "purchase_price": 0})
    assert response.status_code == 403
