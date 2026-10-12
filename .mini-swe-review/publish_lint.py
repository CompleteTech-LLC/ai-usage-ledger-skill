"""Publish the single-file import-style repair after validation."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

BASE = "3f7ca1e5d0528670ec326ef6f59e7398a34537b5"
BRANCH = "fix/mini-swe-provider-identity-20261012"
PATH = "tests/test_package_mini_swe_identity.py"
assert subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == BASE
assert subprocess.check_output(["git", "diff", "--name-only"], text=True).splitlines() == [PATH]
query = "mutation($input:CreateCommitOnBranchInput!){createCommitOnBranch(input:$input){commit{oid url signature{isValid wasSignedByGitHub}}}}"
value = {
    "branch": {"repositoryNameWithOwner": os.environ["GITHUB_REPOSITORY"], "branchName": BRANCH},
    "expectedHeadOid": BASE,
    "message": {"headline": "ci: align mini-SWE regression imports with package-test conventions",
                "body": "Add the same scoped E402 annotations used by existing package tests after the scripts path setup. No runtime, assertion, or quality-gate changes."},
    "fileChanges": {"additions": [{"path": PATH, "contents": base64.b64encode(Path(PATH).read_bytes()).decode()}]},
}
request = urllib.request.Request("https://api.github.com/graphql",
    data=json.dumps({"query": query, "variables": {"input": value}}).encode(),
    headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"], "Content-Type": "application/json"})
with urllib.request.urlopen(request, timeout=90) as response:
    result = json.load(response)
if result.get("errors"):
    raise RuntimeError(json.dumps(result["errors"]))
commit = result["data"]["createCommitOnBranch"]["commit"]
assert commit["signature"] and commit["signature"]["isValid"] and commit["signature"]["wasSignedByGitHub"]
receipt = {"commit": commit, "base": BASE, "branch": BRANCH, "sha256": {PATH: hashlib.sha256(Path(PATH).read_bytes()).hexdigest()}}
print(json.dumps(receipt, indent=2))
Path(os.environ["RUNNER_TEMP"], "mini-swe-lint-publication.json").write_text(json.dumps(receipt, indent=2))
