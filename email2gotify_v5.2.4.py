# email2gotify.py — Textual UI version
# v5.2.4

import framework_base as base
from pathlib import Path
import imaplib
import email
import time
import requests
import tomllib
import sys
import os
import threading
import logging
import asyncio
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta

from textual.app import App, ComposeResult
from textual.screen import ModalScreen
from textual.widgets import RichLog, Footer, Header, Static
from textual.binding import Binding

from rich.text import Text
from textual.containers import Vertical
from textual import work

import bannerHELL

# =============================================================================
# PATH HELPERS
# Handles both normal script execution and PyInstaller compiled exe.
# =============================================================================

def get_bundle_dir() -> Path:
    """Read-only bundled files (PyInstaller _MEIPASS)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def get_runtime_dir() -> Path:
    """Writable runtime directory — next to the exe when compiled, next to the script otherwise."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# ---- Framework setup ----
config_file = "config.toml"
config_path = get_runtime_dir() / config_file

try:
    config_data = base.load_config(config_path)
except FileNotFoundError:
    print(f"\n[ERROR] config.toml not found at: {config_path}")
    print("Create a config.toml in the same directory as this script.")
    print("See the README or example config for details.\n")
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] Failed to load config.toml: {e}\n")
    sys.exit(1)

base.initialize(config_data)
log = base.get_logger(__name__)


# =============================================================================
# HELPERS
# =============================================================================

def load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_rules(rules_dir: Path) -> list[tuple[str, dict]]:
    rules = []
    if not rules_dir.is_dir():
        return rules
    for filename in sorted(os.listdir(rules_dir)):
        if filename.endswith(".toml"):
            data = load_toml(rules_dir / filename)
            rules.append((filename, data))
    return rules


def decode_str(value: str) -> str:
    decoded, encoding = decode_header(value)[0]
    if isinstance(decoded, bytes):
        return decoded.decode(encoding or "utf-8", errors="replace")
    return decoded


def get_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="replace")
    else:
        charset = msg.get_content_charset() or "utf-8"
        return msg.get_payload(decode=True).decode(charset, errors="replace")
    return "(no body)"


def parse_list(value: str) -> list[str]:
    return [s.strip().lower() for s in value.split(",") if s.strip()]


def matches_filter(value: str, filter_list: list[str]) -> bool:
    return any(f in value.lower() for f in filter_list)


# =============================================================================
# TEXTUAL LOG HANDLER — pipes Python logging into the RichLog widget
# =============================================================================

class TextualLogHandler(logging.Handler):
    """Sends log records to the Textual RichLog widget."""

    LEVEL_COLORS = {
        "DEBUG":    "dim cyan",
        "INFO":     "orange3",
        "WARNING":  "yellow",
        "ERROR":    "red",
        "CRITICAL": "bold red",
    }

    def __init__(self, app: "Email2GotifyApp"):
        super().__init__()
        self._app = app

    def emit(self, record: logging.LogRecord):
        import re
        import threading
        markup_re = re.compile(r"\[/?(?:#[0-9a-fA-F]{3,6}|[a-z][a-z0-9 _]*)\]")
        msg = markup_re.sub("", record.getMessage())
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        level = record.levelname
        color = self.LEVEL_COLORS.get(level, "white")

        line = Text()
        line.append(f"[{ts}] ", style="dim")
        line.append(f"{level:<8}", style=color)
        line.append(f"  {msg}")

        try:
            if self._app._thread_id != threading.get_ident():
                self._app.call_from_thread(self._app.append_log, line)
            else:
                self._app.call_later(self._app.append_log, line)
        except Exception:
            pass


# =============================================================================
# TEXTUAL APP
# =============================================================================

STATUS_CSS = """
#status-bar {
    height: 5;
    border: solid orange;
    padding: 0 1;
    background: $surface;
}

#status-line1 {
    height: 1;
    color: $text-muted;
}

#status-line2 {
    height: 1;
    color: $text-muted;
}

#status-line3 {
    height: 1;
    color: $text-muted;
}

#status-header {
    height: 1;
    color: red;
    text-style: bold;
}

RichLog {
    border: solid $surface-lighten-2;
    background: $surface;
    scrollbar-size-vertical: 1;
    scrollbar-size-horizontal: 0;
    scrollbar-color: darkorange;
    scrollbar-color-hover: darkorange;
    scrollbar-color-active: darkorange;
    scrollbar-background: $surface-darken-1;
}
"""


class AboutScreen(ModalScreen):
    CSS = """
    AboutScreen {
        align: center middle;
    }
    #about-dialog {
        width: 60;
        height: auto;
        border: solid orange;
        background: $surface;
        padding: 1 2;
    }
    #about-title {
        text-align: center;
        color: #ff6c6b;
        text-style: bold;
        margin-bottom: 1;
    }
    #about-body {
        text-align: center;
        color: $text-muted;
    }
    #about-close {
        text-align: center;
        margin-top: 1;
        color: #6a9fb5;
    }
    """

    BINDINGS = [("escape", "dismiss", "Close"), ("q", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical(id="about-dialog"):
            yield Static("Email2Gotify", id="about-title")
            yield Static(
                "Establishes connectivity with electronic mail retrieval\n"
                "infrastructure via the Internet Message Access Protocol,\n"
                "subsequently evaluating incoming correspondence against\n"
                "a configurable ruleset and dispatching matched items as\n"
                "push notification events to a designated Gotify endpoint.\n\n"
                "Rules: deposit a .toml configuration artifact into the\n"
                "rules/ directory to register a new notification filter.\n"
                "Logs: timestamped session transcripts persist in logs/."
                "Do not use under influences. Always ask./.",
                id="about-body"
            )
            yield Static("Press ESC and Q to close", id="about-close")


class Email2GotifyApp(App):
    CSS = STATUS_CSS

    BINDINGS = [
        Binding("ctrl+c", "quit", "", show=False),
        Binding("ctrl+p", "command_palette", "", show=False),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_log", "Clear Log"),
        Binding("ctrl+d", "toggle_debug", "Debug On/Off"),
        Binding("ctrl+a", "about", "About"),
    ]

    def __init__(self, config: dict, rules: list):
        super().__init__()
        self.config = config
        self.rules = rules
        self._gotify_status = "unknown"
        self._imap_status = "unknown"
        self._last_poll = "never"
        self._last_match_rule = ""
        self._last_match_subject = ""
        self._last_match_time = ""
        self._poll_interval = int(config["imap"]["poll_interval"])

    def compose(self) -> ComposeResult:
        yield Static("- Emails to Gotify -", id="status-header")
        with Vertical(id="status-bar"):
            yield Static("", id="status-line1")
            yield Static("", id="status-line2")
            yield Static("", id="status-line3")
        yield RichLog(highlight=True, markup=True, wrap=False, id="log")
        yield Footer()

    def action_about(self) -> None:
        self.push_screen(AboutScreen())

    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()

    def action_toggle_debug(self) -> None:
        import logging
        root = logging.getLogger()
        if root.level == logging.DEBUG:
            root.setLevel(logging.INFO)
            self.notify("Debug OFF", severity="information")
        else:
            root.setLevel(logging.DEBUG)
            self.notify("Debug ON", severity="warning")

    def on_mount(self) -> None:
        # Wire logging into this app
        handler = TextualLogHandler(self)
        logging.getLogger().addHandler(handler)
        # Remove RichHandler so no double output
        from rich.logging import RichHandler
        for h in logging.getLogger().handlers[:]:
            if isinstance(h, RichHandler):
                logging.getLogger().removeHandler(h)
        # Start the main worker
        self.run_worker(self.start_relay(), exclusive=True)

    def append_log(self, line: str) -> None:
        self.query_one("#log", RichLog).write(line)

    def update_status(self) -> None:
        gotify_ok = self._gotify_status == "OK"
        imap_ok = self._imap_status == "OK"
        gotify_dot = "[bold green]●[/bold green]" if gotify_ok else "[bold red]●[/bold red]"
        imap_dot = "[bold green]●[/bold green]" if imap_ok else "[bold red]●[/bold red]"
        now = datetime.now().strftime("%H:%M:%S")

        gotify_url = self.config["gotify"]["url"]
        imap_host = self.config["imap"]["host"]
        imap_user = self.config["imap"]["username"]
        folder = self.config["imap"].get("folder", "INBOX")
        rule_names = ", ".join(r[0].replace(".toml", "") for r in self.rules)
        div = "  [dim orange]│[/dim orange]  "

        # Line 1: connection status + server info
        line1 = (
            f"{gotify_dot} [dim]Gotify:[/dim] [orange]{gotify_url}[/orange]"
            f"{div}"
            f"{imap_dot} [dim]IMAP:[/dim] [orange]{imap_user}[/orange] [dim]({imap_host} / {folder})[/dim]"
            f"{div}"
            f"[dim]Rules:[/dim] [orange]{rule_names}[/orange]"
        )

        # Line 2: poll info + time
        line2 = (
            f"[dim]Poll: every {self._poll_interval}s[/dim]"
            f"{div}"
            f"[dim]Last poll:[/dim] [orange]{self._last_poll}[/orange]"
        )

        # Line 3: last match
        if self._last_match_time:
            line3 = (
                f"[dim]Last Match:[/dim] [orange]{self._last_match_rule}[/orange] "
                f"[dim]—[/dim] {self._last_match_subject} "
                f"[dim]({self._last_match_time})[/dim]"
            )
        else:
            line3 = "[dim]Last Match: —[/dim]"

        self.query_one("#status-line1", Static).update(line1)
        self.query_one("#status-line2", Static).update(line2)
        self.query_one("#status-line3", Static).update(line3)

    async def start_relay(self) -> None:
        """Main relay logic — runs as a Textual worker."""
        await asyncio.sleep(0.1)  # Let UI render first

        # Startup checks
        if not startup_checks(self.config, self.rules):
            log.critical("Startup failed — exiting")
            await asyncio.sleep(1)
            self.exit()
            return

        # Debug phase
        debug_rules = [(n, r) for n, r in self.rules if r.get("debug", {}).get("enabled", False)]
        if debug_rules:
            log.info(f"-- Debug Phase ({len(debug_rules)} rule(s)) --")
            for rule_name, rule in debug_rules:
                await asyncio.get_event_loop().run_in_executor(
                    None, debug_rule_sync, self.config, rule_name, rule
                )
            log.info("-- Debug Phase Complete --")

        # Update initial status
        self._gotify_status = "OK"
        self._imap_status = "OK"
        self.update_status()

        # Start heartbeat
        heartbeat_interval = int(self.config.get("options", {}).get("heartbeat_interval", 300))
        hb_thread = threading.Thread(
            target=heartbeat_loop,
            args=(self.config, heartbeat_interval, self),
            daemon=True
        )
        hb_thread.start()

        log.info(f"-- Normal Polling Started (every {self._poll_interval}s) --")

        # Poll loop
        while True:
            await asyncio.get_event_loop().run_in_executor(
                None, self._poll
            )
            self.update_status()
            await asyncio.sleep(self._poll_interval)

    def _poll(self):
        check_mail(self.config, self.rules, self)


# =============================================================================
# STARTUP CHECKS
# =============================================================================

REQUIRED_CONFIG_FIELDS = {
    "imap": ["host", "port", "username", "password", "poll_interval", "folder"],
    "gotify": ["url", "client_token"],
    "options": ["mark_as_read"],
}

REQUIRED_RULE_FIELDS = {
    "gotify": ["token"],
    "filters": [],
    "options": ["content_mode"],
}


def check_config_fields(config: dict) -> bool:
    ok = True
    for section, fields in REQUIRED_CONFIG_FIELDS.items():
        if section not in config:
            log.error(f"config.toml: missing section [{section}]")
            ok = False
            continue
        for field in fields:
            val = config[section].get(field, "")
            if val == "" or val is None:
                log.error(f"config.toml: [{section}] '{field}' is missing or empty")
                ok = False
    return ok


def check_rule_fields(rule_name: str, rule: dict) -> bool:
    ok = True
    for section, fields in REQUIRED_RULE_FIELDS.items():
        if section not in rule:
            log.error(f"Rule '{rule_name}': missing section [{section}]")
            ok = False
            continue
        for field in fields:
            val = rule[section].get(field, "")
            if val == "" or val is None:
                log.error(f"Rule '{rule_name}': [{section}] '{field}' is missing or empty")
                ok = False
    return ok


def verify_imap(config: dict) -> bool:
    host = config["imap"]["host"]
    port = int(config["imap"]["port"])
    username = config["imap"]["username"]
    password = config["imap"]["password"]
    log.info(f"Testing IMAP connection to {host}:{port} as {username}...")
    try:
        mail = imaplib.IMAP4(host, port)
        mail.login(username, password)
        mail.logout()
        log.info("IMAP connection OK")
        return True
    except imaplib.IMAP4.error as e:
        msg = e.args[0].decode() if isinstance(e.args[0], bytes) else str(e)
        log.error(f"IMAP login failed: {msg}")
        return False
    except Exception as e:
        log.error(f"IMAP connection failed: {e}")
        return False


def verify_gotify(config: dict) -> bool:
    url = config["gotify"]["url"]
    client_token = config["gotify"]["client_token"]
    log.info(f"Testing Gotify connection to {url}...")
    try:
        resp = requests.get(
            f"{url}/client",
            headers={"X-Gotify-Key": client_token},
            timeout=10
        )
        if resp.status_code == 200:
            log.info("Gotify connection OK")
            return True
        else:
            log.error(f"Gotify returned HTTP {resp.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        log.error(f"Gotify unreachable: {url}")
        return False
    except requests.exceptions.Timeout:
        log.error(f"Gotify timed out: {url}")
        return False
    except requests.RequestException as e:
        log.error(f"Gotify connection failed: {e}")
        return False


def startup_checks(config: dict, rules: list) -> bool:
    log.info("-- Startup Checks --")
    ok = True

    log.info("Checking config.toml...")
    if check_config_fields(config):
        log.info("config.toml OK")
    else:
        ok = False

    if not ok:
        log.critical("config.toml has errors — fix them and restart")
        return False

    log.info("Checking rules...")
    if not rules:
        log.critical("No rule files found in rules/")
        return False

    for rule_name, rule in rules:
        if check_rule_fields(rule_name, rule):
            log.info(f"{rule_name} OK")
        else:
            log.error(f"{rule_name} has errors")
            ok = False

    if not ok:
        log.critical("One or more rules have errors — fix them and restart")
        return False

    log.info("Checking Gotify...")
    if not verify_gotify(config):
        log.critical("Gotify connection failed")
        return False

    log.info("Checking IMAP...")
    if not verify_imap(config):
        return False

    log.info("All checks passed")
    return True


# =============================================================================
# HEARTBEAT
# =============================================================================

def heartbeat_loop(config: dict, interval_seconds: int, app: Email2GotifyApp):
    url = config["gotify"]["url"]
    client_token = config["gotify"]["client_token"]
    while True:
        time.sleep(interval_seconds)
        try:
            resp = requests.get(
                f"{url}/client",
                headers={"X-Gotify-Key": client_token},
                timeout=10
            )
            if resp.status_code == 200:
                app._gotify_status = "OK"
                log.debug("Heartbeat: Gotify OK")
            else:
                app._gotify_status = "ERROR"
                log.warning(f"Heartbeat: Gotify HTTP {resp.status_code}")
        except Exception as e:
            app._gotify_status = "ERROR"
            log.warning(f"Heartbeat: Gotify unreachable — {e}")
        if app._thread_id != threading.get_ident():
            app.call_from_thread(app.update_status)
        else:
            app.call_later(app.update_status)


# =============================================================================
# MAIL PROCESSING
# =============================================================================

def send_to_gotify(url: str, token: str, title: str, message: str, priority: int = 5):
    log.debug(f"Sending to Gotify: '{title}' priority={priority}")
    try:
        resp = requests.post(
            f"{url}/message",
            params={"token": token},
            json={"title": title, "message": message, "priority": priority},
            timeout=10
        )
        resp.raise_for_status()
        log.info(f"Sent to Gotify: '{title}'")
    except requests.RequestException as e:
        log.error(f"Failed to send to Gotify: {e}")


def apply_rule(rule_name: str, rule: dict, sender: str, subject: str, body: str,
               gotify_url: str, app: Email2GotifyApp) -> bool:
    token = rule.get("gotify", {}).get("token", "").strip()
    priority = int(rule.get("gotify", {}).get("priority", 5))
    content_mode = rule.get("options", {}).get("content_mode", "preview").strip().lower()
    preview_length = int(rule.get("options", {}).get("preview_length", 500))

    filters = rule.get("filters", {})
    allowed_senders = parse_list(filters.get("allowed_senders", ""))
    blocked_senders = parse_list(filters.get("blocked_senders", ""))
    subject_must_contain = parse_list(filters.get("subject_must_contain", ""))
    subject_must_not_contain = parse_list(filters.get("subject_must_not_contain", ""))

    prefix = f"[RULE: {rule_name}]"
    log.debug(f"{prefix} Checking: '{subject}' from '{sender}'")

    if allowed_senders and not matches_filter(sender, allowed_senders):
        log.debug(f"{prefix}  -> No match: sender not in allowed_senders")
        return False
    if blocked_senders and matches_filter(sender, blocked_senders):
        log.debug(f"{prefix}  -> No match: sender in blocked_senders")
        return False
    if subject_must_contain and not matches_filter(subject, subject_must_contain):
        log.debug(f"{prefix}  -> No match: subject missing required keyword")
        return False
    if subject_must_not_contain and matches_filter(subject, subject_must_not_contain):
        log.debug(f"{prefix}  -> No match: subject has excluded keyword")
        return False

    log.info(f"{prefix} Matched: '{subject}' from {sender}")

    if content_mode == "notification_only":
        message_text = f"From: {sender}"
    elif content_mode == "full":
        message_text = f"From: {sender}\n\n{body.strip()}"
    else:
        message_text = f"From: {sender}\n\n{body.strip()[:preview_length]}"

    send_to_gotify(gotify_url, token, subject, message_text, priority)

    app._last_match_rule = rule_name
    app._last_match_subject = subject[:50] + ("..." if len(subject) > 50 else "")
    app._last_match_time = datetime.now().strftime("%H:%M:%S")

    return True


def check_mail(config: dict, rules: list, app: Email2GotifyApp):
    host = config["imap"]["host"]
    port = int(config["imap"]["port"])
    username = config["imap"]["username"]
    password = config["imap"]["password"]
    folder = config["imap"].get("folder", "INBOX")
    gotify_url = config["gotify"]["url"]
    mark_as_read = config["options"].get("mark_as_read", True)

    log.debug(f"Connecting to IMAP {host}:{port}...")
    try:
        mail = imaplib.IMAP4(host, port)
        mail.login(username, password)
        mail.select(folder)

        app._imap_status = "OK"
        app._last_poll = datetime.now().strftime("%H:%M:%S")

        since_date = datetime.now(timezone.utc).strftime("%d-%b-%Y")
        search_query = f'UNSEEN SINCE "{since_date}"'
        log.debug(f"IMAP search: {search_query}")
        search_status, messages = mail.search(None, search_query)

        if search_status != "OK":
            log.warning("Failed to search mailbox")
            mail.logout()
            return

        email_ids = messages[0].split()
        if not email_ids:
            log.debug("[POLL] No new emails")
            mail.logout()
            return

        log.info(f"[POLL] Found {len(email_ids)} new email(s)")

        for eid in email_ids:
            fetch_status, data = mail.fetch(eid, "(RFC822)")
            if fetch_status != "OK":
                continue

            msg = email.message_from_bytes(data[0][1])
            sender = msg.get("From", "Unknown")
            subject = decode_str(msg.get("Subject", "(no subject)"))
            body = get_body(msg)

            log.debug(f"[POLL] Processing: '{subject}' from '{sender}'")

            matched = False
            for rule_name, rule in rules:
                if apply_rule(rule_name, rule, sender, subject, body, gotify_url, app):
                    matched = True

            if matched and mark_as_read:
                mail.store(eid, "+FLAGS", "\\Seen")
            elif not matched:
                log.debug(f"[POLL] No rules matched: '{subject}'")

        log.debug("[POLL] Complete")
        mail.logout()

    except Exception as e:
        app._imap_status = "ERROR"
        log.error(f"IMAP error: {e}")


# =============================================================================
# DEBUG
# =============================================================================

def debug_rule_sync(config: dict, rule_name: str, rule: dict):
    prefix = f"[DEBUG RULE: {rule_name}]"
    log.info(f"{prefix} Starting rule debug test...")

    host = config["imap"]["host"]
    port = int(config["imap"]["port"])
    username = config["imap"]["username"]
    password = config["imap"]["password"]
    folder = config["imap"].get("folder", "INBOX")
    gotify_url = config["gotify"]["url"]

    token = rule.get("gotify", {}).get("token", "").strip()
    priority = int(rule.get("gotify", {}).get("priority", 5))
    content_mode = rule.get("options", {}).get("content_mode", "preview").strip().lower()
    preview_length = int(rule.get("options", {}).get("preview_length", 500))

    filters = rule.get("filters", {})
    allowed_senders = parse_list(filters.get("allowed_senders", ""))
    blocked_senders = parse_list(filters.get("blocked_senders", ""))
    subject_must_contain = parse_list(filters.get("subject_must_contain", ""))
    subject_must_not_contain = parse_list(filters.get("subject_must_not_contain", ""))

    scan_limit = int(rule.get("debug", {}).get("scan_limit", 50))
    scan_days = int(rule.get("debug", {}).get("scan_days", 0))

    try:
        mail = imaplib.IMAP4(host, port)
        mail.login(username, password)
        mail.select(folder)

        if scan_days > 0:
            since_date = (datetime.now(timezone.utc) - timedelta(days=scan_days)).strftime("%d-%b-%Y")
            search_query = f'SINCE "{since_date}"'
            log.info(f"{prefix} Searching since {since_date} (scan_days={scan_days})...")
        else:
            search_query = "ALL"
            log.info(f"{prefix} Searching all emails...")

        search_status, messages = mail.search(None, search_query)
        if search_status != "OK" or not messages[0]:
            log.warning(f"{prefix} No emails found in {folder}")
            mail.logout()
            return

        email_ids = messages[0].split()
        recent_ids = email_ids[-scan_limit:]
        log.info(f"{prefix} Scanning {len(recent_ids)} emails (limit={scan_limit}, found={len(email_ids)})...")

        for eid in reversed(recent_ids):
            fetch_status, data = mail.fetch(eid, "(RFC822)")
            if fetch_status != "OK":
                continue

            msg = email.message_from_bytes(data[0][1])
            sender = msg.get("From", "Unknown")
            subject = decode_str(msg.get("Subject", "(no subject)"))
            body = get_body(msg)

            email_date_str = msg.get("Date", "unknown date")
            try:
                email_date = parsedate_to_datetime(email_date_str).strftime("%Y-%m-%d %H:%M")
            except Exception:
                email_date = email_date_str

            log.debug(f"{prefix} Checking [{email_date}]: '{subject}' from '{sender}'")

            if allowed_senders and not matches_filter(sender, allowed_senders):
                log.debug(f"{prefix}  -> Skip: sender not in allowed_senders")
                continue
            if blocked_senders and matches_filter(sender, blocked_senders):
                log.debug(f"{prefix}  -> Skip: sender in blocked_senders")
                continue
            if subject_must_contain and not matches_filter(subject, subject_must_contain):
                log.debug(f"{prefix}  -> Skip: subject missing required keyword")
                continue
            if subject_must_not_contain and matches_filter(subject, subject_must_not_contain):
                log.debug(f"{prefix}  -> Skip: subject has excluded keyword")
                continue

            log.info(f"{prefix} Match found [{email_date}] — '{subject}' from {sender}")

            if content_mode == "notification_only":
                message_text = f"From: {sender}"
            elif content_mode == "full":
                message_text = f"From: {sender}\n\n{body.strip()}"
            else:
                message_text = f"From: {sender}\n\n{body.strip()[:preview_length]}"

            send_to_gotify(gotify_url, token, f"[DEBUG] {subject}", message_text, priority)
            mail.logout()
            return

        log.warning(f"{prefix} No matching emails found — check filters or increase scan_days/scan_limit")
        mail.logout()

    except Exception as e:
        log.error(f"{prefix} IMAP error: {e}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    base.clear_screen()
    base.resize_console(w=1200, h=720)
    time.sleep(2)
    bannerHELL.print_header()
    log.info("Email to Gotify relay starting...")
    time.sleep(1.4)

    rules_dir = get_runtime_dir() / "rules"
    rules = load_rules(rules_dir)

    app = Email2GotifyApp(config_data, rules)
    app.run()


if __name__ == "__main__":
    main()