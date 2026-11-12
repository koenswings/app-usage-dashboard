"""idea#443: script/release/i443-update-checks.sh pre/post on a fixture idea03.

No Docker on the box: docker, curl and sudo are stubs on PATH that read
<fixture>/stub/*. Every absolute path the script reads is prefixed with the
fixture dir (--fixture). The fixture holds fake secrets so the tests can prove
they never reach the evidence dir.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPT = REPO / "script" / "release" / "i443-update-checks.sh"
sys.path.insert(0, str(HERE))
from test_verify_service_tar import Image, write_tar  # noqa: E402

INST = "usage-dashboard-8fhwrslsrq78xtswed4"
APP = "usage-dashboard-1.1"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
NODEKEY = "nodekey:1382c2ea" + "0" * 48
SECRET_ENV = "IDEA_USAGE_KOEN_PASSWORD=fixture-secret-pw\nTS_AUTHKEY=tskey-auth-fixture\n"
SECRET_PRIV = "privkey:fixture-private-key-material"

DOCKER_STUB = r"""#!/usr/bin/env bash
S="$I443_FX/stub"
case "$1" in
  ps) cat "$S/ps" ;;
  inspect)
    fmt=$3; id=$4; f="$S/inspect.$id"; [ -f "$f" ] || exit 1
    if [[ "$fmt" == *State.Status* ]]; then cat "$f"; else IFS='|' read -r a _ _ _ _ svc < "$f"; echo "$a|$svc"; fi ;;
  exec) cat "$S/status.json" ;;
  port) echo "0.0.0.0:18999" ;;
  image) grep -qxF "$5" "$S/local-images" 2>/dev/null ;;
  *) echo "docker stub: unexpected $*" >&2; exit 9 ;;
esac
"""
CURL_STUB = '#!/usr/bin/env bash\ncat "$I443_FX/stub/health.json"\n'
SUDO_STUB = '#!/usr/bin/env bash\n[ "$1 $3" = "-n version" ] && cat "$I443_FX/stub/helper" || exit 1\n'



# docker inspect --format uses Go text/template with missingkey=error. A
# container with no healthcheck has no State.Health key; {{if .State.Health}}
# then fails with "map has no entry for key Health".
_GO_INSPECT_TMPL = r"""package main
import (
  "encoding/json"
  "fmt"
  "os"
  "text/template"
)
func main() {
  tmpl, err := template.New("f").Option("missingkey=error").Parse(os.Args[1])
  if err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(2) }
  var data any
  if err := json.NewDecoder(os.Stdin).Decode(&data); err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(2) }
  if err := tmpl.Execute(os.Stdout, data); err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
}
"""


def containers_check_format():
    text = SCRIPT.read_text(encoding="utf-8")
    # the P04/Q-shared inspect format inside containers_check
    key = "inspect --format '"
    i = text.find(key)
    if i < 0:
        raise AssertionError("containers_check inspect format not found")
    i += len(key)
    j = text.find("'", i)
    if j < 0:
        raise AssertionError("unclosed inspect format")
    return text[i:j]


def apply_inspect_format(fmt, obj):
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "apply.go"
        src.write_text(_GO_INSPECT_TMPL)
        r = subprocess.run(
            ["go", "run", str(src), fmt],
            input=json.dumps(obj),
            text=True,
            capture_output=True,
            cwd=tmp,
        )
    return r


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def compose(version, images):
    return """x-app:
  name: usage-dashboard
  version: "%s"
  backup:
    method: hook
    exclude:
      - keys
      - tailscale
      - tailscale-run
      - data/backup/daily
    hookExclude:
      - usage.sqlite
services:
  tailscale:
    image: %s
    labels:
      x-app-version: "%s"
  collector:
    image: %s
    labels:
      x-app-version: "%s"
  web:
    image: %s
    labels:
      x-app-version: "%s"
""" % (version, images["tailscale"], version, images["collector"], version, images["web"], version)


class Fixture:
    def __init__(self, root: Path):
        self.root = root
        self.fx = root / "fx"
        fx = self.fx
        self.stub = fx / "stub"
        self.bin = root / "bin"
        for d in (self.stub, self.bin, fx / "apps", fx / "services", fx / "disks" / "sdb1",
                  fx / "var/lib/idea/usage", fx / "home/pi/kid-evidence"):
            d.mkdir(parents=True, exist_ok=True)
        for name, body in (("docker", DOCKER_STUB), ("curl", CURL_STUB), ("sudo", SUDO_STUB)):
            p = self.bin / name
            p.write_text(body)
            p.chmod(0o755)
        # service images: fake OCI tars whose index digest is the compose pin
        repos = {"tailscale": "tailscale/tailscale:v1.88.3", "collector": "python:3.12-slim-bookworm",
                 "web": "ghcr.io/koenswings/usage-dashboard-web:1.0"}
        self.images = {}
        for svc, rt in repos.items():
            img = Image(svc)
            self.images[svc] = "%s@%s" % (rt, img.index)
            tar_name = rt.replace("/", "_") + ".tar"
            write_tar(fx / "services" / tar_name, [img.entry(rt)], [img], [rt])
        # live instance (unversioned master, as today)
        inst = fx / "instances" / INST
        (inst / "data/tailscale").mkdir(parents=True)
        (inst / "data/keys").mkdir(parents=True)
        (inst / "data/tailscale/tailscaled.state").write_text('{"_machinekey":"%s"}' % SECRET_PRIV)
        (inst / "data/keys/pull_key").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nfixture\n")
        (inst / ".env").write_text(SECRET_ENV)
        (inst / "compose.yaml").write_text(compose("69d40e913146ef5937fb89d8a4b4f64c217c9205", self.images))
        (fx / "apps" / "usage-dashboard-69d40e913146ef5937fb89d8a4b4f64c217c9205").mkdir()
        (fx / "var/lib/idea/usage/settings.json").write_text('{"usageMonitoring":"on"}\n')
        (fx / "disks/sdb1/BACKUP.yaml").write_text(
            "mode: on-demand\nlinks:\n  - instanceId: %s\n    lastBackup: 1000\n" % INST)
        # Engine checkout
        eng = fx / "home/pi/idea/agents/agent-engine-dev"
        eng.mkdir(parents=True)
        (eng / "package.json").write_text('{\n  "name": "engine",\n  "version": "1.2.3",\n}\n')
        git = ["git", "-C", str(eng), "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q", str(eng)], check=True)
        subprocess.run(git + ["add", "."], check=True)
        subprocess.run(git + ["commit", "-qm", "engine"], check=True)
        self.engine_head = subprocess.check_output(["git", "-C", str(eng), "rev-parse", "HEAD"], text=True).strip()
        # stick
        self.stick = fx / "disks" / "sdc1"
        b = self.stick / "apps" / APP
        (b / "collector/src").mkdir(parents=True)
        (self.stick / "META.yaml").write_text(
            "diskId: i443-stick\nisHardwareId: false\ndiskName: usage-dashboard 1.1\ncreated: 1762905600000\nlastDocked: 1762905600000\n")
        (b / "compose.yaml").write_text(compose("1.1", self.images))
        (b / "collector/src/main.py").write_text("print('hi')\n")
        (b / "collector/build-info.json").write_text('{"version": "1.1", "commit": "%s"}\n' % COMMIT)
        self.write_sums()
        self.tag_sha = sha256(b / "compose.yaml")
        # docker state
        (self.stub / "ps").write_text("aaa\nbbb\nccc\n")
        for cid, svc, img in (("aaa", "tailscale", "ts"), ("bbb", "collector", "py"), ("ccc", "web", "web")):
            health = "none" if svc == "collector" else "healthy"
            (self.stub / ("inspect." + cid)).write_text("%s%s|/%s|%s|running|%s|%s\n" % (cid, "0" * 61, svc, img, health, svc))
        self.set_status("Running", NODEKEY)
        self.set_health("1.0", None)
        (self.stub / "helper").write_text("idea-app-data 9\n")
        (self.stub / "local-images").write_text("".join(
            "%s@%s\n" % (r.split("@")[0].rsplit(":", 1)[0], r.split("@")[1]) for r in self.images.values()))

    def write_sums(self):
        root = self.stick
        bdir = root / "apps" / APP
        lines = []
        for p in sorted(bdir.rglob("*")):
            if p.is_file() and p.name != "SHA256SUMS":
                lines.append("%s  %s" % (sha256(p), p.relative_to(bdir).as_posix()))
        (bdir / "SHA256SUMS").write_text("\n".join(lines) + "\n")
        # Isolated-tree disk-root SHA256SUMS. sha256sum --check only verifies
        # listed paths; unlisted top-level Disk B content is not a failure.
        root_lines = []
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if rel == "SHA256SUMS":
                continue
            if rel.startswith("apps/") or rel.startswith("services/"):
                root_lines.append("%s  %s" % (sha256(p), rel))
        if root_lines:
            (root / "SHA256SUMS").write_text("\n".join(root_lines) + "\n")

    def set_status(self, state, pub):
        (self.stub / "status.json").write_text(json.dumps(
            {"BackendState": state, "Self": {"PublicKey": pub, "PrivateKey": SECRET_PRIV, "HostName": "idea-hub"}}))

    def set_health(self, version, commit):
        (self.stub / "health.json").write_text(json.dumps({"ok": True, "schema": 1, "version": version, "commit": commit}))

    def apply_update(self):
        """What a passing updateApp leaves behind (Swap + snapshot without identity)."""
        fx = self.fx
        b = self.stick / "apps" / APP
        dst = fx / "apps" / APP
        shutil.copytree(b, dst)
        (dst / "SHA256SUMS").unlink()  # copyBundle skips it
        inst = fx / "instances" / INST
        shutil.copy(b / "compose.yaml", inst / "compose.yaml")
        snap = fx / ".pre-update" / INST
        (snap / "data/data/backup").mkdir(parents=True)
        (snap / "data/compose.yaml").write_text("old\n")
        (snap / "COMPLETE").write_text("")
        self.set_health("1.1", COMMIT)

    def run(self, *args):
        env = dict(os.environ, I443_FX=str(self.fx), PATH="%s:%s" % (self.bin, os.environ["PATH"]))
        return subprocess.run(["bash", str(SCRIPT), *args, "--fixture", str(self.fx)],
                              capture_output=True, text=True, env=env)

    def pre(self, *extra):
        return self.run("pre", "--stick", "/disks/sdc1", "--out", "/home/pi/kid-evidence/pre", *extra)

    def post(self, *extra):
        return self.run("post", "--pre", str(self.fx / "home/pi/kid-evidence/pre"), "--stick", "/disks/sdc1",
                        "--expect-commit", COMMIT, "--tag-compose-sha256", self.tag_sha,
                        "--out", "/home/pi/kid-evidence/post", *extra)


class UpdateChecksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Fixture(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def line(self, out, check_id):
        for ln in out.splitlines():
            parts = ln.split(" ", 2)
            if len(parts) > 1 and parts[1] == check_id:
                return ln
        self.fail("no %s line in:\n%s" % (check_id, out))

    def assert_no_secrets(self, out_dir: Path, stdout: str):
        blob = stdout
        for p in out_dir.rglob("*"):
            if p.is_file():
                blob += p.read_text(errors="replace")
        for s in ("fixture-secret-pw", "tskey-auth-fixture", "fixture-private-key-material", "OPENSSH PRIVATE KEY"):
            self.assertNotIn(s, blob)

    def test_pre_passes_and_records_baseline(self):
        r = self.f.pre("--require-engine-commit", self.f.engine_head, "--tag-compose-sha256", self.f.tag_sha)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for cid in ("P01", "P02", "P04", "P05", "P06", "P07", "P08", "P09", "P10", "P11", "P12", "P13", "P14", "P15", "P99"):
            self.assertTrue(self.line(r.stdout, cid).startswith("PASS"), self.line(r.stdout, cid))
        self.assertIn("usage-dashboard-69d40e91", self.line(r.stdout, "P03"))
        self.assertIn("nodekey:1382c2ea", self.line(r.stdout, "P05"))
        out = self.f.fx / "home/pi/kid-evidence/pre"
        base = (out / "baseline.env").read_text()
        self.assertIn("nodekey_prefix=nodekey:1382c2ea\n", base)
        self.assertIn("backend_state=Running\n", base)
        self.assertIn("usage_monitoring=on\n", base)
        self.assertRegex(base, r"tailscale_inode=\d+\n")
        self.assertIn("env_hash=sha256:", base)
        self.assert_no_secrets(out, r.stdout)

    def test_pre_only_writes_its_out_dir(self):
        before = sorted(p for p in self.f.fx.rglob("*") if "kid-evidence" not in p.parts)
        self.f.pre()
        after = sorted(p for p in self.f.fx.rglob("*") if "kid-evidence" not in p.parts)
        self.assertEqual(before, after)

    def test_dry_run_writes_nothing(self):
        r = self.f.run("pre", "--stick", "/disks/sdc1", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DRY RUN", r.stdout)
        self.assertEqual(list((self.f.fx / "home/pi/kid-evidence").iterdir()), [])

    def test_out_outside_evidence_root_refused(self):
        r = self.f.run("pre", "--stick", "/disks/sdc1", "--out", "/tmp/elsewhere")
        self.assertEqual(r.returncode, 2)
        self.assertIn("kid-evidence", r.stderr)

    def test_existing_out_refused(self):
        self.f.pre()
        r = self.f.pre()
        self.assertEqual(r.returncode, 2)

    def test_pre_fails_on_missing_engine_commit_and_old_helper(self):
        (self.f.stub / "helper").write_text("idea-app-data 8\n")
        r = self.f.pre("--require-engine-commit", "f" * 40)
        self.assertEqual(r.returncode, 1)
        self.assertTrue(self.line(r.stdout, "P01").startswith("FAIL"))
        self.assertTrue(self.line(r.stdout, "P02").startswith("FAIL"))

    def test_pre_fails_when_image_neither_local_nor_match(self):
        (self.f.stub / "local-images").write_text("")
        tar = self.f.fx / "services" / "python:3.12-slim-bookworm.tar"
        tar.rename(tar.with_suffix(".moved"))
        r = self.f.pre()
        self.assertEqual(r.returncode, 1)
        p12 = self.line(r.stdout, "P12")
        self.assertTrue(p12.startswith("FAIL"), p12)
        self.assertIn("python", p12)
        self.assertTrue(self.line(r.stdout, "P11").startswith("FAIL"))

    def test_pre_passes_p12_when_local_even_without_tar(self):
        tar = self.f.fx / "services" / "python:3.12-slim-bookworm.tar"
        tar.rename(tar.with_suffix(".moved"))
        r = self.f.pre()
        self.assertTrue(self.line(r.stdout, "P12").startswith("PASS"), r.stdout)

    def test_pre_fails_usage_off_and_not_running(self):
        (self.f.fx / "var/lib/idea/usage/settings.json").write_text('{"usageMonitoring":"off"}')
        self.f.set_status("NeedsLogin", NODEKEY)
        r = self.f.pre()
        self.assertTrue(self.line(r.stdout, "P08").startswith("FAIL"))
        self.assertTrue(self.line(r.stdout, "P05").startswith("FAIL"))

    def test_pre_fails_stick_without_meta_or_with_data_dir(self):
        (self.f.stick / "META.yaml").unlink()
        b = self.f.stick / "apps" / APP
        (b / "data/tailscale").mkdir(parents=True)
        (b / "data/tailscale/x").write_text("x")
        self.f.write_sums()
        r = self.f.pre()
        p13 = self.line(r.stdout, "P13")
        self.assertTrue(p13.startswith("FAIL"), p13)
        self.assertIn("META.yaml-missing", p13)

    def test_pre_fails_on_tampered_stick_and_wrong_tag(self):
        (self.f.stick / "apps" / APP / "collector/src/main.py").write_text("tampered\n")
        r = self.f.pre("--tag-compose-sha256", "0" * 64)
        self.assertTrue(self.line(r.stdout, "P13").startswith("FAIL"))
        self.assertTrue(self.line(r.stdout, "P14").startswith("FAIL"))

    def test_backup_age_skipped_without_backup_time(self):
        r = self.f.pre("--max-backup-age-s", "3600")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.line(r.stdout, "P16"), "INFO P16 backup-age: skipped: supply --backup-time")

    def test_backup_time_epoch_ms_and_iso(self):
        import time
        now_ms = int(time.time() * 1000)
        r = self.f.pre("--backup-time", str(now_ms - 600_000), "--max-backup-age-s", "3600")
        p16 = self.line(r.stdout, "P16")
        self.assertTrue(p16.startswith("INFO P16 backup-age: 6"), p16)
        iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ms / 1000 - 7200))
        r2 = Fixture(Path(self.tmp.name) / "b").pre("--backup-time", iso, "--max-backup-age-s", "3600")
        self.assertEqual(r2.returncode, 1)
        self.assertTrue(self.line(r2.stdout, "P16").startswith("FAIL"), r2.stdout)

    def test_bad_backup_time_is_usage_error(self):
        r = self.f.pre("--backup-time", "yesterday")
        self.assertEqual(r.returncode, 2)

    def test_never_reads_under_disks_except_stick(self):
        # Disk B in the fixture holds a BACKUP.yaml and is made unreadable; nothing may
        # notice it, and nothing names it.
        sdb1 = self.f.fx / "disks" / "sdb1"
        (sdb1 / "BACKUP.yaml").write_text("links:\n  - instanceId: %s\n    lastBackup: 1\n" % INST)
        sdb1.chmod(0)
        try:
            r = self.f.pre()
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.f.apply_update()
            r2 = self.f.post()
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            d = self.f.run("pre", "--stick", "/disks/sdc1", "--dry-run")
        finally:
            sdb1.chmod(0o755)
        for out in (r.stdout + r.stderr, r2.stdout + r2.stderr, d.stdout):
            self.assertNotIn("sdb1", out)
            self.assertNotIn("BACKUP.yaml", out)
        # static: the only /disks mention in code is the --stick help/guard text
        code = [ln for ln in SCRIPT.read_text().splitlines() if not ln.lstrip().startswith("#")]
        hits = [ln for ln in code if "/disks" in ln]
        self.assertTrue(all("usage_err" in ln or "/disks|/disks/*" in ln for ln in hits), hits)

    def test_other_paths_under_disks_refused(self):
        for args in (("--snapshot-dir", "/disks/sdb1/.pre-update/x"), ("--engine-dir", "/disks/sdb1/e")):
            with self.subTest(args=args):
                r = self.f.run("pre", "--stick", "/disks/sdc1", *args)
                self.assertEqual(r.returncode, 2)
                self.assertIn("under /disks/", r.stderr)

    def test_post_passes_after_update(self):
        self.assertEqual(self.f.pre().returncode, 0)
        self.f.apply_update()
        r = self.f.post()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for cid in ("Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07", "Q08", "Q09", "Q10", "Q11", "Q12", "P99"):
            self.assertTrue(self.line(r.stdout, cid).startswith("PASS"), self.line(r.stdout, cid))
        self.assert_no_secrets(self.f.fx / "home/pi/kid-evidence/post", r.stdout)

    def test_post_fails_on_identity_change(self):
        self.f.pre()
        self.f.apply_update()
        self.f.set_status("Running", "nodekey:deadbeef" + "0" * 48)
        ts = self.f.fx / "instances" / INST / "data/tailscale"
        ts.rename(ts.with_name("tailscale-old"))
        ts.mkdir()
        r = self.f.post()
        self.assertEqual(r.returncode, 1)
        self.assertTrue(self.line(r.stdout, "Q03").startswith("FAIL"))
        self.assertTrue(self.line(r.stdout, "Q04").startswith("FAIL"))

    def test_post_fails_on_version_commit_and_instanceof(self):
        self.f.pre()
        self.f.apply_update()
        self.f.set_health("1.1", None)
        (self.f.fx / "instances" / INST / "compose.yaml").write_text(
            compose("69d40e913146ef5937fb89d8a4b4f64c217c9205", self.f.images))
        r = self.f.post()
        self.assertTrue(self.line(r.stdout, "Q01").startswith("FAIL"))
        self.assertTrue(self.line(r.stdout, "Q02").startswith("FAIL"))

    def test_post_drift_check(self):
        self.f.pre()
        self.f.apply_update()
        with open(self.f.fx / "apps" / APP / "compose.yaml", "a") as fh:
            fh.write("# hand edit\n")
        r = self.f.post()
        for cid in ("Q08", "Q09", "Q10"):
            self.assertTrue(self.line(r.stdout, cid).startswith("FAIL"), self.line(r.stdout, cid))

    def test_post_fails_when_snapshot_holds_identity(self):
        self.f.pre()
        self.f.apply_update()
        snap = self.f.fx / ".pre-update" / INST / "data/data/tailscale"
        snap.mkdir(parents=True)
        (snap / "tailscaled.state").write_text("{}")
        r = self.f.post()
        q11 = self.line(r.stdout, "Q11")
        self.assertTrue(q11.startswith("FAIL"), q11)
        self.assertIn("data/data/tailscale", q11)

    def test_post_needs_pre_and_args(self):
        r = self.f.run("post", "--stick", "/disks/sdc1")
        self.assertEqual(r.returncode, 2)


    def test_p04_inspect_format_handles_container_without_health_key(self):
        """Collector-like inspect JSON has no State.Health; the live template must still work.

        On idea03 the 1.0 collector has no Health key. The old
        `{{if .State.Health}}` format made docker inspect exit 1, and P04
        reported collector=absent even though the container was running.
        """
        fmt = containers_check_format()
        self.assertIn('index .State "Health"', fmt)
        self.assertNotIn("if .State.Health", fmt)
        collector = {
            "Id": "44cc875fffb3" + "0" * 52,
            "Name": "/usage-dashboard-8fhwrslsrq78xtswed4-collector-1",
            "Config": {
                "Image": "python:3.12-slim-bookworm",
                "Labels": {"com.docker.compose.service": "collector"},
            },
            "State": {"Status": "running"},  # no Health key
        }
        web = {
            "Id": "1efcb9f3b065" + "0" * 52,
            "Name": "/usage-dashboard-8fhwrslsrq78xtswed4-web-1",
            "Config": {
                "Image": "ghcr.io/koenswings/usage-dashboard-web:1.0",
                "Labels": {"com.docker.compose.service": "web"},
            },
            "State": {"Status": "running", "Health": {"Status": "healthy"}},
        }
        r = apply_inspect_format(fmt, collector)
        self.assertEqual(r.returncode, 0, r.stderr)
        parts = r.stdout.strip().split("|")
        self.assertEqual(len(parts), 6, r.stdout)
        self.assertEqual(parts[3], "running")
        self.assertEqual(parts[4], "none")
        self.assertEqual(parts[5], "collector")
        r = apply_inspect_format(fmt, web)
        self.assertEqual(r.returncode, 0, r.stderr)
        parts = r.stdout.strip().split("|")
        self.assertEqual(parts[3], "running")
        self.assertEqual(parts[4], "healthy")
        self.assertEqual(parts[5], "web")
        # the old format must still fail on a container with no Health key
        old = '{{.Id}}|{{.Name}}|{{.Config.Image}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{index .Config.Labels "com.docker.compose.service"}}'
        r = apply_inspect_format(old, collector)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("Health", r.stderr)

    def test_shellcheck_clean(self):
        sc = shutil.which("shellcheck")
        if not sc:
            self.skipTest("shellcheck not installed")
        r = subprocess.run([sc, str(SCRIPT), str(REPO / "script/build-release-bundle.sh")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
