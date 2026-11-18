# ioDocs in a container. It keeps everything in MariaDB / MySQL (DB_* below), the scans of every document included, so the container itself is stateless.
FROM python:3.12-slim
WORKDIR /app
COPY iodocs/pyproject.toml iodocs/README.md ./
COPY iodocs/app ./app
COPY iodocs/static ./static
# the suite's shared library, from the same commit: shared/ of the repository (the build context is the repository root)
COPY shared /opt/iosuite-shared
# Tesseract (and its English words) reads the scans; poppler turns a scanned PDF into pictures for it
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng poppler-utils && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir /opt/iosuite-shared
RUN pip install --no-cache-dir -e . \
    && useradd --uid 1000 --user-group --no-create-home --shell /usr/sbin/nologin iodocs && chown -R iodocs:iodocs /app
# the commit the image was built from, for Maintenance › Updates and logs (the workflow passes it)
ARG COMMIT=unknown
RUN echo "$COMMIT" > COMMIT
# the database settings come from the environment (docker-compose.yml): no password is baked into the image
ENV DB_HOST=db DB_PORT=3306 DB_NAME=iodocs DB_USER=iodocs PORT=8720 PYTHONUNBUFFERED=1
EXPOSE 8720
USER iodocs
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8720/api/status', timeout=4)" || exit 1
CMD ["python", "-m", "app"]
