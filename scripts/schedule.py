#!/usr/bin/env python3
"""
schedule.py - install, remove or inspect the scheduled `ledger.py run` on this machine.

    python3 schedule.py install --frequency daily --time 03:00 [--weekday mon] [--dry-run]
    python3 schedule.py remove [--dry-run]
    python3 schedule.py status

Windows uses Task Scheduler (schtasks, task name "AI Usage Ledger"); Linux, WSL and macOS use the user's crontab
(one line tagged `# ai-usage-ledger`). Each backend runs a small wrapper written to the ledger home
(run-ledger.cmd or run-ledger.sh) that appends output to <home>/logs/run.log, so the command line stays simple
and the wrapper can be edited by hand. Nothing here needs elevation. macOS may additionally require granting
cron Full Disk Access for the tools' directories; the status output says so.

Standard library only.
"""
import argparse
import os
import shlex
import subprocess
import sys

TASK_NAME = "AI Usage Ledger"
MARK = "# ai-usage-ledger"
IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
HERE = os.path.dirname(os.path.abspath(__file__))
WEEKDAYS = {"mon": ("MON", 1), "tue": ("TUE", 2), "wed": ("WED", 3), "thu": ("THU", 4), "fri": ("FRI", 5), "sat": ("SAT", 6), "sun": ("SUN", 0)}


def parse_time(t):
    hh, mm = (t or "03:00").split(":")
    return int(hh) % 24, int(mm) % 60


def wrapper_path(home):
    return os.path.join(home, "run-ledger.cmd" if IS_WIN else "run-ledger.sh")


def write_wrapper(home, python, extra_args=""):
    os.makedirs(os.path.join(home, "logs"), exist_ok=True)
    ledger = os.path.join(HERE, "ledger.py")
    log = os.path.join(home, "logs", "run.log")
    p = wrapper_path(home)
    if IS_WIN:
        body = '@echo off\r\nset "AI_USAGE_LEDGER_HOME=%s"\r\necho [%%date%% %%time%%] scheduled run >> "%s"\r\n"%s" "%s" run %s >> "%s" 2>&1\r\n' % (home, log, python, ledger, extra_args, log)
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(body)
    else:
        body = "#!/bin/sh\nexport AI_USAGE_LEDGER_HOME=%s\necho \"[$(date -Iseconds)] scheduled run\" >> %s\n%s %s run %s >> %s 2>&1\n" % (
            shlex.quote(home), shlex.quote(log), shlex.quote(python), shlex.quote(ledger), extra_args, shlex.quote(log))
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        os.chmod(p, 0o755)
    return p


def _run(cmd, dry_run=False, input_text=None):
    print("$ " + (" ".join(shlex.quote(c) for c in cmd) if not IS_WIN else " ".join('"%s"' % c if " " in c else c for c in cmd)))
    if dry_run:
        return 0, ""
    r = subprocess.run(cmd, capture_output=True, text=True, input=input_text)
    if r.returncode != 0:
        sys.stderr.write((r.stderr or r.stdout or "").strip() + "\n")
    return r.returncode, r.stdout


def crontab_lines():
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if r.returncode != 0:
        return []
    return [line for line in r.stdout.splitlines()]


def install(home, python, frequency, time_, weekday="mon", extra_args="", dry_run=False):
    hh, mm = parse_time(time_)
    wrapper = write_wrapper(home, python, extra_args) if not dry_run else wrapper_path(home)
    if frequency == "none":
        return remove(home, dry_run)
    if IS_WIN:
        cmd = ["schtasks", "/Create", "/F", "/TN", TASK_NAME, "/TR", '"%s"' % wrapper, "/ST", "%02d:%02d" % (hh, mm)]
        if frequency == "daily":
            cmd += ["/SC", "DAILY"]
        elif frequency == "weekly":
            cmd += ["/SC", "WEEKLY", "/D", WEEKDAYS.get(weekday, WEEKDAYS["mon"])[0]]
        elif frequency == "monthly":
            cmd += ["/SC", "MONTHLY", "/D", "1"]
        else:
            raise SystemExit("frequency must be none, daily, weekly or monthly")
        rc, _ = _run(cmd, dry_run)
        return rc
    spec = {"daily": "%d %d * * *", "weekly": "%d %d * * " + str(WEEKDAYS.get(weekday, WEEKDAYS["mon"])[1]), "monthly": "%d %d 1 * *"}.get(frequency)
    if not spec:
        raise SystemExit("frequency must be none, daily, weekly or monthly")
    line = "%s %s %s" % (spec % (mm, hh), shlex.quote(wrapper), MARK)
    keep = [x for x in crontab_lines() if MARK not in x] if not dry_run else []
    new = "\n".join(keep + [line]) + "\n"
    print("crontab line: " + line)
    rc, _ = _run(["crontab", "-"], dry_run, input_text=new)
    if IS_MAC and rc == 0:
        print("macOS: if the run log shows permission errors, grant cron (or your terminal) Full Disk Access in System Settings > Privacy & Security.")
    return rc


def remove(home, dry_run=False):
    if IS_WIN:
        rc, _ = _run(["schtasks", "/Delete", "/F", "/TN", TASK_NAME], dry_run)
        return 0 if rc in (0, 1) else rc  # 1 = task did not exist
    keep = [x for x in crontab_lines() if MARK not in x]
    rc, _ = _run(["crontab", "-"], dry_run, input_text="\n".join(keep) + ("\n" if keep else ""))
    return rc


def status(home):
    if IS_WIN:
        r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"], capture_output=True, text=True)
        if r.returncode != 0:
            print("scheduled task: not installed")
            return 1
        want = ("Task To Run", "Schedule Type", "Start Time", "Days", "Last Run Time", "Last Result", "Next Run Time", "Status")
        for line in r.stdout.splitlines():
            if any(line.strip().startswith(w) for w in want):
                print("  " + line.strip())
        return 0
    lines = [x for x in crontab_lines() if MARK in x]
    if not lines:
        print("cron entry: not installed")
        return 1
    for x in lines:
        print("  " + x)
    log = os.path.join(home, "logs", "run.log")
    if os.path.isfile(log):
        with open(log, encoding="utf-8", errors="replace") as fh:
            tail = fh.readlines()[-3:]
        print("  last log lines: " + "".join(tail).strip().replace("\n", " | "))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", default=os.path.expanduser(os.environ.get("AI_USAGE_LEDGER_HOME") or "~/.ai-usage-ledger"))
    ap.add_argument("--python", default=sys.executable)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("install")
    i.add_argument("--frequency", default="daily", choices=["none", "daily", "weekly", "monthly"])
    i.add_argument("--time", default="03:00", help="HH:MM local time")
    i.add_argument("--weekday", default="mon", choices=sorted(WEEKDAYS))
    i.add_argument("--extra-args", default="", help="appended to `ledger.py run`, e.g. --anonymize")
    i.add_argument("--dry-run", action="store_true", help="print the command without changing anything")
    r = sub.add_parser("remove")
    r.add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    a = ap.parse_args()
    if a.cmd == "install":
        return install(a.home, a.python, a.frequency, a.time, a.weekday, a.extra_args, a.dry_run)
    if a.cmd == "remove":
        return remove(a.home, a.dry_run)
    return status(a.home)


if __name__ == "__main__":
    sys.exit(main())
