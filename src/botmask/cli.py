#!/usr/bin/env python3
"""
botmask CLI — natural browser interactions via CDP.

Connects to the shared Brave CDP instance for all browser interactions.
Interaction commands (click, scroll, fill, hover, read, warm_up, navigate)
use the Behavior class. Inspection commands (snapshot, eval,
list_pages, viewport) use direct CDP access. AI targeting commands
(a11y, a11y_click, os_click, input_calib) use the interaction-model modules.

Usage:
    python -m botmask.cli [--tab URL_SUBSTR] COMMAND ...

    python -m botmask.cli click       "h2#Enlaces_externos"
    python -m botmask.cli scroll      --times 3 --direction down
    python -m botmask.cli scroll      --container          (inner scroller)
    python -m botmask.cli hover       --count 4
    python -m botmask.cli read        --sections 3
    python -m botmask.cli warm_up
    python -m botmask.cli viewport
    python -m botmask.cli fill        "#input-id" "text to type"
    python -m botmask.cli fill        "#input-id" "text" --clear
    python -m botmask.cli fill_clear  "#input-id" "replacement text"
    python -m botmask.cli navigate    "https://example.com"
    python -m botmask.cli type_text   "#search" "python developer"
    python -m botmask.cli snapshot    [--filePath /tmp/snapshot.txt]
    python -m botmask.cli eval        "document.title"
    python -m botmask.cli list_pages
    python -m botmask.cli new_page    "https://example.com"
    python -m botmask.cli screenshot  [--filePath /tmp/shot.png]
    python -m botmask.cli check                            (overlays/modals)
    python -m botmask.cli doctor                           (CDP health)
    python -m botmask.cli stealth_audit                    (detection probes)
    python -m botmask.cli a11y        [--limit 300]
    python -m botmask.cli a11y_click 42
    python -m botmask.cli os_click    42
    python -m botmask.cli input_calib

Output: JSON with {status, action, message, ...} for machine parsing.
"""

import argparse
import json
import random
import sys
import time

from patchright.sync_api import sync_playwright, Page

from botmask.a11y import resolve_target, snapshot_interactives
from botmask.config import get_cdp_url
from botmask.behavior import Behavior
from botmask.input_os import calibrate, click_locator


def _get_page(tab_filter: str | None = None) -> tuple:
    """Connect to CDP and return (playwright, browser, page).

    When ``tab_filter`` is given, pick the first open tab whose URL contains
    it (case-insensitive). Without it, use the most recently opened tab.
    """
    cdp_url = get_cdp_url()
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(cdp_url)

    page = None
    if tab_filter:
        needle = tab_filter.lower()
        for ctx in browser.contexts:
            for p in ctx.pages:
                if needle in p.url.lower():
                    page = p
                    break
            if page:
                break
        if not page:
            available = [p.url for c in browser.contexts for p in c.pages]
            raise ValueError(
                f"No tab matching '{tab_filter}'. Open tabs: {available}"
            )
    else:
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
    """Natural click: viewport check → scroll → Bezier hover → click."""
    hb = Behavior(page)
    locator = page.locator(args.selector)
    hb.click(locator)
    return {
        "status": "ok",
        "action": "click",
        "selector": args.selector,
        "message": f"Clicked {args.selector}",
    }


def cmd_scroll(page: Page, args) -> dict:
    """Natural scroll with inertia, multi-segment."""
    hb = Behavior(page)
    hb.scroll(times=args.times, direction=args.direction)
    return {
        "status": "ok",
        "action": "scroll",
        "times": args.times,
        "direction": args.direction,
    }


def cmd_hover(page: Page, args) -> dict:
    """Hover over visible links/buttons in viewport."""
    hb = Behavior(page)
    hb.hover_over_links(count=args.count)
    return {"status": "ok", "action": "hover", "count": args.count}


def cmd_read(page: Page, args) -> dict:
    """Simulate reading: scroll, hover, find-on-page."""
    hb = Behavior(page)
    hb.read_page(sections=args.sections)
    return {"status": "ok", "action": "read", "sections": args.sections}


def cmd_warm_up(page: Page, args) -> dict:
    """Warm-up browser on neutral sites."""
    hb = Behavior(page)
    hb.warm_up()
    return {"status": "ok", "action": "warm_up"}


def cmd_fill(page: Page, args) -> dict:
    """Fill input with natural typing."""
    hb = Behavior(page)
    locator = page.locator(args.selector)
    if getattr(args, "clear", False):
        # Select-all + delete before typing (fill appends, never clears)
        locator.click()
        time.sleep(random.uniform(0.15, 0.35))
        page.keyboard.press("Control+a")
        time.sleep(random.uniform(0.1, 0.2))
        page.keyboard.press("Delete")
        time.sleep(random.uniform(0.2, 0.4))
    hb.type_text(locator, args.text)
    return {
        "status": "ok",
        "action": "fill",
        "selector": args.selector,
        "cleared": getattr(args, "clear", False),
    }


def cmd_fill_clear(page: Page, args) -> dict:
    """Clear the field (select-all + delete) then type with natural cadence."""
    hb = Behavior(page)
    locator = page.locator(args.selector)
    locator.click()
    time.sleep(random.uniform(0.2, 0.4))
    page.keyboard.press("Control+a")
    time.sleep(random.uniform(0.1, 0.25))
    page.keyboard.press("Delete")
    time.sleep(random.uniform(0.2, 0.4))
    hb.type_text(locator, args.text)
    return {
        "status": "ok",
        "action": "fill_clear",
        "selector": args.selector,
    }


def cmd_scroll(page: Page, args) -> dict:
    """Natural scroll with inertia, multi-segment.

    With ``--container``, auto-detect the inner scrollable element (e.g.
    LinkedIn's results panel) and wheel-scroll it instead of the window.
    """
    hb = Behavior(page)
    if getattr(args, "container", False):
        dy = 600 if args.direction == "down" else -600
        for _ in range(args.times):
            moved = page.evaluate("""(dy) => {
                const els = Array.from(document.querySelectorAll('div, ul, section'));
                const scrollers = els.filter(el => {
                    const st = getComputedStyle(el);
                    return (st.overflowY === 'auto' || st.overflowY === 'scroll')
                        && el.scrollHeight > el.clientHeight + 100
                        && el.clientHeight > 200;
                });
                if (!scrollers.length) return false;
                // Pick the tallest inner scroller (most likely the results panel)
                scrollers.sort((a, b) => b.clientHeight - a.clientHeight);
                const el = scrollers[0];
                const before = el.scrollTop;
                const r = el.getBoundingClientRect();
                // Natural wheel over the container center
                const cx = r.left + r.width / 2;
                const cy = r.top + Math.min(r.height / 2, window.innerHeight / 2);
                return {before, canScroll: el.scrollHeight - el.clientHeight - el.scrollTop > 2, cx, cy};
            }""", dy)
            if not moved:
                return {"status": "ok", "action": "scroll", "container": True,
                        "message": "no inner scrollable container found"}
            page.mouse.move(moved["cx"], moved["cy"])
            page.mouse.wheel(0, dy)
            time.sleep(random.uniform(0.4, 0.9))
        return {
            "status": "ok",
            "action": "scroll",
            "container": True,
            "times": args.times,
            "direction": args.direction,
        }
    hb.scroll(times=args.times, direction=args.direction)
    return {
        "status": "ok",
        "action": "scroll",
        "times": args.times,
        "direction": args.direction,
    }


def cmd_navigate(page: Page, args) -> dict:
    """Navigate to URL with natural sequence."""
    hb = Behavior(page)
    hb.navigate(url=args.url, warm_up=args.warm_up)
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
    path = getattr(args, "filePath", None) or "/tmp/botmask_screenshot.png"
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
    """Natural CDP click on snapshot index (recommended path)."""
    target = _resolve_index(page, args.index)
    hb = Behavior(page)
    hb.click(target["locator"])
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


_OVERLAY_PROBE_JS = """() => {
    const findings = [];
    const visible = (el) => {
        const st = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        return st.display !== 'none' && st.visibility !== 'hidden'
            && r.width > 10 && r.height > 10;
    };
    // SweetAlert2 modals (block submits silently)
    document.querySelectorAll('.swal2-container').forEach(el => {
        if (visible(el)) {
            const title = el.querySelector('.swal2-title, h2');
            findings.push({
                kind: 'sweetalert2',
                text: title ? title.textContent.trim().slice(0, 200) : '',
                selector: '.swal2-container',
            });
        }
    });
    // Generic dialogs
    document.querySelectorAll('[role="dialog"], .modal.show, .modal[style*="block"]')
        .forEach(el => {
            if (visible(el)) {
                const t = (el.getAttribute('aria-label') || el.textContent || '')
                    .trim().replace(/\\s+/g, ' ').slice(0, 200);
                if (t) {
                    findings.push({
                        kind: 'dialog', text: t,
                        selector: '[role="dialog"], .modal.show',
                    });
                }
            }
        });
    // Cookie / consent banners
    document.querySelectorAll(
        '[class*="cookie" i], [id*="cookie" i], [class*="consent" i], [id*="onetrust-banner"], .iubenda-cs-banner'
    ).forEach(el => {
        if (visible(el)) {
            findings.push({
                kind: 'cookie-banner',
                text: (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 150),
                selector: el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''),
            });
        }
    });
    // Captcha challenges (must be solved by the operator)
    document.querySelectorAll('iframe[src*="recaptcha"], iframe[title*="recaptcha" i], .g-recaptcha, .h-captcha')
        .forEach(el => {
            findings.push({
                kind: 'captcha',
                text: el.getAttribute('src') || 'captcha widget',
                selector: 'iframe[src*="recaptcha"]',
            });
        });
    return findings;
}"""


def cmd_check(page: Page, args) -> dict:
    """Detect blocking overlays: modals, cookie banners, captchas.

    Run before clicking submit — silent SweetAlert2 confirmations were the
    root cause of a lost application in the field.
    """
    findings = page.evaluate(_OVERLAY_PROBE_JS)
    # Deduplicate by (kind, text)
    seen = set()
    unique = []
    for f in findings:
        key = (f["kind"], f["text"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return {
        "status": "ok",
        "action": "check",
        "url": page.url,
        "blocking": len(unique),
        "findings": unique,
    }


_STEALTH_PROBES_JS = """() => {
    const results = [];
    const add = (name, passed, detail) => results.push({probe: name, pass: !!passed, detail: detail || ''});
    add('navigator.webdriver', navigator.webdriver === false || navigator.webdriver === undefined,
        'value=' + String(navigator.webdriver));
    add('user-agent', !/HeadlessChrome/i.test(navigator.userAgent), navigator.userAgent.slice(0, 120));
    add('navigator.plugins', navigator.plugins.length > 0, 'count=' + navigator.plugins.length);
    add('navigator.mimeTypes', navigator.mimeTypes.length > 0, 'count=' + navigator.mimeTypes.length);
    add('navigator.languages', Array.isArray(navigator.languages) && navigator.languages.length > 0,
        JSON.stringify(navigator.languages));
    const hasChrome = typeof window.chrome === 'object' && window.chrome !== null;
    add('window.chrome', hasChrome);
    add('chrome.runtime', hasChrome && typeof chrome.runtime !== 'undefined');
    // WebGL vendor / renderer (SwiftShader = software rendering leak)
    let glOk = false, glDetail = 'no-webgl';
    try {
        const c = document.createElement('canvas');
        const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
        if (gl) {
            const ext = gl.getExtension('WEBGL_debug_renderer_info');
            const vendor = ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR);
            const renderer = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
            glOk = !/SwiftShader|llvmpipe|Software/i.test(String(renderer));
            glDetail = vendor + ' / ' + renderer;
        }
    } catch (e) { glDetail = 'error: ' + e.message; }
    add('webgl.renderer', glOk, glDetail);
    // cdc_ variables (chromedriver artifact)
    const cdc = Object.keys(document).filter(k => /^cdc_|^\\$cdc_/.test(k));
    add('no-cdc-vars', cdc.length === 0, cdc.join(','));
    let consoleOk = false;
    try { consoleOk = /native code/i.test(Function.prototype.toString.call(console.debug)); }
    catch (e) {}
    add('console.debug-native', consoleOk);
    add('notification-api', typeof Notification !== 'undefined');
    add('hardware-concurrency', navigator.hardwareConcurrency > 0,
        'cores=' + navigator.hardwareConcurrency);
    add('device-pixel-ratio', window.devicePixelRatio > 0,
        'dpr=' + window.devicePixelRatio);
    return results;
}"""


def cmd_stealth_audit(page: Page, args) -> dict:
    """Run anti-detection probes against the current browser page."""
    results = page.evaluate(_STEALTH_PROBES_JS)
    # Async permission probe: headless Chrome leaks 'prompt' here where a
    # real Chrome reports 'denied'/'granted' — classic headless tell.
    try:
        perm = page.evaluate(
            """async () => {
                try {
                    const st = await navigator.permissions.query({name: 'notifications'});
                    return st.state;
                } catch (e) { return 'error: ' + e.message; }
            }"""
        )
        results.append({
            "probe": "permissions.notifications",
            "pass": perm in ("granted", "denied"),
            "detail": perm,
        })
    except Exception as e:  # noqa: BLE001
        results.append({"probe": "permissions.notifications", "pass": False,
                        "detail": str(e)})

    leaks = [r for r in results if not r["pass"]]
    return {
        "status": "ok",
        "action": "stealth_audit",
        "url": page.url,
        "passed": len(results) - len(leaks),
        "total": len(results),
        "leaks": leaks,
        "results": results,
    }


def cmd_doctor(page: Page, args) -> dict:
    """CDP health check: connectivity, session responsiveness, tab inventory."""
    start = time.time()
    pages_info = []
    for ctx in page.context.browser.contexts:
        for p in ctx.pages:
            try:
                title = p.title()
                pages_info.append({"url": p.url, "title": title, "responsive": True})
            except Exception as e:  # noqa: BLE001
                pages_info.append({"url": p.url, "title": None, "responsive": False,
                                   "error": str(e)[:120]})
    latency_ms = round((time.time() - start) * 1000, 1)
    # Round-trip JS probe
    js_ok = True
    try:
        page.evaluate("1 + 1")
    except Exception:  # noqa: BLE001
        js_ok = False
    healthy = js_ok and all(p["responsive"] for p in pages_info)
    result = {
        "status": "ok" if healthy else "degraded",
        "action": "doctor",
        "cdp_url": get_cdp_url(),
        "latency_ms": latency_ms,
        "js_roundtrip": js_ok,
        "tabs": pages_info,
        "healthy": healthy,
    }
    if not healthy:
        result["hint"] = ("CDP session appears corrupted. Restart the browser "
                          "container/service; profile persists in browser_data/.")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="botmask CLI — natural browser interactions",
    )
    parser.add_argument(
        "--tab", default=None, metavar="SUBSTR",
        help="Target the first open tab whose URL contains SUBSTR "
             "(default: most recently opened tab)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # viewport
    sub.add_parser("viewport", help="Get current viewport state")

    # click
    p_click = sub.add_parser("click", help="Natural click with viewport check + scroll")
    p_click.add_argument("selector", help="CSS selector for element")

    # scroll
    p_scroll = sub.add_parser("scroll", help="Natural scroll with inertia")
    p_scroll.add_argument("--times", type=int, default=3, help="Scroll segments")
    p_scroll.add_argument("--direction", choices=["down", "up"], default="down")
    p_scroll.add_argument("--container", action="store_true",
                          help="Auto-detect inner scrollable element and wheel it")

    # hover
    p_hover = sub.add_parser("hover", help="Hover over visible links")
    p_hover.add_argument("--count", type=int, default=4, help="Elements to hover")

    # read
    p_read = sub.add_parser("read", help="Simulate reading page")
    p_read.add_argument("--sections", type=int, default=3, help="Reading sections")

    # warm_up
    sub.add_parser("warm_up", help="Warm-up on neutral sites")

    # fill
    p_fill = sub.add_parser("fill", help="Natural typing into input")
    p_fill.add_argument("selector", help="CSS selector")
    p_fill.add_argument("text", help="Text to type")
    p_fill.add_argument("--clear", action="store_true",
                        help="Select-all + delete before typing")

    # fill_clear
    p_fc = sub.add_parser("fill_clear", help="Clear field then type (select-all + delete)")
    p_fc.add_argument("selector", help="CSS selector")
    p_fc.add_argument("text", help="Text to type")

    # navigate
    p_nav = sub.add_parser("navigate", help="Navigate with natural sequence")
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
    p_ac = sub.add_parser("a11y_click", help="Natural CDP click on snapshot index")
    p_ac.add_argument("index", type=int, help="Snapshot index to click")

    # os_click
    p_oc = sub.add_parser("os_click", help="OS-level (PyAutoGUI) click on snapshot index")
    p_oc.add_argument("index", type=int, help="Snapshot index to click")

    # input_calib
    sub.add_parser("input_calib", help="Print viewport->screen offset")

    # check
    sub.add_parser("check", help="Detect blocking overlays (modals, cookie banners, captchas)")

    # doctor
    sub.add_parser("doctor", help="CDP health check: latency, tab responsiveness")

    # stealth_audit
    sub.add_parser("stealth_audit", help="Run anti-detection probes against current page")

    parsed = parser.parse_args()

    pw = None
    try:
        pw, browser, page = _get_page(parsed.tab)

        cmds = {
            "viewport": cmd_viewport,
            "click": cmd_click,
            "scroll": cmd_scroll,
            "hover": cmd_hover,
            "read": cmd_read,
            "warm_up": cmd_warm_up,
            "fill": cmd_fill,
            "fill_clear": cmd_fill_clear,
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
            "check": cmd_check,
            "doctor": cmd_doctor,
            "stealth_audit": cmd_stealth_audit,
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