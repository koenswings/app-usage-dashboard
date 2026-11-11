# Programme dashboard operator accounts

Only Koen and Marco may open the programme usage dashboard (U-9). The App
provisions exactly two operator accounts, `koen` and `marco`. There is no
`admin` operator and no anonymous access to programme data.

House password convention (same as Nextcloud and Kolibri): `<account>911!`.

| Account | First-run seed (compose default) |
|---|---|
| `koen` | `koen911!` |
| `marco` | `marco911!` |

## How they are created

On first start the collector reads the seed values from the instance
environment — the same pattern Nextcloud uses for `NEXTCLOUD_ADMIN_PASSWORD`:

```yaml
- IDEA_USAGE_KOEN_PASSWORD=${IDEA_USAGE_KOEN_PASSWORD:-koen911!}
- IDEA_USAGE_MARCO_PASSWORD=${IDEA_USAGE_MARCO_PASSWORD:-marco911!}
```

Those strings are hashed with salted PBKDF2-SHA256 and written to
`./data/operators.json` (mode 0640, schema `idea-usage-operators/1`). The
plaintext seeds are never written to that file and never printed in collector
logs.

Later starts keep the stored hashes. Changing a password (below) updates the
file; a container restart does **not** reset the password from compose/env.
Override the seed env vars only when you want a *new* install to start with
something other than the house defaults.

If a seed env var is missing when that account has no stored hash yet, the
collector refuses to start and names the variable (not the password) in the
error.

## Changing a password

`PUT /api/v1/session/password` (operator session required):

```json
{ "currentPassword": "…", "newPassword": "…" }
```

`newPassword` must be at least 8 characters. A wrong `currentPassword` is
`401`; a short new password is `400`. The current session cookie stays valid
until it expires (12 hours). The other operator's password is unchanged.

## Existing deployments

This replaces the earlier single `admin` account (`IDEA_USAGE_ADMIN_PASSWORD`,
default `admin911!`) and the optional `IDEA_USAGE_OPERATORS` / operators-file
list of extra users.

- A fresh install, or an existing data directory with no operators file, gets
  `koen` and `marco` from the compose defaults (or from instance env if Atlas
  set them). `admin` can no longer sign in.
- If `./data/operators.json` (or `IDEA_USAGE_OPERATORS_FILE`) already exists,
  hashes for `koen` and `marco` are kept. Any other username in that file —
  including `admin` — is dropped on startup. A leftover plaintext secret for
  `koen` or `marco` is rehashed in place.
- `IDEA_USAGE_ADMIN_PASSWORD` and `IDEA_USAGE_OPERATORS` are ignored. They do
  not create accounts.
- Existing `admin` session cookies stop working.

Atlas should drop `IDEA_USAGE_ADMIN_PASSWORD` from any instance `.env` it
still writes. Setting the two `IDEA_USAGE_*_PASSWORD` vars is optional: the
compose defaults match the house convention.

## What is reachable without a login

- `GET /api/v1/health` — Engine healthCheck (no database).
- `GET /api/v1/session` — returns `{authenticated: false}` so the login page
  can ask.
- `POST /api/v1/session` — sign in.
- `DELETE /api/v1/session` — sign out (clears the cookie).

Every other `/api/v1` path requires the `idea_usage_session` cookie. The web
container serves the login page itself without a session (otherwise nobody
could sign in). The collector listens on `0.0.0.0:8080` in the Tailscale
sidecar network namespace, so a tailnet peer that can reach that port talks
to the same HTTP API; it does not bypass the session.

See `docs/API.md` and `docs/runbook.md`.
