# ioCalendar in a container. It keeps everything in MariaDB / MySQL (DB_* below), so the container itself is stateless.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
COPY static ./static
# git only while installing: iothing-auth (the suite's shared accounts) comes from its GitHub repository
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && pip install --no-cache-dir -e . \
    && apt-get purge -y --auto-remove git && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --user-group --no-create-home --shell /usr/sbin/nologin iocalendar && chown -R iocalendar:iocalendar /app
ENV DB_HOST=db DB_PORT=3306 DB_NAME=calendar DB_USER=calendar DB_PASSWORD=calendar PYTHONUNBUFFERED=1
EXPOSE 8620
USER iocalendar
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8620/api/status', timeout=4)" || exit 1
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8620", "--proxy-headers", "--forwarded-allow-ips=*"]
