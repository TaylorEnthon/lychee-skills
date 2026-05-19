#!/usr/bin/env bash
set -euo pipefail

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
CLIENT="$CLAUDE_HOME/skills/tts-lychee/scripts/tts_client.py"

if [ ! -f "$CLIENT" ]; then
  echo "tts-lychee is not installed at: $CLAUDE_HOME/skills/tts-lychee"
  exit 1
fi

PYTHON=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON="python"
else
  echo "Python not found. Install Python 3.8+ and rerun this doctor."
  exit 1
fi

"$PYTHON" "$CLIENT" --doctor