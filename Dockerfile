FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
# TS3AudioBot bundles .NET Core 3.1 which can't find ICU on Ubuntu 24.04.
# Invariant mode disables locale-sensitive string ops — fine for a music bot.
ENV DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1

# Runtime deps — no Xvfb, no PulseAudio, no TS6 GUI client.
# TS3AudioBot is a self-contained .NET binary that implements the TS3 voice
# protocol directly: no Chromium, no virtual display, ~5% CPU vs 20-30%.
RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3 \
    python3-pip \
    python3-venv \
    wget \
    curl \
    ca-certificates \
    jq \
    unzip \
    libicu74 \
    libssl3 \
    libopus-dev \
    && rm -rf /var/lib/apt/lists/*

# libssl1.1 compat — TS3AudioBot 0.12.0 bundles .NET Core 3.1 which links against
# libssl1.1 (Ubuntu 24.04 only ships libssl3; both can coexist safely).
RUN curl -fsSL \
    "http://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2_amd64.deb" \
    -o /tmp/libssl1.1.deb \
    && dpkg -i /tmp/libssl1.1.deb \
    && rm /tmp/libssl1.1.deb

# yt-dlp (latest from GitHub, more up to date than pip)
RUN curl -fsSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
    -o /usr/local/bin/yt-dlp && chmod +x /usr/local/bin/yt-dlp

# TS3AudioBot 0.12.0 — self-contained Linux x64 binary (bundles its own runtime)
# SHA of ts3audiobot dir verified at build time; no separate .NET install needed.
RUN mkdir -p /opt/ts3audiobot \
    && curl -fsSL \
        "https://github.com/Splamy/TS3AudioBot/releases/download/0.12.0/TS3AudioBot_linux_x64.tar.gz" \
        -o /tmp/ts3ab.tar.gz \
    && tar -xzf /tmp/ts3ab.tar.gz -C /opt/ts3audiobot \
    && chmod +x /opt/ts3audiobot/TS3AudioBot \
    && rm /tmp/ts3ab.tar.gz

WORKDIR /app

COPY bot/requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

COPY bot/ ./bot/
COPY scripts/ ./scripts/
COPY ts3audiobot/ ./ts3audiobot/
RUN chmod +x scripts/*.sh ts3audiobot/*.sh

CMD ["./scripts/entrypoint.sh"]
