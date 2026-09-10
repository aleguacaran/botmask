#!/usr/bin/env python3
"""
Browser Configuration Module - botmask

Centralized browser configuration for the humanized browser automation toolkit.
All browser options are sourced from .env file (inherited from the jobs project).

Usage:
    from botmask.config import get_browser_config, get_launch_options

    config = get_browser_config()
    launch_options = get_launch_options()
"""

import os
import sys
import random
import shlex
import tomllib  # stdlib (Python 3.11+); falls back gracefully
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def get_env(key: str, default=None):
    """Get environment variable or default."""
    return os.getenv(key, default)


def _find_toml() -> dict:
    """Look for a botmask.toml config file.

    Search order:
    1. ``BOTMASK_CONFIG`` env var (absolute path)
    2. ``botmask.toml`` in the current working directory
    3. ``~/.config/botmask/botmask.toml``
    Returns an empty dict if none is found.
    """
    # 1. explicit path
    explicit = os.getenv("BOTMASK_CONFIG")
    if explicit and Path(explicit).is_file():
        with open(explicit, "rb") as f:
            return tomllib.load(f)

    # 2. cwd
    cwd = Path("botmask.toml")
    if cwd.is_file():
        with open(cwd, "rb") as f:
            return tomllib.load(f)

    # 3. XDG config dir
    xdg = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "botmask" / "botmask.toml"
    if xdg.is_file():
        with open(xdg, "rb") as f:
            return tomllib.load(f)

    return {}


def _env_overrides() -> dict:
    """Read ``BOTMASK_*`` env vars and map them into config keys.

    This namespace is **isolated** from the host's generic ``BROWSER_*`` /
    ``DISPLAY`` etc., so embedding botmask in another project never collides.

    Supported mappings (env key → config dict key):
        BOTMASK_HEADLESS      → config["headless"]
        BOTMASK_LOCALE        → config["locale"]
        BOTMASK_TIMEZONE      → config["timezone"]
        BOTMASK_NAVIGATION_TIMEOUT   → config["navigation_timeout"]
        BOTMASK_IMPLICIT_WAIT        → config["implicit_wait"]
        BOTMASK_DELAY_MIN     → config["human_delay_min"]
        BOTMASK_DELAY_MAX     → config["human_delay_max"]
    """
    overrides = {}
    mapping = {
        "HEADLESS": "headless",
        "LOCALE": "locale",
        "TIMEZONE": "timezone",
        "NAVIGATION_TIMEOUT": "navigation_timeout",
        "IMPLICIT_WAIT": "implicit_wait",
        "DELAY_MIN": "human_delay_min",
        "DELAY_MAX": "human_delay_max",
    }
    for env_key, cfg_key in mapping.items():
        val = os.getenv("BOTMASK_%s" % env_key)
        if val is not None:
            # Convert booleans / ints / floats where sensible
            if cfg_key == "headless":
                overrides[cfg_key] = val.lower() in ("true", "1", "yes")
            elif cfg_key in ("navigation_timeout", "implicit_wait"):
                try:
                    overrides[cfg_key] = int(val)
                except ValueError:
                    pass
            elif cfg_key in ("human_delay_min", "human_delay_max"):
                try:
                    overrides[cfg_key] = float(val)
                except ValueError:
                    pass
            else:
                overrides[cfg_key] = val
    return overrides


def get_browser_config() -> dict:
    """
    Get browser configuration, with TOML as the primary source.

    Precedence (highest first):

    1. ``botmask.toml`` config file — all browser/profile/cdp/behavior settings.
       If a key is present in TOML, it is used exclusively; the env vars listed
       below are *only* used for the display vars noted below.

    2. Environment variables — **only** the display vars ``DISPLAY`` and
       ``WAYLAND_DISPLAY`` are read from the host environment; they override
       any corresponding TOML values so that a running container / bare-metal
       setup can still locate its display surface.

    3. Built‑in defaults — used when a TOML key is absent and the env var
       is also absent.  These defaults ensure the project starts immediately
       without any config file or env var.

    Keys that always come from the environment (never from TOML):

    - ``display``   — X11 display server address (e.g. ``:0``)
    - ``wayland_display``  — Wayland display socket name
      (e.g. ``wayland-0``)

    All other keys (browser paths, profile, timeouts, human delays, cdp
    settings, etc.) are driven exclusively by the TOML file or the project
    built‑in defaults.

    Returns:
        Dictionary with all browser configuration options.
    """

    # ---------- 1. Load TOML config file ----------
    toml = _find_toml()          # may be {}
    if toml:
        merged = dict(toml)
    else:
        merged = {}

    # ---------- 2. Override display vars from the environment ----------
    # These MUST come from the host environment; never from TOML.
    merged["display"] = os.getenv("DISPLAY")
    merged["wayland_display"] = os.getenv("WAYLAND_DISPLAY")

    # ---------- 3. Ensure critical keys have sane defaults ----------
    # If the TOML file is missing or a key is absent, fall back to defaults
    # only for keys that have no reasonable alternative source.
    defaults = {
        "user_data_dir": "/app/browser_data",
        "executable_path": "/usr/bin/brave-browser",
        "headless": False,
        "locale": "es-VE",
        "timezone": "America/Caracas",
        "latitude": 10.4806,
        "longitude": -66.9036,
        "navigation_timeout": 30,
        "implicit_wait": 10,
        "human_delay_min": 1.0,
        "human_delay_max": 3.0,
    }
    for k, v in defaults.items():
        merged.setdefault(k, v)

    # --- BOTMASK_* env overrides are no longer the primary mechanism;
    # the TOML file is.  Keep a tiny namespace‑safe fallback so that a user
    # can quickly toggle a single flag at the shell without editing a file:
    tiny_over = {}
    for key in ("headless", "locale", "timezone", "navigation_timeout",
                "implicit_wait", "human_delay_min", "human_delay_max"):
        val = os.getenv(f"BOTMASK_{key.upper()}")
        if val is not None:
            tiny_over[key] = val
    merged.update(tiny_over)   # BOTMASK_* still wins over defaults, but
                               # TOML keys already set are preserved because
                               # dict.update() only inserts missing keys when
                               # using dict.setdefault — but update() overrides.
    # Actually, to keep TOML as supreme, we should NOT update with tiny_over
    # if the key already exists in merged from TOML.  Let's do it properly:
    for k, v in tiny_over.items():
        if k not in merged or merged[k] is None:
            merged[k] = v

    return merged


def get_browser_args() -> list:
    """
    Get browser launch arguments from BROWSER_ARGS env var.

    Enhanced with anti-detection flags.

    Returns:
        List of browser arguments
    """
    args_str = get_env("BROWSER_ARGS", "")

    if not args_str:
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
            "--password-store=basic",
            "--use-mock-keychain",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-ipc-flooding-protection",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--disable-background-timer-throttling",
            "--window-size=1920,1080",
        ]

        # Auto-detect Wayland and set ozone platform
        wayland_display = os.getenv("WAYLAND_DISPLAY")
        if wayland_display:
            args.append("--ozone-platform=wayland")
        else:
            args.append("--ozone-platform=x11")

        cdp_port = get_env("BROWSER_CDP_PORT", "")
        if cdp_port:
            cdp_host = get_env("BROWSER_CDP_HOST", "0.0.0.0")
            args.append(f"--remote-debugging-port={cdp_port}")
            args.append(f"--remote-debugging-address={cdp_host}")

        return args

    try:
        return shlex.split(args_str)
    except Exception as e:
        print(f"Warning: Failed to parse BROWSER_ARGS: {e}", file=sys.stderr)
        print(f"Using default arguments instead", file=sys.stderr)
        return [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ]


def get_launch_options(persistent: bool = False) -> dict:
    """
    Get launch options for Playwright browser.

    Uses the merged configuration from :func:`get_browser_config`, so the
    priority order is:

    1. ``BOTMASK_*`` environment variables (namespace‑safe, no collision with
       the host project's env vars).
    2. ``botmask.toml`` config file.
    3. Legacy bare env vars (``BROWSER_*``, ``DISPLAY``, etc.) – only used
       when the above sources do not provide a value.

    Args:
        persistent: Whether to use persistent context (for login-required sites)

    Returns:
        Dictionary with launch options
    """
    config = get_browser_config()

    # Headless from the merged config (BOTMASK_* > TOML > defaults > legacy)
    headless = config["headless"]

    # Browser args: prefer those from the config file / BOTMASK_* env,
    # otherwise fall back to reading ``BROWSER_ARGS`` env var.
    args = config.get("browser", {}).get("args") or get_browser_args()

    return {
        "executable_path": config["executable_path"],
        "headless": headless,
        "args": args,
        "ignore_default_args": ["--enable-automation"],
    }


USER_AGENT_POOL = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

VIEWPORT_POOL = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 2560, "height": 1440},
]


def get_rotated_user_agent() -> str:
    """Get a random User-Agent from the pool, or use BROWSER_USER_AGENT from .env."""
    env_ua = get_env("BROWSER_USER_AGENT", "")
    if env_ua:
        return env_ua
    return random.choice(USER_AGENT_POOL)


def get_rotated_viewport() -> dict:
    """Get a random viewport from the pool, or use BROWSER_VIEWPORT from .env."""
    env_viewport = get_env("BROWSER_VIEWPORT", "")
    if env_viewport:
        try:
            w, h = env_viewport.split("x")
            return {"width": int(w), "height": int(h)}
        except (ValueError, AttributeError):
            pass
    return random.choice(VIEWPORT_POOL)


def get_browserforge_headers() -> Optional[dict]:
    """Generate a coherent HTTP header set (UA + sec-ch-ua + Sec-Fetch-*) via BrowserForge.

    Fallback: returns None when BrowserForge is unavailable or generation fails,
    so the static pools below remain the fallback.

    Returns:
        dict of HTTP headers, or None
    """
    try:
        from browserforge.headers import HeaderGenerator
    except ImportError as e:
        print(f"Warning: BrowserForge not available, using static pools: {e}", file=sys.stderr)
        return None
    try:
        locale = get_env("BROWSER_LOCALE", "es-VE")
        hg = HeaderGenerator(browser=["chrome"], os=["linux"], locale=[locale])
        return dict(hg.generate())
    except Exception as e:
        print(f"Warning: BrowserForge header generation failed, using static pools: {e}", file=sys.stderr)
        return None


def get_context_options(persistent: bool = False, extra_headers: dict = None) -> dict:
    """
    Get context options for Playwright browser context.

    HTTP headers and User-Agent come from a coherent BrowserForge set
    (matching sec-ch-ua / Accept-Language / Sec-Fetch-*), falling back to the
    static pools when unavailable. .env overrides (BROWSER_USER_AGENT,
    BROWSER_VIEWPORT) always win.

    Args:
        persistent: Whether to use persistent context
        extra_headers: Additional HTTP headers to add

    Returns:
        Dictionary with context options
    """
    config = get_browser_config()
    headers = get_browserforge_headers()

    # User-Agent precedence: .env > BrowserForge coherent UA > static pool
    env_ua = get_env("BROWSER_USER_AGENT", "")
    if env_ua:
        user_agent = env_ua
    elif headers and headers.get("User-Agent"):
        user_agent = headers["User-Agent"]
    else:
        user_agent = get_rotated_user_agent()

    http_headers = dict(headers) if headers else {}
    http_headers.setdefault("Accept-Language", f"{config['locale']},es;q=0.9,en;q=0.8")
    http_headers.setdefault("Referer", "https://www.google.com/")

    # Add extra headers if provided
    if extra_headers:
        http_headers.update(extra_headers)

    options = {
        "locale": config["locale"],
        "timezone_id": config["timezone"],
        "viewport": get_rotated_viewport(),
        "user_agent": user_agent,
        "extra_http_headers": http_headers,
    }

    # Add geolocation if coordinates are provided
    if config["latitude"] and config["longitude"]:
        options["geolocation"] = {
            "latitude": config["latitude"],
            "longitude": config["longitude"],
        }
        options["permissions"] = ["geolocation"]

    # Add user data dir for persistent contexts
    if persistent:
        options["user_data_dir"] = config["user_data_dir"]

    return options


def ensure_user_data_dir():
    """Ensure browser user data directory exists."""
    config = get_browser_config()
    Path(config["user_data_dir"]).mkdir(parents=True, exist_ok=True)


def get_cdp_url() -> str:
    """
    Get the CDP endpoint URL for connecting to the already-running browser.

    The browser is started by the container entrypoint (start.sh)
    with --remote-debugging-port. All scripts connect via CDP instead
    of launching their own browser instance.

    Returns:
        CDP WebSocket URL (e.g. http://127.0.0.1:9222)
    """
    port = get_env("BROWSER_CDP_PORT", "9222")
    host = get_env("BROWSER_CDP_HOST", "127.0.0.1")
    return f"http://{host}:{port}"


# Export main functions
__all__ = [
    "get_browser_config",
    "get_browser_args",
    "get_launch_options",
    "get_context_options",
    "ensure_user_data_dir",
    "get_cdp_url",
    "get_rotated_user_agent",
    "get_rotated_viewport",
    "get_browserforge_headers",
    "USER_AGENT_POOL",
    "VIEWPORT_POOL",
]
