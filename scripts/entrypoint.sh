#!/bin/bash
set -e

# ts3voice (Rust binary) handles TS voice connection directly via UDP.
# No PulseAudio, no Xvfb, no audio hardware needed.

echo "[entrypoint] Starting Python orchestrator..."


cd /app
exec python3 bot/main.py
