#!/usr/bin/env sh
set -eu
ROOT=${1:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
TOKEN=${UPDATE_AGENT_TOKEN:?Set UPDATE_AGENT_TOKEN before starting the updater}
LIFECYCLE=${UPDATE_AGENT_LIFECYCLE:-$ROOT/tools/lifecycle.docker.json}
exec python3 "$ROOT/tools/update_agent.py" --root "$ROOT" --lifecycle "$LIFECYCLE" --token "$TOKEN" --port "${UPDATE_AGENT_PORT:-8765}"
