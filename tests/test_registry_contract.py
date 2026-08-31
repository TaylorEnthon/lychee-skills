from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

from lychee_tts.api import LycheeApiError, PublicVoice, VoiceSelectionError
from lychee_tts.registry import StoredVoice, VoiceRegistry
from tts_client import build_parser, resolve_voice


def load_voice_types():
    spec = importlib.util.find_spec("lychee_tts.voices")
    assert spec is not None, "lychee_tts.voices must own public/personal identity"
    module = importlib.import_module("lychee_tts.voices")
    return module.VoiceReference, module.VoiceResolver


def test_saved_clone_voice_can_be_resolved_by_alias(tmp_path: Path):
    registry = VoiceRegistry(tmp_path / "voices.json")
    stored = registry.save(StoredVoice(alias="我的声音", speaker_id="clone-request-123"))

    assert stored.speaker_id == "clone-request-123"
    assert registry.get("我的声音").speaker_id == "clone-request-123"


def test_optional_clone_flags_are_omitted_when_not_requested():
    args = build_parser().parse_args(["--clone-audio", "sample.wav", "--clone-name", "我的声音"])

    assert args.clone_is_public is None
    assert args.clone_clip_short is None


def test_clone_requires_explicit_confirmation(tmp_path: Path):
    from tts_client import run_clone

    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFF" + b"0" * 40)
    args = build_parser().parse_args(["--clone-audio", str(audio), "--clone-name", "我的声音"])

    with pytest.raises(ValueError, match="confirm-clone"):
        run_clone(args)


def test_clone_url_preserves_audio_extension_for_provider_validation(tmp_path: Path, monkeypatch):
    from lychee_tts.api import CloneResult
    from tts_client import run_clone

    captured = {}

    class Api:
        def download_audio(self, url, destination):
            captured["download_destination"] = destination
            destination.write_bytes(b"RIFF" + b"0" * 40)
            return destination

        def clone_voice(self, audio_path, **kwargs):
            captured["clone_path"] = audio_path
            return CloneResult(speaker_id="clone-request-123", request_id="clone-request-123")

    monkeypatch.setattr("tts_client.build_api", lambda args: Api())
    args = build_parser().parse_args([
        "--clone-url", "https://example.test/design-preview.wav",
        "--clone-name", "我的声音",
        "--confirm-clone",
        "--registry", str(tmp_path / "voices.json"),
    ])

    result = run_clone(args)

    assert result["success"] is True
    assert captured["download_destination"].suffix == ".wav"
    assert captured["clone_path"].suffix == ".wav"


def test_public_voice_name_wins_over_colliding_personal_alias(tmp_path: Path):
    registry = VoiceRegistry(tmp_path / "voices.json")
    registry.save(StoredVoice(alias="同名音色", speaker_id="private-id"))
    args = build_parser().parse_args([
        "--text", "你好", "--voice", "同名音色", "--registry", str(registry.path),
    ])

    class Api:
        def resolve_public_voice(self, requested):
            return PublicVoice(name=requested)

    assert resolve_voice(args, Api()) == ("同名音色", "同名音色", "public")


def test_personal_alias_is_used_when_public_voice_is_not_found(tmp_path: Path):
    registry = VoiceRegistry(tmp_path / "voices.json")
    registry.save(StoredVoice(alias="我的声音", speaker_id="private-id"))
    args = build_parser().parse_args([
        "--text", "你好", "--voice", "我的声音", "--registry", str(registry.path),
    ])

    class Api:
        def resolve_public_voice(self, requested):
            raise VoiceSelectionError("未找到公共音色")

    assert resolve_voice(args, Api()) == ("我的声音", "private-id", "custom")


def test_duplicate_personal_alias_requires_explicit_replacement(tmp_path: Path):
    registry = VoiceRegistry(tmp_path / "voices.json")
    registry.save(StoredVoice(alias="我的声音", speaker_id="first-id"))

    with pytest.raises(FileExistsError, match="我的声音"):
        registry.save(StoredVoice(alias="我的声音", speaker_id="second-id"))

    replaced = registry.save(
        StoredVoice(alias="我的声音", speaker_id="second-id"),
        replace=True,
    )

    assert replaced.speaker_id == "second-id"
    assert registry.get("我的声音").speaker_id == "second-id"


def test_explicit_public_voice_skips_catalog_request(tmp_path: Path):
    VoiceReference, VoiceResolver = load_voice_types()

    class Api:
        def resolve_public_voice(self, requested):
            raise AssertionError("explicit public voice must not query the catalog")

    reference = VoiceResolver(Api(), VoiceRegistry(tmp_path / "voices.json")).resolve(
        public_name="靖轩",
    )

    assert reference == VoiceReference("靖轩", "靖轩", "public")


def test_explicit_personal_voice_resolves_only_from_registry(tmp_path: Path):
    VoiceReference, VoiceResolver = load_voice_types()
    registry = VoiceRegistry(tmp_path / "voices.json")
    registry.save(StoredVoice(alias="我的声音", speaker_id="clone-request"))

    class Api:
        def resolve_public_voice(self, requested):
            raise AssertionError("explicit personal voice must not query the catalog")

    reference = VoiceResolver(Api(), registry).resolve(personal_alias="我的声音")

    assert reference == VoiceReference("我的声音", "clone-request", "personal")


def test_catalog_outage_never_switches_legacy_public_name_to_personal_alias(tmp_path: Path):
    _, VoiceResolver = load_voice_types()
    registry = VoiceRegistry(tmp_path / "voices.json")
    registry.save(StoredVoice(alias="靖轩", speaker_id="private-id"))

    class Api:
        def resolve_public_voice(self, requested):
            raise LycheeApiError("catalog unavailable")

    with pytest.raises(LycheeApiError, match="catalog unavailable"):
        VoiceResolver(Api(), registry).resolve(legacy_name="靖轩")
