# TTS Lychee Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden `tts-lychee` streaming, voice identity, playback, output contracts, runtime isolation, catalog efficiency, and clone-audio validation while preserving simple conversational use and every existing installation path.

**Architecture:** Keep `tts_client.py` as a compatibility adapter and move reusable behavior into focused runtime-contract and voice-resolution modules. Deepen the existing stream and sink modules with lifecycle recovery and queued playback, then keep platform differences isolated in PowerShell/Bash launch adapters.

**Tech Stack:** Python 3.8+, `argparse`, `requests`, `websocket-client`, optional `sounddevice`, `pytest`, PowerShell 5.1/7, Bash, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-29-tts-runtime-hardening-design.md`

## Global Constraints

- Preserve all existing installation methods and default install targets.
- Preserve `--voice` and all existing final JSON fields; new fields are additive.
- Keep true-streaming invariants fixed at PCM16 mono, 16000 Hz, speed 1.0.
- Do not add ordinary-user confirmations for search, selection, synthesis, save, or playback.
- Keep confirmations for clone, replace, rename, remove, and overwrite operations.
- Store voice-design preview URLs exactly as returned; do not strip query parameters.
- Never store, print, log, or commit API keys.
- Avoid live paid synthesis in the repeatable test suite.

---

### Task 1: Versioned Agent Result and Error Contract

**Files:**
- Create: `skills/tts-lychee/scripts/lychee_tts/contracts.py`
- Create: `tests/test_output_contract.py`
- Modify: `skills/tts-lychee/scripts/tts_client.py`
- Modify: `tests/test_cli_management.py`

**Interfaces:**
- Produces: `SCHEMA_VERSION`, `new_run_id()`, `event_record()`, `result_record()`, `error_record()`.
- Preserves: top-level `success`, `error`, and existing operation-specific payload fields.
- Produces: optional CLI flag `--jsonl`; `--progress` behavior remains unchanged.

- [ ] **Step 1: Write failing contract tests**

Add tests equivalent to:

```python
def test_result_contract_adds_metadata_without_removing_legacy_fields():
    result = result_record("personal_voices", "run-1", {"success": True, "total": 0})
    assert result == {
        "schema_version": "1.0",
        "type": "result",
        "operation": "personal_voices",
        "run_id": "run-1",
        "success": True,
        "total": 0,
    }


def test_error_contract_is_machine_readable_and_keeps_error_text():
    result = error_record("speak", "run-2", ValueError("text is required"))
    assert result["success"] is False
    assert result["error"] == "text is required"
    assert result["error_code"] == "invalid_arguments"
    assert result["stage"] == "validation"
    assert result["retryable"] is False


def test_jsonl_writes_progress_and_final_result_to_stdout(monkeypatch, capsys):
    monkeypatch.setattr(
        tts_client,
        "resolve_voice",
        lambda args, api: ("voice", "voice", "public"),
    )
    monkeypatch.setattr(tts_client, "StreamingTtsClient", FakeStreamingClient)
    monkeypatch.setattr(
        sys,
        "argv",
        ["tts_client.py", "--text", "hello", "--public-voice", "voice", "--jsonl"],
    )
    assert tts_client.main() == 0
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert records[0]["type"] == "event"
    assert records[-1]["type"] == "result"
    assert {record["run_id"] for record in records} == {records[0]["run_id"]}
```

`FakeStreamingClient.stream()` must open the supplied sink, write one aligned PCM16
chunk, close it successfully, emit `first_audio`, and return a `StreamResult`; this
keeps the JSONL test in-process and performs no network request.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
python -m pytest -q tests/test_output_contract.py tests/test_cli_management.py
```

Expected: failures because `contracts.py`, metadata, and `--jsonl` do not exist.

- [ ] **Step 3: Implement the runtime contract module**

Create these exact public functions:

```python
SCHEMA_VERSION = "1.0"


def new_run_id() -> str:
    return uuid.uuid4().hex


def event_record(
    operation: str,
    run_id: str,
    event: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "type": "event",
        "operation": operation,
        "run_id": run_id,
        "event": event,
        **(details or {}),
    }


def result_record(operation: str, run_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "type": "result",
        "operation": operation,
        "run_id": run_id,
        **payload,
    }
```

Implement `error_record()` with attribute-based overrides (`error_code`, `stage`, `retryable`, `partial_output`) and built-in fallbacks:

- `ValueError` -> `invalid_arguments`, `validation`, false.
- `FileExistsError` -> `conflict`, `validation`, false.
- `KeyboardInterrupt` -> `cancelled`, `streaming`, false.
- any other exception -> `internal_error`, `runtime`, false unless the exception supplies attributes.

- [ ] **Step 4: Integrate contract records into the CLI adapter**

Generate one `run_id` per invocation. Wrap every successful payload with `result_record()`. Wrap every failure with `error_record()`. Handle `KeyboardInterrupt` separately and return exit code 130.

For speech progress:

```python
record = event_record("speak", args.run_id, name, details)
destination = sys.stdout if args.jsonl else sys.stderr
print(json.dumps(record, ensure_ascii=False), file=destination, flush=True)
```

When `--jsonl` is active, write the final result/error to stdout. Otherwise retain the current stdout-success/stderr-error behavior.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
python -m pytest -q tests/test_output_contract.py tests/test_cli_management.py
```

Expected: all focused tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add skills/tts-lychee/scripts/lychee_tts/contracts.py skills/tts-lychee/scripts/tts_client.py tests/test_output_contract.py tests/test_cli_management.py
git commit -m "feat: add versioned tts agent output contract"
```

---

### Task 2: Explicit Public and Personal Voice Identity

**Files:**
- Create: `skills/tts-lychee/scripts/lychee_tts/voices.py`
- Modify: `skills/tts-lychee/scripts/tts_client.py`
- Modify: `tests/test_registry_contract.py`
- Modify: `tests/test_cli_management.py`

**Interfaces:**
- Produces: immutable `VoiceReference(display_name, speaker_id, kind)`.
- Produces: `VoiceResolver.resolve(public_name=None, personal_alias=None, legacy_name=None, speaker_id=None)`.
- Produces: additive CLI flags `--public-voice` and `--personal-voice`.
- Preserves: legacy `--voice` public-first behavior when catalog resolution completes normally.

- [ ] **Step 1: Write failing voice identity tests**

Add tests equivalent to:

```python
def test_explicit_public_voice_skips_catalog_request():
    api = FailingIfCalledApi()
    reference = VoiceResolver(api, VoiceRegistry(path)).resolve(public_name="靖轩")
    assert reference == VoiceReference("靖轩", "靖轩", "public")


def test_explicit_personal_voice_resolves_only_from_registry(tmp_path):
    registry = VoiceRegistry(tmp_path / "voices.json")
    registry.save(StoredVoice(alias="我的声音", speaker_id="clone-request"))
    reference = VoiceResolver(FailingIfCalledApi(), registry).resolve(personal_alias="我的声音")
    assert reference.speaker_id == "clone-request"
    assert reference.kind == "personal"


def test_catalog_outage_never_switches_legacy_public_name_to_personal_alias(tmp_path):
    registry = VoiceRegistry(tmp_path / "voices.json")
    registry.save(StoredVoice(alias="靖轩", speaker_id="private-id"))
    with pytest.raises(LycheeApiError):
        VoiceResolver(OutageApi(), registry).resolve(legacy_name="靖轩")
```

Also assert that supplying more than one of `--voice`, `--public-voice`, `--personal-voice`, and hidden `--speaker-id` fails as invalid arguments.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
python -m pytest -q tests/test_registry_contract.py tests/test_cli_management.py
```

Expected: failures because the voice module and explicit flags do not exist.

- [ ] **Step 3: Implement `VoiceReference` and `VoiceResolver`**

Use these exact definitions:

```python
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
```

Reject multiple populated selectors. Resolve explicit public names without HTTP. Resolve explicit personal aliases locally or raise `VoiceSelectionError`. For legacy names, preserve exact public lookup first; use a stored alias only when public resolution completed with a genuine “not found” result. Re-raise transport/provider failures.

- [ ] **Step 4: Integrate the resolver into `tts_client.py`**

Keep `resolve_voice()` as a compatibility wrapper returning the existing tuple, but delegate to `VoiceResolver`. Add both new flags to parser validation and include them as speak-only modifiers. Use `kind="personal"` in new results while continuing to accept historical `kind="custom"` only where old tests require it; update tests and documentation to the clearer output value if no external test relies on `custom`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
python -m pytest -q tests/test_registry_contract.py tests/test_cli_management.py tests/test_streaming_contract.py
```

Expected: all focused tests pass, including legacy behavior.

- [ ] **Step 6: Commit Task 2**

```bash
git add skills/tts-lychee/scripts/lychee_tts/voices.py skills/tts-lychee/scripts/tts_client.py tests/test_registry_contract.py tests/test_cli_management.py tests/test_streaming_contract.py
git commit -m "feat: make tts voice identity explicit"
```

---

### Task 3: Recoverable WAV and Queued Playback Adapters

**Files:**
- Modify: `skills/tts-lychee/scripts/lychee_tts/sinks.py`
- Modify: `skills/tts-lychee/scripts/tts_client.py`
- Modify: `tests/test_sinks.py`
- Modify: `tests/test_streaming_contract.py`

**Interfaces:**
- Extends: `WaveFileSink(output_path, sample_rate=16000, overwrite=False, preserve_on_failure=False)` with `failure_path`.
- Produces: `QueuedSink(sink, max_chunks=64)` satisfying the existing `AudioSink` interface.
- Preserves: `BestEffortSink` as the optional-playback failure adapter.

- [ ] **Step 1: Write failing sink tests**

Add tests equivalent to:

```python
def test_wave_sink_can_finalize_valid_received_audio_as_unique_partial(tmp_path):
    sink = WaveFileSink(tmp_path / "speech.wav", preserve_on_failure=True)
    sink.open()
    sink.write(b"\x01\x00\x02\x00")
    sink.close(False)
    assert sink.failure_path is not None
    assert sink.failure_path.name.startswith("speech.partial-")
    with wave.open(str(sink.failure_path), "rb") as reader:
        assert reader.readframes(2) == b"\x01\x00\x02\x00"


def test_wave_sink_still_removes_empty_failure_file(tmp_path):
    sink = WaveFileSink(tmp_path / "speech.wav", preserve_on_failure=True)
    sink.open()
    sink.close(False)
    assert sink.failure_path is None


def test_queued_sink_returns_before_slow_downstream_write_finishes():
    downstream = BlockingSink()
    sink = QueuedSink(downstream, max_chunks=2)
    sink.open()
    sink.write(b"\x01\x00")
    assert downstream.write_started.wait(1)
    assert downstream.write_finished.is_set() is False
    downstream.release.set()
    sink.close(True)
```

Add a cancellation test proving `close(False)` discards queued chunks and returns after the active downstream write is released.

- [ ] **Step 2: Run sink tests and verify RED**

Run:

```bash
python -m pytest -q tests/test_sinks.py tests/test_streaming_contract.py
```

Expected: failures because partial preservation and `QueuedSink` do not exist.

- [ ] **Step 3: Implement recoverable WAV failure output**

Add `preserve_on_failure`, `failure_path`, and a timestamped failure-name helper. On `close(False)`, close the `wave` writer first so its header is valid. Preserve only when `bytes_written > 0`; otherwise remove the working file. Do not overwrite an existing final WAV or prior partial WAV.

- [ ] **Step 4: Implement `QueuedSink`**

Use `queue.Queue(maxsize=max_chunks)` and one daemon worker thread. `write()` must use bounded timeout loops so a worker failure cannot leave the producer blocked forever. On successful close, enqueue a sentinel, join, then close downstream with success. On failed close, discard queued items, enqueue the sentinel, join, and close downstream with failure. Propagate worker errors to the caller so `BestEffortSink` can convert them to warnings.

- [ ] **Step 5: Wire queued playback into speech**

Construct playback as:

```python
playback = BestEffortSink(QueuedSink(PlaybackSink(), max_chunks=64))
```

Keep WAV first in `TeeSink` so every received PCM block is committed to the authoritative output before optional playback is queued.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```bash
python -m pytest -q tests/test_sinks.py tests/test_streaming_contract.py
```

Expected: all focused tests pass without timing sleeps.

- [ ] **Step 7: Commit Task 3**

```bash
git add skills/tts-lychee/scripts/lychee_tts/sinks.py skills/tts-lychee/scripts/tts_client.py tests/test_sinks.py tests/test_streaming_contract.py
git commit -m "feat: queue tts playback and preserve partial audio"
```

---

### Task 4: Streaming Cancellation, Progress Timeout, and Safe Retry

**Files:**
- Modify: `skills/tts-lychee/scripts/lychee_tts/streaming.py`
- Modify: `skills/tts-lychee/scripts/lychee_tts/sinks.py`
- Modify: `skills/tts-lychee/scripts/tts_client.py`
- Modify: `tests/test_streaming_contract.py`
- Modify: `tests/test_output_contract.py`

**Interfaces:**
- Extends: `TtsStreamError(message, error_code, stage, retryable, partial_output=None)`.
- Extends: `PcmStream.received_bytes` to include its pending odd byte.
- Preserves: `StreamingTtsClient.stream(text, speaker_id, sink, on_event=None) -> StreamResult`.
- Emits: additive `segment_retrying` progress event.

- [ ] **Step 1: Write failing lifecycle tests**

Cover these exact cases with deterministic fake clocks/WebSockets:

```python
def test_meaningless_frames_cannot_keep_stream_alive_forever(monkeypatch):
    # Repeated text/unknown frames advance fake time beyond timeout.
    with pytest.raises(TtsStreamError, match="有效进度"):
        client.stream("hello", "voice", sink)


def test_pre_audio_connection_failure_retries_once(monkeypatch):
    # First fake connection fails before PCM; second returns valid PCM.
    result = client.stream("hello", "voice", sink, on_event=events.append)
    assert connection_attempts == 2
    assert any(event[0] == "segment_retrying" for event in events)


def test_post_audio_failure_is_never_retried(monkeypatch):
    with pytest.raises(TtsStreamError):
        client.stream("hello", "voice", sink)
    assert connection_attempts == 1


def test_keyboard_interrupt_closes_sink_as_failure(monkeypatch):
    with pytest.raises(KeyboardInterrupt):
        client.stream("hello", "voice", sink)
    assert sink.closed_with is False
```

Add a CLI-level test where valid PCM is followed by failure and assert the structured error contains an existing playable `partial_output`. Add a cancellation record test expecting exit code 130 and `error_code="cancelled"`.

- [ ] **Step 2: Run lifecycle tests and verify RED**

Run:

```bash
python -m pytest -q tests/test_streaming_contract.py tests/test_output_contract.py
```

Expected: failures for timeout, retry, `BaseException` cleanup, and partial metadata.

- [ ] **Step 3: Add structured stream errors and meaningful progress tracking**

Give `TtsStreamError` default fields `error_code="stream_failed"`, `stage="streaming"`, and `retryable=True`. Set `last_progress_at` when a connection is established and update it only for recognized connection/session state transitions or non-empty PCM payloads. After every received frame, including text frames, compare monotonic time with the configured timeout and raise `progress_timeout` when exceeded.

- [ ] **Step 4: Add one safe pre-audio retry**

Wrap each `_stream_segment()` call in at most two attempts. Compare `PcmStream.received_bytes` before and after the attempt. Retry only when unchanged. Emit:

```python
emit(
    "segment_retrying",
    segment=index,
    attempt=2,
    max_attempts=2,
    reason=str(exc),
)
```

Close every failed WebSocket before retrying.

- [ ] **Step 5: Make cleanup cancellation-safe and expose partial output**

Change the stream-level cleanup guard from `except Exception` to `except BaseException`, close sinks with failure, and re-raise. In `run_speak()`, hold the `WaveFileSink` instance and attach its absolute `failure_path` to a propagated stream error or cancellation before `main()` creates the error record.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```bash
python -m pytest -q tests/test_streaming_contract.py tests/test_output_contract.py tests/test_sinks.py
```

Expected: all focused tests pass.

- [ ] **Step 7: Commit Task 4**

```bash
git add skills/tts-lychee/scripts/lychee_tts/streaming.py skills/tts-lychee/scripts/lychee_tts/sinks.py skills/tts-lychee/scripts/tts_client.py tests/test_streaming_contract.py tests/test_output_contract.py
git commit -m "fix: make tts stream lifecycle recoverable"
```

---

### Task 5: Efficient Catalog Output and Hardened Audio Download

**Files:**
- Modify: `skills/tts-lychee/scripts/lychee_tts/api.py`
- Modify: `skills/tts-lychee/scripts/tts_client.py`
- Modify: `tests/test_api_contract.py`
- Modify: `tests/test_cli_management.py`

**Interfaces:**
- Changes internal default: catalog page size 100 -> 1000.
- Produces additive public-list flags: `--compact`, `--offset`, `--limit`.
- Preserves complete preview URL storage and full-list output when shaping flags are absent.
- Produces private helpers `_validated_remote_url()` and `_supported_audio_file()`.

- [ ] **Step 1: Write failing catalog and download tests**

Add tests equivalent to:

```python
def test_catalog_uses_provider_max_page_size():
    api.list_all_public_voices()
    assert session.calls[0][2]["params"]["page_size"] == 1000


def test_compact_catalog_slice_keeps_description_and_reports_more(monkeypatch):
    result = run_list_voices(args(compact=True, offset=1, limit=2))
    assert result["catalog_total"] == 4
    assert result["returned"] == 2
    assert result["has_more"] is True
    assert "description" in result["voices"][0]
    assert "audio_url" not in result["voices"][0]


def test_design_preview_url_is_preserved_byte_for_byte(tmp_path):
    url = "https://cdn.example/audio.wav?permanent=value"
    # Clone with mocked network/provider, then read the registry.
    assert registry.get("voice").preview_audio_url == url


def test_download_rejects_hostname_resolving_to_private_address(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", private_dns_result)
    with pytest.raises(ValueError, match="私有网络"):
        api.download_audio("https://audio.example/voice.wav", destination)


def test_download_rejects_http_200_html_payload(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", global_dns_result)
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeDownloadResponse(b"<html>"))
    with pytest.raises(LycheeApiError, match="音频格式"):
        api.download_audio("https://audio.example/voice.wav", destination)
```

Also cover valid WAV (`RIFF` plus its four-byte size and `WAVE`), MP3 (`ID3` or frame sync), M4A/MP4 (`ftyp`), redirect-to-private rejection, negative offset, and non-positive limit.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
python -m pytest -q tests/test_api_contract.py tests/test_cli_management.py
```

Expected: failures for page size, shaping flags, DNS resolution, and content signatures.

- [ ] **Step 3: Implement catalog shaping**

Set `DEFAULT_PAGE_SIZE = 1000`. In `run_list_voices()`, build all full or matched records first, then validate/slice:

```python
catalog_total = len(records)
end = None if args.limit is None else args.offset + args.limit
records = records[args.offset:end]
return {
    "success": True,
    "query": query or "",
    "catalog_total": catalog_total,
    "total": len(records),
    "returned": len(records),
    "offset": args.offset,
    "has_more": args.offset + len(records) < catalog_total,
    "voices": records,
}
```

Compact records contain only `name`, `description`, `lang_code`, and existing `match` information. Keep unshaped output compatible.

- [ ] **Step 4: Implement DNS and audio-signature validation**

Resolve every non-literal hostname with `socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)` and reject when the result set is empty or contains any non-global address. Repeat for `response.url` after redirects.

After streaming the file within the existing size limit, validate one of:

```python
is_wav = header.startswith(b"RIFF") and header[8:12] == b"WAVE"
is_mp3 = header.startswith(b"ID3") or (
    len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0
)
is_mp4 = len(header) >= 12 and header[4:8] == b"ftyp"
```

Delete the destination on every validation failure. Do not alter or sanitize the source URL stored by `run_clone()`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
python -m pytest -q tests/test_api_contract.py tests/test_cli_management.py tests/test_registry_contract.py
```

Expected: all focused tests pass.

- [ ] **Step 6: Commit Task 5**

```bash
git add skills/tts-lychee/scripts/lychee_tts/api.py skills/tts-lychee/scripts/tts_client.py tests/test_api_contract.py tests/test_cli_management.py tests/test_registry_contract.py
git commit -m "feat: optimize voice catalog and validate clone audio"
```

---

### Task 6: Skill-Owned Python Environment and Compatibility Matrix

**Files:**
- Modify: `skills/tts-lychee/scripts/run.sh`
- Modify: `skills/tts-lychee/scripts/run.ps1`
- Modify: `skills/tts-lychee/scripts/tts_client.py`
- Modify: `tests/test_runtime_and_installers.py`
- Create: `tests/test_skill_manifest.py`
- Modify: `.github/workflows/installers.yml`

**Interfaces:**
- Produces: `TTS_RUNTIME_HOME`; default runtime root `~/.lychee/tts-lychee/runtime`.
- Preserves: `TTS_PYTHON` as highest-priority explicit runtime override.
- Preserves: `--install-deps`, `--install-playback`, and ordinary launcher arguments.
- Adds: doctor check `python executable` without exposing secrets.

- [ ] **Step 1: Write failing isolated-runtime and manifest tests**

Use a temporary runtime root and create a test virtual environment with system site packages:

```python
subprocess.run(
    [sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)],
    check=True,
)
env["TTS_RUNTIME_HOME"] = str(runtime_root)
result = run_launcher("--doctor", env=env)
doctor = json.loads(result.stdout)
python_check = next(item for item in doctor["checks"] if item["name"] == "python executable")
assert Path(python_check["detail"]).resolve() == venv_python.resolve()
```

Add one Bash-path test and one Windows PowerShell-path test, skipping only when that shell is unavailable. Do not invoke pip or the network.

In `test_skill_manifest.py`, parse the frontmatter delimiters and assert:

- name is `tts-lychee`;
- description is non-empty;
- only `name`, `description`, `license`, `allowed-tools`, and `metadata` are accepted top-level keys;
- `version` and `user-invocable` never reappear;
- both runtime launchers and both requirements files exist.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
python -m pytest -q tests/test_runtime_and_installers.py tests/test_skill_manifest.py
```

Expected: failures because launchers do not select the isolated environment and the doctor omits its executable.

- [ ] **Step 3: Implement isolated runtime selection in Bash**

Use:

```bash
RUNTIME_HOME="${TTS_RUNTIME_HOME:-$HOME/.lychee/tts-lychee/runtime}"
VENV_DIR="$RUNTIME_HOME/venv"
```

Resolution order for ordinary commands is explicit `TTS_PYTHON`, valid venv Python (`bin/python` or `Scripts/python.exe`), then discovered system Python. For install commands, discover a bootstrap Python, run `-m venv` only when venv Python is absent, then run venv Python with pip and the existing requirements file.

- [ ] **Step 4: Implement matching PowerShell behavior**

Use `$env:TTS_RUNTIME_HOME` or `Join-Path $HOME ".lychee\tts-lychee\runtime"`. Check both `Scripts\python.exe` and `bin\python`. Preserve `TTS_PYTHON` precedence and use arrays for every argument to keep paths with spaces safe.

- [ ] **Step 5: Expose the selected executable in doctor**

Add a required check:

```python
add("python executable", bool(sys.executable), str(Path(sys.executable).resolve()))
```

Do not include environment variables or command lines in this detail.

- [ ] **Step 6: Expand CI compatibility coverage**

Change Linux tests to a matrix containing `3.8`, `3.11`, and `3.13`. Keep Windows on 3.11 for PowerShell 5.1/7 installation checks. Run `tests/test_skill_manifest.py` in the normal suite and retain Bash syntax checks.

- [ ] **Step 7: Run focused tests and verify GREEN**

Run:

```bash
python -m pytest -q tests/test_runtime_and_installers.py tests/test_skill_manifest.py
bash -n install.sh skills/tts-lychee/doctor.sh skills/tts-lychee/scripts/run.sh
```

Expected: all tests and shell syntax checks pass without writing to the real home directory.

- [ ] **Step 8: Commit Task 6**

```bash
git add skills/tts-lychee/scripts/run.sh skills/tts-lychee/scripts/run.ps1 skills/tts-lychee/scripts/tts_client.py tests/test_runtime_and_installers.py tests/test_skill_manifest.py .github/workflows/installers.yml
git commit -m "feat: isolate tts skill python runtime"
```

---

### Task 7: Skill Guidance, Installer Messages, and Final Verification

**Files:**
- Modify: `skills/tts-lychee/SKILL.md`
- Modify: `README.md`
- Modify: `commands/tts-lychee-list-voices.md`
- Modify: `commands/tts-lychee-search-voices.md`
- Modify: `install.sh`
- Modify: `install.ps1`
- Modify: `skills/tts-lychee/doctor.sh`
- Modify: `skills/tts-lychee/doctor.ps1`

**Interfaces:**
- Documents: simple conversational behavior first.
- Uses internally: explicit voice selectors, compact catalog chunks, isolated dependency install.
- Preserves: every old installer invocation and Claude helper command name.

- [ ] **Step 1: Add documentation assertions before editing guidance**

Extend `tests/test_skill_manifest.py` to assert the Skill guidance contains:

- `--public-voice` and `--personal-voice`;
- compact chunk discovery with `--compact`, `--offset`, and `--limit`;
- partial WAV recovery;
- cancellation and retry behavior;
- `--jsonl` as optional, not required;
- permanent preview URL persistence;
- no instruction asking ordinary users to choose codec, sample rate, speed, Python executable, or virtual environment.

- [ ] **Step 2: Run the manifest test and verify RED**

Run:

```bash
python -m pytest -q tests/test_skill_manifest.py
```

Expected: failures because the new behavior is not documented yet.

- [ ] **Step 3: Update Skill guidance around user intent**

Lead with conversational examples. In operational instructions, have the Agent:

1. use compact catalog chunks internally for broad discovery;
2. display only 2–5 useful candidates;
3. use `--public-voice` after public selection and `--personal-voice` for saved aliases;
4. install dependencies only when doctor reports them missing;
5. report partial audio only on failure;
6. avoid exposing transport/runtime detail unless the user asks.

Keep immutable PCM constraints in a short implementation-safety section rather than making them user choices.

- [ ] **Step 4: Update README, helper commands, and installer output**

Show old installation commands unchanged. Explain the isolated environment as automatic implementation detail. Update helper commands to request compact chunks where appropriate, while preserving the live description-aware selection requirement. Keep permanent preview URL behavior explicit.

- [ ] **Step 5: Run one complete final verification**

Run exactly once on the final worktree:

```bash
python -m pytest -q
python -m compileall -q skills/tts-lychee/scripts tests
bash -n install.sh skills/tts-lychee/doctor.sh skills/tts-lychee/scripts/run.sh
```

Then run the Skill validator with UTF-8 mode, `git diff --check`, and a repository scan for `sk_`-style secrets. Do not perform a live paid TTS request.

- [ ] **Step 6: Commit Task 7**

```bash
git add skills/tts-lychee/SKILL.md README.md commands/tts-lychee-list-voices.md commands/tts-lychee-search-voices.md install.sh install.ps1 skills/tts-lychee/doctor.sh skills/tts-lychee/doctor.ps1 tests/test_skill_manifest.py
git commit -m "docs: simplify universal tts skill usage"
```

- [ ] **Step 7: Report final state**

Report all local commit hashes, final test counts, validator result, clean/dirty worktree state, and whether anything was pushed. Do not claim live provider verification occurred in this phase.
