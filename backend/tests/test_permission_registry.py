import re
from pathlib import Path

from app.services.team_service import PREDEFINED_PERMISSIONS


def test_role_editor_permissions_match_backend_registry():
    repository = Path(__file__).resolve().parents[2]
    editor = (repository / "frontend/src/views/team/RoleManage.vue").read_text(encoding="utf-8")
    permissions = set(re.findall(r"value:\s*['\"]([a-z_]+(?::[a-z_]+)+)['\"]", editor))
    assert permissions == PREDEFINED_PERMISSIONS


def test_api_permissions_are_registered():
    api_directory = Path(__file__).resolve().parents[1] / "app/api"
    permissions = set()
    for source in api_directory.glob("*.py"):
        permissions.update(re.findall(
            r"require_permission\(\s*['\"]([^'\"]+)['\"]",
            source.read_text(encoding="utf-8"),
        ))
    assert permissions
    assert permissions <= PREDEFINED_PERMISSIONS
