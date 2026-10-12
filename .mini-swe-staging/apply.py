import base64
import hashlib
import lzma
from pathlib import Path
import subprocess

stage = Path(__file__).resolve().parent
payload = ''.join(p.read_text().strip() for p in sorted(stage.glob('payload-*.b64')))
patch = lzma.decompress(base64.b64decode(payload, validate=True))
assert hashlib.sha256(patch).hexdigest() == '74d5f7dbaadde7d17d4a5044b98b4e5b8c9fc8519b78697358fd034b3b1269c1'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == 'e9d5e225a802d8eddcc7e1a2fc72cded6db1437e'
subprocess.run(['git', 'apply', '--check', '-'], input=patch, check=True)
subprocess.run(['git', 'apply', '-'], input=patch, check=True)
subprocess.run(['git', 'add', '-N', '.'], check=True)
subprocess.run(['git', 'diff', '--check'], check=True)
print('Applied SHA256-verified implementation patch to pinned main')
