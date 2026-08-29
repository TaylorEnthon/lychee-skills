from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import ipaddress
import mimetypes
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    import requests
except ImportError:  # pragma: no cover - exercised by doctor instead
    requests = None


DEFAULT_BASE_URL = "https://voice.lycheeai.com.cn"
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000
MAX_AUDIO_BYTES = 50 * 1024 * 1024


class LycheeApiError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None, code: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class VoiceSelectionError(LycheeApiError):
    def __init__(self, message: str, candidates: Optional[List["PublicVoice"]] = None):
        super().__init__(message)
        self.candidates = candidates or []


@dataclass(frozen=True)
class PublicVoice:
    name: str
    description: str = ""
    lang_code: str = ""
    audio_url: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "description": self.description,
            "lang_code": self.lang_code,
            "audio_url": self.audio_url,
        }


@dataclass(frozen=True)
class PublicVoiceMatch:
    voice: PublicVoice
    score: int
    matched_fields: Tuple[str, ...]
    matched_terms: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = self.voice.to_dict()
        result["match"] = {
            "score": self.score,
            "fields": list(self.matched_fields),
            "terms": list(self.matched_terms),
        }
        return result


@dataclass(frozen=True)
class VoicePage:
    voices: List[PublicVoice]
    total: int
    page_no: int
    page_size: int


@dataclass(frozen=True)
class DesignResult:
    audio_url: str
    request_id: str = ""
    task_id: str = ""


@dataclass(frozen=True)
class CloneResult:
    speaker_id: str
    request_id: str
    name: str = ""


class LycheeApiClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        session: Any = None,
        timeout: int = 30,
    ):
        self.base_url = (base_url or os.getenv("TTS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or os.getenv("TTS_API_KEY")
        self.timeout = timeout
        self.session = session

    def _session(self) -> Any:
        if self.session is not None:
            return self.session
        if requests is None:
            raise LycheeApiError(
                "缺少 requests 依赖，请使用 Skill 启动脚本执行 --install-deps"
            )
        self.session = requests.Session()
        return self.session

    def _headers(self, content_type: Optional[str] = None) -> Dict[str, str]:
        if not self.api_key:
            raise LycheeApiError("TTS_API_KEY 未配置")
        headers = {"api_key": self.api_key, "Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _request_json(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        kwargs.setdefault("headers", self._headers())
        kwargs.setdefault("timeout", self.timeout)
        url = self.base_url + path
        try:
            response = self._session().request(method, url, **kwargs)
        except Exception as exc:
            if requests is not None and isinstance(exc, requests.RequestException):
                raise LycheeApiError("连接语音服务失败") from exc
            raise

        try:
            payload = response.json()
        except Exception as exc:
            detail = getattr(response, "text", "") or ""
            raise LycheeApiError(
                "语音服务返回了非 JSON 响应" + (f": {detail[:160]}" if detail else ""),
                getattr(response, "status_code", None),
            ) from exc

        status_code = getattr(response, "status_code", None)
        if not isinstance(payload, dict):
            raise LycheeApiError("语音服务返回格式无效", status_code)
        if not getattr(response, "ok", 200 <= (status_code or 500) < 300):
            raise LycheeApiError(
                str(payload.get("info") or payload.get("message") or f"语音服务请求失败 ({status_code})"),
                status_code,
                payload.get("code"),
            )
        code = payload.get("code")
        if code is not None and code != 200:
            raise LycheeApiError(
                str(payload.get("info") or payload.get("message") or "语音服务请求失败"),
                status_code,
                code,
            )
        return payload

    @staticmethod
    def _voice_list(data: Any) -> List[PublicVoice]:
        if not isinstance(data, list):
            return []
        voices = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            voices.append(
                PublicVoice(
                    name=name,
                    description=str(item.get("description") or ""),
                    lang_code=str(item.get("lang_code") or ""),
                    audio_url=str(item.get("audio_url") or ""),
                )
            )
        return voices

    def list_public_voices(
        self,
        name: Optional[str] = None,
        page_no: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> VoicePage:
        if page_no < 1:
            raise ValueError("page_no 必须从 1 开始")
        if page_size < 1 or page_size > MAX_PAGE_SIZE:
            raise ValueError(f"page_size 必须在 1 到 {MAX_PAGE_SIZE} 之间")
        params: Dict[str, Any] = {"page_no": page_no, "page_size": page_size}
        if name and name.strip():
            params["name"] = name.strip()
        payload = self._request_json("GET", "/openapi/voice-list", params=params)
        data = payload.get("data") or {}
        if isinstance(data, list):
            items = data
            total = len(items)
        else:
            items = data.get("list") if isinstance(data, dict) else []
            total_value = data.get("total") if isinstance(data, dict) else 0
            try:
                total = int(total_value or 0)
            except (TypeError, ValueError):
                total = 0
        return VoicePage(self._voice_list(items), total, page_no, page_size)

    def list_all_public_voices(
        self,
        name: Optional[str] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> List[PublicVoice]:
        voices: List[PublicVoice] = []
        page_no = 1
        total: Optional[int] = None
        while page_no <= 1000:
            page = self.list_public_voices(name=name, page_no=page_no, page_size=page_size)
            voices.extend(page.voices)
            total = page.total if total is None else total
            if not page.voices or (total and len(voices) >= total) or len(page.voices) < page_size:
                break
            page_no += 1
        return voices

    @staticmethod
    def _search_terms(query: str) -> List[str]:
        normalized = re.sub(
            r"[\s,，。！？!?、；;：:（）()【】\[\]《》\"'“”‘’]+",
            " ",
            (query or "").casefold(),
        ).strip()
        if not normalized:
            return []

        terms: List[str] = []
        for part in normalized.split():
            if re.search(r"[\u4e00-\u9fff]", part):
                compact = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", part)
                if compact:
                    terms.append(compact)
                if len(compact) > 2:
                    terms.extend(compact[index : index + 2] for index in range(len(compact) - 1))
            else:
                terms.append(part)

        unique: List[str] = []
        for term in terms:
            if len(term) >= 2 and term not in unique:
                unique.append(term)
        return unique

    def search_public_voice_matches(
        self,
        query: str,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> List[PublicVoiceMatch]:
        """Fetch the live catalog, then return explainable local pre-filter matches."""
        voices = self.list_all_public_voices(page_size=page_size)
        terms = self._search_terms(query)
        if not terms:
            return [PublicVoiceMatch(voice, 0, (), ()) for voice in voices]

        ranked: List[PublicVoiceMatch] = []
        for voice in voices:
            name = voice.name.casefold()
            description = voice.description.casefold()
            language = voice.lang_code.casefold()
            score = 0
            matched_fields = set()
            matched_terms = []
            for term in terms:
                term_score = 0
                if term in name:
                    term_score = 4
                    matched_fields.add("name")
                if term in description:
                    term_score = max(term_score, 2)
                    matched_fields.add("description")
                if term in language:
                    term_score = max(term_score, 2)
                    matched_fields.add("lang_code")
                if term_score:
                    score += term_score
                    matched_terms.append(term)
            if score:
                ranked.append(PublicVoiceMatch(
                    voice=voice,
                    score=score,
                    matched_fields=tuple(sorted(matched_fields)),
                    matched_terms=tuple(matched_terms),
                ))

        ranked.sort(key=lambda item: (-item.score, item.voice.name.casefold()))
        if not ranked:
            return []
        strongest = ranked[0].score
        threshold = 2 if len(terms) <= 2 else max(4, (strongest + 1) // 2)
        return [match for match in ranked if match.score >= threshold]

    def search_public_voices(
        self,
        query: str,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> List[PublicVoice]:
        return [
            match.voice
            for match in self.search_public_voice_matches(query, page_size=page_size)
        ]

    def resolve_public_voice(self, requested: str) -> PublicVoice:
        query = (requested or "").strip()
        if not query:
            raise VoiceSelectionError("必须指定公共音色名称")
        candidates = self.list_all_public_voices(name=query)
        exact = [voice for voice in candidates if voice.name == query]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise VoiceSelectionError(f"公共音色名称重复：{query}", exact)
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise VoiceSelectionError(f"未找到公共音色：{query}")
        raise VoiceSelectionError(f"公共音色匹配到多个候选：{query}", candidates[:20])

    def design_voice(
        self,
        description: str,
        text: str,
        optimize_text: bool = False,
    ) -> DesignResult:
        description = (description or "").strip()
        text = (text or "").strip()
        if not description or not text:
            raise ValueError("音色设计需要 description 和 text")
        payload = self._request_json(
            "POST",
            "/openapi/voice-design",
            headers=self._headers("application/json"),
            json={
                "description": description,
                "text": text,
                "optimize_text": bool(optimize_text),
            },
        )
        data = payload.get("data") or {}
        audio_url = str(data.get("audio_url") or "").strip()
        if not audio_url:
            raise LycheeApiError("音色设计未返回试听音频")
        return DesignResult(
            audio_url=audio_url,
            request_id=str(data.get("request_id") or ""),
            task_id=str(data.get("task_id") or ""),
        )

    def clone_voice(
        self,
        audio_path: Path,
        body: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        lang_code: Optional[str] = None,
        gender: Optional[str] = None,
        is_public: Optional[bool] = None,
        clip_short: Optional[bool] = None,
    ) -> CloneResult:
        audio_path = Path(audio_path)
        if not audio_path.is_file():
            raise ValueError(f"音频文件不存在：{audio_path}")
        data: Dict[str, Any] = {}
        if body:
            data["body"] = body
        optional = {
            "name": name,
            "description": description,
            "lang_code": lang_code,
            "gender": gender,
            "is_public": None if is_public is None else str(is_public).lower(),
            "clip_short": None if clip_short is None else str(clip_short).lower(),
        }
        data.update({key: value for key, value in optional.items() if value is not None})
        mime = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
        with audio_path.open("rb") as audio_file:
            payload = self._request_json(
                "POST",
                "/openapi/tts/clone",
                headers=self._headers(),
                files={"audio": (audio_path.name, audio_file, mime)},
                data=data,
            )
        response_data = payload.get("data") or {}
        request_id = str(response_data.get("request_id") or "").strip()
        speaker_id = str(request_id or response_data.get("speaker_id") or "").strip()
        if not speaker_id:
            raise LycheeApiError("音色克隆未返回 request_id")
        return CloneResult(
            speaker_id=speaker_id,
            request_id=request_id or speaker_id,
            name=str(response_data.get("name") or name or "").strip(),
        )

    def download_audio(self, url: str, destination: Path) -> Path:
        parsed = urlparse(url or "")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("试听音频地址不是有效的 HTTP/HTTPS URL")
        hostname = (parsed.hostname or "").casefold()
        if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
            raise ValueError("试听音频地址不能指向本机或私有网络")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("试听音频地址不能指向本机或私有网络")
        if requests is None:
            raise LycheeApiError("缺少 requests 依赖")
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            response = requests.get(url, stream=True, timeout=self.timeout, headers={"Accept": "audio/*"})
            response.raise_for_status()
            final_url = getattr(response, "url", url)
            final_parsed = urlparse(final_url)
            final_hostname = (final_parsed.hostname or "").casefold()
            try:
                final_address = ipaddress.ip_address(final_hostname)
            except ValueError:
                final_address = None
            if (
                final_parsed.scheme not in {"http", "https"}
                or not final_parsed.netloc
                or final_hostname == "localhost"
                or final_hostname.endswith(".localhost")
                or final_hostname.endswith(".local")
                or (final_address is not None and not final_address.is_global)
            ):
                raise LycheeApiError("试听音频重定向到了本机或私有网络")
            total = 0
            with destination.open("wb") as output:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_AUDIO_BYTES:
                        raise LycheeApiError("音频文件超过 50 MB 限制")
                    output.write(chunk)
        except Exception as exc:
            if destination.exists():
                destination.unlink()
            if isinstance(exc, LycheeApiError):
                raise
            if requests is not None and isinstance(exc, requests.RequestException):
                raise LycheeApiError("下载试听音频失败") from exc
            raise
        return destination
