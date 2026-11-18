"""Command line: python -m app.cli <command>

  migrate                 create or update the tables
  check                   connect to the databases and say what is there, and what this server can read off a scan
  read FILE               what ioDocs reads off a scan or a PDF (nothing is kept): a test of OCR on this server

Accounts are the suite's: `iosuite-shared --config . admin NAME --app iodocs` makes an admin (setup.sh does),
`iosuite-shared --config . password NAME` sets a password.
"""
import json
import mimetypes
import sys
from pathlib import Path

from app import db, ocr, users


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "read":
        if len(args) != 1:
            print("read FILE", file=sys.stderr)
            return 2
        raw = Path(args[0]).read_bytes()
        mime = "application/pdf" if raw[:4] == b"%PDF" else mimetypes.guess_type(args[0])[0] or "image/jpeg"
        got = ocr.read(raw, mime)
        print(json.dumps({"reads": ocr.available(), "source": got["source"], "found": got["found"]}, indent=2, default=str))
        print("--- text ---")
        print(got["text"])
        return 0
    db.migrate()
    if cmd == "migrate":
        print("ok: tables ready")
    elif cmd == "check":
        n = db.one("SELECT count(*) AS n FROM doc_documents")["n"]
        users.init()
        print(f"ok: {len(users.all_users())} account(s), {n} document(s); reads: {ocr.available()}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
