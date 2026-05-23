#!/usr/bin/env bash
set -euo pipefail

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SOURCE="$SOURCE_DIR/skills/tts-lychee"
SKILL_TARGET="$CLAUDE_HOME/skills/tts-lychee"
COMMAND_SOURCE_DIR="$SOURCE_DIR/commands"
COMMAND_TARGET_DIR="$CLAUDE_HOME/commands"
LEGACY_COMMAND="$COMMAND_TARGET_DIR/tts-lychee.md"

for required_source_path in \
  "$SKILL_SOURCE/SKILL.md" \
  "$SKILL_SOURCE/doctor.ps1" \
  "$SKILL_SOURCE/doctor.sh" \
  "$SKILL_SOURCE/scripts" \
  "$SKILL_SOURCE/data" \
  "$COMMAND_SOURCE_DIR/tts-lychee-preview-match.md" \
  "$COMMAND_SOURCE_DIR/tts-lychee-list-voices.md"; do
  if [ ! -e "$required_source_path" ]; then
    echo "Required source path is missing: $required_source_path" >&2
    exit 1
  fi
done

mkdir -p "$SKILL_TARGET" "$COMMAND_TARGET_DIR"
cp "$SKILL_SOURCE/SKILL.md" "$SKILL_SOURCE/doctor.ps1" "$SKILL_SOURCE/doctor.sh" "$SKILL_TARGET/"
cp -R "$SKILL_SOURCE/scripts" "$SKILL_SOURCE/data" "$SKILL_TARGET/"
cp "$COMMAND_SOURCE_DIR/tts-lychee-preview-match.md" "$COMMAND_TARGET_DIR/tts-lychee-preview-match.md"
cp "$COMMAND_SOURCE_DIR/tts-lychee-list-voices.md" "$COMMAND_TARGET_DIR/tts-lychee-list-voices.md"

if [ -f "$LEGACY_COMMAND" ]; then
  rm -f "$LEGACY_COMMAND"
  echo "Removed legacy duplicate slash command: $LEGACY_COMMAND"
fi

echo "Installed skill: $SKILL_TARGET"
echo "Restart Claude Code, then use: /tts-lychee <text to synthesize>"
echo "Set TTS_API_KEY before use. Get an API Key from https://shanhaistudio.lycheeai.com.cn/"
