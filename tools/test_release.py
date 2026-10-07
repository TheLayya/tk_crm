"""Isolated release checks: python -m unittest tools.test_release -v."""

import hashlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="tk-crm-release-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.version = "1.2.3"
        files = {
            "version.json": '{"version":"1.2.3"}',
            "backend/app/main.py": "# source\n",
            "backend/app/version.py": 'APP_VERSION = "1.2.3"\n',
            "backend/alembic.ini": "[alembic]\n",
            "frontend/package.json": "{}\n",
            "frontend/src/components/Layout.vue": "const APP_VERSION = '1.2.3'\n",
            "frontend/src/new.png": b"\x89PNG\r\n\x1a\n\x00\xff binary asset",
            "frontend/src/new-component.vue": "<template>new feature</template>\n",
            "backend/.env.example": "EXAMPLE_ONLY=yes\n",
            "backend/.env": "REAL_SECRET=excluded\n",
            "backend/.env.production": "ANOTHER_SECRET=excluded\n",
            "backend/data/runtime.db": b"live database",
            "backend/node_modules/generated.js": "generated\n",
            "docs/build.log": "not source\n",
            "docker-compose.yml": "services: {}\n",
            "deploy.sh": "#!/bin/sh\n",
            "desktop/private.txt": "not a server file\n",
        }
        for name, content in files.items():
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content if isinstance(content, bytes) else content.encode())
        self.git("init", "--quiet")
        self.git("add", ".")
        self.git("-c", "user.name=Release Test", "-c", "user.email=release@example.invalid", "commit", "--quiet", "-m", "fixture")
        self.commit = self.git("rev-parse", "HEAD").decode().strip()
        # A dirty worktree must never enter a fixed-commit package.
        (self.repo / "backend/app/main.py").write_text("# worktree has different bytes\n")
        (self.repo / "frontend/src/untracked.vue").write_text("untracked")
        self.output = self.root / "output"
        self.audit = release.prepare_server(self.repo, self.commit, self.version, "2026-10-07", ["新增功能"], self.output)
        self.archive = self.output / "release-v1.2.3.tar.gz"
        self.manifest = release.read_json(self.output / "server-candidate.json")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.PIPE)

    def source_evidence(self, commit, directory):
        (self.repo / "backend/app/main.py").write_text("# source\n")
        (self.repo / "frontend/src/untracked.vue").unlink(missing_ok=True)
        report = release.verify_windows_source(self.repo, commit)
        release.write_once(directory / "before.json", release.json_bytes(report))
        release.write_once(directory / "after.json", release.json_bytes(report))
        return {"source_audit_before": str(directory / "before.json"),
                "source_audit_after": str(directory / "after.json")}

    def test_fixed_blobs_binary_assets_exclusions_and_determinism(self):
        extracted = release.updater.prepare_release(self.archive, self.root / "extracted", self.version)
        self.assertEqual((extracted / "backend/app/main.py").read_text(), "# source\n")
        self.assertEqual((extracted / "frontend/src/new.png").read_bytes(), b"\x89PNG\r\n\x1a\n\x00\xff binary asset")
        self.assertTrue((extracted / "frontend/src/new-component.vue").is_file())
        self.assertTrue((extracted / "backend/.env.example").is_file())
        for name in ("backend/.env", "backend/.env.production", "backend/data/runtime.db", "backend/node_modules/generated.js", "docs/build.log", "desktop/private.txt", "frontend/src/untracked.vue"):
            self.assertFalse((extracted / name).exists(), name)
        metadata = release.read_json(extracted / "version.json")
        self.assertEqual(metadata["source_commit"], self.commit)
        self.assertNotIn("sha256", metadata)
        self.assertNotIn("package_url", metadata)
        again = self.root / "again"
        release.prepare_server(self.repo, self.commit, self.version, "2026-10-07", ["新增功能"], again)
        self.assertEqual(self.archive.read_bytes(), (again / self.archive.name).read_bytes())
        release.prepare_server(self.repo, self.commit, self.version, "2026-10-07", ["新增功能"], self.output)
        self.assertTrue(self.audit["all_source_blobs_match"])

    def test_different_artifact_and_source_version_are_rejected(self):
        before = self.archive.read_bytes()
        with self.assertRaisesRegex(ValueError, "overwrite"):
            release.prepare_server(self.repo, self.commit, self.version, "2026-10-08", ["different notes"], self.output)
        self.assertEqual(self.archive.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, "Source version differs"):
            release.prepare_server(self.repo, self.commit, "1.2.4", "2026-10-07", [], self.root / "wrong")
        wrong = {**self.manifest, "sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "checksum"):
            release.validate_server(self.archive, wrong, self.repo, self.commit)

    def test_audit_detects_missing_and_modified_blobs(self):
        source = release.updater.prepare_release(self.archive, self.root / "tamper", self.version)
        (source / "frontend/src/new.png").write_bytes(b"tampered PNG")
        changed = self.root / "changed.tar.gz"
        import tarfile
        with tarfile.open(changed, "w:gz") as target:
            for path in source.rglob("*"):
                if path.is_file():
                    target.add(path, arcname=path.relative_to(source).as_posix())
        candidate = {**self.manifest, "sha256": release.sha256(changed)}
        with self.assertRaisesRegex(ValueError, "source blob differs"):
            release.validate_server(changed, candidate, self.repo, self.commit)

    def test_manifest_merge_requires_real_hash_and_same_source_evidence(self):
        exe = self.root / "TkCRM-1.2.3-win-x64-setup.exe"
        exe.write_bytes(b"fixture executable bytes; not claimed to be a Windows smoke test")
        evidence = {"version": self.version, "package_url": release.asset_url(self.version, windows=True),
                    "sha256": release.sha256(exe), "source_commit": self.commit, "verified": True,
                    "source_verified": True, "audit_exit": 0, "smoke_exit": 0}
        evidence.update(self.source_evidence(self.commit, self.root / "source-audits"))
        final = self.root / "version.json"
        # Legacy server candidates get their fixed source commit from the audited archive.
        server = {key: value for key, value in self.manifest.items() if key != "source_commit"}
        release.compose_manifest(server, self.archive, exe, evidence, self.version, final, self.repo)
        result = release.read_json(final)
        self.assertEqual(result["sha256"], release.sha256(self.archive))
        self.assertEqual(result["windows_sha256"], release.sha256(exe))
        self.assertEqual(result["source_commit"], self.commit)
        for field, value in (("verified", False), ("source_verified", False), ("audit_exit", 1), ("smoke_exit", 1), ("audit_exit", False), ("audit_exit", None), ("smoke_exit", True), ("smoke_exit", "0"), ("source_audit_before", None), ("source_audit_after", ""), ("sha256", "0" * 64), ("version", "1.2.4"), ("package_url", "https://example.invalid/installer.exe")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                release.compose_manifest(server, self.archive, exe, {**evidence, field: value}, self.version, self.root / "bad.json", self.repo)
        self.assertFalse((self.root / "bad.json").exists())
        # A documentation-only later commit is a valid installer backfill; changing
        # application or migration bytes under the same version is forbidden.
        (self.repo / "backend/app/main.py").write_text("# source\n")
        (self.repo / "README.md").write_text("documentation-only release follow-up\n")
        self.git("add", "README.md")
        self.git("-c", "user.name=Release Test", "-c", "user.email=release@example.invalid", "commit", "--quiet", "-m", "release documentation")
        newer = self.git("rev-parse", "HEAD").decode().strip()
        output = self.root / "backfill.json"
        later_evidence = {**evidence, "source_commit": newer, **self.source_evidence(newer, self.root / "later-audits")}
        release.compose_manifest(server, self.archive, exe, later_evidence, self.version, output, self.repo)
        self.assertEqual(release.read_json(output)["server_source_commit"], self.commit)
        self.assertEqual(release.read_json(output)["windows_source_commit"], newer)
        (self.repo / "backend/app/main.py").write_text("# changed app\n")
        self.git("add", "backend/app/main.py")
        self.git("-c", "user.name=Release Test", "-c", "user.email=release@example.invalid", "commit", "--quiet", "-m", "application change")
        different = self.git("rev-parse", "HEAD").decode().strip()
        with self.assertRaisesRegex(ValueError, "application source blobs differ"):
            release.compose_manifest(server, self.archive, exe, {**evidence, "source_commit": different}, self.version, self.root / "bad.json", self.repo)

    def test_windows_evidence_reports_are_rehashed_and_bound_to_source_commit(self):
        directory = self.root / "evidence"
        self.source_evidence(self.commit, directory)
        original = release.read_json(directory / "before.json")
        evidence = {"source_audit_before": "before.json", "source_audit_after": "after.json"}
        result = release.validate_windows_audits(evidence, directory, self.repo, self.commit)
        self.assertEqual(result, original["inputs_sha256"])
        bad = [
            {**original, "verified": False},
            {**original, "source_commit": "f" * 40},
            {**original, "file_count": True},
            {**original, "file_count": original["file_count"] + 1},
            {**original, "inputs_sha256": "0" * 64},
        ]
        omitted = original["files"][:-1]
        bad.append({**original, "file_count": len(omitted), "files": omitted,
                    "inputs_sha256": hashlib.sha256(release.json_bytes(omitted)).hexdigest()})
        changed = [{**record} for record in original["files"]]
        changed[0]["git_blob"] = "0" * 40
        bad.append({**original, "files": changed,
                    "inputs_sha256": hashlib.sha256(release.json_bytes(changed)).hexdigest()})
        for index, report in enumerate(bad):
            with self.subTest(index=index):
                # Equal fabricated before/after data must still match fixed Git
                # inputs, so two matching JSON claims cannot satisfy provenance.
                (directory / "before.json").write_bytes(release.json_bytes(report))
                (directory / "after.json").write_bytes(release.json_bytes(report))
                with self.assertRaises(ValueError):
                    release.validate_windows_audits(evidence, directory, self.repo, self.commit)
        (directory / "before.json").write_bytes(release.json_bytes(original))
        (directory / "after.json").write_bytes(release.json_bytes(bad[-1]))
        with self.assertRaisesRegex(ValueError, "changed between"):
            release.validate_windows_audits(evidence, directory, self.repo, self.commit)
        (directory / "after.json").unlink()
        with self.assertRaises(FileNotFoundError):
            release.validate_windows_audits(evidence, directory, self.repo, self.commit)

    def test_windows_input_audit_handles_crlf_and_rejects_changed_or_hidden_inputs(self):
        (self.repo / "backend/app/main.py").write_text("# source\n")
        (self.repo / "frontend/src/untracked.vue").unlink()
        (self.repo / ".gitattributes").write_text("*.py text eol=lf\n")
        (self.repo / ".gitignore").write_text("desktop/hidden-source.cs\n")
        (self.repo / "desktop/app.cs").write_text("// committed desktop input\n")
        self.git("add", ".gitattributes", ".gitignore", "desktop/app.cs")
        self.git("-c", "user.name=Release Test", "-c", "user.email=release@example.invalid", "commit", "--quiet", "-m", "Windows source fixture")
        commit = self.git("rev-parse", "HEAD").decode().strip()
        (self.repo / "backend/app/main.py").write_bytes(b"# source\r\n")
        report = release.verify_windows_source(self.repo, commit)
        self.assertTrue(report["verified"])
        self.assertIn("desktop/app.cs", [item["path"] for item in report["files"]])
        before = report["inputs_sha256"]
        for name in ("desktop/build/compiled.exe", "desktop/TkCrm.Desktop/obj/generated.cs", "desktop/runtime/windows-x64/compiled.dll", "backend/__pycache__/cached.pyc"):
            output = self.repo / name
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"generated runtime output")
        self.assertEqual(release.verify_windows_source(self.repo, commit)["inputs_sha256"], before)
        (self.repo / "desktop/app.cs").write_text("// dirty build input\n")
        with self.assertRaisesRegex(ValueError, "desktop/app.cs"):
            release.verify_windows_source(self.repo, commit)
        self.git("add", "desktop/app.cs")
        with self.assertRaisesRegex(ValueError, "desktop/app.cs"):
            release.verify_windows_source(self.repo, commit)
        (self.repo / "desktop/app.cs").write_text("// committed desktop input\n")
        hidden = self.repo / "desktop/hidden-source.cs"
        hidden.write_text("// ignored C# still enters wildcard compilation\n")
        with self.assertRaisesRegex(ValueError, "Untracked.*hidden-source.cs"):
            release.verify_windows_source(self.repo, commit)
        hidden.unlink()
        (self.repo / "frontend/src/new-component.vue").unlink()
        with self.assertRaisesRegex(ValueError, "input is missing"):
            release.verify_windows_source(self.repo, commit)

    def test_public_download_checks_hashes_and_redirects(self):
        payload = self.archive.read_bytes()
        class Response(io.BytesIO):
            def geturl(self):
                return "https://release-assets.githubusercontent.com/fixture.tar.gz"
        class Opener:
            def open(self, *args, **kwargs):
                return Response(payload)
        with patch.object(release, "build_opener", return_value=Opener()):
            report = release.verify_download(self.manifest, self.root / "download")
            self.assertEqual(report["assets"][0]["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertTrue(report["assets"][0]["verified"])
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                release.verify_download({**self.manifest, "sha256": "0" * 64}, self.root / "bad-download")
        self.assertFalse((self.root / "bad-download/download-verification.json").exists())
        installer = b"public installer fixture"
        combined = {**self.manifest, "windows_package_url": release.asset_url(self.version, windows=True),
                    "windows_sha256": hashlib.sha256(installer).hexdigest()}
        class TwoAssetOpener:
            def open(self, request, **kwargs):
                return Response(installer if request.full_url.endswith(".exe") else payload)
        with patch.object(release, "build_opener", return_value=TwoAssetOpener()):
            report = release.verify_download(combined, self.root / "both-downloads")
            self.assertEqual([item["asset"] for item in report["assets"]], ["server", "windows"])
            with self.assertRaisesRegex(ValueError, "windows public download checksum mismatch"):
                release.verify_download({**combined, "windows_sha256": "0" * 64}, self.root / "bad-windows-download")
        self.assertFalse((self.root / "bad-windows-download/download-verification.json").exists())
        for url in ("http://github.com/file", "https://evil.invalid/file", "https://github.com:444/file", "https://user@github.com/file"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "Untrusted"):
                release.ReleaseRedirectHandler().redirect_request(None, None, 302, "Found", {}, url)


if __name__ == "__main__":
    unittest.main()
