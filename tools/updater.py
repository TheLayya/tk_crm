import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from urllib.request import Request, urlopen


MAX_PACKAGE_BYTES = 128 * 1024 * 1024
MAX_EXTRACTED_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 20000
CODE_ROOTS = {"backend", "frontend", "tools"}
CODE_FILES = {
    ".gitattributes",
    ".gitignore",
    "CLAUDE.md",
    "LICENSE",
    "README.md",
    "deploy.sh",
    "docker-compose.yml",
    "start.py",
    "version.json",
}
PRESERVED_PARTS = {"data", "backups", "logs", "node_modules", "venv", "__pycache__", ".git"}


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise ValueError("Invalid release version")
    return tuple(int(part) for part in value.removeprefix("v").split("."))


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise ValueError("Invalid release manifest")
    version_tuple(manifest.get("version"))
    checksum = manifest.get("sha256", "")
    if not isinstance(checksum, str) or not re.fullmatch(r"[a-f0-9]{64}", checksum):
        raise ValueError("Release SHA-256 is required")
    url = urlparse(manifest.get("package_url", ""))
    if url.scheme != "https" or url.username or url.password or url.fragment:
        raise ValueError("Release must use HTTPS")
    if url.hostname != "github.com" or not url.path.startswith("/TheLayya/tk_crm/releases/download/"):
        raise ValueError("Release must be a published project asset")
    if not isinstance(manifest.get("changes", []), list) or not all(
        isinstance(item, str) for item in manifest.get("changes", [])
    ):
        raise ValueError("Invalid changelog")
    return manifest


def download_package(manifest, target):
    validate_manifest(manifest)
    digest = hashlib.sha256()
    total = 0
    request = Request(manifest["package_url"], headers={"User-Agent": "tk-crm-updater"})
    with urlopen(request, timeout=30) as response, Path(target).open("xb") as output:
        final_url = urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname not in {
            "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"
        }:
            raise ValueError("Untrusted package redirect")
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_PACKAGE_BYTES:
                raise ValueError("Release archive is too large")
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != manifest["sha256"]:
        raise ValueError("Release checksum mismatch")


def safe_extract(archive, destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError("Extraction requires a new staging directory")
    with tarfile.open(archive, "r:gz") as handle:
        members = handle.getmembers()
        if len(members) > MAX_MEMBERS or sum(member.size for member in members) > MAX_EXTRACTED_BYTES:
            raise ValueError("Release extraction limits exceeded")
        names = set()
        for member in members:
            parts = PurePosixPath(member.name).parts
            if not parts or member.name.startswith("/") or "\\" in member.name or ":" in member.name:
                raise ValueError("Unsafe archive path")
            if any(part in {".", ".."} or part.rstrip(" .") != part for part in parts):
                raise ValueError("Unsafe archive path")
            if not (member.isfile() or member.isdir()):
                raise ValueError("Archive links and special files are forbidden")
            name = "/".join(parts).casefold()
            if name in names:
                raise ValueError("Duplicate archive path")
            names.add(name)
        destination.mkdir(parents=True)
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with handle.extractfile(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
    return destination


def is_code_file(relative):
    parts = Path(relative).parts
    if not parts:
        return False
    if any(part in PRESERVED_PARTS or part.startswith(".venv") for part in parts):
        return False
    if any(part == ".env" or part.startswith(".env.") for part in parts):
        return False
    if Path(relative).suffix.lower() in {".db", ".sqlite", ".sqlite3", ".log"}:
        return False
    return parts[0] in CODE_ROOTS or (len(parts) == 1 and parts[0] in CODE_FILES)


def prepare_release(archive, destination, expected_version):
    version_tuple(expected_version)
    extracted = safe_extract(archive, destination)
    package = extracted
    if not (package / "version.json").is_file():
        children = list(package.iterdir())
        if len(children) != 1 or not children[0].is_dir():
            raise ValueError("Release root is missing")
        package = children[0]
    metadata = json.loads((package / "version.json").read_text(encoding="utf-8"))
    if metadata.get("version") != expected_version:
        raise ValueError("Package version differs from requested release")
    for required in ["backend/app/main.py", "backend/alembic.ini", "frontend/package.json", "docker-compose.yml"]:
        if not (package / required).is_file():
            raise ValueError("Incomplete release package")
    for source in package.rglob("*"):
        if source.is_file() and not is_code_file(source.relative_to(package)):
            raise ValueError("Release contains runtime data or unsupported files")
    return package


def backup_database(database, destination):
    database, destination = Path(database), Path(destination)
    if not database.is_file() or destination.exists():
        raise ValueError("Database missing or backup already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(destination) as backup:
            source.backup(backup)
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Database backup integrity check failed")


def remove_database(database):
    database = Path(database)
    for suffix in ["", "-wal", "-shm"]:
        target = Path(str(database) + suffix)
        for attempt in range(10):
            try:
                target.unlink(missing_ok=True)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.2)


def confined_path(root, relative):
    target = root / relative
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Path escapes installation directory")
    for parent in [target, *target.parents]:
        if parent == root:
            break
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError("Installation paths cannot contain links")
    return target


def replace_code(root, source, recovery):
    changes = []
    for incoming in sorted(source.rglob("*")):
        if not incoming.is_file():
            continue
        relative = incoming.relative_to(source)
        if not is_code_file(relative):
            raise ValueError("Runtime files cannot be replaced")
        target = confined_path(root, relative)
        saved = recovery / "code" / relative
        existed = target.is_file()
        if target.exists() and not existed:
            raise ValueError("Code target is not a file")
        if existed:
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
        changes.append((relative, existed))
        (recovery / "changes.json").write_text(json.dumps([(str(path), old) for path, old in changes]), encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(incoming, target)
    return changes


def restore_code(root, recovery):
    changes_file = recovery / "changes.json"
    if not changes_file.is_file():
        return
    for relative, existed in reversed(json.loads(changes_file.read_text(encoding="utf-8"))):
        target = confined_path(root, relative)
        if existed:
            shutil.copy2(recovery / "code" / relative, target)
        else:
            target.unlink(missing_ok=True)


def apply_release(root, manifest, lifecycle=None):
    validate_manifest(manifest)
    root = Path(root).resolve(strict=True)
    if lifecycle is None:
        raise ValueError("A configured service lifecycle is required")
    recovery = root / "backups" / (datetime.now().strftime("update-%Y%m%d%H%M%S-") + uuid.uuid4().hex[:8])
    recovery.mkdir(parents=True)
    database = confined_path(root, Path("backend/data/monitor.db"))
    database_existed = database.is_file()
    database_backup = recovery / "monitor.db"
    stopped = False
    modified = False
    try:
        archive = recovery / "release.tar.gz"
        download_package(manifest, archive)
        source = prepare_release(archive, recovery / "source", manifest["version"])
        lifecycle("stop", root)
        stopped = True
        if database.exists():
            backup_database(database, database_backup)
        modified = True
        replace_code(root, source, recovery)
        lifecycle("migrate", root)
        lifecycle("start", root)
        lifecycle("health", root)
    except Exception:
        if stopped:
            lifecycle("stop", root)
            if modified:
                restore_code(root, recovery)
            if database_backup.exists():
                for suffix in ["-wal", "-shm"]:
                    confined_path(root, Path("backend/data/monitor.db" + suffix)).unlink(missing_ok=True)
                shutil.copy2(database_backup, database)
            elif not database_existed:
                remove_database(database)
            lifecycle("start", root)
            lifecycle("health", root)
        raise
    return recovery


class ServiceLifecycle:
    def __init__(self, config):
        self.config = config
        for phase in ["stop", "migrate", "start"]:
            commands = config.get(phase)
            if not isinstance(commands, list) or not commands or not all(
                isinstance(command, list) and command and all(isinstance(arg, str) for arg in command)
                for command in commands
            ):
                raise ValueError("Lifecycle requires fixed argument arrays for " + phase)
        if not config.get("health_url"):
            raise ValueError("Lifecycle health URL is required")

    def __call__(self, phase, root):
        if phase == "health":
            deadline = time.monotonic() + self.config.get("health_timeout", 120)
            while time.monotonic() < deadline:
                try:
                    with urlopen(self.config["health_url"], timeout=3) as response:
                        payload = json.loads(response.read(4096))
                        if response.status == 200 and payload.get("status") == "ok":
                            return
                except (OSError, ValueError):
                    pass
                time.sleep(2)
            raise RuntimeError("Service failed health check")
        for command in self.config[phase]:
            subprocess.run(command, cwd=root, check=True, timeout=self.config.get("command_timeout", 900))


def main():
    parser = argparse.ArgumentParser(description="Safely stage or apply a release")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--manifest")
    parser.add_argument("--manifest-file", type=Path)
    parser.add_argument("--staging", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--lifecycle", type=Path)
    args = parser.parse_args()
    if args.apply:
        if not args.root or not args.manifest:
            raise SystemExit("--root and --manifest are required with --apply")
        if not args.lifecycle:
            raise SystemExit("--lifecycle is required with --apply")
        lifecycle = ServiceLifecycle(json.loads(args.lifecycle.read_text(encoding="utf-8")))
        apply_release(args.root, validate_manifest(json.loads(args.manifest)), lifecycle)
        return
    if not args.manifest_file or not args.staging:
        raise SystemExit("--manifest-file and --staging are required without --apply")
    manifest = validate_manifest(json.loads(args.manifest_file.read_text(encoding="utf-8")))
    args.staging.mkdir(parents=True, exist_ok=False)
    archive = args.staging / "release.tar.gz"
    download_package(manifest, archive)
    package = prepare_release(archive, args.staging / "source", manifest["version"])
    print(json.dumps({"status": "staged", "version": manifest["version"], "path": str(package)}))


if __name__ == "__main__":
    main()
