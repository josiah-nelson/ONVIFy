# ONVIFy

Enterprise ONVIF/RTSP virtual camera server with pluggable AI detection.

ONVIFy takes real camera streams (RTSP or MJPEG), runs optional AI object detection (motion-gated, two-stage pipeline), and re-exposes them as ONVIF-compliant virtual cameras that NVRs can discover and stream from.

## Features

- **ONVIF-compliant** virtual cameras with WS-Discovery
- **RTSP and MJPEG** input stream support
- **Pluggable AI inference** — local YOLO, OpenAI-compatible API, or dedicated vision server
- **Two-stage detection pipeline** — cheap motion gate filters static scenes before expensive inference
- **Apple Silicon optimized** — MPS and CoreML/Neural Engine acceleration
- **Cross-platform** — Windows Server, Ubuntu 22.04+, macOS (Apple Silicon)
- **Enterprise deployment** — native Windows Service (WiX MSI), systemd, launchd

## Quick Start

See [QUICKSTART.md](QUICKSTART.md) for full setup instructions.

```bash
git clone https://github.com/josiah-nelson/ONVIFy.git
cd ONVIFy
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
onvify --debug
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow and PR standards.

## License

[Elastic License 2.0](LICENSE). See [NOTICE](NOTICE) for third-party licenses.
