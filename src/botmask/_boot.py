#!/usr/bin/env python3
"""
botmask bootstrap — launch Brave with CDP exposed, hold until killed.

Called by start.sh after deps are installed. Does NOT run pip install
itself — that belongs in start.sh or the Dockerfile.
"""
import json
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

    # Disable P3A telemetry in the profile's Local State
    local_state = data_dir / "Local State"
    if local_state.exists():
        try:
            state = json.loads(local_state.read_text())
        except (json.JSONDecodeError, OSError):
            state = {}
    else:
        state = {}
    state.setdefault("brave", {})
    state["brave"].setdefault("p3a", {})["enabled"] = False
    state["brave"].setdefault("stats", {})["reporting_enabled"] = False
    local_state.write_text(json.dumps(state))

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

    # Brave often ignores --remote-debugging-address and binds to 127.0.0.1 only.
    # Use socat to forward 0.0.0.0:9223 → 127.0.0.1:9222 so CDP is reachable from outside.
    socat_port = int(cdp_port) + 1
    socat = subprocess.Popen(
        ["socat", f"TCP-LISTEN:{socat_port},fork,bind=0.0.0.0", f"TCP:127.0.0.1:{cdp_port}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    print(f"[botmask] socat relay :{socat_port} → :{cdp_port} (pid={socat.pid})", flush=True)

    # Forward signals to Brave so docker stop works cleanly
    def shutdown(*_):
        proc.terminate()
        socat.terminate()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        sys.exit(proc.wait())
    except KeyboardInterrupt:
        proc.terminate()
        sys.exit(0)


if __name__ == "__main__":
    main()
