from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
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

    def save(self, voice: StoredVoice) -> StoredVoice:
        alias = voice.alias.strip()
        speaker_id = voice.speaker_id.strip()
        if not alias or not speaker_id:
            raise ValueError("个人音色需要 alias 和 speaker_id")
        current = self._read()
        stored = StoredVoice(
            alias=alias,
            speaker_id=speaker_id,
            description=voice.description,
            preview_audio_url=voice.preview_audio_url,
            created_at=voice.created_at or datetime.now(timezone.utc).isoformat(),
        )
        current[alias] = stored
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        payload = {"version": 1, "voices": [asdict(item) for item in current.values()]}
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(str(temporary), str(self.path))
        return stored

    def remove(self, alias: str) -> bool:
        current = self._read()
        if alias not in current:
            return False
        del current[alias]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        payload = {"version": 1, "voices": [asdict(item) for item in current.values()]}
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(str(temporary), str(self.path))
        return True
