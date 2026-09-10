# SubWoofer - Discord Music Bot 🐶🔊

[🇵🇱 **Polska wersja**](README.md) | [🇬🇧 **English version**](README_EN.md)

---

An advanced, ultra-lightweight, and fully asynchronous music bot for **Discord**, written in **Python 3.11+** utilizing **discord.py**, **yt-dlp**, **ytmusicapi**, and **aiohttp**. It features high-fidelity audio playback, modern Slash Commands, an interactive Dashboard, per-server queue management with pagination, native Spotify link support, volume control, auto-disconnect on inactivity, and YouTube datacenter restriction bypass without requiring logins.

---

## 🚀 Key Features & Capabilities

- **Multi-Platform Audio & Playlist Support:** Play individual tracks, playlists, and albums from **YouTube**, **YouTube Music**, **Spotify** (`open.spotify.com`), and **SoundCloud** (up to 500 tracks per queue).
- **Intelligent Lazy Loading:** Playlist and album imports take only ~2 seconds (metadata extraction only), while the direct audio stream is fetched just-in-time before playback. This prevents URL expiration and avoids YouTube rate-limiting.
- **Native Spotify Support:** Direct support for Spotify track, playlist, and album links without requiring developer application registration or API credentials.
- **Interactive Search (`/search`):** Real-time search returning the top 5 matching videos/songs (strictly excluding channels and playlists) via an interactive Discord Select Menu dropdown.
- **Auto-Disconnect on Inactivity (`/autoleave`):** Automatically disconnects when the voice channel is empty after a configurable timer (default: 10 minutes), saving server resources and proxy bandwidth. Automatically cancels if someone rejoins.
- **Volume Control (`/volume`):** Seamless real-time volume adjustment from 0% to 100% (`PCMVolumeTransformer`) with per-server persistence.
- **Hard Queue Limit (500 Songs):** Built-in queue overflow protection – notifies users if the queue limit is reached.
- **Interactive Control Dashboard (`/dashboard`):** Persistent interactive dashboard with responsive buttons (Play/Pause, Skip, Shuffle, Repeat, Stop, Queue, Refresh, Help) that remain fully functional across bot restarts.
- **Queue Pagination (`/queue`):** Clean, structured list showing track numbers and titles with interactive `◀️`, page indicator (`1/4`), `▶️`, and integrated `🔀` shuffle button.
- **Diagnostic Tools:** Built-in diagnostic commands (`/ping`, `/status` with RAM & uptime metrics, `/logs` with error filtering for administrators).
- **Log Rotation:** Automated log rotation (`RotatingFileHandler`, 10 MB limit, up to 5 backups) preventing VPS disk exhaustion.
- **Discord DAVE E2EE Voice Protocol:** Full support for `davey` and `PyNaCl`, adhering to Discord's latest end-to-end encrypted voice architecture.
- **YouTube Bypass & Datacenter Support:** Built-in Deno JavaScript runtime and proxy routing (e.g. Cloudflare WARP / Privoxy) in Docker for uninterrupted VPS hosting.

---

## 📋 Available Commands (Slash Commands)

All commands and parameter names are in English:

| Command | Parameters | Description |
| :--- | :--- | :--- |
| `/play` | `query` *(text or URL)* | Plays a track or adds a playlist/album to the queue (YouTube, YT Music, Spotify) |
| `/search` | `query` *(keywords)* | Searches YouTube for 5 matching videos/songs and presents an interactive select dropdown |
| `/nowplaying` | *none* | Displays details, duration, and link of the currently playing track |
| `/pause` | *none* | Pauses the currently playing track |
| `/resume` | *none* | Resumes paused playback |
| `/volume` | `level` *(0–100)* | Sets the playback volume percentage |
| `/skip` | *none* | Skips the current track and immediately plays the next song |
| `/skipto` | `position` *(number from 1)* | Immediately jumps to the specified track in the queue |
| `/playnext` | `position` *(number from 1)* | Moves the specified track to position 1 so it plays next |
| `/shuffle` | *none* | Randomly shuffles all tracks currently in the queue |
| `/repeat` | *none* | Toggles looping for the current queue |
| `/stop` | *none* | Stops music, clears the queue, and disconnects the bot from voice |
| `/queue` | *none* | Displays the interactive paginated queue (10 tracks per page) |
| `/dashboard` | `action` *(on / off)* | Enables or disables the persistent interactive control dashboard message |
| `/setchannel` | `channel` *(optional)* | Restricts music commands to a designated text channel (or resets) |
| `/autoleave` | `action`, `minutes` | Configures auto-disconnect when the voice channel is empty (`status`, `enable`, `disable`) |
| `/ping` | *none* | Checks Discord Gateway and Voice connection latency in milliseconds |
| `/status` | *none* | Displays bot uptime, process RAM usage, component versions, and active stats |
| `/logs` | `filter`, `lines` | Displays recent bot logs or error logs (Administrator only) |
| `/help` | *none* | Displays the interactive user guide and command list (also supports `!help`) |

---

## 🛠️ Tech Stack

* **Language:** Python 3.11+
* **Bot Framework:** `discord.py 2.7+` (Cogs, App Commands / Slash Commands, Persistent UI Views)
* **Audio Extraction & Streaming:** `yt-dlp` (with Deno JS engine & proxy routing)
* **Spotify Client:** Asynchronous metadata parser (`aiohttp`)
* **Music Discovery:** `ytmusicapi` (YouTube Music client)
* **Audio Transcoding:** `FFmpeg` (via `discord.FFmpegPCMAudio` & `PCMVolumeTransformer`)
* **Voice Encryption:** `PyNaCl` + `davey` (Discord DAVE E2EE protocol)
* **Containerization:** Docker & Docker Compose

---

## 📂 Project Structure

```text
SubWoofer/
├── cogs/
│   ├── __init__.py             # Cog package initialization
│   └── music.py                # Main music cog, player logic, queue, dashboard & commands
├── deploy/
│   ├── deploy_readme.md        # Step-by-step VPS deployment guide
│   └── subwoofer.service       # Systemd service unit file for Linux VPS
├── docs/
│   ├── dokumentacja.md         # Detailed library and architectural documentation
│   ├── handoff.md              # Developer handoff and onboarding guide
│   └── testy_behawioralne.md   # Behavioral verification test suite
├── .env.example                # Environment variables template
├── .gitignore                  # Git ignore rules
├── Dockerfile                  # Production container definition (Python 3.11 + FFmpeg + Deno + Node.js)
├── docker-compose.yml          # Container orchestration configuration
├── LICENSE                     # GNU General Public License v3.0
├── main.py                     # Bot entrypoint, rotating logger, gateway sync
├── README.md                   # Polish documentation
├── README_EN.md                # English documentation
├── ROADMAP.md                  # Development plans & ideas (P2P / Soulseek streaming)
└── requirements.txt            # Python dependencies
```

---

## ⚡ Quick Start (Local Setup - Windows / Linux / macOS)

### 1. Clone the repository and set up environment
```bash
git clone https://github.com/batorzajac/SubWoofer.git
cd SubWoofer
python -m venv venv
```

Activate the virtual environment:
* **Windows (PowerShell):** `.\venv\Scripts\Activate.ps1`
* **Linux / macOS:** `source venv/bin/activate`

Install dependencies:
```bash
pip install -r requirements.txt
```

### 2. System Requirements (FFmpeg & Deno / Node.js)
* **FFmpeg** (required for audio transcoding):
  * **Windows:** Install via `winget install Gyan.FFmpeg.Essentials` or place `ffmpeg.exe` in the bot root folder.
  * **Linux (Ubuntu/Debian):** `sudo apt update && sudo apt install -y ffmpeg`
* **Deno / Node.js** (required by yt-dlp to solve YouTube JavaScript challenge scripts):
  * **Windows:** `winget install DenoLand.Deno` or [nodejs.org](https://nodejs.org/).
  * **Linux:** `curl -fsSL https://deno.land/install.sh | sh`

### 3. Configure Bot Token
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` and paste your bot token obtained from the [Discord Developer Portal](https://discord.com/developers/applications):
```env
DISCORD_TOKEN=your_bot_token_here
```

### 4. Run the Bot
```bash
python main.py
```

---

## 🐳 Docker Deployment & Hosting (VPS 24/7)

The easiest and most reliable method for 24/7 production hosting on a VPS is Docker:

```bash
docker compose up -d --build
```

View real-time logs:
```bash
docker compose logs -f
```

Stop the bot:
```bash
docker compose down
```

---

## 📄 License

This project is open-source software licensed under the **GNU General Public License v3.0 (GPL-3.0)**. See the [LICENSE](LICENSE) file for details.
