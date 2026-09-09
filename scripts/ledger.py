#!/usr/bin/env python3
"""
ledger.py - the one entry point people and agents use day to day.

    python3 scripts/ledger.py init            # first-run onboarding (interactive on a terminal, defaults with --yes)
    python3 scripts/ledger.py run             # scan every configured host, append new calls to the store, rebuild the reports
    python3 scripts/ledger.py status          # what is configured, what is stored, when it last ran
    python3 scripts/ledger.py export --format csv --out events.csv
    python3 scripts/ledger.py reinit          # fresh onboarding; the old store is kept aside with a timestamp

Preferences (branding, storage backend, working directory, timezone, auto-detection) are captured once,
saved to <home>/config.json and mirrored into the store's prefs table, and reused on every later run.
The store is append-only: rescanning never duplicates a call, so `run` can be executed as often as wanted.

Standard library only.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import detect_hosts  # noqa: E402
import ledger_store  # noqa: E402

CONFIG_VERSION = 1


def home_dir():
    return os.path.expandvars(os.path.expanduser(os.environ.get("AI_USAGE_LEDGER_HOME") or "~/.ai-usage-ledger"))


def config_path():
    return os.path.join(home_dir(), "config.json")


def load_config():
    p = config_path()
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save_config(cfg):
    os.makedirs(home_dir(), exist_ok=True)
    with open(config_path(), "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)


def local_tz_name():
    try:
        tz = datetime.now().astimezone().tzinfo
        key = getattr(tz, "key", None)
        if key:
            return key
        if os.path.exists("/etc/timezone"):
            return open("/etc/timezone").read().strip()
        if os.path.islink("/etc/localtime"):
            return "/".join(os.path.realpath("/etc/localtime").split("/")[-2:])
    except Exception:
        pass
    return "UTC"


def run(cmd, **kw):
    sys.stderr.write("$ %s\n" % " ".join(cmd))
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        raise SystemExit("command failed (%d): %s" % (r.returncode, " ".join(cmd)))


# ----------------------------------------------------------------------------
# onboarding
# ----------------------------------------------------------------------------

DEFAULT_BRAND = {"name": "CompleteTech", "eyebrow": "COMPLETETECH LLC", "tagline": "Innovation at Every Integration",
                 "contact": "complete.tech · Timothy.Gregg@complete.tech", "logo": os.path.join(SKILL, "assets", "logo.png"), "accent": "#1E3A8A",
                 "footer": "CompleteTech LLC · Innovation at Every Integration · complete.tech",
                 "light": {"bg": "#F8FAFC", "surface": "#FFFFFF", "surface-2": "#EEF2FF", "ink": "#0F172A", "ink-2": "#1E293B", "ink-3": "#64748B", "line": "#E2E8F0", "line-2": "#CBD5E1"},
                 "dark": {"bg": "#0F172A", "surface": "#1E293B", "surface-2": "#273449", "ink": "#F1F5F9", "ink-2": "#CBD5E1", "ink-3": "#94A3B8", "line": "#334155", "line-2": "#475569"}}

QUESTIONS = [
    # key, prompt, default-from-current, validator/choices
    ("brand.name", "Brand name shown on the dashboard and study", lambda c: c["branding"]["name"], None),
    ("brand.eyebrow", "Eyebrow line above the name (e.g. company legal name)", lambda c: c["branding"]["eyebrow"], None),
    ("brand.tagline", "Tagline", lambda c: c["branding"]["tagline"], None),
    ("brand.contact", "Contact line (site · e-mail)", lambda c: c["branding"]["contact"], None),
    ("brand.logo", "Logo file (PNG/SVG path, URL, or blank for none)", lambda c: c["branding"]["logo"], None),
    ("brand.accent", "Accent colour (hex)", lambda c: c["branding"]["accent"], None),
    ("brand.footer", "Footer text", lambda c: c["branding"]["footer"], None),
    ("theme", "Default theme (light / dark / system)", lambda c: c["theme"], ["light", "dark", "system"]),
    ("store.kind", "Storage backend (sqlite / json / csv)", lambda c: c["store"]["kind"], ["sqlite", "json", "csv"]),
    ("workdir", "Working directory for scans, compiled tables and reports", lambda c: c["workdir"], None),
    ("timezone", "Timezone for time-of-day analysis", lambda c: c["timezone"], None),
    ("detect.all_profiles", "Also scan other user profiles and other drives on this machine? (y/n)", lambda c: "y" if c["detect"]["all_profiles"] else "n", ["y", "n"]),
    ("detect.wsl", "Probe WSL distros on Windows? (y/n)", lambda c: "y" if c["detect"]["wsl"] else "n", ["y", "n"]),
]


def default_config():
    return {
        "version": CONFIG_VERSION, "initialized_at": None, "home": home_dir(),
        "store": {"kind": "sqlite", "path": os.path.join(home_dir(), "ledger.sqlite")},
        "workdir": os.path.join(home_dir(), "ledger"), "timezone": local_tz_name(), "theme": "system",
        "branding": dict(DEFAULT_BRAND), "detect": {"all_profiles": False, "wsl": True, "on_every_run": True},
        "pricing_path": os.path.join(home_dir(), "pricing.json"), "accounts_path": os.path.join(home_dir(), "accounts.json"),
        "report_config_path": os.path.join(home_dir(), "report_config.json"), "manifest_path": os.path.join(home_dir(), "manifest.json"),
        "package_prefix": "AI_Usage_Ledger", "extra_hosts": [],
    }


def set_dotted(cfg, key, value):
    if key.startswith("brand."):
        cfg["branding"][key[6:]] = value
    elif key == "store.kind":
        cfg["store"]["kind"] = value
        cfg["store"]["path"] = os.path.join(home_dir(), {"sqlite": "ledger.sqlite", "json": "ledger-json", "csv": "ledger-csv"}[value])
    elif key.startswith("detect."):
        cfg["detect"][key[7:]] = value in ("y", "yes", "true", True)
    else:
        cfg[key] = value


def ask(prompt, default, choices=None):
    while True:
        raw = input("%s [%s]: " % (prompt, default)).strip()
        val = raw or default
        if choices and val not in choices:
            print("  choose one of: %s" % ", ".join(choices))
            continue
        return val


def onboard(args):
    cfg = load_config() if not args.reinit else None
    fresh = cfg is None
    cfg = cfg or default_config()
    for kv in args.set or []:
        k, _, v = kv.partition("=")
        set_dotted(cfg, k.strip(), v.strip())
    interactive = sys.stdin.isatty() and sys.stdout.isatty() and not args.yes
    if interactive:
        print("\nAI usage ledger — onboarding. Press Enter to accept a default.\n")
        for key, prompt, current, choices in QUESTIONS:
            set_dotted(cfg, key, ask(prompt, current(cfg), choices))
    # detection
    print("\nDetecting agent logs on this machine%s..." % (" and its WSL distros" if cfg["detect"]["wsl"] and detect_hosts.IS_WIN else ""))
    hosts, notes = detect_hosts.detect_hosts(all_profiles=cfg["detect"]["all_profiles"], probe_wsl=cfg["detect"]["wsl"])
    for h in hosts:
        print("  [%s] %s" % (h["name"], "; ".join(h.get("_found", []))[:200]))
    for n in notes:
        print("  note:", n)
    accounts = detect_hosts.draft_accounts(hosts)
    if interactive:
        print("\nAccounts found (identity claims only):")
        for k, v in accounts["accounts"].items():
            if v.get("provider") in ("openai", "anthropic"):
                print("  %-28s %-34s %s" % (k, v.get("label"), v.get("plan")))
        extra = ask("Add an SSH host to scan? (user@host or blank)", "")
        while extra:
            cfg["extra_hosts"].append({"name": extra.split("@")[-1].split(".")[0], "kind": "ssh", "ssh": extra, "python": "python3",
                                       "claude_roots": ["~/.claude"], "codex_roots": ["~/.codex"], "_comment": "edit roots in manifest.json"})
            extra = ask("Add another SSH host? (user@host or blank)", "")
    # write files
    os.makedirs(home_dir(), exist_ok=True)
    if fresh or not os.path.isfile(cfg["pricing_path"]):
        shutil.copy(os.path.join(SKILL, "templates", "pricing.json"), cfg["pricing_path"])
    if fresh or not os.path.isfile(cfg["accounts_path"]) or args.reinit:
        with open(cfg["accounts_path"], "w", encoding="utf-8") as fh:
            json.dump(accounts, fh, indent=2)
    write_manifest(cfg, hosts)
    write_report_config(cfg)
    if fresh or not cfg.get("initialized_at"):
        cfg["initialized_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_config(cfg)
    st = ledger_store.Store.open(cfg["store"]["kind"], cfg["store"]["path"])
    for k, v in cfg.items():
        st.set_pref(k, v)
    st.close()
    print("\nSaved preferences to %s" % config_path())
    print("Store: %s at %s" % (cfg["store"]["kind"], cfg["store"]["path"]))
    print("Manifest: %s (%d hosts)  Accounts: %s  Pricing: %s" % (cfg["manifest_path"], len(hosts) + len(cfg["extra_hosts"]), cfg["accounts_path"], cfg["pricing_path"]))
    print("Next: python3 scripts/ledger.py run")


def write_manifest(cfg, hosts):
    clean = []
    for h in hosts:
        clean.append({k: v for k, v in h.items() if not k.startswith("_")})
    clean += cfg.get("extra_hosts", [])
    m = {"_comment": "Generated by ledger.py from detect_hosts.py; hand-added hosts live in config.json extra_hosts and survive regeneration.",
         "workdir": cfg["workdir"], "snapshot_date": None, "timezone": cfg["timezone"], "package_prefix": cfg["package_prefix"],
         "pricing": cfg["pricing_path"], "accounts": cfg["accounts_path"], "report_config": cfg["report_config_path"], "hosts": clean}
    with open(cfg["manifest_path"], "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=2)


def write_report_config(cfg):
    b = cfg["branding"]
    rc = {"title": "AI coding-agent usage: token volume, caching and cost study", "html_title": "Agent Usage Study", "dashboard_title": "Agent Token Ledger",
          "prices_as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "theme_default": cfg.get("theme", "system"), "hosts": {}, "excluded_sources": [], "extra_limitations": [],
          "dashboard_excluded_note": "", "branding": b}
    with open(cfg["report_config_path"], "w", encoding="utf-8") as fh:
        json.dump(rc, fh, indent=2)


# ----------------------------------------------------------------------------
# run
# ----------------------------------------------------------------------------

def do_run(args):
    cfg = load_config()
    if cfg is None:
        print("No configuration yet; running onboarding with defaults (use `init` for the interactive version).")
        ns = argparse.Namespace(yes=True, reinit=False, set=[])
        onboard(ns)
        cfg = load_config()
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.time()
    if cfg["detect"].get("on_every_run", True) and not args.no_detect:
        hosts, _ = detect_hosts.detect_hosts(all_profiles=cfg["detect"]["all_profiles"], probe_wsl=cfg["detect"]["wsl"])
        write_manifest(cfg, hosts)
    write_report_config(cfg)
    work = cfg["workdir"]
    os.makedirs(work, exist_ok=True)
    py = sys.executable
    pipeline = os.path.join(HERE, "run_pipeline.py")
    if not args.no_scan:
        run([py, pipeline, "--manifest", cfg["manifest_path"], "--only", "scan"] + (["--hosts", args.hosts] if args.hosts else []))
    # append-only ingest
    st = ledger_store.Store.open(cfg["store"]["kind"], cfg["store"]["path"])
    added = {"events": 0, "sessions": 0, "prompts": 0}
    skipped = {"events": 0, "sessions": 0, "prompts": 0}
    scans = os.path.join(work, "scans")
    for hostdir in sorted(os.listdir(scans)) if os.path.isdir(scans) else []:
        d = os.path.join(scans, hostdir)
        for fn in sorted(os.listdir(d)):
            p = os.path.join(d, fn)
            if fn.startswith("events.") and fn.endswith(".jsonl"):
                a, s = st.ingest_events_file(p)
                added["events"] += a
                skipped["events"] += s
            elif fn.startswith("sessions.") and fn.endswith(".jsonl"):
                a, s = st.ingest_sessions_file(p)
                added["sessions"] += a
                skipped["sessions"] += s
            elif fn.startswith("prompts.") and fn.endswith(".jsonl"):
                a, s = st.ingest_prompts_file(p)
                added["prompts"] += a
                skipped["prompts"] += s
    print("store: added %s, already present %s" % (json.dumps(added), json.dumps(skipped)))
    # materialise the whole store for the report step, then analyse and build
    export_dir = os.path.join(work, "store-export")
    paths = ledger_store.export_jsonl(st, export_dir)
    counts = st.counts()
    compiled = os.path.join(work, "compiled")
    inv = os.path.join(scans, "*", "inventory.*.json")
    run([py, os.path.join(HERE, "compile_ai_logs.py"), "report", "--events", paths["events"][0], "--sessions", paths["sessions"][0], "--prompts", paths["prompts"][0],
         "--inventory", inv, "--pricing", cfg["pricing_path"], "--accounts", cfg["accounts_path"], "--out-dir", compiled])
    run([py, pipeline, "--manifest", cfg["manifest_path"], "--only", "analyze,build"])
    meta = {"started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "seconds": round(time.time() - t0, 1),
            "added": added, "skipped": skipped, "store_counts": counts, "workdir": work}
    st.record_run(meta)
    st.close()
    print("run recorded: %s events in store (%s added this run), %.0fs" % (counts["events"], added["events"], meta["seconds"]))


def do_status(args):
    cfg = load_config()
    if cfg is None:
        print("not initialised; run: python3 scripts/ledger.py init")
        return
    st = ledger_store.Store.open(cfg["store"]["kind"], cfg["store"]["path"])
    print("config:   %s (initialised %s)" % (config_path(), cfg.get("initialized_at")))
    print("store:    %s  %s" % (cfg["store"]["kind"], cfg["store"]["path"]))
    print("counts:   %s" % json.dumps(st.counts()))
    lr = st.last_run()
    print("last run: %s" % (json.dumps({k: lr[k] for k in ("finished_at", "seconds", "added") if k in lr}) if lr else "never"))
    print("workdir:  %s" % cfg["workdir"])
    print("brand:    %s · %s · accent %s · theme %s" % (cfg["branding"].get("name"), cfg["branding"].get("tagline"), cfg["branding"].get("accent"), cfg.get("theme")))
    try:
        with open(cfg["manifest_path"], encoding="utf-8") as fh:
            m = json.load(fh)
        print("hosts:    %s" % ", ".join("%s(%s)" % (h["name"], h.get("kind")) for h in m.get("hosts", [])))
    except Exception:
        print("hosts:    manifest not written yet")
    st.close()


def do_export(args):
    cfg = load_config()
    if cfg is None:
        raise SystemExit("not initialised; run init first")
    st = ledger_store.Store.open(cfg["store"]["kind"], cfg["store"]["path"])
    n = ledger_store.export_table(st, args.table, args.format, args.out)
    st.close()
    print("wrote %d %s to %s" % (n, args.table, args.out))


def do_reinit(args):
    cfg = load_config()
    if cfg and os.path.exists(cfg["store"]["path"]):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        moved = cfg["store"]["path"].rstrip("/\\") + ".before-reinit-" + stamp
        shutil.move(cfg["store"]["path"], moved)
        print("previous store kept at %s" % moved)
    args.reinit = True
    onboard(args)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="first-run onboarding")
    i.add_argument("--yes", action="store_true", help="accept defaults without prompting (for agents and CI)")
    i.add_argument("--set", action="append", help="override a preference, e.g. --set brand.name=Acme --set store.kind=json")
    i.add_argument("--reinit", action="store_true", help=argparse.SUPPRESS)
    i.set_defaults(fn=onboard)
    r = sub.add_parser("run", help="scan, append to the store, rebuild dashboard and study")
    r.add_argument("--hosts", help="comma list of host names to scan")
    r.add_argument("--no-scan", action="store_true", help="rebuild from the store without rescanning")
    r.add_argument("--no-detect", action="store_true", help="do not refresh the manifest from detection")
    r.set_defaults(fn=do_run)
    s = sub.add_parser("status")
    s.set_defaults(fn=do_status)
    e = sub.add_parser("export")
    e.add_argument("--table", default="events", choices=["events", "sessions", "prompts"])
    e.add_argument("--format", default="csv", choices=["csv", "json", "jsonl"])
    e.add_argument("--out", required=True)
    e.set_defaults(fn=do_export)
    ri = sub.add_parser("reinit", help="fresh onboarding; the previous store is kept with a timestamp")
    ri.add_argument("--yes", action="store_true")
    ri.add_argument("--set", action="append")
    ri.set_defaults(fn=do_reinit)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
