# GitHub publication and manifest

Repository: `TheLayya/tk_crm`. Asset names: `release-vX.Y.Z.tar.gz` and `TkCRM-X.Y.Z-win-x64-setup.exe`. Root online manifest contains version/date/changes, server package_url/sha256 and windows_package_url/windows_sha256.

## Publish only ready assets

1. Inspect `git status`, staged paths, source ref, existing tag and `gh release view`. Preserve unrelated files. `gh auth status` should use existing auth; never print credentials.
2. Commit/push selected validated source files. Build candidates from that fixed source. Create a release notes file with actual new behavior, source provenance, migration and platform availability.
3. When explicitly authorized to publish, create a new tag/release with the exact source commit, upload both ready assets, and keep the previous valid manifest until downloads are verified. Use `--notes-file` for multiline notes.
4. If adding the missing Windows installer to an existing version, verify the public server asset digest matches its existing manifest and archive audit. Upload only the new Windows asset without `--clobber`. Never reuse an asset name to replace different bytes.
5. Compose a candidate manifest under `.orchestration/` using the validated server candidate/archive and Windows evidence. This records local hashes; it is not yet the online manifest.
6. Use `tools/release.py verify-download` with that candidate to fetch both public HTTPS assets and recompute SHA-256. Approved final hosts are github.com, release-assets.githubusercontent.com and objects.githubusercontent.com. Confirm tag target, filename, byte size and GitHub digest. Only after success copy the verified candidate into root `version.json`. A server-only release explicitly omits both Windows fields.
7. Commit/push only the final manifest and final release handover. Query GitHub contents API and the fixed commit Raw URL, then ordinary main Raw URL. GitHub CDN can serve old main for minutes; verify the version and hash rather than overwriting assets or claiming a server was upgraded.

Examples:

```powershell
gh release create vX.Y.Z SERVER_ARCHIVE WINDOWS_SETUP --repo TheLayya/tk_crm --target SOURCE_COMMIT --title "TkCRM X.Y.Z" --notes-file .orchestration/release-X.Y.Z/notes.md
gh release upload vX.Y.Z WINDOWS_SETUP --repo TheLayya/tk_crm
python tools/release.py compose-manifest --repo . --server-candidate SERVER_CANDIDATE --server-archive SERVER_ARCHIVE --windows-exe WINDOWS_SETUP --windows-evidence WINDOWS_EVIDENCE --version X.Y.Z --output .orchestration/release-X.Y.Z/version.json
python tools/release.py verify-download --manifest .orchestration/release-X.Y.Z/version.json --output-dir .orchestration/release-X.Y.Z/public-downloads
```

Confirm current tool flags with `--help`. An upload retry must inspect whether that exact asset already exists and compare its digest; silence is not permission to clobber. A failed installer/gate/hash/redirect/source audit prevents manifest publication. Repair and rerun only the affected phase; retain failed logs and successful immutable evidence.

## Completion

Report exact source commits, tag target, release URL, asset names/sizes/hashes, evidence exit codes, platform limitations and server state. Publish/commit work authorized earlier need not be reapproved. Creating or using this skill alone does not authorize external publication.

Team deployment remains a separate user webpage action. Read-only health checks are useful; do not call apply or use SSH restart/rebuild/source copy to bypass that rule. Local Docker updates require the known local compose/project, SQLite online backup, the existing data volume/key, healthy services and schema/data checks; no `down -v`.
