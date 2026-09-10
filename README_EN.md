# SubWoofer - Discord Music Bot 🐶🔊

[🇵🇱 **Polska wersja**](README.md) | [🇬🇧 **English version**](README_EN.md)

---

An advanced, ultra-lightweight, and fully asynchronous music bot for **Discord**, written in **Python 3.10+** utilizing **discord.py**, **yt-dlp**, and **ytmusicapi**. It features high-fidelity audio playback, modern Slash Commands, an interactive Dashboard, per-server queue management with interactive pagination, and age-restriction bypass without requiring YouTube account logins or cookies.

---

## 🚀 Key Features & Capabilities

- **Multi-Platform Audio & Playlist Support:** Play individual tracks as well as full **YouTube / YouTube Music** and **SoundCloud** playlists (up to 500 tracks per queue).
- **Intelligent Lazy Loading:** Playlist imports take only ~2 seconds (metadata extraction only), while the direct audio stream is fetched just-in-time before playback. This prevents URL expiration and avoids YouTube rate-limiting.
- **Hard Queue Limit (500 Songs):** Built-in queue overflow protection – warns users if the queue limit is reached.
- **Age-Restricted Bypass:** Advanced extraction capabilities with `yt-dlp` and `yt-dlp-ejs` (backed by Node.js), enabling playback of 18+ age-restricted content without needing cookies or logins.
- **Interactive Control Dashboard:** Persistent interactive dashboard (`/dashboard on/off`) featuring control buttons (Play/Pause, Skip, Shuffle, Repeat, Stop, Queue, Refresh) that stay responsive even across bot reboots.
- **Queue Pagination:** Compact, clean list showing track numbers and titles with interactive `◀️`, page indicator (`1/4`), `▶️`, and integrated `🔀` shuffle button.
- **Multi-Tier Music Search:** Instant matching and metadata resolution via `ytmusicapi` with an automated fallback to standard `yt-dlp` search.
- **Modern Slash Commands:** Full Discord Application Commands integration with parameter autocomplete and channel restriction support (`/setchannel`).
- **Discord DAVE E2EE Audio Protocol:** Full support for `davey` and `PyNaCl`, adhering to Discord's latest end-to-end encrypted voice architecture.
- **Production Ready:** Pre-configured Docker containerization (`Dockerfile`, `docker-compose.yml`) and Linux `systemd` service files for 24/7 VPS deployment.
- **Comprehensive Logging:** Automated structured event logging to `bot.log` and standard output.

---

## 📋 Available Commands (Slash Commands)

| Command | Parameters | Description |
| :--- | :--- | :--- |
| `/play` | `zapytanie` *(query or URL)* | Searches for a song or extracts a stream/playlist and begins playback or queues it |
| `/pause` | *none* | Pauses the currently playing track |
| `/resume` | *none* | Resumes paused playback |
| `/skip` | *none* | Skips the current track and immediately plays the next song |
| `/skipto` | `pozycja` *(number from 1)* | Immediately jumps to the specified track while preserving the original queue order |
| `/playnext` | `pozycja` *(number from 1)* | Moves the specified track to position 1 so it plays next |
| `/repeat` | *none* | Toggles looping for the entire queue on/off |
| `/shuffle` | *none* | Randomly shuffles all tracks currently in the queue |
| `/stop` | *none* | Stops music, clears the server queue, and disconnects the bot from voice |
| `/queue` | *none* | Displays the interactive paginated queue (10 tracks per page) with shuffle button |
| `/nowplaying` | *none* | Displays details and link of the currently playing track |
| `/dashboard` | `akcja` *(on / off)* | Enables or disables the persistent interactive control dashboard message |
| `/setchannel` | `kanal` *(optional)* | Restricts music commands to a designated text channel (or removes restriction) |

---

## 🛠️ Tech Stack

* **Language:** Python 3.10+
* **Bot Framework:** `discord.py 2.7+` (Cogs, App Commands / Slash Commands, Persistent UI Views)
* **Audio Extraction & Streaming:** `yt-dlp` & `yt-dlp-ejs` (Node.js runtime support)
* **Music Discovery API:** `ytmusicapi` (YouTube Music API client)
* **Audio Transcoding:** `FFmpeg` (via `discord.FFmpegPCMAudio`)
* **Voice Encryption:** `PyNaCl` + `davey` (Discord DAVE E2EE protocol)
* **Configuration:** `python-dotenv`
* **Containerization:** Docker & Docker Compose

---

## 📂 Project Structure

```text
SubWoofer/
├── cogs/
│   ├── __init__.py             # Cog package initialization
│   └── music.py                # Music player, audio logic, queue, dashboard & commands
├── deploy/
│   ├── deploy_readme.md        # Step-by-step VPS deployment guide
│   └── subwoofer.service       # Systemd service unit file for Linux VPS
├── docs/
│   ├── dokumentacja.md         # Detailed library and architectural documentation
│   ├── handoff.md              # Developer handoff and onboarding guide
│   └── testy_behawioralne.md   # Behavioral verification test suite
├── .env.example                # Environment variables template
├── .gitignore                  # Git ignore rules
├── Dockerfile                  # Production container definition (Python 3.11 + FFmpeg + Node.js)
├── docker-compose.yml          # Container orchestration configuration
├── LICENSE                     # GNU General Public License v3.0
├── main.py                     # Bot entrypoint, gateway sync, logger configuration
├── README.md                   # Polish documentation
├── README_EN.md                # English documentation
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

### 2. System Requirements (FFmpeg & Node.js)
* **FFmpeg** (required for audio transcoding):
  * **Windows:** Install via `winget install Gyan.FFmpeg.Essentials` or place `ffmpeg.exe` in the bot root folder.
  * **Linux (Ubuntu/Debian):** `sudo apt update && sudo apt install -y ffmpeg`
* **Node.js** (required by yt-dlp to solve YouTube JavaScript challenge scripts):
  * **Windows:** Install from [nodejs.org](https://nodejs.org/) or via `winget install OpenJS.NodeJS.LTS`.
  * **Linux (Ubuntu/Debian):** `sudo apt install -y nodejs`

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

The easiest and most reliable method for 24/7 production hosting is Docker. It automatically provisions the correct Python, FFmpeg, and Node.js environment:

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
