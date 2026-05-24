# AGENTS.md

Guidance for AI coding agents working in this repository.

## What This Project Is

**ONVIFy** is an enterprise ONVIF/RTSP virtual camera server with pluggable AI object detection. It takes real camera streams (RTSP or MJPEG), runs optional AI inference (motion-gated, two-stage pipeline), and re-exposes them as ONVIF-compliant virtual cameras that NVRs can discover and stream from.

- Backend: Python 3.11+ / FastAPI / Uvicorn
- Frontend: React + TypeScript + Tailwind CSS + shadcn/ui (planned)
- Database: SQLite via aiosqlite
- Streaming: MediaMTX (managed subprocess) for RTSP, native MJPEG handler
- Inference: Pluggable backends (local YOLO, OpenAI-compatible API, dedicated vision API)
- License: Elastic License v2 (ELv2)

## Canonical Sources

Use these in order:

1. `AGENTS.md` — contributor rules, architecture, and code conventions
2. GitHub issues — live roadmap and unfinished work
3. `docs/` — operational and design detail

## Orientation Map

| Path | Purpose |
|------|---------|
| `src/onvify/config.py` | Pydantic Settings configuration |
| `src/onvify/models/` | Domain models (Camera, Detection, ONVIF) |
| `src/onvify/services/` | Business logic (camera lifecycle, streaming, ONVIF, MJPEG) |
| `src/onvify/inference/` | AI pipeline (protocol, backends, motion gate) |
| `src/onvify/api/` | FastAPI routes and WebSocket |
| `src/onvify/infrastructure/` | Logging, database, platform abstraction |
| `src/onvify/onvif_xml/` | ONVIF SOAP response templates |
| `src/onvify/cli.py` | CLI entry point |
| `tests/` | Test suite |
| `tests/fixtures/` | MP4 samples for inference tests |
| `packaging/` | Platform-specific installers (Windows/Linux/macOS) |
| `frontend/` | React SPA (planned) |

## Build and Run

```bash
# Install
pip install -e ".[dev]"

# Run
onvify --debug

# Test
pytest
ruff check .
mypy .
```

## Code Conventions

### General

- **Async-first**: never block with sync calls in async code paths. Use `asyncio.to_thread()` for CPU-bound work.
- **Type hints everywhere**: `mypy --strict` must pass. No `Any` without justification.
- **Pydantic models** for all external data boundaries (API requests/responses, config, persistence).
- **structlog** for logging. Never use `print()`. Bind context (camera_id, stream_id) to loggers.
- **Tests required** for new functionality. Use pytest fixtures, not test-specific setup code.

### Architecture Constraints

- **Inference backends** must implement the `InferenceBackend` Protocol in `inference/protocol.py`.
- **Motion gate always runs locally**. Only Stage 2 inference routes to the configured backend.
- **ONVIF XML templates** are protocol-correct extractions from the upstream project (MIT licensed). Changes require ONVIF spec reference.
- **Platform-specific code** is isolated behind `infrastructure/platform.py`. The rest of the codebase must remain platform-agnostic.
- **Camera model** supports both RTSP and MJPEG stream types. The inference pipeline is stream-type agnostic (receives `np.ndarray` frames).

### Dependencies

- Declare all dependencies in `pyproject.toml`. Never auto-install at runtime.
- Optional dependencies (inference, coreml) are in `[project.optional-dependencies]`.
- Pin minimum versions, not exact versions.

### Formatting and Linting

- **ruff** for linting and formatting (config in `pyproject.toml`)
- Line length: 120 characters
- Import sorting: isort via ruff

### Documentation

- Update docs when behavior, paths, or architecture changes.
- Docs and runtime disagreement: fix docs or open an issue immediately.
- Code comments only for non-obvious "why" — never for "what".

## Testing

### Unit Tests

- Located in `tests/unit/`
- No external dependencies (mock external services)
- Inference tests use MP4 fixtures from `tests/fixtures/`
- Assert deterministic results for idempotency

### Integration Tests

- Located in `tests/integration/`
- Marked with `@pytest.mark.integration`
- Require MediaMTX and/or real cameras
- Run on self-hosted CI runners with platform-specific hardware

### Test Commands

```bash
# Unit tests only
pytest -m "not integration"

# Specific test
pytest tests/unit/test_config.py -v

# With coverage
pytest --cov=onvify --cov-report=term-missing
```

## Deployment Targets

| Platform | Packaging | Service |
|----------|-----------|---------|
| Windows Server | WiX v6/v7 MSI (native service) | Windows Service via WiX ServiceInstall |
| Ubuntu 22.04+ | pip in venv / .deb / Docker | systemd |
| macOS (Apple Silicon) | pip in venv / .pkg | launchd |

## GitHub Workflow

- Use `gh` CLI for GitHub operations
- Do not push directly to `main`
- Open a pull request for all non-trivial work
- Keep PRs to ~500 LOC of diff
- Label issues by domain (see `CONTRIBUTING.md`)

### PR Review Sequence

PRs go through a multi-stage review pipeline before merge:

1. Open PR with structured summary table + test plan checkboxes
2. Wait for CI to pass
3. Wait for **Greptile** automated review (~5 min)
4. Fix all feedback or add inline code documentation to clarify/justify unfixed items
5. Push fixes to the same branch — never open a new PR for feedback
6. Post a summary comment listing fixes and justifications. If score < 4/5, tag `@greptileai review`
7. Repeat 3-6 until Greptile score >= 4/5 with no P0/P1 issues
8. Request **Copilot** review: `gh pr edit --add-reviewer @copilot`
9. Address Copilot feedback (one round only) and flag for human review
