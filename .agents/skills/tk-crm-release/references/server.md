# Server / Docker archive

For local Docker development, use the dedicated compose file and project:

```powershell
docker compose -p tk-crm-local -f docker-compose.local.yml up -d --build --wait
docker compose -p tk-crm-local -f docker-compose.local.yml exec -T backend python -c "from app.version import APP_VERSION; print(APP_VERSION)"
```

The backend image supplies Python dependencies; keep its `build: ./backend` entry so a fresh machine can build it.
The backend binds `backend/` into `/app`, keeps the existing `docker-local/data` bind at `/app/data`,
and runs Uvicorn with `--reload --reload-dir /app/app`. Use `WATCHFILES_FORCE_POLLING=true` for reliable
Python change detection through Docker Desktop on Windows. Only application Python edits reload automatically;
after changing backend requirements, rebuild the backend image. New Alembic migrations run when the backend
starts, so restart it after adding a migration rather than assuming application reload also runs migrations.

The frontend uses the `development` Dockerfile target, binds `frontend/` into `/app`, keeps Linux dependencies
in the separate `frontend_node_modules` volume, and serves Vite HMR at `http://127.0.0.1:8080`.
Vite polling is enabled for Docker Desktop on Windows. When `package-lock.json` changes, refresh that dependency
volume with `docker compose -p tk-crm-local -f docker-compose.local.yml exec frontend npm ci`, then restart frontend.
The regular `docker-compose.yml` continues to build the final Nginx stage for published deployments.

Local source reload is separate from release installation. This development compose deliberately leaves
`UPDATE_AGENT_URL` and `UPDATE_AGENT_TOKEN` empty; release checks still compare the running backend version
with the public manifest, but the web updater stays inactive. Do not point the default Docker update lifecycle
at this development checkout: it targets the published compose ports/data layout and replaces source files.
Preserve the local database, environment file and uncommitted UI work when rebuilding or restarting containers.

`release-vX.Y.Z.tar.gz` is source for Docker updates; do not upload a Docker image tar, the entire working directory, or an installed runtime. Reuse `tools/updater.py`'s whitelist and `prepare_release` through `tools/release.py`.

From the repository root:

Use Python 3.11+; the project environment is `backend/.venv312/Scripts/python.exe`. The skill's PowerShell wrapper selects that environment automatically.

```powershell
python tools/release.py prepare-server --repo . --ref SOURCE_COMMIT --version X.Y.Z --date YYYY-MM-DD --changes-json .orchestration/release-X.Y.Z/base.json --output-dir .orchestration/release-X.Y.Z
python tools/release.py validate-server --repo . --ref SOURCE_COMMIT --archive .orchestration/release-X.Y.Z/release-vX.Y.Z.tar.gz --manifest .orchestration/release-X.Y.Z/server-candidate.json
```

Read `--help` to confirm flags if the tool was changed. The change file is a JSON array of change strings. The ref must resolve to a commit. The archive reads committed Git blobs and stores package metadata `{version,date,changes,source_commit}` in its version.json, with no download URL or self-hash. All other files must match their commit blobs. Keep README/static PNGs; exclude credentials, databases, logs, backups, build output, caches and `.env` except examples.

Prepare a new candidate only after source fixes/tests are committed. Keep the existing complete root manifest online during this work; a source commit may legitimately contain the previous online manifest because the archive substitutes package metadata. Do not infer provenance from current HEAD after generating an archive.

Check migration head and new migrations from the packaged source, not just the workspace. For an upgrade fixture, back up a synthetic old database, migrate and confirm original data survives. Preserve the source commit, archive SHA-256, file count, byte size, extraction audit and required assets in the release evidence.

For a Windows-only addition to an already public version, retain the existing server archive and its original source commit. Do not rebuild or overwrite that server asset.
