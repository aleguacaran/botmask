# tuqueque

> Containerized human-behavior browser automation toolkit. Installable as a plugin in other projects that need browser automation while evading anti-bot systems.

## What is this?

A reusable, containerized browser-automation kit that simulates realistic human behavior
(Bezier-curve mouse movement, inertia scrolling, natural delays, typo typing, warm-up
sessions, reading simulation, auth-barrier detection) on top of **Brave Browser + Patchright**.

Extracted from the `career-ops` pipeline (`~/Proyectos/ai/jobs`) into an isolated, installable
package so it can be dropped into any project that needs stealthy browser interaction.

## Stack

| Layer | Tool |
| --- | --- |
| Runtime | Docker / Docker Compose |
| Browser | **Brave** (Chromium; ad-blocking, anti-fingerprinting) |
| Automation | **Patchright** (undetectable Playwright fork, CDP) |
| Human behavior | `human_behavior` module (this project) |
| Config | `config` module, env-driven (inherited from `jobs`) |
| Hardening | BrowserForge headers (planned), OS-level input fallback (planned) |

**Decision (Phase 0, `docs/decision.md`): Brave only.** Firefox engines (camoufox,
invisible_playwright) were evaluated and discarded. Hard targets are handled with
OS-level input (Xvfb + xdotool/PyAutoGUI) + graceful challenge detection.

## How the AI knows where to click

See **`docs/interaction-model.md`**. Short version: the AI picks elements from a numbered
accessibility tree (never pixel coordinates); the script resolves element → bounding box →
humanized mouse path. OS-level input maps viewport → screen coords via a one-time window
offset calibration.

## Container usage

### Local (real display, like `jobs`) — `develop` target

Shares the host display into the container (Wayland socket + X11). `compose.yaml`
builds the `develop` stage (no virtual display stack).

```bash
cp .env.example .env   # adjust DISPLAY, WAYLAND_DISPLAY for your host
docker compose up -d --build
```

Volumes: `.:/app`, `/tmp/.X11-unix`, `/run/user/<UID>/wayland-0`. CDP exposed at `:9222`.

### Server (no monitor) — Xvfb + noVNC — `deploy` target

The server override lives in **`.gitlab/compose.yaml`**; a future GitLab CI step copies it
to `compose.override.yaml` (which Docker Compose auto-loads), then:

```bash
docker compose up -d --build   # target=deploy via the override
```

Runs Brave headful on an Xvfb virtual display; watch it at `http://<host>:6080` (noVNC) or
VNC at `:5900`. Same element→box→input logic — only the display source differs.

`start.sh` auto-detects the mode from the environment: with `DISPLAY`/`WAYLAND_DISPLAY`
present it runs the browser directly; with none (or `VIRTUAL_DISPLAY=true`) it boots the
Xvfb stack first. On every start it also provisions Python packages + browser binaries at
runtime (`pip install .` + `patchright install chromium`), cached in the `cache` volume
(`/root/.cache` — pip wheels + browsers) so the image itself stays small.

## Status

- **Phase 0 — Evaluation: COMPLETE** → `docs/decision.md`
- **Phase 1 — Package extraction & container scaffold: IN PROGRESS**
  - `config.py` migrated ✅ · Dockerfile (develop/deploy) + compose + start.sh scaffolded ✅
  - Fitts + overshoot mouse port ⏳ · `human_behavior.py` migration ⏳ (see `TODO.md`)

## Docker targets (multistage)

| Target | For | Display | Build |
| --- | --- | --- | --- |
| `develop` (default via compose.yaml) | local dev on host Wayland/X11 | host display | `docker build --target develop -t tuqueque:develop .` |
| `deploy` (default target of plain `docker build`) | headless machine / CI | Xvfb + noVNC | `docker build --target deploy -t tuqueque:deploy .` |

Base image is Debian `python:slim` — Brave requires glibc and cannot run on Alpine/musl.

## Migrating from `jobs`

What can and cannot be reused from the `jobs` project: `docs/migration-from-jobs.md`.
