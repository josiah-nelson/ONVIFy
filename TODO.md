# TODO

Outstanding work from initial scaffolding. Items are roughly ordered by dependency — earlier items unblock later ones.

## Core Functionality

- [x] **Camera persistence** — Wire `CameraManager` to SQLite via `infrastructure/database.py`. Currently cameras exist only in memory and are lost on restart.
- [x] **MediaMTX config lifecycle integration** — Connect `streaming.py` to camera mutations so adding/removing a camera automatically updates MediaMTX config and triggers a reload.
- [x] **MediaMTX binary management** — Download and version-check the MediaMTX binary on first run.
- [x] **RTSP frame grabber** — Implement an async frame grabber that pulls frames from RTSP sources (via OpenCV or FFmpeg subprocess) and feeds them into the inference pipeline.
- [x] **MJPEG frame grabber integration** — Connect `services/mjpeg.py` pull logic to the camera manager so MJPEG cameras automatically start pulling frames on creation.
- [x] **MJPEG output endpoint** — Add a FastAPI streaming route (e.g., `GET /api/cameras/{id}/mjpeg`) that serves live MJPEG for browser preview.
- [x] **Inference pipeline wiring** — Connect the inference pipeline to the frame grabbers so detection runs automatically on cameras with `ai_enabled=True`. Manage pipeline lifecycle (start/stop/reset) alongside camera state changes.
- [x] **Detection event persistence** — Store detection events in SQLite and expose via API (`GET /api/detection/events`).
- [x] **WebSocket event broadcasting** — Wire the `ConnectionManager` to broadcast detection events and camera status changes as they occur.

## ONVIF Protocol

- [x] **ONVIF SOAP response templates** — Extract and adapt the ONVIF XML templates for GetDeviceInformation, GetProfiles, GetStreamUri, GetCapabilities, and GetScopes. Place in `onvif_xml/`.
- [x] **ONVIF HTTP server** — Stand up per-camera ONVIF SOAP endpoints that NVRs can query. Each virtual camera needs its own port.
- [x] **WS-Discovery implementation** — Implement the UDP multicast listener in `onvif_discovery.py` so NVRs can auto-discover virtual cameras on the network.
- [x] **ONVIF event subscription** — Forward AI detection events as ONVIF motion events so NVRs can trigger recording on detection.

## Frontend

- [ ] **React SPA scaffold** — Initialize the React + TypeScript + Tailwind + shadcn/ui project in `frontend/`.
- [ ] **API client generation** — Auto-generate a typed TypeScript API client from FastAPI's OpenAPI schema.
- [ ] **Camera management UI** — CRUD interface for adding, editing, and removing cameras.
- [ ] **Live stream preview** — Display MJPEG preview streams in the browser for each camera.
- [ ] **Detection event feed** — Real-time event display via WebSocket with filtering by camera, object class, and time range.
- [ ] **Grid view / multi-camera layout** — Multi-camera grid composer for monitoring dashboards.
- [ ] **Static asset serving** — Configure FastAPI to serve the built React assets so the entire app deploys as a single process.

## Authentication

- [ ] **API authentication** — Implement session-based or token-based auth for the REST API and WebSocket.
- [ ] **Auth route handlers** — Flesh out `api/routes/auth.py` with login, logout, and session management.
- [ ] **ONVIF credentials** — Per-camera ONVIF username/password for the virtual device SOAP endpoints.
- [ ] **RTSP auth passthrough** — Optional global RTSP authentication on MediaMTX streams.

## Inference

- [ ] **CoreML export pipeline** — Implement automatic YOLO-to-CoreML export and caching on first run for Apple Silicon (the logic exists in the fork and needs to be ported into `local_yolo.py`).
- [ ] **Process isolation** — Move local YOLO inference into a separate worker process via `multiprocessing` to avoid GIL contention with the async event loop.
- [x] **OpenAI-compatible backend testing** — Integration test with a mock server that validates the request format and response parsing.
- [x] **Inference health endpoint** — Expose backend health status via `GET /api/detection/health` using the backend's `health_check()` method.
- [ ] **Test fixtures** — Record or source short MP4 samples (person, vehicle, static scene, multi-object) and add to `tests/fixtures/`.

## Packaging and Deployment

- [x] **Self-hosted CI Python setup** — Fix macOS/Windows self-hosted runner Python toolcache permissions so E2E jobs get past `actions/setup-python`.
- [ ] **WiX MSI project** — Create the WiX v6/v7 `.wxs` file in `packaging/windows/` with ServiceInstall/ServiceControl elements for native Windows Service registration.
- [ ] **PyInstaller bundling** — Script to bundle the Python app into a standalone executable for Windows MSI packaging.
- [ ] **MSI lifecycle test script** — Automated install/verify/uninstall test (similar to BANS `test-msi-lifecycle.ps1`).
- [x] **Dockerfile** — Multi-stage Dockerfile for containerized deployment.
- [x] **docker-compose.yml** — Compose file bundling ONVIFy + MediaMTX.

## Streams and Detection API

- [x] **Streams endpoint** — Implement `GET /api/streams/status` to return active stream status, reader count, and byte counters (via MediaMTX API).
- [x] **Detection config endpoint** — Implement `GET/PATCH /api/detection/config` to view and update inference settings at runtime.

## Observability

- [x] **Structured log context** — Bind `camera_id` and `stream_id` to structlog context in request handlers and background tasks.
- [x] **Health endpoint enrichment** — Include MediaMTX status, inference backend health, database connectivity, and active camera count in `GET /api/system/health`.
- [x] **Diagnostics endpoint** — System info, uptime, resource usage, and per-camera stream statistics.
