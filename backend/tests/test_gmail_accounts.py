from datetime import datetime
import io

import openpyxl
from sqlalchemy import text

from app.models.op_account import OpAccount
from app.schemas.op_account import OpAccountCreate, OpAccountUpdate, OpAccountResponse
from app.services.op_account_service import create_op_account, update_op_account, export_op_accounts, import_from_excel
import uuid


def test_gmail_credentials_and_registration_round_trip(db):
    suffix = uuid.uuid4().hex[:8]
    source_email = f"demo-{suffix}@gmail.com"
    copy_email = f"copy-{suffix}@gmail.com"
    account = create_op_account(db, OpAccountCreate(
        platform="gmail", account=source_email, password="gmail-secret",
        totp_secret="totp-secret", recovery_email="recovery@example.com",
        country="美国", account_created_at=datetime(2024, 1, 2, 3, 4),
    ))
    stored = db.execute(text("SELECT password, totp_secret FROM op_accounts WHERE id=:id"), {"id": account.id}).one()
    assert stored.password != "gmail-secret"
    assert stored.totp_secret != "totp-secret"
    response = OpAccountResponse.model_validate(account)
    assert response.recovery_email == "recovery@example.com"
    assert response.account_created_at == datetime(2024, 1, 2, 3, 4)
    update_op_account(db, account.id, OpAccountUpdate(recovery_email="new@example.com"))
    assert account.recovery_email == "new@example.com"

    workbook = openpyxl.load_workbook(io.BytesIO(export_op_accounts(db, {"platform": "gmail"}, format="xlsx")))
    sheet = workbook.active
    headers = [cell.value for cell in sheet[1]]
    values = [cell.value for cell in sheet[2]]
    values[headers.index("account")] = copy_email
    sheet.delete_rows(2)
    sheet.append(values)
    output = io.BytesIO()
    workbook.save(output)
    result = import_from_excel(db, output.getvalue())
    assert result.success == 1
    copied = db.query(OpAccount).filter_by(account=copy_email).one()
    assert copied.password == "gmail-secret"
    assert copied.recovery_email == "new@example.com"
    assert copied.account_created_at == datetime(2024, 1, 2, 3, 4)
