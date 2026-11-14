"""Minimal loader for systemd-style environment files (KEY=VALUE per line).

Lets the app pick up deploy/qrencoder.env when started directly with uvicorn.
Variables already set in the process environment (e.g. by systemd's
EnvironmentFile=) take precedence.
"""

from __future__ import annotations

import os
from pathlib import Path


def parse(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        result[key] = value
    return result


def load(path: str | os.PathLike) -> None:
    p = Path(path)
    if not p.is_file():
        return
    for key, value in parse(p.read_text(encoding="utf-8")).items():
        os.environ.setdefault(key, value)
