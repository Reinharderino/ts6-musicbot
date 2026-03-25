#!/bin/bash
set -e

SINK_NAME="musicbot_sink"

# Null sink: audio is rendered here (no physical output)
pactl load-module module-null-sink \
    sink_name="$SINK_NAME" \
    sink_properties=device.description="MusicBot_Virtual_Sink"

# Expose sink monitor as a source (microphone) for the TS6 client
pactl load-module module-virtual-source \
    source_name="$SINK_NAME.mic" \
    master="$SINK_NAME.monitor"

echo "[audio] Virtual sink '$SINK_NAME' ready."
