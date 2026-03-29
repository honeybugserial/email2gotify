# framework_base.py

"""
# requirements.txt
rich
pygetwindow
screeninfo
"""

# ----

"""
---- START TEMPLATE SETUP -----

import framework_base as base
from framework_base import console
from pathlib import Path
#import logging

# Define config path (same directory as script)
config_file = "generic-config.toml"
config_path = Path(__file__).with_name(config_file)

# Initialize framework (logging, console, config)
config_data = base.load_config(config_path)
base.initialize(config_data)
log = base.get_logger(__name__)

# Optional: display banner
base.show_banner()

# Start coding
log.info("System Online.")

---- END TEMPLATE SETUP -----

Log Level Cheat Table

| Method            | Level value | Purpose                                                         |
| ----------------- | ----------- | --------------------------------------------------------------- |
| `debug()`         | 10          | Detailed diagnostic info (dev-only, troubleshooting)            |
| `info()`          | 20          | Normal operational messages (expected events)                   |
| `warning()`       | 30          | Something unexpected, but not fatal                             |
| `error()`         | 40          | A failure occurred, but program can continue                    |
| `critical()`      | 50          | Serious failure, program may terminate                          |
| `exception()`     | 40          | Same as `error()` but includes traceback (only inside `except`) |
| `log(level, msg)` | custom      | Manual level logging                                            |

logging.debug()
logging.info()
logging.warning()
logging.error()
logging.critical()
logging.exception()
logging.log(level, msg)

log.debug("Developer diagnostic info")
log.info("Normal operation message")
log.warning("Something unexpected happened")
log.error("Operation failed")
log.exception("Operation failed with traceback")  # inside except
log.critical("Fatal error")


"""

import os
import re
import logging
import sys
import ctypes
import ctypes.wintypes as wt
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install as install_rich_traceback

from rich.theme import Theme

console = Console()

_config: Dict[str, Any] = {}
_logging_initialized = False


# =============================================================================
# CONFIG LOADING
# =============================================================================

def load_config(path: str | Path) -> Dict[str, Any]:
    import tomllib
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "rb") as f:
        return tomllib.load(f)


# =============================================================================
# INITIALIZATION
# =============================================================================

def initialize(config: Dict[str, Any]) -> None:
    global _config
    _config = config

    _initialize_tracebacks()
    _initialize_logging()

def _initialize_tracebacks():
    install_rich_traceback(
        show_locals=False
    )


# =============================================================================
# LOGGING
# =============================================================================

class _MarkupStripFormatter(logging.Formatter):
    """
    Logging formatter that strips Rich markup tags from log messages
    before writing to file. Prevents tags like [bold cyan] appearing
    literally in log files.
    """
    _MARKUP_RE = re.compile(r"\[/?(?:#[0-9a-fA-F]{3,6}|[a-z][a-z0-9 _]*)\]")

    def format(self, record: logging.LogRecord) -> str:
        # Strip markup from the message before formatting
        record = logging.makeLogRecord(record.__dict__)
        record.msg = self._MARKUP_RE.sub("", str(record.msg))
        if record.args:
            # Also strip from any args that are strings
            if isinstance(record.args, tuple):
                record.args = tuple(
                    self._MARKUP_RE.sub("", str(a)) if isinstance(a, str) else a
                    for a in record.args
                )
        return super().format(record)


def _initialize_logging():
    
    global _logging_initialized

    if _logging_initialized:
        return

    log_cfg = _config.get("logging", {})

    enabled = log_cfg.get("enabled", True)
    prefix = log_cfg.get("log_prefix", "log_")
    log_dir = Path(log_cfg.get("log_dir", "logs"))

    debug_enabled = _config.get("debug", {}).get("enabled", False)

    level = logging.DEBUG if debug_enabled else logging.INFO

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    # Console handler (Rich)
    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_level=True,
        omit_repeated_times=False,
        show_path=False,
        markup=True,
        rich_tracebacks=True
    )
    
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    root_logger.addHandler(console_handler)

    # File handler
    if enabled:

        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        logfile = log_dir / f"{prefix}{timestamp}.log"

        file_handler = logging.FileHandler(
            logfile,
            encoding="utf-8"
        )

        file_formatter = _MarkupStripFormatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            "%Y-%m-%d %H:%M:%S"
        )

        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
        logging.debug(f"Log file created: {logfile}")

    _logging_initialized = True


# =============================================================================
# LOGGER ACCESS
# =============================================================================

def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(name)



# =============================================================================
# DEBUG HELPERS
# =============================================================================

def is_debug_enabled() -> bool:
    return _config.get("debug", {}).get("enabled", False)

def should_pause_on_fail() -> bool:
    return _config.get("debug", {}).get("pause_on_fail", False)

def pause():
    logging.info("Paused. Press Enter to continue...")
    console.print("\n[yellow]Paused. Press Enter to continue...[/yellow]")
    input()


# =============================================================================
# ODD THINGS AND END THINGS
# =============================================================================

# --- Print with timestamps and labels (if needed for reasons)
# Exmaple: print_with_timestamp("This is an info message.", "INFO")
def print_with_timestamp(msg: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    level_colors = {
        "INFO": "green",
        "DEBUG": "blue",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold red"
    }
    # Format the message with timestamp and log level
    formatted_msg = f"[{timestamp}] [{level}] {msg}"
    # Use console.print to output the message with color formatting based on level
    console.print(f"[{level_colors.get(level, 'white')}] {formatted_msg}[/]")
    
# =============================================================================
# UTILITIES
# =============================================================================

# --- Clear Console
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

# --- Print Config
def print_config():
    
    from rich.pretty import pprint
    pprint(_config)

# --- Resize Console Window
def resize_console(w: int = 1500, h: int = 800, title: str = None) -> bool:
    try:
        import pygetwindow as gw
    except ImportError:
        logging.debug("resize_console: pygetwindow not installed")
        return False

    try:
        from screeninfo import get_monitors
        monitors = get_monitors()
        primary = next((m for m in monitors if m.x == 0 and m.y == 0), monitors[0])
        screen_w = primary.width
        screen_h = primary.height
    except Exception:
        screen_w = 1920
        screen_h = 1080

    # Clamp to screen
    w = min(w, screen_w)
    h = min(h, screen_h)

    # Center position
    x = (screen_w - w) // 2
    y = (screen_h - h) // 2

    # Find window by title or try common console titles
    console_titles = ["Windows PowerShell", "PowerShell", "Command Prompt", "cmd", "Terminal"]
    win = None

    if title:
        wins = gw.getWindowsWithTitle(title)
        if wins:
            win = wins[0]
    else:
        for t in console_titles:
            wins = gw.getWindowsWithTitle(t)
            if wins:
                win = wins[0]
                break

    if not win:
        logging.debug("resize_console: no console window found")
        return False

    try:
        win.resizeTo(w, h)
        win.moveTo(x, y)
        logging.debug("Console resized to %dx%d", w, h)
        return True
    except Exception:
        logging.exception("resize_console failed")
        return False
        
# --- ADMIN PRIVILEGE CHECK
def is_admin():
    logging.info("Checking for Administrator Privileges")
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        logging.debug("Admin check failed")
        return False

def elevate():
    try:
        params = " ".join([f'"{a}"' for a in sys.argv])
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas",
            sys.executable,
            params,
            None,
            1
        )
    except:
        logging.exception("Elevation failed")
    sys.exit(0)

# --- DISABLE QUICK EDIT
def disable_quickedit():
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        GetStdHandle = kernel32.GetStdHandle
        GetStdHandle.argtypes = [wt.DWORD]
        GetStdHandle.restype = wt.HANDLE

        GetConsoleMode = kernel32.GetConsoleMode
        GetConsoleMode.argtypes = [wt.HANDLE, wt.LPDWORD]
        GetConsoleMode.restype = wt.BOOL

        SetConsoleMode = kernel32.SetConsoleMode
        SetConsoleMode.argtypes = [wt.HANDLE, wt.DWORD]
        SetConsoleMode.restype = wt.BOOL

        STD_INPUT_HANDLE = -10
        ENABLE_QUICK_EDIT = 0x40

        h_stdin = GetStdHandle(STD_INPUT_HANDLE)
        if not h_stdin:
            logging.debug("disable_quickedit: no stdin handle")
            return

        mode = wt.DWORD()

        if not GetConsoleMode(h_stdin, ctypes.byref(mode)):
            logging.debug("disable_quickedit: GetConsoleMode failed")
            return

        new_mode = mode.value & ~ENABLE_QUICK_EDIT

        if not SetConsoleMode(h_stdin, new_mode):
            logging.debug("disable_quickedit: SetConsoleMode failed")
            return

        logging.debug("QuickEdit disabled")

    except Exception:
        logging.exception("disable_quickedit failed")

# --- FATAL
def fatal(msg: str, code: int = 1) -> None:
    # Log the fatal error with a red bold message for visibility
    logging.exception(f"[bold red]FATAL ERROR:[/] {msg}")
    console.print("\n[red]A critical error occurred. The program will now terminate.[/red]")
    input("Press Enter to exit...")
    # Exit with the given exit code (default is 1 for error)
    sys.exit(code)
    
# NOTE: Fatal Example Use:
"""
if not os.path.exists(config_file):
    fatal(f"Config file {config_file} is missing.", 1)
"""