"""Settings: config.env in the app folder (setup.sh writes it), or the environment, which wins. Everything stored
lives in MariaDB, the photos too. The settings every app of the suite shares come from iosuite_shared.config.standard."""
from pathlib import Path

from iosuite_shared import config as shared

APP = "iorecipe"
APP_DIR = Path(__file__).resolve().parent.parent
shared.load_file(APP_DIR)  # first: iosuite_shared reads its settings (the Shared ioSuite database, COOKIE_DOMAIN) from it too
env, env_flag, env_int = shared.env, shared.env_flag, shared.env_int
# APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, TLS_CERT_FILE, TLS_KEY_FILE,
# MCP_FORCED, KEEP_DELETED_DAYS, ADMIN_USER, ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
globals().update(shared.standard(APP, APP_DIR))

# the app's own database (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD; no default password)
_db = shared.own_db("recipe")
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = _db["host"], _db["port"], _db["database"], _db["user"], _db["password"]

MAX_PHOTO_BYTES = 20 * 1024 * 1024    # a photo as it is uploaded (it is kept much smaller: app/images.py)
MAX_PAGE_BYTES = 5 * 1024 * 1024      # a web page a recipe is imported from
MAX_IMPORT_BYTES = 300 * 1024 * 1024  # a file of recipes to import (an ioRecipe or Mealie export, with its photos)
MAX_JSON_BYTES = 2 * 1024 * 1024      # any other request body

# reading a photo of a recipe (app/ocr.py): the languages Tesseract tries, as its codes with + between (eng+nld+fra);
# empty: every language installed
OCR_LANGUAGES = env("OCR_LANGUAGES")

# reading a web page that has no recipe data with AI (app/ai.py): a small model that runs on this server, inside the
# app. AI=0 turns it off; AI_MODEL is another model than the one the app fetches (a GGUF file here, or the address of
# one); AI_TIMEOUT is how many seconds one page may take
AI = env_flag("AI", True)
AI_MODEL = env("AI_MODEL")
AI_TIMEOUT = env_int("AI_TIMEOUT", 300)

# `python -m app.mcp` (stdio) acts as this account. Updates: IORECIPE_REPO, IORECIPE_BRANCH and UPDATE_CHECK are read
# by iosuite_shared.updates (app.auth.updater)
MCP_USER = env("MCP_USER")
