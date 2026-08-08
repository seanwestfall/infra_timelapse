FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_DIR=/tmp/infra-timelapse/images \
    METADATA_FILE=/tmp/infra-timelapse/metadata.json

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py fetch_images.py cloud_run_job.py capture_api.py ./
COPY infra_timelapse_ports_corridors.json ./
COPY entrypoint.sh ./

RUN chmod 755 entrypoint.sh

USER 65532:65532

ENTRYPOINT ["./entrypoint.sh"]
