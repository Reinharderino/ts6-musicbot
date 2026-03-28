#!/bin/bash
# Writes ts3audiobot.toml into /opt/ts3audiobot/data/ from environment variables.
# Called by entrypoint.sh before starting TS3AudioBot.

DATA_DIR="/opt/ts3audiobot/data"
mkdir -p "$DATA_DIR"
CONF="$DATA_DIR/ts3audiobot.toml"

cat > "$CONF" <<EOF
[connect]
address = "${TS_SERVER_HOST}"
port    = ${TS_SERVER_PORT:-9987}
${TS_SERVER_PASSWORD:+password = "${TS_SERVER_PASSWORD}"}

[bot]
name    = "${TS_BOT_NICKNAME:-tendroaudio}"
channel = "${TS_CHANNEL}"
${TS_CHANNEL_PASSWORD:+channel_password = "${TS_CHANNEL_PASSWORD}"}

[web]
enable = true
hosts  = ["*"]
port   = 58913

[rights]
enabled = false
EOF

echo "[ts3audiobot] Config written to $CONF"
