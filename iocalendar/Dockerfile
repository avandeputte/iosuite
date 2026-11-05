# ioCalendar in a container. It keeps everything in MariaDB / MySQL (DB_* below), so the container itself is stateless.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
COPY static ./static
# git only while installing: iosuite-shared (the suite's shared library) comes from its GitHub repository, avandeputte/iosuite-shared
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && pip install --no-cache-dir -e . \
    && apt-get purge -y --auto-remove git && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --user-group --no-create-home --shell /usr/sbin/nologin iocalendar && chown -R iocalendar:iocalendar /app
# the commit the image was built from, for Maintenance › Updates and logs (the workflow passes it)
ARG COMMIT=unknown
RUN echo "$COMMIT" > COMMIT
ENV DB_HOST=db DB_PORT=3306 DB_NAME=calendar DB_USER=calendar DB_PASSWORD=calendar PORT=8620 PYTHONUNBUFFERED=1
EXPOSE 8620
USER iocalendar
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8620/api/status', timeout=4)" || exit 1
CMD ["python", "-m", "app"]
