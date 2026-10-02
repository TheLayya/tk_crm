import argparse
import json
import os
import subprocess
import time
from pathlib import Path


def runtime_file(root):
    return Path(root) / 'backend' / 'data' / 'windows-runtime.json'


def stop(root):
    path = runtime_file(root)
    if not path.is_file():
        return
    state = json.loads(path.read_text(encoding='utf-8'))
    for key in ('frontend_pid', 'backend_pid'):
        pid = state.get(key)
        if isinstance(pid, int) and pid != os.getpid():
            subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True, check=False)
    for _ in range(15):
        still_running = False
        for key in ('frontend_pid', 'backend_pid'):
            pid = state.get(key)
            if isinstance(pid, int):
                result = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {pid}'],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if str(pid) in result.stdout:
                    still_running = True
                    break
        if not still_running:
            break
        time.sleep(1)
    path.unlink(missing_ok=True)


def start(root):
    root = Path(root).resolve()
    subprocess.Popen(
        [os.fspath(Path(os.sys.executable)), os.fspath(root / 'start.py'), '--background'],
        cwd=root,
        creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['stop', 'start'])
    parser.add_argument('--root', required=True)
    args = parser.parse_args()
    (stop if args.action == 'stop' else start)(args.root)


if __name__ == '__main__':
    main()
