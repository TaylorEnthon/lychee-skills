from __future__ import annotations

import json
from pathlib import Path

import pytest

import lychee_tts.api as api_module
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


class FakeDownloadResponse:
    def __init__(
        self,
        body,
        url="https://audio.example/voice.wav",
        status_code=200,
        headers=None,
    ):
        self.body = body
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield self.body

    def close(self):
        self.closed = True


class FakeRequests:
    class RequestException(Exception):
        pass

    def __init__(self, response):
        self.responses = list(response) if isinstance(response, list) else [response]
        self.calls = []

    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
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
    assert session.calls[0][2]["params"] == {"name": "清新少女", "page_no": 1, "page_size": 1000}


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
        for index in range(1000)
    ]
    session = FakeSession([
        FakeResponse({"code": 200, "data": {"list": first_page, "total": 1001}}),
        FakeResponse({"code": 200, "data": {"list": [{"name": "voice-1000"}], "total": 1001}}),
    ])

    voices = LycheeApiClient(api_key="test-key", session=session).list_all_public_voices()

    assert len(voices) == 1001
    assert session.calls[0][2]["params"]["page_size"] == 1000
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


def test_natural_language_prefilter_drops_generic_weak_matches():
    session = FakeSession([
        FakeResponse({
            "code": 200,
            "data": {
                "list": [
                    {"name": "岳山", "description": "沉稳成熟男声，适合纪录片旁白"},
                    {"name": "叶玲", "description": "明亮女声，适合短视频"},
                ],
                "total": 2,
            },
        })
    ])

    voices = LycheeApiClient(api_key="test-key", session=session).search_public_voices(
        "适合纪录片旁白的成熟男声"
    )

    assert [voice.name for voice in voices] == ["岳山"]


def test_voice_prefilter_explains_which_fields_and_terms_matched():
    session = FakeSession([
        FakeResponse({
            "code": 200,
            "data": {
                "list": [
                    {"name": "岳山", "description": "沉稳男声，适合纪录片旁白", "lang_code": "zh"},
                ],
                "total": 1,
            },
        })
    ])

    matches = LycheeApiClient(api_key="test-key", session=session).search_public_voice_matches(
        "纪录片"
    )

    assert matches[0].voice.name == "岳山"
    assert matches[0].matched_fields == ("description",)
    assert "纪录片" in matches[0].matched_terms


def test_clone_download_rejects_private_literal_before_network(tmp_path: Path, monkeypatch):
    class RequestsSentinel:
        class RequestException(Exception):
            pass

        @staticmethod
        def get(*args, **kwargs):
            raise AssertionError("private URL must be rejected before network access")

    monkeypatch.setattr(api_module, "requests", RequestsSentinel)

    with pytest.raises(ValueError, match="私有|本机"):
        LycheeApiClient(api_key="test-key").download_audio(
            "http://127.0.0.1/sample.wav",
            tmp_path / "sample.wav",
        )


def test_clone_download_rejects_hostname_resolving_to_private_address(
    tmp_path: Path, monkeypatch
):
    requests_sentinel = FakeRequests(FakeDownloadResponse(b"not reached"))
    monkeypatch.setattr(api_module, "requests", requests_sentinel)
    monkeypatch.setattr(
        api_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (api_module.socket.AF_INET, api_module.socket.SOCK_STREAM, 6, "", ("10.0.0.7", 443))
        ],
    )

    with pytest.raises(ValueError, match="私有网络"):
        LycheeApiClient(api_key="test-key").download_audio(
            "https://audio.example/voice.wav",
            tmp_path / "voice.wav",
        )

    assert requests_sentinel.calls == []


@pytest.mark.parametrize(
    ("filename", "body"),
    [
        ("voice.wav", b"RIFF\x24\x00\x00\x00WAVEfmt "),
        ("voice.mp3", b"ID3\x04\x00\x00\x00\x00\x00\x00"),
        ("voice-frame.mp3", b"\xff\xfb\x90\x64"),
        ("voice.m4a", b"\x00\x00\x00\x18ftypM4A "),
    ],
)
def test_clone_download_accepts_supported_audio_signatures(
    filename: str, body: bytes, tmp_path: Path, monkeypatch
):
    response = FakeDownloadResponse(body)
    monkeypatch.setattr(api_module, "requests", FakeRequests(response))
    monkeypatch.setattr(
        api_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (api_module.socket.AF_INET, api_module.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )
    destination = tmp_path / filename

    result = LycheeApiClient(api_key="test-key").download_audio(
        "https://audio.example/voice.wav", destination
    )

    assert result == destination
    assert destination.read_bytes() == body
    assert response.closed is True


def test_clone_download_rejects_http_200_non_audio_payload(tmp_path: Path, monkeypatch):
    response = FakeDownloadResponse(b"<html><body>login</body></html>")
    monkeypatch.setattr(api_module, "requests", FakeRequests(response))
    monkeypatch.setattr(
        api_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (api_module.socket.AF_INET, api_module.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )
    destination = tmp_path / "voice.wav"

    with pytest.raises(LycheeApiError, match="音频格式"):
        LycheeApiClient(api_key="test-key").download_audio(
            "https://audio.example/voice.wav", destination
        )

    assert not destination.exists()
    assert response.closed is True


def test_clone_download_rejects_redirect_to_private_hostname(tmp_path: Path, monkeypatch):
    response = FakeDownloadResponse(
        b"",
        status_code=302,
        headers={"Location": "http://internal.example/voice.wav"},
    )
    fake_requests = FakeRequests(response)
    monkeypatch.setattr(api_module, "requests", fake_requests)

    def addresses(host, *args, **kwargs):
        address = "10.0.0.9" if host == "internal.example" else "93.184.216.34"
        return [
            (api_module.socket.AF_INET, api_module.socket.SOCK_STREAM, 6, "", (address, 443))
        ]

    monkeypatch.setattr(api_module.socket, "getaddrinfo", addresses)
    destination = tmp_path / "voice.wav"

    with pytest.raises(LycheeApiError, match="重定向.*私有网络"):
        LycheeApiClient(api_key="test-key").download_audio(
            "https://audio.example/voice.wav", destination
        )

    assert not destination.exists()
    assert len(fake_requests.calls) == 1
    assert response.closed is True
