// ts3voice: reads raw s16le PCM from a TCP socket, Opus-encodes, and streams
// to a TeamSpeak 3/6 server.  No audio hardware or PulseAudio required.
//
// Environment variables:
//   TS_SERVER_HOST       – server hostname/IP (required)
//   TS_SERVER_PORT       – UDP voice port (default 9987)
//   TS_BOT_NICKNAME      – display name (default "ts3voice")
//   TS_CHANNEL           – channel to join by name (default: server default)
//   TS_SERVER_PASSWORD   – server password (optional)
//   TS_PCM_PORT          – local TCP port to listen for PCM (default 7777)
//
// PCM format: s16le, 48 000 Hz, mono, 960-sample frames (1920 bytes each).
// ffmpeg pipeline example:
//   ffmpeg -i track.webm -f s16le -ar 48000 -ac 1 tcp://127.0.0.1:7777

use std::env;
use std::time::Duration;

use tokio::net::TcpListener;

use anyhow::{bail, Result};
use audiopus::{Application, Bitrate, Channels, SampleRate};
use audiopus::coder::Encoder;
use futures::prelude::*;
use tokio::sync::mpsc;
use tokio::sync::mpsc::error::TryRecvError;
use tsclientlib::{Connection, DisconnectOptions, Identity, StreamItem};
use tsclientlib::messages::c2s;
use tsproto_packets::packets::{AudioData, CodecType, OutAudio};

const FRAME_SAMPLES: usize = 960; // 20 ms at 48 kHz
const FRAME_BYTES: usize = FRAME_SAMPLES * 2; // s16le mono: 1920 bytes

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
    let pcm_port: u16 = env::var("TS_PCM_PORT")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(7777);

    // Bind TCP listener early so it's ready before we even connect to TS.
    let listener = TcpListener::bind(format!("127.0.0.1:{}", pcm_port)).await?;
    eprintln!("[ts3voice] Listening for PCM on 127.0.0.1:{}", pcm_port);

    let id = Identity::create();

    let opts = Connection::build(format!("{}:{}", server_host, server_port))
        .name(nickname.clone())
        .identity(id)
        .input_muted(false)
        .output_muted(false);

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

    // Force unmuted / hardware-enabled state on the server.
    // TS6 may override these flags after clientinit, silently blocking send_audio.
    let update_packet = c2s::OutClientUpdateMessage::new(&mut std::iter::once(c2s::OutClientUpdatePart {
        name: None,
        input_muted: Some(false),
        output_muted: Some(false),
        is_away: Some(false),
        away_message: None,
        input_hardware_enabled: Some(true),
        output_hardware_enabled: Some(true),
        is_channel_commander: None,
        avatar_hash: None,
        phonetic_name: None,
        talk_power_request: None,
        talk_power_request_message: None,
        is_recording: None,
        badges: None,
    }));
    if let Err(e) = con.send_command(update_packet) {
        eprintln!("[ts3voice] clientupdate failed: {}", e);
    } else {
        eprintln!("[ts3voice] clientupdate sent: input_muted=0 output_muted=0 hardware=1");
    }

    // Opus encoder lives on the main thread (audiopus::Encoder is !Send)
    let mut encoder = Encoder::new(SampleRate::Hz48000, Channels::Mono, Application::Audio)?;
    encoder.set_bitrate(Bitrate::BitsPerSecond(64_000))?;

    // Accept PCM connections in a loop: one TCP connection per track.
    // Each connect → blocking reader thread → disconnect → wait for next track.
    // Channel stays alive (via listener_tx) until the accept loop itself fails.
    let (pcm_tx, mut pcm_rx) = mpsc::channel::<Vec<i16>>(16);
    let listener_tx = pcm_tx.clone();
    drop(pcm_tx); // listener_tx is the only sender; dropping it exits the main loop

    tokio::spawn(async move {
        loop {
            match listener.accept().await {
                Ok((socket, addr)) => {
                    eprintln!("[ts3voice] PCM stream connected from {}", addr);
                    let tx = listener_tx.clone();
                    // Convert to std TcpStream for blocking read_exact in a thread.
                    let mut std_sock = match socket.into_std() {
                        Ok(s) => s,
                        Err(e) => { eprintln!("[ts3voice] socket error: {}", e); continue; }
                    };
                    if let Err(e) = std_sock.set_nonblocking(false) {
                        eprintln!("[ts3voice] set_nonblocking error: {}", e); continue;
                    }
                    std::thread::spawn(move || {
                        use std::io::Read;
                        let mut raw = vec![0u8; FRAME_BYTES];
                        loop {
                            match std_sock.read_exact(&mut raw) {
                                Ok(()) => {
                                    let samples: Vec<i16> = raw
                                        .chunks_exact(2)
                                        .map(|b| i16::from_le_bytes([b[0], b[1]]))
                                        .collect();
                                    if tx.blocking_send(samples).is_err() { break; }
                                }
                                Err(_) => break, // track ended → ffmpeg closed connection
                            }
                        }
                        eprintln!("[ts3voice] PCM stream disconnected");
                        // tx dropped here; listener_tx still alive → channel stays open
                    });
                }
                Err(e) => {
                    eprintln!("[ts3voice] TCP accept error: {}", e);
                    break; // listener_tx dropped → channel disconnects → main loop exits
                }
            }
        }
    });

    let mut voice_id: u16 = 0;
    let mut opus_buf = vec![0u8; 4096];

    // Pace audio at exactly 20 ms / frame (960 samples @ 48 kHz) so we never
    // burst-send frames faster than real-time regardless of how fast ffmpeg
    // decodes the file.
    let mut interval = tokio::time::interval(Duration::from_millis(20));
    interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);

    // TS6 resets input_hardware_enabled=false on the bot's client state when
    // no audio is flowing. Re-send clientupdate at the start of each new
    // transmission burst so the server allows the audio through.
    let mut was_transmitting = false;

    loop {
        // Re-create the events drive-future each iteration so borrow is fresh.
        // select! drops it before the tick branch body executes, freeing &mut con.
        let events = con.events().try_for_each(|_| future::ok(()));

        tokio::select! {
            _ = interval.tick() => {
                match pcm_rx.try_recv() {
                    Ok(samples) => {
                        if !was_transmitting {
                            // First frame after silence — re-assert unmuted/hardware state
                            // so the server doesn't silently drop the audio.
                            let upd = c2s::OutClientUpdateMessage::new(&mut std::iter::once(c2s::OutClientUpdatePart {
                                name: None,
                                input_muted: Some(false),
                                output_muted: Some(false),
                                is_away: Some(false),
                                away_message: None,
                                input_hardware_enabled: Some(true),
                                output_hardware_enabled: Some(true),
                                is_channel_commander: None,
                                avatar_hash: None,
                                phonetic_name: None,
                                talk_power_request: None,
                                talk_power_request_message: None,
                                is_recording: None,
                                badges: None,
                            }));
                            if let Err(e) = con.send_command(upd) {
                                eprintln!("[ts3voice] clientupdate (resume) failed: {}", e);
                            }
                            was_transmitting = true;
                        }
                        let len = match encoder.encode(&samples, &mut opus_buf) {
                            Ok(n) => n,
                            Err(e) => {
                                eprintln!("[ts3voice] encode error: {}", e);
                                continue;
                            }
                        };
                        let packet = OutAudio::new(&AudioData::C2S {
                            id: voice_id,
                            codec: CodecType::OpusMusic,
                            data: &opus_buf[..len],
                        });
                        voice_id = voice_id.wrapping_add(1);
                        if let Err(e) = con.send_audio(packet) {
                            eprintln!("[ts3voice] send_audio error: {}", e);
                        }
                    }
                    Err(TryRecvError::Empty) => {
                        was_transmitting = false; // track silence periods
                    }
                    Err(TryRecvError::Disconnected) => {
                        eprintln!("[ts3voice] PCM listener exited");
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
