# ONVIFy — Project Overview

## What ONVIFy Is

ONVIFy is an enterprise-grade virtual camera server. It connects to real IP camera streams — RTSP or MJPEG — and re-exposes them as fully ONVIF-compliant virtual cameras. NVRs like UniFi Protect, Blue Iris, and Milestone can discover and stream from ONVIFy cameras just like physical hardware, but with added capabilities: AI object detection, stream normalization, and centralized management through a modern web interface and REST API.

The core value proposition is bridging cameras that don't speak ONVIF (or speak it poorly) into enterprise NVR ecosystems, while layering on intelligent detection that the cameras themselves can't provide.

## Who It's For

ONVIFy targets enterprise and professional deployments — organizations that need reliable, scalable camera infrastructure with proper logging, monitoring, and deployment tooling. It's designed to run as a managed service on Windows Server, Ubuntu, or macOS, with native service integration on each platform.

## Key Features

### Virtual ONVIF Cameras

Each source stream becomes a virtual ONVIF device on the network. ONVIFy handles WS-Discovery so NVRs can auto-discover cameras, and implements the ONVIF Device, Media, and Events services so NVRs can query profiles, request stream URIs, and subscribe to motion events.

### Pluggable AI Detection

Object detection runs through a two-stage pipeline designed to minimize compute waste:

1. **Motion gate** — A lightweight OpenCV pixel-difference check runs on every frame locally. If the scene hasn't changed, the expensive inference step is skipped entirely. This means a static hallway camera costs nearly zero CPU.

2. **Inference backend** — When motion is detected, the frame is forwarded to whichever backend is configured:
   - **Local YOLO** — Runs YOLOv8/11 locally using the best available hardware: Apple Neural Engine via CoreML, Metal Performance Shaders (MPS) on Apple Silicon, or CPU. The model is loaded once and shared across cameras.
   - **OpenAI-compatible API** — Offloads inference to any server exposing the standard `/v1/chat/completions` vision endpoint. Works with vLLM, llama.cpp, Ollama, or any compatible service. This allows running the ONVIF server on lightweight hardware while a GPU server handles detection.
   - **Dedicated vision API** — For high-camera-count deployments, connects to purpose-built inference servers like Triton or TorchServe for batched, optimized detection.

All backends implement the same Protocol interface, so swapping between them is a configuration change, not a code change.

### RTSP and MJPEG Support

ONVIFy accepts both RTSP and MJPEG source streams. RTSP is the standard for modern IP cameras; MJPEG support covers older or lower-cost cameras that only expose HTTP motion JPEG streams. The inference pipeline is stream-type agnostic — both produce frames that flow through the same motion gate and detection path.

MJPEG output is also served for browser-native live preview without requiring HLS, WebRTC, or any browser plugins.

### Real-Time Events

A WebSocket endpoint streams detection events and camera status changes to connected clients in real time. When the AI detects a person, vehicle, or animal, the event is broadcast immediately — the web UI, external integrations, or custom dashboards can subscribe and react without polling.

### Cross-Platform Deployment

ONVIFy runs as a native service on all three target platforms:

- **Windows Server** — Installed via MSI (built with WiX Toolset v6/v7), registered as a native Windows Service. Supports standard `sc.exe` management, starts on boot, and runs under a configurable service account. Release artifacts are Azure code-signed.
- **Ubuntu Server 22.04+** — Runs as a systemd service with security hardening (NoNewPrivileges, ProtectSystem, PrivateTmp). Also available as a Docker container.
- **macOS (Apple Silicon)** — Runs as a launchd daemon. Automatically detects and uses MPS/CoreML for GPU-accelerated inference.

## Architecture

### Process Model

ONVIFy runs as a single main process (FastAPI on Uvicorn) with an inference worker subprocess for AI detection. MediaMTX runs as a managed subprocess handling RTSP stream routing.

```
Main Process (FastAPI + Uvicorn)
├── REST API + WebSocket
├── ONVIF SOAP services
├── Camera lifecycle management
├── Motion detection (local, cheap)
├── MJPEG stream handler
│
├── Inference Worker Process (IPC)
│   └── Local YOLO / External API client
│
└── MediaMTX (managed subprocess)
    └── RTSP stream routing
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| API server | FastAPI + Uvicorn |
| Configuration | Pydantic Settings (env vars + .env) |
| Database | SQLite + aiosqlite |
| Logging | structlog (JSON in production, console in dev) |
| RTSP server | MediaMTX (managed subprocess) |
| AI inference | ultralytics (YOLO), optional CoreML/MPS |
| Frontend | React + TypeScript + Tailwind CSS + shadcn/ui (planned) |
| Packaging | WiX (Windows), systemd (Linux), launchd (macOS) |

### Project Structure

```
src/onvify/
├── config.py              # Pydantic Settings — all env-based config
├── cli.py                 # CLI entry point
├── models/                # Domain models (Camera, Detection, ONVIF types)
├── services/              # Business logic
│   ├── camera_manager.py  # Camera lifecycle and persistence
│   ├── streaming.py       # MediaMTX process and config management
│   ├── mjpeg.py           # MJPEG input/output handlers
│   ├── onvif_device.py    # ONVIF Device/Media/Events service
│   └── onvif_discovery.py # WS-Discovery responder
├── inference/             # AI detection pipeline
│   ├── protocol.py        # InferenceBackend Protocol definition
│   ├── local_yolo.py      # Local YOLO backend (MPS/CoreML/CPU)
│   ├── openai_compatible.py # External API backend
│   ├── motion_gate.py     # Stage 1 motion pre-filter
│   └── pipeline.py        # Two-stage orchestrator
├── api/                   # FastAPI routes and WebSocket
├── onvif_xml/             # ONVIF SOAP response templates
└── infrastructure/        # Logging, database, platform abstraction
```

## Development Standards

- **Type-safe**: `mypy --strict` on all source code
- **Tested**: pytest with fixtures; inference tests use short MP4 samples for deterministic, idempotent assertions
- **Linted**: ruff for formatting and lint rules
- **PR discipline**: ~500 LOC per PR, structured summary with test plan, CI must pass before merge
- **Async-first**: no sync blocking in async code paths
- **Pydantic everywhere**: all external data boundaries (API, config, persistence) use Pydantic models

## CI/CD

GitHub Actions with a multi-stage pipeline:

1. **Build & Unit Tests** (GitHub-hosted) — lint, type check, unit tests across Python 3.11/3.12
2. **Windows E2E** (self-hosted) — MSI build/install lifecycle, integration tests
3. **macOS E2E** (self-hosted, Apple Silicon) — CoreML inference, launchd service tests
4. **Release & Sign** (self-hosted, tag-triggered) — Azure OIDC code signing, MSI packaging, GitHub Release creation

Self-hosted runner jobs are guarded against fork PRs and the release environment restricts signing secrets to `v*` tags only.
