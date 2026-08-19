#!/usr/bin/env python3
"""
Human Behavior CDP CLI — Human-like browser interactions via CDP.

Connects to the shared Brave CDP instance for all browser interactions.
Human-like commands (click, scroll, fill, hover, read, warm_up, navigate)
use the HumanBehavior class. Inspection commands (snapshot, eval,
list_pages, viewport) use direct CDP access. AI targeting commands
(a11y, a11y_click, os_click, input_calib) use the interaction-model modules.

Usage:
    python -m tuqueque.human_cdp click       "h2#Enlaces_externos"
    python -m tuqueque.human_cdp scroll      --times 3 --direction down
    python -m tuqueque.human_cdp hover       --count 4
    python -m tuqueque.human_cdp read        --sections 3
    python -m tuqueque.human_cdp warm_up
    python -m tuqueque.human_cdp viewport
    python -m tuqueque.human_cdp fill        "#input-id" "text to type"
    python -m tuqueque.human_cdp navigate    "https://example.com"
    python -m tuqueque.human_cdp type_text   "#search" "python developer"
    python -m tuqueque.human_cdp snapshot    [--filePath /tmp/snapshot.txt]
    python -m tuqueque.human_cdp eval        "document.title"
    python -m tuqueque.human_cdp list_pages
    python -m tuqueque.human_cdp new_page    "https://example.com"
    python -m tuqueque.human_cdp screenshot  [--filePath /tmp/shot.png]
    python -m tuqueque.human_cdp a11y        [--limit 300]
    python -m tuqueque.human_cdp a11y_click 42
    python -m tuqueque.human_cdp os_click    42
    python -m tuqueque.human_cdp input_calib

Output: JSON with {status, action, message, ...} for machine parsing.
"""

import argparse
import json
import random
import sys
import time

from patchright.sync_api import sync_playwright, Page

from tuqueque.a11y import resolve_target, snapshot_interactives
from tuqueque.config import get_cdp_url
from tuqueque.human_behavior import HumanBehavior
from tuqueque.input_os import calibrate, click_locator


def _get_page() -> tuple:
    """Connect to CDP and return (playwright, browser, page)."""
    cdp_url = get_cdp_url()
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(cdp_url)

    # Find the first available page across all contexts
    page = None
    for ctx in browser.contexts:
        if ctx.pages:
            page = ctx.pages[-1]
            break

    if not page:
        page = browser.new_page()

    return pw, browser, page


def cmd_viewport(page: Page, args) -> dict:
    """Get current viewport and element position info."""
    vp = page.evaluate("""() => ({
        scrollX: window.scrollX,
        scrollY: window.scrollY,
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
        outerWidth: window.outerWidth,
        outerHeight: window.outerHeight,
        documentHeight: document.documentElement.scrollHeight,
        url: window.location.href,
        title: document.title,
    })""")
    return {"status": "ok", "action": "viewport", **vp}


def cmd_click(page: Page, args) -> dict:
    """Human click: viewport check → scroll → Bezier hover → click."""
    hb = HumanBehavior(page)
    locator = page.locator(args.selector)
    hb.human_click(locator)
    return {
        "status": "ok",
        "action": "click",
        "selector": args.selector,
        "message": f"Clicked {args.selector}",
    }


def cmd_scroll(page: Page, args) -> dict:
    """Human scroll with inertia, multi-segment."""
    hb = HumanBehavior(page)
    hb.human_scroll(times=args.times, direction=args.direction)
    return {
        "status": "ok",
        "action": "scroll",
        "times": args.times,
        "direction": args.direction,
    }


def cmd_hover(page: Page, args) -> dict:
    """Hover over visible links/buttons in viewport."""
    hb = HumanBehavior(page)
    hb.hover_over_links(count=args.count)
    return {"status": "ok", "action": "hover", "count": args.count}


def cmd_read(page: Page, args) -> dict:
    """Simulate reading: scroll, hover, find-on-page."""
    hb = HumanBehavior(page)
    hb.read_page(sections=args.sections)
    return {"status": "ok", "action": "read", "sections": args.sections}


def cmd_warm_up(page: Page, args) -> dict:
    """Warm-up browser on neutral sites."""
    hb = HumanBehavior(page)
    hb.warm_up()
    return {"status": "ok", "action": "warm_up"}


def cmd_fill(page: Page, args) -> dict:
    """Fill input with human-like typing."""
    hb = HumanBehavior(page)
    locator = page.locator(args.selector)
    hb.human_type(locator, args.text)
    return {
        "status": "ok",
        "action": "fill",
        "selector": args.selector,
    }


def cmd_navigate(page: Page, args) -> dict:
    """Navigate to URL with human-like sequence."""
    hb = HumanBehavior(page)
    hb.human_navigate(url=args.url, warm_up=args.warm_up)
    return {
        "status": "ok",
        "action": "navigate",
        "url": args.url,
        "warm_up": args.warm_up,
    }


def cmd_type_text(page: Page, args) -> dict:
    """Type text (simpler than fill, just keyboard type)."""
    locator = page.locator(args.selector)
    locator.click()
    time.sleep(random.uniform(0.2, 0.5))
    page.keyboard.type(args.text, delay=random.randint(40, 100))
    return {
        "status": "ok",
        "action": "type_text",
        "selector": args.selector,
    }


def _get_prop(node, prop_name):
    """Extract a property value from CDP AX node's properties array."""
    for p in node.get("properties", []):
        if p.get("name") == prop_name:
            v = p.get("value", {})
            return v.get("value", v)
    return None


def _build_tree(nodes):
    """Convert flat CDP AX node list into a rooted tree."""
    by_id = {}
    child_ids_set = set()

    for n in nodes:
        by_id[n["nodeId"]] = n
        for cid in n.get("childIds", []):
            child_ids_set.add(cid)

    # Find roots: nodes not referenced as a child
    roots = [n for nid, n in by_id.items() if nid not in child_ids_set]
    return roots, by_id


def _format_tree(node_id, by_id, uid_counter, indent=0):
    """Recursively format a CDP AX tree node."""
    node = by_id.get(node_id)
    if not node:
        return ""

    role = node.get("role", {}).get("value", "?")
    name = node.get("name", {}).get("value", "")

    # Skip low-level text nodes (info is in parent name)
    if role in ("StaticText", "InlineTextBox"):
        return ""

    uid = uid_counter[0]
    uid_counter[0] += 1

    line = f"{'  ' * indent}uid={uid} {role}"
    if name:
        line += f' "{name}"'

    url = _get_prop(node, "url")
    if url:
        line += f' url="{url}"'

    value = _get_prop(node, "value")
    if value:
        line += f' value="{value}"'

    level = _get_prop(node, "level")
    if level:
        line += f" level={level}"

    for attr in ("checked", "expanded", "pressed", "selected"):
        val = _get_prop(node, attr)
        if val:
            line += f" {attr}={val}"

    parts = [line]
    for cid in node.get("childIds", []):
        child_text = _format_tree(cid, by_id, uid_counter, indent + 1)
        if child_text:
            parts.append(child_text)

    return "\n".join(parts)


def cmd_snapshot(page: Page, args) -> dict:
    """Get accessibility tree snapshot via CDP."""
    session = page.context.new_cdp_session(page)
    tree = session.send("Accessibility.getFullAXTree")
    roots, by_id = _build_tree(tree.get("nodes", []))
    uid_counter = [0]
    lines = []
    for root in roots:
        text = _format_tree(root["nodeId"], by_id, uid_counter, 0)
        if text:
            lines.append(text)
    text = "\n".join(lines)
    result = {"status": "ok", "action": "snapshot", "text": text}
    if getattr(args, "filePath", None):
        with open(args.filePath, "w") as f:
            f.write(text)
        result["filePath"] = args.filePath
    return result


def cmd_eval(page: Page, args) -> dict:
    """Evaluate JavaScript and return result."""
    try:
        value = page.evaluate(args.code)
        return {"status": "ok", "action": "eval", "code": args.code, "result": value}
    except Exception as e:
        return {"status": "error", "action": "eval", "code": args.code, "error": str(e)}


def cmd_screenshot(page: Page, args) -> dict:
    """Take a screenshot of the current viewport."""
    path = getattr(args, "filePath", None) or "/tmp/human_cdp_screenshot.png"
    page.screenshot(path=path, full_page=getattr(args, "full_page", False))
    return {"status": "ok", "action": "screenshot", "filePath": path}


def cmd_list_pages(page: Page, args) -> dict:
    """List all open pages across contexts."""
    pages_info = []
    for ctx in page.context.browser.contexts:
        for p in ctx.pages:
            pages_info.append({
                "url": p.url,
                "title": p.title(),
            })
    return {"status": "ok", "action": "list_pages", "pages": pages_info}


def cmd_set_input_files(page: Page, args) -> dict:
    """Upload file to a file input element."""
    locator = page.locator(args.selector)
    locator.set_input_files(args.file_path, timeout=5000)
    page.evaluate("""(sel) => {
        const el = document.querySelector(sel);
        if (el) {
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        }
    }""", args.selector)
    return {
        "status": "ok",
        "action": "set_input_files",
        "selector": args.selector,
        "file_path": args.file_path,
    }


def cmd_new_page(page: Page, args) -> dict:
    """Open a new page and optionally navigate."""
    ctx = None
    for c in page.context.browser.contexts:
        ctx = c
        break
    new_p = ctx.new_page()
    if args.url:
        new_p.goto(args.url, wait_until="domcontentloaded")
    return {
        "status": "ok",
        "action": "new_page",
        "url": args.url,
    }


def cmd_a11y(page: Page, args) -> dict:
    """Numbered snapshot of interactive elements for AI targeting."""
    items = snapshot_interactives(page, limit=args.limit)
    visible = sum(1 for it in items if it["visible"])
    return {
        "status": "ok",
        "action": "a11y",
        "count": len(items),
        "visible": visible,
        "items": items,
    }


def _resolve_index(page: Page, index: int):
    target = resolve_target(page, index)
    if not target:
        raise ValueError(f"Index {index} not resolvable (element gone or hidden)")
    return target


def cmd_a11y_click(page: Page, args) -> dict:
    """Human CDP click on snapshot index (recommended path)."""
    target = _resolve_index(page, args.index)
    hb = HumanBehavior(page)
    hb.human_click(target["locator"])
    return {
        "status": "ok",
        "action": "a11y_click",
        "index": args.index,
        "box": target["box"],
        "message": f"Clicked index {args.index}",
    }


def cmd_os_click(page: Page, args) -> dict:
    """OS-level (PyAutoGUI) click on snapshot index (hard-target fallback)."""
    target = _resolve_index(page, args.index)
    click_locator(page, target["locator"])
    return {
        "status": "ok",
        "action": "os_click",
        "index": args.index,
        "box": target["box"],
        "message": f"OS-clicked index {args.index}",
    }


def cmd_input_calib(page: Page, args) -> dict:
    """Print the viewport->screen offset for OS-level input calibration."""
    off = calibrate(page)
    return {
        "status": "ok",
        "action": "input_calib",
        "offset": off,
        "hint": "screen = viewport + offset (re-calibrate before each batch of clicks)",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Human Behavior CDP CLI — human-like browser interactions",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # viewport
    sub.add_parser("viewport", help="Get current viewport state")

    # click
    p_click = sub.add_parser("click", help="Human click with viewport check + scroll")
    p_click.add_argument("selector", help="CSS selector for element")

    # scroll
    p_scroll = sub.add_parser("scroll", help="Human scroll with inertia")
    p_scroll.add_argument("--times", type=int, default=3, help="Scroll segments")
    p_scroll.add_argument("--direction", choices=["down", "up"], default="down")

    # hover
    p_hover = sub.add_parser("hover", help="Hover over visible links")
    p_hover.add_argument("--count", type=int, default=4, help="Elements to hover")

    # read
    p_read = sub.add_parser("read", help="Simulate reading page")
    p_read.add_argument("--sections", type=int, default=3, help="Reading sections")

    # warm_up
    sub.add_parser("warm_up", help="Warm-up on neutral sites")

    # fill
    p_fill = sub.add_parser("fill", help="Human typing into input")
    p_fill.add_argument("selector", help="CSS selector")
    p_fill.add_argument("text", help="Text to type")

    # navigate
    p_nav = sub.add_parser("navigate", help="Navigate with human sequence")
    p_nav.add_argument("url", help="Target URL")
    p_nav.add_argument("--warm-up", action="store_true", help="Warm-up first")

    # type_text
    p_type = sub.add_parser("type_text", help="Quick keyboard type")
    p_type.add_argument("selector", help="CSS selector")
    p_type.add_argument("text", help="Text to type")

    # snapshot
    p_snap = sub.add_parser("snapshot", help="Get visible page text")
    p_snap.add_argument("--filePath", "-f", help="Save to file")

    # eval
    p_eval = sub.add_parser("eval", help="Evaluate JavaScript")
    p_eval.add_argument("code", help="JS code to evaluate")

    # screenshot
    p_shot = sub.add_parser("screenshot", help="Take screenshot")
    p_shot.add_argument("--filePath", "-f", help="Output path")
    p_shot.add_argument("--full-page", action="store_true", help="Full page capture")

    # list_pages
    sub.add_parser("list_pages", help="List open tabs")

    # set_input_files
    p_file = sub.add_parser("set_input_files", help="Upload file to input")
    p_file.add_argument("selector", help="CSS selector for file input")
    p_file.add_argument("file_path", help="Absolute path to file on disk")

    # new_page
    p_new = sub.add_parser("new_page", help="Open a new page")
    p_new.add_argument("url", nargs="?", default="about:blank", help="URL to open")

    # a11y
    p_a11y = sub.add_parser("a11y", help="Numbered interactive-element snapshot")
    p_a11y.add_argument("--limit", type=int, default=300, help="Max entries")

    # a11y_click
    p_ac = sub.add_parser("a11y_click", help="Human CDP click on snapshot index")
    p_ac.add_argument("index", type=int, help="Snapshot index to click")

    # os_click
    p_oc = sub.add_parser("os_click", help="OS-level (PyAutoGUI) click on snapshot index")
    p_oc.add_argument("index", type=int, help="Snapshot index to click")

    # input_calib
    sub.add_parser("input_calib", help="Print viewport->screen offset")

    parsed = parser.parse_args()

    pw = None
    try:
        pw, browser, page = _get_page()

        cmds = {
            "viewport": cmd_viewport,
            "click": cmd_click,
            "scroll": cmd_scroll,
            "hover": cmd_hover,
            "read": cmd_read,
            "warm_up": cmd_warm_up,
            "fill": cmd_fill,
            "navigate": cmd_navigate,
            "type_text": cmd_type_text,
            "snapshot": cmd_snapshot,
            "eval": cmd_eval,
            "screenshot": cmd_screenshot,
            "list_pages": cmd_list_pages,
            "new_page": cmd_new_page,
            "set_input_files": cmd_set_input_files,
            "a11y": cmd_a11y,
            "a11y_click": cmd_a11y_click,
            "os_click": cmd_os_click,
            "input_calib": cmd_input_calib,
        }

        result = cmds[parsed.command](page, parsed)
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(json.dumps({"status": "error", "action": parsed.command, "error": str(e)}, indent=2))
        sys.exit(1)
    finally:
        if pw:
            pw.stop()


if __name__ == "__main__":
    main()