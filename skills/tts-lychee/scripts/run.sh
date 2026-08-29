#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT="$SCRIPT_DIR/tts_client.py"
PYTHON_CMD=()

is_python() {
  "$@" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1
}

if [[ -n "${TTS_PYTHON:-}" ]]; then
  if is_python "$TTS_PYTHON"; then
    PYTHON_CMD=("$TTS_PYTHON")
  else
    echo "TTS_PYTHON is not an executable Python 3.8+ runtime: $TTS_PYTHON" >&2
    exit 127
  fi
else
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && is_python "$candidate"; then
      PYTHON_CMD=("$candidate")
      break
    fi
  done
  if [[ ${#PYTHON_CMD[@]} -eq 0 ]] && command -v py >/dev/null 2>&1 && is_python py -3; then
    PYTHON_CMD=(py -3)
  fi
fi

if [[ ${#PYTHON_CMD[@]} -eq 0 ]]; then
  echo "Python 3.8+ not found. Install Python and rerun this launcher." >&2
  exit 127
fi

if [[ "${1:-}" == "--install-deps" ]]; then
  exec "${PYTHON_CMD[@]}" -m pip install -r "$SCRIPT_DIR/../requirements.txt"
fi
if [[ "${1:-}" == "--install-playback" ]]; then
  exec "${PYTHON_CMD[@]}" -m pip install -r "$SCRIPT_DIR/../requirements-playback.txt"
fi

exec "${PYTHON_CMD[@]}" "$CLIENT" "$@"
