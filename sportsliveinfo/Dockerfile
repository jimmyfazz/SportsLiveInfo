FROM python:3.12-alpine
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/opt/sportsliveinfo/src SLI_DATA_DIR=/data
WORKDIR /opt/sportsliveinfo
COPY src/ ./src/
COPY icon.png ./src/sportsliveinfo/icon.png
CMD ["python", "-m", "sportsliveinfo"]
