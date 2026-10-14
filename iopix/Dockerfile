# digiKam Viewer in a container. Mount the digiKam database folder and the photo folder
# read-only, and a writable volume at /data for everything the viewer writes (index,
# thumbnails, models, state, backups). See docker-compose.yml and README "Running in Docker".
#
# Build arguments:
#   AI=1        (default) also install content search, text recognition and object detection
#               (fastembed, rapidocr, onnxruntime, numpy; several hundred MB). AI=0 for browsing only.
#   CAPTIONS=1  also install PyTorch (CPU build) and transformers for photo descriptions; about
#               1 GB more and slow without a GPU. Off by default.
# The image contains no models. On the first start the viewer downloads the ones named in
# AUTO_MODELS (default: SigLIP 2 search, YOLOX objects, GeoNames places; about 1.6 GB) into the
# /data volume, one after another, while the library is already browsable; later starts find them
# there. Set AUTO_MODELS="" to skip, add "blip" with CAPTIONS=1, or use Settings > Models and data.
FROM python:3.12-slim
ARG AI=1
ARG CAPTIONS=0
# ffmpeg: video thumbnails. exiftool: metadata editing and the consistency checker.
# libheif1: HEIC decoding for pillow-heif. libglib2.0-0: needed by RapidOCR's headless OpenCV.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libimage-exiftool-perl libheif1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$AI" = "1" ]; then pip install --no-cache-dir -r requirements-search.txt -r requirements-ocr.txt -r requirements-objects.txt; fi \
    && if [ "$CAPTIONS" = "1" ]; then pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-captions.txt; fi
COPY app ./app
COPY static ./static
# DIGIKAM_CHECK=ask: the container cannot see the host's processes, so before writing digiKam's
# database the viewer asks you to confirm digiKam is closed. HF_HUB_OFFLINE=1: the server never
# contacts the model hub (downloads run in a child process that turns it back on).
ENV DIGIKAM_DB_DIR=/library/digikamDB PHOTOS_ROOT=/library/photos DATA_DIR=/data \
    DIGIKAM_CHECK=ask VISION_ENGINE=portable HF_HUB_OFFLINE=1 CAPTIONS=${CAPTIONS} PYTHONUNBUFFERED=1 \
    AUTO_MODELS=siglip2,yolox,geonames
EXPOSE 8600
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8600/api/status', timeout=4)" || exit 1
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8600"]
