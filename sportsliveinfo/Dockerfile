FROM python:3.12-alpine

# Supervisor passes these build arguments when building a custom Home Assistant
# App from a Dockerfile. Defaults also make an independent local docker build
# carry valid metadata for amd64 development.
ARG BUILD_VERSION=0.3.11
ARG BUILD_ARCH=amd64
LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/sportsliveinfo/src \
    SLI_DATA_DIR=/data
WORKDIR /opt/sportsliveinfo
COPY src/ ./src/
COPY icon.png ./src/sportsliveinfo/icon.png
CMD ["python", "-m", "sportsliveinfo"]
