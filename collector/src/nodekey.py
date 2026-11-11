"""Derive a Tailscale nodekey from persisted state and compare it to status JSON.

Never prints private keys. Public prefixes and match booleans only.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any, Iterable

P = 2**255 - 19
A24 = 121665
_PRIVKEY_RE = re.compile(r"^privkey:([0-9a-fA-F]{64})$")


def x25519(k_bytes: bytes, u_bytes: bytes) -> bytes:
    k = bytearray(k_bytes)
    k[0] &= 248
    k[31] &= 127
    k[31] |= 64
    n = int.from_bytes(k, "little")
    u = int.from_bytes(u_bytes, "little") % (1 << 255)
    x_1 = u
    x_2, z_2 = 1, 0
    x_3, z_3 = u, 1
    swap = 0
    for t in range(254, -1, -1):
        k_t = (n >> t) & 1
        swap ^= k_t
        if swap:
            x_2, x_3 = x_3, x_2
            z_2, z_3 = z_3, z_2
        swap = k_t
        A = (x_2 + z_2) % P
        AA = pow(A, 2, P)
        B = (x_2 - z_2) % P
        BB = pow(B, 2, P)
        E = (AA - BB) % P
        C = (x_3 + z_3) % P
        D = (x_3 - z_3) % P
        DA = (D * A) % P
        CB = (C * B) % P
        x_3 = pow((DA + CB) % P, 2, P)
        z_3 = (x_1 * pow((DA - CB) % P, 2, P)) % P
        x_2 = (AA * BB) % P
        z_2 = (E * (AA + A24 * E)) % P
    if swap:
        x_2, x_3 = x_3, x_2
        z_2, z_3 = z_3, z_2
    return ((x_2 * pow(z_2, P - 2, P)) % P).to_bytes(32, "little")


def public_from_private_hex(priv_hex: str) -> str:
    raw = bytes.fromhex(priv_hex)
    if len(raw) != 32:
        raise ValueError("private node key must be 32 bytes")
    nine = (9).to_bytes(32, "little")
    return x25519(raw, nine).hex()


def _b64d(value: str) -> bytes:
    raw = value.encode() if isinstance(value, str) else value
    pad = (-len(raw)) % 4
    return base64.b64decode(raw + b"=" * pad)


def walk_private_node_keys(obj: Any, path: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        val = obj.get("PrivateNodeKey")
        if isinstance(val, str):
            m = _PRIVKEY_RE.match(val)
            if m:
                found.append((path + ".PrivateNodeKey", m.group(1)))
        for key, child in obj.items():
            if key == "PrivateNodeKey":
                continue
            found.extend(walk_private_node_keys(child, path + "." + str(key)))
    elif isinstance(obj, list):
        for i, child in enumerate(obj):
            found.extend(walk_private_node_keys(child, "%s[%d]" % (path, i)))
    return found


def disk_nodekeys(state_path: Path) -> list[tuple[str, str]]:
    """Return (json_path, public_hex) pairs from tailscaled.state. Never returns privates."""
    outer = json.loads(state_path.read_text())
    pubs: list[tuple[str, str]] = []
    if not isinstance(outer, dict):
        return pubs
    for key, value in outer.items():
        try:
            raw = _b64d(value)
        except Exception:
            continue
        try:
            inner = json.loads(raw.decode("utf-8"))
        except Exception:
            continue
        for jpath, priv_hex in walk_private_node_keys(inner, key):
            pubs.append((jpath, public_from_private_hex(priv_hex)))
    return pubs


def normalize_public(value: str | None) -> str:
    if not value:
        return ""
    return value.split(":")[-1].lower()


def status_self_public(status: dict) -> str:
    self = status.get("Self") or {}
    return normalize_public(self.get("PublicKey"))


def compare(disk_pubs: Iterable[tuple[str, str]], status_pub: str) -> dict:
    status_norm = normalize_public(status_pub)
    disk_list = [(path, normalize_public(pub)) for path, pub in disk_pubs]
    match = bool(status_norm) and any(pub == status_norm for _, pub in disk_list)
    return {
        "disk_prefixes": [(path, pub[:16] if pub else None) for path, pub in disk_list],
        "status_prefix": status_norm[:16] if status_norm else None,
        "disk_count": len(disk_list),
        "match": match,
    }
