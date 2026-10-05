import argparse
import json
import os
import secrets
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from .updater import ServiceLifecycle, apply_release, validate_manifest
except ImportError:
    from updater import ServiceLifecycle, apply_release, validate_manifest


class Agent:
    def __init__(self, root: Path, token: str, lifecycle, on_completed=None):
        self.root = root.resolve()
        self.token = token
        self.lifecycle = lifecycle
        self.on_completed = on_completed
        self.lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.state_path = self.root / "backend" / "data" / "update-agent-state.json"
        self.state = self._load_state()
        if self.state.get("message") == "Updater restarted before the update completed":
            self._persist_state()

    def _load_state(self):
        default = {"status": "idle", "message": "", "latest_version": None}
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default
        if not isinstance(state, dict) or state.get("status") not in {
            "idle", "running", "completed", "failed"
        }:
            return default
        state = {**default, **{key: state[key] for key in default if key in state}}
        if state["status"] == "running":
            state.update(status="failed", message="Updater restarted before the update completed")
        return state

    def _set_state(self, **changes):
        with self.state_lock:
            self.state.update(changes)
            self._persist_state()

    def _persist_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.state_path)

    def snapshot(self):
        with self.state_lock:
            return dict(self.state)

    def start(self, manifest: dict):
        if not self.lock.acquire(blocking=False):
            return False
        try:
            self._set_state(status="running", message="Updating", latest_version=manifest["version"])
        except Exception:
            self.lock.release()
            raise

        def run():
            completed = False
            try:
                apply_release(self.root, manifest, self.lifecycle)
                self._record_history(manifest)
                self._set_state(status="completed", message="Update completed")
                completed = True
            except Exception as exc:
                self._set_state(status="failed", message=str(exc))
            finally:
                self.lock.release()
            if completed and self.on_completed:
                self.on_completed()

        threading.Thread(target=run, daemon=True).start()
        return True

    def _record_history(self, manifest: dict):
        history_path = self.root / "backend" / "data" / "update-history.json"
        try:
            history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.is_file() else []
        except (OSError, ValueError):
            history = []
        if not isinstance(history, list):
            history = []
        history = [item for item in history if isinstance(item, dict)]
        history.insert(0, {
            "version": manifest["version"],
            "date": manifest.get("date"),
            "changes": manifest.get("changes", []),
            "installed_at": datetime.now().isoformat(timespec="seconds"),
        })
        history_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = history_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(history[:50], ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(history_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--lifecycle", required=True, type=Path)
    parser.add_argument("--token", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument(
        "--restart-after-update",
        action="store_true",
        help="Reload the updater process after a successful update",
    )
    args = parser.parse_args()
    if len(args.token) < 32:
        raise SystemExit("Use a random agent token of at least 32 characters")
    lifecycle = ServiceLifecycle(json.loads(args.lifecycle.read_text(encoding="utf-8")))
    on_completed = None
    if args.restart_after_update:
        def restart_agent():
            os.execv(sys.executable, [sys.executable, *sys.argv])

        on_completed = restart_agent
    agent = Agent(args.root, args.token, lifecycle, on_completed=on_completed)

    class Handler(BaseHTTPRequestHandler):
        def _json(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self):
            return secrets.compare_digest(self.headers.get("Authorization", ""), f"Bearer {agent.token}")

        def do_GET(self):
            if self.path == "/status" and self._authorized():
                self._json(200, agent.snapshot())
            else:
                self._json(404, {"detail": "Not found"})

        def do_POST(self):
            if self.path != "/apply" or not self._authorized():
                self._json(404, {"detail": "Not found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length > 256 * 1024:
                self._json(413, {"detail": "Manifest too large"})
                return
            try:
                manifest = validate_manifest(json.loads(self.rfile.read(length).decode()))
                if not agent.start(manifest):
                    self._json(409, {"detail": "Update is already running"})
                    return
                self._json(202, agent.snapshot())
            except Exception as exc:
                self._json(400, {"detail": str(exc)})

        def log_message(self, *_):
            return

    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
