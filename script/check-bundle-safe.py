#!/usr/bin/env python3
"""Refuse an App bundle that could clobber live instance state on updateApp (idea#443).

agent-engine-dev UpdateApp.ts copyBundle (main 24b3d9e :133-137, #448 3198ed1
:152-156) copies EVERY top-level name of apps/<newAppId>/ over instances/<id>/
with overwrite, except .env, SHA256SUMS and .idea-*. It is not exclude-aware.
So the bundle must not ship:
  - a top-level data/ (the hub's live usage.sqlite, keys, tailscale state),
  - any path in x-app.backup.exclude or hookExclude (normalised like the
    Engine's normalizeBackupExclude: bare name -> data/<name>, a path with a
    slash or a leading dot is instance-relative), nor a parent of one,
  - a .env (copyBundle skips it, but it must never travel in a bundle).
It also checks what the Engine needs to offer and verify the bundle
(UpdateApp.ts sumsLookUsable :442-443, full sha256sum --check --strict):
SHA256SUMS exists, is non-empty, lists compose.yaml, and every bundle file is
listed. --tree checks a git checkout's tracked files instead (no SHA256SUMS).

Usage:
  script/check-bundle-safe.py <bundle dir>            # apps/<appId>/ of a built bundle
  script/check-bundle-safe.py --tree <checkout dir>   # git ls-files of a checkout
Exit 0 = safe; 1 = a FAIL line per problem; 2 = usage error.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ALWAYS_FORBIDDEN = ("data", ".env")


def normalize(raw: str) -> str:
    """Same rule as agent-engine-dev src/utils/backupExclude.ts normalizeBackupExclude."""
    p = raw.strip().strip("'\"")
    while p.startswith("./"):
        p = p[2:]
    p = p.rstrip("/")
    if "/" not in p and p != "data" and not p.startswith("."):
        p = "data/" + p
    return p


def backup_lists(compose_text: str) -> dict[str, list[str]]:
    """x-app.backup.exclude / hookExclude list items (2-space compose style, no PyYAML)."""
    out: dict[str, list[str]] = {"exclude": [], "hookExclude": []}
    in_xapp = in_backup = False
    current = None
    for line in compose_text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            in_xapp = line.startswith("x-app:")
            in_backup = False
            current = None
            continue
        if not in_xapp:
            continue
        if indent == 2:
            in_backup = line.strip() == "backup:"
            current = None
            continue
        if not in_backup:
            continue
        if indent == 4:
            key = line.strip().split(":", 1)[0]
            current = key if key in out else None
            continue
        if current and indent >= 6 and line.strip().startswith("- "):
            item = line.strip()[2:].split(" #", 1)[0].strip()
            if item:
                out[current].append(item)
    return out


def forbidden_paths(compose_text: str) -> list[str]:
    lists = backup_lists(compose_text)
    paths = set(ALWAYS_FORBIDDEN)
    for items in lists.values():
        paths.update(normalize(i) for i in items)
    return sorted(paths)


def clashes(rel: str, forbidden: list[str]) -> str | None:
    for f in forbidden:
        if rel == f or rel.startswith(f + "/") or f.startswith(rel + "/"):
            return f
    return None


SUMS_LINE = re.compile(r"^([0-9a-f]{64}) [ *](.+)$")


def check(files: list[str], compose_text: str, sums_text: str | None, prefix: str) -> list[str]:
    fails: list[str] = []
    forbidden = forbidden_paths(compose_text)
    for rel in sorted(files):
        hit = clashes(rel, forbidden)
        if hit:
            fails.append("FAIL: bundle ships %s, which would overwrite live %s in instances/<id> (copyBundle is not exclude-aware)" % (rel, hit))
    top = sorted({f.split("/", 1)[0] for f in files})
    if "data" in top:
        fails.append("FAIL: bundle has a top-level data/ tree; copyBundle would merge it over the live data/")
    if sums_text is not None:
        listed = []
        for line in sums_text.splitlines():
            m = SUMS_LINE.match(line.strip())
            if m:
                listed.append(m.group(2))
        if not listed:
            fails.append("FAIL: SHA256SUMS is empty; the Engine never offers it")
        if prefix + "compose.yaml" not in listed and "compose.yaml" not in listed:
            fails.append("FAIL: SHA256SUMS does not list compose.yaml (UpdateApp.ts sumsLookUsable)")
        listed_rel = {p[len(prefix):] if p.startswith(prefix) else p for p in listed}
        for rel in sorted(files):
            if rel != "SHA256SUMS" and rel not in listed_rel:
                fails.append("FAIL: %s is not in SHA256SUMS" % rel)
    return fails


def bundle_files(bundle: Path) -> list[str]:
    files = []
    for root, dirs, names in os.walk(bundle):
        for n in names + [d for d in dirs if (Path(root) / d).is_symlink()]:
            rel = os.path.relpath(os.path.join(root, n), bundle)
            if rel == "SHA256SUMS" or rel.startswith(".idea-"):
                continue
            files.append(rel)
        for d in dirs:
            # an empty directory still lands in instances/<id> via fs.copy
            p = Path(root) / d
            if not any(p.iterdir()):
                files.append(os.path.relpath(p, bundle))
    return files


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--tree":
        tree = Path(argv[1])
        try:
            raw = subprocess.check_output(["git", "-C", str(tree), "ls-files", "-z"])
        except (OSError, subprocess.CalledProcessError) as exc:
            print("ERROR: %s" % exc, file=sys.stderr)
            return 2
        files = [f for f in raw.decode().split("\0") if f]
        fails = check(files, (tree / "compose.yaml").read_text(encoding="utf-8"), None, "")
        label = "tree %s" % tree
    elif len(argv) == 1 and not argv[0].startswith("-"):
        bundle = Path(argv[0]).resolve()
        if not (bundle / "compose.yaml").is_file():
            print("ERROR: %s has no compose.yaml" % bundle, file=sys.stderr)
            return 2
        sums = bundle / "SHA256SUMS"
        sums_text = sums.read_text(encoding="utf-8") if sums.is_file() else ""
        prefix = "apps/%s/" % bundle.name
        fails = check(bundle_files(bundle), (bundle / "compose.yaml").read_text(encoding="utf-8"), sums_text, prefix)
        label = "bundle %s" % bundle
    else:
        print(__doc__, file=sys.stderr)
        return 2
    for f in fails:
        print(f)
    if fails:
        return 1
    print("ok: %s is safe for copyBundle (no data/, .env or exclude/hookExclude path)" % label)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
