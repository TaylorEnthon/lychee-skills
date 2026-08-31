# TTS Lychee Runtime Hardening Design

**Date:** 2026-08-29  
**Status:** Approved in conversation  
**Scope:** `tts-lychee` only

## Goal

Make the Skill resilient, low-latency, and portable across Agent runtimes without making normal use more complicated. A user should still be able to ask, “用这个声音朗读这段话并播放,” while the Skill handles voice identity, streaming, recovery, playback, and runtime setup internally.

## User-experience principles

1. **Conversation first.** Users describe the desired voice and speech outcome; they do not need to know PCM, WebSocket events, Python paths, virtual environments, or internal speaker IDs.
2. **Safe defaults, not confirmation walls.** Additional confirmation remains limited to paid or destructive actions: cloning a voice, replacing an existing personal alias, deleting an alias, renaming an alias, and overwriting an output file. Searching, selecting, synthesizing, saving, and best-effort playback do not gain new prompts.
3. **Compatibility first.** Existing installation commands, `--voice`, final JSON fields, environment variables, and Claude helper commands continue to work.
4. **Honest streaming.** PCM is consumed as it arrives. The Skill distinguishes generation progress, playback progress, recoverable partial output, and final completion.
5. **Agent-neutral core.** Runtime-specific behavior stays in launch and installation adapters. Voice and streaming behavior stays identical across Agents.
6. **Permanent preview URLs stay permanent.** A voice-design preview URL is stored exactly as returned. It is not stripped, shortened, or treated as an expiring signed URL.

## Architecture

### Runtime contract module

Add a focused runtime-contract module that creates versioned result, progress, and error records. The CLI remains the compatibility adapter, while callers receive stable machine-readable fields:

- `schema_version`
- `type`: `event`, `result`, or `error`
- `operation`
- `run_id`
- `error_code`, `stage`, and `retryable` on failures

Existing fields such as `success`, `error`, `output`, `first_audio_ms`, and `played` remain present. Human-readable Chinese messages remain, but Agents no longer need to parse them to decide recovery behavior.

`--progress` continues to write JSON events to stderr and one final JSON object to stdout. An optional `--jsonl` mode writes events and the final record to stdout for runtimes that consume a single structured stream. Neither mode is required for ordinary conversational use.

### Voice identity module

Represent a resolved voice as a value containing display name, TTS speaker ID, and kind (`public` or `personal`). Add explicit `--public-voice` and `--personal-voice` inputs for Agent-generated commands while preserving `--voice`.

- An explicit public voice goes directly to WebSocket TTS because the public name is already the speaker ID.
- An explicit personal voice resolves only from the local registry.
- Legacy `--voice` preserves public-name-first behavior when the catalog is available.
- A catalog transport failure must not silently switch a colliding public name to a personal alias. The error instructs the Agent to retry or use the explicit personal input.
- Internal `--speaker-id` remains available for compatibility but stays hidden from normal users and replies.

This removes an HTTP catalog round trip from the confirmed public-voice speech path and makes voice identity independent of temporary network state.

### Streaming lifecycle module

Keep the current segmented PCM stream and add an explicit lifecycle around it:

1. Open authoritative WAV output and optional playback.
2. For each text segment, connect and advance through connection, session, text submission, audio, and close states.
3. Treat only recognized state changes or PCM bytes as meaningful progress.
4. Abort when no meaningful progress occurs for the configured timeout, even if text frames or unknown binary frames keep arriving.
5. Retry a segment once only when that attempt wrote zero PCM bytes. Never retry after audio was written because that could duplicate speech.
6. On normal success, atomically commit the final WAV.
7. On failure after any valid PCM was written, finalize and preserve a uniquely named `*.partial-<timestamp>.wav`; include its path in the structured error.
8. On failure before PCM, remove the working file.
9. On `Ctrl+C` or Agent cancellation, close WebSocket, playback, and WAV, then return exit code 130 with a `cancelled` error record.

The existing `--timeout` remains the simple user-facing control. Internally it applies separately to socket inactivity and meaningful-protocol inactivity, so the interface does not grow extra tuning flags.

### Playback adapter

Wrap the existing playback adapter in a worker backed by a bounded queue of 64 chunks.

- The WebSocket receive path writes WAV synchronously, then enqueues playback data.
- The playback worker consumes queued PCM in order.
- A temporary speed difference is absorbed by the queue; a persistently slow device eventually applies bounded backpressure rather than unbounded memory growth.
- Device open, write, drain, or close failures remain best-effort warnings and do not invalidate WAV generation.
- Successful completion waits for queued playback to drain before reporting `played: true`.
- Cancellation discards queued playback and closes promptly.

### Isolated Python runtime

Keep automatic Python 3.8+ discovery, but install dependencies into a Skill-owned virtual environment under:

```text
~/.lychee/tts-lychee/runtime/venv
```

`TTS_RUNTIME_HOME` can override that location for CI or managed installations.

- `--install-deps` creates or reuses the environment and installs core dependencies.
- `--install-playback` creates or reuses it and installs core plus playback dependencies.
- Normal launches prefer the environment when present and otherwise use the discovered system Python, preserving zero-setup doctor behavior.
- Normal speech commands never install packages implicitly. If dependencies are missing, the Agent can run the documented installer once and retry.
- Requirements retain compatible version ranges; CI verifies the supported Python floor and current Python rather than relying on one machine's exact lock.

### Public voice catalog

Use the provider's supported page size of 1000 to reduce catalog round trips. Preserve existing full output by default and add optional response shaping:

- `--compact`: omit preview URLs while retaining name, description, and language.
- `--offset N` and `--limit N`: return a deterministic catalog slice with `catalog_total`, `returned`, and `has_more`.

The Skill uses compact chunks for broad natural-language discovery, reads every relevant description across chunks, then requests full details only for the final candidates. Final semantic selection remains the Agent's responsibility; the implementation does not regress to name-only matching or embed a second language model.

### Remote clone-audio validation

Continue storing the complete design preview URL in the personal voice registry. Harden only the download operation:

- Permit HTTP and HTTPS.
- Reject localhost, literal private addresses, and hostnames resolving to any non-global address before download.
- Repeat validation after redirects.
- Retain the 50 MB limit.
- Accept WAV, MP3, and M4A/MP4 audio based on file signatures; reject HTML, JSON, images, and other non-audio payloads even when the server returns HTTP 200.
- Treat `application/octet-stream` as acceptable only when the downloaded bytes have a supported audio signature.

## Data flows

### Public voice speech

```text
User intent
  -> Agent queries compact live catalog chunks
  -> Agent reads descriptions and presents candidates
  -> User selects a public name
  -> CLI receives --public-voice
  -> WAV opens
  -> WebSocket PCM arrives
  -> WAV write + queued playback
  -> versioned result
```

There is no second catalog lookup after the user selects the public name.

### Designed personal voice

```text
User description
  -> voice design
  -> permanent preview URL shown to user
  -> user confirms clone
  -> URL validated and downloaded
  -> clone request_id stored under personal alias
  -> later CLI receives --personal-voice
  -> local registry resolves speaker ID
  -> same WebSocket streaming path
```

### Failure and recovery

```text
Failure before PCM
  -> close resources
  -> remove working WAV
  -> structured retryable/non-retryable error

Failure after PCM
  -> close resources
  -> finalize unique partial WAV
  -> structured error with partial_output
```

## Compatibility

- Existing no-argument installers still target Claude.
- Existing `claude`, `codex`, `agents`, and `all` targets remain.
- Existing `npx skills add` layout remains valid.
- Existing `LYCHEE_API_KEY`, `TTS_PYTHON`, `TTS_BASE_URL`, `TTS_WS_URL`, and `TTS_VOICE_REGISTRY` behavior remains.
- Existing `--voice`, `--progress`, voice design, clone, list, rename, remove, output, and playback commands remain.
- Existing top-level JSON fields remain; new structured fields are additive.
- The complete preview URL remains persisted and returned for personal voices.

## Testing strategy

Add focused tests before each implementation change:

- cancellation closes every resource and preserves only valid partial PCM;
- meaningless frames hit a progress timeout;
- pre-audio failure retries exactly once, while post-audio failure does not retry;
- later-segment failure returns a playable partial WAV;
- explicit public voice skips catalog HTTP;
- catalog outage never changes a public request into a personal voice;
- explicit personal voice resolves locally;
- queued playback does not block the first receive/write path and drains on success;
- structured result, event, error, cancellation, and JSONL records retain legacy fields;
- Bash and PowerShell launchers prefer an isolated environment without touching the real user home in tests;
- compact catalog slicing is deterministic and preserves description-based search;
- DNS-private targets, redirected private targets, and non-audio HTTP 200 payloads are rejected;
- permanent preview URLs are preserved byte-for-byte in the registry;
- CI covers Python 3.8, 3.11, and 3.13 on Linux, plus Windows installer and launcher checks.

Live paid synthesis is not part of the repeatable suite. Existing successful live provider verification remains separate; this change uses protocol fakes and local files unless a new live check is explicitly requested.

## Acceptance criteria

1. A normal user can use the same conversational requests as before without learning new flags.
2. Existing installation methods and legacy CLI calls continue to pass.
3. Public and personal voices cannot silently exchange identity.
4. Confirmed public voices begin TTS without a catalog preflight request.
5. Cancellation and stream failures leave no corrupt working file; valid received audio is recoverable.
6. Playback failure never causes successful WAV generation to fail.
7. Every final outcome has a stable structured contract while retaining current fields.
8. Dependency installation is isolated from project and Agent Python environments.
9. Public voice discovery remains live and description-aware with lower request and context cost.
10. Complete permanent design preview URLs remain available after cloning.
