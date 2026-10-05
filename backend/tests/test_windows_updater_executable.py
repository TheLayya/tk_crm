import json
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Requires Windows executable")
@pytest.mark.parametrize("case", [
    "untrusted_url", "invalid_checksum", "runtime_data", "http_url",
    "query_url", "source_archive", "status_inside_installation", "missing_server",
    "data_inside_installation", "installation_inside_data", "status_inside_data", "missing_configuration",
])
def test_updater_rejects_unsafe_inputs_without_changing_installation(tmp_path, case):
    executable = Path(os.environ.get("TKCRM_TEST_UPDATER_EXE") or Path(__file__).resolve().parents[2] / "desktop/build/updater-test/TkCrm.Updater.exe")
    if not executable.is_file():
        pytest.skip("Publish the updater into desktop/build/updater-test first")
    installation = tmp_path / "中文安装目录"
    (installation / "server").mkdir(parents=True)
    desktop = installation / "TkCrm.Desktop.exe"
    desktop.write_bytes(b"unchanged desktop")
    (installation / "server/TkCrm.Server.exe").write_bytes(b"unchanged server")
    url = "https://github.com/TheLayya/tk_crm/releases/download/v99.0.0/setup.exe"
    checksum = "a" * 64
    if case == "untrusted_url":
        url = "https://example.com/setup.exe"
    elif case == "invalid_checksum":
        checksum = "invalid"
    elif case == "runtime_data":
        (installation / "monitor.db").write_bytes(b"do not modify")
    elif case == "http_url":
        url = url.replace("https://", "http://")
    elif case == "query_url":
        url += "?download=1"
    elif case == "source_archive":
        url = url.replace("setup.exe", "source.tar.gz")
    elif case == "missing_server":
        (installation / "server/TkCrm.Server.exe").unlink()
    status = tmp_path / "status.json"
    data = tmp_path / "user-data"
    data.mkdir()
    (data / "monitor.db").write_bytes(b"user data")
    (data / ".env").write_bytes(b"user configuration")
    if case == "data_inside_installation":
        data = installation / "user-data"
        data.mkdir()
        (data / "monitor.db").write_bytes(b"user data")
        (data / ".env").write_bytes(b"user configuration")
    elif case == "installation_inside_data":
        data = tmp_path
        (data / "monitor.db").write_bytes(b"user data")
        (data / ".env").write_bytes(b"user configuration")
    elif case == "status_inside_data":
        status = data / "status.json"
    elif case == "missing_configuration":
        (data / ".env").unlink()
    if case == "status_inside_installation":
        status = installation / "status.json"
    manifest = tmp_path / "release.json"
    manifest.write_text(json.dumps({
        "version": "99.0.0", "windows_package_url": url,
        "windows_sha256": checksum, "changes": ["Executable safety test"],
    }), encoding="utf-8")
    result = subprocess.run([
        str(executable), "--parent-pid", str(os.getpid()), "--install-dir", str(installation),
        "--data-dir", str(data), "--expected-version", "99.0.0", "--installer-url", url,
        "--manifest-file", str(manifest), "--sha256", checksum, "--status-file", str(status),
    ], capture_output=True, timeout=20)
    assert result.returncode == 1
    assert json.loads(status.read_text(encoding="utf-8"))["status"] == "failed"
    assert desktop.read_bytes() == b"unchanged desktop"
    if case == "runtime_data":
        assert (installation / "monitor.db").read_bytes() == b"do not modify"
    assert (data / "monitor.db").read_bytes() == b"user data"
