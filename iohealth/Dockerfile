# ioHealth in a container: the iPhone's upload API and the web app on port 8650. Everything it keeps is in MariaDB
# (DB_* and the Shared ioSuite database, IOSUITE_DB_*); only the server log is written, to data/ inside the container. See docker-compose.yml.
FROM python:3.12-slim
WORKDIR /app
COPY iohealth/pyproject.toml ./
COPY iohealth/app ./app
COPY iohealth/static ./static
# the suite's shared library, from the same commit: shared/ of the repository (the build context is the repository root)
COPY shared /opt/iosuite-shared
RUN pip install --no-cache-dir /opt/iosuite-shared
RUN pip install --no-cache-dir -e .
# the commit the image was built from, for Maintenance › ioHealth version (the workflow passes it)
ARG COMMIT=unknown
RUN echo "$COMMIT" > COMMIT
# runs as its own user (uid 1000), not as root, like iopix and ionote
RUN useradd --uid 1000 --user-group --create-home --shell /usr/sbin/nologin iohealth && chown -R iohealth:iohealth /app
ENV PYTHONUNBUFFERED=1
EXPOSE 8650
USER iohealth
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8650/v1/health', timeout=4)" || exit 1
CMD ["python", "-m", "app"]
