import pytest
import json
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import text
from app.models.op_account import EmailAccount, EmailAccountRelation, EmailAssetRelation, OpAccount
from app.models.team import Department, OperationLog, Role, RolePermission, UserRole
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


def test_email_import_three_field_mixed_batch(client, db, super_admin):
    response = client.post("/api/emails/import", headers=auth_headers(super_admin), json={
        "text": "\n".join([
            "three-dash@gmail.com----dash-password----DASHKEY",
            "three-pipe@gmail.com|pipe-password|PIPEKEY",
            'three-colon@gmail.com:"colon:password":COLONKEY',
            "four-fields@gmail.com----four-password----helper@example.com----FOURKEY",
        ]),
        "purchase_channel": "供应商", "purchase_price": 0,
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["total"], result["success"], result["failed"]) == (4, 4, 0)
    for suffix, password, key in [
        ("dash", "dash-password", "DASHKEY"),
        ("pipe", "pipe-password", "PIPEKEY"),
        ("colon", "colon:password", "COLONKEY"),
    ]:
        email = db.query(EmailAccount).filter_by(email=f"three-{suffix}@gmail.com").one()
        assert (email.password, email.totp_secret, email.recovery_email) == (password, key, None)
        assert email.registrant == super_admin.username
    assert db.query(EmailAccount).filter_by(email="four-fields@gmail.com").one().recovery_email == "helper@example.com"


def test_email_import_four_fields_allow_empty_and_null_recovery(client, db, super_admin):
    response = client.post("/api/emails/import", headers=auth_headers(super_admin), json={
        "text": "\n".join(
            f"empty-recovery-{index}@gmail.com----password----{recovery}----KEY"
            for index, recovery in enumerate(["", "null", "NULL"])
        ),
        "import_format": "credentials_4", "delimiter": "----",
        "purchase_channel": "供应商", "purchase_price": 0,
    })
    assert response.status_code == 200, response.text
    assert response.json()["success"] == 3, response.text
    assert all(email.recovery_email is None and email.totp_secret == "KEY" for email in db.query(EmailAccount).all())


def test_email_import_selected_format_isolates_mismatch_and_hides_secrets(client, db, super_admin):
    response = client.post("/api/emails/import", headers=auth_headers(super_admin), json={
        "text": "\n".join([
            "selected-valid@gmail.com----valid-password----VALIDKEY",
            "selected-mismatch@gmail.com----mismatch-secret----helper@example.com----MISMATCHKEY",
            "invalid-email----invalid-secret----INVALIDKEY",
        ]),
        "import_format": "credentials_3", "delimiter": "----",
        "purchase_channel": "供应商", "purchase_price": 0,
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["total"], result["success"], result["failed"]) == (3, 1, 2)
    assert [row["_result"] for row in result["rows"]] == ["success", "failed", "failed"]
    assert [row["line"] for row in result["rows"]] == [1, 2, 3]
    assert db.query(EmailAccount).one().email == "selected-valid@gmail.com"
    for secret in ["valid-password", "VALIDKEY", "mismatch-secret", "MISMATCHKEY", "invalid-secret", "INVALIDKEY"]:
        assert secret not in response.text


def test_email_import_forced_dash_preserves_passwords(client, db, super_admin):
    response = client.post("/api/emails/import", headers=auth_headers(super_admin), json={
        "text": "\n".join([
            "punctuation@gmail.com----secret|with:punctuation----null----PUNCTUATIONKEY",
            "literal-null@gmail.com----null----NULL----NULLKEY",
        ]),
        "import_format": "credentials_4", "delimiter": "----",
        "purchase_channel": "供应商", "purchase_price": 0,
    })
    assert response.status_code == 200, response.text
    assert response.json()["success"] == 2, response.text
    punctuation = db.query(EmailAccount).filter_by(email="punctuation@gmail.com").one()
    literal_null = db.query(EmailAccount).filter_by(email="literal-null@gmail.com").one()
    assert punctuation.password == "secret|with:punctuation"
    assert literal_null.password == "null"
    assert punctuation.recovery_email is None and literal_null.recovery_email is None
    stored = db.execute(text("SELECT password FROM email_accounts WHERE id=:id"), {"id": punctuation.id}).scalar_one()
    assert stored != punctuation.password


@pytest.mark.parametrize("delimiter", ["----", "|", ":"])
def test_email_import_selected_full_format_keeps_iso_time(client, db, super_admin, delimiter):
    response = client.post("/api/emails/import", headers=auth_headers(super_admin), json={
        "text": delimiter.join(["full-format@gmail.com", "password", "null", "KEY", "2024-03-02T12:30:45", "France"]),
        "import_format": "full_6", "delimiter": delimiter,
        "purchase_channel": "供应商", "purchase_price": 0,
    })
    assert response.status_code == 200, response.text
    assert response.json()["success"] == 1, response.text
    email = db.query(EmailAccount).one()
    assert email.account_created_at.isoformat() == "2024-03-02T12:30:45"
    assert email.account_created_year is None
    assert email.country == "France"
    assert email.recovery_email is None


def test_email_import_realistic_mixed_country_rows_and_duplicates(client, db, super_admin):
    key = "jbsw y3dp ehpk 3pxp jbsw y3dp ehpk 3pxp"
    fields = [
        ["helper-only@example.invalid", "pass-one", "helper@example.invalid", "", "ch"],
        ["third-key@example.invalid", "pass-two", key, "", "ch"],
        ["repeated-key@example.invalid", "pass-three", key, key.upper().replace(" ", ""), "cg"],
        ["opaque-key@example.invalid", "pass-four", "helper@example.invalid", "opaque-key-123", "br"],
        ["country-four@example.invalid", "pass-five", "helper@example.invalid", "ca"],
        ["key-country-four@example.invalid", "pass-six", key, "br"],
        ["legacy-three@example.invalid", "pass-seven", "LEGACYKEY"],
        ["legacy-four@example.invalid", "pass-eight", "helper@example.invalid", "LEGACYKEY"],
        ["full-six@example.invalid", "pass-nine", "helper@example.invalid", "FULLKEY", "2024", "France"],
        ["helper-three@example.invalid", "pass-ten", "helper@example.invalid"],
    ]
    lines = ["----".join(row) for row in fields]
    conflicting = "----".join(["conflict@example.invalid", "hidden-password", key, "A" * 32, "us"])
    response = client.post("/api/emails/import", headers=auth_headers(super_admin), json={
        "text": "\n".join([*lines, *lines, conflicting]), "purchase_channel": "供应商", "purchase_price": "2.50",
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["total"], result["success"], result["duplicates"], result["failed"]) == (21, 10, 10, 1)
    expected = [
        ("helper@example.invalid", None, "ch"), (None, key, "ch"),
        (None, key.upper().replace(" ", ""), "cg"), ("helper@example.invalid", "opaque-key-123", "br"),
        ("helper@example.invalid", None, "ca"), (None, key, "br"),
        (None, "LEGACYKEY", None), ("helper@example.invalid", "LEGACYKEY", None),
        ("helper@example.invalid", "FULLKEY", "France"),
        ("helper@example.invalid", None, None),
    ]
    for source, trade in zip(fields, expected):
        email = db.query(EmailAccount).filter_by(email=source[0]).one()
        assert (email.recovery_email, email.totp_secret, email.country) == trade
        assert email.password == source[1] and email.purchase_price == Decimal("2.50")
    assert result["rows"][-1]["_reason"] == "辅助邮箱列与2FA列包含不同密钥，请核对这两列"
    for secret in [key, "hidden-password", "opaque-key-123", *[row[1] for row in fields]]:
        assert secret not in response.text
    assert db.query(EmailAccount).filter_by(email="conflict@example.invalid").count() == 0


@pytest.mark.parametrize("delimiter", ["----", "|", ":", ",", "，", "\t"])
def test_email_import_country_formats_and_delimiters(client, db, super_admin, delimiter):
    import csv
    import io
    fields = ["country@example.invalid", "pass:with|punctuation", "helper@example.invalid", "ch"]
    if delimiter == "----":
        line = delimiter.join(fields)
    else:
        output = io.StringIO()
        csv.writer(output, delimiter=delimiter).writerow(fields)
        line = output.getvalue().rstrip("\r\n")
    response = client.post("/api/emails/import", headers=auth_headers(super_admin), json={
        "text": line, "purchase_channel": "供应商", "purchase_price": 0,
    })
    assert response.status_code == 200 and response.json()["success"] == 1, response.text
    email = db.query(EmailAccount).one()
    assert (email.password, email.recovery_email, email.totp_secret, email.country) == (fields[1], fields[2], None, "ch")


@pytest.mark.parametrize("format, last, expected_country, expected_key", [
    ("auto", "美国", "美国", None), ("auto", "United States", "United States", None),
    ("auto", "US", "US", None), ("auto", "ZX", None, "ZX"), ("credentials_4", "US", None, "US"),
    ("country_4", "Custom Country", "Custom Country", None),
])
def test_email_import_fourth_field_country_or_explicit_key(client, db, super_admin, format, last, expected_country, expected_key):
    response = client.post("/api/emails/import", headers=auth_headers(super_admin), json={
        "text": f"explicit@example.invalid----password----helper@example.invalid----{last}",
        "purchase_channel": "供应商", "purchase_price": 0, "import_format": format,
    })
    assert response.status_code == 200 and response.json()["success"] == 1, response.text
    email = db.query(EmailAccount).one()
    assert (email.country, email.totp_secret) == (expected_country, expected_key)


def test_email_import_explicit_five_fields_quoted_password_and_isolated_failures(client, db, super_admin):
    response = client.post("/api/emails/import", headers=auth_headers(super_admin), json={
        "text": 'quoted@example.invalid,"  secret,with:colon|and，comma  ",null,opaqueKEY,ch\nwrong@example.invalid,password,helper@example.invalid,ch',
        "import_format": "country_5", "delimiter": ",", "purchase_channel": "供应商", "purchase_price": 0,
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["success"], result["failed"]) == (1, 1)
    email = db.query(EmailAccount).one()
    assert (email.password, email.recovery_email, email.totp_secret, email.country) == ("  secret,with:colon|and，comma  ", None, "opaqueKEY", "ch")
    assert result["rows"][1]["_reason"] == "当前格式需要五项：邮箱、密码、辅助邮箱或2FA、2FA、国家"
    assert "opaqueKEY" not in response.text and "secret,with" not in response.text


def test_email_import_invalid_date_error_never_echoes_fields(client, super_admin):
    response = client.post("/api/emails/import", headers=auth_headers(super_admin), json={
        "text": "date@example.invalid----password----helper@example.invalid----KEY----private-field----us",
        "purchase_channel": "供应商", "purchase_price": 0,
    })
    assert response.status_code == 200
    assert response.json()["rows"][0]["_reason"] == "注册时间格式无效"
    assert "private-field" not in response.text and "password" not in response.text


def test_email_import_explicit_formats_preserve_legacy_columns(client, db, super_admin):
    key = "JBSWY3DPEHPK3PXP"
    for format, fields in [
        ("auto", ["legacy-six-auto@example.invalid", "secret", key, "opaque", "2024", "ch"]),
        ("credentials_3", ["legacy-three@example.invalid", "secret", "helper@example.invalid"]),
        ("credentials_4", ["legacy-four@example.invalid", "secret", key, "opaque"]),
        ("full_6", ["legacy-six@example.invalid", "secret", key, "opaque", "2024", "ch"]),
    ]:
        response = client.post("/api/emails/import", headers=auth_headers(super_admin), json={
            "text": "----".join(fields), "import_format": format, "purchase_channel": "供应商", "purchase_price": 0,
        })
        assert response.status_code == 200 and response.json()["success"] == 1, response.text
        email = db.query(EmailAccount).filter_by(email=fields[0]).one()
        assert email.totp_secret == fields[2 if format == "credentials_3" else 3]
        assert email.recovery_email == (None if format == "credentials_3" else key)


def test_email_import_third_non_key_is_preserved_without_guessing(client, db, super_admin):
    invalid_key = "A" * 17
    response = client.post("/api/emails/import", headers=auth_headers(super_admin), json={
        "text": f"unrecognized@example.invalid----secret----{invalid_key}----opaque----cg",
        "purchase_channel": "供应商", "purchase_price": 0,
    })
    assert response.status_code == 200 and response.json()["success"] == 1, response.text
    email = db.query(EmailAccount).one()
    assert (email.recovery_email, email.totp_secret, email.country) == (invalid_key, "opaque", "cg")


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


def test_email_totp_standard_vector_and_auth(client, db, super_admin, normal_user, monkeypatch):
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    email = EmailAccount(email="totp@gmail.com", registrant="root", totp_secret=secret)
    db.add(email)
    db.commit()
    monkeypatch.setattr("app.services.totp_service.time.time", lambda: 59)
    path = f"/api/emails/{email.id}/totp"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=auth_headers(normal_user)).status_code == 403
    response = client.get(path, headers=auth_headers(super_admin))
    assert response.status_code == 200, response.text
    assert response.json() == {"code": "287082", "remaining": 1, "valid_for": 1}
    assert response.headers["cache-control"] == "no-store"
    assert secret not in response.text
    listed = client.get("/api/emails", headers=auth_headers(super_admin)).json()["items"][0]
    assert all(field not in listed for field in ("code", "remaining", "valid_for"))


def test_email_totp_subsecond_expiry(client, db, super_admin, monkeypatch):
    email = EmailAccount(email="boundary-totp@gmail.com", registrant="root",
                         totp_secret="GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")
    db.add(email)
    db.commit()
    path = f"/api/emails/{email.id}/totp"
    headers = auth_headers(super_admin)
    monkeypatch.setattr("app.api.emails.time.time", lambda: 59.9)
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["code"] == "287082"
    assert response.json()["remaining"] == 1
    assert response.json()["valid_for"] == pytest.approx(0.1)
    monkeypatch.setattr("app.api.emails.time.time", lambda: 60.0)
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"code": "359152", "remaining": 30, "valid_for": 30}


@pytest.mark.parametrize("secret", [None, "", "---", "invalid!"])
def test_email_totp_rejects_missing_or_invalid_secret(client, db, super_admin, secret):
    email = EmailAccount(email="invalid-totp@gmail.com", registrant="root", totp_secret=secret)
    db.add(email)
    db.commit()
    response = client.get(f"/api/emails/{email.id}/totp", headers=auth_headers(super_admin))
    assert response.status_code == 422
    assert response.json() == {"detail": "该邮箱没有有效的 2FA 密钥"}


@pytest.mark.parametrize("scope, visible", [
    ("self", {"registrant", "operator"}),
    ("dept", {"registrant", "operator", "peer"}),
    ("all", {"registrant", "operator", "peer", "outside"}),
])
def test_email_totp_respects_scope(client, db, normal_user, other_user, super_admin, monkeypatch, scope, visible):
    department = Department(name="email-team")
    role = Role(name=f"email-totp-{scope}", data_scope=scope)
    db.add_all([department, role])
    db.flush()
    normal_user.department_id = other_user.department_id = department.id
    db.add(UserRole(user_id=normal_user.id, role_id=role.id))
    db.add(RolePermission(role_id=role.id, permission="email:view"))
    owners = {
        "registrant": {"registrant": normal_user.username},
        "operator": {"operator": normal_user.username},
        "peer": {"registrant": other_user.username},
        "outside": {"operator": super_admin.username},
    }
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    emails = {name: EmailAccount(email=f"{name}@gmail.com", totp_secret=secret, **owner)
              for name, owner in owners.items()}
    db.add_all(emails.values())
    db.commit()
    monkeypatch.setattr("app.services.totp_service.time.time", lambda: 59)
    headers = auth_headers(normal_user)
    for name, email in emails.items():
        response = client.get(f"/api/emails/{email.id}/totp", headers=headers)
        if name in visible:
            assert response.status_code == 200, response.text
            assert response.json() == {"code": "287082", "remaining": 1, "valid_for": 1}
        else:
            assert response.status_code == 404
            assert secret not in response.text and "287082" not in response.text
    assert client.get("/api/emails/999999/totp", headers=headers).status_code == 404


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


def sale_payload(email_ids, **values):
    return {"email_ids": email_ids, "sale_customer": "客户 A", "sale_price": "8.50",
            "sale_date": "2026-10-12", "sellers": ["root"], **values}


def test_email_batch_sale_deduplicates_and_preserves_credentials_assets(client, db, super_admin):
    emails = [EmailAccount(email=f"sale-{index}@gmail.com", password="delivery-password",
                           totp_secret="DELIVERYKEY", recovery_email="recovery@example.com",
                           registrant=super_admin.username, operator="original-operator",
                           purchase_channel="供应商", purchase_price=Decimal("3.50"),
                           management_status=status, platform_tags='["TikTok"]')
              for index, status in enumerate(["闲置", "使用中"])]
    db.add_all(emails)
    db.commit()
    ids = [email.id for email in emails]
    response = client.post("/api/emails/batch-sale", headers=auth_headers(super_admin),
                           json=sale_payload([ids[1], ids[0], ids[1]], sale_customer=" 客户 A ", sellers=[" root "]))
    assert response.status_code == 200, response.text
    assert response.json() == {"updated": 2, "email_ids": [ids[1], ids[0]]}
    assert "delivery-password" not in response.text and "DELIVERYKEY" not in response.text
    for email in emails:
        db.refresh(email)
        assert (email.management_status, email.sale_customer, email.sale_price, email.sale_date) == (
            "已出售", "客户 A", Decimal("8.50"), date(2026, 10, 12))
        assert json.loads(email.sellers) == ["root"]
        assert (email.password, email.totp_secret, email.recovery_email) == (
            "delivery-password", "DELIVERYKEY", "recovery@example.com")
        assert (email.purchase_channel, email.purchase_price, email.platform_tags, email.operator) == (
            "供应商", Decimal("3.50"), '["TikTok"]', "original-operator")
    log = db.query(OperationLog).filter_by(summary="UPDATE /api/emails/batch-sale").one()
    assert (log.module, log.action, log.username, log.result) == ("邮箱管理", "UPDATE", "root", "success")


def test_email_batch_sale_requires_valid_trade_and_bounded_ids(client, db, super_admin):
    email = EmailAccount(email="sale-validation@gmail.com", registrant=super_admin.username)
    db.add(email)
    db.commit()
    headers = auth_headers(super_admin)
    invalid_values = [
        {"email_ids": []}, {"email_ids": [0]}, {"email_ids": [-1]}, {"email_ids": [email.id] * 501},
        {"sale_customer": " "}, {"sale_customer": "x" * 256}, {"sale_price": -1},
        {"sale_price": "NaN"}, {"sale_price": "Infinity"}, {"sale_price": "8.555"},
        {"sale_price": "100000000.00"}, {"sale_date": None}, {"sale_date": "2026-13-01"},
        {"sellers": []}, {"sellers": [" "]}, {"sellers": [None]},
    ]
    for values in invalid_values:
        payload = sale_payload([email.id])
        payload.update(values)
        response = client.post("/api/emails/batch-sale", headers=headers, json=payload)
        assert response.status_code == 422, (values, response.text)
    for field in ("sale_customer", "sale_price", "sale_date", "sellers"):
        payload = sale_payload([email.id])
        del payload[field]
        assert client.post("/api/emails/batch-sale", headers=headers, json=payload).status_code == 422
    db.refresh(email)
    assert email.management_status == "闲置" and email.sale_customer is None
    assert client.post("/api/emails/batch-sale", headers=headers,
                       json=sale_payload([email.id], sale_price=0)).status_code == 200


def test_email_batch_sale_rejects_missing_and_sold_without_partial_changes(client, db, super_admin):
    available = EmailAccount(email="available@gmail.com", registrant=super_admin.username)
    sold = EmailAccount(email="sold@gmail.com", registrant=super_admin.username,
                        management_status="已出售", sale_customer="原客户", sale_price=Decimal("6.00"),
                        sale_date=date(2026, 10, 1), sellers='["original-seller"]')
    db.add_all([available, sold])
    db.commit()
    headers = auth_headers(super_admin)
    assert client.post("/api/emails/batch-sale", headers=headers,
                       json=sale_payload([available.id, 999999])).status_code == 404
    assert client.post("/api/emails/batch-sale", headers=headers,
                       json=sale_payload([available.id, sold.id])).status_code == 409
    db.refresh(available)
    db.refresh(sold)
    assert available.management_status == "闲置" and available.sale_customer is None
    assert (sold.sale_customer, sold.sale_price, sold.sale_date, sold.sellers) == (
        "原客户", Decimal("6.00"), date(2026, 10, 1), '["original-seller"]')


@pytest.mark.parametrize("scope, expected", [
    ("self", {"registrant", "operator"}),
    ("dept", {"registrant", "operator", "peer"}),
    ("all", {"registrant", "operator", "peer", "outside"}),
])
def test_email_batch_sale_respects_permissions_and_scope(client, db, normal_user, other_user, super_admin, scope, expected):
    department = Department(name="email-sale-team")
    role = Role(name=f"email-sale-{scope}", data_scope=scope)
    db.add_all([department, role])
    db.flush()
    normal_user.department_id = other_user.department_id = department.id
    db.add(UserRole(user_id=normal_user.id, role_id=role.id))
    owners = {"registrant": {"registrant": normal_user.username}, "operator": {"operator": normal_user.username},
              "peer": {"registrant": other_user.username}, "outside": {"registrant": super_admin.username}}
    emails = {name: EmailAccount(email=f"sale-{name}@gmail.com", **owner) for name, owner in owners.items()}
    db.add_all(emails.values())
    db.commit()
    payload = sale_payload([emails["registrant"].id], sellers=[normal_user.username])
    headers = auth_headers(normal_user)
    assert client.post("/api/emails/batch-sale", json=payload).status_code == 401
    assert client.post("/api/emails/batch-sale", headers=headers, json=payload).status_code == 403
    db.add(RolePermission(role_id=role.id, permission="email:manage"))
    db.commit()
    if scope != "all":
        response = client.post("/api/emails/batch-sale", headers=headers,
                               json=sale_payload([emails["registrant"].id, emails["outside"].id]))
        assert response.status_code == 404
        db.refresh(emails["registrant"])
        assert emails["registrant"].management_status == "闲置"
    for name, email in emails.items():
        response = client.post("/api/emails/batch-sale", headers=headers,
                               json=sale_payload([email.id], sellers=[normal_user.username]))
        assert response.status_code == (200 if name in expected else 404), response.text
        db.refresh(email)
        assert email.management_status == ("已出售" if name in expected else "闲置")


@pytest.mark.parametrize("concurrent_action", ["sale", "claim"])
def test_email_batch_sale_rolls_back_if_another_sale_or_claim_wins(client, db, super_admin, monkeypatch, concurrent_action):
    from sqlalchemy.orm import Query
    available = EmailAccount(email="race-available@gmail.com", registrant=super_admin.username)
    concurrent = EmailAccount(email="race-sold@gmail.com", registrant=super_admin.username)
    db.add_all([available, concurrent])
    db.commit()
    update = Query.update

    def concurrent_update(query, *args, **kwargs):
        # Another request changes one selected email after the initial status check.
        if concurrent_action == "sale":
            concurrent.management_status = "已出售"
            concurrent.sale_customer = "先成交客户"
            concurrent.sale_price = Decimal("5.00")
            concurrent.sale_date = date(2026, 10, 11)
            concurrent.sellers = '["first-seller"]'
        else:
            concurrent.claimed_by = "claim-user"
            concurrent.claimed_platform = "TikTok"
        db.commit()
        return update(query, *args, **kwargs)

    monkeypatch.setattr(Query, "update", concurrent_update)
    response = client.post("/api/emails/batch-sale", headers=auth_headers(super_admin),
                           json=sale_payload([available.id, concurrent.id]))
    assert response.status_code == 409, response.text
    db.refresh(available)
    db.refresh(concurrent)
    assert available.management_status == "闲置" and available.sale_customer is None
    if concurrent_action == "sale":
        assert (concurrent.management_status, concurrent.sale_customer, concurrent.sale_price, concurrent.sellers) == (
            "已出售", "先成交客户", Decimal("5.00"), '["first-seller"]')
    else:
        assert (concurrent.management_status, concurrent.claimed_by, concurrent.claimed_platform) == (
            "闲置", "claim-user", "TikTok")


def test_email_batch_sale_rejects_claimed_without_partial_changes(client, db, super_admin):
    available = EmailAccount(email="unclaimed@gmail.com", registrant=super_admin.username)
    claimed = EmailAccount(email="claimed@gmail.com", registrant=super_admin.username,
                           claimed_by="claim-user", claimed_platform="TikTok")
    db.add_all([available, claimed])
    db.commit()
    response = client.post("/api/emails/batch-sale", headers=auth_headers(super_admin),
                           json=sale_payload([available.id, claimed.id]))
    assert response.status_code == 409, response.text
    db.refresh(available)
    db.refresh(claimed)
    assert available.management_status == "闲置" and available.sale_customer is None
    assert (claimed.management_status, claimed.claimed_by, claimed.claimed_platform) == (
        "闲置", "claim-user", "TikTok")


def test_email_batch_sale_supports_500_rows_and_list_limit(client, db, super_admin):
    emails = [EmailAccount(email=f"bulk-{index}@gmail.com", registrant=super_admin.username) for index in range(500)]
    db.add_all(emails)
    db.commit()
    headers = auth_headers(super_admin)
    listed = client.get("/api/emails", headers=headers, params={"limit": 500})
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) == 500
    assert client.get("/api/emails", headers=headers, params={"limit": 501}).status_code == 422
    response = client.post("/api/emails/batch-sale", headers=headers,
                           json=sale_payload([email.id for email in emails]))
    assert response.status_code == 200, response.text
    assert response.json()["updated"] == 500
    assert db.query(EmailAccount).filter_by(management_status="已出售").count() == 500


@pytest.mark.parametrize("status", ["闲置", "使用中", "锁定", "废弃"])
def test_email_batch_status_only_changes_usage_and_records_operator(client, db, super_admin, status):
    account = make_account(db)
    emails = [EmailAccount(email=f"status-{index}@gmail.com", registrant=super_admin.username,
                           password="original-password", totp_secret="ORIGINALKEY", recovery_email="helper@example.com",
                           management_status="使用中", gmail_check_status="正常", gmail_check_raw_status="live",
                           gmail_checked_at=datetime(2026, 10, 1), operator="original-operator", platform_tags='["TikTok"]',
                           sale_customer="原客户", sale_price=Decimal("8.50"), sale_date=date(2026, 10, 1), sellers='["seller"]')
              for index in range(2)]
    db.add_all(emails)
    db.flush()
    relation = EmailAccountRelation(email_id=emails[0].id, op_account_id=account.id, operator="root")
    db.add(relation)
    db.commit()
    ids = [email.id for email in emails]
    response = client.post("/api/emails/batch-status", headers=auth_headers(super_admin),
                           json={"email_ids": [ids[1], ids[0], ids[1]], "management_status": status})
    assert response.status_code == 200, response.text
    assert response.json() == {"updated": 2, "email_ids": [ids[1], ids[0]]}
    assert "original-password" not in response.text and "ORIGINALKEY" not in response.text
    for email in emails:
        db.refresh(email)
        assert email.management_status == status
        assert (email.password, email.totp_secret, email.recovery_email, email.operator, email.platform_tags) == (
            "original-password", "ORIGINALKEY", "helper@example.com", "original-operator", '["TikTok"]')
        assert (email.gmail_check_status, email.gmail_check_raw_status, email.gmail_checked_at) == (
            "正常", "live", datetime(2026, 10, 1))
        assert (email.sale_customer, email.sale_price, email.sale_date, email.sellers) == (
            "原客户", Decimal("8.50"), date(2026, 10, 1), '["seller"]')
    db.refresh(relation)
    assert relation.unbound_at is None
    log = db.query(OperationLog).filter_by(summary="UPDATE /api/emails/batch-status").one()
    assert (log.module, log.action, log.username, log.result) == ("邮箱管理", "UPDATE", "root", "success")


@pytest.mark.parametrize("status", ["正常", "封禁", "验证", "未注册", "检测失败", None])
def test_email_batch_check_status_is_manual_and_keeps_claims_and_trade(client, db, super_admin, status):
    email = EmailAccount(email="manual-check@example.com", registrant=super_admin.username,
                         management_status="已出售", gmail_check_status="封禁", gmail_check_raw_status="disabled",
                         gmail_checked_at=datetime(2026, 10, 1), claimed_by="claim-user", claimed_platform="TikTok",
                         claimed_at=datetime(2026, 10, 2), sale_customer="原客户", sale_price=Decimal("8.50"))
    db.add(email)
    db.commit()
    response = client.post("/api/emails/batch-status", headers=auth_headers(super_admin),
                           json={"email_ids": [email.id], "gmail_check_status": status})
    assert response.status_code == 200, response.text
    db.refresh(email)
    assert (email.gmail_check_status, email.gmail_check_raw_status, email.gmail_checked_at) == (
        status, "手动标记" if status else None, None)
    assert (email.management_status, email.claimed_by, email.claimed_platform, email.claimed_at) == (
        "已出售", "claim-user", "TikTok", datetime(2026, 10, 2))
    assert (email.sale_customer, email.sale_price) == ("原客户", Decimal("8.50"))


def test_email_batch_status_requires_one_valid_field_and_bounded_ids(client, db, super_admin):
    email = EmailAccount(email="status-validation@gmail.com", registrant=super_admin.username)
    db.add(email)
    db.commit()
    headers = auth_headers(super_admin)
    invalid_values = [
        {}, {"management_status": None}, {"management_status": "已出售"}, {"management_status": "unknown"},
        {"gmail_check_status": "unknown"}, {"gmail_check_status": "未检测"}, {"gmail_check_status": ""},
        {"gmail_check_status": None, "management_status": "锁定"},
        {"management_status": "锁定", "password": "new-password"},
    ]
    for values in invalid_values:
        response = client.post("/api/emails/batch-status", headers=headers, json={"email_ids": [email.id], **values})
        assert response.status_code == 422, (values, response.text)
    for ids in [[], [0], [-1], [True], [str(email.id)], [1.5], [email.id] * 501]:
        response = client.post("/api/emails/batch-status", headers=headers,
                               json={"email_ids": ids, "management_status": "锁定"})
        assert response.status_code == 422, (ids[:2], response.text)
    db.refresh(email)
    assert email.management_status == "闲置" and email.gmail_check_status is None


@pytest.mark.parametrize("field, status", [("management_status", "锁定"), ("gmail_check_status", "正常")])
@pytest.mark.parametrize("scope, expected", [
    ("self", {"registrant", "operator"}),
    ("dept", {"registrant", "operator", "peer"}),
    ("all", {"registrant", "operator", "peer", "outside"}),
])
def test_email_batch_status_respects_permissions_scope_and_atomicity(client, db, normal_user, other_user,
                                                                    super_admin, field, status, scope, expected):
    department = Department(name="email-status-team")
    role = Role(name=f"email-status-{scope}", data_scope=scope)
    db.add_all([department, role])
    db.flush()
    normal_user.department_id = other_user.department_id = department.id
    db.add(UserRole(user_id=normal_user.id, role_id=role.id))
    owners = {"registrant": {"registrant": normal_user.username}, "operator": {"operator": normal_user.username},
              "peer": {"registrant": other_user.username}, "outside": {"registrant": super_admin.username}}
    emails = {name: EmailAccount(email=f"status-{name}@gmail.com", **owner) for name, owner in owners.items()}
    db.add_all(emails.values())
    db.commit()
    payload = {"email_ids": [emails["registrant"].id], field: status}
    headers = auth_headers(normal_user)
    assert client.post("/api/emails/batch-status", json=payload).status_code == 401
    assert client.post("/api/emails/batch-status", headers=headers, json=payload).status_code == 403
    db.add(RolePermission(role_id=role.id, permission="email:manage"))
    db.commit()
    for other_id in [999999, *([emails["outside"].id] if scope != "all" else [])]:
        response = client.post("/api/emails/batch-status", headers=headers,
                               json={"email_ids": [emails["registrant"].id, other_id], field: status})
        assert response.status_code == 404, response.text
        db.refresh(emails["registrant"])
        assert getattr(emails["registrant"], field) == ("闲置" if field == "management_status" else None)
    for name, email in emails.items():
        response = client.post("/api/emails/batch-status", headers=headers, json={"email_ids": [email.id], field: status})
        assert response.status_code == (200 if name in expected else 404), response.text
        db.refresh(email)
        assert getattr(email, field) == (status if name in expected else "闲置" if field == "management_status" else None)


@pytest.mark.parametrize("protected", ["sale", "claim"])
def test_email_batch_usage_status_rejects_sold_and_claimed_without_partial_changes(client, db, super_admin, protected):
    available = EmailAccount(email="status-available@gmail.com", registrant=super_admin.username)
    other = EmailAccount(email="status-protected@gmail.com", registrant=super_admin.username)
    if protected == "sale":
        other.management_status, other.sale_customer = "已出售", "原客户"
    else:
        other.claimed_by, other.claimed_platform = "claim-user", "TikTok"
    db.add_all([available, other])
    db.commit()
    response = client.post("/api/emails/batch-status", headers=auth_headers(super_admin),
                           json={"email_ids": [available.id, other.id], "management_status": "锁定"})
    assert response.status_code == 409, response.text
    db.refresh(available)
    db.refresh(other)
    assert available.management_status == "闲置"
    assert (other.management_status, other.sale_customer, other.claimed_by, other.claimed_platform) == (
        ("已出售", "原客户", None, None) if protected == "sale" else ("闲置", None, "claim-user", "TikTok"))


@pytest.mark.parametrize("concurrent_action", ["sale", "claim"])
def test_email_batch_usage_status_rolls_back_concurrent_sale_or_claim(client, db, super_admin, monkeypatch, concurrent_action):
    from sqlalchemy.orm import Query
    available = EmailAccount(email="status-race-available@gmail.com", registrant=super_admin.username)
    other = EmailAccount(email="status-race-other@gmail.com", registrant=super_admin.username)
    db.add_all([available, other])
    db.commit()
    update = Query.update

    def concurrent_update(query, *args, **kwargs):
        if concurrent_action == "sale":
            other.management_status, other.sale_customer = "已出售", "先成交客户"
        else:
            other.claimed_by, other.claimed_platform = "claim-user", "TikTok"
        db.commit()
        return update(query, *args, **kwargs)

    monkeypatch.setattr(Query, "update", concurrent_update)
    response = client.post("/api/emails/batch-status", headers=auth_headers(super_admin),
                           json={"email_ids": [available.id, other.id], "management_status": "锁定"})
    assert response.status_code == 409, response.text
    db.refresh(available)
    db.refresh(other)
    assert available.management_status == "闲置"
    assert (other.management_status, other.sale_customer, other.claimed_by, other.claimed_platform) == (
        ("已出售", "先成交客户", None, None) if concurrent_action == "sale" else ("闲置", None, "claim-user", "TikTok"))


def test_email_batch_status_supports_500_rows(client, db, super_admin):
    emails = [EmailAccount(email=f"status-bulk-{index}@gmail.com", registrant=super_admin.username) for index in range(500)]
    db.add_all(emails)
    db.commit()
    response = client.post("/api/emails/batch-status", headers=auth_headers(super_admin),
                           json={"email_ids": [email.id for email in emails], "management_status": "锁定"})
    assert response.status_code == 200, response.text
    assert response.json()["updated"] == 500
    assert db.query(EmailAccount).filter_by(management_status="锁定").count() == 500


def test_email_manual_check_and_probe_share_lock_without_blocking_usage_changes(client, db, super_admin, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app.api import emails as emails_api
    from app.api.op_accounts import gmail_check_lock
    email = EmailAccount(email="status-check-race@gmail.com", registrant=super_admin.username,
                         gmail_check_status="封禁", gmail_check_raw_status="disabled")
    db.add(email)
    db.commit()
    email_id = email.id
    started, finish = Event(), Event()
    headers = auth_headers(super_admin)
    get_email = emails_api.get_email

    def get_email_while_locked(*args, **kwargs):
        assert gmail_check_lock.locked()
        return get_email(*args, **kwargs)

    def blocking_probe(addresses):
        started.set()
        assert finish.wait(timeout=10)
        return [{"email": address, "status": "live"} for address in addresses]

    monkeypatch.setattr(emails_api, "get_email", get_email_while_locked)
    monkeypatch.setattr(emails_api, "check_gmail_accounts", blocking_probe)
    with ThreadPoolExecutor(max_workers=1) as executor:
        probe = executor.submit(client.post, "/api/emails/check", headers=headers, json={"account_ids": [email_id], "consent": True})
        try:
            assert started.wait(timeout=10)
            manual = client.post("/api/emails/batch-status", headers=headers,
                                 json={"email_ids": [email_id], "gmail_check_status": "验证"})
            assert manual.status_code == 429, manual.text
            usage = client.post("/api/emails/batch-status", headers=headers,
                                json={"email_ids": [email_id], "management_status": "锁定"})
            assert usage.status_code == 200, usage.text
        finally:
            finish.set()
        response = probe.result(timeout=10)
    assert response.status_code == 200, response.text
    db.refresh(email)
    assert (email.gmail_check_status, email.gmail_check_raw_status, email.management_status) == ("正常", "live", "锁定")
    assert email.gmail_checked_at is not None
    manual = client.post("/api/emails/batch-status", headers=headers,
                         json={"email_ids": [email_id], "gmail_check_status": "验证"})
    assert manual.status_code == 200, manual.text
    db.refresh(email)
    assert (email.gmail_check_status, email.gmail_check_raw_status, email.gmail_checked_at) == ("验证", "手动标记", None)
    response = client.post("/api/emails/check", headers=headers, json={"account_ids": [email_id], "consent": True})
    assert response.status_code == 200, response.text
    db.refresh(email)
    assert (email.gmail_check_status, email.gmail_check_raw_status) == ("正常", "live")
    assert email.gmail_checked_at is not None and not gmail_check_lock.locked()


@pytest.mark.parametrize("error", ["missing", "conflict", "commit"])
def test_email_batch_manual_check_releases_lock_after_error(client, db, super_admin, monkeypatch, error):
    from fastapi import HTTPException
    from sqlalchemy.orm import Query
    from app.api import emails as emails_api
    from app.api.op_accounts import gmail_check_lock
    email = EmailAccount(email="manual-check-error@gmail.com", registrant=super_admin.username)
    db.add(email)
    db.commit()
    headers = auth_headers(super_admin)
    with monkeypatch.context() as patch:
        if error == "conflict":
            patch.setattr(Query, "update", lambda *args, **kwargs: 0)
        elif error == "commit":
            def failed_save(session):
                session.rollback()
                raise HTTPException(status_code=409, detail="保存冲突")
            patch.setattr(emails_api, "save", failed_save)
        response = client.post("/api/emails/batch-status", headers=headers,
                               json={"email_ids": [999999 if error == "missing" else email.id], "gmail_check_status": "正常"})
        assert response.status_code == (404 if error == "missing" else 409), response.text
    assert not gmail_check_lock.locked()
    response = client.post("/api/emails/batch-status", headers=headers,
                           json={"email_ids": [email.id], "gmail_check_status": "正常"})
    assert response.status_code == 200, response.text
    assert not gmail_check_lock.locked()


@pytest.mark.parametrize("failure", ["missing", "unsupported", "service"])
def test_email_probe_releases_lock_after_validation_or_service_error(client, db, super_admin, monkeypatch, failure):
    from app.api import emails as emails_api
    from app.api.op_accounts import gmail_check_lock
    email = EmailAccount(email="probe-error@example.com" if failure == "unsupported" else "probe-error@gmail.com",
                         registrant=super_admin.username)
    db.add(email)
    db.commit()

    def failed_probe(addresses):
        raise RuntimeError("synthetic probe failure")

    monkeypatch.setattr(emails_api, "check_gmail_accounts", failed_probe)
    response = client.post("/api/emails/check", headers=auth_headers(super_admin),
                           json={"account_ids": [999999 if failure == "missing" else email.id], "consent": True})
    assert response.status_code == {"missing": 404, "unsupported": 422, "service": 502}[failure], response.text
    assert not gmail_check_lock.locked()
    response = client.post("/api/emails/batch-status", headers=auth_headers(super_admin),
                           json={"email_ids": [email.id], "gmail_check_status": "正常"})
    assert response.status_code == 200, response.text
