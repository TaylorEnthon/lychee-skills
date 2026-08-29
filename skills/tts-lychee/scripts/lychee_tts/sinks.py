from __future__ import annotations

from pathlib import Path
import os
import wave
from typing import Any, Iterable, List, Optional, Protocol, Tuple


class AudioSink(Protocol):
    def open(self) -> None:
        ...

    def write(self, chunk: bytes) -> None:
        ...

    def close(self, success: bool) -> None:
        ...


class WaveFileSink:
    def __init__(self, output_path: Path, sample_rate: int = 16000, overwrite: bool = False):
        self.output_path = Path(output_path)
        self.sample_rate = sample_rate
        self.overwrite = overwrite
        suffix = self.output_path.suffix or ".wav"
        self.partial_path = self.output_path.with_name(f"{self.output_path.stem}.part{suffix}")
        self._writer: Optional[wave.Wave_write] = None
        self.bytes_written = 0

    def open(self) -> None:
        if self.output_path.exists() and not self.overwrite:
            raise FileExistsError(f"输出文件已存在：{self.output_path}")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        if self.partial_path.exists():
            self.partial_path.unlink()
        self._writer = wave.open(str(self.partial_path), "wb")
        self._writer.setnchannels(1)
        self._writer.setsampwidth(2)
        self._writer.setframerate(self.sample_rate)
        self.bytes_written = 0

    def write(self, chunk: bytes) -> None:
        if self._writer is None:
            raise RuntimeError("WAV Sink 尚未打开")
        data = bytes(chunk)
        if len(data) % 2:
            raise ValueError("PCM chunk 必须按 16-bit sample 对齐")
        if data:
            self._writer.writeframesraw(data)
            self.bytes_written += len(data)

    def close(self, success: bool) -> None:
        writer, self._writer = self._writer, None
        if writer is not None:
            writer.close()
        if success:
            os.replace(str(self.partial_path), str(self.output_path))
        elif self.partial_path.exists():
            self.partial_path.unlink()


class PlaybackSink:
    def __init__(self, sample_rate: int = 16000, device: Optional[Any] = None):
        self.sample_rate = sample_rate
        self.device = device
        self._stream: Any = None

    @staticmethod
    def availability() -> Tuple[bool, str]:
        try:
            import sounddevice as sd
        except Exception as exc:
            return False, f"sounddevice/PortAudio 不可用：{exc}"
        try:
            devices = sd.query_devices()
            has_output = any(
                int(device.get("max_output_channels", 0)) > 0
                for device in devices
                if hasattr(device, "get")
            )
        except Exception as exc:
            return False, f"无法查询音频输出设备：{exc}"
        if not has_output:
            return False, "没有可用的音频输出设备"
        return True, "sounddevice 与音频输出设备可用"

    @staticmethod
    def dependency_available() -> bool:
        return PlaybackSink.availability()[0]

    def open(self) -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:  # pragma: no cover - environment-specific
            raise RuntimeError("缺少 sounddevice，无法实时播放；可先保存 WAV") from exc
        self._stream = sd.RawOutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            device=self.device,
        )
        self._stream.start()

    def write(self, chunk: bytes) -> None:
        if self._stream is None:
            raise RuntimeError("播放 Sink 尚未打开")
        if chunk:
            self._stream.write(bytes(chunk))

    def close(self, success: bool) -> None:
        stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            stream.stop()
        finally:
            stream.close()


class TeeSink:
    def __init__(self, sinks: Iterable[AudioSink]):
        self.sinks: List[AudioSink] = list(sinks)
        self._opened: List[AudioSink] = []

    def open(self) -> None:
        try:
            for sink in self.sinks:
                sink.open()
                self._opened.append(sink)
        except Exception:
            for sink in reversed(self._opened):
                try:
                    sink.close(False)
                except Exception:
                    pass
            self._opened = []
            raise

    def write(self, chunk: bytes) -> None:
        for sink in self._opened:
            sink.write(chunk)

    def close(self, success: bool) -> None:
        errors = []
        for sink in reversed(self._opened):
            try:
                sink.close(success)
            except Exception as exc:
                errors.append(exc)
        self._opened = []
        if errors:
            raise errors[0]


class BestEffortSink:
    """Keep an optional output adapter from failing the authoritative stream."""

    def __init__(self, sink: AudioSink):
        self.sink = sink
        self.error: Optional[Exception] = None
        self._opened = False
        self._completed = False

    @property
    def succeeded(self) -> bool:
        return self._completed and self.error is None

    def open(self) -> None:
        try:
            self.sink.open()
            self._opened = True
        except Exception as exc:
            self.error = exc

    def write(self, chunk: bytes) -> None:
        if not self._opened or self.error is not None:
            return
        try:
            self.sink.write(chunk)
        except Exception as exc:
            self.error = exc
            try:
                self.sink.close(False)
            except Exception:
                pass
            self._opened = False

    def close(self, success: bool) -> None:
        if not self._opened:
            return
        try:
            self.sink.close(success)
            self._completed = bool(success)
        except Exception as exc:
            self.error = exc
        finally:
            self._opened = False


class PcmStream:
    """Align arbitrary transport chunks to PCM16 samples without buffering the response."""

    def __init__(self, sink: AudioSink):
        self.sink = sink
        self._carry = b""
        self.bytes_written = 0

    def write(self, chunk: bytes) -> None:
        data = self._carry + bytes(chunk)
        usable = len(data) - (len(data) % 2)
        self._carry = data[usable:]
        if usable:
            aligned = data[:usable]
            self.sink.write(aligned)
            self.bytes_written += usable

    def finish(self) -> None:
        if self._carry:
            raise ValueError("TTS PCM 数据以不完整的 16-bit sample 结束")
