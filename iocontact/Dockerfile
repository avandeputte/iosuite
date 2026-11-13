# ioContact in a container. It keeps everything in MariaDB / MySQL (DB_* below), so the container itself is stateless.
FROM python:3.12-slim
WORKDIR /app
COPY iocontact/pyproject.toml iocontact/README.md ./
COPY iocontact/app ./app
COPY iocontact/static ./static
# the suite's shared library, from the same commit: shared/ of the repository (the build context is the repository root)
COPY shared /opt/iosuite-shared
RUN pip install --no-cache-dir /opt/iosuite-shared
RUN pip install --no-cache-dir -e . \
    && useradd --uid 1000 --user-group --no-create-home --shell /usr/sbin/nologin iocontact && chown -R iocontact:iocontact /app
# the commit the image was built from, for Maintenance › Updates and logs (the workflow passes it)
ARG COMMIT=unknown
RUN echo "$COMMIT" > COMMIT
# the database settings come from the environment (docker-compose.yml): no password is baked into the image
ENV DB_HOST=db DB_PORT=3306 DB_NAME=contacts DB_USER=contacts PORT=8640 LDAP_PORT=3890 PYTHONUNBUFFERED=1
EXPOSE 8640 3890
USER iocontact
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8640/api/status', timeout=4)" || exit 1
CMD ["python", "-m", "app"]
