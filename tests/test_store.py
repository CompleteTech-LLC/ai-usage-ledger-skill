#!/usr/bin/env python3
"""
Store, onboarding and end-to-end `ledger run` checks on the synthetic fixtures.

    python3 tests/test_store.py     # prints STORE OK on success

Covers: every backend (sqlite, json, csv) ingests the fixture scan once and skips it entirely the second
time; exported events reproduce the scanner totals; `ledger.py init --yes` writes a config, manifest and
accounts draft without prompting; `ledger.py run --no-detect` scans the fixture host into the store and
renders the dashboard and study; a second run adds nothing; `status` and `export` work.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)
import ledger_store  # noqa: E402
import make_fixtures  # noqa: E402

OUT = os.path.join(HERE, "out")
FX = os.path.join(HERE, "fixtures")


def totals(events):
    t = {}
    for e in events:
        a = t.setdefault(e["tool"], [0, 0])
        a[0] += 1
        a[1] += int(e["total"])
    return t


def check_backends(scan_dir):
    ev = os.path.join(scan_dir, "events.fixture.jsonl")
    base = totals(json.loads(line) for line in open(ev, encoding="utf-8"))
    ok = True
    for kind in ("sqlite", "json", "csv"):
        path = os.path.join(OUT, "store-" + kind + (".sqlite" if kind == "sqlite" else ""))
        shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else (os.remove(path) if os.path.exists(path) else None)
        st = ledger_store.Store.open(kind, path)
        a1, s1 = st.ingest_events_file(ev)
        st.ingest_sessions_file(os.path.join(scan_dir, "sessions.fixture.jsonl"))
        st.ingest_prompts_file(os.path.join(scan_dir, "prompts.fixture.jsonl"))
        a2, s2 = st.ingest_events_file(ev)  # same scan again: everything must be skipped
        st.close()
        st = ledger_store.Store.open(kind, path)  # reopen: the id index must persist
        a3, s3 = st.ingest_events_file(ev)
        got = totals(st.iter_events())
        st.set_pref("brand", {"name": "Test"})
        pref = st.get_pref("brand")
        counts = st.counts()
        st.close()
        n = sum(v[0] for v in base.values())
        good = a1 == n and s1 == 0 and a2 == 0 and s2 == n and a3 == 0 and s3 == n and got == base and pref == {"name": "Test"} and counts["events"] == n
        print("%-7s first %d/%d  second %d/%d  reopened %d/%d  totals %s  prefs %s  %s" % (kind, a1, s1, a2, s2, a3, s3, "match" if got == base else "DIFFER", "ok" if pref else "bad", "OK" if good else "FAIL"))
        ok = ok and good
    return ok


def run(cmd, env=None, check=True):
    r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        sys.stdout.write(r.stdout[-3000:])
        sys.stderr.write(r.stderr[-3000:])
        raise SystemExit("command failed: %s" % " ".join(cmd))
    return r


def check_cli(scan_dir):
    home = os.path.join(OUT, "home")
    shutil.rmtree(home, ignore_errors=True)
    env = dict(os.environ, AI_USAGE_LEDGER_HOME=home)
    py = sys.executable
    ledger = os.path.join(SCRIPTS, "ledger.py")
    run([py, ledger, "init", "--yes", "--set", "store.kind=json", "--set", "brand.name=Fixture Co", "--set", "detect.wsl=n", "--set", "workdir=" + os.path.join(OUT, "cli-work")], env=env)
    cfg = json.load(open(os.path.join(home, "config.json"), encoding="utf-8"))
    ok = cfg["store"]["kind"] == "json" and cfg["branding"]["name"] == "Fixture Co" and os.path.isfile(cfg["manifest_path"]) and os.path.isfile(cfg["accounts_path"]) and os.path.isfile(cfg["pricing_path"])
    print("init:    config %s, store %s, brand %s  %s" % (os.path.basename(home), cfg["store"]["kind"], cfg["branding"]["name"], "OK" if ok else "FAIL"))
    # point the manifest at the fixture host only (a real run would use the auto-detected hosts)
    m = json.load(open(cfg["manifest_path"], encoding="utf-8"))
    m["hosts"] = [{"name": "fixture", "kind": "local", "claude_roots": [os.path.join(FX, "claude")], "codex_roots": [os.path.join(FX, "codex")], "gemini_roots": [os.path.join(FX, "gemini")],
                   "cline_roots": ["cline=" + os.path.join(FX, "cline")], "aider_roots": [os.path.join(FX, "aider")], "kimi_roots": [os.path.join(FX, "kimi")], "vibe_roots": [os.path.join(FX, "vibe")],
                   "continue_roots": [os.path.join(FX, "continue")], "pi_roots": [os.path.join(FX, "pi")], "generic_roots": ["codebuff=" + os.path.join(FX, "generic")]}]
    json.dump(m, open(cfg["manifest_path"], "w", encoding="utf-8"), indent=2)
    shutil.copy(os.path.join(ROOT, "examples", "accounts.fixtures.json"), cfg["accounts_path"])
    r1 = run([py, ledger, "run", "--no-detect"], env=env)
    r2 = run([py, ledger, "run", "--no-detect"], env=env)
    st = ledger_store.Store.open("json", cfg["store"]["path"])
    counts = st.counts()
    last = st.last_run()
    st.close()
    n = sum(1 for _ in open(os.path.join(scan_dir, "events.fixture.jsonl"), encoding="utf-8"))
    dash = os.path.join(cfg["workdir"], "compiled", "agent-ledger.html")
    pkgs = [d for d in os.listdir(os.path.join(cfg["workdir"], "reports")) if d.endswith(".zip")] if os.path.isdir(os.path.join(cfg["workdir"], "reports")) else []
    good = counts["events"] == n and last and last["added"]["events"] == 0 and counts["runs"] == 2 and os.path.isfile(dash) and pkgs and "Fixture Co" in open(dash, encoding="utf-8").read()
    print("run x2:  %d events in store (expected %d), second run added %s, runs %d, dashboard %s, package %s  %s" % (
        counts["events"], n, last["added"]["events"] if last else "?", counts["runs"], "yes" if os.path.isfile(dash) else "no", "yes" if pkgs else "no", "OK" if good else "FAIL"))
    if not good:
        sys.stdout.write(r1.stdout[-2000:] + r2.stdout[-2000:])
    ok = ok and bool(good)
    s = run([py, ledger, "status"], env=env)
    good = "events" in s.stdout and "Fixture Co" in s.stdout
    print("status:  %s" % ("OK" if good else "FAIL\n" + s.stdout))
    ok = ok and good
    out_csv = os.path.join(OUT, "export.csv")
    e = run([py, ledger, "export", "--format", "csv", "--out", out_csv], env=env)
    rows = sum(1 for _ in open(out_csv, encoding="utf-8")) - 1
    good = rows == n and "wrote" in e.stdout
    print("export:  %d rows  %s" % (rows, "OK" if good else "FAIL"))
    ok = ok and good
    return ok


def main():
    make_fixtures.build()
    scan_dir = os.path.join(OUT, "scan")
    shutil.rmtree(scan_dir, ignore_errors=True)
    run([sys.executable, os.path.join(SCRIPTS, "compile_ai_logs.py"), "scan", "--host", "fixture", "--out-dir", scan_dir,
         "--claude-root", os.path.join(FX, "claude"), "--codex-root", os.path.join(FX, "codex"), "--gemini-root", os.path.join(FX, "gemini"),
         "--cline-root", "cline=" + os.path.join(FX, "cline"), "--aider-root", os.path.join(FX, "aider"), "--kimi-root", os.path.join(FX, "kimi"),
         "--vibe-root", os.path.join(FX, "vibe"), "--continue-root", os.path.join(FX, "continue"), "--pi-root", os.path.join(FX, "pi"),
         "--generic-root", "codebuff=" + os.path.join(FX, "generic")])
    ok = check_backends(scan_dir)
    ok = check_cli(scan_dir) and ok
    print("STORE OK" if ok else "STORE CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
