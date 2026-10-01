import logging

import pytest
from fastapi import HTTPException

from app.models.team import LoginLog
from app.services.auth_service import login


@pytest.mark.parametrize("password, successful", [("alicepass", True), ("wrong-pass", False)])
def test_login_preserves_audit_without_logging_credentials(db, normal_user, caplog, password, successful):
    hash_prefix = normal_user.password_hash[:20]
    with caplog.at_level(logging.INFO):
        if successful:
            result = login(normal_user.username, password, "127.0.0.1", db)
            assert result["user"]["username"] == normal_user.username
            assert result["access_token"]
        else:
            with pytest.raises(HTTPException) as error:
                login(normal_user.username, password, "127.0.0.1", db)
            assert error.value.status_code == 401
    assert "LOGIN DEBUG" not in caplog.text
    assert hash_prefix not in caplog.text
    assert password not in caplog.text
    log = db.query(LoginLog).filter(LoginLog.username == normal_user.username).one()
    assert log.result == ("success" if successful else "failed")
