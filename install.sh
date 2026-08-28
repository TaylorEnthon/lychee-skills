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
  "$SKILL_SOURCE/requirements.txt" \
  "$COMMAND_SOURCE_DIR/tts-lychee-search-voices.md" \
  "$COMMAND_SOURCE_DIR/tts-lychee-list-voices.md"; do
  if [ ! -e "$required_source_path" ]; then
    echo "Required source path is missing: $required_source_path" >&2
    exit 1
  fi
done

mkdir -p "$SKILL_TARGET" "$COMMAND_TARGET_DIR"
cp "$SKILL_SOURCE/SKILL.md" "$SKILL_SOURCE/doctor.ps1" "$SKILL_SOURCE/doctor.sh" "$SKILL_TARGET/"
cp -R "$SKILL_SOURCE/scripts" "$SKILL_TARGET/"
cp "$SKILL_SOURCE/requirements.txt" "$SKILL_TARGET/requirements.txt"
cp "$COMMAND_SOURCE_DIR/tts-lychee-list-voices.md" "$COMMAND_TARGET_DIR/tts-lychee-list-voices.md"
cp "$COMMAND_SOURCE_DIR/tts-lychee-search-voices.md" "$COMMAND_TARGET_DIR/tts-lychee-search-voices.md"

if [ -d "$SKILL_TARGET/data" ]; then
  rm -rf "$SKILL_TARGET/data"
  echo "Removed legacy bundled voice data: $SKILL_TARGET/data"
fi

if [ -f "$COMMAND_TARGET_DIR/tts-lychee-preview-match.md" ]; then
  rm -f "$COMMAND_TARGET_DIR/tts-lychee-preview-match.md"
  echo "Removed obsolete voice matching command: $COMMAND_TARGET_DIR/tts-lychee-preview-match.md"
fi

if [ -f "$LEGACY_COMMAND" ]; then
  rm -f "$LEGACY_COMMAND"
  echo "Removed legacy duplicate slash command: $LEGACY_COMMAND"
fi

echo "Installed skill: $SKILL_TARGET"
echo "Install dependencies with: python3 -m pip install -r \"$SKILL_TARGET/requirements.txt\""
echo "Restart Claude Code, then use: /tts-lychee <text to synthesize>"
echo "Set TTS_API_KEY before use. Get an API Key from https://voice.lycheeai.com.cn/"
