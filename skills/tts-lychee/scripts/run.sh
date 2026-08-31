#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT="$SCRIPT_DIR/tts_client.py"
RUNTIME_HOME="${TTS_RUNTIME_HOME:-$HOME/.lychee/tts-lychee/runtime}"
VENV_DIR="$RUNTIME_HOME/venv"
PYTHON_CMD=()
EXPLICIT_RUNTIME=false

is_python() {
  "$@" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1
}

select_venv_python() {
  local candidate
  for candidate in "$VENV_DIR/bin/python" "$VENV_DIR/Scripts/python.exe"; do
    if [[ -f "$candidate" ]] && is_python "$candidate"; then
      PYTHON_CMD=("$candidate")
      return 0
    fi
  done
  return 1
}

select_system_python() {
  local candidate
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && is_python "$candidate"; then
      PYTHON_CMD=("$candidate")
      return 0
    fi
  done
  if command -v py >/dev/null 2>&1 && is_python py -3; then
    PYTHON_CMD=(py -3)
    return 0
  fi
  return 1
}

if [[ -n "${TTS_PYTHON:-}" ]]; then
  if is_python "$TTS_PYTHON"; then
    PYTHON_CMD=("$TTS_PYTHON")
    EXPLICIT_RUNTIME=true
  else
    echo "TTS_PYTHON is not an executable Python 3.8+ runtime: $TTS_PYTHON" >&2
    exit 127
  fi
else
  if ! select_venv_python; then
    select_system_python || true
  fi
fi

if [[ ${#PYTHON_CMD[@]} -eq 0 ]]; then
  echo "Python 3.8+ not found. Install Python and rerun this launcher." >&2
  exit 127
fi

INSTALL_MODE="${1:-}"
if [[ "$INSTALL_MODE" == "--install-deps" || "$INSTALL_MODE" == "--install-playback" ]]; then
  if [[ "$EXPLICIT_RUNTIME" == false ]] && ! select_venv_python; then
    if ! select_system_python; then
      echo "Python 3.8+ not found. Install Python and rerun this launcher." >&2
      exit 127
    fi
    BOOTSTRAP_CMD=("${PYTHON_CMD[@]}")
    mkdir -p "$RUNTIME_HOME"
    "${BOOTSTRAP_CMD[@]}" -m venv "$VENV_DIR"
    if ! select_venv_python; then
      echo "Failed to create the tts-lychee Python runtime: $VENV_DIR" >&2
      exit 1
    fi
  fi
fi

if [[ "$INSTALL_MODE" == "--install-deps" ]]; then
  exec "${PYTHON_CMD[@]}" -m pip install -r "$SCRIPT_DIR/../requirements.txt"
fi
if [[ "$INSTALL_MODE" == "--install-playback" ]]; then
  exec "${PYTHON_CMD[@]}" -m pip install -r "$SCRIPT_DIR/../requirements-playback.txt"
fi

exec "${PYTHON_CMD[@]}" "$CLIENT" "$@"
