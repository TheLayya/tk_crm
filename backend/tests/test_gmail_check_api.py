import pytest
import httpx

from app.models.op_account import OpAccount, OpAuditLog
from app.models.team import Role, RolePermission, UserRole
from tests.conftest import auth_headers

URL = "/api/op-accounts/gmail-check"


@pytest.fixture(autouse=True)
def clean_accounts(db, clean_tables):
    for model in (OpAuditLog, OpAccount):
        db.query(model).delete()
    db.commit()
    yield
    db.rollback()
    for model in (OpAuditLog, OpAccount):
        db.query(model).delete()
    db.commit()


def make_account(db, registrant="root", platform="gmail"):
    account = OpAccount(platform=platform, account="test@gmail.com", registrant=registrant,
                        password="secret", totp_secret="totp", status="自用")
    db.add(account)
    db.commit()
    return account


def test_check_saves_probe_without_overwriting_business_status(client, db, super_admin, monkeypatch):
    account = make_account(db)

    def check(emails):
        assert emails == ["test@gmail.com"]
        return [{"email": emails[0], "status": "Disabled"}]

    monkeypatch.setattr("app.api.op_accounts.check_gmail_accounts", check)
    response = client.post(URL, headers=auth_headers(super_admin), json={"account_ids": [account.id], "consent": True})
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["status"] == "封禁"
    db.refresh(account)
    assert (account.status, account.password, account.totp_secret) == ("自用", "secret", "totp")
    assert account.gmail_check_raw_status == "Disabled"
    assert account.gmail_checked_at is not None
    assert db.query(OpAuditLog).filter_by(action="gmail_check").count() == 1


def test_check_requires_consent_and_rejects_other_platforms(client, db, super_admin, monkeypatch):
    account = make_account(db, platform="tiktok")
    monkeypatch.setattr("app.api.op_accounts.check_gmail_accounts", lambda emails: pytest.fail("unexpected transmission"))
    headers = auth_headers(super_admin)
    assert client.post(URL, headers=headers, json={"account_ids": [account.id]}).status_code == 422
    assert client.post(URL, headers=headers, json={"account_ids": [account.id], "consent": False}).status_code == 422
    assert client.post(URL, headers=headers, json={"account_ids": [account.id], "consent": True}).status_code == 422


def test_check_enforces_data_scope_before_transmission(client, db, normal_user, monkeypatch):
    account = make_account(db)
    role = Role(name="gmail-checker", data_scope="self")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=normal_user.id, role_id=role.id))
    db.add(RolePermission(role_id=role.id, permission="op_account:collect"))
    db.commit()
    monkeypatch.setattr("app.api.op_accounts.check_gmail_accounts", lambda emails: pytest.fail("unexpected transmission"))
    response = client.post(URL, headers=auth_headers(normal_user), json={"account_ids": [account.id], "consent": True})
    assert response.status_code == 403


def test_check_network_failure_preserves_previous_result(client, db, super_admin, monkeypatch):
    account = make_account(db)
    account.gmail_check_status = "正常"
    db.commit()

    def check(emails):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr("app.api.op_accounts.check_gmail_accounts", check)
    response = client.post(URL, headers=auth_headers(super_admin), json={"account_ids": [account.id], "consent": True})
    assert response.status_code == 502
    db.refresh(account)
    assert account.gmail_check_status == "正常"
    assert db.query(OpAuditLog).filter_by(action="gmail_check").count() == 0


def test_gmail_text_upload_imports_without_collection(client, db, super_admin, monkeypatch):
    monkeypatch.setattr("app.api.op_accounts.op_account_service.trigger_collect", lambda *args: pytest.fail("Gmail must not collect"))
    content = 'BULK@gmail.com:"secret:with:colon":helper@example.com:KEY:2026-10-01 12:34:56:美国\nother@gmail.com:pass::::'
    response = client.post("/api/op-accounts/import", headers=auth_headers(super_admin),
                           files={"file": ("gmail.txt", content.encode("utf-8"), "text/plain")})
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["total"], result["success"], result["failed"]) == (2, 2, 0)
    assert result["task_id"] is None
    assert "secret:with:colon" not in response.text
    account = db.query(OpAccount).filter_by(account="bulk@gmail.com").one()
    assert account.password == "secret:with:colon"
    assert account.recovery_email == "helper@example.com"
    assert account.totp_secret == "KEY"
    assert account.account_created_at.isoformat() == "2026-10-01T12:34:56"
    assert account.country == "美国"
    assert account.registrant == super_admin.username


def test_gmail_text_duplicates_and_invalid_lines_are_isolated(client, db, super_admin):
    make_account(db)
    content = 'TEST@gmail.com:duplicate::::\ninvalid:secret::::\nnew@gmail.com:pass:::bad-date:美国\ngood@gmail.com:pass::::'
    response = client.post("/api/op-accounts/import", headers=auth_headers(super_admin),
                           files={"file": ("gmail.txt", content.encode("utf-8"), "text/plain")})
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["success"], result["duplicates"], result["failed"]) == (1, 1, 2)
    assert "secret" not in response.text
    assert db.query(OpAccount).filter_by(account="good@gmail.com").count() == 1


def test_gmail_text_accepts_year_only_registration_date(client, db, super_admin):
    content = "year-only@gmail.com:pass:helper@example.com:KEY:2021:Brazil"
    response = client.post("/api/op-accounts/import", headers=auth_headers(super_admin),
                           files={"file": ("gmail.txt", content.encode("utf-8"), "text/plain")})
    assert response.status_code == 200, response.text
    assert response.json()["success"] == 1
    account = db.query(OpAccount).filter_by(account="year-only@gmail.com").one()
    assert account.account_created_at is None
    assert account.account_created_year == 2021


def test_gmail_text_accepts_four_field_dash_separator(client, db, super_admin):
    content = "dash-format@gmail.com----secret----helper@example.com----KEY"
    response = client.post("/api/op-accounts/import", headers=auth_headers(super_admin),
                           files={"file": ("gmail.txt", content.encode("utf-8"), "text/plain")})
    assert response.status_code == 200, response.text
    assert response.json()["success"] == 1
    account = db.query(OpAccount).filter_by(account="dash-format@gmail.com").one()
    assert account.account_created_at is None
    assert account.account_created_year is None
    assert account.country is None


def test_gmail_text_accepts_three_fields_and_null_recovery(client, db, super_admin):
    content = "three@gmail.com----password----KEY\nnull-recovery@gmail.com----password----null----KEY"
    response = client.post("/api/op-accounts/import", headers=auth_headers(super_admin),
                           files={"file": ("gmail.txt", content.encode("utf-8"), "text/plain")})
    assert response.status_code == 200, response.text
    assert response.json()["success"] == 2
    three = db.query(OpAccount).filter_by(account="three@gmail.com").one()
    null_recovery = db.query(OpAccount).filter_by(account="null-recovery@gmail.com").one()
    assert three.recovery_email is None and three.totp_secret == "KEY"
    assert null_recovery.recovery_email is None and null_recovery.totp_secret == "KEY"


def test_gmail_mixed_rows_do_not_share_registration_year(client, db, super_admin):
    content = '\n'.join([
        'mixed-year@gmail.com:pass:helper@example.com:KEY:2024:France',
        'mixed-empty@gmail.com----pass----helper@example.com----KEY',
        'mixed-date@gmail.com:pass:helper@example.com:KEY:2020-06-15:Brazil',
    ])
    response = client.post('/api/op-accounts/import', headers=auth_headers(super_admin),
                           files={'file': ('gmail.txt', content.encode('utf-8'), 'text/plain')})
    assert response.status_code == 200, response.text
    assert response.json()['success'] == 3
    year = db.query(OpAccount).filter_by(account='mixed-year@gmail.com').one()
    empty = db.query(OpAccount).filter_by(account='mixed-empty@gmail.com').one()
    dated = db.query(OpAccount).filter_by(account='mixed-date@gmail.com').one()
    assert year.account_created_year == 2024 and year.account_created_at is None
    assert empty.account_created_year is None and empty.account_created_at is None
    assert dated.account_created_year is None
    assert dated.account_created_at.isoformat() == '2020-06-15T00:00:00'
