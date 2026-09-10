#!/usr/bin/env python3
"""
botmask bootstrap — launch Brave with CDP exposed, hold until killed.

Called by start.sh after deps are installed. Does NOT run pip install
itself — that belongs in start.sh or the Dockerfile.
"""
import os
import signal
import subprocess
import sys
from pathlib import Path

# Ensure package is importable when run directly
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))


def main():
    from botmask.config import get_browser_config, get_browser_args

    cfg = get_browser_config()
    args = get_browser_args()

    # Ensure user data dir exists
    data_dir = Path(cfg["user_data_dir"])
    data_dir.mkdir(parents=True, exist_ok=True)

    # Remove stale lock files from previous unclean shutdowns
    for lock in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        (data_dir / lock).unlink(missing_ok=True)

    cdp_port = os.getenv("BROWSER_CDP_PORT", "9222")
    cdp_host = os.getenv("BROWSER_CDP_HOST", "0.0.0.0")

    cmd = [cfg["executable_path"]] + args + [
        f"--remote-debugging-port={cdp_port}",
        f"--remote-debugging-address={cdp_host}",
        f"--user-data-dir={cfg['user_data_dir']}",
    ]

    proc = subprocess.Popen(cmd)
    print(f"[botmask] Brave launched (pid={proc.pid}), CDP on {cdp_host}:{cdp_port}",
          flush=True)

    # Forward signals to Brave so docker stop works cleanly
    signal.signal(signal.SIGTERM, lambda *_: proc.terminate())
    signal.signal(signal.SIGINT, lambda *_: proc.terminate())

    try:
        sys.exit(proc.wait())
    except KeyboardInterrupt:
        proc.terminate()
        sys.exit(0)


if __name__ == "__main__":
    main()
