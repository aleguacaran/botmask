# syntax=docker/dockerfile:1

# ═══════════════════════════════════════════════════════════════════════════
# base — common runtime: Python, Brave, fonts/locale/timezone, patchright
# ═══════════════════════════════════════════════════════════════════════════
FROM python:slim AS base

# System dependencies for Docker fingerprint mimicry
RUN apt update && apt upgrade -y

# Fonts, locale, timezone, and system utilities
RUN apt install -y --no-install-recommends \
    curl \
    ca-certificates \
    fonts-liberation \
    fonts-liberation-sans-narrow \
    fonts-dejavu-core \
    fonts-noto \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    tzdata \
    locales \
    dbus-x11 \
    xdg-utils \
    libnss3-tools \
    libavcodec-extra \
    socat \
    2>&1

# Configure locale (default es_VE, change LANG in .env if needed)
RUN echo "es_VE.UTF-8 UTF-8" >> /etc/locale.gen && \
    locale-gen && \
    update-locale LANG=es_VE.UTF-8 LC_ALL=es_VE.UTF-8

# Set timezone (matching .env default)
RUN ln -fs /usr/share/zoneinfo/America/Caracas /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata

# Create consistent machine-id (mimics a real system)
RUN echo "b9e7a1c2d3f4e5a6b7c8d9e0f1a2b3c4" > /etc/machine-id && \
    echo "b9e7a1c2d3f4e5a6b7c8d9e0f1a2b3c4" > /var/lib/dbus/machine-id

# Brave Browser (glibc → Debian base; Brave cannot run on musl/Alpine)
RUN curl -fsS https://dl.brave.com/install.sh | sh

# Pip: suppress root-user warning
ENV PIP_ROOT_USER_ACTION=ignore

COPY . .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install . && \
    patchright install chromium

# ═══════════════════════════════════════════════════════════════════════════
# develop — LOCAL dev on the host display (Wayland/X11 shared via compose.yaml)
#   Build: docker build --target develop -t tuqueque:develop .
#   Run:   docker compose up -d --build        (target=develop set in compose.yaml)
#   No virtual display stack → start.sh runs the browser directly.
# ═══════════════════════════════════════════════════════════════════════════
FROM base AS develop

ENTRYPOINT ["/app/start.sh"]

# ═══════════════════════════════════════════════════════════════════════════
# server — HEADLESS machine: Xvfb + noVNC + OS-level input tooling
#   Build: docker build --target server -t tuqueque:server .
#   Run:   docker compose up -d --build  (after CI copies .gitlab/compose.yaml
#          → compose.override.yaml, which sets target=server)
#   Default target (plain `docker build .`) → server.
# ═══════════════════════════════════════════════════════════════════════════
FROM base AS server

# Virtual display & remote viewing (server mode) + OS-level input
RUN apt install -y --no-install-recommends \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    openbox \
    xdotool \
    python3-xlib \
    python3-pil \
    scrot \
    2>&1

ENTRYPOINT ["/app/start.sh"]
