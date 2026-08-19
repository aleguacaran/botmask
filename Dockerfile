FROM python:slim AS base

RUN apt update && apt upgrade -y

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

RUN echo "es_VE.UTF-8 UTF-8" >> /etc/locale.gen && \
    locale-gen && \
    update-locale LANG=es_VE.UTF-8 LC_ALL=es_VE.UTF-8

RUN ln -fs /usr/share/zoneinfo/America/Caracas /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata

RUN echo "b9e7a1c2d3f4e5a6b7c8d9e0f1a2b3c4" > /etc/machine-id && \
    echo "b9e7a1c2d3f4e5a6b7c8d9e0f1a2b3c4" > /var/lib/dbus/machine-id

RUN curl -fsS https://dl.brave.com/install.sh | sh

COPY . .

FROM base AS develop

ENTRYPOINT ["/app/start.sh"]

FROM base AS deploy

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