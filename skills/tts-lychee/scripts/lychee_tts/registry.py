from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
from typing import Dict, List, Optional


@dataclass(frozen=True)
class StoredVoice:
    alias: str
    speaker_id: str
    description: str = ""
    preview_audio_url: str = ""
    created_at: str = ""


class VoiceRegistry:
    def __init__(self, path: Optional[Path] = None):
        default_path = Path.home() / ".lychee" / "tts-lychee" / "voices.json"
        self.path = Path(path or os.getenv("TTS_VOICE_REGISTRY") or default_path)

    def _read(self) -> Dict[str, StoredVoice]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"音色注册表无法读取：{self.path}") from exc
        entries = payload.get("voices", []) if isinstance(payload, dict) else []
        result: Dict[str, StoredVoice] = {}
        if isinstance(entries, list):
            for item in entries:
                if not isinstance(item, dict):
                    continue
                alias = str(item.get("alias") or "").strip()
                speaker_id = str(item.get("speaker_id") or "").strip()
                if alias and speaker_id:
                    result[alias] = StoredVoice(
                        alias=alias,
                        speaker_id=speaker_id,
                        description=str(item.get("description") or ""),
                        preview_audio_url=str(item.get("preview_audio_url") or ""),
                        created_at=str(item.get("created_at") or ""),
                    )
        return result

    def list(self) -> List[StoredVoice]:
        return list(self._read().values())

    def get(self, alias: Optional[str]) -> Optional[StoredVoice]:
        if not alias:
            return None
        return self._read().get(alias.strip())

    @contextmanager
    def _write_lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(self.path.name + ".lock")
        handle = lock_path.open("a+b")
        locked = False
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            locked = True
            yield
        finally:
            try:
                if locked:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def _write(self, voices: Dict[str, StoredVoice]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "voices": [asdict(item) for item in voices.values()]}
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=self.path.name + ".",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
                output.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            os.replace(str(temporary), str(self.path))
        finally:
            if temporary.exists():
                temporary.unlink()

    def save(self, voice: StoredVoice, replace: bool = False) -> StoredVoice:
        alias = voice.alias.strip()
        speaker_id = voice.speaker_id.strip()
        if not alias or not speaker_id:
            raise ValueError("个人音色需要 alias 和 speaker_id")
        with self._write_lock():
            current = self._read()
            existing = current.get(alias)
            if existing and existing.speaker_id != speaker_id and not replace:
                raise FileExistsError(f"个人音色别名已存在：{alias}")
            stored = StoredVoice(
                alias=alias,
                speaker_id=speaker_id,
                description=voice.description,
                preview_audio_url=voice.preview_audio_url,
                created_at=(
                    voice.created_at
                    or (existing.created_at if existing else "")
                    or datetime.now(timezone.utc).isoformat()
                ),
            )
            current[alias] = stored
            self._write(current)
            return stored

    def remove(self, alias: str) -> bool:
        alias = (alias or "").strip()
        if not alias:
            raise ValueError("个人音色别名不能为空")
        with self._write_lock():
            current = self._read()
            if alias not in current:
                return False
            del current[alias]
            self._write(current)
            return True

    def rename(self, alias: str, new_alias: str) -> StoredVoice:
        alias = (alias or "").strip()
        new_alias = (new_alias or "").strip()
        if not alias or not new_alias:
            raise ValueError("旧别名和新别名都不能为空")
        with self._write_lock():
            current = self._read()
            source = current.get(alias)
            if source is None:
                raise ValueError(f"未找到个人音色：{alias}")
            if new_alias != alias and new_alias in current:
                raise FileExistsError(f"个人音色别名已存在：{new_alias}")
            renamed = StoredVoice(
                alias=new_alias,
                speaker_id=source.speaker_id,
                description=source.description,
                preview_audio_url=source.preview_audio_url,
                created_at=source.created_at,
            )
            if new_alias != alias:
                del current[alias]
            current[new_alias] = renamed
            self._write(current)
            return renamed
