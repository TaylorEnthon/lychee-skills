from __future__ import annotations

import threading
import wave
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import lychee_tts.sinks as sinks_module
from lychee_tts.sinks import PcmStream, PlaybackSink, WaveFileSink


def test_wave_sink_writes_pcm_incrementally_and_commits_only_on_success(tmp_path: Path):
    output = tmp_path / "speech.wav"
    sink = WaveFileSink(output)
    sink.open()
    sink.write(b"\x01\x00")
    sink.write(b"\x02\x00")
    sink.close(True)

    assert output.exists()
    assert not (tmp_path / "speech.part.wav").exists()
    with wave.open(str(output), "rb") as reader:
        assert reader.getframerate() == 16000
        assert reader.getnchannels() == 1
        assert reader.getsampwidth() == 2
        assert reader.readframes(2) == b"\x01\x00\x02\x00"


def test_wave_sink_removes_partial_file_on_failure(tmp_path: Path):
    output = tmp_path / "speech.wav"
    sink = WaveFileSink(output)
    sink.open()
    sink.write(b"\x01\x00")
    sink.close(False)

    assert not output.exists()
    assert not (tmp_path / "speech.part.wav").exists()


def test_wave_sink_can_finalize_received_audio_as_a_unique_partial(tmp_path: Path):
    output = tmp_path / "speech.wav"
    sink = WaveFileSink(output, preserve_on_failure=True)
    sink.open()
    sink.write(b"\x01\x00\x02\x00")
    sink.close(False)

    assert not output.exists()
    assert sink.failure_path is not None
    assert sink.failure_path.parent == tmp_path
    assert sink.failure_path.name.startswith("speech.partial-")
    assert sink.failure_path.suffix == ".wav"
    assert not (tmp_path / "speech.part.wav").exists()
    with wave.open(str(sink.failure_path), "rb") as reader:
        assert reader.getframerate() == 16000
        assert reader.getnchannels() == 1
        assert reader.getsampwidth() == 2
        assert reader.readframes(2) == b"\x01\x00\x02\x00"


def test_wave_sink_still_removes_an_empty_failed_output(tmp_path: Path):
    output = tmp_path / "speech.wav"
    sink = WaveFileSink(output, preserve_on_failure=True)
    sink.open()
    sink.close(False)

    assert not output.exists()
    assert sink.failure_path is None
    assert list(tmp_path.iterdir()) == []


def test_pcm_stream_carries_an_odd_byte_between_transport_chunks():
    chunks = []

    class Sink:
        def write(self, chunk):
            chunks.append(bytes(chunk))

    stream = PcmStream(Sink())
    stream.write(b"\x01")
    stream.write(b"\x00\x02")
    stream.write(b"\x00")
    stream.finish()

    assert chunks == [b"\x01\x00", b"\x02\x00"]


def test_pcm_stream_rejects_an_incomplete_final_sample():
    class Sink:
        def write(self, chunk):
            pass

    stream = PcmStream(Sink())
    stream.write(b"\x01")
    with pytest.raises(ValueError, match="不完整"):
        stream.finish()


def test_sounddevice_load_error_is_reported_as_unavailable(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fail_sounddevice(name, *args, **kwargs):
        if name == "sounddevice":
            raise OSError("PortAudio library not found")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_sounddevice)

    assert PlaybackSink.dependency_available() is False


def test_sounddevice_without_an_output_device_is_unavailable(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "sounddevice",
        SimpleNamespace(query_devices=lambda: [{"max_output_channels": 0}]),
    )

    assert PlaybackSink.dependency_available() is False


def test_queued_sink_does_not_block_the_producer_on_a_slow_write():
    assert hasattr(sinks_module, "QueuedSink")

    write_started = threading.Event()
    release_write = threading.Event()
    received = []

    class SlowSink:
        def open(self):
            pass

        def write(self, chunk):
            write_started.set()
            assert release_write.wait(timeout=2)
            received.append(bytes(chunk))

        def close(self, success):
            assert success is True

    sink = sinks_module.QueuedSink(SlowSink(), max_chunks=2)
    sink.open()
    sink.write(b"\x01\x00")
    assert write_started.wait(timeout=1)

    producer_returned = threading.Event()
    producer = threading.Thread(
        target=lambda: (sink.write(b"\x02\x00"), producer_returned.set())
    )
    producer.start()
    assert producer_returned.wait(timeout=0.2)

    release_write.set()
    producer.join(timeout=1)
    sink.close(True)
    assert received == [b"\x01\x00", b"\x02\x00"]


def test_queued_sink_discards_pending_chunks_when_cancelled():
    write_started = threading.Event()
    release_write = threading.Event()
    close_finished = threading.Event()
    received = []
    closed_with = []

    class SlowSink:
        def open(self):
            pass

        def write(self, chunk):
            write_started.set()
            assert release_write.wait(timeout=2)
            received.append(bytes(chunk))

        def close(self, success):
            closed_with.append(success)

    sink = sinks_module.QueuedSink(SlowSink(), max_chunks=2)
    sink.open()
    sink.write(b"\x01\x00")
    assert write_started.wait(timeout=1)
    sink.write(b"\x02\x00")

    closer = threading.Thread(target=lambda: (sink.close(False), close_finished.set()))
    closer.start()
    assert not close_finished.wait(timeout=0.1)
    release_write.set()
    assert close_finished.wait(timeout=1)
    closer.join(timeout=1)

    assert received == [b"\x01\x00"]
    assert closed_with == [False]
