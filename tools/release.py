"""Build and verify release artifacts. Publishing remains an explicit gh/git step."""

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

try:
    from . import updater
except ImportError:
    import updater


ASSET_BASE = "https://github.com/TheLayya/tk_crm/releases/download"
DOWNLOAD_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
WINDOWS_INPUT_ROOTS = ("backend", "frontend", "desktop")
WINDOWS_INPUT_FILES = ("requirements-dev.txt",)
WINDOWS_IGNORED_PARTS = {
    ".git", ".venv", ".venv312", "venv", "env", "__pycache__", "node_modules", "dist", "build",
    "runtime", "bin", "obj", ".cache", ".pytest_cache", ".mypy_cache", "data", "logs",
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_once(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"Refusing to overwrite a different artifact: {path}")
        return
    with path.open("xb") as handle:
        handle.write(content)


def check_version(version):
    updater.version_tuple(version)
    if version.startswith("v"):
        raise ValueError("Use a version without the v prefix")


def asset_url(version, windows=False):
    check_version(version)
    name = f"TkCRM-{version}-win-x64-setup.exe" if windows else f"release-v{version}.tar.gz"
    return f"{ASSET_BASE}/v{version}/{name}"


def check_manifest(manifest):
    updater.validate_manifest(manifest)
    if manifest["package_url"] != asset_url(manifest["version"]):
        raise ValueError("Server URL must match the manifest version and canonical asset name")
    if "windows_package_url" in manifest or "windows_sha256" in manifest:
        if manifest.get("windows_package_url") != asset_url(manifest["version"], windows=True):
            raise ValueError("Windows URL must match the manifest version and canonical asset name")
        checksum = manifest.get("windows_sha256", "")
        if not isinstance(checksum, str) or not re.fullmatch(r"[a-f0-9]{64}", checksum):
            raise ValueError("Invalid Windows SHA-256")
    return manifest


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)


def source_files(repo, ref):
    commit = git(repo, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").decode().strip()
    files = {}
    for entry in git(repo, "ls-tree", "-r", "-z", commit).split(b"\0"):
        if not entry:
            continue
        info, raw_name = entry.split(b"\t", 1)
        mode, kind, blob = info.decode().split()
        name = raw_name.decode("utf-8")
        if updater.is_code_file(Path(name)):
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise ValueError(f"Release source contains a link or unsupported entry: {name}")
            files[name] = (blob, int(mode[-3:], 8))
    return commit, files


def _windows_input_path(path):
    path = Path(path)
    parts = path.parts
    if path.as_posix() in WINDOWS_INPUT_FILES:
        return True
    if not parts or parts[0] not in WINDOWS_INPUT_ROOTS:
        return False
    if any(part in WINDOWS_IGNORED_PARTS or part.startswith(".env") for part in parts):
        return False
    if path.name == ".coverage" or path.name.startswith(".coverage.") or path.name in {"coverage.xml", ".cover"}:
        return False
    return path.suffix.lower() not in {".db", ".sqlite", ".sqlite3", ".log", ".pyc"}


def windows_commit_files(repo, commit):
    expected = {}
    # Compare the commit, rather than the working index: staging an accidental
    # change must not let it enter a build under the old commit's provenance.
    for entry in git(repo, "ls-tree", "-r", "-z", commit).split(b"\0"):
        if not entry:
            continue
        info, raw_name = entry.split(b"\t", 1)
        name = raw_name.decode("utf-8")
        if _windows_input_path(name):
            mode, kind, blob = info.decode().split()
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise ValueError(f"Unsupported Windows build source entry: {name}")
            expected[name] = blob
    if not expected:
        raise ValueError("No Windows build inputs found in selected commit")
    return expected


def windows_filtered_blobs(repo, expected):
    # Normalize both sides with Git's clean/EOL filter. Some historical commits
    # store CRLF while the current checkout enables core.autocrlf.
    committed = source_blobs(repo, {name: (blob, 0o644) for name, blob in expected.items()})
    return {name: subprocess.check_output(
                ["git", "hash-object", "--path", name, "--stdin"], cwd=repo,
                input=committed[blob], stderr=subprocess.PIPE,
            ).decode().strip() for name, blob in expected.items()}


def verify_windows_source(repo, ref):
    """Verify Windows build inputs are a clean-filtered snapshot of one commit.

    The report is safe to retain as build evidence: it contains paths and hashes,
    never source content. Ignored build/runtime output is deliberately omitted;
    untracked source files in the input roots are rejected.
    """
    repo = Path(repo)
    commit = git(repo, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").decode().strip()
    expected = windows_commit_files(repo, commit)
    actual_paths = set()
    for root in WINDOWS_INPUT_ROOTS:
        for directory, folders, filenames in os.walk(repo / root):
            relative = Path(directory).relative_to(repo)
            folders[:] = [name for name in folders if _windows_input_path(relative / name)]
            for name in filenames:
                path = relative / name
                if _windows_input_path(path):
                    actual_paths.add(path.as_posix())
    actual_paths.update(name for name in WINDOWS_INPUT_FILES if (repo / name).is_file())
    untracked = actual_paths - set(expected)
    if untracked:
        raise ValueError("Untracked Windows build input(s): " + ", ".join(sorted(untracked)))
    paths = sorted(expected)
    for name in paths:
        working = repo / name
        if working.is_symlink() or not working.is_file():
            raise ValueError(f"Windows build input is missing: {name}")
        if "\n" in name or "\r" in name:
            raise ValueError("Windows build source filename contains a newline")
    expected_clean = windows_filtered_blobs(repo, expected)
    hashes = subprocess.check_output(["git", "hash-object", "--stdin-paths"], cwd=repo,
                                     input="".join(name + "\n" for name in paths).encode("utf-8"), stderr=subprocess.PIPE).decode().splitlines()
    if len(hashes) != len(paths):
        raise ValueError("Incomplete Windows input hash audit")
    records = []
    for name, actual in zip(paths, hashes):
        if actual != expected_clean[name]:
            raise ValueError(f"Windows build input differs from {commit}: {name}")
        records.append({"path": name, "git_blob": actual})
    return {"source_commit": commit, "verified": True, "file_count": len(records),
            "inputs_sha256": hashlib.sha256(json_bytes(records)).hexdigest(), "files": records}


def validate_windows_audits(evidence, evidence_dir, repo, windows_commit):
    reports = []
    for field in ("source_audit_before", "source_audit_after"):
        name = evidence.get(field)
        if not isinstance(name, str) or not name:
            raise ValueError(f"Windows evidence requires {field} report path")
        path = Path(name)
        if not path.is_absolute():
            path = Path(evidence_dir) / path
        report = read_json(path)
        if not isinstance(report, dict) or report.get("verified") is not True or report.get("source_commit") != windows_commit:
            raise ValueError(f"Windows {field} must verify the fixed Windows source commit")
        records = report.get("files")
        if not isinstance(records, list) or not records or type(report.get("file_count")) is not int or report["file_count"] != len(records):
            raise ValueError(f"Windows {field} has an invalid file count")
        for record in records:
            if not isinstance(record, dict) or set(record) != {"path", "git_blob"} or not isinstance(record["path"], str) or not isinstance(record["git_blob"], str) or not re.fullmatch(r"[a-f0-9]{40,64}", record["git_blob"]):
                raise ValueError(f"Windows {field} has invalid source records")
        actual = hashlib.sha256(json_bytes(records)).hexdigest()
        if report.get("inputs_sha256") != actual:
            raise ValueError(f"Windows {field} input digest differs from its records")
        reports.append(report)
    if reports[0]["files"] != reports[1]["files"] or reports[0]["inputs_sha256"] != reports[1]["inputs_sha256"]:
        raise ValueError("Windows build inputs changed between before/after audits")
    expected = windows_filtered_blobs(repo, windows_commit_files(repo, windows_commit))
    records = [{"path": name, "git_blob": blob} for name, blob in sorted(expected.items())]
    if reports[0]["files"] != records:
        raise ValueError("Windows build audit records differ from fixed source commit")
    return reports[0]["inputs_sha256"]


def source_blobs(repo, files):
    """Read committed bytes in one Git process, including arbitrary binary assets."""
    hashes = list(dict.fromkeys(blob for blob, _ in files.values()))
    payload = subprocess.check_output(["git", "-C", str(repo), "cat-file", "--batch"],
                                      input="".join(blob + "\n" for blob in hashes).encode(), stderr=subprocess.PIPE)
    stream, blobs = io.BytesIO(payload), {}
    for expected in hashes:
        blob, kind, size = stream.readline().decode().split()
        if blob != expected or kind != "blob":
            raise ValueError("Unexpected Git source blob response")
        blobs[blob] = stream.read(int(size))
        if len(blobs[blob]) != int(size) or stream.read(1) != b"\n":
            raise ValueError("Incomplete Git source blob response")
    return blobs


def check_source_version(files, blobs, version):
    for name, pattern in (
        ("backend/app/version.py", r'APP_VERSION\s*=\s*[\'"]([^\'"]+)[\'"]'),
        ("frontend/src/components/Layout.vue", r'const APP_VERSION\s*=\s*[\'"]([^\'"]+)[\'"]'),
    ):
        if name not in files:
            raise ValueError(f"Source version file is missing: {name}")
        content = blobs[files[name][0]].decode("utf-8")
        match = re.search(pattern, content)
        if not match or match[1] != version:
            raise ValueError(f"Source version differs from release: {name}")


def archive_metadata(archive, version):
    with tempfile.TemporaryDirectory(prefix="TkCRM-release-audit-") as directory:
        package = updater.prepare_release(archive, Path(directory) / "source", version)
        return read_json(package / "version.json")


def validate_server(archive, manifest, repo, ref):
    archive, repo = Path(archive), Path(repo)
    check_manifest(manifest)
    if sha256(archive) != manifest["sha256"]:
        raise ValueError("Server archive checksum mismatch")
    commit, files = source_files(repo, ref)
    blobs = source_blobs(repo, files)
    check_source_version(files, blobs, manifest["version"])
    with tempfile.TemporaryDirectory(prefix="TkCRM-release-audit-") as directory:
        package = updater.prepare_release(archive, Path(directory) / "source", manifest["version"])
        metadata = read_json(package / "version.json")
        if metadata.get("source_commit") != commit or manifest.get("source_commit", commit) != commit:
            raise ValueError("Server archive source commit mismatch")
        for field in ("version", "date", "changes"):
            if metadata.get(field) != manifest.get(field):
                raise ValueError(f"Server archive metadata differs: {field}")
        actual = {path.relative_to(package).as_posix() for path in package.rglob("*") if path.is_file()}
        if actual != set(files):
            raise ValueError("Server archive file list differs from source commit")
        for name, (blob, _) in files.items():
            if name != "version.json" and (package / name).read_bytes() != blobs[blob]:
                raise ValueError(f"Server archive source blob differs: {name}")
    return {
        "version": manifest["version"], "source_commit": commit,
        "archive": archive.name, "files": len(files), "bytes": archive.stat().st_size,
        "sha256": manifest["sha256"], "all_source_blobs_match": True,
        "pngs": sorted(name for name in files if name.lower().endswith(".png")),
    }


def prepare_server(repo, ref, version, release_date, changes, output_dir):
    check_version(version)
    date.fromisoformat(release_date)
    if not isinstance(changes, list) or not all(isinstance(item, str) for item in changes):
        raise ValueError("Changes JSON must contain an array of strings")
    repo, output_dir = Path(repo), Path(output_dir)
    commit, files = source_files(repo, ref)
    blobs = source_blobs(repo, files)
    check_source_version(files, blobs, version)
    metadata = {"version": version, "date": release_date, "changes": changes, "source_commit": commit}
    archive = output_dir / f"release-v{version}.tar.gz"
    with tempfile.TemporaryDirectory(prefix="TkCRM-release-build-") as directory:
        temporary = Path(directory) / archive.name
        with temporary.open("xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as target:
                for name, (blob, mode) in sorted(files.items()):
                    content = json_bytes(metadata) if name == "version.json" else blobs[blob]
                    member = tarfile.TarInfo(name)
                    member.size, member.mode, member.mtime = len(content), mode, 0
                    target.addfile(member, io.BytesIO(content))
        manifest = {**metadata, "package_url": asset_url(version), "sha256": sha256(temporary)}
        audit = validate_server(temporary, manifest, repo, commit)
        # Only retain an artifact once its contents have passed the updater and source audit.
        write_once(archive, temporary.read_bytes())
    write_once(output_dir / "server-candidate.json", json_bytes(manifest))
    write_once(output_dir / "server-audit.json", json_bytes(audit))
    return audit


def compose_manifest(server, server_archive, windows_exe, evidence, version, output, repo, evidence_dir=None):
    check_manifest(server)
    check_version(version)
    if server["version"] != version or evidence.get("version") != version:
        raise ValueError("Both artifacts must use the requested release version")
    if sha256(server_archive) != server["sha256"]:
        raise ValueError("Server archive checksum mismatch")
    metadata = archive_metadata(server_archive, version)
    commit = metadata.get("source_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[a-f0-9]{40,64}", commit):
        raise ValueError("Server archive must record a fixed source commit")
    if server.get("source_commit", commit) != commit:
        raise ValueError("Server candidate source commit differs from archive")
    validate_server(server_archive, server, repo, commit)
    windows_commit, windows_files = source_files(repo, evidence.get("source_commit", ""))
    if evidence.get("source_commit") != windows_commit:
        raise ValueError("Windows evidence must record the full fixed source commit")
    _, server_files = source_files(repo, commit)
    # A later documentation/manifest commit may legitimately build a missing installer.
    # Its packaged application and migrations must still match the published server.
    server_payload = {name: blob for name, blob in server_files.items() if Path(name).parts[0] in {"backend", "frontend"}}
    windows_payload = {name: blob for name, blob in windows_files.items() if Path(name).parts[0] in {"backend", "frontend"}}
    if server_payload != windows_payload:
        raise ValueError("Windows and server application source blobs differ")
    for field in ("version", "date", "changes"):
        if metadata.get(field) != server.get(field):
            raise ValueError(f"Server archive metadata differs: {field}")
    windows_exe = Path(windows_exe)
    if windows_exe.name != f"TkCRM-{version}-win-x64-setup.exe":
        raise ValueError("Windows installer filename differs from requested version")
    digest = sha256(windows_exe)
    if evidence.get("verified") is not True or evidence.get("source_verified") is not True:
        raise ValueError("Windows evidence must record a verified installer with its actual SHA-256")
    for field in ("audit_exit", "smoke_exit"):
        if type(evidence.get(field)) is not int or evidence[field] != 0:
            raise ValueError(f"Windows evidence {field} must be integer 0")
    if evidence.get("sha256") != digest:
        raise ValueError("Windows evidence SHA-256 differs from installer")
    if evidence.get("package_url") != asset_url(version, windows=True):
        raise ValueError("Windows evidence must name the canonical release URL")
    input_digest = validate_windows_audits(evidence, evidence_dir or Path.cwd(), repo, windows_commit)
    manifest = {**server, "source_commit": commit, "server_source_commit": commit,
                "windows_source_commit": windows_commit,
                "windows_package_url": asset_url(version, windows=True), "windows_sha256": digest}
    check_manifest(manifest)
    write_once(output, json_bytes(manifest))
    return {"version": version, "server_source_commit": commit, "windows_source_commit": windows_commit,
            "application_source_blobs_match": True, "manifest": str(output),
            "server_sha256": server["sha256"], "windows_sha256": digest, "windows_inputs_sha256": input_digest}


def check_download_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in DOWNLOAD_HOSTS or parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValueError("Untrusted release download redirect")


class ReleaseRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_download_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def verify_download(manifest, output_dir):
    check_manifest(manifest)
    output_dir = Path(output_dir)
    opener = build_opener(ReleaseRedirectHandler())
    assets = [("server", "package_url", "sha256", updater.MAX_PACKAGE_BYTES)]
    if "windows_package_url" in manifest:
        assets.append(("windows", "windows_package_url", "windows_sha256", 1024 * 1024 * 1024))
    results = []
    with tempfile.TemporaryDirectory(prefix="TkCRM-public-download-") as directory:
        for kind, url_field, hash_field, limit in assets:
            url = manifest[url_field]
            target = Path(directory) / url.rsplit("/", 1)[-1]
            digest, total = hashlib.sha256(), 0
            with opener.open(Request(url, headers={"User-Agent": "tk-crm-release-verification"}), timeout=60) as response, target.open("xb") as output:
                final_url = response.geturl()
                check_download_url(final_url)
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > limit:
                        raise ValueError(f"{kind} release exceeds download size limit")
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != manifest[hash_field]:
                raise ValueError(f"{kind} public download checksum mismatch")
            output_dir.mkdir(parents=True, exist_ok=True)
            destination = output_dir / target.name
            if destination.exists():
                if sha256(destination) != digest.hexdigest():
                    raise ValueError(f"Refusing to overwrite a different download: {destination}")
            else:
                with target.open("rb") as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output)
            results.append({"asset": kind, "package_url": url, "final_host": urlparse(final_url).hostname,
                            "bytes": total, "sha256": digest.hexdigest(), "verified": True})
    report = {"version": manifest["version"], "assets": results}
    write_once(output_dir / "download-verification.json", json_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare-server", help="Build an immutable server package from fixed Git blobs")
    prepare.add_argument("--repo", type=Path, default=Path.cwd())
    prepare.add_argument("--ref", required=True)
    prepare.add_argument("--version", required=True)
    prepare.add_argument("--date", required=True)
    prepare.add_argument("--changes-json", type=Path, required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    validate = commands.add_parser("validate-server", help="Audit archive contents against the fixed source commit")
    validate.add_argument("--repo", type=Path, default=Path.cwd())
    validate.add_argument("--ref", required=True)
    validate.add_argument("--archive", type=Path, required=True)
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--output", type=Path)
    compose = commands.add_parser("compose-manifest", help="Combine verified server and Windows artifacts")
    compose.add_argument("--server-candidate", type=Path, required=True)
    compose.add_argument("--repo", type=Path, default=Path.cwd())
    compose.add_argument("--server-archive", type=Path, required=True)
    compose.add_argument("--windows-exe", type=Path, required=True)
    compose.add_argument("--windows-evidence", type=Path, required=True)
    compose.add_argument("--version", required=True)
    compose.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify-download", help="Download and hash the actual public GitHub assets")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--output-dir", type=Path, required=True)
    inputs = commands.add_parser("verify-windows-source", help="Audit committed Windows build inputs before and after a build")
    inputs.add_argument("--repo", type=Path, default=Path.cwd())
    inputs.add_argument("--ref", required=True)
    inputs.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare-server":
            result = prepare_server(args.repo, args.ref, args.version, args.date, read_json(args.changes_json), args.output_dir)
        elif args.command == "validate-server":
            result = validate_server(args.archive, read_json(args.manifest), args.repo, args.ref)
            if args.output:
                write_once(args.output, json_bytes(result))
        elif args.command == "compose-manifest":
            result = compose_manifest(read_json(args.server_candidate), args.server_archive, args.windows_exe,
                                      read_json(args.windows_evidence), args.version, args.output, args.repo, args.windows_evidence.parent)
        elif args.command == "verify-windows-source":
            result = verify_windows_source(args.repo, args.ref)
            if args.output:
                write_once(args.output, json_bytes(result))
        else:
            result = verify_download(read_json(args.manifest), args.output_dir)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Release operation failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
