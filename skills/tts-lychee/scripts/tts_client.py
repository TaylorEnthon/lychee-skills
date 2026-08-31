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
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lychee_tts.api import (  # noqa: E402
    LycheeApiClient,
    VoiceSelectionError,
)
from lychee_tts.contracts import (  # noqa: E402
    error_record,
    event_record,
    new_run_id,
    result_record,
)
from lychee_tts.registry import StoredVoice, VoiceRegistry  # noqa: E402
from lychee_tts.sinks import (  # noqa: E402
    BestEffortSink,
    PlaybackSink,
    QueuedSink,
    TeeSink,
    WaveFileSink,
)
from lychee_tts.streaming import StreamingTtsClient  # noqa: E402
from lychee_tts.voices import VoiceResolver  # noqa: E402


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
    reference = VoiceResolver(api, VoiceRegistry(args.registry)).resolve(
        public_name=args.public_voice,
        personal_alias=args.personal_voice,
        legacy_name=args.voice,
        speaker_id=args.speaker_id,
    )
    output_kind = "custom" if reference.kind == "personal" else reference.kind
    return reference.display_name, reference.speaker_id, output_kind


def run_list_voices(args: argparse.Namespace) -> Dict[str, Any]:
    api = build_api(args)
    query = args.search_voices or args.voice_query
    if query:
        matches = api.search_public_voice_matches(query)
        voices = [match.to_dict() for match in matches]
    else:
        voices = [voice.to_dict() for voice in api.list_all_public_voices()]
    return {
        "success": True,
        "query": query or "",
        "total": len(voices),
        "voices": voices,
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
    registry = VoiceRegistry(args.registry)
    if registry.get(args.clone_name) and not args.replace_personal_voice:
        raise FileExistsError(
            f"个人音色别名已存在：{args.clone_name}；确认替换时添加 --replace-personal-voice"
        )
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
    stored = registry.save(
        StoredVoice(
            alias=args.clone_name,
            speaker_id=result.speaker_id,
            description=args.clone_description or "",
            preview_audio_url=args.clone_url or "",
        ),
        replace=args.replace_personal_voice,
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


def run_list_personal_voices(args: argparse.Namespace) -> Dict[str, Any]:
    voices = sorted(VoiceRegistry(args.registry).list(), key=lambda item: item.alias.casefold())
    return {
        "success": True,
        "total": len(voices),
        "voices": [
            {
                "alias": voice.alias,
                "description": voice.description,
                "preview_audio_url": voice.preview_audio_url,
                "created_at": voice.created_at,
            }
            for voice in voices
        ],
    }


def run_remove_personal_voice(args: argparse.Namespace) -> Dict[str, Any]:
    if not args.confirm_remove:
        raise ValueError("删除个人音色别名需要明确确认，请添加 --confirm-remove")
    alias = (args.remove_personal_voice or "").strip()
    registry = VoiceRegistry(args.registry)
    if not registry.remove(alias):
        raise ValueError(f"未找到个人音色：{alias}")
    return {"success": True, "voice": alias, "removed": True, "scope": "local_alias"}


def run_rename_personal_voice(args: argparse.Namespace) -> Dict[str, Any]:
    if not args.confirm_rename:
        raise ValueError("重命名个人音色需要明确确认，请添加 --confirm-rename")
    if not args.new_personal_voice_name:
        raise ValueError("重命名个人音色需要 --new-personal-voice-name")
    renamed = VoiceRegistry(args.registry).rename(
        args.rename_personal_voice,
        args.new_personal_voice_name,
    )
    return {
        "success": True,
        "voice": renamed.alias,
        "renamed_from": args.rename_personal_voice,
        "scope": "local_alias",
    }


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
        "installed" if websocket_installed else "missing: use the Skill launcher with --install-deps",
    )
    add(
        "requests",
        requests_installed,
        "installed" if requests_installed else "missing: use the Skill launcher with --install-deps",
    )
    sounddevice_installed, playback_detail = PlaybackSink.availability()
    add(
        "sounddevice",
        sounddevice_installed,
        playback_detail,
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
    operation_started = time.monotonic()

    def progress(name: str, details: Dict[str, Any]) -> None:
        if not args.progress and not args.jsonl:
            return
        payload = dict(details)
        if name == "first_audio":
            payload["end_to_end_first_audio_ms"] = int(
                (time.monotonic() - operation_started) * 1000
            )
        record = event_record("speak", args.run_id, name, payload)
        destination = sys.stdout if args.jsonl else sys.stderr
        print(json.dumps(record, ensure_ascii=False), file=destination, flush=True)

    progress("voice_resolution_started", {})
    resolution_started = time.monotonic()
    api = build_api(args)
    voice_label, speaker_id, voice_kind = resolve_voice(args, api)
    voice_resolution_ms = int((time.monotonic() - resolution_started) * 1000)
    progress(
        "voice_resolved",
        {"voice": voice_label, "voice_kind": voice_kind, "duration_ms": voice_resolution_ms},
    )
    output_path = Path(args.output) if args.output else Path(
        f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-{sanitize_filename_part(voice_label)}_tts.wav"
    )
    if output_path.suffix.lower() != ".wav":
        raise ValueError("真流式模式输出必须使用 .wav 文件")

    wave_sink = WaveFileSink(
        output_path,
        overwrite=args.overwrite,
        preserve_on_failure=True,
    )
    sinks = [wave_sink]
    warnings = []
    playback: Optional[BestEffortSink] = None
    if args.play:
        if PlaybackSink.dependency_available():
            playback = BestEffortSink(QueuedSink(PlaybackSink(), max_chunks=64))
            sinks.append(playback)
        else:
            warnings.append("实时播放依赖或输出设备不可用，已改为只生成 WAV")

    stream_started = time.monotonic()
    try:
        result = StreamingTtsClient(
            api_key=os.getenv("TTS_API_KEY"),
            ws_url=args.ws_url,
            timeout=args.timeout,
        ).stream(args.text, speaker_id, TeeSink(sinks), on_event=progress)
    except BaseException as exc:
        if wave_sink.failure_path is not None and not getattr(exc, "partial_output", None):
            exc.partial_output = str(wave_sink.failure_path.resolve())
        raise
    total_duration_ms = int((time.monotonic() - operation_started) * 1000)
    played = bool(playback and playback.succeeded)
    if playback and playback.error is not None:
        warnings.append(f"实时播放失败，WAV 已保留：{playback.error}")
    end_to_end_first_audio_ms = None
    if result.first_audio_ms is not None:
        end_to_end_first_audio_ms = int((stream_started - operation_started) * 1000) + result.first_audio_ms
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
        "end_to_end_first_audio_ms": end_to_end_first_audio_ms,
        "voice_resolution_ms": voice_resolution_ms,
        "total_duration_ms": total_duration_ms,
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
    parser.add_argument("--list-personal-voices", action="store_true")
    parser.add_argument("--remove-personal-voice", metavar="ALIAS")
    parser.add_argument("--confirm-remove", action="store_true")
    parser.add_argument("--rename-personal-voice", metavar="ALIAS")
    parser.add_argument("--new-personal-voice-name", metavar="ALIAS")
    parser.add_argument("--confirm-rename", action="store_true")
    parser.add_argument("--text")
    parser.add_argument("--voice", help="实时公共音色名称或已保存的个人音色别名")
    parser.add_argument("--public-voice", help="已确认的实时公共音色名称")
    parser.add_argument("--personal-voice", help="已保存的个人音色别名")
    parser.add_argument("--speaker-id", help=argparse.SUPPRESS)
    parser.add_argument("--output")
    parser.add_argument("--play", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--progress", action="store_true", help="将流式进度事件输出到 stderr")
    parser.add_argument("--jsonl", action="store_true", help="将进度与最终结果作为 JSON Lines 输出到 stdout")
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
    parser.add_argument("--replace-personal-voice", action="store_true")
    parser.add_argument("--clone-body")
    parser.add_argument("--clone-description")
    parser.add_argument("--clone-lang-code")
    parser.add_argument("--clone-gender")
    parser.add_argument("--clone-is-public", action="store_true", default=None)
    parser.add_argument("--clone-clip-short", action="store_true", default=None)
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    return parser


def select_operation(args: argparse.Namespace) -> str:
    selected = []
    if args.doctor:
        selected.append("doctor")
    if args.list_voices or args.search_voices or args.voice_query:
        selected.append("public_voices")
    if args.list_personal_voices:
        selected.append("personal_voices")
    if args.remove_personal_voice:
        selected.append("remove_personal_voice")
    if args.rename_personal_voice:
        selected.append("rename_personal_voice")
    if args.design_description is not None or args.design_text is not None:
        selected.append("design")
    if args.clone_audio or args.clone_url:
        selected.append("clone")
    if args.text is not None:
        selected.append("speak")
    if len(selected) > 1:
        raise ValueError("不能同时执行多个操作，请只选择 doctor、查询、设计、克隆或朗读中的一个")
    operation = selected[0] if selected else "speak"

    clone_modifiers = (
        args.clone_name,
        args.confirm_clone,
        args.replace_personal_voice,
        args.clone_body,
        args.clone_description,
        args.clone_lang_code,
        args.clone_gender,
        args.clone_is_public,
        args.clone_clip_short,
    )
    if operation != "clone" and any(value is not None and value is not False for value in clone_modifiers):
        raise ValueError("克隆参数只能与 --clone-audio 或 --clone-url 一起使用")
    speak_modifiers = (
        args.voice,
        args.public_voice,
        args.personal_voice,
        args.speaker_id,
        args.output,
        args.play,
        args.overwrite,
        args.progress,
    )
    if operation != "speak" and any(value is not None and value is not False for value in speak_modifiers):
        raise ValueError("朗读参数只能与 --text 一起使用")
    if operation != "design" and args.optimize_text:
        raise ValueError("--optimize-text 只能用于音色设计")
    if operation != "remove_personal_voice" and args.confirm_remove:
        raise ValueError("--confirm-remove 只能用于删除个人音色")
    rename_modifiers = (args.new_personal_voice_name, args.confirm_rename)
    if operation != "rename_personal_voice" and any(
        value is not None and value is not False for value in rename_modifiers
    ):
        raise ValueError("重命名参数只能与 --rename-personal-voice 一起使用")
    return operation


def main() -> int:
    configure_stdio()
    args = build_parser().parse_args()
    args.run_id = new_run_id()
    operation = "unknown"
    try:
        operation = select_operation(args)
        if operation == "doctor":
            result = run_doctor(args)
        elif operation == "public_voices":
            result = run_list_voices(args)
        elif operation == "personal_voices":
            result = run_list_personal_voices(args)
        elif operation == "remove_personal_voice":
            result = run_remove_personal_voice(args)
        elif operation == "rename_personal_voice":
            result = run_rename_personal_voice(args)
        elif operation == "design":
            if not args.design_description or not args.design_text:
                raise ValueError("音色设计需要同时提供 --design-description 和 --design-text")
            result = run_design(args)
        elif operation == "clone":
            if bool(args.clone_audio) == bool(args.clone_url):
                raise ValueError("音色克隆必须且只能提供 --clone-audio 或 --clone-url")
            result = run_clone(args)
        else:
            if not args.text:
                raise ValueError("text is required")
            result = run_speak(args)
        output = result_record(operation, args.run_id, result)
        print(json.dumps(output, ensure_ascii=False))
        return 0 if result.get("success") else 1
    except KeyboardInterrupt as exc:
        output = error_record(operation, args.run_id, exc)
        destination = sys.stdout if args.jsonl else sys.stderr
        print(json.dumps(output, ensure_ascii=False), file=destination)
        return 130
    except VoiceSelectionError as exc:
        output = error_record(operation, args.run_id, exc)
        output.update({
            "error_code": "voice_selection_failed",
            "stage": "voice_resolution",
            "retryable": False,
        })
        if exc.candidates:
            output["candidates"] = [voice.to_dict() for voice in exc.candidates]
        destination = sys.stdout if args.jsonl else sys.stderr
        print(json.dumps(output, ensure_ascii=False), file=destination)
        return 2
    except Exception as exc:
        output = error_record(operation, args.run_id, exc)
        destination = sys.stdout if args.jsonl else sys.stderr
        print(json.dumps(output, ensure_ascii=False), file=destination)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
