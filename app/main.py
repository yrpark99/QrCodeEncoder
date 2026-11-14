"""QR Code Encoder web service (FastAPI)."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import envfile

# Load settings file before anything reads the environment.
# QRENCODER_ENV_FILE can point to another file; default is deploy/qrencoder.env.
envfile.load(os.environ.get(
    "QRENCODER_ENV_FILE",
    Path(__file__).resolve().parent.parent / "deploy" / "qrencoder.env",
))

from . import qrencode  # noqa: E402  (reads QRENCODE_LIB at import time)

log = logging.getLogger("qrencoder")

SETTINGS = qrencode.QRSettings.from_env()
# Welcome message shown above the input box. Not shown if unset or empty.
WELCOME_MESSAGE = os.environ.get("WELCOME_MESSAGE", "").strip()
# Max QR capacity is 2953 bytes (version 40, level L, 8-bit). Leave some slack
# for the JSON envelope; the library reports ERANGE for anything that does not fit.
MAX_INPUT_BYTES = int(os.environ.get("MAX_INPUT_BYTES", "4096"))

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="QR Code Encoder", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def no_stale_assets(request: Request, call_next):
    # Make browsers revalidate the page and static files on every load (cheap 304
    # via ETag), so an updated app.js/style.css is never served from a stale cache.
    response = await call_next(request)
    response.headers.setdefault("Cache-Control", "no-cache")
    return response

if qrencode.LIB_VERSION != qrencode.EXPECTED_LIB_VERSION:
    log.warning("libqrencode %s loaded, but %s is expected (STB uses %s)",
                qrencode.LIB_VERSION, qrencode.EXPECTED_LIB_VERSION, qrencode.EXPECTED_LIB_VERSION)


class EncodeRequest(BaseModel):
    text: str


@app.get("/", include_in_schema=False)
def index() -> HTMLResponse:
    # Append a content hash to asset URLs (cache busting): when app.js or
    # style.css changes, the URL changes, so browsers can never reuse an old copy.
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for name in ("app.js", "style.css"):
        digest = hashlib.sha256((STATIC_DIR / name).read_bytes()).hexdigest()[:10]
        html = html.replace(f"/static/{name}\"", f"/static/{name}?v={digest}\"")
    return HTMLResponse(html)


@app.get("/api/info")
def info() -> dict:
    return {
        "welcome": WELCOME_MESSAGE,
        "libqrencode": qrencode.LIB_VERSION,
        "level": SETTINGS.level,
        "version": SETTINGS.version,
        "mode": SETTINGS.mode,
        "casesensitive": SETTINGS.casesensitive,
        "newline": SETTINGS.newline,
        "margin": SETTINGS.margin,
        "max_input_bytes": MAX_INPUT_BYTES,
    }


@app.post("/api/encode")
async def encode(request: Request) -> Response:
    body = await request.body()
    if len(body) > MAX_INPUT_BYTES + 1024:
        return JSONResponse({"error": "Request too large"}, status_code=413)
    try:
        req = EncodeRequest.model_validate_json(body)
    except ValueError:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    if len(req.text.encode("utf-8")) > MAX_INPUT_BYTES:
        return JSONResponse({"error": f"Input exceeds {MAX_INPUT_BYTES} bytes"}, status_code=400)

    try:
        matrix = qrencode.encode(req.text, SETTINGS)
    except qrencode.QREncodeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    svg = qrencode.to_svg(matrix, margin=SETTINGS.margin)
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "X-QR-Version": str(matrix.version),
            "X-QR-Width": str(matrix.width),
            "Cache-Control": "no-store",
        },
    )
