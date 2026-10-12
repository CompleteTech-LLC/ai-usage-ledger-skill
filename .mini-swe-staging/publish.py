import base64
import json
import os
from pathlib import Path
import subprocess
import urllib.request

base = 'e9d5e225a802d8eddcc7e1a2fc72cded6db1437e'
branch = 'feat/mini-swe-native-usage-20261012'
paths = subprocess.check_output(['git', 'diff', '--name-only', '--diff-filter=AM'], text=True).splitlines()
assert paths and all(p.startswith(('scripts/', 'tests/', 'references/', '.github/workflows/mini-swe-integration.yml')) for p in paths)
# The workflow-specific permission is unavailable to GITHUB_TOKEN. Publish source
# through GitHub's signed GraphQL API; the authorized connector adds CI separately.
workflow = '.github/workflows/mini-swe-integration.yml'
files = [{'path': p, 'contents': base64.b64encode(Path(p).read_bytes()).decode()} for p in paths if p != workflow]
query = 'mutation($input:CreateCommitOnBranchInput!){createCommitOnBranch(input:$input){commit{oid url signature{isValid wasSignedByGitHub}}}}'
value = {'branch': {'repositoryNameWithOwner': os.environ['GITHUB_REPOSITORY'], 'branchName': branch},
         'expectedHeadOid': base, 'message': {'headline': 'feat: collect native mini-SWE usage with opt-in pre-cost persistence'},
         'fileChanges': {'additions': files}}
request = urllib.request.Request('https://api.github.com/graphql', data=json.dumps({'query': query, 'variables': {'input': value}}).encode(),
    headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Content-Type': 'application/json', 'Accept': 'application/vnd.github+json'})
with urllib.request.urlopen(request, timeout=90) as response:
    result = json.load(response)
if result.get('errors'):
    raise RuntimeError(json.dumps(result['errors']))
commit = result['data']['createCommitOnBranch']['commit']
assert commit['signature'] and commit['signature']['isValid'] and commit['signature']['wasSignedByGitHub'], commit
print(json.dumps(commit))
Path(os.environ['RUNNER_TEMP'], 'mini-swe-published.json').write_text(json.dumps({'commit': commit, 'branch': branch, 'workflow_to_add': workflow}, indent=2))
