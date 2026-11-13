# ioRecipe in a container. It keeps everything in MariaDB / MySQL (DB_* below), so the container itself keeps nothing but
# the AI model it fetches (a file that can always be fetched again).
# The AI that reads a page without recipe data (app/ai.py) is llama.cpp, compiled here once, for any processor of
# the image's kind (not this machine's own), and carried over as a wheel: the compilers stay out of the image.
FROM python:3.12-slim AS llama
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake git \
    && CMAKE_ARGS="-DGGML_NATIVE=OFF -DLLAVA_BUILD=OFF" pip wheel --no-cache-dir --no-deps -w /wheels "llama-cpp-python>=0.3,<0.4"

FROM python:3.12-slim
WORKDIR /app
COPY iorecipe/pyproject.toml iorecipe/README.md ./
COPY iorecipe/app ./app
COPY iorecipe/static ./static
# the suite's shared library, from the same commit: shared/ of the repository (the build context is the repository root)
COPY shared /opt/iosuite-shared
RUN pip install --no-cache-dir /opt/iosuite-shared
# tesseract stays: it reads the text on a photo of a recipe (Import › Photo), in English, Dutch, French and German
# libgomp1 stays too: the AI model's runtime works with it. The model itself (about 1 GB) is fetched on the first
# start into /app/data/models: keep that folder on a volume (docker-compose.yml does)
RUN --mount=type=bind,from=llama,source=/wheels,target=/wheels \
    apt-get update && apt-get install -y --no-install-recommends libgomp1 tesseract-ocr tesseract-ocr-nld tesseract-ocr-fra tesseract-ocr-deu \
    && pip install --no-cache-dir -e . && pip install --no-cache-dir --find-links /wheels "llama-cpp-python>=0.3,<0.4" \
    && mkdir -p /app/data \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --user-group --no-create-home --shell /usr/sbin/nologin iorecipe && chown -R iorecipe:iorecipe /app
# the commit the image was built from, for Maintenance › Updates and logs (the workflow passes it)
ARG COMMIT=unknown
RUN echo "$COMMIT" > COMMIT
# the database settings come from the environment (docker-compose.yml): no password is baked into the image
ENV DB_HOST=db DB_PORT=3306 DB_NAME=recipe DB_USER=recipe PORT=8690 PYTHONUNBUFFERED=1
EXPOSE 8690
USER iorecipe
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8690/api/status', timeout=4)" || exit 1
CMD ["python", "-m", "app"]
