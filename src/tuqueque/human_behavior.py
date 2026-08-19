#!/usr/bin/env python3
"""
Human Behavior Simulation Module - tuqueque

Realistic human behavior simulation for browser automation:
- Bezier-curve mouse movement
- Natural scrolling with inertia and acceleration
- Event-based delays (wait for visibility, not fixed sleeps)
- Reading simulation with per-section pauses
- Browser warm-up sequence before target sites
- Auth barrier detection for login/challenge pages
- Typing simulation with per-character variance

Usage:
    from tuqueque.human_behavior import HumanBehavior

    hb = HumanBehavior(page)
    hb.warm_up()
    hb.human_scroll(times=3)
    hb.move_mouse_to(element)
    hb.read_page()
    hb.detect_auth_barrier()
"""

import math
import random
import time
import sys
from typing import Optional, List, Tuple

from patchright.sync_api import Page, Locator


WARM_UP_SITES = [
    {"url": "https://www.google.com", "wait_range": (2.0, 4.0), "interact": True},
    {"url": "https://es.wikipedia.org", "wait_range": (3.0, 5.0), "interact": True},
    {"url": "https://github.com", "wait_range": (2.0, 3.5), "interact": False},
    {"url": "https://news.ycombinator.com", "wait_range": (3.0, 5.0), "interact": True},
    {"url": "https://stackoverflow.com", "wait_range": (2.0, 4.0), "interact": True},
    {"url": "https://developer.mozilla.org/es/", "wait_range": (2.0, 4.0), "interact": True},
    {"url": "https://www.reddit.com/r/programming/", "wait_range": (3.0, 5.0), "interact": True},
    {"url": "https://www.google.com/search?q=python+backend+developer+2026", "wait_range": (3.0, 5.0), "interact": False},
    {"url": "https://www.google.com/search?q=typescript+remote+jobs+latin+america", "wait_range": (3.0, 5.0), "interact": False},
    {"url": "https://www.google.com/search?q=laboral+lATAM+2026", "wait_range": (3.0, 5.0), "interact": False},
    {"url": "https://www.lipsum.com", "wait_range": (2.0, 3.0), "interact": False},
    {"url": "https://http.cat", "wait_range": (1.0, 2.0), "interact": True},
]

SESSION_PACES = {"fast": 0.7, "medium": 1.0, "slow": 1.5}

AUTH_BARRIER_PATTERNS = [
    "/login",
    "/authwall",
    "/checkpoint",
    "/challenge",
    "/signin",
    "/accounts/login",
    "/uas/login",
    "/secure",
    "/auth/login",
]

AUTH_BARRIER_TITLES = [
    "iniciar sesion",
    "log in",
    "sign in",
    "inicia sesion",
    "acceder",
    "verificacion",
    "checking your browser",
    "just a moment",
    "un momento",
    "cloudflare",
    "attention required",
]


def _bezier_point(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    return ((1 - t) ** 3 * p0 +
            3 * (1 - t) ** 2 * t * p1 +
            3 * (1 - t) * t ** 2 * p2 +
            t ** 3 * p3)


def fitts(distance: float, width: float) -> float:
    """Fitts's Law: expected movement time (MT) for a given distance/target width."""
    a, b = 0, 2 / 3
    return a + b * math.log2(distance / width + 1)


def fitts_steps(length: float, width: float) -> int:
    """Step count for a movement of `length` px to a target of `width` px.

    Longer distances + smaller targets → more steps → slower approach.
    """
    mt = fitts(length, width)
    return max(2, math.ceil((math.log2(mt + 1) + random.random() * 25) * 3))


def overshoot(point: Tuple[float, float], radius: float = 120) -> Tuple[float, float]:
    """Point slightly past `point` in a random direction (miss-and-re-adjust)."""
    x, y = point
    angle = random.uniform(-math.pi, math.pi)
    return (x + radius * math.cos(angle), y + radius * math.sin(angle))


def should_overshoot(start: Tuple[float, float], end: Tuple[float, float], threshold: float = 500) -> bool:
    """Whether a long movement warrants an overshoot-and-correct path."""
    return math.hypot(end[0] - start[0], end[1] - start[1]) > threshold


def _generate_bezier_path(
    start: Tuple[float, float],
    end: Tuple[float, float],
    steps: int = 50,
    spread: Optional[float] = None,
) -> Tuple[List[Tuple[float, float]], float]:
    """Generate a cubic Bezier path from start to end.

    Control-point spread is clamped to 2–200 px (matches ghost-cursor) so long
    movements don't curve unrealistically wide.

    Returns:
        (path points, curve length in px)
    """
    sx, sy = start
    ex, ey = end

    dist = math.hypot(ex - sx, ey - sy)
    if dist < 1:
        return [(sx, sy)], 0.0

    if spread is None:
        spread = max(2, min(200, dist))

    angle = math.atan2(ey - sy, ex - sx)

    perp_angle = angle + math.pi / 2
    if random.random() < 0.5:
        perp_angle = angle - math.pi / 2

    cp1x = sx + (ex - sx) * random.uniform(0.2, 0.4) + math.cos(perp_angle) * spread * random.uniform(0.3, 1.0)
    cp1y = sy + (ey - sy) * random.uniform(0.2, 0.4) + math.sin(perp_angle) * spread * random.uniform(0.3, 1.0)

    cp2x = sx + (ex - sx) * random.uniform(0.6, 0.8) + math.cos(perp_angle) * spread * random.uniform(0.1, 0.6)
    cp2y = sy + (ey - sy) * random.uniform(0.6, 0.8) + math.sin(perp_angle) * spread * random.uniform(0.1, 0.6)

    path = []
    length = 0.0
    prev = (sx, sy)
    for i in range(steps + 1):
        t = i / steps
        x = _bezier_point(t, sx, cp1x, cp2x, ex)
        y = _bezier_point(t, sy, cp1y, cp2y, ey)
        path.append((x, y))
        if i > 0:
            length += math.hypot(x - prev[0], y - prev[1])
        prev = (x, y)

    return path, length


class HumanBehavior:
    """
    Realistic human behavior simulation for browser automation.

    Provides natural mouse movement, scrolling, delays, and
    page interaction patterns that mimic real user behavior
    to avoid anti-bot detection systems.
    """

    def __init__(self, page: Page, viewport: Optional[dict] = None):
        self.page = page
        self.viewport = viewport or {"width": 1920, "height": 1080}
        self._mouse_pos: Tuple[float, float] = (
            random.uniform(100, self.viewport["width"] - 100),
            random.uniform(100, self.viewport["height"] - 100),
        )
        pace_key = random.choices(
            ["fast", "medium", "slow"],
            weights=[0.25, 0.50, 0.25],
        )[0]
        self.pace_multiplier = SESSION_PACES[pace_key]

    def _get_viewport_info(self) -> dict:
        """Get current scroll position and viewport dimensions."""
        return self.page.evaluate("""() => ({
            scrollX: window.scrollX,
            scrollY: window.scrollY,
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
        })""")

    def _is_in_viewport(self, box: dict, viewport_info: dict) -> bool:
        """Check if bounding box is fully visible within the viewport."""
        return (
            box["x"] >= 0
            and box["y"] >= 0
            and box["x"] + box["width"] >= viewport_info["scrollX"]
            and box["x"] < viewport_info["scrollX"] + viewport_info["innerWidth"]
            and box["y"] + box["height"] >= viewport_info["scrollY"]
            and box["y"] < viewport_info["scrollY"] + viewport_info["innerHeight"]
        )

    def _ensure_in_viewport(self, locator: Locator) -> Optional[dict]:
        """
        Scroll the element into view with human-like scrolling if needed.

        Gets the element's bounding box and current viewport state.
        If the element is not fully visible, scrolls smoothly to it
        using natural scroll behavior instead of instant JS scrollIntoView.

        Args:
            locator: Element to check and scroll to

        Returns:
            Bounding box dict or None if element not found
        """
        try:
            box = locator.bounding_box(timeout=3000)
            if not box:
                return None
        except Exception:
            return None

        viewport_info = self._get_viewport_info()

        if self._is_in_viewport(box, viewport_info):
            return box

        target_y = box["y"] + box["height"] / 2
        current_y = viewport_info["scrollY"]
        delta = target_y - current_y - viewport_info["innerHeight"] / 2

        if abs(delta) < 50:
            return box

        direction = "down" if delta > 0 else "up"
        segments = max(1, min(20, int(abs(delta) / 400)))
        self.human_scroll(times=segments, direction=direction)
        self.human_delay(0.3, 0.8)

        # Re-check position after scroll
        try:
            box = locator.bounding_box(timeout=2000)
        except Exception:
            pass

        return box

    def human_delay(
        self,
        min_sec: float = 1.0,
        max_sec: float = 3.0,
        distribution: str = "lognormal",
    ):
        """
        Wait with a natural distribution, not uniform random.

        Args:
            min_sec: Minimum delay
            max_sec: Maximum delay
            distribution: 'lognormal' (skewed toward min, more natural)
                         or 'uniform' (fallback, same as before)
        """
        if distribution == "lognormal":
            mu = math.log((min_sec + max_sec) / 2)
            sigma = 0.4
            raw = random.lognormvariate(mu, sigma)
            delay = max(min_sec, min(max_sec, raw))
        else:
            delay = random.uniform(min_sec, max_sec)

        time.sleep(delay * self.pace_multiplier)

    def _scroll_page(self, delta: int, container_selector: Optional[str] = None):
        """Scroll page using evaluate (works in both CDP and direct Playwright)."""
        if container_selector:
            try:
                self.page.evaluate(
                    f"""() => {{
                        const el = document.querySelector('{container_selector}');
                        if (el) el.scrollTop += {delta};
                    }}"""
                )
            except Exception:
                self.page.evaluate(f"window.scrollBy(0, {delta})")
        else:
            self.page.evaluate(f"window.scrollBy(0, {delta})")

    def human_scroll(
        self,
        times: int = 3,
        direction: str = "down",
        container_selector: Optional[str] = None,
    ):
        """
        Scroll with human-like inertia, acceleration, and deceleration.

        Uses window.scrollBy with smooth behavior and variable deltas
        to simulate natural scrolling patterns.

        Args:
            times: Number of scroll segments
            direction: 'down' or 'up'
            container_selector: If set, scroll within this element
        """
        print(f"  [human] Scrolling {direction} ({times} segments)...", file=sys.stderr)

        delta_sign = 1 if direction == "down" else -1

        for segment in range(times):
            total_delta = random.randint(500, 900)
            num_steps = random.randint(8, 20)
            remaining = total_delta

            for step in range(num_steps):
                progress = step / max(num_steps - 1, 1)

                if progress < 0.3:
                    speed_factor = 0.3 + (progress / 0.3) * 0.7
                elif progress > 0.7:
                    speed_factor = 1.0 - ((progress - 0.7) / 0.3) * 0.6
                else:
                    speed_factor = random.uniform(0.8, 1.2)

                if step == num_steps - 1:
                    step_delta = remaining
                else:
                    max_step = int(remaining * 0.5)
                    step_delta = max(10, random.randint(5, max(30, max_step)))
                    step_delta = min(step_delta, remaining)
                    remaining -= step_delta

                delta = int(step_delta * speed_factor) * delta_sign
                self._scroll_page(delta, container_selector)

                step_delay = random.uniform(0.01, 0.06)
                time.sleep(step_delay)

            between_segment = random.uniform(0.3, 1.2)
            time.sleep(between_segment)

            if random.random() < 0.25:
                jitter = random.randint(-30, 30) * delta_sign
                self._scroll_page(jitter, container_selector)
                time.sleep(random.uniform(0.05, 0.15))

            # Overshoot correction: occasionally scroll a bit back
            if random.random() < 0.15:
                correction_delta = random.randint(-80, -20) * delta_sign
                self._scroll_page(correction_delta, container_selector)
                time.sleep(random.uniform(0.1, 0.3))

    def move_mouse_to(
        self,
        target_x: Optional[float] = None,
        target_y: Optional[float] = None,
        locator: Optional[Locator] = None,
        steps: Optional[int] = None,
    ):
        """
        Move mouse along a Bezier curve to a target position.

        Step count is derived from Fitts's Law (distance + target width) unless
        `steps` is given explicitly. Long movements (>500 px) overshoot the
        target and trace a tight correction curve back (miss-and-re-adjust).

        Args:
            target_x: Target X coordinate (overrides locator)
            target_y: Target Y coordinate (overrides locator)
            locator: Playwright Locator to move to
            steps: Explicit step count (overrides Fitts's Law)
        """
        target_width = 20.0
        if locator is not None:
            box = self._ensure_in_viewport(locator)
            if box:
                target_width = max(box["width"], 1.0)
                target_x = box["x"] + box["width"] * random.uniform(0, 1)
                target_y = box["y"] + box["height"] * random.uniform(0, 1)
            else:
                return

        if target_x is None or target_y is None:
            return

        target_x = max(0, min(target_x, self.viewport["width"]))
        target_y = max(0, min(target_y, self.viewport["height"]))

        if steps is not None:
            path, _ = _generate_bezier_path(self._mouse_pos, (target_x, target_y), steps=steps)
            self._trace_path(path)
            self._settle(target_x, target_y)
        else:
            self._move_mouse_human((target_x, target_y), target_width)

    def _move_mouse_human(self, target: Tuple[float, float], target_width: float):
        """Move with Fitts's Law pacing; overshoot-and-correct on long distances."""
        start = self._mouse_pos
        dist = math.hypot(target[0] - start[0], target[1] - start[1])
        if dist < 1:
            return

        if should_overshoot(start, target, threshold=500):
            over = overshoot(target, radius=120)
            over = (
                max(0, min(over[0], self.viewport["width"])),
                max(0, min(over[1], self.viewport["height"])),
            )
            outbound, _ = _generate_bezier_path(start, over, steps=fitts_steps(dist, target_width))
            self._trace_path(outbound)
            correction, _ = _generate_bezier_path(
                self._mouse_pos, target,
                steps=max(8, fitts_steps(dist, target_width) // 2),
            )
            self._trace_path(correction)
        else:
            path, _ = _generate_bezier_path(start, target, steps=fitts_steps(dist, target_width))
            self._trace_path(path)

        self._settle(target[0], target[1])

    def _trace_path(self, path: List[Tuple[float, float]]):
        """Emit mouse moves with trapezoidal speed profile (slow ends, fast middle)."""
        for i, (x, y) in enumerate(path):
            self.page.mouse.move(x, y)
            self._mouse_pos = (x, y)

            if i < len(path) - 1:
                progress = i / max(len(path) - 1, 1)
                speed_factor = 1.0 + abs(progress - 0.5) * 2
                delay = random.uniform(0.002, 0.015) * speed_factor
                if random.random() < 0.03:
                    delay += random.uniform(0.05, 0.15)
                time.sleep(delay)

    def _settle(self, target_x: float, target_y: float):
        """Micro-adjustments at target (humans don't land perfectly)."""
        if random.random() < 0.4:
            settle_steps = random.randint(1, 3)
            for _ in range(settle_steps):
                sx = target_x + random.gauss(0, 4)
                sy = target_y + random.gauss(0, 4)
                sx = max(0, min(sx, self.viewport["width"]))
                sy = max(0, min(sy, self.viewport["height"]))
                self.page.mouse.move(sx, sy)
                self._mouse_pos = (sx, sy)
                time.sleep(random.uniform(0.02, 0.08))
            # Final settle to actual target
            self.page.mouse.move(target_x, target_y)
            self._mouse_pos = (target_x, target_y)

    def idle_wander(self, duration_sec: float = 2.0):
        """
        Simulate idle mouse wandering (micro-movements while 'reading').

        Users don't keep the mouse perfectly still. Small random
        movements between reading pauses make the session look real.

        Args:
            duration_sec: Total time to wander
        """
        end_time = time.time() + duration_sec

        while time.time() < end_time:
            offset_x = random.gauss(0, 8)
            offset_y = random.gauss(0, 8)

            new_x = max(0, min(self._mouse_pos[0] + offset_x, self.viewport["width"]))
            new_y = max(0, min(self._mouse_pos[1] + offset_y, self.viewport["height"]))

            self.page.mouse.move(new_x, new_y)
            self._mouse_pos = (new_x, new_y)

            time.sleep(random.uniform(0.2, 0.8))

    def read_page(self, sections: int = 3):
        """
        Simulate a human reading the page content.

        Moves mouse to different sections, scrolls between them,
        adds reading pauses, dismisses cookie banners, and
        occasionally uses find-in-page.

        Args:
            sections: Number of reading sections to simulate
        """
        print(f"  [human] Simulating reading ({sections} sections)...", file=sys.stderr)

        self.dismiss_cookie_consent()

        for i in range(sections):
            target_y = (i + 1) * (self.viewport["height"] / (sections + 1))
            target_x = random.uniform(
                self.viewport["width"] * 0.15,
                self.viewport["width"] * 0.85,
            )

            self.move_mouse_to(target_x=target_x, target_y=target_y, steps=random.randint(30, 60))
            self.human_delay(1.5, 4.0, distribution="lognormal")

            self.idle_wander(random.uniform(0.5, 2.0))

            if i < sections - 1:
                self.human_scroll(times=1)
                self.human_delay(0.5, 1.5)

        self.find_on_page()

    def human_click(
        self,
        locator: Locator,
        pre_move: bool = True,
        hover_pause: bool = True,
    ):
        """
        Click an element with pre-hover and human timing.

        Real users move the mouse to an element, hover briefly,
        then click. This simulates that full interaction chain.

        Args:
            locator: Playwright Locator to click
            pre_move: Whether to move mouse along Bezier curve first
            hover_pause: Whether to pause on hover before clicking
        """
        self._ensure_in_viewport(locator)

        if pre_move:
            self.move_mouse_to(locator=locator)

        if hover_pause:
            self.human_delay(0.3, 0.8)

        locator.click()
        self.human_delay(0.2, 0.6)

    def human_type(
        self,
        locator: Locator,
        text: str,
        mistake_probability: float = 0.02,
    ):
        """
        Type text character by character with per-key variance and
        occasional mistakes (backspace + retype).

        Args:
            locator: Playwright Locator to type into
            text: Text to type
            mistake_probability: Chance of a typo per character (0-1)
        """
        self._ensure_in_viewport(locator)
        locator.click()
        self.human_delay(0.2, 0.5)

        i = 0
        while i < len(text):
            char = text[i]

            if random.random() < mistake_probability and i > 0 and char != ' ':
                nearby_keys = self._nearby_keys(char)
                if nearby_keys:
                    wrong_char = random.choice(nearby_keys)
                    self.page.keyboard.type(wrong_char, delay=random.randint(30, 80))
                    self.human_delay(0.15, 0.4)
                    self.page.keyboard.press("Backspace")
                    self.human_delay(0.1, 0.3)

            self.page.keyboard.type(char, delay=random.randint(40, 120))
            i += 1

            if random.random() < 0.08:
                self.human_delay(0.1, 0.5)

    @staticmethod
    def _nearby_keys(char: str) -> List[str]:
        """Get physically nearby keys on a QWERTY keyboard for typo simulation."""
        keyboard_map = {
            'a': ['q', 's', 'z'], 'b': ['v', 'n', 'h'], 'c': ['x', 'v', 'd'],
            'd': ['s', 'f', 'e', 'c'], 'e': ['w', 'r', 'd'], 'f': ['d', 'g', 'r', 'v'],
            'g': ['f', 'h', 't', 'b'], 'h': ['g', 'j', 'y', 'n'], 'i': ['u', 'o', 'k'],
            'j': ['h', 'k', 'u', 'n'], 'k': ['j', 'l', 'i', 'm'], 'l': ['k', 'o', 'p'],
            'm': ['n', 'j', 'k'], 'n': ['b', 'j', 'h', 'm'], 'o': ['i', 'p', 'l'],
            'p': ['o', 'l'], 'q': ['w', 'a', 's'], 'r': ['e', 't', 'f'],
            's': ['a', 'd', 'w', 'z'], 't': ['r', 'y', 'g', 'f'], 'u': ['y', 'i', 'j', 'h'],
            'v': ['c', 'b', 'f', 'g'], 'w': ['q', 'e', 'a', 's'], 'x': ['z', 'c', 's', 'd'],
            'y': ['t', 'u', 'h', 'g'], 'z': ['x', 'a', 's'],
        }
        return keyboard_map.get(char.lower(), [])

    def hover_over_links(self, count: int = None):
        """
        Hover over clickable elements (links, buttons) with Bezier mouse movement.

        Uses page.evaluate to efficiently find elements in the viewport
        without creating hundreds of Playwright locator handles.

        Args:
            count: Number of elements to hover (default: random 3-6)
        """
        count = count or random.randint(3, 6)
        viewport_info = self._get_viewport_info()

        # Use evaluate to find visible in-viewport elements
        candidates = self.page.evaluate(f"""() => {{
            const vp = {viewport_info};
            const selectors = ['a[href]', 'button', 'h2 a', 'h3 a'];
            const results = [];
            for (const sel of selectors) {{
                const els = document.querySelectorAll(sel);
                for (const el of els) {{
                    const r = el.getBoundingClientRect();
                    const inViewport = (
                        r.top >= 0 && r.left >= 0 &&
                        r.bottom <= vp.innerHeight &&
                        r.right <= vp.innerWidth
                    );
                    if (inViewport && results.length < {count * 2}) {{
                        results.push({{
                            tag: el.tagName,
                            text: (el.textContent || '').trim().substring(0, 40),
                            x: r.left + r.width / 2,
                            y: r.top + r.height / 2,
                        }});
                    }}
                }}
            }}
            return results;
        }}""")

        if not candidates:
            return

        random.shuffle(candidates)
        hovered = 0
        for c in candidates:
            if hovered >= count:
                break
            try:
                self.move_mouse_to(target_x=c["x"], target_y=c["y"])
                self.human_delay(0.4, 1.2, distribution="lognormal")
                hovered += 1
            except Exception:
                continue

        if hovered:
            print(f"  [human] Hovered over {hovered} link(s)/button(s)", file=sys.stderr)

    def warm_up(self, sites: Optional[List[dict]] = None):
        """
        Visit neutral sites before the target portal to create a
        realistic navigation history (warm-up pattern).

        Anti-bot systems check browsing history patterns. A session
        that goes directly to LinkedIn with no prior navigation is
        suspicious. This method visits 3-5 random neutral sites.

        Args:
            sites: List of warm-up site dicts with 'url' and 'wait_range'.
                   If None, picks a random subset from WARM_UP_SITES.
        """
        if sites is None:
            count = random.randint(3, 5)
            sites = random.sample(WARM_UP_SITES, min(count, len(WARM_UP_SITES)))

        print(f"[human] Browser warm-up: visiting {len(sites)} neutral sites...", file=sys.stderr)

        for site in sites:
            url = site["url"]
            wait_range = site.get("wait_range", (2.0, 4.0))
            interact = site.get("interact", False)

            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
                self.human_delay(*wait_range, distribution="lognormal")

                if interact:
                    self.human_scroll(times=random.randint(1, 2))
                    self.hover_over_links(random.randint(2, 4))
                    self.idle_wander(random.uniform(0.5, 1.5))

                print(f"  [human] Warm-up: {url} (waited {wait_range[0]}-{wait_range[1]}s)", file=sys.stderr)

            except Exception as e:
                print(f"  [human] Warm-up skip {url}: {e}", file=sys.stderr)

        self.human_delay(1.0, 2.5)

    def detect_auth_barrier(self) -> bool:
        """
        Detect if the current page is an authentication barrier
        (login, challenge, CAPTCHA, rate-limit, etc.).

        Checks both URL patterns and page title indicators across
        multiple platforms (LinkedIn, Tecnoempleo, generic).

        Returns:
            True if an auth barrier was detected
        """
        current_url = self.page.url.lower()
        current_title = self.page.title().lower()

        for pattern in AUTH_BARRIER_PATTERNS:
            if pattern in current_url:
                print(f"  [human] Auth barrier detected in URL: {pattern}", file=sys.stderr)
                print(f"  [human] Current URL: {self.page.url}", file=sys.stderr)
                return True

        for indicator in AUTH_BARRIER_TITLES:
            if indicator in current_title:
                print(f"  [human] Auth barrier detected in title: '{indicator}'", file=sys.stderr)
                print(f"  [human] Current title: {self.page.title()}", file=sys.stderr)
                return True

        challenge_selectors = [
            'input[type="password"]',
            '#captcha',
            '.captcha',
            '[data-test="challenge"]',
            'iframe[src*="captcha"]',
            'iframe[src*="recaptcha"]',
            'iframe[src*="hcaptcha"]',
        ]

        for selector in challenge_selectors:
            try:
                if self.page.locator(selector).first.is_visible(timeout=500):
                    print(f"  [human] Auth barrier detected: challenge element '{selector}'", file=sys.stderr)
                    return True
            except Exception:
                continue

        return False

    def detect_rate_limit(self) -> bool:
        """
        Detect if the page shows a rate-limiting message.

        Returns:
            True if rate limiting was detected
        """
        rate_limit_indicators = [
            "too many requests",
            "rate limit",
            "slow down",
            "demasiadas solicitudes",
            "intenta mas tarde",
            "try again later",
            "temporarily blocked",
            "unusual activity",
            "actividad inusual",
        ]

        try:
            page_text = self.page.inner_text("body").lower()
            for indicator in rate_limit_indicators:
                if indicator in page_text:
                    print(f"  [human] Rate limit detected: '{indicator}'", file=sys.stderr)
                    return True
        except Exception:
            pass

        return False

    def human_navigate(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout: int = 30000,
        warm_up: bool = False,
    ):
        """
        Navigate to a URL with full human behavior sequence.

        Combines warm-up, navigation, reading simulation, and
        auth barrier detection in a single method call.

        Args:
            url: Target URL
            wait_until: Playwright wait condition
            timeout: Navigation timeout in ms
            warm_up: Whether to warm up browser first
        """
        if warm_up:
            self.warm_up()

        self.human_delay(1.0, 2.5)
        self.page.goto(url, wait_until=wait_until, timeout=timeout)
        self.human_delay(1.5, 3.5)

        if self.detect_auth_barrier():
            raise AuthBarrierError(self.page.url)

        if self.detect_rate_limit():
            raise RateLimitError(self.page.url)


    def dismiss_cookie_consent(self, selectors: Optional[List[str]] = None):
        """
        Detect and dismiss cookie consent banners.

        Many portals show cookie banners on first visit. Dismissing them
        makes navigation look more natural and prevents the banner from
        blocking clickable elements.

        Args:
            selectors: CSS selectors for cookie accept buttons.
                       Defaults to common patterns.
        """
        selectors = selectors or [
            'button:has-text("Aceptar")',
            'button:has-text("Accept")',
            'button:has-text("Acepto")',
            'button:has-text("Entendido")',
            'button:has-text("Got it")',
            'button:has-text("Allow")',
            'button:has-text("Permitir")',
            'button:has-text("De acuerdo")',
            '#cookies button',
            '.cookie-consent button',
            '[aria-label*="cookie" i]',
            '[aria-label*="consent" i]',
        ]

        for selector in selectors:
            try:
                btn = self.page.locator(selector).first
                if btn.is_visible(timeout=1000):
                    self.move_mouse_to(locator=btn)
                    self.human_delay(0.2, 0.6)
                    btn.click(timeout=2000)
                    self.human_delay(0.3, 0.8)
                    return
            except Exception:
                continue

    def find_on_page(self, probability: float = 0.3):
        """
        Simulate pressing Ctrl+F to find text on the page.

        Developers and power users frequently use find-in-page.
        This opens the find bar, types a common word, browses results,
        then closes.

        Args:
            probability: Chance of actually doing it per call (0-1)
        """
        if random.random() >= probability:
            return

        common_words = [
            "python", "rails", "ruby", "remoto", "remote", "trabajo",
            "desarrollador", "developer", "salario", "experiencia",
            "requisitos", "beneficios", "modalidad", "jornada",
        ]
        word = random.choice(common_words)

        try:
            self.page.keyboard.press("Control+f")
            self.human_delay(0.3, 0.8)
            self.page.keyboard.type(word, delay=random.randint(30, 70))
            self.human_delay(0.5, 1.5)
            self.page.keyboard.press("Escape")
            self.human_delay(0.2, 0.5)
        except Exception:
            pass


class AuthBarrierError(Exception):
    """Raised when an authentication barrier is detected."""

    def __init__(self, url: str):
        self.url = url
        super().__init__(f"Auth barrier detected at: {url}")


class RateLimitError(Exception):
    """Raised when rate limiting is detected."""

    def __init__(self, url: str):
        self.url = url
        super().__init__(f"Rate limit detected at: {url}")