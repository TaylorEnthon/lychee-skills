#!/usr/bin/env python3
"""Preset WebSocket TTS client for ShortDrama-Translator.

Input: text + voice name/description.
Output: JSON with base64 mp3, or write mp3 when --output is provided.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime
import json
import os
import re
import struct
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    import websocket
except ImportError:  # pragma: no cover
    websocket = None

DEFAULT_WS_URL = "wss://shanhaistudio.lycheeai.com.cn/openapi/tts/ws_binary/v2"
DEFAULT_VOICE_ID = "默认女声"

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
EVENT_TTS_SENTENCE_END = 351
EVENT_TTS_RESPONSE = 352


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

def data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def load_json(name: str) -> Dict[str, Any]:
    path = data_dir() / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_optional_json(name: str) -> Dict[str, Any]:
    path = data_dir() / name
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_speaker_id(preset: Dict[str, Any]) -> str:
    speaker_ref = preset.get("speaker_ref")
    if isinstance(speaker_ref, str) and speaker_ref:
        encoded = speaker_ref[4:] if speaker_ref.startswith("b64:") else speaker_ref
        return base64.b64decode(encoded).decode("utf-8")
    speaker_id = preset.get("speaker_id")
    if isinstance(speaker_id, str) and speaker_id:
        return speaker_id
    raise ValueError("preset is missing speaker reference")


def supports_contains_matching(preset: Dict[str, Any]) -> bool:
    return preset.get("match_mode", "normal") != "exact"


def resolve_voice_id(
    user_voice: Optional[str],
    alias_map: Dict[str, str],
    presets: Dict[str, Any],
    voice_aliases: Optional[Dict[str, Any]] = None,
) -> Tuple[str, bool, Optional[str]]:
    if not user_voice:
        return DEFAULT_VOICE_ID, True, None

    voice = user_voice.strip()
    if voice in alias_map:
        return alias_map[voice], False, voice
    if voice in presets:
        return voice, False, voice

    # Prefer longer official aliases so specific names win before shorter overlapping names.
    for alias in sorted(alias_map.keys(), key=len, reverse=True):
        voice_id = alias_map[alias]
        if alias in voice and voice_id in presets and supports_contains_matching(presets[voice_id]):
            return voice_id, False, alias

    expanded_aliases = []
    for voice_id, aliases in (voice_aliases or {}).items():
        if voice_id not in presets or not isinstance(aliases, list) or not supports_contains_matching(presets[voice_id]):
            continue
        for alias in aliases:
            if isinstance(alias, str) and alias:
                expanded_aliases.append((alias, voice_id))
    for alias, voice_id in sorted(expanded_aliases, key=lambda item: len(item[0]), reverse=True):
        if alias in voice:
            return voice_id, False, alias

    keyword_rules = [
        (("男童",), "小男孩声音"),
        (("女童",), "小女孩声音"),
        (("东北", "男"), "东北话男声"),
        (("东北", "女"), "东北话女声"),
        (("四川", "男"), "四川话男声"),
        (("四川", "女"), "四川话女声"),
        (("河南", "男"), "河南话男声"),
        (("河南", "女"), "河南话女声"),
        (("陕西", "男"), "陕西话男声"),
        (("陕西", "女"), "陕西话女声"),
        (("播音", "男"), "播音员男声"),
        (("播音", "女"), "播音员女声"),
        (("新闻", "男"), "播音员男声"),
        (("新闻", "女"), "播音员女声"),
        (("旁白",), "旁白男声"),
        (("客服", "男"), "客服男声"),
        (("客服", "女"), "客服女声"),
        (("助眠", "男"), "助眠男声"),
        (("助眠", "女"), "助眠女声"),
        (("耳语", "男"), "耳语男声"),
        (("耳语", "女"), "耳语女声"),
        (("低沉", "男"), "低沉男声"),
        (("低沉", "女"), "低沉女声"),
        (("甜", "女"), "甜美女声"),
        (("温柔",), "温柔女声"),
    ]
    for keywords, alias in keyword_rules:
        if all(keyword in voice for keyword in keywords) and alias in alias_map:
            return alias_map[alias], False, alias

    if "男" in voice and "默认男声" in alias_map:
        return alias_map["默认男声"], True, None
    if "女" in voice and "默认女声" in alias_map:
        return alias_map["默认女声"], True, None

    return DEFAULT_VOICE_ID, True, None


def int_to_bytes(value: int) -> bytes:
    return struct.pack(">I", value)


def bytes_to_int(data: bytes) -> int:
    return struct.unpack(">I", data)[0]


def make_header(message_type: int, serialization: int = JSON_SERIALIZATION) -> bytes:
    return bytes([
        (PROTOCOL_VERSION << 4) | DEFAULT_HEADER_SIZE,
        (message_type << 4) | MSG_TYPE_FLAG_WITH_EVENT,
        (serialization << 4) | COMPRESSION_NO,
        0,
    ])


def make_optional(event: int, session_id: Optional[str] = None) -> bytes:
    data = int_to_bytes(event)
    if session_id is not None:
        session_bytes = session_id.encode("utf-8")
        data += int_to_bytes(len(session_bytes)) + session_bytes
    return data


def make_packet(event: int, payload: Dict[str, Any], session_id: Optional[str] = None) -> bytes:
    payload_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return make_header(FULL_CLIENT_REQUEST) + make_optional(event, session_id) + int_to_bytes(len(payload_bytes)) + payload_bytes


def read_sized_bytes(data: bytes, offset: int) -> Tuple[bytes, int]:
    size = bytes_to_int(data[offset:offset + 4])
    offset += 4
    return data[offset:offset + size], offset + size


def parse_response(data: bytes) -> Dict[str, Any]:
    if len(data) < 4:
        raise ValueError("response too short")

    message_type = (data[1] >> 4) & 0x0F
    flags = data[1] & 0x0F
    offset = 4
    event = 0
    session_id = None
    payload = b""
    meta = None
    error_code = None

    if message_type == ERROR_INFORMATION:
        error_code = bytes_to_int(data[offset:offset + 4])
        offset += 4
        payload, offset = read_sized_bytes(data, offset)
        return {"message_type": message_type, "event": event, "payload": payload, "error_code": error_code}

    if flags == MSG_TYPE_FLAG_WITH_EVENT:
        event = bytes_to_int(data[offset:offset + 4])
        offset += 4

    if event == EVENT_CONNECTION_STARTED:
        connection_id, offset = read_sized_bytes(data, offset)
        if offset < len(data):
            payload, offset = read_sized_bytes(data, offset)
        return {"message_type": message_type, "event": event, "connection_id": connection_id.decode("utf-8", "replace"), "payload": payload}

    if event in (EVENT_SESSION_STARTED, EVENT_SESSION_FINISHED, EVENT_SESSION_FAILED):
        session_raw, offset = read_sized_bytes(data, offset)
        session_id = session_raw.decode("utf-8", "replace")
        if offset < len(data):
            meta_raw, offset = read_sized_bytes(data, offset)
            meta = meta_raw.decode("utf-8", "replace")
        return {"message_type": message_type, "event": event, "session_id": session_id, "meta": meta}

    if event:
        if offset + 4 <= len(data):
            maybe_size = bytes_to_int(data[offset:offset + 4])
            if offset + 4 + maybe_size <= len(data):
                session_raw, offset = read_sized_bytes(data, offset)
                session_id = session_raw.decode("utf-8", "replace")
        if offset + 4 <= len(data):
            payload, offset = read_sized_bytes(data, offset)

    return {"message_type": message_type, "event": event, "session_id": session_id, "payload": payload}


def send_packet(ws: Any, event: int, payload: Dict[str, Any], session_id: Optional[str] = None) -> None:
    ws.send(make_packet(event, payload, session_id), opcode=websocket.ABNF.OPCODE_BINARY)


def synthesize(text: str, voice: Optional[str] = None, timeout: int = 90) -> Dict[str, Any]:
    if websocket is None:
        raise RuntimeError("Missing dependency: install websocket-client with `python3 -m pip install websocket-client`")
    if not text or not text.strip():
        raise ValueError("text is required")

    api_key = os.getenv("TTS_API_KEY")
    if not api_key:
        raise RuntimeError("TTS_API_KEY is required. Get an API Key from https://shanhaistudio.lycheeai.com.cn/")

    alias_map = load_json("alias_map.json")
    presets = load_json("presets.json")
    voice_aliases = load_optional_json("voice_aliases.json")
    voice_id, used_default, matched_alias = resolve_voice_id(voice, alias_map, presets, voice_aliases)
    preset = presets[voice_id]
    speaker_id = resolve_speaker_id(preset)

    ws_url = os.getenv("TTS_WS_URL", DEFAULT_WS_URL)
    session_id = uuid.uuid4().hex
    audio = bytearray()
    started = time.monotonic()

    ws = websocket.create_connection(ws_url, header=[f"api_key: {api_key}"], timeout=timeout)
    try:
        send_packet(ws, EVENT_START_CONNECTION, {})
        while True:
            if time.monotonic() - started > timeout:
                raise TimeoutError("TTS timed out")
            raw = ws.recv()
            if isinstance(raw, str):
                continue
            res = parse_response(raw)
            event = res.get("event")
            message_type = res.get("message_type")

            if message_type == ERROR_INFORMATION:
                raise RuntimeError(f"TTS error {res.get('error_code')}: {res.get('payload', b'').decode('utf-8', 'replace')}")
            if event in (EVENT_CONNECTION_FAILED, EVENT_SESSION_FAILED):
                raise RuntimeError(f"TTS failed at event {event}: {res.get('meta') or res.get('payload')}")
            if event == EVENT_CONNECTION_STARTED:
                send_packet(ws, EVENT_START_SESSION, {
                    "event": EVENT_START_SESSION,
                    "codec": "mp3",
                    "sample_rate": 24000,
                    "speaker_id": speaker_id,
                    "speed": 1.0,
                }, session_id)
            elif event == EVENT_SESSION_STARTED:
                send_packet(ws, EVENT_TASK_REQUEST, {"event": EVENT_TASK_REQUEST, "text": text}, session_id)
                send_packet(ws, EVENT_FINISH_SESSION, {}, session_id)
            elif event == EVENT_TTS_RESPONSE:
                payload = res.get("payload") or b""
                if message_type == AUDIO_ONLY_RESPONSE and payload:
                    audio.extend(payload)
            elif event == EVENT_SESSION_FINISHED:
                send_packet(ws, EVENT_FINISH_CONNECTION, {})
            elif event == EVENT_CONNECTION_FINISHED:
                break

        if not audio:
            raise RuntimeError("TTS completed without audio payload")

        return {
            "success": True,
            "audio_data": base64.b64encode(bytes(audio)).decode("ascii"),
            "voice": preset["name"],
            "voice_id": voice_id,
            "used_default_voice": used_default,
            "matched_alias": matched_alias,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    finally:
        ws.close()



def sanitize_filename_part(value: str, max_chars: int = 16) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\r\n\t，。！？、；：‘’“”（）【】《》]+", "", value or "")
    cleaned = re.sub(r"\s+", "", cleaned).strip(". ")
    return cleaned[:max_chars] or "默认音色"


def load_voice_data() -> Tuple[Dict[str, str], Dict[str, Any], Dict[str, Any]]:
    return load_json("alias_map.json"), load_json("presets.json"), load_optional_json("voice_aliases.json")


def preview_match(voice: Optional[str]) -> Dict[str, Any]:
    alias_map, presets, voice_aliases = load_voice_data()
    voice_id, used_default, matched_alias = resolve_voice_id(voice, alias_map, presets, voice_aliases)
    preset = presets[voice_id]
    result = {
        "success": True,
        "voice": preset["name"],
        "used_default_voice": used_default,
    }
    if matched_alias:
        result["matched"] = matched_alias
    return result


def list_voices(presets: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    voice_presets = presets or load_json("presets.json")
    categories = []
    category_map = {}

    for preset in voice_presets.values():
        if not preset.get("listable", True):
            continue
        category = preset.get("category", "扩展")
        if category not in category_map:
            category_map[category] = []
            categories.append(category)
        category_map[category].append(preset["name"])

    return {
        "success": True,
        "categories": [{"name": name, "voices": category_map[name]} for name in categories],
    }


def run_doctor() -> Dict[str, Any]:
    checks = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    def has_required_preset_fields(preset: Any) -> bool:
        return (
            isinstance(preset, dict)
            and isinstance(preset.get("name"), str)
            and bool(preset.get("name"))
            and bool(preset.get("speaker_ref") or preset.get("speaker_id"))
        )

    add("python", sys.version_info >= (3, 8), f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    add("websocket-client", websocket is not None, "installed" if websocket is not None else "missing: python -m pip install websocket-client")
    add("TTS_API_KEY", bool(os.getenv("TTS_API_KEY")), "set" if os.getenv("TTS_API_KEY") else "missing")

    try:
        alias_map, presets, voice_aliases = load_voice_data()
        add(
            "data files",
            isinstance(alias_map, dict) and isinstance(presets, dict) and isinstance(voice_aliases, dict),
            f"{len(presets)} presets, {len(alias_map)} aliases, {len(voice_aliases)} voice groups",
        )

        required_voices = ["默认女声", "默认男声", "性感女声", "小男孩声音", "云南话男声"]
        missing_voices = [
            voice_id
            for voice_id in required_voices
            if voice_id not in presets or not has_required_preset_fields(presets[voice_id])
        ]
        add(
            "core voices",
            not missing_voices,
            "ok" if not missing_voices else "missing or invalid: " + ", ".join(missing_voices),
        )

        broken_aliases = [
            alias
            for alias in ["默认女声", "默认男声", "性感女声", "小男孩声音", "云南话男声"]
            if alias_map.get(alias) not in presets
        ]
        add(
            "core aliases",
            not broken_aliases,
            "ok" if not broken_aliases else "broken: " + ", ".join(broken_aliases),
        )

        voice_id, used_default, matched_alias = resolve_voice_id("性感的女声", alias_map, presets, voice_aliases)
        add(
            "voice matching",
            voice_id == "性感女声" and not used_default,
            f"性感的女声 -> {voice_id} ({matched_alias})",
        )
    except Exception as exc:
        add("data files", False, str(exc))

    ok = all(item["ok"] for item in checks)
    return {"success": ok, "checks": checks}


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Generate TTS mp3 from preset voices.")
    parser.add_argument("--doctor", action="store_true", help="Run offline installation checks and exit")
    parser.add_argument("--list-voices", action="store_true", help="List public voice names and exit")
    parser.add_argument("--preview-match", help="Preview which public voice a description will use, without synthesis")
    parser.add_argument("--text", help="Text to synthesize")
    parser.add_argument("--voice", default="默认女声", help="Voice name or description")
    parser.add_argument("--output", help="Write mp3 to this path. Defaults to ./YYYYMMDD-voice_tts.mp3")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--debug", action="store_true", help="Include internal matching fields in JSON output")
    args = parser.parse_args()

    if args.doctor:
        result = run_doctor()
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("success") else 1
    if args.list_voices:
        print(json.dumps(list_voices(), ensure_ascii=False))
        return 0
    if args.preview_match is not None:
        print(json.dumps(preview_match(args.preview_match), ensure_ascii=False))
        return 0

    try:
        if not args.text:
            raise ValueError("text is required")
        result = synthesize(args.text, args.voice, args.timeout)
        audio_data = base64.b64decode(result.pop("audio_data"))
        voice_name = sanitize_filename_part(result.get("voice") or args.voice)
        output_arg = args.output or f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{voice_name}_tts.mp3"
        output_path = Path(output_arg)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_data)
        public_result = {
            "success": True,
            "output": str(output_path.resolve()),
            "voice": result.get("voice"),
            "duration_ms": result.get("duration_ms"),
        }
        if args.debug:
            public_result.update({
                "voice_id": result.get("voice_id"),
                "used_default_voice": result.get("used_default_voice"),
                "matched_alias": result.get("matched_alias"),
            })
        print(json.dumps(public_result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
