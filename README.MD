# email2gotify

Establishes connectivity with electronic mail retrieval infrastructure via the Internet Message Access Protocol, subsequently evaluating incoming correspondence against a configurable ruleset and dispatching matched items as push notification events to a designated Gotify endpoint.

Works with any standard IMAP server. Designed to run on Windows alongside Proton Mail Bridge, but not limited to it.

![email2gotify screenshot](https://raw.githubusercontent.com/honeybugserial/email2gotify/refs/heads/main/screenShott.png)

## Download

A pre-compiled Windows binary is available if you don't want to run from source:

[**Download email2gotify v5.2.4 (Windows .exe)**](https://archive.org/details/dist_email2gotify_v5.2.4.7z)

Extract the archive and place `email2gotify.exe` alongside `config.toml` and the `rules/` directory.

---

## Requirements

**Python 3.11+** is required (`tomllib` is built-in from 3.11).

```
pip install -r requirements.txt
```

---

## File Structure

```
email2gotify/
├── email2gotify_v5.x.x.py   # Main script
├── framework_base.py         # Shared framework (logging, config, utilities)
├── bannerHELL.py             # Startup splash screen
├── config.toml               # Server / connection settings
├── requirements.txt          # Python dependencies
└── rules/
    ├── ruleExample.toml          # Template — copy this to create a new rule
    ├── domainWebsite.toml           # One rule per file
    └── ...
```

---

## Setup

### 1. Install dependencies

```
pip install -r requirements.txt
```

### 2. Configure config.toml

Edit `config.toml` with your IMAP and Gotify connection details. You only need to do this once.

**Required fields:**

| Section | Field | Description |
|---|---|---|
| `[imap]` | `host` | IMAP server hostname or IP |
| `[imap]` | `port` | IMAP port |
| `[imap]` | `username` | Your email address |
| `[imap]` | `password` | Your IMAP password |
| `[imap]` | `poll_interval` | How often to check for new emails (seconds) |
| `[imap]` | `folder` | Mailbox folder to watch (usually `INBOX`) |
| `[gotify]` | `url` | Your Gotify server URL |
| `[gotify]` | `client_token` | Your Gotify **client** token (startup verification only) |

> **Proton Mail Bridge users:** Bridge runs a local IMAP server. Set `host = "127.0.0.1"` and use the port and Bridge password shown in the Bridge app. Your username is your Proton email address.

### 3. Understand Gotify tokens

Gotify has two types of tokens — make sure you use the right one in the right place:

| Token type | Where to get it | Where to use it |
|---|---|---|
| **Client token** | Gotify web UI → Clients | `config.toml` → `[gotify] client_token` |
| **App token** | Gotify web UI → Apps | Each rule file → `[gotify] token` |

The client token is only used to verify the Gotify server is reachable on startup. The app token is what actually sends notifications. Create a separate Gotify app for each rule if you want notifications organized by source.

### 4. Create at least one rule

Copy `example.toml` from the `rules/` directory, rename it, and fill in your filters and app token. The script loads all `.toml` files from `rules/` automatically on startup.

---

## Creating Rules

Each `.toml` file in the `rules/` directory is one rule. Drop a new file in to add a rule — no script changes needed.

### Filters

All filter fields are optional. Leave blank to match everything.

| Field | Behavior |
|---|---|
| `allowed_senders` | Only forward emails from these senders. Comma separated. |
| `blocked_senders` | Never forward emails from these senders. |
| `subject_must_contain` | Only forward if subject contains at least one of these. Comma separated. |
| `subject_must_not_contain` | Skip emails where subject contains any of these. |

Matching is **case insensitive** and uses **contains** logic — `domainwebsite.gov` will match `noreply@domainwebsite.gov`.

### Content modes

| Mode | What gets sent |
|---|---|
| `preview` | Subject + sender + first N characters of body |
| `full` | Subject + sender + entire email body |
| `notification_only` | Subject + sender only, no body |

### Priority

Gotify priority scale: `1` = minimum, `5` = default, `10` = maximum/urgent.

---

## Testing a Rule

The `[debug]` section in each rule lets you test your filters without waiting for a real email.

When `enabled = true`, on startup the script will:
1. Search your mailbox for the most recent email matching the rule's filters
2. Send it to Gotify with `[DEBUG]` prepended to the title
3. Continue into normal polling as usual

**Debug options:**

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Set to `true` to run a debug test on startup |
| `scan_days` | `7` | How many days back to search. `0` = no date limit. |
| `scan_limit` | `50` | Max emails to scan. Increase if no match is found. |

> Always set `enabled = false` when done testing.

---

## UI / Keyboard Shortcuts

The script runs a Textual TUI. Available bindings shown in the footer bar:

| Key | Action |
|---|---|
| `Ctrl+Q` | Quit |
| `Ctrl+L` | Clear log panel |
| `Ctrl+D` | Toggle debug logging on/off |
| `Ctrl+A` | About |

---

## Logging

Logs are written to the `logs/` directory with a timestamp in the filename.

Log verbosity is controlled by `[debug] enabled` in `config.toml`:

- `enabled = false` — INFO level. Matches, sends, and errors only.
- `enabled = true` — DEBUG level. Every email checked, every filter decision, IMAP queries, Gotify responses.

Debug mode can also be toggled live with `Ctrl+D` while the script is running.

### Log prefixes

| Prefix | Meaning |
|---|---|
| `[POLL]` | Normal polling activity |
| `[RULE: filename.toml]` | A rule evaluating or matching an email |
| `[DEBUG RULE: filename.toml]` | Rule debug test phase on startup |

---

## Normal Polling Behavior

- On each poll, connects to IMAP and searches for **unread emails received today**
- Each email is evaluated against **all rules** — an email can match multiple rules
- If at least one rule matched, the email is marked as read (if `mark_as_read = true`)
- If no rules match, the email is left unread and silently skipped

---

## Startup Checks

On every start the script verifies:

1. `config.toml` exists and all required fields are filled in
2. At least one rule file exists in `rules/`
3. Each rule file has all required fields including a non-empty app token
4. Gotify server is reachable
5. IMAP connection and login succeeds

If any check fails the script exits with a clear error message.

---

## Quick Reference

```bash
# Normal run
python email2gotify_v5.x.x.py

# Test a rule:
# 1. Open the rule file in rules/
# 2. Set enabled = true under [debug]
# 3. Run the script — it finds the last matching email and sends it to Gotify
# 4. Check the notification, adjust filters if needed
# 5. Set enabled = false when done
```
