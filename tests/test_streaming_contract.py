from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

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
from lychee_tts.contracts import error_record
from lychee_tts.streaming import (
    StreamResult,
    StreamingTtsClient,
    TtsStreamError,
    split_text,
)
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
        if isinstance(value, BaseException):
            raise value
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


def test_long_text_is_segmented_before_the_provider_limit():
    segments = split_text("测" * 1001)

    assert [len(segment) for segment in segments] == [1000, 1]


def test_continuous_frames_do_not_hit_a_total_wall_clock_timeout(monkeypatch):
    trace = []

    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

    clock = Clock()
    incoming = [
        response_packet(FULL_SERVER_RESPONSE, EVENT_CONNECTION_STARTED),
        response_packet(FULL_SERVER_RESPONSE, EVENT_SESSION_STARTED),
        response_packet(AUDIO_ONLY_RESPONSE, EVENT_TTS_RESPONSE, payload=b"\x01\x00"),
        response_packet(AUDIO_ONLY_RESPONSE, EVENT_TTS_RESPONSE, payload=b"\x02\x00"),
        response_packet(FULL_SERVER_RESPONSE, EVENT_SESSION_FINISHED),
        response_packet(FULL_SERVER_RESPONSE, EVENT_CONNECTION_FINISHED),
    ]

    class AdvancingWebSocket(FakeWebSocket):
        def recv(self):
            clock.now += 20
            return super().recv()

    socket = AdvancingWebSocket(incoming, trace)
    monkeypatch.setattr("lychee_tts.streaming.time.monotonic", clock.monotonic)
    monkeypatch.setattr("lychee_tts.streaming.websocket.create_connection", lambda *args, **kwargs: socket)

    result = StreamingTtsClient(api_key="test-key", timeout=30).stream(
        "持续输出的长文本", "清新少女", FakeSink(trace)
    )

    assert result.audio_bytes == 4
    assert result.duration_ms >= 100_000


def test_unknown_frames_do_not_reset_meaningful_progress_timeout(monkeypatch):
    trace = []

    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

    clock = Clock()

    class AdvancingWebSocket(FakeWebSocket):
        def recv(self):
            clock.now += 11
            return super().recv()

    def make_socket():
        return AdvancingWebSocket(
            [
                response_packet(FULL_SERVER_RESPONSE, EVENT_CONNECTION_STARTED),
                "ignored text frame 1",
                "ignored text frame 2",
                "ignored text frame 3",
            ],
            trace,
        )

    attempts = []

    def create_connection(*args, **kwargs):
        attempts.append(1)
        return make_socket()

    monkeypatch.setattr("lychee_tts.streaming.time.monotonic", clock.monotonic)
    monkeypatch.setattr(
        "lychee_tts.streaming.websocket.create_connection",
        create_connection,
    )

    with pytest.raises(TtsStreamError, match="有效进展"):
        StreamingTtsClient(api_key="test-key", timeout=30).stream(
            "不能被无意义帧无限拖住", "清新少女", FakeSink(trace)
        )

    assert ("sink.close", False) in trace
    assert len(attempts) == 2


def test_pre_audio_transport_failure_retries_once(monkeypatch):
    trace = []
    successful_socket = FakeWebSocket(
        [
            response_packet(FULL_SERVER_RESPONSE, EVENT_CONNECTION_STARTED),
            response_packet(FULL_SERVER_RESPONSE, EVENT_SESSION_STARTED),
            response_packet(AUDIO_ONLY_RESPONSE, EVENT_TTS_RESPONSE, payload=b"\x01\x00"),
            response_packet(FULL_SERVER_RESPONSE, EVENT_SESSION_FINISHED),
            response_packet(FULL_SERVER_RESPONSE, EVENT_CONNECTION_FINISHED),
        ],
        trace,
    )
    attempts = []

    def create_connection(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("temporary connection failure")
        return successful_socket

    monkeypatch.setattr(
        "lychee_tts.streaming.websocket.create_connection", create_connection
    )
    events = []

    def on_event(name, details):
        events.append((name, details))

    result = StreamingTtsClient(api_key="test-key").stream(
        "连接恢复后继续", "清新少女", FakeSink(trace), on_event=on_event
    )

    assert len(attempts) == 2
    assert result.audio_bytes == 2
    assert ("sink.close", True) in trace
    retry = next(details for name, details in events if name == "segment_retrying")
    assert retry["attempt"] == 2
    assert retry["max_attempts"] == 2


def test_post_audio_transport_failure_is_not_retried(monkeypatch):
    trace = []
    socket = FakeWebSocket(
        [
            response_packet(FULL_SERVER_RESPONSE, EVENT_CONNECTION_STARTED),
            response_packet(FULL_SERVER_RESPONSE, EVENT_SESSION_STARTED),
            response_packet(AUDIO_ONLY_RESPONSE, EVENT_TTS_RESPONSE, payload=b"\x01\x00"),
            OSError("connection lost after audio"),
        ],
        trace,
    )
    attempts = []

    def create_connection(*args, **kwargs):
        attempts.append(1)
        return socket

    monkeypatch.setattr(
        "lychee_tts.streaming.websocket.create_connection", create_connection
    )

    with pytest.raises(TtsStreamError, match="接收失败"):
        StreamingTtsClient(api_key="test-key").stream(
            "已收到音频后失败", "清新少女", FakeSink(trace)
        )

    assert len(attempts) == 1
    assert ("sink.close", False) in trace


def test_partial_pcm_sample_also_disables_retry(monkeypatch):
    trace = []
    socket = FakeWebSocket(
        [
            response_packet(FULL_SERVER_RESPONSE, EVENT_CONNECTION_STARTED),
            response_packet(FULL_SERVER_RESPONSE, EVENT_SESSION_STARTED),
            response_packet(AUDIO_ONLY_RESPONSE, EVENT_TTS_RESPONSE, payload=b"\x01"),
            OSError("connection lost after one PCM byte"),
        ],
        trace,
    )
    attempts = []

    def create_connection(*args, **kwargs):
        attempts.append(1)
        return socket

    monkeypatch.setattr(
        "lychee_tts.streaming.websocket.create_connection", create_connection
    )

    with pytest.raises(TtsStreamError, match="接收失败"):
        StreamingTtsClient(api_key="test-key").stream(
            "单字节也代表服务已开始输出", "清新少女", FakeSink(trace)
        )

    assert len(attempts) == 1


def test_keyboard_interrupt_closes_the_sink_as_failed(monkeypatch):
    trace = []
    socket = FakeWebSocket([KeyboardInterrupt()], trace)
    monkeypatch.setattr(
        "lychee_tts.streaming.websocket.create_connection",
        lambda *args, **kwargs: socket,
    )

    with pytest.raises(KeyboardInterrupt):
        StreamingTtsClient(api_key="test-key").stream(
            "用户主动中断", "清新少女", FakeSink(trace)
        )

    assert ("sink.close", False) in trace
    assert any(item[0] == "close" for item in trace)


def test_playback_open_failure_falls_back_to_a_valid_wav(tmp_path, monkeypatch):
    output = tmp_path / "speech.wav"
    args = tts_client.build_parser().parse_args([
        "--text", "你好", "--voice", "清新少女", "--output", str(output), "--play",
    ])

    class FailingPlaybackSink:
        @staticmethod
        def dependency_available():
            return True

        def open(self):
            raise RuntimeError("没有可用的输出设备")

        def write(self, chunk):
            raise AssertionError("failed playback must not receive data")

        def close(self, success):
            pass

    class FakeStreamingClient:
        def __init__(self, **kwargs):
            pass

        def stream(self, text, speaker_id, sink, on_event=None):
            sink.open()
            sink.write(b"\x01\x00\x02\x00")
            sink.close(True)
            return StreamResult(4, 10, 5, 1)

    monkeypatch.setattr(tts_client, "build_api", lambda args: SimpleNamespace())
    monkeypatch.setattr(tts_client, "resolve_voice", lambda args, api: ("清新少女", "清新少女", "public"))
    monkeypatch.setattr(tts_client, "PlaybackSink", FailingPlaybackSink)
    monkeypatch.setattr(tts_client, "StreamingTtsClient", FakeStreamingClient)

    result = tts_client.run_speak(args)

    assert output.exists()
    assert result["success"] is True
    assert result["played"] is False
    assert any("输出设备" in warning for warning in result["warnings"])


def test_streaming_cli_error_exposes_a_playable_partial_wav(tmp_path, monkeypatch):
    output = tmp_path / "speech.wav"
    args = tts_client.build_parser().parse_args([
        "--text", "这段语音会在中途失败", "--voice", "清新少女", "--output", str(output),
    ])

    class FailingStreamingClient:
        def __init__(self, **kwargs):
            pass

        def stream(self, text, speaker_id, sink, on_event=None):
            sink.open()
            sink.write(b"\x01\x00\x02\x00")
            sink.close(False)
            raise TtsStreamError("连接在音频传输中断开")

    monkeypatch.setattr(tts_client, "build_api", lambda args: SimpleNamespace())
    monkeypatch.setattr(
        tts_client,
        "resolve_voice",
        lambda args, api: ("清新少女", "清新少女", "public"),
    )
    monkeypatch.setattr(tts_client, "StreamingTtsClient", FailingStreamingClient)

    with pytest.raises(TtsStreamError) as raised:
        tts_client.run_speak(args)

    contract = error_record("speak", "test-run", raised.value)
    partial = Path(contract["partial_output"])
    assert partial.exists()
    assert partial.name.startswith("speech.partial-")
    with wave.open(str(partial), "rb") as reader:
        assert reader.readframes(2) == b"\x01\x00\x02\x00"
