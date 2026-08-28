from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from lychee_tts.protocol import (
    AUDIO_ONLY_RESPONSE,
    ERROR_INFORMATION,
    EVENT_CONNECTION_FINISHED,
    EVENT_CONNECTION_STARTED,
    EVENT_SESSION_FINISHED,
    EVENT_SESSION_STARTED,
    EVENT_TTS_RESPONSE,
    FULL_SERVER_RESPONSE,
    make_header,
    make_optional,
    parse_response,
)
from lychee_tts.streaming import StreamingTtsClient
import tts_client


def response_packet(message_type, event, session_id=None, payload=b""):
    packet = bytearray(make_header(message_type))
    packet.extend(make_optional(event))
    if event == EVENT_CONNECTION_STARTED:
        first = b"connection-1"
    else:
        first = (session_id or "session-1").encode()
    packet.extend(len(first).to_bytes(4, "big"))
    packet.extend(first)
    packet.extend(len(payload).to_bytes(4, "big"))
    packet.extend(payload)
    return bytes(packet)


class FakeWebSocket:
    def __init__(self, incoming, trace):
        self.incoming = list(incoming)
        self.trace = trace

    def send(self, data, opcode=None):
        self.trace.append(("send", data, opcode))

    def recv(self):
        value = self.incoming.pop(0)
        self.trace.append(("recv", value))
        return value

    def close(self, *args):
        self.trace.append(("close", args))


class FakeSink:
    def __init__(self, trace):
        self.trace = trace
        self.chunks = []

    def open(self):
        self.trace.append(("sink.open",))

    def write(self, chunk):
        self.chunks.append(bytes(chunk))
        self.trace.append(("sink.write", bytes(chunk)))

    def close(self, success):
        self.trace.append(("sink.close", success))


def test_first_pcm_chunk_is_written_before_connection_finishes(monkeypatch):
    trace = []
    incoming = [
        response_packet(FULL_SERVER_RESPONSE, EVENT_CONNECTION_STARTED),
        response_packet(FULL_SERVER_RESPONSE, EVENT_SESSION_STARTED),
        response_packet(AUDIO_ONLY_RESPONSE, EVENT_TTS_RESPONSE, payload=b"\x01\x00\x02\x00"),
        response_packet(FULL_SERVER_RESPONSE, EVENT_SESSION_FINISHED),
        response_packet(FULL_SERVER_RESPONSE, EVENT_CONNECTION_FINISHED),
    ]
    socket = FakeWebSocket(incoming, trace)
    monkeypatch.setattr("lychee_tts.streaming.websocket.create_connection", lambda *args, **kwargs: socket)
    sink = FakeSink(trace)

    result = StreamingTtsClient(api_key="test-key").stream("你好", "清新少女", sink)

    assert sink.chunks == [b"\x01\x00\x02\x00"]
    assert result.audio_bytes == 4
    write_index = next(i for i, item in enumerate(trace) if item[0] == "sink.write")
    finish_index = next(i for i, item in enumerate(trace) if item[0] == "sink.close")
    assert write_index < finish_index

    sent_payloads = []
    for item in trace:
        if item[0] == "send":
            packet = item[1]
            sent_payloads.append(packet)
    start_session = sent_payloads[1]
    assert b'"codec":"pcm"' in start_session
    assert b'"sample_rate":16000' in start_session
    assert b'"speed":1.0' in start_session
    assert write_index < next(
        i for i, item in enumerate(trace)
        if item[0] == "send" and int.from_bytes(item[1][4:8], "big") == 2
    )


def test_stream_does_not_accept_non_realtime_speed():
    try:
        StreamingTtsClient(api_key="test-key").validate_stream_options(speed=0.9)
    except ValueError as exc:
        assert "1.0" in str(exc)
    else:
        raise AssertionError("non-1.0 streaming speed must be rejected")


def test_stream_failure_closes_sink_without_committing_output(monkeypatch):
    trace = []
    incoming = [
        response_packet(FULL_SERVER_RESPONSE, EVENT_CONNECTION_STARTED),
        response_packet(FULL_SERVER_RESPONSE, 51, payload=b"upstream failed"),
    ]
    socket = FakeWebSocket(incoming, trace)
    monkeypatch.setattr("lychee_tts.streaming.websocket.create_connection", lambda *args, **kwargs: socket)
    sink = FakeSink(trace)

    try:
        StreamingTtsClient(api_key="test-key").stream("你好", "清新少女", sink)
    except RuntimeError as exc:
        assert "会话失败" in str(exc)
    else:
        raise AssertionError("upstream failure must fail the stream")

    assert ("sink.close", False) in trace


def test_streaming_cli_rejects_non_wav_output(monkeypatch):
    args = tts_client.build_parser().parse_args([
        "--text", "你好", "--voice", "清新少女", "--output", "speech.mp3",
    ])
    monkeypatch.setattr(tts_client, "build_api", lambda args: SimpleNamespace())
    monkeypatch.setattr(tts_client, "resolve_voice", lambda args, api: ("清新少女", "清新少女", "public"))

    try:
        tts_client.run_speak(args)
    except ValueError as exc:
        assert ".wav" in str(exc)
    else:
        raise AssertionError("streaming output must reject mp3 paths")


def test_error_information_frame_reads_error_code_after_header():
    payload = b"invalid request"
    packet = bytearray(make_header(ERROR_INFORMATION))
    packet.extend((45000001).to_bytes(4, "big"))
    packet.extend(len(payload).to_bytes(4, "big"))
    packet.extend(payload)

    result = parse_response(bytes(packet))

    assert result["error_code"] == 45000001
    assert result["payload"] == payload
