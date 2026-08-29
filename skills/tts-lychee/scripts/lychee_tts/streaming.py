from __future__ import annotations

from dataclasses import dataclass
import os
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

try:
    import websocket
except ImportError:  # pragma: no cover
    websocket = None

from .protocol import (
    AUDIO_ONLY_RESPONSE,
    ERROR_INFORMATION,
    EVENT_CONNECTION_FAILED,
    EVENT_CONNECTION_FINISHED,
    EVENT_CONNECTION_STARTED,
    EVENT_FINISH_CONNECTION,
    EVENT_FINISH_SESSION,
    EVENT_SESSION_FAILED,
    EVENT_SESSION_FINISHED,
    EVENT_SESSION_STARTED,
    EVENT_START_CONNECTION,
    EVENT_START_SESSION,
    EVENT_TASK_REQUEST,
    EVENT_TTS_RESPONSE,
    parse_response,
    send_packet,
)
from .sinks import AudioSink, PcmStream


DEFAULT_WS_URL = "wss://voice.lycheeai.com.cn/openapi/tts/ws_binary/v2"
STREAM_CODEC = "pcm"
STREAM_SAMPLE_RATE = 16000
STREAM_SPEED = 1.0
MAX_TEXT_LENGTH = 10000
# Smaller segments bound recovery cost while keeping connection overhead low for long-form speech.
SEGMENT_TEXT_LENGTH = 1000


class TtsStreamError(RuntimeError):
    pass


@dataclass(frozen=True)
class StreamResult:
    audio_bytes: int
    duration_ms: int
    first_audio_ms: Optional[int]
    segments: int


def split_text(text: str, max_length: int = SEGMENT_TEXT_LENGTH) -> List[str]:
    text = (text or "").strip()
    if max_length < 1 or max_length > MAX_TEXT_LENGTH:
        raise ValueError("max_length 无效")
    if len(text) <= max_length:
        return [text]
    result: List[str] = []
    remaining = text
    punctuation = "。！？!?；;\n"
    while remaining:
        if len(remaining) <= max_length:
            result.append(remaining.strip())
            break
        cut = max(remaining.rfind(mark, 0, max_length + 1) for mark in punctuation)
        if cut < max_length // 2:
            cut = max_length
        else:
            cut += 1
        result.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return [part for part in result if part]


class StreamingTtsClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        ws_url: Optional[str] = None,
        timeout: int = 90,
    ):
        self.api_key = api_key or os.getenv("TTS_API_KEY")
        self.ws_url = ws_url or os.getenv("TTS_WS_URL") or DEFAULT_WS_URL
        self.timeout = timeout

    @staticmethod
    def validate_stream_options(
        speed: float = STREAM_SPEED,
        codec: str = STREAM_CODEC,
        sample_rate: int = STREAM_SAMPLE_RATE,
    ) -> None:
        if speed != STREAM_SPEED:
            raise ValueError("真流式 TTS 只支持 speed=1.0")
        if codec != STREAM_CODEC:
            raise ValueError("真流式 TTS 只支持 codec=pcm")
        if sample_rate != STREAM_SAMPLE_RATE:
            raise ValueError("真流式 TTS 只支持 sample_rate=16000")

    @staticmethod
    def _error_text(payload: Any) -> str:
        if isinstance(payload, bytes):
            text = payload.decode("utf-8", "replace").strip()
        else:
            text = str(payload or "").strip()
        return text[:500] or "TTS 流式合成失败"

    def stream(
        self,
        text: str,
        speaker_id: str,
        sink: AudioSink,
        on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> StreamResult:
        if websocket is None:
            raise TtsStreamError(
                "缺少 websocket-client 依赖，请使用 Skill 启动脚本执行 --install-deps"
            )
        if not self.api_key:
            raise TtsStreamError("TTS_API_KEY 未配置")
        text = (text or "").strip()
        speaker_id = (speaker_id or "").strip()
        if not text:
            raise ValueError("text 不能为空")
        if not speaker_id:
            raise ValueError("speaker_id 不能为空")
        self.validate_stream_options()
        segments = split_text(text)
        started = time.monotonic()
        pcm = PcmStream(sink)
        first_audio_ms: Optional[int] = None
        opened = False

        def emit(name: str, **details: Any) -> None:
            if on_event:
                on_event(name, details)

        try:
            sink.open()
            opened = True
            for index, segment in enumerate(segments, start=1):
                segment_first = self._stream_segment(
                    segment,
                    speaker_id,
                    pcm,
                    started,
                    emit,
                    index,
                )
                if first_audio_ms is None and segment_first is not None:
                    first_audio_ms = segment_first
                emit("segment_finished", segment=index, total_segments=len(segments))
            pcm.finish()
            if pcm.bytes_written <= 0:
                raise TtsStreamError("TTS 完成但未返回音频")
            duration_ms = int((time.monotonic() - started) * 1000)
            sink.close(True)
            opened = False
            return StreamResult(pcm.bytes_written, duration_ms, first_audio_ms, len(segments))
        except Exception:
            if opened:
                try:
                    sink.close(False)
                except Exception:
                    pass
            raise

    def _stream_segment(
        self,
        text: str,
        speaker_id: str,
        pcm: PcmStream,
        overall_started: float,
        emit: Callable[..., None],
        segment_index: int,
    ) -> Optional[int]:
        session_id = uuid.uuid4().hex
        connection = None
        got_audio = False
        first_audio_ms: Optional[int] = None
        try:
            emit("connecting", segment=segment_index)
            try:
                connection = websocket.create_connection(
                    self.ws_url,
                    header=[f"api_key: {self.api_key}"],
                    timeout=self.timeout,
                )
            except Exception as exc:
                raise TtsStreamError("TTS WebSocket 连接失败") from exc

            send_packet(connection, EVENT_START_CONNECTION, {})
            while True:
                try:
                    raw = connection.recv()
                except Exception as exc:
                    timeout_error = getattr(websocket, "WebSocketTimeoutException", ())
                    if timeout_error and isinstance(exc, timeout_error):
                        raise TtsStreamError(
                            f"TTS 流式连接超过 {self.timeout} 秒未收到数据"
                        ) from exc
                    raise TtsStreamError("TTS WebSocket 接收失败") from exc
                if raw is None or raw == b"":
                    raise TtsStreamError("TTS WebSocket 提前关闭")
                if isinstance(raw, str):
                    continue
                try:
                    response = parse_response(raw)
                except Exception as exc:
                    raise TtsStreamError("TTS 响应协议解析失败") from exc

                message_type = response.get("message_type")
                event = response.get("event")
                payload = response.get("payload") or b""
                if message_type == ERROR_INFORMATION:
                    raise TtsStreamError(
                        f"TTS 服务错误 {response.get('error_code')}: {self._error_text(payload)}"
                    )
                if event in (EVENT_CONNECTION_FAILED, EVENT_SESSION_FAILED):
                    raise TtsStreamError(f"TTS 会话失败 ({event}): {self._error_text(payload)}")
                if event == EVENT_CONNECTION_STARTED:
                    send_packet(
                        connection,
                        EVENT_START_SESSION,
                        {
                            "event": EVENT_START_SESSION,
                            "speaker_id": speaker_id,
                            "codec": STREAM_CODEC,
                            "sample_rate": STREAM_SAMPLE_RATE,
                            "speed": STREAM_SPEED,
                            "text_normalizer": True,
                        },
                        session_id,
                    )
                    emit("session_starting", segment=segment_index)
                elif event == EVENT_SESSION_STARTED:
                    send_packet(
                        connection,
                        EVENT_TASK_REQUEST,
                        {"event": EVENT_TASK_REQUEST, "text": text},
                        session_id,
                    )
                    send_packet(connection, EVENT_FINISH_SESSION, {}, session_id)
                    emit("text_sent", segment=segment_index)
                elif event == EVENT_TTS_RESPONSE:
                    if message_type == AUDIO_ONLY_RESPONSE and payload:
                        pcm.write(payload)
                        got_audio = True
                        if first_audio_ms is None:
                            first_audio_ms = int((time.monotonic() - overall_started) * 1000)
                            emit(
                                "first_audio",
                                segment=segment_index,
                                first_audio_ms=first_audio_ms,
                                bytes=pcm.bytes_written,
                            )
                elif event == EVENT_SESSION_FINISHED:
                    send_packet(connection, EVENT_FINISH_CONNECTION, {})
                elif event == EVENT_CONNECTION_FINISHED:
                    if not got_audio:
                        raise TtsStreamError("TTS 会话完成但没有音频")
                    emit("connection_finished", segment=segment_index)
                    return first_audio_ms
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
