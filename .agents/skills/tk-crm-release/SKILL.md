---
name: tk-crm-release
description: "Package, validate, publish, or update TkCRM server/Docker releases and Windows installers, including synchronized manifests and release evidence."
license: MIT
---

# TkCRM Release

Use this skill when releasing this repository. A normal release includes both the server/Docker archive and Windows installer; an explicit partial release may omit a platform but must say so and omit its manifest fields.

## Repository and permission boundaries

- Resolve the repository with git rev-parse --show-toplevel. Read the latest release handover, current root version.json, backend/app/version.py and frontend/src/components/Layout.vue. Historical notes are evidence, not current state.
- The team server must be upgraded by the user's webpage click. Publishing assets does not authorize calling /api/updates/apply, SSH rebuilds/restarts or source overwrites. Check other server actions against the current user authorization.
- Select Git files individually; preserve user archives, backups, staging and deleted screenshots. Never stage .env, databases, runtime data or logs.
- Never overwrite a published asset or reuse a version for a different payload. Windows 1.1.16 is not a Windows 1.1.17 asset.
- A Windows installer build must use a clean fixed-commit checkout (or a recorded before/after input-blob audit) that includes backend, frontend, desktop, updater and installer inputs. A dirty working-tree build cannot be used as provenance.
- Windows evidence must include before/after input audit paths, `source_verified: true`, `audit_exit: 0`, and `smoke_exit: 0`; the manifest tool checks the input records and rejects missing or failed gates.

## Workflow

1. Agree on version and platforms from the task; update backend and frontend version/changelog. Keep the previous complete online manifest until new assets are public. Package-internal version metadata is separate from the online download manifest.
2. Complete required code gates and independent review. Record actual exit codes; a failed gate stops dependent publication. Build candidates and obtain reviewable evidence before any required approval question.
3. Read [server.md](references/server.md) for fixed-commit server packaging with tools/release.py. Keep static PNGs. Validate extraction, archive whitelist and byte parity with Git blobs.
4. Read [windows.md](references/windows.md) before Windows build, local installer smoke or online upgrade smoke. Reuse desktop scripts; use synthetic, isolated data and never uninstall a user's existing installation to make tests pass.
5. Read [publish.md](references/publish.md) before GitHub upload or manifest change. Upload ready assets, verify public download SHA-256, then update the complete online manifest. Do not push placeholders, absent asset URLs or mismatched Windows hashes.
6. Save provenance, hashes, sizes, gates and limitations in docs/handover. Report release URL, platform availability and whether any server was actually upgraded.

## Maintaining this module

Keep deterministic mechanics in tools/release.py and existing desktop scripts; keep decisions and ownership in this skill. When the updater, assets, manifest schema or desktop scripts change, update only the relevant reference and add a behavioral regression. Test the script and skill with an isolated forward test. Avoid copying long historical handovers into SKILL.md.

Useful entry points: tools/release.py --help; desktop/publish.ps1; desktop/build-installer.ps1; desktop/tests/release-audit.ps1; desktop/tests/installer-smoke.ps1; desktop/tests/online-update-smoke.ps1.
