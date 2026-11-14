"""libqrencode (4.1.1) ctypes binding and SVG renderer.

The library only produces a module matrix (QRcode struct). SVG generation
follows the same idea as writeSVG() in qrenc.c of libqrencode: a background
rectangle plus horizontal run-length encoded dark modules.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import errno
import os
import threading
from dataclasses import dataclass

# --- libqrencode enums (qrencode.h) -----------------------------------------
QR_ECLEVEL = {"L": 0, "M": 1, "Q": 2, "H": 3}
QR_MODE_8 = 2
QR_MODE_KANJI = 3

EXPECTED_LIB_VERSION = "4.1.1"


class _QRcode(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_int),
        ("width", ctypes.c_int),
        ("data", ctypes.POINTER(ctypes.c_ubyte)),
    ]


_QRcode_p = ctypes.POINTER(_QRcode)


def _load_library() -> ctypes.CDLL:
    candidates = []
    env_path = os.environ.get("QRENCODE_LIB")
    if env_path:
        candidates.append(env_path)
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, "..", "vendor", "libqrencode", "lib", "libqrencode.so"))
    found = ctypes.util.find_library("qrencode")
    if found:
        candidates.append(found)

    errors = []
    for path in candidates:
        try:
            return ctypes.CDLL(path, use_errno=True)
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    raise OSError("libqrencode not found. Tried:\n  " + "\n  ".join(errors))


_lib = _load_library()

_lib.QRcode_encodeString.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
_lib.QRcode_encodeString.restype = _QRcode_p
_lib.QRcode_encodeString8bit.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
_lib.QRcode_encodeString8bit.restype = _QRcode_p
_lib.QRcode_free.argtypes = [_QRcode_p]
_lib.QRcode_free.restype = None
_lib.QRcode_APIVersionString.argtypes = []
_lib.QRcode_APIVersionString.restype = ctypes.c_char_p

LIB_VERSION = _lib.QRcode_APIVersionString().decode()

# Calls are serialized: cheap, and avoids depending on how the library was
# built with respect to pthread support.
_lock = threading.Lock()


class QREncodeError(ValueError):
    """Raised when the input can not be encoded (e.g. too long)."""


@dataclass(frozen=True)
class QRMatrix:
    version: int
    width: int
    modules: list[list[bool]]  # modules[y][x] is True for a dark module


@dataclass(frozen=True)
class QRSettings:
    level: str = "L"          # L / M / Q / H
    version: int = 0          # 0 = smallest version that fits
    mode: str = "string"      # string | 8bit | kanji
    casesensitive: bool = True
    newline: str = "lf"       # lf | crlf | keep
    margin: int = 4           # quiet zone in modules (display only)

    @classmethod
    def from_env(cls) -> "QRSettings":
        s = cls(
            level=os.environ.get("QR_LEVEL", "L").upper(),
            version=int(os.environ.get("QR_VERSION", "0")),
            mode=os.environ.get("QR_MODE", "string").lower(),
            casesensitive=os.environ.get("QR_CASESENSITIVE", "1") not in ("0", "false", "no"),
            newline=os.environ.get("QR_NEWLINE", "lf").lower(),
            margin=int(os.environ.get("QR_MARGIN", "4")),
        )
        if s.level not in QR_ECLEVEL:
            raise ValueError(f"QR_LEVEL must be one of L/M/Q/H, got {s.level!r}")
        if not 0 <= s.version <= 40:
            raise ValueError("QR_VERSION must be 0..40")
        if s.mode not in ("string", "8bit", "kanji"):
            raise ValueError("QR_MODE must be string, 8bit or kanji")
        if s.newline not in ("lf", "crlf", "keep"):
            raise ValueError("QR_NEWLINE must be lf, crlf or keep")
        if s.margin < 0:
            raise ValueError("QR_MARGIN must be >= 0")
        return s


def normalize_newlines(text: str, mode: str) -> str:
    if mode == "keep":
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if mode == "crlf":
        text = text.replace("\n", "\r\n")
    return text


def encode(text: str, settings: QRSettings) -> QRMatrix:
    """Encode text with libqrencode and return the module matrix."""
    text = normalize_newlines(text, settings.newline)
    data = text.encode("utf-8")
    if b"\x00" in data:
        raise QREncodeError("NUL characters are not allowed")
    if not data:
        raise QREncodeError("Input is empty")

    level = QR_ECLEVEL[settings.level]
    with _lock:
        ctypes.set_errno(0)
        if settings.mode == "8bit":
            qr = _lib.QRcode_encodeString8bit(data, settings.version, level)
        else:
            hint = QR_MODE_KANJI if settings.mode == "kanji" else QR_MODE_8
            qr = _lib.QRcode_encodeString(data, settings.version, level, hint,
                                          1 if settings.casesensitive else 0)
        err = ctypes.get_errno()

        if not qr:
            if err == errno.ERANGE:
                raise QREncodeError("Input data is too large for a QR code")
            raise QREncodeError(f"Encoding failed: {os.strerror(err) if err else 'unknown error'}")
        try:
            width = qr.contents.width
            version = qr.contents.version
            raw = ctypes.string_at(qr.contents.data, width * width)
        finally:
            _lib.QRcode_free(qr)

    # Bit 0 of each byte: 1 = dark module (see qrencode.h)
    modules = [[bool(raw[y * width + x] & 1) for x in range(width)] for y in range(width)]
    return QRMatrix(version=version, width=width, modules=modules)


def to_svg(matrix: QRMatrix, margin: int = 4, fg: str = "#000000", bg: str = "#ffffff") -> str:
    """Render the matrix as SVG. Coordinates are in modules; scale with CSS."""
    size = matrix.width + margin * 2
    parts = []
    for y, row in enumerate(matrix.modules):
        x = 0
        while x < matrix.width:
            if row[x]:
                x0 = x
                while x < matrix.width and row[x]:
                    x += 1
                parts.append(f"M{x0 + margin},{y + margin}h{x - x0}v1h-{x - x0}z")
            else:
                x += 1
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
        f'viewBox="0 0 {size} {size}" shape-rendering="crispEdges">'
        f'<rect x="0" y="0" width="{size}" height="{size}" fill="{bg}"/>'
        f'<path fill="{fg}" d="{"".join(parts)}"/>'
        f"</svg>"
    )
