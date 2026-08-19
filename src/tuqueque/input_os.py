#!/usr/bin/env python3
"""
OS-level Input Module — viewport -> screen calibration + PyAutoGUI dispatch.

Hard-target fallback when CDP/DOM input is detected. Converts viewport CSS
coordinates to screen coordinates:

    screen = viewport + window_offset
    window_offset = (window.screenX, window.screenY) + (outerHeight - innerHeight)

On Xvfb + a window manager the window position is deterministic, so calibrate
once after launch and reuse. Re-derive the offset before every batch of clicks
(the window can drift).

Usage:
    from tuqueque.input_os import calibrate, click_at, click_locator

    click_locator(page, locator)
"""

from typing import Dict, Tuple

from patchright.sync_api import Locator, Page


def _window_geometry() -> Dict:
    """Get the top-level browser window geometry from the X server (xdotool).

    Returns the largest visible Brave window: {"x", "y", "w", "h"} in screen
    pixels, or an empty dict when xdotool is unavailable / no window found.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["xdotool", "search", "--onlyvisible", "--class", "brave"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return {}
    best = {}
    for wid in out.stdout.split():
        try:
            g = subprocess.run(
                ["xdotool", "getwindowgeometry", "--shell", wid],
                capture_output=True, text=True, timeout=5,
            ).stdout
        except Exception:
            continue
        kv = {}
        for line in g.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                try:
                    kv[k] = int(v)
                except ValueError:
                    pass
        area = kv.get("WIDTH", 0) * kv.get("HEIGHT", 0)
        if area > best.get("w", 0) * best.get("h", 0):
            best = {"x": kv.get("X", 0), "y": kv.get("Y", 0), "w": kv.get("WIDTH", 0), "h": kv.get("HEIGHT", 0)}
    return best


def calibrate(page: Page) -> Dict:
    """Compute the viewport->screen offset for the current window position.

    screen = window_origin + (window_size - content_size) + viewport_point

    The X window can be larger than the content (openbox frame/chrome), so the
    content origin inside the window is derived from the X window geometry
    (xdotool) minus the JS inner size. Falls back to window.screenX/screenY +
    browser chrome when xdotool is unavailable.
    """
    win = _window_geometry()
    if win:
        inner = page.evaluate("() => ({w: innerWidth, h: innerHeight})")
        return {
            "x": win["x"] + (win["w"] - inner["w"]),
            "y": win["y"] + (win["h"] - inner["h"]),
        }
    return page.evaluate(
        """() => ({
            x: window.screenX,
            y: window.screenY + (window.outerHeight - window.innerHeight),
        })"""
    )


def _pyautogui():
    try:
        import pyautogui
    except Exception as e:
        raise RuntimeError(
            f"OS-level input unavailable (no display / PyAutoGUI): {e}"
        ) from e
    pyautogui.FAILSAFE = False
    return pyautogui


def move_to(page: Page, x: float, y: float, duration: float = 0.2) -> Dict:
    """Move the OS cursor to a viewport coordinate (x, y)."""
    pg = _pyautogui()
    off = calibrate(page)
    pg.moveTo(x + off["x"], y + off["y"], duration=duration)
    return {"x": x, "y": y, "offset": off}


def click_at(page: Page, x: float, y: float, button: str = "left", duration: float = 0.2) -> Dict:
    """OS-level click at a viewport coordinate (x, y)."""
    pg = _pyautogui()
    off = calibrate(page)
    pg.moveTo(x + off["x"], y + off["y"], duration=duration)
    pg.click(button=button)
    return {"x": x, "y": y, "offset": off}


def click_locator(page: Page, locator: Locator, button: str = "left") -> Dict:
    """OS-level click at the center of a locator's bounding box.

    Raises ValueError when the element has no bounding box (hidden/off-screen).
    """
    box = locator.bounding_box()
    if not box:
        raise ValueError("Element not visible (no bounding box)")
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    return click_at(page, cx, cy, button=button) | {"box": box}