# ── Build stage ─────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir build \
    && python -m build --wheel --outdir /build/dist

# ── Runtime stage ──────────────────────────────
FROM python:3.13-slim

LABEL org.opencontainers.image.title="ONVIFy" \
      org.opencontainers.image.description="Enterprise ONVIF/RTSP virtual camera server with pluggable AI detection" \
      org.opencontainers.image.source="https://github.com/josiah-nelson/ONVIFy"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 onvify \
    && useradd --uid 1000 --gid onvify --create-home onvify

WORKDIR /app

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl "onvify[inference]" \
    && rm -f /tmp/*.whl

RUN mkdir -p /data && chown onvify:onvify /data
VOLUME /data

USER onvify

ENV ROOT_DIR=/data \
    MEDIAMTX_AUTO_DOWNLOAD=true \
    LOG_FORMAT=json

EXPOSE 5552 8554 9997

ENTRYPOINT ["onvify"]
CMD ["--host", "0.0.0.0"]
