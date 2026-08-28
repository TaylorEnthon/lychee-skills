from __future__ import annotations

import json
from pathlib import Path

import pytest

from lychee_tts.api import LycheeApiClient, LycheeApiError, VoiceSelectionError


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return json.loads(self.text)


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def test_public_voice_name_is_resolved_from_live_api():
    session = FakeSession([
        FakeResponse({
            "code": 200,
            "info": "success",
            "data": {
                "list": [
                    {"name": "清新少女", "description": "清晰", "lang_code": "zh", "audio_url": "https://example.test/a.wav"},
                ],
                "total": 1,
            },
        })
    ])

    client = LycheeApiClient(api_key="test-key", session=session)
    voice = client.resolve_public_voice("清新少女")

    assert voice.name == "清新少女"
    assert session.calls[0][1].endswith("/openapi/voice-list")
    assert session.calls[0][2]["params"] == {"name": "清新少女", "page_no": 1, "page_size": 100}


def test_clone_request_id_becomes_saved_speaker_id(tmp_path: Path):
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFF" + b"0" * 40)
    session = FakeSession([
        FakeResponse({
            "code": 200,
            "info": "success",
            "data": {"request_id": "clone-request-123", "name": "我的声音"},
        })
    ])

    client = LycheeApiClient(api_key="test-key", session=session)
    result = client.clone_voice(audio, name="我的声音")

    assert result.speaker_id == "clone-request-123"
    assert result.request_id == "clone-request-123"
    assert session.calls[0][0] == "POST"
    assert session.calls[0][2]["data"]["name"] == "我的声音"


def test_clone_request_id_wins_when_response_also_contains_speaker_id(tmp_path: Path):
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFF" + b"0" * 40)
    session = FakeSession([
        FakeResponse({
            "code": 200,
            "data": {
                "request_id": "clone-request-123",
                "speaker_id": "server-speaker-456",
            },
        })
    ])

    result = LycheeApiClient(api_key="test-key", session=session).clone_voice(audio)

    assert result.speaker_id == "clone-request-123"


def test_public_voice_list_paginates_until_total():
    first_page = [
        {"name": f"voice-{index}", "description": "", "lang_code": "zh", "audio_url": ""}
        for index in range(100)
    ]
    session = FakeSession([
        FakeResponse({"code": 200, "data": {"list": first_page, "total": 101}}),
        FakeResponse({"code": 200, "data": {"list": [{"name": "voice-100"}], "total": 101}}),
    ])

    voices = LycheeApiClient(api_key="test-key", session=session).list_all_public_voices()

    assert len(voices) == 101
    assert session.calls[1][2]["params"]["page_no"] == 2


def test_search_public_voices_matches_description_after_fetching_full_list():
    session = FakeSession([
        FakeResponse({
            "code": 200,
            "data": {
                "list": [
                    {"name": "岳山", "description": "沉稳男声，适合纪录片旁白"},
                    {"name": "叶玲", "description": "明亮女声，适合短视频"},
                ],
                "total": 2,
            },
        })
    ])

    voices = LycheeApiClient(api_key="test-key", session=session).search_public_voices("纪录片")

    assert [voice.name for voice in voices] == ["岳山"]
    assert "name" not in session.calls[0][2]["params"]


def test_multiple_fuzzy_public_voice_matches_are_not_silently_replaced():
    session = FakeSession([
        FakeResponse({
            "code": 200,
            "data": {"list": [{"name": "温柔女声"}, {"name": "温柔男声"}], "total": 2},
        })
    ])

    with pytest.raises(VoiceSelectionError) as error:
        LycheeApiClient(api_key="test-key", session=session).resolve_public_voice("温柔")

    assert [voice.name for voice in error.value.candidates] == ["温柔女声", "温柔男声"]


def test_non_object_api_response_is_reported_as_api_error():
    session = FakeSession([FakeResponse(["invalid"])])

    with pytest.raises(LycheeApiError, match="返回格式无效"):
        LycheeApiClient(api_key="test-key", session=session).list_public_voices()


def test_voice_design_returns_preview_url_without_confusing_request_ids():
    session = FakeSession([
        FakeResponse({
            "code": 200,
            "data": {
                "audio_url": "https://example.test/preview.wav",
                "request_id": "design-request-123",
                "task_id": "design-task-123",
            },
        })
    ])

    result = LycheeApiClient(api_key="test-key", session=session).design_voice(
        "清晰、亲切的女性声音", "晚上好。"
    )

    assert result.audio_url == "https://example.test/preview.wav"
    assert result.request_id == "design-request-123"
    assert session.calls[0][2]["json"]["optimize_text"] is False
