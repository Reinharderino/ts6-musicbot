FROM ubuntu:22.04 AS ts3voice-builder
ENV DEBIAN_FRONTEND=noninteractive

# Build deps: Rust toolchain + libs needed by tsclientlib/audiopus
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    pkg-config \
    libssl-dev \
    libopus-dev \
    cmake \
    && rm -rf /var/lib/apt/lists/*

RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain stable
ENV PATH="/root/.cargo/bin:$PATH"

WORKDIR /build
COPY ts3voice/ .

# Pre-fetch deps so we can patch tsproto before compiling.
# Two TS3-era constraints in tsproto 0.2 break TS6 certificate parsing:
#   1. Intermediate block data range check rejects TS6 values (e.g. 0x104, 0xb8b7f440)
#   2. Block type 8 (TS6 extension, 42 extra bytes) is unknown to tsproto and causes parse failure
RUN cargo fetch

# Expose tsclientlib::Connection::send_command so we can send a clientupdate
# after connecting to fix mute/hardware flags overridden by the TS6 server.
RUN TSCLIENTLIB_LIB=$(find /root/.cargo/registry/src -name "lib.rs" \
        -path "*/tsclientlib-*/src/*" 2>/dev/null | head -1) && \
    echo "Patching $TSCLIENTLIB_LIB" && \
    sed -i 's/fn send_command(&mut self/pub fn send_command(\&mut self/' "$TSCLIENTLIB_LIB" && \
    grep -n "pub fn send_command" "$TSCLIENTLIB_LIB"

RUN TSPROTO_LICENSE=$(find /root/.cargo/registry/src -name "license.rs" \
        -path "*/tsproto-*/src/*" 2>/dev/null | head -1) && \
    echo "Patching $TSPROTO_LICENSE" && \
    # 1. Remove intermediate data range check: TS6 sends u32 values the TS3-era check rejects
    sed -i 's/return Err(Error::IntermediateInvalidData(license_data));//' "$TSPROTO_LICENSE" && \
    # 2. Handle block type 8 (TS6 extension): 42 extra bytes after the 42-byte header
    sed -i 's/32 => (InnerLicense::Ephemeral, 0),/8 => { if data.len() < 84 { return Err(Error::TooShort); } (InnerLicense::Ephemeral, 42) } 32 => (InnerLicense::Ephemeral, 0),/' "$TSPROTO_LICENSE" && \
    grep -n "IntermediateInvalidData\|InnerLicense::Ephemeral" "$TSPROTO_LICENSE"

RUN cargo build --release

# ── Runtime image ─────────────────────────────────────────────────────────────
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

# Runtime deps: ffmpeg (audio decode), python3, yt-dlp, libopus0 (ts3voice runtime)
# libssl3 (ts3voice TLS), ca-certificates (HTTPS)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3 \
    python3-pip \
    curl \
    ca-certificates \
    libopus0 \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp (latest from GitHub)
RUN curl -fsSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
    -o /usr/local/bin/yt-dlp && chmod +x /usr/local/bin/yt-dlp

# ts3voice Rust binary
COPY --from=ts3voice-builder /build/target/release/ts3voice /usr/local/bin/ts3voice

WORKDIR /app

COPY bot/requirements.txt .
RUN pip3 install -r requirements.txt

COPY bot/ ./bot/
COPY scripts/ ./scripts/
RUN chmod +x scripts/*.sh

CMD ["./scripts/entrypoint.sh"]
