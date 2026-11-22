# Authoritative Documentation Index — Kid (app-usage-dashboard)

IDEA App: programme field-usage dashboard on idea (idea#414/#415).

For organization-wide documentation guidance, see [`koenswings/idea/docs/INDEX.md`](https://github.com/koenswings/idea/blob/main/docs/INDEX.md).

Update this file whenever an authoritative doc is added or significantly revised.

| Doc | Purpose |
|-----|---------|
| [API.md](./API.md) | Collector data model (idea#414): how export records land in SQLite and how they are shaped for the UI endpoints |
| [API-PIXEL-NOTES.md](./API-PIXEL-NOTES.md) | Remaining collector-side differences from Pixel `b4fa49b` / `idea-usage-api/1`, plus collector additions |
| [accounts.md](./accounts.md) | Operator accounts: only `koen`, `marco` and `justice` (U-9), house `<account>911!` seeds, password change, and unauthenticated routes |
| [packaging.md](./packaging.md) | Web-image packaging: ghcr digest pin, tar-in-bundle fallback, pin-change runbook (idea#445), and how `/health` reports `commit` |
| [runbook.md](./runbook.md) | Install and operate the dashboard on idea only: idea-hub Tailscale identity, secrets, backup hook (idea#444), restore, and known limits |
