# ts6-musicbot

Bot de música para TeamSpeak 6. Reproduce audio de YouTube en un canal usando yt-dlp, ffmpeg y un sink virtual de PulseAudio.

---

## Cómo funciona

```
Usuario escribe !play <query>
        │
        ▼
ChatListener (SSH ServerQuery, puerto 10012)
  └─ recibe notifytextmessage en tiempo real
        │
        ▼
CommandParser → resolve() → yt-dlp obtiene URL de stream
        │
        ▼
AudioPlayer → ffmpeg → PulseAudio virtual sink (musicbot_sink)
        │
        ▼
TS6 Desktop Client captura musicbot_sink.monitor como micrófono
  └─ el audio sale en el canal de voz
        │
        ▼
WebQueryClient (HTTP WebQuery, puerto 10081)
  └─ envía respuestas de texto al canal
```

El bot usa **dos conexiones** al servidor TS6:
- **WebQuery HTTP** (puerto 10081): API REST stateless para enviar mensajes de texto.
- **SSH ServerQuery** (puerto 10012): protocolo TS3-compatible vía SSH para recibir eventos de chat en tiempo real.

---

## Requisitos previos

- Docker / Podman + docker-compose
- Acceso a un servidor TeamSpeak 6
- El archivo `teamspeak-client.tar.gz` del cliente Linux de TS6 (ver abajo)
- Una cuenta de ServerQuery creada en el servidor con permisos de `b_virtualserver_notify_register`

---

## 1. Obtener el cliente TS6

El binario no está incluido en el repo (183 MB). Descárgalo desde https://teamspeak.com/en/downloads/#client (Linux 64-bit) y colócalo en la raíz del proyecto como `teamspeak-client.tar.gz`.

Verifica la integridad con la versión testeada:

```bash
sha256sum teamspeak-client.tar.gz
# esperado: b9ba408a0b58170ce32384fc8bba56800840d694bd310050cbadd09246d4bf27
```

> Si usas una versión diferente puede funcionar igual, pero no está garantizado.

---

## 2. Crear el usuario de ServerQuery

Conéctate al servidor como `serveradmin` vía SSH (puerto 10012):

```bash
ssh serveradmin@tu-servidor.cl -p 10012
```

Crea el usuario query dedicado al bot:

```
use 0
queryloginadd client_login_name=musicbot
# Guarda la contraseña que devuelve: client_login_password=XXXXXXXX
```

Dale permisos de Admin Server Query para poder registrarse a eventos:

```
use 1
clientdbfind pattern=musicbot -uid
# anota el cldbid
servergroupaddclient sgid=2 cldbid=<cldbid>
```

> El grupo `sgid=2` es "Admin Server Query" — otorga el permiso `b_virtualserver_notify_register` necesario para recibir mensajes de chat.

---

## 3. Configurar el entorno

Copia el archivo de ejemplo y completa los valores:

```bash
cp .env.example .env
```

```env
# Servidor TS6
TS_SERVER_HOST=tu-servidor.cl
TS_SERVER_PORT=9988
TS_SERVER_PASSWORD=
TS_CHANNEL=NombreDelCanal
TS_BOT_NICKNAME=tendroaudio

# WebQuery HTTP (envío de mensajes)
TS_WEBQUERY_HOST=tu-servidor.cl
TS_WEBQUERY_PORT=10081
TS_WEBQUERY_APIKEY=tu-api-key

# SSH ServerQuery (recepción de eventos de chat)
TS_QUERY_PORT=10012
TS_QUERY_USERNAME=musicbot
TS_QUERY_PASSWORD=la-password-generada-arriba

# Volumen inicial (0–100)
AUDIO_VOLUME=85
```

El API key de WebQuery se genera desde la interfaz de administración del servidor TS6.

---

## 4. Levantar el bot

```bash
docker compose up -d
```

La primera vez construye la imagen (puede tardar unos minutos). Al iniciar:

1. Xvfb arranca en `:99` (display virtual, necesario para el cliente TS6)
2. PulseAudio crea el sink virtual `musicbot_sink`
3. El cliente TS6 se conecta al servidor y entra al canal configurado
4. El bot Python se conecta por WebQuery y SSH ServerQuery
5. El bot envía `MusicBot connected. Type !help for commands.` al canal

Ver logs en tiempo real:

```bash
docker compose logs -f 2>&1 | grep -v "chromium\|dbus\|gcm\|registration_request"
```

---

## 5. Comandos

Escríbelos en el chat del canal de TS6:

| Comando | Descripción |
|---|---|
| `!play <búsqueda o URL>` | Busca en YouTube y encola el audio |
| `!skip` | Salta el track actual |
| `!stop` | Detiene la reproducción y limpia la cola |
| `!queue` | Muestra los primeros 10 tracks en cola |
| `!np` | Muestra el track reproduciéndose ahora |
| `!vol <0-100>` | Ajusta el volumen |
| `!help` | Lista los comandos |

---

## Estructura del proyecto

```
ts6-musicbot/
├── bot/
│   ├── main.py                  # Orquestador principal (asyncio)
│   ├── ts6/
│   │   ├── webquery.py          # Cliente HTTP WebQuery (envío)
│   │   └── chat_listener.py     # Cliente SSH ServerQuery (recepción)
│   ├── audio/
│   │   ├── player.py            # Cola de reproducción + ffmpeg → PulseAudio
│   │   └── resolver.py          # yt-dlp: resuelve query → URL de stream
│   ├── commands/
│   │   └── parser.py            # Dispatcher de comandos !
│   └── tests/
│       ├── test_chat_listener.py
│       ├── test_webquery.py
│       ├── test_integration.py  # Tests reales contra el servidor TS6
│       └── ...
├── scripts/
│   ├── entrypoint.sh            # Arranca Xvfb, PulseAudio, TS6 client, bot
│   └── launch_ts6.sh            # Lanza el cliente TS6 con la URI de conexión
├── ts6_config/
│   └── settings.ini             # Configuración del cliente TS6
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Solución de problemas

**El bot no responde a comandos**
Verifica que el usuario `musicbot` tenga el permiso `b_virtualserver_notify_register`. En el log deberías ver `ChatListener ready — waiting for messages in <canal>`.

**Access denied en PulseAudio**
El contenedor está corriendo con PulseAudio caído. Reinicia: `docker compose restart`. El entrypoint mata cualquier instancia previa antes de iniciar una nueva.

**El audio se corta**
Es normal en conexiones inestables — ffmpeg tiene `-reconnect` activo y se recupera solo. Si es frecuente, revisa el ancho de banda del servidor.

**Option buffer_size not found (ffmpeg)**
Asegúrate de usar la imagen más reciente: `docker compose build --no-cache && docker compose up -d`.
