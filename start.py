#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TikTok Monitor - 一键启动脚本
"""

import subprocess
import socket
import sys
import re
import os
import time
import threading
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"


def is_port_free(port: int) -> bool:
    """检查端口在所有地址上都没有被占用"""
    for host in ('', '127.0.0.1', '0.0.0.0'):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
            except OSError:
                return False
    # 也检查是否有进程在监听
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.1)
        if s.connect_ex(('127.0.0.1', port)) == 0:
            return False
    return True


def find_available_port(start_port: int, max_attempts: int = 10) -> int:
    for port in range(start_port, start_port + max_attempts):
        if is_port_free(port):
            return port
    return None


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def is_our_backend_ready(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', port)) == 0


def update_env_port(env_file: Path, new_port: int):
    if env_file.exists():
        content = env_file.read_text(encoding='utf-8')
        if re.search(r'^PORT=', content, flags=re.MULTILINE):
            content = re.sub(r'^PORT=\d+', f'PORT={new_port}', content, flags=re.MULTILINE)
        else:
            content += f'\nPORT={new_port}'
        env_file.write_text(content, encoding='utf-8')


def update_env_frontend(env_file: Path, backend_port: int):
    new_url = f'VITE_API_BASE_URL=http://127.0.0.1:{backend_port}'
    if env_file.exists():
        content = env_file.read_text(encoding='utf-8')
        content = re.sub(r'^VITE_API_BASE_URL=.*', new_url, content, flags=re.MULTILINE)
    else:
        content = new_url + '\n'
    env_file.write_text(content, encoding='utf-8')


def get_python_executable() -> str:
    """优先使用完整的系统 Python（conda），避免 venv 精简版缺少 SSL 等模块"""
    # 1. 优先用运行 start.py 的当前 Python（通常是 conda，功能完整）
    current = sys.executable
    # 检查当前 Python 是否有 ssl
    try:
        result = subprocess.run(
            [current, '-c', 'import ssl'],
            capture_output=True, timeout=5
        )
        if result.returncode == 0:
            return current
    except Exception:
        pass

    # 2. 尝试 backend/venv
    venv_win = BACKEND_DIR / 'venv' / 'Scripts' / 'python.exe'
    venv_unix = BACKEND_DIR / 'venv' / 'bin' / 'python'
    for venv_py in [venv_win, venv_unix]:
        if venv_py.exists():
            try:
                result = subprocess.run(
                    [str(venv_py), '-c', 'import ssl'],
                    capture_output=True, timeout=5
                )
                if result.returncode == 0:
                    return str(venv_py)
            except Exception:
                pass

    return current


def check_node():
    try:
        subprocess.run(['node', '--version'], capture_output=True, check=True, shell=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def check_npm_deps():
    return (FRONTEND_DIR / 'node_modules').exists()


def stream_output(proc, prefix, use_stderr=False):
    try:
        stream = proc.stderr if use_stderr else proc.stdout
        for line in iter(stream.readline, b''):
            text = line.decode('utf-8', errors='replace').rstrip()
            if text:
                print(f"[{prefix}] {text}", flush=True)
    except Exception:
        pass


# ── 端口分配 ──────────────────────────────────────────────
print("TikTok Monitor starting...")
print("-" * 45)

backend_port = find_available_port(8000)
if not backend_port:
    print("ERROR: no available port in range 8000-8009")
    sys.exit(1)

frontend_port = find_available_port(5173)
if not frontend_port:
    print("ERROR: no available port in range 5173-5182")
    sys.exit(1)

if backend_port != 8000:
    print(f"[warn] port 8000 in use, backend -> {backend_port}")
if frontend_port != 5173:
    print(f"[warn] port 5173 in use, frontend -> {frontend_port}")

update_env_port(BACKEND_DIR / '.env', backend_port)
update_env_frontend(FRONTEND_DIR / '.env', backend_port)

# ── 检查后端依赖 ──────────────────────────────────────────
python_exec = get_python_executable()
print(f"Using Python: {python_exec}")

result = subprocess.run(
    [python_exec, '-c', 'import uvicorn, fastapi, sqlalchemy'],
    capture_output=True
)
if result.returncode != 0:
    print("Installing backend dependencies...")
    subprocess.run(
        [python_exec, '-m', 'pip', 'install', '-r', str(BACKEND_DIR / 'requirements.txt')],
        check=True
    )
    print("Backend dependencies installed.")

# ── 检查 Node / npm 依赖 ──────────────────────────────────
if not check_node():
    print("ERROR: Node.js not found. Install from https://nodejs.org/")
    sys.exit(1)

if not check_npm_deps():
    print("Installing frontend dependencies...")
    result = subprocess.run('npm install', cwd=FRONTEND_DIR, shell=True)
    if result.returncode != 0:
        print("ERROR: npm install failed. Run manually: cd frontend && npm install")
        sys.exit(1)
    print("Frontend dependencies installed.")

# ── 启动后端 ──────────────────────────────────────────────
print(f"\nStarting backend on port {backend_port}...")

child_env = os.environ.copy()
child_env['PYTHONIOENCODING'] = 'utf-8'
child_env['PORT'] = str(backend_port)

backend_proc = subprocess.Popen(
    [python_exec, 'run.py'],
    cwd=BACKEND_DIR,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env=child_env
)

threading.Thread(target=stream_output, args=(backend_proc, 'backend'), daemon=True).start()
threading.Thread(target=stream_output, args=(backend_proc, 'backend-err', True), daemon=True).start()

print("Waiting for backend...")
time.sleep(8)
if backend_proc.poll() is not None:
    print("ERROR: backend process exited unexpectedly")
    sys.exit(1)
print(f"Backend started on port {backend_port}")

# ── 启动前端 ──────────────────────────────────────────────
print(f"\nStarting frontend on port {frontend_port}...")

frontend_proc = subprocess.Popen(
    f'npm run dev -- --port {frontend_port}',
    cwd=FRONTEND_DIR,
    shell=True
)

print("Waiting for frontend...")
for _ in range(60):
    time.sleep(1)
    if is_port_in_use(frontend_port):
        print(f"Frontend ready on port {frontend_port}")
        break
else:
    print("Frontend port check timeout, it may still be starting...")

# ── 完成 ──────────────────────────────────────────────────
print()
print("-" * 45)
print(f"All services started!")
print(f"  Frontend : http://localhost:{frontend_port}")
print(f"  Backend  : http://localhost:{backend_port}")
print(f"  API Docs : http://localhost:{backend_port}/docs")
print("-" * 45)
print("Press Ctrl+C to stop all services\n")

time.sleep(1)
webbrowser.open(f"http://localhost:{frontend_port}")

try:
    backend_proc.wait()
except KeyboardInterrupt:
    print("\nStopping services...")
    backend_proc.terminate()
    frontend_proc.terminate()
    print("Stopped.")
