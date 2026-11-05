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
import time
from pathlib import Path

# Ensure package is importable when run directly
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))


def _in_container() -> bool:
    """True when running inside a container (Docker/containerd/podman/k8s)."""
    if Path("/.dockerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup").read_text()
    except OSError:
        return False
    return any(k in cgroup for k in ("docker", "containerd", "kubepods", "libpod"))


def _resolve_relay(relay_setting: str, cdp_port: str) -> tuple[bool, str]:
    """Decide whether the CDP relay runs and on which port.

    ``auto`` (default): relay only inside containers — the loopback-only CDP
    bind is a barrier there, while a bare-metal consumer on the same host
    reaches 127.0.0.1 directly and may not even have socat installed.
    A port number forces the relay on; ``off`` disables it.
    """
    setting = relay_setting.strip().lower()
    default_port = str(int(cdp_port) + 1)
    if setting in ("off", "no", "0"):
        return False, default_port
    if setting in ("auto", ""):
        return _in_container(), default_port
    return True, setting if setting.isdigit() else default_port


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

    # All runtime settings come from botmask.toml (TOML > defaults).
    # Only DISPLAY/WAYLAND_DISPLAY stay env-driven (host-injected values).
    cdp_port = str(cfg["cdp_port"])
    relay_on, relay_port = _resolve_relay(str(cfg["cdp_relay_port"]), cdp_port)

    cmd = [cfg["executable_path"]] + args + [
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={cfg['user_data_dir']}",
    ]

    proc = subprocess.Popen(cmd)
    print(f"[botmask] Brave launched (pid={proc.pid}), CDP on 127.0.0.1:{cdp_port} "
          f"(loopback only)",
          flush=True)

    # Forward signals to both children so docker stop works cleanly
    relay: subprocess.Popen | None = None

    def _shutdown(*_):
        proc.terminate()
        if relay:
            relay.terminate()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Brave ignores --remote-debugging-address and binds CDP to 127.0.0.1 ONLY,
    # so other containers/hosts cannot reach it through a published port. Relay
    # the CDP endpoint on 0.0.0.0:<relay_port> so consumers work cross-container.
    # auto: only inside containers (bare metal reaches loopback directly).
    if relay_on:
        try:
            import urllib.request

            for _ in range(60):
                try:
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{cdp_port}/json/version", timeout=1
                    )
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(1)
            relay = subprocess.Popen([
                "socat",
                f"TCP-LISTEN:{relay_port},reuseaddr,fork",
                f"TCP:127.0.0.1:{cdp_port}",
            ])
            print(f"[botmask] CDP relay on 0.0.0.0:{relay_port} -> 127.0.0.1:{cdp_port}. "
                  f"Cross-container/host consumers connect via IP:{relay_port} "
                  f"(not the DNS name — Brave rejects non-IP Host headers)",
                  flush=True)
        except FileNotFoundError:
            print(f"[botmask] ERROR: socat not found — the CDP relay on "
                  f"{relay_port} could not start. Other containers cannot reach "
                  f"this browser; install socat or set cdp_relay_port = \"off\" "
                  f"in botmask.toml.",
                  file=sys.stderr)
    else:
        print(f"[botmask] CDP relay skipped (botmask.toml cdp_relay_port="
              f"\"{cfg['cdp_relay_port']}\"); CDP reachable at "
              f"127.0.0.1:{cdp_port} from this host only.",
              flush=True)

    try:
        code = proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        code = 0
    finally:
        if relay:
            relay.terminate()
    sys.exit(code)


if __name__ == "__main__":
    main()
