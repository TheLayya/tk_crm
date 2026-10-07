# Windows build and acceptance

The shipped Windows app includes a frozen Python server, frontend assets, self-contained .NET desktop shell and updater. Updating only frontend/dist or shipping an old setup EXE does not update the actual installed backend.

## Build

Use the tracked scripts from the repository root. They resolve version from `backend/app/version.py`:

```powershell
python tools/release.py verify-windows-source --repo . --ref SOURCE_COMMIT --output .orchestration/release-X.Y.Z/source-before.json
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/publish.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/build-installer.ps1 -BaseManifestPath .orchestration/release-X.Y.Z/server-candidate.json
```

`publish.ps1` rebuilds frontend, PyInstaller server, .NET updater and desktop runtime. It clears only checked build paths under the repository. `build-installer.ps1` validates the Microsoft WebView2 bootstrapper signature, builds Inno Setup, generates the candidate Windows manifest and runs the complete release audit. Pass the new version's server candidate; the root online manifest deliberately still names the previous version at this stage. For an already published server version, the matching root manifest can be the base.

Required tools: repository Python environment with PyInstaller/dependencies, Node/npm, .NET 10 SDK, Inno Setup 6 and Playwright/browser dependencies used by existing audits. Existing scripts resolve local tool paths; inspect exact errors before changing paths or downloading anything.

Required results: package/frontend parity, no runtime data, updater safety/lock/readiness/process/rollback tests, frozen database migration, no-toolchain smoke, business-page layout checks and Windows manifest checksum. Record publish and audit actual exit codes and logs.

## Installer / online smoke

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/tests/installer-smoke.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/tests/online-update-smoke.ps1 -ManifestPath CANDIDATE_MANIFEST
```

The installer and online scripts refuse an existing TkCRM installation or running user app because Inno uses a fixed AppId. Preserve that guard. Use an isolated machine/Windows user when the current user has an installation. Never uninstall or stop a user's app just to enable a smoke test. Report this as pending evidence until tested in isolation.

The online script requires uploaded GitHub assets; it uses an isolated old installation and synthetic encrypted data. Its production updater entry proves download/hash/install/migrate/readiness/history/uninstall, not an actual click in the old UI. Keep this distinction in the handover. It currently defaults to a pinned historical 1.1.15 installer; inspect/update the fixture deliberately when changing the old baseline.

Build evidence JSON used by `compose-manifest`:

```json
{
  "version": "X.Y.Z",
  "package_url": "https://github.com/TheLayya/tk_crm/releases/download/vX.Y.Z/TkCRM-X.Y.Z-win-x64-setup.exe",
  "sha256": "REAL_SHA256",
  "source_commit": "ACTUAL_WINDOWS_BUILD_COMMIT",
  "verified": true,
  "source_verified": true,
  "source_audit_before": "source-before.json",
  "source_audit_after": "source-after.json",
  "audit_exit": 0,
  "smoke_exit": 0
}
```

Set `verified` only after matching checks succeeded for this exact installer hash. Repeat `verify-windows-source` after building and smoke testing, saving `source-after.json`. The two audit paths are relative to the evidence JSON directory; compose checks their file lists and recomputed digests against the selected commit. `audit_exit` and `smoke_exit` must be integer zero; the manifest tool rejects missing or failed gates. This does not replace public download verification. If server/Windows provenance differs only by manifest or docs commits, record both source commits and verify application blobs match; do not pretend both came from one commit.

Physical mixed-DPI dual monitors, clean machines without WebView2, all business-page manual acceptance and code signing are separate evidence. Do not claim them from browser viewport tests or a valid Microsoft bootstrapper signature.

The build scripts operate on the checkout's files. Build in a clean fixed-commit worktree/source copy, or run a build-input audit before and after the build that checks tracked and untracked backend, frontend, desktop, updater and installer inputs against the selected commit. A dirty Windows build must not claim fixed-commit provenance.
