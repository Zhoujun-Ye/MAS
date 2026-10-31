"""Configuration files, protected .env secrets and stable digests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path = ROOT / ".env") -> None:
    """Export KEY=VALUE lines without overriding the environment; never logs values."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _merge(base: dict, extra: dict) -> dict:
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(*paths: str | Path) -> dict:
    """Merge YAML files left to right: nested mappings merge, other values replace."""
    merged: dict = {}
    for path in paths:
        merged = _merge(merged, yaml.safe_load(Path(path).read_text()) or {})
    return merged


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(obj) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()[:16]


SOURCE_PACKAGES = ("harness", "benchmarks", "analysis", "scripts", "configs")
NOT_SOURCE = {"upstream", "assets", "__pycache__"}  # pinned checkouts and prepared inputs


def source_digest() -> str:
    """Hash of our own source, recorded with every output directory and result."""
    paths = []
    for package in SOURCE_PACKAGES:
        for folder, dirs, files in os.walk(ROOT / package):
            dirs[:] = [d for d in dirs if d not in NOT_SOURCE]
            paths += [Path(folder) / name for name in files if name.endswith((".py", ".yaml", ".json"))]
    h = hashlib.sha256()
    for path in sorted(paths):
        h.update(str(path.relative_to(ROOT)).encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:16]
