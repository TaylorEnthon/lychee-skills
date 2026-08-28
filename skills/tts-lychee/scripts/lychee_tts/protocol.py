from __future__ import annotations

import json
import struct
from typing import Any, Dict, Optional, Tuple

try:
    import websocket
except ImportError:  # pragma: no cover
    websocket = None


PROTOCOL_VERSION = 0b0001
DEFAULT_HEADER_SIZE = 0b0001
FULL_CLIENT_REQUEST = 0b0001
AUDIO_ONLY_RESPONSE = 0b1011
FULL_SERVER_RESPONSE = 0b1001
ERROR_INFORMATION = 0b1111
MSG_TYPE_FLAG_WITH_EVENT = 0b0100
JSON_SERIALIZATION = 0b0001
COMPRESSION_NO = 0b0000

EVENT_START_CONNECTION = 1
EVENT_FINISH_CONNECTION = 2
EVENT_CONNECTION_STARTED = 50
EVENT_CONNECTION_FAILED = 51
EVENT_CONNECTION_FINISHED = 52
EVENT_START_SESSION = 100
EVENT_FINISH_SESSION = 102
EVENT_SESSION_STARTED = 150
EVENT_SESSION_FINISHED = 152
EVENT_SESSION_FAILED = 153
EVENT_TASK_REQUEST = 200
EVENT_TTS_SENTENCE_START = 350
EVENT_TTS_SENTENCE_END = 351
EVENT_TTS_RESPONSE = 352


class ProtocolError(ValueError):
    pass


def int_to_bytes(value: int) -> bytes:
    return struct.pack(">I", value)


def bytes_to_int(data: bytes) -> int:
    if len(data) != 4:
        raise ProtocolError("协议整数长度无效")
    return struct.unpack(">I", data)[0]


def make_header(message_type: int, serialization: int = JSON_SERIALIZATION) -> bytes:
    return bytes([
        (PROTOCOL_VERSION << 4) | DEFAULT_HEADER_SIZE,
        (message_type << 4) | MSG_TYPE_FLAG_WITH_EVENT,
        (serialization << 4) | COMPRESSION_NO,
        0,
    ])


def make_optional(event: int, session_id: Optional[str] = None) -> bytes:
    output = int_to_bytes(event)
    if session_id is not None:
        encoded = session_id.encode("utf-8")
        output += int_to_bytes(len(encoded)) + encoded
    return output


def make_packet(event: int, payload: Dict[str, Any], session_id: Optional[str] = None) -> bytes:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return make_header(FULL_CLIENT_REQUEST) + make_optional(event, session_id) + int_to_bytes(len(encoded)) + encoded


def _read_sized(view: memoryview, offset: int) -> Tuple[bytes, int]:
    if offset + 4 > len(view):
        raise ProtocolError("协议缺少长度字段")
    size = struct.unpack(">I", view[offset:offset + 4])[0]
    offset += 4
    end = offset + size
    if end > len(view):
        raise ProtocolError("协议长度超过响应范围")
    return view[offset:end].tobytes(), end


def parse_response(data: Any) -> Dict[str, Any]:
    if isinstance(data, memoryview):
        view = data
    else:
        view = memoryview(bytes(data))
    if len(view) < 4:
        raise ProtocolError("response too short")
    header_size = (view[0] & 0x0F) * 4
    if header_size < 4 or header_size > len(view):
        raise ProtocolError("响应头长度无效")
    message_type = (view[1] >> 4) & 0x0F
    flags = view[1] & 0x0F
    offset = header_size
    event = 0
    if message_type == ERROR_INFORMATION:
        if offset + 4 > len(view):
            raise ProtocolError("错误响应缺少错误码")
        error_code = struct.unpack(">I", view[offset:offset + 4])[0]
        offset += 4
        payload, _ = _read_sized(view, offset)
        return {
            "message_type": message_type,
            "event": event,
            "payload": payload,
            "error_code": error_code,
        }

    if flags == MSG_TYPE_FLAG_WITH_EVENT:
        if offset + 4 > len(view):
            raise ProtocolError("响应缺少 event")
        event = struct.unpack(">I", view[offset:offset + 4])[0]
        offset += 4

    result: Dict[str, Any] = {
        "message_type": message_type,
        "event": event,
        "session_id": None,
        "payload": b"",
    }
    if offset >= len(view):
        return result

    first, offset = _read_sized(view, offset)
    if event == EVENT_CONNECTION_STARTED:
        result["connection_id"] = first.decode("utf-8", "replace")
    else:
        result["session_id"] = first.decode("utf-8", "replace")
    if offset < len(view):
        result["payload"], offset = _read_sized(view, offset)
    return result


def send_packet(ws: Any, event: int, payload: Dict[str, Any], session_id: Optional[str] = None) -> None:
    packet = make_packet(event, payload, session_id)
    opcode = getattr(getattr(websocket, "ABNF", None), "OPCODE_BINARY", None)
    if opcode is None:
        ws.send(packet)
    else:
        ws.send(packet, opcode=opcode)
