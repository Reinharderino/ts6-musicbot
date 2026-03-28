FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Minimal runtime deps — no Xvfb, no PulseAudio, no TeamSpeak GUI client.
# TS3AudioBot runs as a separate container and handles all voice protocol work.
RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3 \
    python3-pip \
    python3-venv \
    wget \
    curl \
    ca-certificates \
    jq \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp (latest from GitHub, more up to date than pip)
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
    -o /usr/local/bin/yt-dlp && chmod +x /usr/local/bin/yt-dlp

WORKDIR /app

COPY bot/requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

COPY bot/ ./bot/
COPY scripts/ ./scripts/
RUN chmod +x scripts/*.sh

CMD ["./scripts/entrypoint.sh"]
