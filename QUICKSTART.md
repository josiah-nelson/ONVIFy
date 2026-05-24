# Quickstart

Get ONVIFy running locally in development mode.

---

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.11+ | `python3 --version` |
| pip | Latest | `pip --version` |
| Node.js | 20+ | `node --version` (for frontend, optional) |
| MediaMTX | 1.18+ | Auto-downloaded by default; optional if `MEDIAMTX_BIN` is set |

---

## 1. Clone and Install

```bash
git clone https://github.com/josiah-nelson/ONVIFy.git
cd ONVIFy

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# Install with development dependencies
pip install -e ".[dev]"

# Install AI inference dependencies (optional)
pip install -e ".[inference]"

# Install CoreML support (macOS Apple Silicon only)
pip install -e ".[coreml]"
```

---

## 2. Configure (Optional)

Copy the example environment file and edit as needed:

```bash
cp .env.example .env
```

All settings have sensible defaults. The server starts with zero configuration.

By default ONVIFy downloads the configured MediaMTX release into `data/bin/mediamtx/`
on first run, verifies the archive against `checksums.sha256`, and checks
`mediamtx --version` before starting it. Set `MEDIAMTX_AUTO_DOWNLOAD=false` to
disable this, or `MEDIAMTX_BIN=/path/to/mediamtx` to use a preinstalled binary.

---

## 3. Run the Server

```bash
onvify --debug
```

The API server starts on **http://localhost:5552**. You should see:

```
ONVIFy starting, version=0.1.0
```

Open **http://localhost:5552/docs** for the interactive API documentation.

---

## 4. Add a Camera

```bash
curl -X POST http://localhost:5552/api/cameras/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Front Door", "source_url": "rtsp://192.168.1.100:554/stream1"}'
```

For MJPEG cameras:
```bash
curl -X POST http://localhost:5552/api/cameras/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Lobby", "source_url": "http://192.168.1.101/mjpeg", "stream_type": "mjpeg"}'
```

---

## 5. Run Tests

```bash
# All unit tests
pytest

# With coverage
pytest --cov=onvify

# Lint and type check
ruff check .
mypy .
```

---

## Project Layout

```
src/onvify/              # Core application
  config.py              # Pydantic Settings (env vars + .env)
  cli.py                 # CLI entry point
  models/                # Domain models (Camera, Detection, ONVIF)
  services/              # Business logic (camera lifecycle, streaming, ONVIF, MJPEG)
  inference/             # AI pipeline (protocol, backends, motion gate)
  api/                   # FastAPI routes and WebSocket
  infrastructure/        # Logging, database, platform abstraction
  onvif_xml/             # ONVIF SOAP response templates

tests/                   # Test suite
  unit/                  # Unit tests (no external deps)
  integration/           # Integration tests (require MediaMTX/cameras)
  fixtures/              # MP4 samples for inference tests

packaging/               # Platform-specific installers
  windows/               # WiX MSI project
  linux/                 # systemd unit file
  macos/                 # launchd plist
```

---

## Key Reference

| File | Purpose |
|------|---------|
| `AGENTS.md` | Contributor guidance and architecture |
| `CONTRIBUTING.md` | Development workflow and PR standards |
| `pyproject.toml` | Dependencies, tool config, build system |
| `.env.example` | All configurable environment variables |
