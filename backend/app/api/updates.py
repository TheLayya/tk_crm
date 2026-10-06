from typing import Any
from app.models.team import User
import json
import logging
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException

from app.services.auth_service import get_current_user_from_header, require_permission
from app.core.config import settings
from app.version import APP_VERSION, UPDATE_MANIFEST_URL

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/updates", tags=["Updates"])
HISTORY_PATH = Path(settings.UPDATE_HISTORY_PATH) if settings.UPDATE_HISTORY_PATH else Path(__file__).resolve().parents[2] / "data" / "update-history.json"


def _version_tuple(value: object) -> tuple[int, ...]:
    if not isinstance(value, str) or not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise ValueError("Invalid release version")
    return tuple(int(part) for part in value.removeprefix("v").split("."))


def _validate_package_manifest(data: dict[str, Any]) -> None:
    checksum = data.get("sha256", "")
    if not isinstance(checksum, str) or not re.fullmatch(r"[a-f0-9]{64}", checksum):
        raise ValueError("Invalid release checksum")
    package_url = urlparse(data.get("package_url", ""))
    if (
        package_url.scheme != "https"
        or package_url.username
        or package_url.password
        or package_url.fragment
        or package_url.hostname != "github.com"
        or not package_url.path.startswith("/TheLayya/tk_crm/releases/download/")
    ):
        raise ValueError("Invalid release package URL")


def _has_windows_package(data: dict[str, Any]) -> bool:
    package_url = data.get("windows_package_url")
    checksum = data.get("windows_sha256")
    if package_url is None and checksum is None:
        return False
    if not isinstance(package_url, str) or not isinstance(checksum, str) or not re.fullmatch(r"[a-f0-9]{64}", checksum):
        raise ValueError("Invalid Windows release package")
    parsed = urlparse(package_url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.query
        or parsed.hostname != "github.com"
        or not parsed.path.startswith("/TheLayya/tk_crm/releases/download/")
        or not parsed.path.lower().endswith(".exe")
    ):
        raise ValueError("Invalid Windows release package URL")
    return True


def _manifest() -> dict[str, Any]:
    url = settings.UPDATE_MANIFEST_URL or os.getenv("UPDATE_MANIFEST_URL", UPDATE_MANIFEST_URL)
    request = Request(url, headers={"User-Agent": "tk-crm-updater"})
    with urlopen(request, timeout=10) as response:
        raw = response.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024:
        raise ValueError("Manifest exceeds size limit")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid manifest")
    _version_tuple(data.get("version"))
    if not isinstance(data.get("changes", []), list) or not all(
        isinstance(item, str) for item in data.get("changes", [])
    ):
        raise ValueError("Invalid changelog")
    return data


@router.get("/version", response_model=None)
def current_version(_: User = Depends(get_current_user_from_header)) -> dict[str, object]:
    return {"current_version": APP_VERSION}


@router.get("/history", response_model=None)
def update_history(_: User = Depends(require_permission("settings:view"))) -> dict[str, object]:
    if not HISTORY_PATH.is_file():
        return {"items": []}
    try:
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        history = []
    return {"items": history if isinstance(history, list) else []}


@router.get("/check", response_model=None)
def check_update(_: User = Depends(require_permission("settings:view"))) -> dict[str, object]:
    try:
        manifest = _manifest()
        latest = manifest["version"]
        has_update = _version_tuple(latest) > _version_tuple(APP_VERSION)
        windows_supported = _has_windows_package(manifest) if settings.UPDATE_CLIENT_TYPE == "desktop" else None
        if has_update and settings.UPDATE_CLIENT_TYPE != "desktop":
            _validate_package_manifest(manifest)
    except Exception as exc:
        logger.warning("Update check failed: %s", exc)
        raise HTTPException(status_code=502, detail="Unable to fetch release manifest") from exc
    return {
        "current_version": APP_VERSION,
        "latest_version": latest,
        "has_update": has_update,
        "date": manifest.get("date"),
        "changes": manifest.get("changes", []),
        "configured": _agent_configured(),
        "desktop_supported": windows_supported,
        "client_type": settings.UPDATE_CLIENT_TYPE,
    }


@router.get("/status", response_model=None)
def update_status(_: User = Depends(require_permission("settings:view"))) -> object:
    return _agent_request("GET", "/status") if _agent_configured() else {
        "status": "not_configured", "message": "Local updater initialization required"
    }


def _agent_configured() -> bool:
    return bool(settings.UPDATE_AGENT_URL and settings.UPDATE_AGENT_TOKEN)


def _agent_request(method: str, path: str, payload: dict[str, Any] | None = None) -> object:
    url = settings.UPDATE_AGENT_URL.rstrip("/") + path
    request = Request(url, method=method, headers={"Authorization": f"Bearer {settings.UPDATE_AGENT_TOKEN}"})
    if payload is not None:
        body = json.dumps(payload).encode()
        request.data = body
        request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except URLError as exc:
        raise HTTPException(status_code=503, detail="Local updater is unavailable") from exc


@router.post("/apply", response_model=None)
def apply_update(_: User = Depends(require_permission("settings:edit"))) -> object:
    if not _agent_configured():
        raise HTTPException(status_code=409, detail="Local updater is not initialized")
    try:
        manifest = _manifest()
        if _version_tuple(manifest["version"]) <= _version_tuple(APP_VERSION):
            raise HTTPException(status_code=409, detail="Already on the latest version")
        if settings.UPDATE_CLIENT_TYPE == "desktop":
            if not _has_windows_package(manifest):
                raise HTTPException(status_code=409, detail="This release has no Windows installer")
        else:
            _validate_package_manifest(manifest)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to fetch release manifest") from exc
    return _agent_request("POST", "/apply", manifest)
