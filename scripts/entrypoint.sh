#!/bin/bash
set -e

# tendroplayer branch — TS3AudioBot handles voice; Python bot handles chat/queue.
# No Xvfb, no PulseAudio, no TeamSpeak GUI client.

echo "[entrypoint] Generating TS3AudioBot config..."
/app/ts3audiobot/generate_config.sh

echo "[entrypoint] Starting TS3AudioBot..."
cd /opt/ts3audiobot
./TS3AudioBot > /tmp/ts3audiobot.log 2>&1 &
TSAB_PID=$!

# Wait up to 30 s for the REST API to become reachable
echo "[entrypoint] Waiting for TS3AudioBot API on :58913..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:58913/api/bot/info/0 > /dev/null 2>&1; then
        echo "[entrypoint] TS3AudioBot API ready (attempt $i)"
        break
    fi
    sleep 1
done

echo "[entrypoint] Starting Python orchestrator..."
cd /app
exec python3 bot/main.py
