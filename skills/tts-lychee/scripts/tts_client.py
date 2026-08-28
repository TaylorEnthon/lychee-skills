#!/usr/bin/env python3
"""Live Lychee TTS CLI with PCM/16000 true streaming output."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lychee_tts.api import (  # noqa: E402
    LycheeApiClient,
    LycheeApiError,
    PublicVoice,
    VoiceSelectionError,
)
from lychee_tts.registry import StoredVoice, VoiceRegistry  # noqa: E402
from lychee_tts.sinks import PlaybackSink, TeeSink, WaveFileSink  # noqa: E402
from lychee_tts.streaming import StreamingTtsClient  # noqa: E402


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def sanitize_filename_part(value: str, max_chars: int = 20) -> str:
    import re

    cleaned = re.sub(r"[\\/:*?\"<>|\r\n\t，。！？、；：‘’“”（）【】《》]+", "", value or "")
    cleaned = re.sub(r"\s+", "", cleaned).strip(". ")
    return cleaned[:max_chars] or "speech"


def build_api(args: argparse.Namespace) -> LycheeApiClient:
    return LycheeApiClient(
        base_url=args.base_url,
        api_key=os.getenv("TTS_API_KEY"),
        timeout=args.timeout,
    )


def resolve_voice(args: argparse.Namespace, api: LycheeApiClient) -> Tuple[str, str, str]:
    if args.speaker_id:
        speaker_id = args.speaker_id.strip()
        if not speaker_id:
            raise ValueError("speaker_id 不能为空")
        return args.voice or speaker_id, speaker_id, "custom"
    requested = (args.voice or "").strip()
    if not requested:
        raise ValueError("请指定 --voice；可先使用 --list-voices 查询实时公共音色")
    stored = VoiceRegistry(args.registry).get(requested)
    try:
        voice = api.resolve_public_voice(requested)
    except VoiceSelectionError as exc:
        if exc.candidates or not stored:
            raise
        return stored.alias, stored.speaker_id, "custom"
    except LycheeApiError:
        if not stored:
            raise
        return stored.alias, stored.speaker_id, "custom"
    return voice.name, voice.name, "public"


def run_list_voices(args: argparse.Namespace) -> Dict[str, Any]:
    api = build_api(args)
    query = args.search_voices or args.voice_query
    voices = api.search_public_voices(query) if query else api.list_all_public_voices()
    return {
        "success": True,
        "query": query or "",
        "total": len(voices),
        "voices": [voice.to_dict() for voice in voices],
    }


def run_design(args: argparse.Namespace) -> Dict[str, Any]:
    result = build_api(args).design_voice(
        args.design_description,
        args.design_text,
        args.optimize_text,
    )
    return {
        "success": True,
        "preview_audio_url": result.audio_url,
        "design_request_id": result.request_id,
        "task_id": result.task_id,
    }


def run_clone(args: argparse.Namespace) -> Dict[str, Any]:
    if not args.clone_name:
        raise ValueError("音色克隆需要 --clone-name，作为本地个人音色别名")
    if not args.confirm_clone:
        raise ValueError("音色克隆需要明确确认，请添加 --confirm-clone")
    api = build_api(args)
    with tempfile.TemporaryDirectory(prefix="tts-lychee-") as temporary:
        if args.clone_audio:
            audio_path = Path(args.clone_audio)
        else:
            suffix = Path(urlparse(args.clone_url).path).suffix.lower()
            if suffix not in {".mp3", ".wav", ".m4a"}:
                suffix = ".wav"
            audio_path = api.download_audio(
                args.clone_url,
                Path(temporary) / f"design-preview{suffix}",
            )
        result = api.clone_voice(
            audio_path,
            body=args.clone_body,
            name=args.clone_name,
            description=args.clone_description,
            lang_code=args.clone_lang_code,
            gender=args.clone_gender,
            is_public=args.clone_is_public,
            clip_short=args.clone_clip_short,
        )
    stored = VoiceRegistry(args.registry).save(
        StoredVoice(
            alias=args.clone_name,
            speaker_id=result.speaker_id,
            description=args.clone_description or "",
            preview_audio_url=args.clone_url or "",
        )
    )
    output: Dict[str, Any] = {
        "success": True,
        "voice": stored.alias,
        "ready": True,
    }
    if args.debug:
        output["speaker_id"] = stored.speaker_id
        output["request_id"] = result.request_id
    return output


def run_doctor(args: argparse.Namespace) -> Dict[str, Any]:
    import importlib.util

    checks = []

    def add(name: str, ok: bool, detail: str, required: bool = True) -> None:
        checks.append({"name": name, "ok": ok, "required": required, "detail": detail})

    add(
        "python",
        sys.version_info >= (3, 8),
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    )
    websocket_installed = importlib.util.find_spec("websocket") is not None
    requests_installed = importlib.util.find_spec("requests") is not None
    add(
        "websocket-client",
        websocket_installed,
        "installed" if websocket_installed else "missing: python -m pip install -r requirements.txt",
    )
    add(
        "requests",
        requests_installed,
        "installed" if requests_installed else "missing: python -m pip install -r requirements.txt",
    )
    sounddevice_installed = PlaybackSink.dependency_available()
    add(
        "sounddevice",
        sounddevice_installed,
        "installed" if sounddevice_installed else "missing: playback will be unavailable",
        required=False,
    )
    add("TTS_API_KEY", bool(os.getenv("TTS_API_KEY")), "set" if os.getenv("TTS_API_KEY") else "missing")
    legacy_data = SCRIPT_DIR.parent / "data"
    add(
        "legacy voice data",
        not legacy_data.exists(),
        "not present" if not legacy_data.exists() else "remove obsolete data directory",
    )
    required_ok = all(item["ok"] for item in checks if item["required"])
    return {"success": required_ok, "checks": checks}


def run_speak(args: argparse.Namespace) -> Dict[str, Any]:
    api = build_api(args)
    voice_label, speaker_id, voice_kind = resolve_voice(args, api)
    output_path = Path(args.output) if args.output else Path(
        f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{sanitize_filename_part(voice_label)}_tts.wav"
    )
    if output_path.suffix.lower() != ".wav":
        raise ValueError("真流式模式输出必须使用 .wav 文件")

    sinks = [WaveFileSink(output_path, overwrite=args.overwrite)]
    warnings = []
    played = False
    if args.play:
        if PlaybackSink.dependency_available():
            sinks.append(PlaybackSink())
            played = True
        else:
            warnings.append("缺少 sounddevice，已改为只生成 WAV")

    progress = None
    if args.progress:
        def progress(name: str, details: Dict[str, Any]) -> None:
            print(json.dumps({"event": name, **details}, ensure_ascii=False), file=sys.stderr)

    result = StreamingTtsClient(
        api_key=os.getenv("TTS_API_KEY"),
        ws_url=args.ws_url,
        timeout=args.timeout,
    ).stream(args.text, speaker_id, TeeSink(sinks), on_event=progress)
    output: Dict[str, Any] = {
        "success": True,
        "output": str(output_path.resolve()),
        "voice": voice_label,
        "voice_kind": voice_kind,
        "format": "wav",
        "codec": "pcm_s16le",
        "sample_rate": 16000,
        "channels": 1,
        "bytes_written": result.audio_bytes,
        "duration_ms": result.duration_ms,
        "first_audio_ms": result.first_audio_ms,
        "segments": result.segments,
        "played": played,
    }
    if warnings:
        output["warnings"] = warnings
    if args.debug:
        output["speaker_id"] = speaker_id
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Lychee TTS as a true PCM stream.")
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--list-voices", action="store_true")
    parser.add_argument("--search-voices", metavar="NAME")
    parser.add_argument("--voice-query", metavar="NAME")
    parser.add_argument("--text")
    parser.add_argument("--voice", help="实时公共音色名称或已保存的个人音色别名")
    parser.add_argument("--speaker-id", help=argparse.SUPPRESS)
    parser.add_argument("--output")
    parser.add_argument("--play", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--progress", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--base-url", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--ws-url", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--registry", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--design-description")
    parser.add_argument("--design-text")
    parser.add_argument("--optimize-text", action="store_true")
    parser.add_argument("--clone-audio")
    parser.add_argument("--clone-url")
    parser.add_argument("--clone-name")
    parser.add_argument("--confirm-clone", action="store_true")
    parser.add_argument("--clone-body")
    parser.add_argument("--clone-description")
    parser.add_argument("--clone-lang-code")
    parser.add_argument("--clone-gender")
    parser.add_argument("--clone-is-public", action="store_true", default=None)
    parser.add_argument("--clone-clip-short", action="store_true", default=None)
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    return parser


def main() -> int:
    configure_stdio()
    args = build_parser().parse_args()
    try:
        if args.doctor:
            result = run_doctor(args)
        elif args.list_voices or args.search_voices or args.voice_query:
            result = run_list_voices(args)
        elif args.design_description is not None or args.design_text is not None:
            if not args.design_description or not args.design_text:
                raise ValueError("音色设计需要同时提供 --design-description 和 --design-text")
            result = run_design(args)
        elif args.clone_audio or args.clone_url:
            if bool(args.clone_audio) == bool(args.clone_url):
                raise ValueError("音色克隆必须且只能提供 --clone-audio 或 --clone-url")
            result = run_clone(args)
        else:
            if not args.text:
                raise ValueError("text is required")
            result = run_speak(args)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("success") else 1
    except VoiceSelectionError as exc:
        output: Dict[str, Any] = {"success": False, "error": str(exc)}
        if exc.candidates:
            output["candidates"] = [voice.to_dict() for voice in exc.candidates]
        print(json.dumps(output, ensure_ascii=False), file=sys.stderr)
        return 2
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
