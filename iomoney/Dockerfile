# ioMoney in a container. It keeps everything in MariaDB / MySQL (DB_* below), so the container itself keeps nothing.
FROM python:3.12-slim
WORKDIR /app
COPY iomoney/pyproject.toml iomoney/README.md ./
COPY iomoney/app ./app
COPY iomoney/static ./static
# the suite's shared library, from the same commit: shared/ of the repository (the build context is the repository root)
COPY shared /opt/iosuite-shared
RUN pip install --no-cache-dir /opt/iosuite-shared \
    && pip install --no-cache-dir -e . \
    && mkdir -p /app/data \
    && useradd --uid 1000 --user-group --no-create-home --shell /usr/sbin/nologin iomoney && chown -R iomoney:iomoney /app
# the commit the image was built from, for Maintenance › Updates and logs (the workflow passes it)
ARG COMMIT=unknown
RUN echo "$COMMIT" > COMMIT
# the database settings come from the environment (docker-compose.yml): no password is baked into the image
ENV DB_HOST=db DB_PORT=3306 DB_NAME=iomoney DB_USER=iomoney PORT=8710 PYTHONUNBUFFERED=1
EXPOSE 8710
USER iomoney
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8710/api/status', timeout=4)" || exit 1
CMD ["python", "-m", "app"]
