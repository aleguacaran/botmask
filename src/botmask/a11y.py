#!/usr/bin/env python3
"""
Accessibility Snapshot Module — numbered interactive elements for AI targeting.

The AI never computes pixel coordinates. It picks an element by index from a
numbered snapshot; this module resolves index -> locator -> bounding_box.

Usage:
    from botmask.a11y import snapshot_interactives, get_locator

    items = snapshot_interactives(page)   # [{"index": 0, "tag": "a", ...}, ...]
    locator = get_locator(page, 42)       # -> page.locator(...).nth(42)
"""

from typing import Dict, List, Optional

from patchright.sync_api import Locator, Page

# Must match the JS in snapshot_interactives so index -> locator is stable.
INTERACTIVE_SELECTOR = (
    "a, button, input, select, textarea, summary, "
    "[role=button], [role=link], [role=tab], [role=menuitem], "
    "[contenteditable=true], [onclick], [data-testid]"
)

MAX_ITEMS = 300


def snapshot_interactives(page: Page, limit: int = MAX_ITEMS) -> List[Dict]:
    """Collect interactive elements in document order, numbered from 0.

    Indices are positions in the full (unfiltered) INTERACTIVE_SELECTOR list,
    so ``get_locator(page, index)`` always resolves to the same element even
    after the page changes. Hidden elements are marked ``visible: false`` and
    kept in the list only to preserve stable numbering.

    Args:
        page: The Playwright page.
        limit: Maximum number of entries to return.

    Returns:
        List of dicts with index, tag, role, type, name, href, visible, box.
    """
    items = page.evaluate(
        """(arg) => {
            const sel = arg.sel;
            const maxItems = arg.maxItems;
            const els = Array.from(document.querySelectorAll(sel));
            const isVisible = (el) => {
                const r = el.getBoundingClientRect();
                if (!r.width && !r.height) return false;
                const s = getComputedStyle(el);
                if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
                return true;
            };
            const name = (el) => {
                let t = (el.getAttribute('aria-label')
                    || el.value
                    || el.placeholder
                    || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
                return t;
            };
            const box = (el) => {
                const r = el.getBoundingClientRect();
                return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
            };
            const out = [];
            for (let i = 0; i < els.length; i++) {
                const el = els[i];
                const b = box(el);
                if (out.length >= maxItems) break;
                out.push({
                    index: i,
                    tag: el.tagName.toLowerCase(),
                    role: el.getAttribute('role') || '',
                    type: el.getAttribute('type') || '',
                    name: name(el),
                    href: el.getAttribute('href') || '',
                    visible: isVisible(el),
                    box: b,
                });
            }
            return out;
        }""",
        {"sel": INTERACTIVE_SELECTOR, "maxItems": limit},
    )
    return items


def get_locator(page: Page, index: int) -> Locator:
    """Resolve a snapshot index to a locator on the same INTERACTIVE_SELECTOR list."""
    return page.locator(INTERACTIVE_SELECTOR).nth(index)


def resolve_target(page: Page, index: int, require_visible: bool = True) -> Optional[Dict]:
    """Resolve index to (locator, box). Returns None when the element is gone/hidden.

    Args:
        page: The Playwright page.
        index: Snapshot index.
        require_visible: Reject hidden elements (no bounding box).

    Returns:
        dict with "locator", "box" and "center", or None.
    """
    locator = get_locator(page, index)
    box = locator.bounding_box()
    if not box or (require_visible and (box["width"] == 0 or box["height"] == 0)):
        return None
    return {
        "locator": locator,
        "box": box,
        "center": (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2),
    }