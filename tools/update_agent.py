import argparse
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from updater import ServiceLifecycle, apply_release, validate_manifest


class Agent:
    def __init__(self, root: Path, token: str, lifecycle):
        self.root = root.resolve()
        self.token = token
        self.lifecycle = lifecycle
        self.lock = threading.Lock()
        self.state = {"status": "idle", "message": "", "latest_version": None}

    def start(self, manifest: dict):
        if not self.lock.acquire(blocking=False):
            return False
        self.state.update(status="running", message="Updating", latest_version=manifest["version"])

        def run():
            try:
                apply_release(self.root, manifest, self.lifecycle)
                self.state.update(status="completed", message="Update completed")
            except Exception as exc:
                self.state.update(status="failed", message=str(exc))
            finally:
                self.lock.release()

        threading.Thread(target=run, daemon=True).start()
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--lifecycle", required=True, type=Path)
    parser.add_argument("--token", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    if len(args.token) < 32:
        raise SystemExit("Use a random agent token of at least 32 characters")
    lifecycle = ServiceLifecycle(json.loads(args.lifecycle.read_text(encoding="utf-8")))
    agent = Agent(args.root, args.token, lifecycle)

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
                self._json(200, agent.state)
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
                self._json(202, agent.state)
            except Exception as exc:
                self._json(400, {"detail": str(exc)})

        def log_message(self, *_):
            return

    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
