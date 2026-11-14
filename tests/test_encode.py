"""Compare our module matrix with the `qrencode` CLI of libqrencode 4.1.1.

Run:  pytest -q
The CLI comparison is skipped if no `qrencode` binary is found.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app import qrencode

ROOT = Path(__file__).resolve().parents[1]
VENDOR_BIN = ROOT / "vendor" / "libqrencode" / "bin" / "qrencode"
CLI = str(VENDOR_BIN) if VENDOR_BIN.exists() else shutil.which("qrencode")

SAMPLES = [
    "hello",
    "HELLO WORLD 12345",
    "line1\nline2\nline3",
    "English\n한글 테스트\n日本語",
    "https://example.com/path?q=1&r=2",
    "x" * 2953,  # max capacity at version 40-L in 8-bit mode
]

DEFAULT = qrencode.QRSettings()


def cli_matrix(text: str) -> list[list[bool]]:
    assert CLI is not None
    env = dict(os.environ)
    if VENDOR_BIN.exists():
        env["LD_LIBRARY_PATH"] = str(ROOT / "vendor" / "libqrencode" / "lib")
    # qrencode CLI defaults: -l L, -v 0, mode 8 hint, case sensitive.
    out = subprocess.run(
        [CLI, "-t", "ASCII", "-m", "0", "-o", "-", text],
        check=True, capture_output=True, env=env,
    ).stdout.decode()
    return [[line[i:i + 2] == "##" for i in range(0, len(line), 2)]
            for line in out.splitlines() if line]


def test_lib_version():
    assert qrencode.LIB_VERSION == qrencode.EXPECTED_LIB_VERSION


@pytest.mark.skipif(CLI is None, reason="qrencode CLI not available")
@pytest.mark.parametrize("text", SAMPLES)
def test_matches_cli(text):
    assert qrencode.encode(text, DEFAULT).modules == cli_matrix(text)


def test_too_long():
    with pytest.raises(qrencode.QREncodeError):
        qrencode.encode("x" * 2954, DEFAULT)


def test_crlf_normalized():
    a = qrencode.encode("a\r\nb", DEFAULT)
    b = qrencode.encode("a\nb", DEFAULT)
    assert a.modules == b.modules


def test_svg_shape():
    m = qrencode.encode("hello", DEFAULT)
    svg = qrencode.to_svg(m, margin=4)
    size = m.width + 8
    assert svg.startswith("<svg") and f'viewBox="0 0 {size} {size}"' in svg
