# ioBackup in a container. Its settings live in MariaDB / MySQL (DB_* below); backups go to the destinations you add (a
# volume mounted at /backups is the suggested local one) and are put together in /data/work first.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
COPY static ./static
# git only while installing: iosuite-shared (the suite's shared library) comes from its GitHub repository, avandeputte/iosuite-shared
# mariadb-client: mariadb-dump and mariadb, which take the backups and replay them; openssl signs Google service account keys
RUN apt-get update && apt-get install -y --no-install-recommends git mariadb-client openssl \
    && pip install --no-cache-dir -e . \
    && apt-get purge -y --auto-remove git && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --user-group --no-create-home --shell /usr/sbin/nologin iobackup && chown -R iobackup:iobackup /app \
    && mkdir -p /data /backups && chown iobackup:iobackup /data /backups
# the commit the image was built from, for Maintenance › Updates and logs (the workflow passes it)
ARG COMMIT=unknown
RUN echo "$COMMIT" > COMMIT
# the database settings come from the environment (docker-compose.yml): no password is baked into the image
ENV DB_HOST=db DB_PORT=3306 DB_NAME=backup DB_USER=backup PORT=8680 DATA_DIR=/data BACKUP_DIR=/backups PYTHONUNBUFFERED=1
VOLUME ["/data", "/backups"]
EXPOSE 8680
USER iobackup
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8680/api/status', timeout=4)" || exit 1
CMD ["python", "-m", "app"]
