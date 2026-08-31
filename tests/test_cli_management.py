from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from lychee_tts.registry import StoredVoice, VoiceRegistry


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "skills" / "tts-lychee" / "scripts" / "tts_client.py"


def run_client(*arguments: str, env=None):
    return subprocess.run(
        [sys.executable, str(CLIENT), *arguments],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_conflicting_operations_fail_instead_of_using_hidden_priority():
    env = os.environ.copy()
    env["TTS_API_KEY"] = "test-key"

    result = run_client("--doctor", "--list-voices", env=env)

    assert result.returncode == 1
    assert "不能同时" in result.stderr or "只能选择" in result.stderr


def test_operation_specific_flags_are_not_silently_ignored():
    env = os.environ.copy()
    env["TTS_API_KEY"] = "test-key"

    result = run_client("--doctor", "--voice", "不应被忽略", env=env)

    assert result.returncode == 1
    assert "朗读参数" in result.stderr


def test_voice_selectors_are_explicit_and_mutually_exclusive():
    result = run_client(
        "--text", "你好",
        "--voice", "旧入口",
        "--public-voice", "明确公共音色",
    )

    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert payload["error_code"] == "invalid_arguments"
    assert "只能指定一种音色" in payload["error"]


def test_personal_voices_can_be_listed_without_exposing_speaker_ids(tmp_path: Path):
    registry = VoiceRegistry(tmp_path / "voices.json")
    registry.save(StoredVoice(
        alias="我的旁白",
        speaker_id="private-speaker-id",
        description="沉稳纪录片男声",
    ))

    result = run_client("--list-personal-voices", "--registry", str(registry.path))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["voices"] == [{
        "alias": "我的旁白",
        "description": "沉稳纪录片男声",
        "preview_audio_url": "",
        "created_at": registry.get("我的旁白").created_at,
    }]
    assert "speaker_id" not in result.stdout


def test_personal_voice_removal_requires_confirmation(tmp_path: Path):
    registry = VoiceRegistry(tmp_path / "voices.json")
    registry.save(StoredVoice(alias="待删除音色", speaker_id="private-id"))

    rejected = run_client(
        "--remove-personal-voice", "待删除音色",
        "--registry", str(registry.path),
    )

    assert rejected.returncode == 1
    assert "confirm-remove" in rejected.stderr
    assert registry.get("待删除音色") is not None

    removed = run_client(
        "--remove-personal-voice", "待删除音色",
        "--confirm-remove",
        "--registry", str(registry.path),
    )

    assert removed.returncode == 0
    assert json.loads(removed.stdout)["removed"] is True
    assert registry.get("待删除音色") is None


def test_personal_voice_alias_can_be_renamed_after_confirmation(tmp_path: Path):
    registry = VoiceRegistry(tmp_path / "voices.json")
    registry.save(StoredVoice(alias="旧名字", speaker_id="private-id"))

    renamed = run_client(
        "--rename-personal-voice", "旧名字",
        "--new-personal-voice-name", "新名字",
        "--confirm-rename",
        "--registry", str(registry.path),
    )

    assert renamed.returncode == 0
    assert json.loads(renamed.stdout)["voice"] == "新名字"
    assert registry.get("旧名字") is None
    assert registry.get("新名字").speaker_id == "private-id"
    assert "private-id" not in renamed.stdout
