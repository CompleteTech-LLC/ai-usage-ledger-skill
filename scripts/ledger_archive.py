#!/usr/bin/env python3
"""
ledger_archive.py - keep the raw agent logs themselves, not just the numbers derived from them.

Harness-agnostic by construction: the archive does not know what a Codex rollout or a Cline task folder is. It
archives every source file the scanners actually read (the `src` on each event and the `file` on each session,
whatever the tool), plus the tools' own counters found next to those files (stats-cache.json, state_5.sqlite,
history.jsonl). A new parser therefore gets archived automatically.

Layout:  <archive>/<host>/<path with the drive or share prefix folded in>[.gz]
Index:   <archive>/index.sqlite  (files: host, path, size, mtime, sha256, archived_at, versions)

Append-only: a file is copied when it is new or has grown/changed; earlier bytes are never rewritten by the
tools (their logs are append-only), so the latest copy is a superset. Nothing is deleted here.

    python3 ledger_archive.py --archive ~/.ai-usage-ledger/archive status
    python3 ledger_archive.py --archive ... list [--host h] [--grep-path codex]
    python3 ledger_archive.py --archive ... grep "pattern" [--host h] [--since 2026-08-01] [--limit 50]
    python3 ledger_archive.py --archive ... restore --host h --to /tmp/restored [--match sessions/2026/08]

Standard library only. Remote (ssh) hosts are pulled with `ssh <host> tar czf - -T -`.
"""
import argparse
import glob
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone

COUNTER_FILES = ("stats-cache.json", "state_5.sqlite", "history.jsonl", "session-store.db", "auth.json.NEVER")  # auth files are never archived


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rel_path(path):
    """Fold a native path into an archive-relative path: C:\\Users\\x -> C/Users/x ; //wsl$/Ubuntu/home/x -> home/x ; /home/x -> home/x."""
    p = path.replace("\\", "/")
    m = re.match(r"^//wsl\$/[^/]+/(.*)$", p)
    if m:
        return m.group(1)
    m = re.match(r"^//([^/]+)/(.*)$", p)  # other UNC shares: keep the server name
    if m:
        return "unc-%s/%s" % (m.group(1), m.group(2))
    m = re.match(r"^([A-Za-z]):/(.*)$", p)
    if m:
        return "%s/%s" % (m.group(1).upper(), m.group(2))
    return p.lstrip("/")


def collect_sources(scans_dir, host_name):
    """Every distinct source file the scanners read for one host, plus counters beside the roots."""
    srcs = set()
    d = os.path.join(scans_dir, host_name)
    for pat in ("events.*.jsonl", "sessions.*.jsonl"):
        for p in glob.glob(os.path.join(d, pat)):
            with open(p, "rb") as fh:
                for raw in fh:
                    try:
                        row = json.loads(raw)
                    except Exception:
                        continue
                    s = row.get("src") or row.get("file")
                    if s:
                        srcs.add(s)
    roots = set()
    for p in glob.glob(os.path.join(d, "inventory.*.json")):
        try:
            inv = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        for r in inv.get("roots", []):
            if r.get("root"):
                roots.add(r["root"])
    return srcs, roots


class Archive:
    def __init__(self, path, compress=True):
        self.path = path
        self.compress = compress
        os.makedirs(path, exist_ok=True)
        self.db = sqlite3.connect(os.path.join(path, "index.sqlite"))
        self.db.execute("CREATE TABLE IF NOT EXISTS files (host TEXT, path TEXT, rel TEXT, size INTEGER, mtime REAL, sha256 TEXT, archived_at TEXT, versions INTEGER DEFAULT 1, PRIMARY KEY (host, path))")
        self.db.execute("CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, host TEXT, started_at TEXT, finished_at TEXT, files_new INTEGER, files_updated INTEGER, bytes INTEGER, note TEXT)")
        self.db.commit()

    # ---- helpers --------------------------------------------------------------
    def _known(self, host):
        return {row[0]: (row[1], row[2]) for row in self.db.execute("SELECT path, size, mtime FROM files WHERE host=?", (host,))}

    def dest_for(self, host, path):
        rel = rel_path(path)
        return os.path.join(self.path, host, rel + (".gz" if self.compress else "")), rel

    def _write(self, host, path, data, size, mtime, sha, existed):
        dest, rel = self.dest_for(host, path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".part"
        if self.compress:
            with gzip.open(tmp, "wb", compresslevel=6) as fh:
                fh.write(data)
        else:
            with open(tmp, "wb") as fh:
                fh.write(data)
        os.replace(tmp, dest)
        if existed:
            self.db.execute("UPDATE files SET size=?, mtime=?, sha256=?, archived_at=?, versions=versions+1, rel=? WHERE host=? AND path=?", (size, mtime, sha, now(), rel, host, path))
        else:
            self.db.execute("INSERT INTO files (host, path, rel, size, mtime, sha256, archived_at) VALUES (?,?,?,?,?,?,?)", (host, path, rel, size, mtime, sha, now()))

    # ---- local / share / wsl-share -------------------------------------------
    def archive_local(self, host, paths, prefix="", log=print):
        """paths are native paths on that host; prefix (e.g. //wsl$/Ubuntu) makes them readable here."""
        known = self._known(host)
        new = upd = nbytes = 0
        started = now()
        for p in sorted(paths):
            local = (prefix.rstrip("/\\") + p) if prefix and not p.startswith(prefix) else p
            if os.path.basename(p).lower() in ("auth.json", ".credentials.json", "credentials.json"):
                continue
            try:
                st = os.stat(local)
            except OSError:
                continue
            if not os.path.isfile(local):
                continue
            prev = known.get(p)
            if prev and prev[0] == st.st_size and abs(prev[1] - st.st_mtime) < 1:
                continue
            try:
                with open(local, "rb") as fh:
                    data = fh.read()
            except OSError as ex:
                log("  skip %s: %s" % (p, ex))
                continue
            sha = hashlib.sha256(data).hexdigest()
            self._write(host, p, data, st.st_size, st.st_mtime, sha, existed=prev is not None)
            nbytes += st.st_size
            if prev:
                upd += 1
            else:
                new += 1
            if (new + upd) % 200 == 0:
                self.db.commit()
                log("  %s: %d new, %d updated, %.2f GB" % (host, new, upd, nbytes / 1e9))
        self.db.execute("INSERT INTO runs (host, started_at, finished_at, files_new, files_updated, bytes) VALUES (?,?,?,?,?,?)", (host, started, now(), new, upd, nbytes))
        self.db.commit()
        return new, upd, nbytes

    # ---- ssh ------------------------------------------------------------------
    def archive_ssh(self, host, ssh, paths, log=print):
        """Pull the listed files in one tar stream; the remote side needs tar and ssh access only."""
        known = self._known(host)
        wanted = sorted(p for p in paths if os.path.basename(p).lower() not in ("auth.json", ".credentials.json"))
        if not wanted:
            return 0, 0, 0
        # ask for size+mtime first so unchanged files are not transferred. The remote command is a small shell
        # script fed on stdin (no quoting through Windows argv); the file list travels inside a quoted heredoc.
        listing = "\n".join(wanted)
        stat_script = "while IFS= read -r f; do [ -f \"$f\" ] && stat -c '%s %Y %n' -- \"$f\" 2>/dev/null; done <<'AI_USAGE_LEDGER_EOF'\n" + listing + "\nAI_USAGE_LEDGER_EOF\nexit 0\n"
        # bytes, not text mode: on Windows text mode would turn the newlines into CRLF and break every path
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", ssh, "sh"], input=stat_script.encode("utf-8"), capture_output=True)
        if r.returncode != 0:
            log("  ssh stat failed for %s: %s" % (host, r.stderr.decode("utf-8", "replace")[-300:]))
        remote = {}
        for line in r.stdout.decode("utf-8", "replace").splitlines():
            parts = line.split(" ", 2)
            if len(parts) == 3:
                remote[parts[2]] = (int(parts[0]), float(parts[1]))
        todo = [p for p in wanted if p in remote and not (known.get(p) and known[p][0] == remote[p][0] and abs(known[p][1] - remote[p][1]) < 1)]
        if not todo:
            return 0, 0, 0
        started = now()
        tar_script = "tar czf - -T - <<'AI_USAGE_LEDGER_EOF'\n" + "\n".join(todo) + "\nAI_USAGE_LEDGER_EOF\n"
        proc = subprocess.Popen(["ssh", "-o", "BatchMode=yes", ssh, "sh"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate(input=tar_script.encode("utf-8"))
        if proc.returncode not in (0, 1):  # 1 = some files changed while reading; acceptable for append-only logs
            log("  ssh tar failed for %s: %s" % (host, err.decode("utf-8", "replace")[-300:]))
            return 0, 0, 0
        new = upd = nbytes = 0
        with tarfile.open(fileobj=io.BytesIO(out), mode="r:gz") as tf:
            for m in tf:
                if not m.isfile():
                    continue
                p = "/" + m.name.lstrip("./") if not m.name.startswith("/") else m.name
                data = tf.extractfile(m).read()
                sha = hashlib.sha256(data).hexdigest()
                prev = known.get(p)
                size, mtime = remote.get(p, (len(data), m.mtime))
                self._write(host, p, data, size, mtime, sha, existed=prev is not None)
                nbytes += len(data)
                if prev:
                    upd += 1
                else:
                    new += 1
        self.db.execute("INSERT INTO runs (host, started_at, finished_at, files_new, files_updated, bytes) VALUES (?,?,?,?,?,?)", (host, started, now(), new, upd, nbytes))
        self.db.commit()
        return new, upd, nbytes

    # ---- reading back ----------------------------------------------------------
    def status(self):
        rows = self.db.execute("SELECT host, COUNT(*), SUM(size), MAX(archived_at) FROM files GROUP BY host ORDER BY host").fetchall()
        on_disk = 0
        for dp, _, fns in os.walk(self.path):
            for fn in fns:
                if fn != "index.sqlite":
                    on_disk += os.path.getsize(os.path.join(dp, fn))
        return {"hosts": [{"host": h, "files": n, "bytes_original": s or 0, "last_archived": la} for h, n, s, la in rows], "bytes_on_disk": on_disk, "path": self.path, "compressed": self.compress}

    def list(self, host=None, grep_path=None):
        q = "SELECT host, path, size, mtime, archived_at, versions FROM files"
        args = []
        if host:
            q += " WHERE host=?"
            args.append(host)
        for row in self.db.execute(q + " ORDER BY host, path", args):
            if grep_path and grep_path.lower() not in row[1].lower():
                continue
            yield {"host": row[0], "path": row[1], "size": row[2], "mtime": datetime.fromtimestamp(row[3]).isoformat(timespec="seconds"), "archived_at": row[4], "versions": row[5]}

    def open(self, host, path):
        dest, _ = self.dest_for(host, path)
        return gzip.open(dest, "rb") if self.compress else open(dest, "rb")

    def grep(self, pattern, host=None, since=None, until=None, path_filter=None, limit=100, context=160, ignore_case=True):
        """Search inside the archived logs. Dates come from a timestamp-looking field on the matching line when there is one."""
        rx = re.compile(pattern.encode("utf-8"), re.IGNORECASE if ignore_case else 0)
        ts_rx = re.compile(rb'"(?:timestamp|ts|created_at|createdAt|time)"\s*:\s*"?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}[^"]*)"?')
        n = 0
        for f in self.list(host):
            if path_filter and path_filter.lower() not in f["path"].lower():
                continue
            if since and f["mtime"][:10] < since:
                continue
            try:
                with self.open(f["host"], f["path"]) as fh:
                    for lineno, line in enumerate(fh, 1):
                        m = rx.search(line)
                        if not m:
                            continue
                        tm = ts_rx.search(line)
                        ts = tm.group(1).decode("utf-8", "replace")[:19] if tm else ""
                        if since and ts and ts[:10] < since:
                            continue
                        if until and ts and ts[:10] > until:
                            continue
                        a = max(0, m.start() - context // 2)
                        snippet = line[a:a + context].decode("utf-8", "replace").replace("\n", " ")
                        yield {"host": f["host"], "path": f["path"], "line": lineno, "ts": ts, "snippet": snippet}
                        n += 1
                        if n >= limit:
                            return
            except (OSError, EOFError) as ex:
                yield {"host": f["host"], "path": f["path"], "line": 0, "ts": "", "snippet": "unreadable: %s" % ex}

    def restore(self, host, to, match=None):
        n = 0
        for f in self.list(host, match):
            dest = os.path.join(to, host, f["path"] and rel_path(f["path"]))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with self.open(host, f["path"]) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            n += 1
        return n

    def close(self):
        self.db.close()


def archive_from_scans(archive, hosts, scans_dir, log=print):
    """Archive every source the last scan touched, per host, using the host kind from the manifest."""
    summary = {}
    for h in hosts:
        name = h["name"]
        srcs, roots = collect_sources(scans_dir, name)
        for r in roots:  # counters that sit beside the roots
            for fn in COUNTER_FILES:
                if fn.endswith(".NEVER"):
                    continue
                srcs.add(os.path.join(r, fn).replace("\\", "/") if "/" in r else os.path.join(r, fn))
        if not srcs:
            continue
        t0 = time.time()
        kind = h.get("kind", "local")
        if kind == "ssh":
            res = archive.archive_ssh(name, h["ssh"], srcs, log)
        elif kind == "wsl":
            share = h.get("share_fallback") or ("//wsl$/%s" % h.get("distro", "Ubuntu"))
            res = archive.archive_local(name, srcs, prefix=share, log=log)
        else:
            res = archive.archive_local(name, srcs, log=log)
        summary[name] = {"new": res[0], "updated": res[1], "bytes": res[2], "seconds": round(time.time() - t0, 1)}
        log("archive %s: %d new, %d updated, %.2f GB in %.0fs" % (name, res[0], res[1], res[2] / 1e9, time.time() - t0))
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive", required=True, help="archive directory")
    ap.add_argument("--no-compress", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    ls = sub.add_parser("list")
    ls.add_argument("--host")
    ls.add_argument("--grep-path")
    g = sub.add_parser("grep")
    g.add_argument("pattern")
    g.add_argument("--host")
    g.add_argument("--since")
    g.add_argument("--until")
    g.add_argument("--path", dest="path_filter")
    g.add_argument("--limit", type=int, default=100)
    g.add_argument("--json", action="store_true")
    rs = sub.add_parser("restore")
    rs.add_argument("--host", required=True)
    rs.add_argument("--to", required=True)
    rs.add_argument("--match")
    a = ap.parse_args()
    ar = Archive(a.archive, compress=not a.no_compress)
    if a.cmd == "status":
        print(json.dumps(ar.status(), indent=2))
    elif a.cmd == "list":
        for f in ar.list(a.host, a.grep_path):
            print("%-14s %10d  %s  v%d  %s" % (f["host"], f["size"], f["mtime"], f["versions"], f["path"]))
    elif a.cmd == "grep":
        for hit in ar.grep(a.pattern, a.host, a.since, a.until, a.path_filter, a.limit):
            if a.json:
                print(json.dumps(hit))
            else:
                print("%s  %s:%d  %s\n    %s" % (hit["ts"] or "----------T--:--:--", hit["path"], hit["line"], hit["host"], hit["snippet"]))
    elif a.cmd == "restore":
        print("restored %d files under %s" % (ar.restore(a.host, a.to, a.match), a.to))
    ar.close()


if __name__ == "__main__":
    sys.exit(main())
