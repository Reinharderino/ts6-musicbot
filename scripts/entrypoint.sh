#!/bin/bash
set -e

# tendroplayer branch — no Xvfb, no PulseAudio, no TeamSpeak GUI client.
# TS3AudioBot (sidecar container) handles all voice protocol work.
# This container just runs the Python orchestrator.

echo "[entrypoint] Starting Python orchestrator..."
cd /app
exec python3 bot/main.py
