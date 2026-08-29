#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER="$SKILL_DIR/scripts/run.sh"

if [ ! -f "$LAUNCHER" ]; then
  echo "tts-lychee launcher is missing at: $LAUNCHER"
  exit 1
fi

bash "$LAUNCHER" --doctor
