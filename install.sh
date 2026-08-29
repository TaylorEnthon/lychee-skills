#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SOURCE="$SOURCE_DIR/skills/tts-lychee"
COMMAND_SOURCE_DIR="$SOURCE_DIR/commands"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
AGENTS_HOME="${AGENTS_HOME:-$HOME/.agents}"
TARGET="claude"

usage() {
  echo "Usage: $0 [--target claude|codex|agents|all]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      [[ $# -ge 2 ]] || { echo "--target requires a value" >&2; exit 2; }
      TARGET="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$TARGET" in
  claude|codex|agents|all) ;;
  *)
    echo "Unsupported target: $TARGET" >&2
    usage >&2
    exit 2
    ;;
esac

for required_source_path in \
  "$SKILL_SOURCE/SKILL.md" \
  "$SKILL_SOURCE/doctor.ps1" \
  "$SKILL_SOURCE/doctor.sh" \
  "$SKILL_SOURCE/scripts" \
  "$SKILL_SOURCE/requirements.txt" \
  "$SKILL_SOURCE/requirements-playback.txt" \
  "$COMMAND_SOURCE_DIR/tts-lychee-search-voices.md" \
  "$COMMAND_SOURCE_DIR/tts-lychee-list-voices.md"; do
  if [[ ! -e "$required_source_path" ]]; then
    echo "Required source path is missing: $required_source_path" >&2
    exit 1
  fi
done

install_skill() {
  local agent_home="$1"
  local install_commands="$2"
  local skill_target="$agent_home/skills/tts-lychee"

  mkdir -p "$skill_target"
  cp "$SKILL_SOURCE/SKILL.md" "$SKILL_SOURCE/doctor.ps1" "$SKILL_SOURCE/doctor.sh" "$skill_target/"
  cp -R "$SKILL_SOURCE/scripts" "$skill_target/"
  cp "$SKILL_SOURCE/requirements.txt" "$SKILL_SOURCE/requirements-playback.txt" "$skill_target/"

  if [[ -d "$skill_target/data" ]]; then
    rm -rf "$skill_target/data"
    echo "Removed legacy bundled voice data: $skill_target/data"
  fi

  if [[ "$install_commands" == "true" ]]; then
    local command_target_dir="$agent_home/commands"
    mkdir -p "$command_target_dir"
    cp "$COMMAND_SOURCE_DIR/tts-lychee-list-voices.md" "$command_target_dir/tts-lychee-list-voices.md"
    cp "$COMMAND_SOURCE_DIR/tts-lychee-search-voices.md" "$command_target_dir/tts-lychee-search-voices.md"
    rm -f \
      "$command_target_dir/tts-lychee-preview-match.md" \
      "$command_target_dir/tts-lychee.md"
  fi

  echo "Installed skill: $skill_target"
  echo "Install core dependencies: bash \"$skill_target/scripts/run.sh\" --install-deps"
  echo "Optional live playback: bash \"$skill_target/scripts/run.sh\" --install-playback"
}

if [[ "$TARGET" == "claude" || "$TARGET" == "all" ]]; then
  install_skill "$CLAUDE_HOME" true
fi
if [[ "$TARGET" == "codex" || "$TARGET" == "all" ]]; then
  install_skill "$CODEX_HOME" false
fi
if [[ "$TARGET" == "agents" || "$TARGET" == "all" ]]; then
  install_skill "$AGENTS_HOME" false
fi

echo "Set TTS_API_KEY, restart the target Agent, then ask it to synthesize or play speech."
