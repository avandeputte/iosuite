# ionote in a container. Everything it keeps is in its MariaDB/MySQL database (DB_* below); /data only holds
# the session secret, the log and settings an admin saved. See docker-compose.yml and README "Running in Docker".
#
# Build arguments:
#   COMMIT  the commit the image is built from (the version check compares it with GitHub)
#   OCR=1  (default) also install RapidOCR, which reads the text in pictures added in the web app
#          (the Mac and iPhone apps read it themselves). OCR=0 for a smaller image.
FROM python:3.12-slim
ARG OCR=1
# libheif1: HEIC pictures from iPhones (pillow-heif). libglib2.0-0: RapidOCR's headless OpenCV.
RUN apt-get update && apt-get install -y --no-install-recommends libheif1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY ionote/pyproject.toml ionote/README.md ./
COPY ionote/app ./app
COPY ionote/static ./static
# the suite's shared library, from the same commit: shared/ of the repository (the build context is the repository root)
COPY shared /opt/iosuite-shared
RUN pip install --no-cache-dir /opt/iosuite-shared
ARG COMMIT=unknown
RUN echo "$COMMIT" > COMMIT
RUN pip install --no-cache-dir -e ".$([ "$OCR" = "1" ] && echo [ocr])"
# runs as its own user (uid 1000), not as root, like iopix
RUN useradd --uid 1000 --user-group --create-home --shell /usr/sbin/nologin ionote \
    && mkdir -p /data && chown -R ionote:ionote /data /app
VOLUME ["/data"]
ENV DATA_DIR=/data PYTHONUNBUFFERED=1 OCR=${OCR}
EXPOSE 8610
USER ionote
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8610/api/status', timeout=4)" || exit 1
CMD ["python", "-m", "app"]
