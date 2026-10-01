import os
from pathlib import Path
import subprocess
import sys
import shutil

from dotenv import dotenv_values
import pytest


@pytest.mark.parametrize('password', ['strong-admin-pass', "a'quoted\\password", 'value$HOME # & | "', '${USER}'])
def test_deploy_configuration_preserves_password_and_replaces_placeholders(tmp_path, password):
    repository = Path(__file__).resolve().parents[2]
    script = (repository / 'deploy.sh').read_text(encoding='utf-8')
    generation = script.split("python3 - <<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
    directory = tmp_path / 'backend'
    directory.mkdir()
    target = directory / '.env'
    template = directory / '.env.example'
    template.write_text((repository / 'backend/.env.example').read_text(encoding='utf-8'), encoding='utf-8')
    result = subprocess.run(
        [sys.executable, '-c', generation], cwd=tmp_path, capture_output=True,
        env={**os.environ, 'JWT_SECRET': 'b' * 64, 'FIELD_KEY': 'a' * 64, 'ADMIN_PASSWORD': password},
    )
    if '${' in password:
        assert result.returncode != 0
        assert not target.exists()
        password = 'valid-retry-password'
        result = subprocess.run(
            [sys.executable, '-c', generation], cwd=tmp_path, capture_output=True,
            env={**os.environ, 'JWT_SECRET': 'b' * 64, 'FIELD_KEY': 'a' * 64, 'ADMIN_PASSWORD': password},
        )
    assert result.returncode == 0, result.stderr
    configuration = dotenv_values(target)
    assert configuration['JWT_SECRET'] == 'b' * 64
    assert configuration['FIELD_ENCRYPTION_KEY'] == 'a' * 64
    assert configuration['SUPER_ADMIN_PASSWORD'] == password
    assert configuration['DATABASE_URL'] == 'sqlite:///./data/monitor.db'
    saved = target.read_bytes()
    repeated = subprocess.run(
        [sys.executable, '-c', generation], cwd=tmp_path, capture_output=True,
        env={**os.environ, 'JWT_SECRET': 'c' * 64, 'FIELD_KEY': 'd' * 64, 'ADMIN_PASSWORD': 'replacement'},
    )
    assert repeated.returncode != 0
    assert target.read_bytes() == saved
    if os.name != 'nt':
        assert target.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('status,expected', [('healthy', 0), ('unhealthy', 1), ('starting', 1)])
def test_deploy_wait_requires_both_services_healthy(status, expected):
    bash = shutil.which('bash') or str(Path('C:/Program Files/Git/bin/bash.exe'))
    if not Path(bash).is_file():
        pytest.skip('Bash unavailable')
    repository = Path(__file__).resolve().parents[2]
    script = (repository / 'deploy.sh').read_text(encoding='utf-8')
    wait = script.split('wait_for_services() {', 1)[1].split('\n}\n', 1)[0]
    harness = '''
error() { echo "$1"; exit 1; }
sleep() { :; }
docker() {
  if [ "$1" = "inspect" ]; then
    if [ "$4" = "tiktok-monitor-backend" ]; then
      echo healthy
    else
      echo "$TEST_FRONTEND_STATUS"
    fi
  fi
}
wait_for_services() {
''' + wait + '\n}\nwait_for_services\necho deployment-success\n'
    result = subprocess.run(
        [bash, '-c', harness], capture_output=True,
        env={**os.environ, 'TEST_FRONTEND_STATUS': status},
    )
    assert result.returncode == expected, result.stderr
    assert (b'deployment-success' in result.stdout) == (expected == 0)


@pytest.mark.parametrize('exit_code', [0, 1])
def test_git_auth_uses_temporary_script_and_cleans_it_on_exit(exit_code):
    bash = shutil.which('bash') or str(Path('C:/Program Files/Git/bin/bash.exe'))
    if not Path(bash).is_file():
        pytest.skip('Bash unavailable')
    repository = Path(__file__).resolve().parents[2]
    script = (repository / 'deploy.sh').read_text(encoding='utf-8')
    auth = script.split('prepare_git_auth() {', 1)[1].split('\n}\n', 1)[0]
    harness = 'set -e\nprepare_git_auth() {' + auth + '''
}
GITHUB_TOKEN=''
prepare_git_auth
GITHUB_TOKEN='fake-test-token-not-real'
prepare_git_auth
old_path="$GITHUB_ASKPASS"
prepare_git_auth
test ! -e "$old_path"
test "$("$GIT_ASKPASS" Username)" = 'x-access-token'
test "$("$GIT_ASKPASS" Password)" = "$GITHUB_TOKEN"
if grep -q "$GITHUB_TOKEN" "$GIT_ASKPASS"; then exit 2; fi
printf 'temporary-path=%s\\n' "$GIT_ASKPASS"
exit "$TEST_EXIT_CODE"
'''
    result = subprocess.run(
        [bash, '-c', harness], capture_output=True,
        env={**os.environ, 'TEST_EXIT_CODE': str(exit_code)},
    )
    assert result.returncode == exit_code, result.stderr
    path = next(line.partition(b'=')[2] for line in result.stdout.splitlines()
                if line.startswith(b'temporary-path='))
    cleanup = subprocess.run(
        [bash, '-c', 'test ! -e "$TEST_AUTH_PATH"'], capture_output=True,
        env={**os.environ, 'TEST_AUTH_PATH': path.decode()},
    )
    assert cleanup.returncode == 0, 'Deployment exit hook left its authentication script behind'


def test_deploy_clones_as_current_user_after_preparing_directory():
    script = (Path(__file__).resolve().parents[2] / 'deploy.sh').read_text(encoding='utf-8')
    assert 'sudo --preserve-env=GIT_ASKPASS' not in script
    assert 'sudo mkdir -p "$INSTALL_DIR"' in script
    assert 'sudo chown "$USER:$USER" "$INSTALL_DIR"' in script
    assert 'git clone "$GITHUB_REPO" "$INSTALL_DIR"' in script
