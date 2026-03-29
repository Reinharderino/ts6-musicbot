#!/bin/bash
# Writes TS3AudioBot config files from environment variables.
# Called by entrypoint.sh before starting TS3AudioBot.

set -e

DATA_DIR="/opt/ts3audiobot/data"
mkdir -p "$DATA_DIR" "$DATA_DIR/bots"

# ── Main config ──────────────────────────────────────────────────────────────
# The [bot] section acts as the default template for all bots.
# Setting run = true + providing connect details here will auto-start a bot.

{
  printf '[connect]\n'
  printf 'address = "%s"\n' "${TS_SERVER_HOST}"
  printf 'port = %s\n' "${TS_SERVER_PORT:-9988}"
  printf '\n'
  printf '[bot]\n'
  printf 'name = "%s"\n' "${TS_BOT_NICKNAME:-tendroaudio}"
  printf 'run = true\n'
  printf '\n'
  printf '[bot.connect]\n'
  printf 'address = "%s:%s"\n' "${TS_SERVER_HOST}" "${TS_SERVER_PORT:-9988}"
  printf 'name = "%s"\n' "${TS_BOT_NICKNAME:-tendroaudio}"
  printf 'channel = "%s"\n' "${TS_CHANNEL}"
  if [ -n "${TS_SERVER_PASSWORD}" ]; then
    printf 'server_password = { pw = "%s", hashed = false, autohash = false }\n' "${TS_SERVER_PASSWORD}"
  fi
  printf '\n'
  printf '[web]\n'
  printf 'enable = true\n'
  printf 'hosts = ["*"]\n'
  printf 'port = 58913\n'
  printf '\n'
  printf '[web.api]\n'
  printf 'enabled = true\n'
  printf 'matcher = "exact"\n'
  printf '\n'
  printf '[rights]\n'
  printf 'enabled = false\n'
  printf '\n'
  printf '[configs]\n'
  printf 'bots_path = "bots"\n'
} > "$DATA_DIR/ts3audiobot.toml"

# ── Per-bot config: lives in bots/<name>.toml ────────────────────────────────
# TS3AudioBot loads all *.toml from bots_path and starts ones with run = true.
BOT_CONF="$DATA_DIR/bots/${TS_BOT_NICKNAME:-tendroaudio}.toml"

# Preserve the identity key so the client doesn't re-register every restart.
EXISTING_KEY='key = ""'
if [ -f "$BOT_CONF" ]; then
  KEY_LINE=$(grep -m1 '^key = ' "$BOT_CONF" 2>/dev/null || true)
  if [ -n "$KEY_LINE" ]; then
    EXISTING_KEY="$KEY_LINE"
  fi
fi

{
  printf 'run = true\n'
  printf '\n'
  printf '[connect]\n'
  printf 'address = "%s:%s"\n' "${TS_SERVER_HOST}" "${TS_SERVER_PORT:-9988}"
  printf 'name = "%s"\n' "${TS_BOT_NICKNAME:-tendroaudio}"
  printf 'channel = "%s"\n' "${TS_CHANNEL}"
  if [ -n "${TS_SERVER_PASSWORD}" ]; then
    printf 'server_password = { pw = "%s", hashed = false, autohash = false }\n' "${TS_SERVER_PASSWORD}"
  fi
  printf '\n'
  printf '[connect.identity]\n'
  printf '%s\n' "$EXISTING_KEY"
  printf 'offset = 0\n'
  printf 'level = -1\n'
} > "$BOT_CONF"

echo "[ts3audiobot] Config written — bot: ${TS_BOT_NICKNAME:-tendroaudio} → ${TS_SERVER_HOST}:${TS_SERVER_PORT:-9988} / ${TS_CHANNEL}"
