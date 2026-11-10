# app-usage-dashboard

IDEA App for the programme field-usage dashboard (koenswings/idea proposal merged in idea#410).

- Install **only on idea**, never on a school kit. The usage-pull key is provisioned only there.
- Services (in progress, idea#414): `tailscale` (userspace sidecar node tagged `tag:idea-hub`), `collector` (deterministic, no LLM; uplink history and E1 pulls into SQLite under `./data`), `web` (dashboard UI and read-only API).
- `web/` is the dashboard UI (Pixel, idea#415).
- `collector/` and `docs/API.md` are App Dev (Kid, idea#414).
- Never binds 80, 3333, 3334 or 8081, and never touches MilkWise.
