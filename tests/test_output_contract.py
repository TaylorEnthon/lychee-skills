from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

import tts_client
from lychee_tts.streaming import StreamResult


def load_contracts():
    spec = importlib.util.find_spec("lychee_tts.contracts")
    assert spec is not None, "lychee_tts.contracts must define the Agent output contract"
    return importlib.import_module("lychee_tts.contracts")


def test_result_contract_adds_metadata_without_removing_legacy_fields():
    contracts = load_contracts()

    result = contracts.result_record(
        "personal_voices",
        "run-1",
        {"success": True, "total": 0},
    )

    assert result == {
        "schema_version": "1.0",
        "type": "result",
        "operation": "personal_voices",
        "run_id": "run-1",
        "success": True,
        "total": 0,
    }


def test_error_contract_is_machine_readable_and_keeps_error_text():
    contracts = load_contracts()

    result = contracts.error_record(
        "speak",
        "run-2",
        ValueError("text is required"),
    )

    assert result == {
        "schema_version": "1.0",
        "type": "error",
        "operation": "speak",
        "run_id": "run-2",
        "success": False,
        "error": "text is required",
        "error_code": "invalid_arguments",
        "stage": "validation",
        "retryable": False,
    }


def test_error_contract_uses_structured_exception_attributes():
    contracts = load_contracts()

    error = RuntimeError("temporary stream failure")
    error.error_code = "stream_timeout"
    error.stage = "streaming"
    error.retryable = True
    error.partial_output = "speech.partial.wav"

    result = contracts.error_record("speak", "run-3", error)

    assert result["error_code"] == "stream_timeout"
    assert result["stage"] == "streaming"
    assert result["retryable"] is True
    assert result["partial_output"] == "speech.partial.wav"


class FakeStreamingClient:
    def __init__(self, *args, **kwargs):
        pass

    def stream(self, text, speaker_id, sink, on_event=None):
        sink.open()
        if on_event:
            on_event("connecting", {"segment": 1})
        sink.write(b"\x01\x00\x02\x00")
        if on_event:
            on_event("first_audio", {"segment": 1, "first_audio_ms": 1, "bytes": 4})
        sink.close(True)
        return StreamResult(audio_bytes=4, duration_ms=2, first_audio_ms=1, segments=1)


def test_jsonl_writes_progress_and_final_result_to_stdout(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    output = tmp_path / "speech.wav"
    monkeypatch.setattr(tts_client, "configure_stdio", lambda: None)
    monkeypatch.setattr(tts_client, "StreamingTtsClient", FakeStreamingClient)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tts_client.py",
            "--text",
            "hello",
            "--speaker-id",
            "voice-id",
            "--output",
            str(output),
            "--jsonl",
        ],
    )

    assert tts_client.main() == 0

    captured = capsys.readouterr()
    records = [json.loads(line) for line in captured.out.splitlines()]
    assert all(record["type"] == "event" for record in records[:-1])
    assert records[-1]["type"] == "result"
    assert {record["event"] for record in records[:-1]} >= {
        "voice_resolution_started",
        "voice_resolved",
        "first_audio",
    }
    assert {record["run_id"] for record in records} == {records[0]["run_id"]}
    assert records[-1]["success"] is True
    assert captured.err == ""
    assert output.exists()


def test_keyboard_interrupt_has_a_stable_cancelled_contract():
    contracts = load_contracts()

    result = contracts.error_record("speak", "run-4", KeyboardInterrupt())

    assert result["error_code"] == "cancelled"
    assert result["stage"] == "streaming"
    assert result["retryable"] is False


def test_cli_keyboard_interrupt_returns_130(monkeypatch, capsys):
    def interrupted(args):
        raise KeyboardInterrupt()

    monkeypatch.setattr(tts_client, "run_speak", interrupted)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tts_client.py",
            "--text",
            "会被取消",
            "--public-voice",
            "测试音色",
        ],
    )

    assert tts_client.main() == 130
    payload = json.loads(capsys.readouterr().err)
    assert payload["error_code"] == "cancelled"
    assert payload["operation"] == "speak"
