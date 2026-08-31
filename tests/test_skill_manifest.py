from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, Set, Tuple


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "tts-lychee"
MANIFEST = SKILL / "SKILL.md"


def frontmatter() -> Tuple[Dict[str, str], Set[str]]:
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


def test_skill_guidance_covers_portable_agent_workflows():
    text = MANIFEST.read_text(encoding="utf-8")

    for required in (
        "--public-voice",
        "--personal-voice",
        "--compact",
        "--offset",
        "--limit",
        "partial_output",
        "--jsonl",
        "长期可访问",
        "查询参数",
        "取消",
        "重试一次",
    ):
        assert required in text

    jsonl_context = text[max(0, text.index("--jsonl") - 80) : text.index("--jsonl") + 120]
    assert "可选" in jsonl_context

    for forbidden in (
        "询问用户 codec",
        "让用户选择 codec",
        "询问用户采样率",
        "让用户选择采样率",
        "让用户选择 Python",
        "让用户选择虚拟环境",
    ):
        assert forbidden not in text
