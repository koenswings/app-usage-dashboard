"""idea#443: script/build-release-bundle.sh puts collector/build-info.json into the
App bundle (and its SHA256SUMS), and script/check-bundle-safe.py refuses a bundle
that copyBundle would let clobber live instance state.

The wrapper is run against a throwaway clone of this repo with a LOCAL-ONLY tag
(never pushed). Two build scripts are used: a minimal stand-in that does what
agent-app-dev build-app-bundle.sh does (git ls-files copy, SHA256SUMS), always;
and the real agent-app-dev script when found (BUILD_APP_BUNDLE env, or a sibling
agent-app-dev checkout), otherwise that case is skipped.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WRAP = REPO / "script" / "build-release-bundle.sh"
SAFE = REPO / "script" / "check-bundle-safe.py"
sys.path.insert(0, str(REPO / "collector"))
from src import buildinfo  # noqa: E402

STUB_BAB = r"""#!/usr/bin/env bash
# stand-in for agent-app-dev build-app-bundle.sh: tag==HEAD, git ls-files copy, SHA256SUMS
set -euo pipefail
while [ $# -gt 0 ]; do case "$1" in --app-dir) A=$2;; --disk-root) R=$2;; --ref) F=$2;; esac; shift 2; done
if [ "${ALLOW_UNTAGGED:-}" = 1 ]; then V="0.0-dev+$(git -C "$A" rev-parse --short=12 HEAD)"; else
  [ "$(git -C "$A" rev-parse "refs/tags/$F^{commit}")" = "$(git -C "$A" rev-parse HEAD)" ] || { echo "not HEAD" >&2; exit 1; }; V=$F; fi
B="apps/usage-dashboard-$V"; mkdir -p "$R/$B"
(cd "$A" && git ls-files -z | tar --null -T - -cf -) | tar -xpf - -C "$R/$B"
(cd "$R/$B" && find . -type f ! -name SHA256SUMS | sed 's|^\./||' | LC_ALL=C sort | while read -r f; do sha256sum -- "$f"; done) > "$R/$B/SHA256SUMS"
# Isolated-tree disk-root SHA256SUMS (services/*.tar + apps/**). sha256sum --check
# only verifies listed paths; unlisted live-disk content is not a failure.
(cd "$R" && { find apps \( -type f -o -type l \); find services -maxdepth 1 -type f -name '*.tar' 2>/dev/null || true; } | LC_ALL=C sort -u | while read -r f; do sha256sum -- "$f"; done) > "$R/SHA256SUMS"
echo "ok: $R/$B ($(wc -l < "$R/$B/SHA256SUMS") files in SHA256SUMS)"
"""
DOCKER_STUB = '#!/usr/bin/env bash\n[ "$1" = save ] && { echo "placeholder $2"; exit 0; }\nexit 9\n'


def _bab_has_zx(path):
    """agent-app-dev script/check-compose.mjs imports zx; skip a checkout without it."""
    return (Path(path).resolve().parent.parent / "node_modules" / "zx").is_dir()


def find_real_bab():
    forced = os.environ.get("BUILD_APP_BUNDLE", "")
    cands = [forced,
             str(REPO.parent / "agent-app-dev" / "script" / "build-app-bundle.sh"),
             "/workspace/kid-aad-main-5af736f/script/build-app-bundle.sh",
             "/workspace/agent-app-dev/script/build-app-bundle.sh"]
    for c in cands:
        if not c or not Path(c).is_file():
            continue
        # Honour an explicit BUILD_APP_BUNDLE even if zx is missing (will fail loudly).
        if c == forced or _bab_has_zx(c):
            return c
    return None


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class BuildReleaseBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = Path(self.tmp.name)
        # a throwaway copy of this repo's committed HEAD, plus the working tree's
        # wrapper/check scripts committed on top (so the test sees this change)
        self.app = self.t / "app"
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(REPO), str(self.app)], check=True)
        g = ["git", "-C", str(self.app), "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "-C", str(self.app), "fetch", "-q", str(REPO), "HEAD"], check=True)
        subprocess.run(g + ["checkout", "-q", "--detach", "FETCH_HEAD"], check=True)
        for rel in ("script/build-release-bundle.sh", "script/check-bundle-safe.py", "script/write-build-info.sh"):
            (self.app / rel).write_bytes((REPO / rel).read_bytes())
            (self.app / rel).chmod(0o755)
        # Working-tree compose and scripts must be committed: the wrapper
        # builds the --ref tag only. Leave official tags 1.1 and 1.2 in place (they
        # point at other commits) so a tags fetch cannot steal checkout.
        (self.app / "compose.yaml").write_bytes((REPO / "compose.yaml").read_bytes())
        subprocess.run(g + ["add", "-A", "script", "compose.yaml"], check=True)
        subprocess.run(g + ["commit", "-qm", "test", "--allow-empty"], check=True)
        subprocess.run(g + ["tag", "-f", "1.5"], check=True)  # throwaway clone; official 1.5 is tagged later
        self.sha = subprocess.check_output(["git", "-C", str(self.app), "rev-parse", "HEAD"], text=True).strip()
        self.stub = self.t / "build-app-bundle.sh"
        self.stub.write_text(STUB_BAB)
        self.stub.chmod(0o755)
        self.docker = self.t / "docker"
        self.docker.write_text(DOCKER_STUB)
        self.docker.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, bab, ref="1.5", root_name="root", untagged=False):
        root = self.t / root_name
        root.mkdir()
        env = dict(os.environ, DOCKER=str(self.docker))
        env.pop("ALLOW_UNTAGGED", None)
        if untagged:
            env["ALLOW_UNTAGGED"] = "1"
        r = subprocess.run([str(self.app / "script/build-release-bundle.sh"), "--build-app-bundle", str(bab),
                            "--disk-root", str(root), "--ref", ref, "--app-dir", str(self.app)],
                           capture_output=True, text=True, env=env)
        return r, root

    def assert_bundle(self, root, app_id):
        b = root / "apps" / app_id
        bi = b / "collector" / "build-info.json"
        self.assertTrue(bi.is_file())
        self.assertEqual(json.loads(bi.read_text()), {"version": "1.5", "commit": self.sha})
        sums = (b / "SHA256SUMS").read_text()
        self.assertIn("%s  collector/build-info.json\n" % sha256(bi), sums)
        subprocess.run(["sha256sum", "--quiet", "--strict", "--check", "SHA256SUMS"], cwd=b, check=True)
        if (root / "SHA256SUMS").is_file():
            subprocess.run(["sha256sum", "--quiet", "--strict", "--check", "SHA256SUMS"], cwd=root, check=True)
        self.assertFalse((b / "data").exists())
        self.assertFalse((b / ".env").exists())
        # health resolves the commit from the bundled file
        os.environ["USAGE_DASHBOARD_BUILD_INFO"] = str(bi)
        os.environ.pop("USAGE_DASHBOARD_COMMIT", None)
        try:
            self.assertEqual(buildinfo.dashboard_commit(), self.sha)
        finally:
            os.environ.pop("USAGE_DASHBOARD_BUILD_INFO", None)
        return bi

    def test_stub_tagged_build_has_build_info_in_sums(self):
        r, root = self.build(self.stub)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_bundle(root, "usage-dashboard-1.5")
        self.assertIn("build-info: apps/usage-dashboard-1.5/collector/build-info.json", r.stdout)
        # the checkout itself is untouched (index and tree)
        st = subprocess.check_output(["git", "-C", str(self.app), "status", "--porcelain", "--ignored"], text=True)
        self.assertNotIn("build-info.json", st)

    def test_reproducible(self):
        r1, a = self.build(self.stub, root_name="a")
        r2, b = self.build(self.stub, root_name="b")
        self.assertEqual(r1.returncode, 0, r1.stderr)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        p = "apps/usage-dashboard-1.5/"
        self.assertEqual(sha256(a / p / "collector/build-info.json"), sha256(b / p / "collector/build-info.json"))
        self.assertEqual((a / p / "SHA256SUMS").read_bytes(), (b / p / "SHA256SUMS").read_bytes())

    def test_ref_must_equal_xapp_version(self):
        subprocess.run(["git", "-C", str(self.app), "tag", "1.6"], check=True)
        r, _ = self.build(self.stub, ref="1.6")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("does not equal compose.yaml x-app.version", r.stderr)

    def test_ref_1_2_builds_from_1_2_commit_when_1_1_tag_also_present(self):
        """A second older tag must not divert --ref 1.2 onto the 1.1 commit."""
        repo = self.t / "two_tags"
        repo.mkdir()
        g = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        (repo / "script").mkdir()
        (repo / "collector").mkdir()
        for rel in ("script/build-release-bundle.sh", "script/check-bundle-safe.py",
                    "script/write-build-info.sh"):
            dest = repo / rel
            dest.write_bytes((REPO / rel).read_bytes())
            dest.chmod(0o755)
        compose = (REPO / "compose.yaml").read_text()

        def stamp(version, marker):
            lines = []
            replaced = False
            for line in compose.splitlines(True):
                if line.startswith("  version:"):
                    lines.append('  version: "%s"\n' % version)
                    replaced = True
                else:
                    lines.append(line)
            if not replaced:
                raise AssertionError("compose.yaml has no x-app version line to stamp")
            (repo / "compose.yaml").write_text("".join(lines))
            (repo / "marker.txt").write_text(marker + "\n")

        stamp("1.1", "from-1.1")
        subprocess.run(g + ["add", "-A"], check=True)
        subprocess.run(g + ["commit", "-qm", "tag 1.1"], check=True)
        subprocess.run(g + ["tag", "1.1"], check=True)
        sha_11 = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        stamp("1.2", "from-1.2")
        subprocess.run(g + ["add", "-A"], check=True)
        subprocess.run(g + ["commit", "-qm", "tag 1.2"], check=True)
        subprocess.run(g + ["tag", "1.2"], check=True)
        sha_12 = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        self.assertNotEqual(sha_11, sha_12)
        self.assertEqual(
            subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "refs/tags/1.1^{commit}"], text=True
            ).strip(),
            sha_11,
        )

        root = self.t / "two_tags_root"
        root.mkdir()
        env = dict(os.environ, DOCKER=str(self.docker))
        env.pop("ALLOW_UNTAGGED", None)
        r = subprocess.run(
            [str(repo / "script/build-release-bundle.sh"),
             "--build-app-bundle", str(self.stub),
             "--disk-root", str(root), "--ref", "1.2", "--app-dir", str(repo)],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        b = root / "apps" / "usage-dashboard-1.2"
        self.assertEqual((b / "marker.txt").read_text(), "from-1.2\n")
        self.assertEqual(
            json.loads((b / "collector/build-info.json").read_text()),
            {"version": "1.2", "commit": sha_12},
        )
        self.assertNotIn(sha_11, (b / "collector/build-info.json").read_text())

    def test_untagged_dev_bundle_still_carries_xapp_version(self):
        r, root = self.build(self.stub, untagged=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_bundle(root, "usage-dashboard-0.0-dev+" + self.sha[:12])

    def test_real_build_app_bundle(self):
        bab = find_real_bab()
        if not bab:
            self.skipTest("agent-app-dev build-app-bundle.sh not found (set BUILD_APP_BUNDLE)")
        r, root = self.build(bab)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_bundle(root, "usage-dashboard-1.5")
        # tagged 1.5 bundle compose == the tag's compose byte for byte (the post-check drift basis)
        tag_compose = subprocess.check_output(["git", "-C", str(self.app), "show", "1.5:compose.yaml"])
        self.assertEqual((root / "apps/usage-dashboard-1.5/compose.yaml").read_bytes(), tag_compose)
        sums = (root / "apps/usage-dashboard-1.5/SHA256SUMS").read_text()
        self.assertRegex(sums, r"(?m)^[0-9a-f]{64}  compose\.yaml$")


class CheckBundleSafeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.b = Path(self.tmp.name) / "apps" / "usage-dashboard-1.5"
        (self.b / "collector").mkdir(parents=True)
        (self.b / "compose.yaml").write_bytes((REPO / "compose.yaml").read_bytes())
        (self.b / "collector" / "build-info.json").write_text("{}\n")

    def tearDown(self):
        self.tmp.cleanup()

    def sums(self, skip=()):
        lines = []
        for p in sorted(self.b.rglob("*")):
            if p.is_file() and p.name != "SHA256SUMS" and p.name not in skip:
                lines.append("%s  %s" % (sha256(p), p.relative_to(self.b).as_posix()))
        (self.b / "SHA256SUMS").write_text("".join(l + "\n" for l in lines))

    def run_safe(self, *args):
        return subprocess.run([sys.executable, str(SAFE), *args], capture_output=True, text=True)

    def test_repo_tree_is_safe(self):
        r = self.run_safe("--tree", str(REPO))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_clean_bundle_passes(self):
        self.sums()
        r = self.run_safe(str(self.b))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_data_tree_refused(self):
        for rel in ("data/tailscale/tailscaled.state", "data/keys/pull_key", "data/tailscale-run/x",
                    "data/usage.sqlite", "data/operators.json"):
            with self.subTest(rel=rel):
                p = self.b / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("x")
                self.sums()
                r = self.run_safe(str(self.b))
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn("data", r.stdout)
                p.unlink()

    def test_empty_data_dir_refused(self):
        (self.b / "data" / "tailscale").mkdir(parents=True)
        self.sums()
        r = self.run_safe(str(self.b))
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_env_refused(self):
        (self.b / ".env").write_text("X=1\n")
        self.sums()
        r = self.run_safe(str(self.b))
        self.assertEqual(r.returncode, 1)
        self.assertIn(".env", r.stdout)

    def test_sums_must_list_compose_and_every_file(self):
        self.sums(skip=("compose.yaml",))
        r = self.run_safe(str(self.b))
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not list compose.yaml", r.stdout)
        (self.b / "SHA256SUMS").write_text("")
        r = self.run_safe(str(self.b))
        self.assertIn("SHA256SUMS is empty", r.stdout)

    def test_forbidden_list_follows_compose(self):
        sys.path.insert(0, str(REPO / "script"))
        import importlib.util
        spec = importlib.util.spec_from_file_location("cbs", SAFE)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        got = m.forbidden_paths((REPO / "compose.yaml").read_text())
        for p in ("data", ".env", "data/keys", "data/tailscale", "data/tailscale-run",
                  "data/backup/daily", "data/usage.sqlite", "data/usage.sqlite-wal", "data/usage.sqlite-shm"):
            self.assertIn(p, got)


if __name__ == "__main__":
    unittest.main()
