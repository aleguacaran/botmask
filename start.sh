#!/bin/bash
set -e

BROWSER="${BROWSER_EXECUTABLE_PATH:-/usr/bin/brave-browser}"
DATA_DIR="${BROWSER_USER_DATA_DIR:-/app/browser_data}"
CDP_PORT="${BRAVE_CDP_PORT:-9222}"

# ── Display mode detection ──────────────────────────────────────────────────
# The container picks a mode from its environment, so one entrypoint serves
# both the local and server images:
#
#   Host-display (local dev, develop image)   DISPLAY or WAYLAND_DISPLAY is
#     set (shared from the host by compose.yaml) → just run the browser.
#   Virtual-display (server image)            no real display available →
#     boot Xvfb + openbox + x11vnc + noVNC first, then run the browser.
#
# Mode decision:
#   - VIRTUAL_DISPLAY=true                                  → force server mode
#   - no DISPLAY and no WAYLAND_DISPLAY (and not headless)  → auto-detect
#   - DISPLAY or WAYLAND_DISPLAY present                    → host display
need_virtual="false"
[ "${VIRTUAL_DISPLAY}" = "true" ] && need_virtual="true"
[ -z "${DISPLAY}" ] && [ -z "${WAYLAND_DISPLAY}" ] && \
    [ "${BROWSER_HEADLESS}" != "true" ] && need_virtual="true"

if [ "${need_virtual}" = "true" ]; then
    if ! command -v Xvfb >/dev/null 2>&1; then
        echo "ERROR: server mode requested (VIRTUAL_DISPLAY / no DISPLAY) but Xvfb is not installed." >&2
        echo "       Build/use the server image: docker compose up --build (target=server)" >&2
        exit 1
    fi
    echo "Server mode: starting virtual display (Xvfb :99)..."
    XVFB_SCREEN="${XVFB_SCREEN:-1920x1080x24}"
    Xvfb :99 -screen 0 "${XVFB_SCREEN}" -ac &
    sleep 1
    export DISPLAY=:99
    unset WAYLAND_DISPLAY

    # Window manager → deterministic window placement (needed for OS-level input calibration)
    if command -v openbox >/dev/null 2>&1; then
        openbox &
    fi

    # VNC + noVNC for remote viewing (noVNC web at :6080, VNC at :5900)
    if command -v x11vnc >/dev/null 2>&1; then
        x11vnc -display :99 -forever -shared -nopw -quiet &
    fi
    if command -v websockify >/dev/null 2>&1 && [ -d /usr/share/novnc ]; then
        websockify --web=/usr/share/novnc 6080 localhost:5900 &
    fi
    echo "Virtual display ready — noVNC at http://<host>:6080, VNC at :5900"
else
    echo "Host-display mode: DISPLAY=${DISPLAY:-unset} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-unset}"
fi

echo "Starting Brave Browser with CDP on port ${CDP_PORT}..."

rm -f "${DATA_DIR}"/Singleton*

[ "${BROWSER_HEADLESS}" = "true" ] && HEADLESS="--headless"

"${BROWSER}" \
    --user-data-dir="${DATA_DIR}" \
    --remote-debugging-port="${CDP_PORT}" \
    ${HEADLESS} \
    ${BROWSER_ARGS} &
BRAVE_PID=$!

echo "Waiting for CDP on port ${CDP_PORT}..."
for i in $(seq 1 30); do
    if curl -s http://127.0.0.1:${CDP_PORT}/json/version >/dev/null 2>&1; then
        echo "Brave ready (PID ${BRAVE_PID}) - CDP at ws://127.0.0.1:${CDP_PORT}"
        break
    fi
    sleep 1
done

# Relay CDP from port 9223 (0.0.0.0) to 9222 (127.0.0.1 - Brave)
RELAY_PORT=$((CDP_PORT + 1))
socat TCP-LISTEN:${RELAY_PORT},reuseaddr,fork TCP:127.0.0.1:${CDP_PORT} &
SOCAT_PID=$!
echo "CDP relay (PID ${SOCAT_PID}) - accepting connections on 0.0.0.0:${RELAY_PORT}"

wait $BRAVE_PID
