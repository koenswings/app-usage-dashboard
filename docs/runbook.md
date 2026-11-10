# Runbook — field usage dashboard (idea only)

## Install

Install onto idea's **system disk** with `installApp`. Do not install on a school kit. Proof installs go on idea03 or idea04 first, never on golden idea01 and never on idea until Koen says so.

The Engine assigns `${port}` in the instance `.env`. The web entrypoint refuses 80, 3333, 3334 and 8081.

## Secrets

| Path | What | Backup |
|---|---|---|
| `./data/keys/pull_key` | usage-pull private key, mode 0600 | idea's encrypted Borg only (`x-app.backup.exclude: keys`) |
| `./data/tailscale/` | sidecar Tailscale state | idea's encrypted Borg only (`exclude: tailscale`) |
| instance `.env` `TS_AUTHKEY` | tagged, non-ephemeral auth key for `tag:idea-hub` | Engine instance env (not this repo) |
| `IDEA_USAGE_ADMIN_PASSWORD` | operator login (default convention `admin911!` if unset) | instance env |

Atlas installs the matching public key on each kit as helper v7 (`/etc/ssh/idea_usage_keys/pi`), pinned `from=` the sidecar's own Tailscale IPv4, forced command `/usr/local/sbin/idea-usage-export`. Never paste a key into chat or git.

If sidecar state is lost, Koen re-registers the node and sets its previous 100.x IPv4 in the Tailscale admin console so the kits' `from=` lines keep working (idea#375).

## Registry

`./data/registry.json`:

```json
{
  "kits": [
    {
      "engine": "happy-zebra",
      "tailscaleName": "happy-zebra",
      "school": "Nharira",
      "deploymentId": "dep-nharira",
      "timezone": "Africa/Harare",
      "note": "own apps + Demo"
    }
  ]
}
```

`timezone` is optional IANA. Without it the API labels ticks as `kit local time (UTC±offset)` from the latest presence sample.

## Restore

1. Restore `./data/usage.sqlite` from a `VACUUM INTO` snapshot under `./data/backup/` or from idea's Borg copy of App data.
2. Restore `./data/keys/pull_key` and `./data/tailscale/` only from idea's encrypted Borg.
3. Restart the App. The collector opens SQLite in WAL mode and keeps serving the last stored data if Tailscale is down.
