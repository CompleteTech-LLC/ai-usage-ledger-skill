"""One-shot review repair; this helper is not part of the product PR."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

BASE = "c241e5443738bd6c1b61fb823b7285f35286649c"
BRANCH = "fix/mini-swe-provider-identity-20261012"
PATHS = ["scripts/mini_swe_usage.py", "references/mini-swe-agent.md", "tests/test_package_mini_swe_identity.py"]
TESTS = '''"""Observed-provider identity regression; synthetic data and real ledger stores."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import compile_ai_logs as scanner
import ledger_store
import mini_swe_usage as usage


def response(provider=None):
    return {"id": "shared-response-id", "model": "shared-model", "provider": provider,
            "created": 1780000000,
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}


def trajectory(*responses):
    return {"trajectory_format": usage.TRAJECTORY,
            "info": {"config": {"model_type": "minisweagent.models.litellm_model.LitellmModel",
                                "model": {"model_name": "routing-alias"}}},
            "messages": [{"role": "assistant", "extra": {"response": value}} for value in responses]}


class MiniSweProviderIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def snapshot(self, provider=None, **kwargs):
        return usage.usage_snapshot(response(provider), backend="litellm",
                                    requested_model=kwargs.pop("requested_model", "routing-alias"), **kwargs)

    def event(self, snapshot):
        return usage.normalize(snapshot, "test-host", self.root / "run.traj.json")

    def scan(self):
        output, stats = io.StringIO(), scanner.Stats()
        usage.scan(str(self.root), "test-host", output, stats, [], set())
        return [json.loads(line) for line in output.getvalue().splitlines()], stats

    def test_different_observed_providers_do_not_collide(self):
        for requested, configured in (("routing-alias", None), ("openai/shared-model", None),
                                      ("routing-alias", "custom-endpoint")):
            with self.subTest(requested=requested, configured=configured):
                left = self.event(self.snapshot("provider-a", requested_model=requested, provider=configured))
                right = self.event(self.snapshot("provider-b", requested_model=requested, provider=configured))
                self.assertNotEqual(left["request_id"], right["request_id"])
                self.assertEqual(left["provider"], right["provider"])
                self.assertEqual((left["upstream_provider"], right["upstream_provider"]),
                                 ("provider-a", "provider-b"))

    def test_observed_provider_not_routing_alias_namespaces_identity(self):
        left = self.event(self.snapshot("provider-a", provider="route-a"))
        right = self.event(self.snapshot("provider-a", provider="route-b"))
        self.assertEqual(left["request_id"], right["request_id"])
        self.assertEqual((left["provider"], right["provider"]), ("route-a", "route-b"))
        self.assertEqual(left["request_id"], "mini-swe:" + usage.digest(
            "provider", "provider-a", "shared-model", "shared-response-id"))

    def test_missing_or_invalid_observed_provider_preserves_fallback(self):
        for observed in (None, "", "https://invalid.example/?secret=no", {"not": "an identifier"}):
            with self.subTest(observed=observed):
                event = self.event(self.snapshot(observed, provider="configured-provider"))
                self.assertEqual(event["request_id"], "mini-swe:" + usage.digest(
                    "provider", "configured-provider", "shared-model", "shared-response-id"))
                self.assertIsNone(event["upstream_provider"])

    def test_export_trajectory_copies_and_resume_share_namespace(self):
        document = trajectory(response("provider-a"), response("provider-b"))
        (self.root / "run.traj.json").write_text(json.dumps(document), encoding="utf-8")
        (self.root / "resumed.traj.json").write_text(json.dumps(document), encoding="utf-8")
        for provider in ("provider-a", "provider-b"):
            snapshot = self.snapshot(provider)
            snapshot.update(invocation_id=provider + "-invocation", session_id="resumed-session", status="completed")
            (self.root / (provider + ".usage.json")).write_text(json.dumps(snapshot), encoding="utf-8")
        original = {path.name: path.read_bytes() for path in self.root.iterdir()}
        events, stats = self.scan()
        self.assertEqual((len(events), stats.dedup), (2, 4))
        self.assertEqual({event["upstream_provider"] for event in events}, {"provider-a", "provider-b"})
        self.assertEqual(sum(event["total"] for event in events), 240)
        replay, replay_stats = self.scan()
        self.assertEqual(events, replay)
        self.assertEqual(replay_stats.dedup, 4)
        self.assertEqual(original, {path.name: path.read_bytes() for path in self.root.iterdir()})

    def test_distinct_providers_survive_all_stores_and_repeated_scans(self):
        (self.root / "run.traj.json").write_text(json.dumps(
            trajectory(response("provider-a"), response("provider-b"))), encoding="utf-8")
        for kind in ("sqlite", "json", "csv"):
            with self.subTest(store=kind):
                store = ledger_store.Store.open(kind, str(self.root / ("store-" + kind)))
                try:
                    for expected in ((2, 0), (0, 2)):
                        events, _ = self.scan()
                        output = self.root / "events.jsonl"
                        output.write_text("".join(json.dumps(event) + "\\n" for event in events), encoding="utf-8")
                        self.assertEqual(store.ingest_events_file(str(output)), expected)
                    stored = list(store.iter_events())
                    self.assertEqual(len(stored), 2)
                    self.assertEqual(len({event["request_id"] for event in stored}), 2)
                    self.assertEqual(sum(event["total"] for event in stored), 240)
                finally:
                    store.close()

    def test_invocation_fallback_unchanged_without_response_id(self):
        ids = []
        for provider in ("provider-a", "provider-b", None):
            snapshot = self.snapshot(provider)
            snapshot.update(source_request_id=None, invocation_id="one-export-invocation")
            event = self.event(snapshot)
            self.assertEqual(event["identity_provenance"], "export_invocation_id")
            ids.append(event["request_id"])
        self.assertEqual(len(set(ids)), 1)


if __name__ == "__main__":
    unittest.main()
'''


def replace_once(path, before, after):
    content = path.read_text(encoding="utf-8")
    if content.count(before) != 1:
        raise RuntimeError("review anchor changed: " + str(path))
    path.write_text(content.replace(before, after), encoding="utf-8")


def apply():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if head != BASE:
        raise RuntimeError("refuse to patch unexpected checkout: " + head)
    test_path = Path(PATHS[2])
    if test_path.exists():
        raise RuntimeError("regression test already exists")
    test_path.write_text(TESTS, encoding="utf-8")
    red = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p",
                          "test_package_mini_swe_identity.py", "-v"], capture_output=True, text=True)
    log = red.stdout + red.stderr
    Path(os.environ["RUNNER_TEMP"], "mini-swe-review-red.txt").write_text(log, encoding="utf-8")
    print(log)
    if red.returncode == 0 or "ERROR:" in log or "FAIL: test_different_observed_providers_do_not_collide" not in log:
        raise RuntimeError("did not reproduce the reviewed collision as a test assertion failure")
    replace_once(Path(PATHS[0]),
                 '        identity = ("provider", provider, model, source_id)\n',
                 '        # A routing alias is not the observed provider: independent providers\n'
                 '        # may return identical response IDs for the same model.\n'
                 '        identity_provider = snap.get("upstream_provider") or provider\n'
                 '        identity = ("provider", identity_provider, model, source_id)\n')
    replace_once(Path(PATHS[1]),
                 'A response ID is namespaced by provider and observed model. Without one, the\n',
                 'A response ID is namespaced by the observed upstream provider when available,\n'
                 'falling back to the configured provider, and by the observed model. The\n'
                 'reporting `provider` routing label and `upstream_provider` evidence are both\n'
                 'preserved. Different providers returning the same ID/model must not collapse;\n'
                 'the same observed provider response reached through different routing labels\n'
                 'must not be counted twice. Without a response ID, the\n')
    replace_once(Path(PATHS[1]),
                 "python -m unittest discover -s tests -p 'test_package_mini_swe.py' -v\n",
                 "python -m unittest discover -s tests -p 'test_package_mini_swe*.py' -v\n")
    replace_once(Path(PATHS[1]),
                 'The existing append-only stores remain append-only. A scan during an invocation\n',
                 'Experimental imports from before the observed-provider identity fix should be\n'
                 'rebuilt from approved source records before using the corrected collector;\n'
                 'append-only stores do not migrate earlier routing-only identity keys.\n\n'
                 'The existing append-only stores remain append-only. A scan during an invocation\n')
    subprocess.run(["git", "add", "-N", str(test_path)], check=True)
    subprocess.run(["git", "diff", "--check"], check=True)
    changed = subprocess.check_output(["git", "diff", "--name-only"], text=True).splitlines()
    if set(changed) != set(PATHS):
        raise RuntimeError("unexpected changed files: " + repr(changed))
    print("Applied three-file review fix; no upstream, workflow, pricing, or consent changes")


def publish():
    changed = subprocess.check_output(["git", "diff", "--name-only"], text=True).splitlines()
    if set(changed) != set(PATHS):
        raise RuntimeError("unexpected publication files")
    files = [{"path": path, "contents": base64.b64encode(Path(path).read_bytes()).decode()} for path in PATHS]
    query = "mutation($input:CreateCommitOnBranchInput!){createCommitOnBranch(input:$input){commit{oid url signature{isValid wasSignedByGitHub}}}}"
    value = {"branch": {"repositoryNameWithOwner": os.environ["GITHUB_REPOSITORY"], "branchName": BRANCH},
             "expectedHeadOid": BASE,
             "message": {"headline": "fix: namespace mini-SWE response identities by observed provider",
                         "body": "Address PR #35 review r4252094125. Preserve routing attribution and fallback identity, and verify trajectory/export overlap, resumed copies and repeat ingestion across all stores with synthetic regressions."},
             "fileChanges": {"additions": files}}
    request = urllib.request.Request("https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"input": value}}).encode(),
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"], "Content-Type": "application/json",
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=90) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError(json.dumps(result["errors"]))
    commit = result["data"]["createCommitOnBranch"]["commit"]
    if not commit["signature"] or not commit["signature"]["isValid"] or not commit["signature"]["wasSignedByGitHub"]:
        raise RuntimeError("commit signature was not verified")
    receipt = {"commit": commit, "base": BASE, "branch": BRANCH,
               "sha256": {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in PATHS}}
    print(json.dumps(receipt, indent=2))
    Path(os.environ["RUNNER_TEMP"], "mini-swe-review-publication.json").write_text(json.dumps(receipt, indent=2))
    patch = subprocess.check_output(["git", "diff", "--binary"])
    Path(os.environ["RUNNER_TEMP"], "mini-swe-review-fix.patch").write_bytes(patch)


if __name__ == "__main__":
    {"apply": apply, "publish": publish}[sys.argv[1]]()
