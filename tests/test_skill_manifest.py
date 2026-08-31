from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "tts-lychee"
MANIFEST = SKILL / "SKILL.md"


def frontmatter() -> tuple[dict[str, str], set[str]]:
    text = MANIFEST.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "---"
    closing = lines.index("---", 1)
    values = {}
    keys = set()
    for line in lines[1:closing]:
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if match:
            key, value = match.groups()
            keys.add(key)
            values[key] = value.strip()
    return values, keys


def test_skill_frontmatter_uses_only_portable_fields():
    values, keys = frontmatter()

    assert values["name"] == "tts-lychee"
    assert values["description"]
    assert keys <= {"name", "description", "license", "allowed-tools", "metadata"}
    assert "version" not in keys
    assert "user-invocable" not in keys


def test_skill_package_contains_both_launchers_and_requirement_sets():
    expected = [
        SKILL / "scripts" / "run.sh",
        SKILL / "scripts" / "run.ps1",
        SKILL / "requirements.txt",
        SKILL / "requirements-playback.txt",
    ]

    assert all(path.is_file() for path in expected)
