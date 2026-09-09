#!/usr/bin/env python3
"""
safety.py - input validation shared by the pipeline, renderers and scheduler.

Everything the skill executes or renders is built from operator-controlled files (manifest, config, branding).
Those files are trusted input, but a value with shell syntax, HTML or a stray newline must stay literal rather
than become a command or markup. This module is the single place that enforces it:

  check_path(value, what)          no NUL, newline or other control characters in a path or argument
  validate_ssh_host(host)          ssh target, remote_tmp and python interpreter grammar for SSH hosts
  validate_wsl_host(host)          distro name and python interpreter grammar for WSL hosts
  warn_if_writable(path)           POSIX: warn when a config file is group- or world-writable
  sanitize_branding(b, base_dir)   escaped text, validated colours/tokens/fonts, local-only logo, opt-in extra CSS
  CSP_META                         a restrictive Content-Security-Policy for every generated HTML page

Standard library only.
"""
import html
import os
import re
import stat
import sys

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
SSH_TARGET_RE = re.compile(r"^(?:[A-Za-z0-9._-]+@)?[A-Za-z0-9][A-Za-z0-9._-]*$")
REMOTE_PATH_RE = re.compile(r"^/[A-Za-z0-9._/-]+$")
INTERPRETER_RE = re.compile(r"^(?:python3?(?:\.\d+)?|/[A-Za-z0-9._/-]+/python3?(?:\.\d+)?)$")
DISTRO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
COLOR_RE = re.compile(r"^(?:#[0-9A-Fa-f]{3,8}|[A-Za-z]{3,30}|(?:rgb|rgba|hsl|hsla)\([0-9.,%\s]+\))$")
CSS_TOKEN_NAME_RE = re.compile(r"^[a-z0-9-]{1,40}$")
CSS_TOKEN_VALUE_RE = re.compile(r"^[A-Za-z0-9#%.,()\s'\"-]{1,120}$")
FONT_RE = re.compile(r"^[A-Za-z0-9 ,'\"-]{1,120}$")
_CSS_FORBIDDEN = re.compile(r"</|@import|url\s*\(|expression\s*\(|javascript:|behavior\s*:|-moz-binding", re.IGNORECASE)

# inline styles and scripts are what the self-contained pages are made of; nothing may be fetched from anywhere
CSP_META = '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'; img-src data:; font-src data:; connect-src \'none\'; frame-ancestors \'none\'; form-action \'none\'">'
CSP_META_EXTERNAL = '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\' https://fonts.googleapis.com; script-src \'unsafe-inline\'; img-src data: https:; font-src data: https://fonts.gstatic.com; connect-src \'none\'; frame-ancestors \'none\'; form-action \'none\'">'


class UnsafeValue(SystemExit):
    pass


def check_path(value, what="path"):
    """Reject control characters (NUL, newline, ...) in anything that becomes a path or a command argument."""
    if value is None:
        return value
    s = str(value)
    if _CONTROL.search(s):
        raise UnsafeValue("%s contains a control character and was refused: %r" % (what, s[:80]))
    if s.startswith("-") and what != "argument":
        raise UnsafeValue("%s must not start with '-' (looks like an option): %r" % (what, s[:80]))
    return s


def validate_ssh_host(host):
    """SSH hosts: the target, the remote scratch directory and the interpreter are passed to a remote shell."""
    target = str(host.get("ssh") or "")
    if not SSH_TARGET_RE.match(target):
        raise UnsafeValue("ssh target must be host or user@host without options or spaces: %r" % target)
    remote_tmp = str(host.get("remote_tmp") or "/tmp/ai-usage-ledger")
    if not REMOTE_PATH_RE.match(remote_tmp) or ".." in remote_tmp:
        raise UnsafeValue("remote_tmp must be an absolute path of [A-Za-z0-9._/-]: %r" % remote_tmp)
    python = str(host.get("python") or "python3")
    if not INTERPRETER_RE.match(python):
        raise UnsafeValue("python must be python3, python, python3.N or an absolute path to one: %r" % python)
    return target, remote_tmp, python


def validate_wsl_host(host):
    distro = str(host.get("distro") or "Ubuntu")
    if not DISTRO_RE.match(distro):
        raise UnsafeValue("WSL distro name is not plain: %r" % distro)
    python = str(host.get("python") or "python3")
    if not INTERPRETER_RE.match(python):
        raise UnsafeValue("python must be python3, python, python3.N or an absolute path to one: %r" % python)
    return distro, python


def warn_if_writable(path, log=None):
    """Manifests and configs are executable configuration; say so when others could edit them."""
    if os.name == "nt" or not path or not os.path.exists(path):
        return False
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return False
    if mode & (stat.S_IWGRP | stat.S_IWOTH):
        msg = "warning: %s is group- or world-writable; anyone who can edit it controls what this skill runs" % path
        (log or (lambda m: sys.stderr.write(m + "\n")))(msg)
        return True
    return False


def _text(v):
    return html.escape(str(v), quote=True) if v is not None else ""


def sanitize_branding(b, base_dir=None, logo_to_data_uri=None):
    """Return a branding dict safe to interpolate into HTML/CSS. Invalid values are dropped with a warning, never passed through."""
    b = dict(b or {})
    out = {}
    warnings = []
    for k in ("name", "eyebrow", "tagline", "contact", "footer"):
        if b.get(k):
            out[k] = _text(b[k])
    if b.get("accent"):
        if COLOR_RE.match(str(b["accent"]).strip()):
            out["accent"] = str(b["accent"]).strip()
        else:
            warnings.append("branding.accent is not a colour and was ignored: %r" % str(b["accent"])[:40])
    for k in ("font_display", "font_body", "font_mono"):
        if b.get(k):
            if FONT_RE.match(str(b[k])):
                out[k] = str(b[k])
            else:
                warnings.append("branding.%s is not a font family list and was ignored" % k)
    for theme in ("light", "dark"):
        tokens = {}
        for name, value in (b.get(theme) or {}).items():
            if CSS_TOKEN_NAME_RE.match(str(name)) and CSS_TOKEN_VALUE_RE.match(str(value)) and not _CSS_FORBIDDEN.search(str(value)):
                tokens[str(name)] = str(value)
            else:
                warnings.append("branding.%s.%s was ignored (not a plain CSS value)" % (theme, str(name)[:40]))
        if tokens:
            out[theme] = tokens
    allow_external = bool(b.get("allow_external_resources"))
    logo = b.get("logo")
    if logo:
        s = str(logo)
        if s.startswith("data:image/"):
            out["logo"] = s
        elif s.startswith(("http://", "https://")):
            if allow_external and s.startswith("https://"):
                out["logo"] = _text(s)
            else:
                warnings.append("branding.logo is a remote URL; set allow_external_resources: true to load it, or point it at a local file")
        else:
            uri = logo_to_data_uri(s, base_dir) if logo_to_data_uri else None
            if uri and str(uri).startswith("data:"):
                out["logo"] = uri
            else:
                warnings.append("branding.logo file not found and was ignored: %r" % s[:80])
    if b.get("google_fonts_url"):
        u = str(b["google_fonts_url"])
        if allow_external and u.startswith("https://fonts.googleapis.com/") and not _CONTROL.search(u):
            out["google_fonts_url"] = _text(u)
        else:
            warnings.append("branding.google_fonts_url ignored: pages are self-contained unless allow_external_resources is true and the URL is on fonts.googleapis.com")
    if b.get("extra_css"):
        css = str(b["extra_css"])
        if b.get("unsafe_extra_css") and not _CSS_FORBIDDEN.search(css):
            out["extra_css"] = css
        else:
            warnings.append("branding.extra_css ignored: set unsafe_extra_css: true and avoid </, @import, url(), expression()")
    out["allow_external_resources"] = allow_external
    out["_warnings"] = warnings
    for w in warnings:
        sys.stderr.write("branding: %s\n" % w)
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(sanitize_branding(json.loads(sys.stdin.read() or "{}")), indent=2))
