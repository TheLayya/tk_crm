import pytest

from app.core.config import Settings


VALID = {
    "FIELD_ENCRYPTION_KEY": "a" * 64,
    "JWT_SECRET": "test-jwt-secret",
    "SUPER_ADMIN_PASSWORD": "test-admin-password",
}


def test_security_settings_accept_valid_values():
    configuration = Settings(**VALID)
    assert configuration.JWT_SECRET == VALID["JWT_SECRET"]
    assert configuration.SUPER_ADMIN_PASSWORD == VALID["SUPER_ADMIN_PASSWORD"]


@pytest.mark.parametrize("name", list(VALID))
@pytest.mark.parametrize("value", ["", "   "])
def test_security_settings_reject_empty_values(name, value):
    with pytest.raises(ValueError, match=name):
        Settings(_env_file=None, **{**VALID, name: value})


@pytest.mark.parametrize("name", list(VALID))
def test_security_settings_reject_absent_values(name, monkeypatch):
    monkeypatch.delenv(name, raising=False)
    values = {key: value for key, value in VALID.items() if key != name}
    with pytest.raises(ValueError, match=name):
        Settings(_env_file=None, **values)
