# 1.2 acceptance fleet shape (idea03, 2026-11-12)

Verbatim copies of `/api/school`, `/api/nextcloud`, `/api/kolibri` and
`/api/kiwix` from Pixel's read-only 1.2 acceptance run on the idea03 hub
(idea#462, https://github.com/koenswings/idea/issues/462#issuecomment-6822185925).

Shape that exposed the bug: 4 own Nextcloud copies with an ok day and
`beyondSeed` 0 for teacher and learner, plus the listed, non-hooked
`nextcloud-files-b-001` with no ok day (`setup` null). 1.2 served
`setupStatus.nextcloud` as `complete: null` with both items in `missing` AND
`unknown`; the expected verdict is `complete: false`, both in `missing`,
`unknown: []`. `school.json` is kept as served by 1.2 (the buggy output).
