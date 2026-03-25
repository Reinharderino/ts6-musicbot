#!/bin/bash
set -e

echo "[entrypoint] Starting Xvfb on :99..."
Xvfb :99 -screen 0 1280x720x24 &
XVFB_PID=$!
sleep 1

echo "[entrypoint] Starting PulseAudio..."
pulseaudio --start --log-target=stderr --exit-idle-time=-1
sleep 1

echo "[entrypoint] Setting up virtual audio..."
/app/scripts/setup_audio.sh

echo "[entrypoint] Launching TS6 client..."
/app/scripts/launch_ts6.sh &
TS6_PID=$!
sleep 8  # allow client to connect and register with WebQuery

echo "[entrypoint] Starting Python orchestrator..."
cd /app
python3 bot/main.py

# Cleanup
kill $XVFB_PID $TS6_PID 2>/dev/null || true
