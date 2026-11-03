# ioContacts in a container. It keeps everything in MariaDB / MySQL (DB_* below), so the container itself is stateless.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
COPY static ./static
RUN pip install --no-cache-dir -e . \
    && useradd --uid 1000 --user-group --no-create-home --shell /usr/sbin/nologin iocontacts && chown -R iocontacts:iocontacts /app
ENV DB_HOST=db DB_PORT=3306 DB_NAME=contacts DB_USER=contacts DB_PASSWORD=contacts LDAP_PORT=3890 PYTHONUNBUFFERED=1
EXPOSE 8610 3890
USER iocontacts
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8610/api/status', timeout=4)" || exit 1
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8610", "--proxy-headers", "--forwarded-allow-ips=*"]
