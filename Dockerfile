# ioSuite in a container. Its few settings live in MariaDB / MySQL (DB_* below), so the container itself is stateless.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
COPY static ./static
# git only while installing: the suite's shared library (avandeputte/iosuite-shared) comes from GitHub
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && pip install --no-cache-dir -e . \
    && apt-get purge -y --auto-remove git && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --user-group --no-create-home --shell /usr/sbin/nologin iosuite && chown -R iosuite:iosuite /app
# the commit the image was built from, for Maintenance › Updates and logs (the workflow passes it)
ARG COMMIT=unknown
RUN echo "$COMMIT" > COMMIT
# the database settings come from the environment (docker-compose.yml): no password is baked into the image
ENV DB_HOST=db DB_PORT=3306 DB_NAME=suite DB_USER=suite PORT=8630 PYTHONUNBUFFERED=1
EXPOSE 8630
USER iosuite
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8630/api/status', timeout=4)" || exit 1
CMD ["python", "-m", "app"]
