"""Collector identity guard for the idea-hub sidecar.

Ride out a short LocalAPI blip (NoState, Starting, or a zeroed PublicKey)
that happens when containerboot restarts tailscaled. Fail closed immediately
on a real nodekey change, NeedsLogin / logged-out, any AuthURL, a state-file
inode or size change (regen), or a blip that outlasts the configured bound.

Never logs private keys or AuthURL values — prefixes and booleans only.
The collector does not mount ./data/tailscale, so the inode watch is optional
and stays silent when the state file is not visible.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from .nodekey import normalize_public, status_self_public

# Wall-clock bound for a NoState / Starting / zeroed-key blip.
DEFAULT_IDENTITY_BLIP_S = 15
# Consecutive blip polls allowed; 0 disables the poll bound (time only).
DEFAULT_IDENTITY_BLIP_POLLS = 0
# How often to re-poll LocalAPI while a blip is in flight.
DEFAULT_IDENTITY_BLIP_POLL_S = 1

BLIP_STATES = frozenset({"NoState", "Starting"})
GAP_IDENTITY = "sidecar-identity-failed"
GAP_LOGGED_OUT = "sidecar-logged-out"


def env_blip_s() -> int:
    raw = os.environ.get("IDENTITY_BLIP_S")
    return int(raw) if raw else DEFAULT_IDENTITY_BLIP_S


def env_blip_polls() -> int:
    raw = os.environ.get("IDENTITY_BLIP_POLLS")
    if raw is None or raw == "":
        return DEFAULT_IDENTITY_BLIP_POLLS
    return int(raw)


def env_blip_poll_s() -> int:
    raw = os.environ.get("IDENTITY_BLIP_POLL_S")
    return int(raw) if raw else DEFAULT_IDENTITY_BLIP_POLL_S


def env_state_file() -> str | None:
    override = os.environ.get("TS_STATE_FILE")
    if override:
        return override
    directory = os.environ.get("TS_STATE_DIR")
    if directory:
        return os.path.join(directory, "tailscaled.state")
    # Default path inside the sidecar. The collector's /data/tailscale is a
    # hiding tmpfs, so this is usually missing there and the watch is skipped.
    return "/var/lib/tailscale/tailscaled.state"



def _backend_state(status: dict[str, Any] | None) -> str:
    if not status:
        return ""
    return str(status.get("BackendState") or status.get("backendState") or "")


def _is_logged_out(status: dict[str, Any] | None) -> bool:
    if not status:
        return False
    if _backend_state(status) == "NeedsLogin":
        return True
    if status.get("LoggedOut") is True:
        return True
    return False


def is_zero_public(pub: str | None) -> bool:
    hexpart = normalize_public(pub)
    return (not hexpart) or set(hexpart) <= {"0"}


def status_auth_url(status: dict[str, Any] | None) -> bool:
    if not status:
        return False
    if status.get("AuthURL"):
        return True
    self = status.get("Self") or {}
    return bool(self.get("AuthURL"))


def state_stamp(path: str | None) -> tuple[int, int] | None:
    """(inode, size) for the sidecar state file, or None if it cannot be stat'd."""
    if not path:
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_ino, st.st_size)


@dataclass
class IdentityState:
    """Mutable guard memory across loop ticks."""

    known_key: str = ""  # normalized non-zero public hex
    stamp: tuple[int, int] | None = None
    blip_since: float | None = None
    blip_polls: int = 0
    failed: bool = False
    reason: str | None = None
    log: str | None = None
    # Set on the tick that first fails closed, then stays set.
    gap_reason: str | None = None

    def reset_blip(self) -> None:
        self.blip_since = None
        self.blip_polls = 0


@dataclass
class IdentityDecision:
    fail_closed: bool
    in_blip: bool
    reason: str | None
    log: str | None
    gap_reason: str | None
    # Prefix only, never a full key.
    known_prefix: str | None = None
    seen_prefix: str | None = None


def _prefix(pub: str) -> str | None:
    return pub[:16] if pub else None


def decide_identity(
    status: dict[str, Any] | None,
    error: str | None,
    now: float,
    state: IdentityState,
    blip_s: int = DEFAULT_IDENTITY_BLIP_S,
    blip_polls: int = DEFAULT_IDENTITY_BLIP_POLLS,
    stamp: tuple[int, int] | None = None,
) -> IdentityDecision:
    """Pure identity policy for one loop tick.

    ``stamp`` is the current (inode, size) of the state file, or None when
    the file is not visible. A first-time None is ignored (the collector
    hides ./data/tailscale behind a tmpfs). A None after a stamp was
    recorded is a disappearance and fails closed.
    """
    if state.failed:
        return IdentityDecision(
            fail_closed=True,
            in_blip=False,
            reason=state.reason,
            log=None,
            gap_reason=state.gap_reason,
            known_prefix=_prefix(state.known_key),
        )

    def fail(reason: str, log: str, gap: str) -> IdentityDecision:
        state.failed = True
        state.reason = reason
        state.log = log
        state.gap_reason = gap
        state.reset_blip()
        return IdentityDecision(
            fail_closed=True,
            in_blip=False,
            reason=reason,
            log=log,
            gap_reason=gap,
            known_prefix=_prefix(state.known_key),
            seen_prefix=_prefix(status_self_public(status) if status else ""),
        )

    # Inode / size watch: a change or a disappearance after we have a stamp
    # is treated as a regen / state replacement. Do this before trusting status.
    if stamp is None and state.stamp is not None:
        return fail(
            "state-missing",
            "sidecar state file disappeared after it had been observed; failing closed",
            GAP_IDENTITY,
        )
    if stamp is not None and state.stamp is None:
        state.stamp = stamp
    elif stamp is not None and state.stamp is not None and stamp != state.stamp:
        inode_changed = stamp[0] != state.stamp[0]
        size_changed = stamp[1] != state.stamp[1]
        detail = []
        if inode_changed:
            detail.append("inode")
        if size_changed:
            detail.append("size")
        return fail(
            "state-changed",
            "sidecar state file %s changed; failing closed (possible regen)" % (
                " and ".join(detail) or "identity stamp"
            ),
            GAP_IDENTITY,
        )

    # Unreachable LocalAPI is a watchdog matter, not an identity verdict.
    if status is None or error:
        state.reset_blip()
        return IdentityDecision(
            fail_closed=False,
            in_blip=False,
            reason=None,
            log=None,
            gap_reason=None,
            known_prefix=_prefix(state.known_key),
        )

    if _is_logged_out(status):
        return fail(
            "logged-out",
            "sidecar LocalAPI reports BackendState=%s (logged out); failing closed — not restarting and not joining"
            % (_backend_state(status) or "logged-out"),
            GAP_LOGGED_OUT,
        )

    if status_auth_url(status):
        return fail(
            "auth-url",
            "sidecar LocalAPI reports a non-empty AuthURL; failing closed — not opening a login URL and not joining",
            GAP_IDENTITY,
        )

    pub = status_self_public(status)
    zero = is_zero_public(pub)
    if pub and not zero and state.known_key and pub != state.known_key:
        return fail(
            "nodekey-changed",
            "sidecar PublicKey changed from %s… to %s… (non-zero); failing closed"
            % (_prefix(state.known_key), _prefix(pub)),
            GAP_IDENTITY,
        )

    st = _backend_state(status)
    blip_like = (st in BLIP_STATES) or (zero and st != "Running") or (
        zero and st == "Running" and bool(state.known_key)
    )
    if blip_like:
        if state.blip_since is None:
            state.blip_since = now
        state.blip_polls += 1
        elapsed = now - state.blip_since
        over_time = blip_s > 0 and elapsed > blip_s
        over_polls = blip_polls > 0 and state.blip_polls > blip_polls
        if over_time or over_polls:
            bound = "polls" if over_polls and not over_time else "seconds"
            return fail(
                "blip-timeout",
                "sidecar identity blip (BackendState=%s, PublicKey %s) lasted %ss / %s polls; failing closed"
                % (
                    st or "unknown",
                    "zeroed" if zero else (_prefix(pub) or "empty"),
                    int(elapsed),
                    state.blip_polls,
                ),
                GAP_IDENTITY,
            )
        return IdentityDecision(
            fail_closed=False,
            in_blip=True,
            reason=None,
            log=(
                "sidecar identity blip BackendState=%s PublicKey=%s; riding it out "
                "(%ss / %s polls, bound %ss / %s polls)"
                % (
                    st or "unknown",
                    "zeroed" if zero else (_prefix(pub) or "empty"),
                    int(elapsed),
                    state.blip_polls,
                    blip_s,
                    blip_polls or "off",
                )
            ),
            gap_reason=None,
            known_prefix=_prefix(state.known_key),
            seen_prefix=_prefix(pub) if pub and not zero else None,
        )

    # Healthy / non-blip status. Remember the first non-zero key.
    if pub and not zero:
        if not state.known_key:
            state.known_key = pub
        state.reset_blip()
        return IdentityDecision(
            fail_closed=False,
            in_blip=False,
            reason=None,
            log=None,
            gap_reason=None,
            known_prefix=_prefix(state.known_key),
            seen_prefix=_prefix(pub),
        )

    state.reset_blip()
    return IdentityDecision(
        fail_closed=False,
        in_blip=False,
        reason=None,
        log=None,
        gap_reason=None,
        known_prefix=_prefix(state.known_key),
        seen_prefix=_prefix(pub) if pub else None,
    )


def observe_stamp(path: str | None, stat_fn: Callable[[str | None], tuple[int, int] | None] | None = None):
    """Return (stamp, unavailable). unavailable is True when the file is not visible."""
    fn = stat_fn or state_stamp
    stamp = fn(path)
    if path and stamp is None:
        # Distinguish "path configured but missing after a prior stamp" vs
        # "never visible (tmpfs hide)". The policy function uses state.stamp
        # for disappearance; callers pass stamp_unavailable when the path is
        # unset or was never readable on the first attempts.
        return None, True
    if not path:
        return None, True
    return stamp, False
