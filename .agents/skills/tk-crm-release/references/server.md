# Server / Docker archive

`release-vX.Y.Z.tar.gz` is source for Docker updates; do not upload a Docker image tar, the entire working directory, or an installed runtime. Reuse `tools/updater.py`'s whitelist and `prepare_release` through `tools/release.py`.

From the repository root:

```powershell
python tools/release.py prepare-server --repo . --ref SOURCE_COMMIT --version X.Y.Z --date YYYY-MM-DD --changes-json .orchestration/release-X.Y.Z/base.json --output-dir .orchestration/release-X.Y.Z
python tools/release.py validate-server --repo . --ref SOURCE_COMMIT --archive .orchestration/release-X.Y.Z/release-vX.Y.Z.tar.gz --manifest .orchestration/release-X.Y.Z/server-candidate.json
```

Read `--help` to confirm flags if the tool was changed. The change file is a JSON array of change strings. The ref must resolve to a commit. The archive reads committed Git blobs and stores package metadata `{version,date,changes,source_commit}` in its version.json, with no download URL or self-hash. All other files must match their commit blobs. Keep README/static PNGs; exclude credentials, databases, logs, backups, build output, caches and `.env` except examples.

Prepare a new candidate only after source fixes/tests are committed. Keep the existing complete root manifest online during this work; a source commit may legitimately contain the previous online manifest because the archive substitutes package metadata. Do not infer provenance from current HEAD after generating an archive.

Check migration head and new migrations from the packaged source, not just the workspace. For an upgrade fixture, back up a synthetic old database, migrate and confirm original data survives. Preserve the source commit, archive SHA-256, file count, byte size, extraction audit and required assets in the release evidence.

For a Windows-only addition to an already public version, retain the existing server archive and its original source commit. Do not rebuild or overwrite that server asset.
