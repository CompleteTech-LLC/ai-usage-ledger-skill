# Finding the logs and the accounts

`scripts/detect_hosts.py` does the routine part of this automatically and `ledger.py init` runs it during onboarding. Read on for what it looks for, what it cannot see, and how to check its output.

## What the detector covers

| Platform | Home directories | Extra locations |
|---|---|---|
| Windows | `%USERPROFILE%`; with `--all-profiles` every `<drive>:\Users\<name>` on every mounted drive | `%APPDATA%\{Code, Code - Insiders, VSCodium, Cursor, Windsurf, Trae, Kiro, Antigravity}\User\globalStorage` for Cline / Roo / Kilo; `%LOCALAPPDATA%` tools |
| WSL | every distro from `wsl.exe -l -q` (Docker distros skipped), every `/home/<name>` reached through `\\wsl$\<distro>` | `~/.vscode-server/data/User/globalStorage`, `~/.cursor-server/...` for remote-mode extensions; the distro path is written to the manifest with the share as `share_fallback` |
| macOS | `~`; with `--all-profiles` every `/Users/<name>` | `~/Library/Application Support/<editor>/User/globalStorage` |
| Linux | `~`; with `--all-profiles` every `/home/<name>` | `~/.config/<editor>/User/globalStorage`, `~/.vscode-server/...` |

Per home it checks, in order: `CODEX_HOME` or `~/.codex` (needs `sessions/` or `archived_sessions/`; `state_5.sqlite` noted), `~/.claude` (needs `projects/`; `stats-cache.json` noted), `COPILOT_HOME` or `~/.copilot/session-state`, `GEMINI_DATA_DIR` or `~/.gemini/tmp`, `QWEN_DATA_DIR` or `~/.qwen/history`, `KIMI_DATA_DIR` / `KIMI_SHARE_DIR` / `~/.kimi` / `~/.kimi-code`, `VIBE_HOME` or `~/.vibe/logs/session`, `~/.continue/dev_data`, `PI_AGENT_DIR` or `~/.pi/agent/sessions`, `OPENCODE_DATA_DIR` or `~/.local/share/opencode/opencode.db`, `OPENCLAW_DIR` or `~/.openclaw/agents`, the Cline family under each editor's global storage and `~/.cline`, and generic roots for Codebuff (`~/.config/manicode`), Droid (`~/.factory/sessions`), Amp, LM Studio, OpenHands, Grok, Hermes and Zcode. Environment overrides apply only to the profile the detector runs as.

Two profiles that resolve to the same directory (a mapped or `subst` drive letter, a bind mount, a symlinked home) are reported once; the note `same volume as an already detected profile` explains the skip. Without that rule every call would be stored twice under two host names.

What it does not do: read anything that needs elevation, follow SSH (name those hosts at the prompt or in `config.json` `extra_hosts`), or find gateway logs kept outside a home directory (`/srv`, `/opt`, containers). Use the sweep below for those and add them to the manifest by hand.

Enumerate every user profile on every drive and host; the interesting material is often in an old profile backup or a second OS on the same box.

## Where each tool keeps usage

| Tool | Per-call records (class A) | Tool's own counter (class B) | Prompts | Credentials / account |
|---|---|---|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` | `~/.claude/stats-cache.json` | `~/.claude/history.jsonl` | `~/.claude.json` (`oauthAccount.emailAddress`, `organizationRateLimitTier`), `~/.claude/.credentials.json` (`subscriptionType`, `rateLimitTier`) |
| Codex (CLI, Desktop, VS Code) | `~/.codex/sessions/**/rollout-*.jsonl`, `~/.codex/archived_sessions/` | `~/.codex/state_5.sqlite` | `~/.codex/history.jsonl` | `~/.codex/auth.json` (id_token claims), saved copies in `~/.codex-auths/`, registries like `libreevolve_auths.json`, `~/.codex/log/codex-login.log` (login timestamps only) |
| Copilot CLI | `~/.copilot/session-state/*/events.jsonl` | `~/.copilot/session-store.db` | in events | GitHub account |
| opencode | `~/.local/share/opencode/opencode.db` | same | same | `~/.local/share/opencode/auth.json` |
| OpenClaw | `<deploy>/config/agents/*/sessions/*.jsonl` | – | in sessions | provider API keys in the gateway env |
| Antigravity / Gemini | `~/.gemini/antigravity/conversations/*.db` (protobuf blobs, no token fields) | – | – | not usable |
| Cursor / Cline / Continue | usually only skills and settings | – | – | – |

`~` means each user profile: `C:\Users\<name>`, `/home/<name>`, `/Users/<name>`, plus WSL distros (`\\wsl$\<distro>\home\<name>`) and any backed-up profile on other drives.

## Sweep commands

Windows Git Bash / any POSIX shell (adjust roots):

```
for r in /c/Users/* /d /e /g; do
  find "$r" -maxdepth 7 \( -type d \( -name .claude -o -name .codex -o -name .copilot -o -name .gemini -o -name .opencode \) \
     -o -type f \( -name history.jsonl -o -name 'rollout-*.jsonl' -o -name stats-cache.json \) \) \
     -not -path '*/node_modules/*' -not -path '*/.git/*' 2>/dev/null
done
```

Then keep only `.claude` dirs that contain `projects/` and `.codex` dirs that contain `sessions/` (repos often carry `.claude/settings.json` or `.codex/config.toml` that hold no usage).

Extend the sweep with the other names from `harness-catalog.md`: dot-dirs `.gemini .qwen .kimi .kimi-code .vibe .continue .pi .factory .amp .grok .hermes .zcode .cline .cursor .codeium .kiro .lmstudio .ollama .openhands .aider*`; VS Code storage `*/User/globalStorage/{saoudrizwan.claude-dev,rooveterinaryinc.roo-cline,kilocode.kilo-code}` and `*/User/workspaceStorage/*/chatSessions`; app data `Cursor/User/globalStorage/state.vscdb`, `Zed/threads`, `JetBrains/*/workspace`, `~/.config/manicode`, `~/.local/share/{opencode,amp,kilo,goose,crush,zed}`; and files `.aider.chat.history.md`, `tokensGenerated.jsonl`, `wire.jsonl`, `ui_messages.json`, `chat-messages.json`, `sessions.db`, `state.db`, `grok.db`.

Inside WSL: `find ~ -maxdepth 5 -type d \( -name .claude -o -name .codex \)`; also check `~/.local/share` and `~/.config`.

Remote hosts over SSH: run the same `find` plus `ls /home` and `podman ps` / `docker ps` for gateways that keep their own session logs (`/srv`, `/opt`, `/var/lib`). Note what needs sudo and record it as excluded rather than guessing.

Size first: `du -sh` each candidate. Codex trees of tens of GB are normal; the scanner streams them but a WSL tree scanned over the `\\wsl$` share is roughly four times slower than scanning inside the distro.

## Reading accounts without exposing secrets

Codex `auth.json` (do not print the tokens; decode claims only):

```python
import json, base64
d = json.load(open(path)); t = d.get("tokens", {}); tok = t.get("id_token") or t.get("access_token")
p = tok.split(".")[1]; p += "=" * (-len(p) % 4); c = json.loads(base64.urlsafe_b64decode(p))
auth = c.get("https://api.openai.com/auth", {}); prof = c.get("https://api.openai.com/profile", {})
print(prof.get("email"), auth.get("chatgpt_plan_type"), auth.get("chatgpt_account_id")[:8], [o.get("title") for o in auth.get("organizations", [])], d.get("last_refresh"))
```

Claude: `~/.claude.json` → `oauthAccount.emailAddress`, `organizationType`, `organizationRateLimitTier`, `subscriptionCreatedAt`; `~/.claude/.credentials.json` → `claudeAiOauth.subscriptionType`, `rateLimitTier`.

Each distinct `chatgpt_account_id` (or Claude e-mail) is one account. The same account id under two e-mails is one account whose e-mail changed. Saved auth snapshots (e.g. `~/.codex-auths/*/auth.json` with `created_at` notes) tell you when a switch happened and for which project; login logs tell you when re-logins happened but not to which account.

## Attribution rules you can defend

1. A per-call plan stamp (`rate_limits.plan_type`) beats everything: usage-based calls are usage-based regardless of host.
2. A host whose profile has only ever held one login: that login, medium confidence (high if the auth file predates the first rollout).
3. A project directory tied to a saved auth switch from a known date: that account from that date.
4. Everything else on a host: the host's current login, medium confidence; note unexplained re-logins as a limitation.

Write each rule with its `why`; the report prints them.
