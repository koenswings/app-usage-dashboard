"""Dashboard version and commit for GET /api/v1/health.

The collector runs the stock python image with ./collector bind-mounted at
/app, so a COMMIT baked into the web image never reaches this module.
`script/write-build-info.sh` writes collector/build-info.json at App Disk
bundle time (read here as /app/build-info.json). A custom collector image
can also bake /etc/idea-usage/build-info.json outside the mount.

Resolution: non-empty USAGE_DASHBOARD_COMMIT (optional override), then the
build-info JSON, then the Engine bundle directory name
`usage-dashboard-<sha>` parsed from /proc/self/mountinfo.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

APP_VERSION_DEFAULT = "1.0"
COMMIT_ENV = "USAGE_DASHBOARD_COMMIT"
VERSION_ENV = "USAGE_DASHBOARD_VERSION"
BUILD_INFO_ENV = "USAGE_DASHBOARD_BUILD_INFO"
DEFAULT_BUILD_INFO_PATHS = (
    "/etc/idea-usage/build-info.json",
    "/app/build-info.json",
)
_BUNDLE_SHA = re.compile(r"(?:^|/)usage-dashboard-([0-9a-f]{7,40})(?:/|$)", re.I)


def _nonempty(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _load_json(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _build_info_paths() -> list[str]:
    paths = []
    override = _nonempty(os.environ.get(BUILD_INFO_ENV))
    if override:
        paths.append(override)
    paths.extend(DEFAULT_BUILD_INFO_PATHS)
    return paths


def _info_from_files() -> dict[str, Any]:
    for path in _build_info_paths():
        if os.path.isfile(path):
            return _load_json(path)
    return {}


def commit_from_mountinfo(text: str | None = None) -> str | None:
    """Parse `usage-dashboard-<sha>` from mountinfo (or the given text)."""
    if text is None:
        try:
            with open("/proc/self/mountinfo", encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            return None
    match = _BUNDLE_SHA.search(text)
    return match.group(1) if match else None


def dashboard_version() -> str:
    env = _nonempty(os.environ.get(VERSION_ENV))
    if env:
        return env
    file_value = _nonempty(_info_from_files().get("version"))
    if file_value:
        return file_value
    return APP_VERSION_DEFAULT


def dashboard_commit() -> str | None:
    env = _nonempty(os.environ.get(COMMIT_ENV))
    if env:
        return env
    file_value = _nonempty(_info_from_files().get("commit"))
    if file_value:
        return file_value
    return commit_from_mountinfo()
