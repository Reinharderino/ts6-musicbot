// ts3voice: reads raw s16le PCM from stdin, Opus-encodes, and streams to a
// TeamSpeak 3/6 server.  No audio hardware or PulseAudio required.
//
// Environment variables:
//   TS_SERVER_HOST       – server hostname/IP (required)
//   TS_SERVER_PORT       – UDP voice port (default 9987)
//   TS_BOT_NICKNAME      – display name (default "ts3voice")
//   TS_CHANNEL           – channel to join by name (default: server default)
//   TS_SERVER_PASSWORD   – server password (optional)
//
// Stdin format: s16le, 48 000 Hz, mono, 960-sample frames (1920 bytes each).
// ffmpeg pipeline example:
//   ffmpeg -i track.webm -f s16le -ar 48000 -ac 1 pipe:1 | ts3voice

use std::env;

use anyhow::{bail, Result};
use audiopus::{Application, Bitrate, Channels, SampleRate};
use audiopus::coder::Encoder;
use futures::prelude::*;
use tokio::sync::mpsc;
use tsclientlib::{Connection, DisconnectOptions, Identity, StreamItem};
use tsproto_packets::packets::{AudioData, CodecType, OutAudio};

const FRAME_SAMPLES: usize = 960; // 20 ms at 48 kHz
const FRAME_BYTES: usize = FRAME_SAMPLES * 2; // s16le: 2 bytes per sample

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| {
                    tracing_subscriber::EnvFilter::new("warn")
                }),
        )
        .with_writer(std::io::stderr)
        .init();

    let server_host = env::var("TS_SERVER_HOST").unwrap_or_else(|_| "localhost".into());
    let server_port: u16 = env::var("TS_SERVER_PORT")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(9987);
    let nickname = env::var("TS_BOT_NICKNAME").unwrap_or_else(|_| "ts3voice".into());
    let channel = env::var("TS_CHANNEL").unwrap_or_default();
    let server_password = env::var("TS_SERVER_PASSWORD").unwrap_or_default();

    let id = Identity::create();

    let opts = Connection::build(format!("{}:{}", server_host, server_port))
        .name(nickname.clone())
        .identity(id)
        .input_muted(false)
        .output_muted(true); // we don't use incoming audio

    let opts = if channel.is_empty() {
        opts
    } else {
        opts.channel(channel.clone())
    };

    let opts = if server_password.is_empty() {
        opts
    } else {
        opts.password(server_password)
    };

    let mut con = opts.connect()?;

    // Wait for initial server state to be received
    let r = con
        .events()
        .try_filter(|e| future::ready(matches!(e, StreamItem::BookEvents(_))))
        .next()
        .await;
    if let Some(Err(e)) = r {
        bail!("Connection setup failed: {}", e);
    }

    {
        use std::io::Write;
        let stderr = std::io::stderr();
        let mut h = stderr.lock();
        writeln!(
            h,
            "[ts3voice] Connected to {}:{} as '{}' channel='{}'",
            server_host, server_port, nickname, channel
        ).ok();
        h.flush().ok();
    }

    // Opus encoder lives on the main thread (audiopus::Encoder is !Send)
    let mut encoder = Encoder::new(SampleRate::Hz48000, Channels::Mono, Application::Audio)?;
    encoder.set_bitrate(Bitrate::BitsPerSecond(128_000))?;

    // Spawn a blocking OS thread to read raw PCM from stdin.
    // Sends 960-sample Vec<i16> frames over an async channel.
    let (pcm_tx, mut pcm_rx) = mpsc::channel::<Vec<i16>>(16);
    std::thread::spawn(move || {
        use std::io::Read;
        let stdin = std::io::stdin();
        let mut handle = stdin.lock();
        let mut raw = vec![0u8; FRAME_BYTES];

        loop {
            match handle.read_exact(&mut raw) {
                Ok(()) => {
                    let samples: Vec<i16> = raw
                        .chunks_exact(2)
                        .map(|b| i16::from_le_bytes([b[0], b[1]]))
                        .collect();
                    if pcm_tx.blocking_send(samples).is_err() {
                        break;
                    }
                }
                Err(_) => break, // stdin closed → ffmpeg finished
            }
        }
        eprintln!("[ts3voice] stdin closed");
        // drop pcm_tx to signal main loop
    });

    let mut voice_id: u16 = 0;
    let mut opus_buf = vec![0u8; 4096];

    loop {
        // Re-create the events drive-future each iteration so borrow is fresh.
        // select! drops it before the pcm branch body executes, freeing &mut con.
        let events = con.events().try_for_each(|_| future::ok(()));

        tokio::select! {
            pcm = pcm_rx.recv() => {
                match pcm {
                    Some(samples) => {
                        let len = match encoder.encode(&samples, &mut opus_buf) {
                            Ok(n) => n,
                            Err(e) => {
                                eprintln!("[ts3voice] encode error: {}", e);
                                continue;
                            }
                        };
                        let packet = OutAudio::new(&AudioData::C2S {
                            id: voice_id,
                            codec: CodecType::OpusVoice,
                            data: &opus_buf[..len],
                        });
                        voice_id = voice_id.wrapping_add(1);
                        if let Err(e) = con.send_audio(packet) {
                            eprintln!("[ts3voice] send_audio error: {}", e);
                        }
                    }
                    None => {
                        // stdin closed — no more audio
                        eprintln!("[ts3voice] audio stream ended");
                        break;
                    }
                }
            }
            r = events => {
                match r {
                    Ok(()) => bail!("Connection closed by server"),
                    Err(e) => bail!("Connection error: {}", e),
                }
            }
        }
    }

    con.disconnect(DisconnectOptions::new())?;
    con.events().for_each(|_| future::ready(())).await;

    eprintln!("[ts3voice] Disconnected.");
    Ok(())
}
