from __future__ import annotations

import wave
from pathlib import Path

import pytest

from lychee_tts.sinks import PcmStream, WaveFileSink


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
