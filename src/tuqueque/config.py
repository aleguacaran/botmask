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
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def get_env(key: str, default=None):
    """Get environment variable or default."""
    return os.getenv(key, default)


def get_browser_config() -> dict:
    """
    Get browser configuration from .env.

    Returns:
        Dictionary with all browser configuration options
    """
    return {
        # Browser paths
        "user_data_dir": get_env("BROWSER_USER_DATA_DIR", "/app/browser_data"),
        "executable_path": get_env("BROWSER_EXECUTABLE_PATH", "/usr/bin/brave-browser"),

        # Display and headless
        "headless": get_env("BROWSER_HEADLESS", "false").lower() == "true",
        "display": get_env("DISPLAY"),
        "wayland_display": get_env("WAYLAND_DISPLAY"),

        # Profile and geolocation
        "locale": get_env("BROWSER_LOCALE", "es-VE"),
        "timezone": get_env("BROWSER_TIMEZONE", "America/Caracas"),
        "latitude": float(get_env("BROWSER_LATITUDE", "10.4806")),
        "longitude": float(get_env("BROWSER_LONGITUDE", "-66.9036")),

        # Timeouts
        "navigation_timeout": int(get_env("BROWSER_NAVIGATION_TIMEOUT", "30")),
        "implicit_wait": int(get_env("BROWSER_IMPLICIT_WAIT", "10")),

        # Human delays
        "human_delay_min": float(get_env("HUMAN_DELAY_MIN", "1.0")),
        "human_delay_max": float(get_env("HUMAN_DELAY_MAX", "3.0")),
    }


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

    CRITICAL: BROWSER_HEADLESS from .env takes absolute precedence.
    Only auto-detect if BROWSER_HEADLESS is not set.

    Args:
        persistent: Whether to use persistent context (for login-required sites)

    Returns:
        Dictionary with launch options
    """
    config = get_browser_config()

    # PRIORITY: 1) BROWSER_HEADLESS from .env, 2) auto-detect from display availability
    env_headless = get_env("BROWSER_HEADLESS", "").lower()

    if env_headless in ("true", "false"):
        # .env takes absolute precedence - never override this
        headless = env_headless == "true"
    else:
        # Auto-detect only if BROWSER_HEADLESS not explicitly set
        display_available = config["display"] or config["wayland_display"]
        headless = not display_available
        print(f"⚠️  Warning: BROWSER_HEADLESS not set in .env, auto-detected headless={headless}", file=sys.stderr)

    return {
        "executable_path": config["executable_path"],
        "headless": headless,
        "args": get_browser_args(),
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


def get_context_options(persistent: bool = False, extra_headers: dict = None) -> dict:
    """
    Get context options for Playwright browser context.

    Args:
        persistent: Whether to use persistent context
        extra_headers: Additional HTTP headers to add

    Returns:
        Dictionary with context options
    """
    config = get_browser_config()

    options = {
        "locale": config["locale"],
        "timezone_id": config["timezone"],
        "viewport": get_rotated_viewport(),
        "user_agent": get_rotated_user_agent(),
        "extra_http_headers": {
            "Accept-Language": f"{config['locale']},es;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Referer": "https://www.google.com/",
        },
    }

    # Add extra headers if provided
    if extra_headers:
        options["extra_http_headers"].update(extra_headers)

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
    "USER_AGENT_POOL",
    "VIEWPORT_POOL",
]
