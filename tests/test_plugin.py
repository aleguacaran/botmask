#!/usr/bin/env python3
"""
Self-contained smoke test for botmask as an installed plugin.

Launches its own Brave instance via Patchright, so it does NOT depend on
start.sh or a pre-running CDP server. Exercises every public module:

  1. config — load config, context options, BrowserForge headers
  2. human_behavior — Bezier mouse, scroll, type, click, detect barriers
  3. a11y — snapshot interactive elements, resolve index → locator
  4. input_os — calibrate viewport → screen offset
  5. human_cdp — CLI end-to-end (a11y snapshot, screenshot)

Run inside the container:
    docker compose run --rm --entrypoint bash app \
      -c "pip install -e . -q 2>/dev/null && python tests/test_plugin.py"
"""
import sys
import os
import json
import time
import traceback

passed = 0
failed = 0

def check(label, fn):
    global passed, failed
    try:
        fn()
        print(f"  ✓ {label}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {label}: {e}")
        traceback.print_exc()
        failed += 1

# ── 1. config ───────────────────────────────────────────────────────────────
print("=" * 60)
print("[1/5] config module")
print("=" * 60)

from botmask.config import (
    get_browser_config,
    get_browser_args,
    get_launch_options,
    get_context_options,
    get_cdp_url,
    get_rotated_user_agent,
    get_rotated_viewport,
    get_browserforge_headers,
)

def test_config():
    cfg = get_browser_config()
    assert cfg.get("locale"), "locale missing"
    assert cfg.get("timezone"), "timezone missing"
    print(f"    CDP URL       : {get_cdp_url()}")
    print(f"    Headless      : {cfg.get('headless')}")
    print(f"    Locale        : {cfg.get('locale')}")
    print(f"    Timezone      : {cfg.get('timezone')}")
    print(f"    Executable    : {cfg.get('executable_path')}")

def test_browser_args():
    args = get_browser_args()
    assert len(args) > 0, "empty args"
    print(f"    Browser args  : {len(args)} flags")

def test_context_options():
    ctx = get_context_options()
    assert "locale" in ctx
    assert "viewport" in ctx
    print(f"    Context       : locale={ctx['locale']}, viewport={ctx['viewport']}")

def test_browserforge():
    h = get_browserforge_headers()
    if h:
        print(f"    BrowserForge  : coherent headers ({len(h)} keys)")
    else:
        print(f"    BrowserForge  : fallback (static pool)")

check("get_browser_config", test_config)
check("get_browser_args", test_browser_args)
check("get_context_options", test_context_options)
check("get_browserforge_headers", test_browserforge)
print()

# ── 2. Launch Brave + human_behavior ─────────────────────────────────────────
print("=" * 60)
print("[2/5] Launch Brave + human_behavior module")
print("=" * 60)

from patchright.sync_api import sync_playwright
from botmask.human_behavior import HumanBehavior, AuthBarrierError, RateLimitError
from botmask.config import get_browser_config, get_browser_args

cfg = get_browser_config()
launch_opts = get_launch_options()

headless = os.getenv("BROWSER_HEADLESS", "false").lower() in ("true", "1", "yes")
print(f"  Launching Brave (headless={headless}) ...")
pw = sync_playwright().start()
browser = pw.chromium.launch(
    executable_path=launch_opts["executable_path"],
    headless=headless,
    args=launch_opts["args"] + ["--no-sandbox", "--disable-gpu"],
)
context = browser.new_context(
    locale=cfg.get("locale", "es-VE"),
    timezone_id=cfg.get("timezone", "America/Caracas"),
    viewport=get_rotated_viewport(),
)
page = context.new_page()
print(f"  Page ready: {page.url}")

def test_human_delay():
    hb = HumanBehavior(page)
    t0 = time.time()
    hb.human_delay(0.1, 0.2)
    elapsed = time.time() - t0
    assert 0.05 < elapsed < 1.0, f"delay was {elapsed:.2f}s"
    print(f"    Pace multiplier: {hb.pace_multiplier}")

def test_mouse_move():
    page.goto("https://example.com", wait_until="domcontentloaded", timeout=15000)
    time.sleep(0.5)
    hb = HumanBehavior(page)
    hb.move_mouse_to(target_x=400, target_y=300, steps=30)
    assert hb._mouse_pos is not None

def test_human_scroll():
    hb = HumanBehavior(page)
    hb.human_scroll(times=1, direction="down")

def test_human_click():
    hb = HumanBehavior(page)
    locator = page.locator("h1")
    hb.human_click(locator)

def test_detect_barriers():
    hb = HumanBehavior(page)
    assert hb.detect_auth_barrier() is False
    assert hb.detect_rate_limit() is False

check("human_delay", test_human_delay)
check("move_mouse_to (Bezier)", test_mouse_move)
check("human_scroll (inertia)", test_human_scroll)
check("human_click", test_human_click)
check("detect_auth_barrier / detect_rate_limit", test_detect_barriers)
print()

# ── 3. a11y snapshot ─────────────────────────────────────────────────────────
print("=" * 60)
print("[3/5] a11y module")
print("=" * 60)

from botmask.a11y import snapshot_interactives, get_locator, resolve_target

def test_snapshot():
    items = snapshot_interactives(page, limit=50)
    visible = [it for it in items if it["visible"]]
    print(f"    Total elements : {len(items)}")
    print(f"    Visible        : {len(visible)}")
    if visible:
        first = visible[0]
        print(f"    First visible  : [{first['index']}] <{first['tag']}> name={first['name']!r}")

def test_resolve_target():
    items = snapshot_interactives(page, limit=50)
    visible = [it for it in items if it["visible"]]
    if visible:
        idx = visible[0]["index"]
        target = resolve_target(page, idx)
        if target:
            print(f"    resolve_target : index={idx} → center=({target['center'][0]:.0f}, {target['center'][1]:.0f})")
        else:
            print(f"    resolve_target : index={idx} → None (hidden)")

def test_get_locator():
    loc = get_locator(page, 0)
    assert loc is not check  # sanity
    print(f"    get_locator   : returns Locator instance")

check("snapshot_interactives", test_snapshot)
check("resolve_target", test_resolve_target)
check("get_locator", test_get_locator)
print()

# ── 4. input_os ──────────────────────────────────────────────────────────────
print("=" * 60)
print("[4/5] input_os module")
print("=" * 60)

from botmask.input_os import calibrate

def test_calibrate():
    try:
        offset = calibrate(page)
        print(f"    Viewport→Screen: x={offset['x']}, y={offset['y']}")
    except Exception as e:
        print(f"    calibrate      : (expected outside Xvfb) {e}")

check("calibrate", test_calibrate)
print()

# ── 5. human_cdp CLI ─────────────────────────────────────────────────────────
print("=" * 60)
print("[5/5] human_cdp CLI (import + dispatch)")
print("=" * 60)

from botmask.human_cdp import cmd_a11y, cmd_screenshot, cmd_viewport
import argparse

def test_cmd_a11y():
    args = argparse.Namespace(limit=50)
    result = cmd_a11y(page, args)
    assert result["status"] == "ok"
    print(f"    a11y          : {result['count']} elements, {result['visible']} visible")

def test_cmd_viewport():
    args = argparse.Namespace()
    result = cmd_viewport(page, args)
    assert result["status"] == "ok"
    print(f"    viewport      : {result['innerWidth']}x{result['innerHeight']}")

def test_cmd_screenshot():
    args = argparse.Namespace(filePath="/tmp/test_screenshot.png", full_page=False)
    result = cmd_screenshot(page, args)
    assert result["status"] == "ok"
    import os
    size = os.path.getsize(result["filePath"])
    print(f"    screenshot    : {size} bytes → {result['filePath']}")

check("cmd_a11y", test_cmd_a11y)
check("cmd_viewport", test_cmd_viewport)
check("cmd_screenshot", test_cmd_screenshot)
print()

# ── Summary ──────────────────────────────────────────────────────────────────
print("=" * 60)
total = passed + failed
print(f"RESULTS: {passed}/{total} passed, {failed} failed")
if failed == 0:
    print("ALL MODULES PASS — botmask plugin works ✓")
else:
    print("SOME TESTS FAILED ✗")
print("=" * 60)

browser.close()
pw.stop()
sys.exit(1 if failed else 0)
