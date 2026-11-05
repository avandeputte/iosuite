# ionotes in a container. Everything it keeps is in its MariaDB/MySQL database (DB_* below); /data only holds
# the session secret, the log and settings an admin saved. See docker-compose.yml and README "Running in Docker".
#
# Build argument:
#   OCR=1  (default) also install RapidOCR, which reads the text in pictures added in the web app
#          (the Mac and iPhone apps read it themselves). OCR=0 for a smaller image.
FROM python:3.12-slim
ARG OCR=1
# libheif1: HEIC pictures from iPhones (pillow-heif). libglib2.0-0: RapidOCR's headless OpenCV.
# git: pip fetches the ioSuite shared library (package iosuite-shared, repository avandeputte/iosuite-shared) from GitHub.
RUN apt-get update && apt-get install -y --no-install-recommends libheif1 libglib2.0-0 git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
COPY static ./static
RUN pip install --no-cache-dir -e ".$([ "$OCR" = "1" ] && echo [ocr])"
# runs as its own user (uid 1000), not as root, like iopix
RUN useradd --uid 1000 --user-group --create-home --shell /usr/sbin/nologin ionotes \
    && mkdir -p /data && chown -R ionotes:ionotes /data /app
VOLUME ["/data"]
ENV DATA_DIR=/data PYTHONUNBUFFERED=1 OCR=${OCR}
EXPOSE 8610
USER ionotes
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8610/api/status', timeout=4)" || exit 1
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8610", "--proxy-headers"]
