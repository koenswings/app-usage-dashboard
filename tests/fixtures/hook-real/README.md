# Real hook output (contract fixtures, idea#462)

Captured from the shipped App hooks, not hand-written to the PR #410 §7.6 sketch.
The sketch names (`learnersEnrolled`, `signins.*.users`) never came from a real
hook; tests built on them hid idea#462 items 2 and 3.

| File | Source | Hook |
|---|---|---|
| `kolibri-0.19.5-engine-day.json` | idea#413 acceptance run 2 on idea03, Engine-stored day file (Engine adds `engine`, `instance`, `name`, `listed`, `clock`, `collectedAt`, `hookStatus`) | app-kolibri `hooks/usage.sh` (1.2-0.19.5, `d216f7f`) |
| `kolibri-0.15.5-hook-stdout.json` | same run, raw hook stdout on a Kolibri 0.15.5 fixture (demo facility) | same hook |
| `nextcloud-31-engine-day.json` | idea#431 dashboard e2e on idea03, Engine-stored day file | app-nextcloud `hooks/usage.sh` (1.4-31.0.1, `bdcbd24`) |
| `kiwix-3.8.2-engine-day.json` | idea#413 acceptance run 2 | app-kiwix `hooks/usage.sh` (1.2-3.8.2, `553e271`) |

Test data only (instance names `i413-*`, `nextcloud-i431`; no school or person data).
