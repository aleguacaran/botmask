#!/usr/bin/env python3
"""
Browser Configuration Module - tuqueque

Centralized browser configuration for the humanized browser automation toolkit.
All browser options are sourced from .env file (inherited from the jobs project).

Usage:
    from tuqueque.config import get_browser_config, get_launch_options

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
    """Look for a tuqueque.toml config file.

    Search order:
    1. ``TUQUEQUE_CONFIG`` env var (absolute path)
    2. ``tuqueque.toml`` in the current working directory
    3. ``~/.config/tuqueque/tuqueque.toml``
    Returns an empty dict if none is found.
    """
    # 1. explicit path
    explicit = os.getenv("TUQUEQUE_CONFIG")
    if explicit and Path(explicit).is_file():
        with open(explicit, "rb") as f:
            return tomllib.load(f)

    # 2. cwd
    cwd = Path("tuqueque.toml")
    if cwd.is_file():
        with open(cwd, "rb") as f:
            return tomllib.load(f)

    # 3. XDG config dir
    xdg = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "tuqueque" / "tuqueque.toml"
    if xdg.is_file():
        with open(xdg, "rb") as f:
            return tomllib.load(f)

    return {}


def _env_overrides() -> dict:
    """Read ``TUQUEQUE_*`` env vars and map them into config keys.

    This namespace is **isolated** from the host's generic ``BROWSER_*`` /
    ``DISPLAY`` etc., so embedding tuqueque in another project never collides.

    Supported mappings (env key → config dict key):
        TUQUEQUE_HEADLESS      → config["headless"]
        TUQUEQUE_LOCALE        → config["locale"]
        TUQUEQUE_TIMEZONE      → config["timezone"]
        TUQUEQUE_NAVIGATION_TIMEOUT   → config["navigation_timeout"]
        TUQUEQUE_IMPLICIT_WAIT        → config["implicit_wait"]
        TUQUEQUE_DELAY_MIN     → config["human_delay_min"]
        TUQUEQUE_DELAY_MAX     → config["human_delay_max"]
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
        val = os.getenv("TUQUEQUE_%s" % env_key)
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
    Get browser configuration, with the following precedence (highest first):

    1. ``TUQUEQUE_*`` environment variables (isolated namespace – no collision
       with the host project's env vars).
    2. ``tuqueque.toml`` config file ( discovered via ``TUQUEQUE_CONFIG``,
       ``./tuqueque.toml``, or ``~/.config/tuqueque/tuqueque.toml``).
    3. Legacy bare env vars (``BROWSER_*``, ``DISPLAY``, etc.) – only used
       when the above sources do not provide a value, so that the Docker
       ``.env`` / compose workflow still works unchanged.

    Returns:
        Dictionary with all browser configuration options.
    """

    # ---------- 1. built‑in defaults ----------
    defaults = {
        # Browser paths
        "user_data_dir": "/app/browser_data",
        "executable_path": "/usr/bin/brave-browser",

        # Display and headless
        "headless": False,
        "display": None,
        "wayland_display": None,

        # Profile and geolocation
        "locale": "es-VE",
        "timezone": "America/Caracas",
        "latitude": 10.4806,
        "longitude": -66.9036,

        # Timeouts
        "navigation_timeout": 30,
        "implicit_wait": 10,

        # Human delays
        "human_delay_min": 1.0,
        "human_delay_max": 3.0,
    }

    # ---------- 2. TUQUEQUE_* env overrides (namespace‑safe) ----------
    overrides = _env_overrides()

    # ---------- 3. TOML config file ----------
    toml = _find_toml()

    # ---------- 4. Merge: TUQUEQUE > TOML > defaults, then legacy fallback ----------
    merged = dict(defaults)          # start with defaults
    merged.update(toml)            # TOML overrides defaults
    merged.update(overrides)       # TUQUEQUE_* overrides TOML & defaults

    # Legacy bare env vars as final fallback (only when new sources omit a key)
    legacy = {
        "user_data_dir": get_env("BROWSER_USER_DATA_DIR"),
        "executable_path": get_env("BROWSER_EXECUTABLE_PATH"),
        "headless": get_env("BROWSER_HEADLESS", "").lower() == "true",
        "display": get_env("DISPLAY"),
        "wayland_display": get_env("WAYLAND_DISPLAY"),
        "locale": get_env("BROWSER_LOCALE"),
        "timezone": get_env("BROWSER_TIMEZONE"),
        "latitude": float(get_env("BROWSER_LATITUDE", "10.4806"))
        if get_env("BROWSER_LATITUDE") else 10.4806,
        "longitude": float(get_env("BROWSER_LONGITUDE", "-66.9036"))
        if get_env("BROWSER_LONGITUDE") else -66.9036,
        "navigation_timeout": int(get_env("BROWSER_NAVIGATION_TIMEOUT", "30"))
        if get_env("BROWSER_NAVIGATION_TIMEOUT")
        else 30,
        "implicit_wait": int(get_env("BROWSER_IMPLICIT_WAIT", "10"))
        if get_env("BROWSER_IMPLICIT_WAIT")
        else 10,
        "human_delay_min": float(get_env("HUMAN_DELAY_MIN", "1.0"))
        if get_env("HUMAN_DELAY_MIN")
        else 1.0,
        "human_delay_max": float(get_env("HUMAN_DELAY_MAX", "3.0"))
        if get_env("HUMAN_DELAY_MAX")
        else 3.0,
    }
    for k, v in legacy.items():
        if merged.get(k) is None:  # only fill if not already set by higher priority
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

    1. ``TUQUEQUE_*`` environment variables (namespace‑safe, no collision with
       the host project's env vars).
    2. ``tuqueque.toml`` config file.
    3. Legacy bare env vars (``BROWSER_*``, ``DISPLAY``, etc.) – only used
       when the above sources do not provide a value.

    Args:
        persistent: Whether to use persistent context (for login-required sites)

    Returns:
        Dictionary with launch options
    """
    config = get_browser_config()

    # Headless from the merged config (TUQUEQUE_* > TOML > defaults > legacy)
    headless = config["headless"]

    # Browser args: prefer those from the config file / TUQUEQUE_* env,
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
