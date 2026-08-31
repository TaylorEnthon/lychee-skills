from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .api import LycheeApiClient, VoiceSelectionError
from .registry import VoiceRegistry


@dataclass(frozen=True)
class VoiceReference:
    display_name: str
    speaker_id: str
    kind: str


class VoiceResolver:
    def __init__(self, api: LycheeApiClient, registry: VoiceRegistry):
        self.api = api
        self.registry = registry

    def resolve(
        self,
        public_name: Optional[str] = None,
        personal_alias: Optional[str] = None,
        legacy_name: Optional[str] = None,
        speaker_id: Optional[str] = None,
    ) -> VoiceReference:
        values = [public_name, personal_alias, legacy_name, speaker_id]
        selected = [value.strip() for value in values if value and value.strip()]
        if len(selected) != 1:
            if not selected:
                raise ValueError("请指定 --voice、--public-voice 或 --personal-voice")
            raise ValueError("必须且只能指定一种音色")

        if speaker_id and speaker_id.strip():
            value = speaker_id.strip()
            return VoiceReference(value, value, "personal")

        if public_name and public_name.strip():
            value = public_name.strip()
            return VoiceReference(value, value, "public")

        if personal_alias and personal_alias.strip():
            stored = self.registry.get(personal_alias)
            if stored is None:
                raise VoiceSelectionError(f"未找到个人音色：{personal_alias.strip()}")
            return VoiceReference(stored.alias, stored.speaker_id, "personal")

        requested = (legacy_name or "").strip()
        stored = self.registry.get(requested)
        try:
            public = self.api.resolve_public_voice(requested)
        except VoiceSelectionError as exc:
            if exc.candidates or stored is None:
                raise
            return VoiceReference(stored.alias, stored.speaker_id, "personal")
        return VoiceReference(public.name, public.name, "public")
