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


def calibrate(page: Page) -> Dict:
    """Compute the viewport->screen offset for the current window position."""
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