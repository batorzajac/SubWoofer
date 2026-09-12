import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import logging
import random
import os
import subprocess
import json
import re
import time
import platform
import aiohttp
from typing import Optional
from ytmusicapi import YTMusic

logger = logging.getLogger('musicbot.music_cog')

# Maksymalny limit utworów w kolejce per-serwer
MAX_QUEUE_SIZE = 500

# Inicjalizacja ytmusicapi (do błyskawicznego wyszukiwania w ekosystemie YouTube Music)
ytmusic = YTMusic()

# Opcjonalne proxy (np. lokalne SOCKS5 Cloudflare WARP na VPS) i plik cookies
YTDL_PROXY = os.getenv("YTDL_PROXY")
COOKIE_FILE = os.getenv("COOKIE_FILE", "cookies.txt")

# 1. Konfiguracja do błyskawicznego pobierania metadanych i całych playlist (Lazy Loading)
YTDL_FLAT_OPTIONS = {
    'extract_flat': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

# 2. Konfiguracja do faktycznej ekstrakcji bezpośredniego strumienia audio przed samym odtworzeniem utworu
YTDL_STREAM_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}
if YTDL_PROXY:
    YTDL_FLAT_OPTIONS['proxy'] = YTDL_PROXY
    YTDL_STREAM_OPTIONS['proxy'] = YTDL_PROXY

if os.path.exists(COOKIE_FILE):
    YTDL_FLAT_OPTIONS['cookiefile'] = COOKIE_FILE
    YTDL_STREAM_OPTIONS['cookiefile'] = COOKIE_FILE

# Parametry optymalizujące przerywanie dźwięku w FFmpeg
ffmpeg_before = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
if YTDL_PROXY and YTDL_PROXY.startswith("http"):
    ffmpeg_before = f'-http_proxy {YTDL_PROXY} ' + ffmpeg_before

FFMPEG_OPTIONS = {
    'before_options': ffmpeg_before,
    'options': '-vn'
}

ytdl_flat = yt_dlp.YoutubeDL(YTDL_FLAT_OPTIONS)
ytdl_stream = yt_dlp.YoutubeDL(YTDL_STREAM_OPTIONS)


STATE_FILE = "bot_state.json"


class YTDLStreamAudioSource(discord.AudioSource):
    """
    Strumieniowe źródło audio łączące wyjście procesu yt-dlp (stdout) z wejściem FFmpegPCMAudio.
    Zapewnia natychmiastowe rozpoczęcie odtwarzania, omijanie throttlingu YouTube CDN
    oraz pewne i bezpieczne zwalnianie procesów (brak procesów zombie w systemie).
    """
    def __init__(self, proc: subprocess.Popen, ffmpeg_audio: discord.FFmpegPCMAudio):
        self.proc = proc
        self.ffmpeg_audio = ffmpeg_audio
        self._cleaned = False

    def read(self) -> bytes:
        return self.ffmpeg_audio.read()

    def is_opus(self) -> bool:
        return self.ffmpeg_audio.is_opus()

    def cleanup(self):
        if self._cleaned:
            return
        self._cleaned = True
        try:
            self.ffmpeg_audio.cleanup()
        except Exception as e:
            logger.debug(f"Błąd podczas czyszczenia FFmpegPCMAudio: {e}")
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
        except Exception as e:
            logger.debug(f"Błąd podczas zamykania podprocesu yt-dlp: {e}")



class QueuePaginationView(discord.ui.View):
    """Widok paginacji kolejki z przyciskami przełączania stron (po 10 utworów)."""
    def __init__(self, cog, guild_id: int, page: Optional[int] = None):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id

        queue = self.cog.get_queue(self.guild_id)
        current_idx = self.cog.queue_indices.get(self.guild_id, 0)
        total_pages = max(1, (len(queue) + 9) // 10)

        # Otwieramy kolejkę bezpośrednio na stronie z aktualnie odtwarzanym utworem
        if page is None:
            if 0 <= current_idx < len(queue):
                self.page = current_idx // 10
            else:
                self.page = 0
        else:
            self.page = page

        self.page = min(max(0, self.page), total_pages - 1)
        self.update_buttons()

    def update_buttons(self):
        queue = self.cog.get_queue(self.guild_id)
        total_pages = max(1, (len(queue) + 9) // 10)
        self.prev_btn.disabled = (self.page <= 0)
        self.next_btn.disabled = (self.page >= total_pages - 1)
        self.page_indicator.label = f"{self.page + 1}/{total_pages}"
        self.shuffle_btn.disabled = (len(queue) < 2)

    def build_embed(self) -> discord.Embed:
        queue = self.cog.get_queue(self.guild_id)
        current_idx = self.cog.queue_indices.get(self.guild_id, -1)
        total = len(queue)
        total_pages = max(1, (total + 9) // 10)
        repeat_tag = " [🔁 Repeat]" if self.cog.repeat_mode.get(self.guild_id, False) else ""

        embed = discord.Embed(
            title=f"📜 Kolejka Odtwarzania ({total}/{MAX_QUEUE_SIZE}){repeat_tag}",
            color=discord.Color.dark_purple()
        )

        start_idx = self.page * 10
        end_idx = start_idx + 10
        page_songs = queue[start_idx:end_idx]

        if not page_songs:
            embed.description = "*Kolejka jest pusta.*"
        else:
            lines = []
            for i, song in enumerate(page_songs, start=start_idx):
                num = i + 1
                if i == current_idx:
                    lines.append(f"▶️ **{num}. {song['title']}** *(Teraz odtwarzane)*")
                else:
                    lines.append(f"`{num}.` {song['title']}")
            embed.description = "\n".join(lines)

        embed.set_footer(text=f"Strona {self.page + 1} z {total_pages} • Pozycje {start_idx + 1}-{min(end_idx, total)} z {total}")
        return embed

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = self.cog.get_queue(self.guild_id)
        total_pages = max(1, (len(queue) + 9) // 10)
        if self.page > 0:
            self.page = min(self.page - 1, total_pages - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.primary, disabled=True)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = self.cog.get_queue(self.guild_id)
        total_pages = max(1, (len(queue) + 9) // 10)
        if self.page < total_pages - 1:
            self.page += 1
        else:
            self.page = max(0, total_pages - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary)
    async def shuffle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = self.cog.get_queue(self.guild_id)
        if len(queue) >= 2:
            self.cog.shuffle_queue(self.guild_id)
            logger.info(f"Przelosowano kolejkę z poziomu widoku /queue na serwerze {self.guild_id}")
        self.update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await self.cog.update_dashboard(self.guild_id)

    async def on_timeout(self):
        pass


class SearchSelect(discord.ui.Select):
    def __init__(self, cog, guild_id: int, tracks: list):
        self.cog = cog
        self.guild_id = guild_id
        self.tracks = tracks

        options = []
        for i, t in enumerate(tracks[:5]):
            desc = f"{t.get('uploader', 'YouTube')} • {t.get('duration', 'N/A')}"
            options.append(
                discord.SelectOption(
                    label=t['title'][:100],
                    description=desc[:100],
                    value=str(i),
                    emoji="🎵"
                )
            )
        super().__init__(placeholder="Choose a track to play...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        idx = int(self.values[0])
        selected_track = self.tracks[idx]

        if not interaction.user.voice:
            await interaction.response.send_message("❌ You must join a voice channel!", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if not voice_client:
            await voice_channel.connect()
            voice_client = interaction.guild.voice_client

        queue = self.cog.get_queue(self.guild_id)
        if len(queue) >= MAX_QUEUE_SIZE:
            await interaction.response.send_message(f"❌ Queue is full ({MAX_QUEUE_SIZE} tracks max)!", ephemeral=True)
            return

        song_dict = {
            'title': selected_track['title'],
            'webpage_url': selected_track['url']
        }
        queue.append(song_dict)

        for item in self.view.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"✅ Selected: **{selected_track['title']}**", view=self.view)

        if not voice_client.is_playing() and not voice_client.is_paused():
            if self.cog.queue_indices.get(self.guild_id, -1) == -1 or self.cog.queue_indices.get(self.guild_id, 0) >= len(queue) - 1:
                self.cog.queue_indices[self.guild_id] = len(queue) - 2
            self.cog.play_next(interaction)
            msg = await interaction.followup.send(f"🎵 Now playing: **{selected_track['title']}**")
        else:
            msg = await interaction.followup.send(f"➕ Added to queue: **{selected_track['title']}** (Position: {len(queue)}/{MAX_QUEUE_SIZE})")

        if msg:
            try:
                await msg.delete(delay=300)
            except Exception:
                pass


class SearchView(discord.ui.View):
    def __init__(self, cog, guild_id: int, tracks: list):
        super().__init__(timeout=60)
        self.add_item(SearchSelect(cog, guild_id, tracks))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


def get_help_embed() -> discord.Embed:
    """Tworzy przejrzysty przewodnik i spis komend bota w języku angielskim."""
    embed = discord.Embed(
        title="🎧 SubWoofer — Guide & Commands",
        description=(
            "Welcome to **SubWoofer**! A modern 24/7 Discord music bot with Spotify & YouTube support, "
            "queue up to 500 tracks, auto-disconnect, volume control, and an interactive dashboard!\n\n"
            "**Quick Start:** Join a voice channel and type `/play <song or link>` (supports YouTube, YouTube Music & Spotify)!"
        ),
        color=discord.Color.from_rgb(88, 101, 242)
    )

    embed.add_field(
        name="🎵 Playback & Search",
        value=(
            "• `/play <query>` — Play a song or playlist (YouTube, YT Music, Spotify)\n"
            "• `/search <query>` — Search YouTube and choose from top 5 interactive results\n"
            "• `/nowplaying` — Show info about the currently playing song\n"
            "• `/pause` — Pause playback\n"
            "• `/resume` — Resume playback\n"
            "• `/volume <level>` — Set playback volume (0-100%)"
        ),
        inline=False
    )

    embed.add_field(
        name="📜 Queue Management (up to 500 songs)",
        value=(
            "• `/queue` — View upcoming songs (paginated 10 per page)\n"
            "• `/skip` — Skip the current song\n"
            "• `/skipto <position>` — Jump directly to a track number in queue\n"
            "• `/playnext <position>` — Move a track to the top of the queue\n"
            "• `/shuffle` — Shuffle songs in the queue\n"
            "• `/repeat` — Toggle queue loop\n"
            "• `/stop` — Stop music, clear queue, and disconnect bot"
        ),
        inline=False
    )

    embed.add_field(
        name="🎛️ Dashboard & Server Settings",
        value=(
            "• `/dashboard <action>` — Toggle the interactive player dashboard (on/off)\n"
            "• `/setchannel [channel]` — Restrict bot commands to a specific text channel\n"
            "• `/autoleave <action> [minutes]` — Auto-disconnect when voice channel is empty\n"
            "• `/ping` — Check Discord Gateway & Voice connection latency\n"
            "• `/status` — View system diagnostics, RAM usage, and uptime\n"
            "• `/logs [filter] [lines]` — View recent logs or errors (Admin only)\n"
            "• `/help` — Display this command reference"
        ),
        inline=False
    )

    embed.set_footer(
        text="SubWoofer • 24/7 High-Quality Audio • Click 'Send to DM' below to save this guide"
    )
    return embed



class HelpView(discord.ui.View):
    """Widok pomocy z interaktywnymi przyciskami (wysyłka na PW, link zaproszenia, GitHub)."""
    def __init__(self, embed: discord.Embed):
        super().__init__(timeout=180)
        self.embed = embed

        # Bezpośredni link zaproszenia bota na inne serwery
        invite_url = "https://discord.com/oauth2/authorize?client_id=1539396744234934355&permissions=3148800&scope=bot+applications.commands"
        self.add_item(discord.ui.Button(label="Dodaj bota", url=invite_url, emoji="➕"))
        self.add_item(discord.ui.Button(label="GitHub", url="https://github.com/batorzajac/SubWoofer", emoji="⭐"))

    @discord.ui.button(label="Wyślij na PW", emoji="📩", style=discord.ButtonStyle.primary)
    async def send_dm(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.user.send(embed=self.embed)
            await interaction.response.send_message("✅ Wysłano pełny przewodnik w prywatnej wiadomości!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Nie mogłem wysłać wiadomości prywatnej. Sprawdź swoje ustawienia prywatności na Discordzie.", ephemeral=True)


class MusicDashboardView(discord.ui.View):
    """Interaktywny panel przycisków sterujących dashboardem (Persistent View)."""
    def __init__(self, cog=None, guild_id: Optional[int] = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    def _resolve(self, interaction: discord.Interaction):
        cog = self.cog or interaction.client.get_cog("Music")
        guild_id = self.guild_id or (interaction.guild.id if interaction.guild else None)
        return cog, guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get("custom_id") == "sb_help":
            return True
        if not interaction.user.voice:
            await interaction.response.send_message("❌ Musisz być na kanale głosowym, aby używać przycisków panelu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(emoji="⏯️", label="Pauza / Wznów", style=discord.ButtonStyle.primary, custom_id="sb_play_pause")
    async def play_pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog, guild_id = self._resolve(interaction)
        vc = interaction.guild.voice_client if interaction.guild else None
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Wstrzymano odtwarzanie.", ephemeral=True)
        elif vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Wznowiono odtwarzanie.", ephemeral=True)
        else:
            await interaction.response.send_message("Odtwarzacz jest bezczynny.", ephemeral=True)
        if cog and guild_id:
            await cog.update_dashboard(guild_id)

    @discord.ui.button(emoji="⏭️", label="Pomiń", style=discord.ButtonStyle.secondary, custom_id="sb_skip")
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog, guild_id = self._resolve(interaction)
        vc = interaction.guild.voice_client if interaction.guild else None
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("⏭️ Pominięto utwór.", ephemeral=True)
        else:
            await interaction.response.send_message("Nic aktualnie nie gra.", ephemeral=True)
        if cog and guild_id:
            await cog.update_dashboard(guild_id)

    @discord.ui.button(emoji="🔀", label="Przelosuj", style=discord.ButtonStyle.secondary, custom_id="sb_shuffle")
    async def shuffle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog, guild_id = self._resolve(interaction)
        if not cog or not guild_id:
            await interaction.response.send_message("❌ Błąd stanu bota.", ephemeral=True)
            return
        queue = cog.get_queue(guild_id)
        if len(queue) < 2:
            await interaction.response.send_message("❌ Za mało utworów w kolejce do przelosowania.", ephemeral=True)
            return
        cog.shuffle_queue(guild_id)
        await interaction.response.send_message(f"🔀 Przelosowano kolejność utworów w kolejce!", ephemeral=True)
        await cog.update_dashboard(guild_id)

    @discord.ui.button(emoji="🔁", label="Powtarzaj", style=discord.ButtonStyle.secondary, custom_id="sb_repeat")
    async def repeat_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog, guild_id = self._resolve(interaction)
        if not cog or not guild_id:
            return
        curr = cog.repeat_mode.get(guild_id, False)
        cog.repeat_mode[guild_id] = not curr
        cog.save_state()
        st = "WŁĄCZONE 🔁" if cog.repeat_mode[guild_id] else "WYŁĄCZONE ⏹️"
        await interaction.response.send_message(f"🔁 Powtarzanie całej kolejki: **{st}**", ephemeral=True)
        await cog.update_dashboard(guild_id)

    @discord.ui.button(emoji="🛑", label="Zatrzymaj", style=discord.ButtonStyle.danger, custom_id="sb_stop")
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog, guild_id = self._resolve(interaction)
        vc = interaction.guild.voice_client if interaction.guild else None
        if cog:
            await cog.update_presence(None)
        if vc:
            if cog and guild_id:
                cog.get_queue(guild_id).clear()
                cog.queue_indices[guild_id] = -1
                cog.skip_to_indices.pop(guild_id, None)
                cog.current_song.pop(guild_id, None)
            vc.stop()
            await vc.disconnect()
            await interaction.response.send_message("🛑 Zatrzymano muzykę, wyczyszczono kolejkę i rozłączono bota.", ephemeral=True)
        else:
            await interaction.response.send_message("Bot nie jest połączony z kanałem głosowym.", ephemeral=True)
        if cog and guild_id:
            await cog.update_dashboard(guild_id)

    @discord.ui.button(emoji="📜", label="Kolejka", style=discord.ButtonStyle.secondary, custom_id="sb_queue", row=1)
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog, guild_id = self._resolve(interaction)
        if not cog or not guild_id:
            return
        queue = cog.get_queue(guild_id)
        if not queue:
            repeat_status = " (🔁 Repeat: WŁĄCZONE)" if cog.repeat_mode.get(guild_id, False) else ""
            await interaction.response.send_message(f"📜 Kolejka jest w tej chwili całkowicie pusta.{repeat_status}", ephemeral=True)
            return
        view = QueuePaginationView(cog, guild_id, page=None)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(emoji="🔄", label="Odśwież", style=discord.ButtonStyle.secondary, custom_id="sb_refresh", row=1)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog, guild_id = self._resolve(interaction)
        if cog and guild_id:
            await cog.update_dashboard(guild_id)
        await interaction.response.send_message("🔄 Odświeżono stan panelu.", ephemeral=True)

    @discord.ui.button(emoji="❓", label="Pomoc", style=discord.ButtonStyle.secondary, custom_id="sb_help", row=1)
    async def help_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = get_help_embed()
        view = HelpView(embed)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}             # {guild_id: [{'title': str, 'webpage_url': str}, ...]}
        self.queue_indices = {}      # {guild_id: int} (bieżący indeks w playliście, 0-based)
        self.skip_to_indices = {}    # {guild_id: int} (docelowy indeks dla /skipto)
        self.current_song = {}       # {guild_id: dict}
        self.repeat_mode = {}        # {guild_id: bool}
        self.music_channels = {}     # {guild_id: int (channel_id)}
        self.dashboards = {}         # {guild_id: discord.Message}
        self.dashboard_metadata = {} # {guild_id: {'channel_id': int, 'message_id': int}}
        self.guild_volumes = {}      # {guild_id: int (0-100)}
        self.auto_leave_config = {}  # {guild_id: {'enabled': bool, 'minutes': int}}
        self.auto_leave_tasks = {}   # {guild_id: asyncio.Task}
        self.load_state()

    async def cog_load(self):
        # Trwałe przyciski panelu działające nawet po restartach bota
        self.bot.add_view(MusicDashboardView(self))

    def load_state(self):
        """Wczytuje zapisany stan kanałów, dashboardów, głośności, repeat i konfiguracji z pliku."""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.music_channels = {int(k): v for k, v in data.get("music_channels", {}).items()}
                    self.dashboard_metadata = {int(k): v for k, v in data.get("dashboards", {}).items()}
                    self.guild_volumes = {int(k): v for k, v in data.get("guild_volumes", {}).items()}
                    self.auto_leave_config = {int(k): v for k, v in data.get("auto_leave_config", {}).items()}
                    self.repeat_mode = {int(k): v for k, v in data.get("repeat_mode", {}).items()}
                    logger.info("Wczytano zapisany stan dashboardów, ograniczeń kanałów, głośności, repeat i auto-leave.")
        except Exception as e:
            logger.warning(f"Nie udało się wczytać stanu z {STATE_FILE}: {e}")

    def save_state(self):
        """Zapisuje bieżący stan kanałów, dashboardów, głośności, repeat i konfiguracji do pliku."""
        try:
            data = {
                "music_channels": {str(k): v for k, v in self.music_channels.items()},
                "dashboards": {str(k): v for k, v in self.dashboard_metadata.items()},
                "guild_volumes": {str(k): v for k, v in self.guild_volumes.items()},
                "auto_leave_config": {str(k): v for k, v in self.auto_leave_config.items()},
                "repeat_mode": {str(k): v for k, v in self.repeat_mode.items()}
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Nie udało się zapisać stanu do {STATE_FILE}: {e}")

    async def get_dashboard_message(self, guild_id: int) -> Optional[discord.Message]:
        """Zwraca obiekt wiadomości dashboardu (z pamięci lub pobierając z Discord API)."""
        if guild_id in self.dashboards:
            return self.dashboards[guild_id]
        meta = self.dashboard_metadata.get(guild_id)
        if meta:
            channel = self.bot.get_channel(meta.get("channel_id"))
            if channel:
                try:
                    msg = await channel.fetch_message(meta.get("message_id"))
                    self.dashboards[guild_id] = msg
                    return msg
                except Exception:
                    self.dashboard_metadata.pop(guild_id, None)
                    self.save_state()
        return None

    def get_queue(self, guild_id: int):
        """Pobiera (lub tworzy, jeśli brak) kolejkę dla danego serwera."""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    def shuffle_queue(self, guild_id: int):
        """Przelosowuje kolejkę z zachowaniem aktualnie odtwarzanego utworu na bieżącej pozycji."""
        queue = self.get_queue(guild_id)
        if len(queue) < 2:
            return
        current_idx = self.queue_indices.get(guild_id, 0)
        if 0 <= current_idx < len(queue):
            current_song = queue[current_idx]
            other_songs = [s for i, s in enumerate(queue) if i != current_idx]
            random.shuffle(other_songs)
            queue.clear()
            queue.append(current_song)
            queue.extend(other_songs)
            self.queue_indices[guild_id] = 0
        else:
            random.shuffle(queue)
            self.queue_indices[guild_id] = 0

    def generate_dashboard_embed(self, guild_id: int) -> discord.Embed:
        """Tworzy estetyczny Embed reprezentujący aktualny stan bota dla dashboardu."""
        guild = self.bot.get_guild(guild_id)
        vc = guild.voice_client if guild else None
        song = self.current_song.get(guild_id)
        queue = self.get_queue(guild_id)
        repeat = self.repeat_mode.get(guild_id, False)

        embed = discord.Embed(
            title="🐶 SubWoofer",
            color=discord.Color.blue() if (vc and vc.is_playing()) else discord.Color.dark_grey()
        )

        if song:
            link = song.get('webpage_url', '')
            title_text = f"[{song['title']}]({link})" if link else song['title']
            embed.add_field(name="🎶 Aktualnie Odtwarzane", value=title_text, inline=False)
        else:
            embed.add_field(name="🎶 Aktualnie Odtwarzane", value="*Brak — odtwarzacz jest bezczynny*", inline=False)

        if vc and vc.is_playing():
            status = "Odtwarzanie ▶️"
        elif vc and vc.is_paused():
            status = "Wstrzymano ⏸️"
        elif vc and vc.is_connected():
            status = "Połączony (oczekiwanie) ⏳"
        else:
            status = "Rozłączony ⏹️"

        current_idx = self.queue_indices.get(guild_id, -1)
        if 0 <= current_idx < len(queue):
            queue_str = f"{current_idx + 1}/{len(queue)}"
        else:
            queue_str = f"{len(queue)}/{MAX_QUEUE_SIZE}"

        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="W kolejce", value=queue_str, inline=True)
        embed.add_field(name="Zapętlenie", value="Włączone 🔁" if repeat else "Wyłączone ⏹️", inline=True)
        embed.set_footer(text="Steruj przyciskami poniżej lub używaj komend slash (/play, /skip itd.)")
        return embed

    async def update_dashboard(self, guild_id: int):
        """Aktualizuje wiadomość z dashboardem na danym serwerze, jeśli istnieje."""
        msg = await self.get_dashboard_message(guild_id)
        if not msg:
            return
        try:
            embed = self.generate_dashboard_embed(guild_id)
            view = MusicDashboardView(self, guild_id)
            await msg.edit(embed=embed, view=view)
        except (discord.NotFound, discord.HTTPException) as e:
            logger.warning(f"Nie udało się zaktualizować dashboardu na serwerze {guild_id}: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        """Po zalogowaniu czyści status obecności i odświeża zapisane panele dashboardów."""
        is_playing = any(vc.is_playing() for vc in self.bot.voice_clients)
        if not is_playing:
            await self.update_presence(None)
            logger.info("Pomyślnie zresetowano status obecności bota po starcie.")

        for guild_id in list(self.dashboard_metadata.keys()):
            await self.update_dashboard(guild_id)

    async def update_presence(self, song_title: Optional[str] = None):
        """Aktualizuje status profilu bota (Discord Presence) lub czyści go po zakończeniu grania."""
        try:
            if song_title:
                activity = discord.Activity(
                    type=discord.ActivityType.listening,
                    name=song_title[:128]
                )
                await self.bot.change_presence(activity=activity, status=discord.Status.online)
            else:
                await self.bot.change_presence(activity=None, status=discord.Status.online)
        except Exception as e:
            logger.warning(f"Błąd aktualizacji Discord Presence: {e}")

    async def check_channel(self, interaction: discord.Interaction) -> bool:
        """Weryfikuje, czy komenda została wpisana na dozwolonym kanale tekstowym."""
        allowed_id = self.music_channels.get(interaction.guild.id)
        if allowed_id and interaction.channel.id != allowed_id:
            allowed_channel = interaction.guild.get_channel(allowed_id)
            ch_name = allowed_channel.mention if allowed_channel else "dedykowanym kanale"
            await interaction.response.send_message(
                f"❌ Komendy muzyczne są dozwolone tylko na kanale {ch_name}!",
                ephemeral=True
            )
            return False
        return True

    def create_ytdl_process(self, webpage_url: str) -> subprocess.Popen:
        """Uruchamia podproces yt-dlp wyprowadzający bezpośredni strumień audio na standardowe wyjście (stdout)."""
        cmd = [
            'yt-dlp',
            '-f', 'bestaudio/best',
            '-o', '-',
            '--quiet',
            '--no-warnings',
        ]
        if YTDL_PROXY:
            cmd.extend(['--proxy', YTDL_PROXY])
        if os.path.exists(COOKIE_FILE):
            cmd.extend(['--cookies', COOKIE_FILE])

        cmd.append(webpage_url)

        creationflags = 0
        if platform.system() == "Windows":
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )

    async def get_stream_url(self, webpage_url: str):
        """Wyciąga świeży bezpośredni link audio tuż przed startem odtwarzania (Lazy Loading)."""
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl_stream.extract_info(webpage_url, download=False))
            if 'entries' in data and data['entries']:
                data = data['entries'][0]
            stream_url = data.get('url')
            if not stream_url and 'formats' in data:
                for f in reversed(data['formats']):
                    if f.get('acodec') != 'none' and f.get('url'):
                        stream_url = f['url']
                        break
            return stream_url
        except Exception as e:
            logger.error(f"Błąd ekstrakcji strumienia audio dla {webpage_url}: {e}")
            return None

    async def extract_spotify_info(self, url: str):
        """Pobiera metadane utworów lub playlist ze Spotify bez potrzeby kluczy API."""
        match = re.search(r'spotify\.com/(?:[a-z]{2,4}-[a-z]{2,4}/)?(track|playlist|album)/([a-zA-Z0-9]+)', url)
        if not match:
            return False, [], None
        item_type, item_id = match.group(1), match.group(2)
        embed_url = f"https://open.spotify.com/embed/{item_type}/{item_id}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(embed_url, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.warning(f"Spotify embed zwrócił status {resp.status} dla {url}")
                        return False, [], None
                    html = await resp.text()

            next_data = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
            if not next_data:
                logger.warning(f"Nie znaleziono danych __NEXT_DATA__ w Spotify embed dla {url}")
                return False, [], None

            parsed = json.loads(next_data.group(1))
            entity = parsed.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
            if not entity:
                return False, [], None

            if item_type == 'track':
                title = entity.get('name', 'Unknown Track')
                artists_list = entity.get('artists', [])
                artists = ', '.join([a.get('name', '') for a in artists_list if a.get('name')])
                full_title = f"{title} - {artists}" if artists else title
                q = f"{title} {artists}".strip()
                logger.info(f"Rozpoznano utwór Spotify: '{full_title}'")
                return False, [{'title': full_title, 'webpage_url': f"ytsearch1:{q}"}], None

            elif item_type in ('playlist', 'album'):
                p_title = entity.get('title') or entity.get('name') or ('Spotify Playlist' if item_type == 'playlist' else 'Spotify Album')
                track_list = entity.get('trackList', [])
                songs = []
                for t in track_list:
                    if not t:
                        continue
                    t_name = t.get('title', 'Unknown Track')
                    t_sub = t.get('subtitle', '')
                    full_name = f"{t_name} - {t_sub}" if t_sub else t_name
                    q = f"{t_name} {t_sub}".strip()
                    songs.append({'title': full_name, 'webpage_url': f"ytsearch1:{q}"})

                logger.info(f"Rozpoznano {item_type} Spotify: '{p_title}' z {len(songs)} utworami.")
                return True, songs, p_title

        except Exception as e:
            logger.error(f"Błąd podczas parsowania linku Spotify {url}: {e}")
            return False, [], None

        return False, [], None

    async def search_items(self, query: str):
        """
        Wyszukuje pojedynczy utwór lub playlistę w trybie leniwym (Lazy Loading).
        Zwraca: (is_playlist: bool, songs: list[dict], playlist_title: Optional[str])
        """
        loop = asyncio.get_event_loop()
        logger.info(f"Rozpoczynam wyszukiwanie/ekstrakcję dla: {query}")

        # 0. Przypadek: Link Spotify
        if "spotify.com" in query:
            is_pl, sp_songs, sp_title = await self.extract_spotify_info(query)
            if sp_songs:
                return is_pl, sp_songs, sp_title

        # 1. Przypadek: Link bezpośredni (YouTube, YouTube Music, SoundCloud itp.)
        if query.startswith(('http://', 'https://')):
            try:
                data = await loop.run_in_executor(None, lambda: ytdl_flat.extract_info(query, download=False))
                entries = data.get('entries')
                if data.get('_type') == 'playlist' or (entries and len(entries) > 1):
                    playlist_title = data.get('title', 'Playlista')
                    songs = []
                    for entry in entries:
                        if not entry:
                            continue
                        song_title = entry.get('title') or 'Nieznany utwór'
                        song_url = entry.get('url')
                        if song_url and not song_url.startswith('http'):
                            song_url = f"https://www.youtube.com/watch?v={song_url}"
                        songs.append({
                            'title': song_title,
                            'webpage_url': song_url or query
                        })
                    logger.info(f"Znaleziono playlistę: '{playlist_title}' z {len(songs)} utworami.")
                    return True, songs, playlist_title

                if entries and len(entries) == 1:
                    single = entries[0]
                    song_title = single.get('title') or data.get('title') or 'Utwór z linku'
                    song_url = single.get('url') or query
                    if song_url and not song_url.startswith('http'):
                        song_url = f"https://www.youtube.com/watch?v={song_url}"
                else:
                    song_title = data.get('title', 'Utwór z linku')
                    song_url = query

                return False, [{'title': song_title, 'webpage_url': song_url}], None

            except Exception as e:
                logger.error(f"Błąd ekstrakcji linku {query}: {e}")
                return False, [], None

        # 2. Przypadek: Wyszukiwanie tekstowe (YouTube Music)
        try:
            search_results = ytmusic.search(query, filter="songs")
            if search_results and 'videoId' in search_results[0]:
                top_result = search_results[0]
                video_id = top_result['videoId']
                artist_name = top_result.get('artists', [{}])[0].get('name', '')
                title = f"{artist_name} - {top_result['title']}" if artist_name else top_result['title']
                yt_url = f"https://music.youtube.com/watch?v={video_id}"
                return False, [{'title': title, 'webpage_url': yt_url}], None
        except Exception as e:
            logger.warning(f"Błąd wyszukiwania w ytmusicapi: {e}")

        # Fallback do ogólnego wyszukiwania yt-dlp
        try:
            data = await loop.run_in_executor(None, lambda: ytdl_flat.extract_info(f"ytsearch:{query}", download=False))
            if 'entries' in data and data['entries']:
                entry = data['entries'][0]
                title = entry.get('title', query)
                song_url = entry.get('url')
                if song_url and not song_url.startswith('http'):
                    song_url = f"https://www.youtube.com/watch?v={song_url}"
                return False, [{'title': title, 'webpage_url': song_url or query}], None
        except Exception as e:
            logger.error(f"Błąd fallbacku ytsearch: {e}")

        return False, [], None

    def play_next(self, interaction: discord.Interaction):
        """Synchroniczny punkt wywołania z callbacku after; zleca asynchroniczne odtworzenie."""
        coro = self._play_next_async(interaction)
        asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    async def _play_next_async(self, interaction: discord.Interaction):
        """Asynchroniczne pobranie strumienia i odtworzenie kolejnego utworu w stałej playliście."""
        guild_id = interaction.guild.id
        queue = self.get_queue(guild_id)
        voice_client = interaction.guild.voice_client

        if not voice_client or not voice_client.is_connected():
            logger.warning(f"Zażądano _play_next_async, ale brak VoiceClienta na serwerze {guild_id}")
            await self.update_presence(None)
            await self.update_dashboard(guild_id)
            return

        # Jeśli kolejka jest całkowicie pusta
        if not queue:
            self.current_song.pop(guild_id, None)
            self.queue_indices[guild_id] = -1
            logger.info(f"Kolejka odtwarzania na serwerze {guild_id} jest pusta.")
            await self.update_presence(None)
            await self.update_dashboard(guild_id)
            
            # Jeśli repeat nie jest włączony -> automatyczne rozłączenie z kanału głosowego
            if not self.repeat_mode.get(guild_id, False):
                if voice_client.is_connected():
                    await voice_client.disconnect()
                    logger.info(f"SubWoofer opuścił kanał po zakończeniu odtwarzania kolejki (G:{guild_id}).")
            return

        # Wyznaczamy indeks kolejnego utworu
        if guild_id in self.skip_to_indices:
            next_index = self.skip_to_indices.pop(guild_id)
        else:
            current_idx = self.queue_indices.get(guild_id, -1)
            next_index = current_idx + 1

        # Sprawdzamy czy osiągnęliśmy koniec playlisty
        if next_index >= len(queue):
            if self.repeat_mode.get(guild_id, False):
                next_index = 0
                logger.info(f"Osiągnięto koniec playlisty na serwerze {guild_id}. Zapętlenie aktywne: powrót do utworu #1.")
            else:
                self.current_song.pop(guild_id, None)
                self.queue_indices[guild_id] = -1
                logger.info(f"Kolejka odtwarzania na serwerze {guild_id} dobiegła końca.")
                await self.update_presence(None)
                await self.update_dashboard(guild_id)
                if voice_client.is_connected():
                    await voice_client.disconnect()
                    logger.info(f"SubWoofer opuścił kanał po zakończeniu kolejki (G:{guild_id}).")
                return

        if next_index < 0 or next_index >= len(queue):
            next_index = 0

        self.queue_indices[guild_id] = next_index
        song = queue[next_index]
        self.current_song[guild_id] = song

        # LAZY LOADING + DIRECT PIPE STREAMING (yt-dlp -> stdout -> FFmpeg stdin):
        # Pobieramy strumień w czasie rzeczywistym przez potok systemowy w pamięci RAM.
        # Eliminuje to opóźnienie pobierania całego pliku, zrywanie połączeń i throttling YouTube CDN.
        loop = asyncio.get_event_loop()
        try:
            logger.info(f"Rozpoczynam odtwarzanie utworu (potok yt-dlp -> FFmpeg): [{next_index + 1}/{len(queue)}] {song['title']} (Serwer: {guild_id})")
            proc = await loop.run_in_executor(None, lambda: self.create_ytdl_process(song['webpage_url']))
            raw_audio = discord.FFmpegPCMAudio(proc.stdout, pipe=True, options='-vn')
            stream_source = YTDLStreamAudioSource(proc, raw_audio)

            vol = self.guild_volumes.get(guild_id, 100) / 100.0
            source = discord.PCMVolumeTransformer(stream_source, volume=vol)

            def after_playing(error):
                if error:
                    logger.error(f"Błąd odtwarzacza podczas odtwarzania utworu: {error}")
                self.play_next(interaction)

            voice_client.play(source, after=after_playing)
            
            # Ciche odtwarzanie + Discord Presence (Słucha: Tytuł piosenki) + Dashboard
            await self.update_presence(song['title'])
            await self.update_dashboard(guild_id)

        except Exception as e:
            logger.error(f"Wystąpił błąd podczas startu odtwarzania na serwerze {guild_id}: {e}")
            if not self.repeat_mode.get(guild_id, False) and (next_index + 1 >= len(queue)):
                if voice_client.is_connected():
                    await voice_client.disconnect()
                await self.update_presence(None)
                await self.update_dashboard(guild_id)
                return
            self.play_next(interaction)
    # ==========================================
    # SYSTEM AUTO-DISCONNECT PRZY PUSTYM KANALE
    # ==========================================

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        vc = guild.voice_client
        if not vc or not vc.channel:
            return

        # Przypadek 1: Bot sam został rozłączony z kanału
        if member.id == self.bot.user.id:
            if not after.channel:
                guild_id = guild.id
                if guild_id in self.auto_leave_tasks:
                    self.auto_leave_tasks[guild_id].cancel()
                    self.auto_leave_tasks.pop(guild_id, None)
                self.current_song.pop(guild_id, None)
                self.get_queue(guild_id).clear()
                self.queue_indices[guild_id] = -1
                self.skip_to_indices.pop(guild_id, None)
                await self.update_presence(None)
                await self.update_dashboard(guild_id)
                logger.info(f"Bot został odłączony z kanału na serwerze {guild.id}. Stan wyczyszczony.")
            return

        # Przypadek 2: Sprawdzamy czy na kanale bota są jeszcze ludzie
        bot_channel = vc.channel
        human_members = [m for m in bot_channel.members if not m.bot]
        cfg = self.auto_leave_config.get(guild.id, {'enabled': True, 'minutes': 10})

        if not human_members:
            if cfg.get('enabled', True):
                minutes = cfg.get('minutes', 10)
                if guild.id not in self.auto_leave_tasks or self.auto_leave_tasks[guild.id].done():
                    logger.info(f"Kanał #{bot_channel.name} opustoszał. Zaplanowano auto-leave za {minutes} min (G:{guild.id}).")
                    self.auto_leave_tasks[guild_id] = asyncio.create_task(self._auto_leave_timer(guild.id, minutes * 60))
        else:
            if guild.id in self.auto_leave_tasks and not self.auto_leave_tasks[guild.id].done():
                self.auto_leave_tasks[guild.id].cancel()
                self.auto_leave_tasks.pop(guild_id, None)
                logger.info(f"Użytkownik dołączył do #{bot_channel.name}. Anulowano timer auto-leave (G:{guild.id}).")

    async def _auto_leave_timer(self, guild_id: int, delay_seconds: int):
        try:
            await asyncio.sleep(delay_seconds)
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return
            vc = guild.voice_client
            if not vc or not vc.channel:
                return
            human_members = [m for m in vc.channel.members if not m.bot]
            if not human_members:
                logger.info(f"Auto-disconnect: kanał był pusty przez {delay_seconds // 60} min (G:{guild_id}). Rozłączam.")
                if vc.is_playing() or vc.is_paused():
                    vc.stop()
                if vc.is_connected():
                    await vc.disconnect()
                self.current_song.pop(guild_id, None)
                self.get_queue(guild_id).clear()
                self.queue_indices[guild_id] = -1
                self.skip_to_indices.pop(guild_id, None)
                await self.update_presence(None)
                await self.update_dashboard(guild_id)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Błąd w _auto_leave_timer dla serwera {guild_id}: {e}")
        finally:
            self.auto_leave_tasks.pop(guild_id, None)

    # ==========================================
    # DISCORD SLASH COMMANDS (ALL IN ENGLISH)
    # ==========================================

    @app_commands.command(name="play", description="Play a song or playlist (YouTube, YouTube Music, or Spotify)")
    @app_commands.describe(query="Song title, search keywords, or URL (YouTube / Spotify)")
    async def play(self, interaction: discord.Interaction, query: str):
        if not await self.check_channel(interaction):
            return

        logger.info(f"Użytkownik {interaction.user} (G:{interaction.guild.id}) żąda /play [{query}]")

        if not interaction.user.voice:
            await interaction.response.send_message("❌ Musisz dołączyć do kanału głosowego!", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if not voice_client:
            await voice_channel.connect()
            voice_client = interaction.guild.voice_client
            logger.info(f"Dołączono do kanału {voice_channel.name} (G:{interaction.guild.id})")

        queue = self.get_queue(interaction.guild.id)

        # Weryfikacja twardego limitu 500 utworów
        if len(queue) >= MAX_QUEUE_SIZE:
            await interaction.response.send_message(
                f"❌ **Przekroczono limit kolejki!** W kolejce znajduje się już maksymalna dopuszczalna liczba utworów ({MAX_QUEUE_SIZE}). Poczekaj, aż część utworów zostanie odtworzona.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        is_playlist, songs, playlist_title = await self.search_items(query)
        if not songs:
            logger.error(f"Nie udało się odnaleźć muzyki dla zapytania '{query}' (G:{interaction.guild.id})")
            err_msg = await interaction.followup.send("❌ Nie znaleziono utworu/playlisty lub wystąpił błąd przy pobieraniu.")
            if err_msg:
                try:
                    await err_msg.delete(delay=30)
                except Exception:
                    pass
            return

        current_len = len(queue)
        available_slots = MAX_QUEUE_SIZE - current_len

        sent_msg = None
        try:
            if is_playlist:
                total_playlist_songs = len(songs)
                if total_playlist_songs > available_slots:
                    songs_to_add = songs[:available_slots]
                    queue.extend(songs_to_add)
                    sent_msg = await interaction.followup.send(
                        f"⚠️ **Dodano {len(songs_to_add)} utworów z playlisty '{playlist_title}'!**\n"
                        f"Osiągnięto limit **{MAX_QUEUE_SIZE}** utworów w kolejce (pominięto {total_playlist_songs - available_slots} nadmiarowych utworów)."
                    )
                else:
                    queue.extend(songs)
                    sent_msg = await interaction.followup.send(
                        f"📑 **Dodano playlistę:** `{playlist_title}` ({len(songs)} utworów) do kolejki! 🎶 (Łącznie w kolejce: {len(queue)}/{MAX_QUEUE_SIZE})"
                    )
            else:
                song = songs[0]
                queue.append(song)
                if not voice_client.is_playing() and not voice_client.is_paused():
                    sent_msg = await interaction.followup.send(f"🎵 Załadowano: **{song['title']}**...")
                else:
                    sent_msg = await interaction.followup.send(f"➕ Dodano do kolejki: **{song['title']}** (Pozycja: {len(queue)}/{MAX_QUEUE_SIZE})")

            if sent_msg:
                await sent_msg.delete(delay=300)
        except Exception as e:
            logger.error(f"Błąd podczas wysyłania wiadomości w /play: {e}")

        await self.update_dashboard(interaction.guild.id)

        if not voice_client.is_playing() and not voice_client.is_paused():
            if self.queue_indices.get(interaction.guild.id, -1) == -1 or self.queue_indices.get(interaction.guild.id, 0) >= current_len:
                self.queue_indices[interaction.guild.id] = current_len - 1
            self.play_next(interaction)

    @app_commands.command(name="search", description="Search YouTube and choose from top 5 interactive results")
    @app_commands.describe(query="Song title or search keywords")
    async def search(self, interaction: discord.Interaction, query: str):
        if not await self.check_channel(interaction):
            return

        if not interaction.user.voice:
            await interaction.response.send_message("❌ Musisz dołączyć do kanału głosowego!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        loop = asyncio.get_event_loop()
        raw_entries = []
        try:
            data = await loop.run_in_executor(None, lambda: ytdl_flat.extract_info(f"ytsearch15:{query}", download=False))
            raw_entries = data.get('entries', []) if data else []
        except Exception as e:
            logger.error(f"Błąd w /search dla '{query}': {e}")
            raw_entries = []

        # Filtrujemy wyniki, aby pominąć kanały i playlisty (szukamy wyłącznie pojedynczych filmów i utworów muzycznych)
        entries = []
        for e in raw_entries:
            if not e:
                continue
            # Odrzucamy playlisty i kanały
            if e.get('_type') in ('playlist', 'multi_video'):
                continue
            if e.get('ie_key') not in ('Youtube', None):
                continue
            item_id = str(e.get('id', ''))
            if item_id.startswith(('UC', 'PL')):
                continue
            if e.get('duration') is None:
                continue
            entries.append(e)
            if len(entries) >= 5:
                break

        tracks = []
        for e in entries:
            title = e.get('title', 'Nieznany utwór')
            url = e.get('url') or e.get('webpage_url')
            if url and not url.startswith('http'):
                url = f"https://www.youtube.com/watch?v={url}"
            dur_sec = e.get('duration')
            if dur_sec:
                m, s = divmod(int(dur_sec), 60)
                dur_str = f"{m}:{s:02d}"
            else:
                dur_str = "N/A"
            uploader = e.get('uploader') or e.get('channel') or "YouTube"
            tracks.append({'title': title, 'url': url or f"ytsearch1:{query}", 'duration': dur_str, 'uploader': uploader})

        # Fallback do YouTube Music (utwory), jeśli yt-dlp nie zwrócił żadnych pojedynczych filmów
        if not tracks:
            try:
                music_results = ytmusic.search(query, filter="songs")
                for r in music_results[:5]:
                    if not r or 'videoId' not in r:
                        continue
                    v_id = r['videoId']
                    v_title = r.get('title', 'Nieznany utwór')
                    artists_list = r.get('artists', [{}])
                    artist_str = artists_list[0].get('name', '') if artists_list else ''
                    full_t = f"{artist_str} - {v_title}" if artist_str else v_title
                    dur_str = r.get('duration', 'N/A')
                    tracks.append({
                        'title': full_t,
                        'url': f"https://music.youtube.com/watch?v={v_id}",
                        'duration': dur_str,
                        'uploader': artist_str or "YouTube Music"
                    })
            except Exception as e:
                logger.warning(f"Błąd fallbacku ytmusic w /search: {e}")

        if not tracks:
            await interaction.followup.send(f"❌ Nie znaleziono filmów ani utworów dla zapytania `{query}`.", ephemeral=True)
            return

        view = SearchView(self, interaction.guild.id, tracks)
        await interaction.followup.send(f"🔍 **Wyniki wyszukiwania dla:** `{query}`\nWybierz utwór z listy poniżej:", view=view, ephemeral=True)

    @app_commands.command(name="volume", description="Adjust playback volume (0-100%)")
    @app_commands.describe(level="Volume percentage from 0 to 100")
    async def volume(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]):
        if not await self.check_channel(interaction):
            return

        guild_id = interaction.guild.id
        self.guild_volumes[guild_id] = level
        self.save_state()

        vc = interaction.guild.voice_client
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = level / 100.0

        await interaction.response.send_message(f"🔊 Głośność odtwarzacza została ustawiona na **{level}%**.", ephemeral=True)

    @app_commands.command(name="repeat", description="Toggle loop mode for the current playlist")
    async def repeat(self, interaction: discord.Interaction):
        if not await self.check_channel(interaction):
            return

        guild_id = interaction.guild.id
        current = self.repeat_mode.get(guild_id, False)
        self.repeat_mode[guild_id] = not current
        self.save_state()
        status = "WŁĄCZONE 🔁" if self.repeat_mode[guild_id] else "WYŁĄCZONE ⏹️"
        logger.info(f"Użytkownik {interaction.user} zmienił repeat na: {status} (G:{guild_id})")
        await interaction.response.send_message(f"🔁 Powtarzanie całej kolejki: **{status}**", ephemeral=True)
        await self.update_dashboard(guild_id)

    @app_commands.command(name="shuffle", description="Randomly shuffle the upcoming songs in the queue")
    async def shuffle(self, interaction: discord.Interaction):
        if not await self.check_channel(interaction):
            return

        queue = self.get_queue(interaction.guild.id)
        if len(queue) < 2:
            await interaction.response.send_message("❌ Za mało utworów w kolejce, aby przelosować (minimum 2).", ephemeral=True)
            return

        self.shuffle_queue(interaction.guild.id)
        logger.info(f"Użytkownik {interaction.user} przelosował kolejkę (G:{interaction.guild.id})")
        await interaction.response.send_message(f"🔀 Przelosowano kolejność utworów w kolejce!", ephemeral=True)
        await self.update_dashboard(interaction.guild.id)

    @app_commands.command(name="skipto", description="Skip directly to a specific track number in the queue")
    @app_commands.describe(position="Track number in queue to jump to (from 1)")
    async def skipto(self, interaction: discord.Interaction, position: int):
        if not await self.check_channel(interaction):
            return

        queue = self.get_queue(interaction.guild.id)
        if position < 1 or position > len(queue):
            await interaction.response.send_message(
                f"❌ Nieprawidłowy numer! Podaj pozycję od 1 do {len(queue)}.",
                ephemeral=True
            )
            return

        target_song = queue[position - 1]
        self.skip_to_indices[interaction.guild.id] = position - 1

        voice_client = interaction.guild.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            logger.info(f"Użytkownik {interaction.user} użył skipto {position}: {target_song['title']} (G:{interaction.guild.id})")
            voice_client.stop()
            await interaction.response.send_message(
                f"⏭️ Przeskoczono do utworu **{position}. {target_song['title']}**.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("Bot nie odtwarza obecnie muzyki.", ephemeral=True)

        await self.update_dashboard(interaction.guild.id)

    @app_commands.command(name="playnext", description="Move a track from the queue to play next")
    @app_commands.describe(position="Track number in queue to move to the front (from 1)")
    async def playnext(self, interaction: discord.Interaction, position: int):
        if not await self.check_channel(interaction):
            return

        queue = self.get_queue(interaction.guild.id)
        if position < 1 or position > len(queue):
            await interaction.response.send_message(
                f"❌ Nieprawidłowy numer! Podaj pozycję od 1 do {len(queue)}.",
                ephemeral=True
            )
            return

        current_idx = self.queue_indices.get(interaction.guild.id, 0)
        target_idx = position - 1
        if target_idx == current_idx:
            await interaction.response.send_message("Ten utwór jest właśnie odtwarzany!", ephemeral=True)
            return

        song = queue.pop(target_idx)
        if target_idx < current_idx:
            current_idx -= 1
            self.queue_indices[interaction.guild.id] = current_idx

        insert_pos = current_idx + 1
        queue.insert(insert_pos, song)

        logger.info(f"Użytkownik {interaction.user} ustawił utwór jako następny: {song['title']} (G:{interaction.guild.id})")
        await interaction.response.send_message(f"⏩ Utwór **{song['title']}** zagra teraz jako następny w kolejce (Pozycja {insert_pos + 1})!", ephemeral=True)
        await self.update_dashboard(interaction.guild.id)

    @app_commands.command(name="stop", description="Stop music, clear queue, and disconnect bot")
    async def stop(self, interaction: discord.Interaction):
        if not await self.check_channel(interaction):
            return

        logger.info(f"Wywołano /stop przez {interaction.user} (G:{interaction.guild.id})")
        voice_client = interaction.guild.voice_client

        await self.update_presence(None)

        if voice_client:
            self.get_queue(interaction.guild.id).clear()
            self.queue_indices[interaction.guild.id] = -1
            self.skip_to_indices.pop(interaction.guild.id, None)
            self.current_song.pop(interaction.guild.id, None)
            voice_client.stop()
            await voice_client.disconnect()
            logger.info(f"Oczyszczono kolejkę i rozłączono kanał na (G:{interaction.guild.id})")
            await interaction.response.send_message("🛑 Zatrzymano muzykę i wyczyszczono kolejkę. Bot opuścił kanał.", ephemeral=True)
        else:
            await interaction.response.send_message("Bot aktualnie nie odtwarza muzyki na żadnym kanale głosowym.", ephemeral=True)

        await self.update_dashboard(interaction.guild.id)

    @app_commands.command(name="skip", description="Skip the currently playing song")
    async def skip(self, interaction: discord.Interaction):
        if not await self.check_channel(interaction):
            return

        logger.info(f"Wywołano /skip przez {interaction.user} (G:{interaction.guild.id})")
        voice_client = interaction.guild.voice_client

        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await interaction.response.send_message("⏭️ Pomyślnie pominięto utwór.", ephemeral=True)
        else:
            await interaction.response.send_message("Obecnie nie odtwarzam żadnego utworu.", ephemeral=True)

        await self.update_dashboard(interaction.guild.id)

    @app_commands.command(name="queue", description="Display the current song queue (up to 500 tracks)")
    async def queue(self, interaction: discord.Interaction):
        if not await self.check_channel(interaction):
            return

        logger.info(f"Wywołano /queue przez {interaction.user} (G:{interaction.guild.id})")
        queue = self.get_queue(interaction.guild.id)

        if not queue:
            repeat_status = " (🔁 Repeat: WŁĄCZONE)" if self.repeat_mode.get(interaction.guild.id, False) else ""
            await interaction.response.send_message(f"📜 Kolejka jest w tej chwili całkowicie pusta.{repeat_status}", ephemeral=True)
            return

        view = QueuePaginationView(self, interaction.guild.id, page=None)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="pause", description="Pause playback of the current song")
    async def pause(self, interaction: discord.Interaction):
        if not await self.check_channel(interaction):
            return

        logger.info(f"Wywołano /pause przez {interaction.user} (G:{interaction.guild.id})")
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message("⏸️ Wstrzymano odtwarzanie.", ephemeral=True)
        else:
            await interaction.response.send_message("Obecnie żaden utwór nie jest odtwarzany.", ephemeral=True)

        await self.update_dashboard(interaction.guild.id)

    @app_commands.command(name="resume", description="Resume paused playback")
    async def resume(self, interaction: discord.Interaction):
        if not await self.check_channel(interaction):
            return

        logger.info(f"Wywołano /resume przez {interaction.user} (G:{interaction.guild.id})")
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message("▶️ Wznowiono odtwarzanie.", ephemeral=True)
        else:
            await interaction.response.send_message("Odtwarzanie nie jest wstrzymane.", ephemeral=True)

        await self.update_dashboard(interaction.guild.id)

    @app_commands.command(name="nowplaying", description="Show info about the currently playing song")
    async def nowplaying(self, interaction: discord.Interaction):
        if not await self.check_channel(interaction):
            return

        logger.info(f"Wywołano /nowplaying przez {interaction.user} (G:{interaction.guild.id})")
        song = self.current_song.get(interaction.guild.id)
        if song:
            embed = discord.Embed(
                title="Aktualnie odtwarzany utwór",
                description=f"🎶 **{song['title']}**",
                color=discord.Color.green()
            )
            if song.get('webpage_url'):
                embed.add_field(name="Link", value=song['webpage_url'], inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("W tej chwili nic nie jest odtwarzane.", ephemeral=True)

    @app_commands.command(name="dashboard", description="Toggle the persistent interactive music dashboard")
    @app_commands.describe(action="Turn dashboard ON or OFF on this channel")
    @app_commands.choices(action=[
        app_commands.Choice(name="Turn dashboard ON", value="on"),
        app_commands.Choice(name="Turn dashboard OFF", value="off")
    ])
    async def dashboard(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        if not await self.check_channel(interaction):
            return

        guild_id = interaction.guild.id

        if action.value == "on":
            old_msg = await self.get_dashboard_message(guild_id)
            if old_msg:
                try:
                    await old_msg.delete()
                except Exception:
                    pass

            embed = self.generate_dashboard_embed(guild_id)
            view = MusicDashboardView(self, guild_id)
            msg = await interaction.channel.send(embed=embed, view=view)
            self.dashboards[guild_id] = msg
            self.dashboard_metadata[guild_id] = {
                "channel_id": interaction.channel.id,
                "message_id": msg.id
            }
            self.save_state()
            logger.info(f"Utworzono panel dashboardu na kanale #{interaction.channel.name} (G:{guild_id})")
            await interaction.response.send_message("✅ Pomyślnie utworzono interaktywny panel sterowania!", ephemeral=True)

        elif action.value == "off":
            old_msg = await self.get_dashboard_message(guild_id)
            self.dashboards.pop(guild_id, None)
            self.dashboard_metadata.pop(guild_id, None)
            self.save_state()
            if old_msg:
                try:
                    await old_msg.delete()
                except Exception:
                    pass
                logger.info(f"Usunięto panel dashboardu na serwerze (G:{guild_id})")
                await interaction.response.send_message("🛑 Panel dashboardu został wyłączony i usunięty.", ephemeral=True)
            else:
                await interaction.response.send_message("ℹ️ Na tym serwerze nie ma aktywnego panelu dashboardu.", ephemeral=True)

    @app_commands.command(name="setchannel", description="Restrict bot commands to a specific text channel (or reset)")
    @app_commands.describe(channel="Text channel for bot commands (leave empty to allow all)")
    @app_commands.default_permissions(manage_guild=True)
    async def setchannel(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        guild_id = interaction.guild.id
        if channel:
            self.music_channels[guild_id] = channel.id
            self.save_state()
            logger.info(f"Użytkownik {interaction.user} ograniczył bota do kanału #{channel.name} (G:{guild_id})")
            await interaction.response.send_message(f"🔒 Komendy muzyczne zostały ograniczone do kanału {channel.mention}.", ephemeral=True)
        else:
            self.music_channels.pop(guild_id, None)
            self.save_state()
            logger.info(f"Użytkownik {interaction.user} usunął ograniczenie kanału (G:{guild_id})")
            await interaction.response.send_message("🔓 Usunięto ograniczenie kanału. Komendy muzyczne działają teraz na wszystkich kanałach tekstowych.", ephemeral=True)

    @app_commands.command(name="autoleave", description="Configure auto-disconnect when the voice channel is empty")
    @app_commands.describe(
        action="Action to perform",
        minutes="Inactivity time in minutes before disconnecting (1-60, default 10)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Status (show current config)", value="status"),
        app_commands.Choice(name="Enable auto-disconnect", value="enable"),
        app_commands.Choice(name="Disable auto-disconnect", value="disable")
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def autoleave(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        minutes: Optional[app_commands.Range[int, 1, 60]] = None
    ):
        guild_id = interaction.guild.id
        cfg = self.auto_leave_config.get(guild_id, {'enabled': True, 'minutes': 10})

        if action.value == "status":
            st = "WŁĄCZONE ✅" if cfg.get('enabled', True) else "WYŁĄCZONE ❌"
            m = cfg.get('minutes', 10)
            await interaction.response.send_message(
                f"⚙️ **Status Auto-disconnect:**\n• Stan: **{st}**\n• Czas bezczynności: **{m} minut** pustego kanału głosowego.",
                ephemeral=True
            )
        elif action.value == "enable":
            new_min = minutes if minutes is not None else cfg.get('minutes', 10)
            self.auto_leave_config[guild_id] = {'enabled': True, 'minutes': new_min}
            self.save_state()
            await interaction.response.send_message(
                f"✅ Auto-disconnect został **WŁĄCZONY** z czasem **{new_min} minut**.",
                ephemeral=True
            )
        elif action.value == "disable":
            self.auto_leave_config[guild_id] = {'enabled': False, 'minutes': cfg.get('minutes', 10)}
            self.save_state()
            if guild_id in self.auto_leave_tasks:
                self.auto_leave_tasks[guild_id].cancel()
                self.auto_leave_tasks.pop(guild_id, None)
            await interaction.response.send_message(
                "🛑 Auto-disconnect został **WYŁĄCZONY**. Bot pozostanie na kanale bez limitu czasu.",
                ephemeral=True
            )

    @app_commands.command(name="ping", description="Check Discord Gateway and Voice connection latency")
    async def ping(self, interaction: discord.Interaction):
        ws_ping = round(self.bot.latency * 1000)
        vc = interaction.guild.voice_client if interaction.guild else None
        voice_ping = None
        if vc and hasattr(vc, 'average_latency'):
            voice_ping = round(vc.average_latency * 1000)

        msg = f"🏓 **Pong!**\n• Discord Gateway: `{ws_ping} ms`"
        if voice_ping is not None:
            msg += f"\n• Voice WebSocket: `{voice_ping} ms`"
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="status", description="Show bot diagnostics, system metrics, and uptime")
    async def status(self, interaction: discord.Interaction):
        uptime_sec = int(time.time() - getattr(self.bot, 'start_time', time.time()))
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s" if days else f"{hours}h {minutes}m {seconds}s"

        ram_mb = "N/A"
        try:
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        kb = int(line.split()[1])
                        ram_mb = f"{round(kb / 1024, 1)} MB"
                        break
        except Exception:
            pass

        guild_count = len(self.bot.guilds)
        active_vcs = len([vc for vc in self.bot.voice_clients if vc.is_playing() or vc.is_paused()])

        embed = discord.Embed(
            title="📊 SubWoofer — System Status",
            color=discord.Color.green()
        )
        embed.add_field(name="⏱️ Uptime", value=f"`{uptime_str}`", inline=True)
        embed.add_field(name="💾 RAM Usage", value=f"`{ram_mb}`", inline=True)
        embed.add_field(name="🌐 Ping", value=f"`{round(self.bot.latency * 1000)} ms`", inline=True)
        embed.add_field(name="🏰 Servers", value=f"`{guild_count}`", inline=True)
        embed.add_field(name="🎵 Active Players", value=f"`{active_vcs}`", inline=True)
        embed.add_field(name="🐍 Python", value=f"`{platform.python_version()}`", inline=True)
        embed.add_field(name="📦 discord.py", value=f"`{discord.__version__}`", inline=True)
        embed.add_field(name="📹 yt-dlp", value=f"`{yt_dlp.version.__version__}`", inline=True)
        embed.set_footer(text="SubWoofer • 24/7 Discord Music Bot")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="logs", description="View recent system logs or errors (Admin only)")
    @app_commands.describe(
        filter="Log filter type",
        lines="Number of lines to show (5-35, default 15)"
    )
    @app_commands.choices(filter=[
        app_commands.Choice(name="All recent logs", value="all"),
        app_commands.Choice(name="Errors only (ERROR / CRITICAL)", value="errors"),
        app_commands.Choice(name="Warnings and errors (WARNING / ERROR)", value="warnings")
    ])
    @app_commands.default_permissions(administrator=True)
    async def logs(
        self,
        interaction: discord.Interaction,
        filter: app_commands.Choice[str],
        lines: Optional[app_commands.Range[int, 5, 35]] = 15
    ):
        log_file = 'bot.log'
        if not os.path.exists(log_file):
            await interaction.response.send_message("❌ Nie znaleziono pliku `bot.log`.", ephemeral=True)
            return

        try:
            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                all_lines = f.readlines()
        except Exception as e:
            await interaction.response.send_message(f"❌ Nie udało się odczytać pliku logów: {e}", ephemeral=True)
            return

        selected_lines = []
        if filter.value == "errors":
            selected_lines = [l for l in all_lines if any(k in l for k in ("ERROR", "CRITICAL", "Traceback", "Exception"))]
        elif filter.value == "warnings":
            selected_lines = [l for l in all_lines if any(k in l for k in ("WARNING", "ERROR", "CRITICAL", "Traceback", "Exception"))]
        else:
            selected_lines = all_lines

        if not selected_lines:
            await interaction.response.send_message(f"ℹ️ Brak wpisów w logach dla filtru `{filter.name}`.", ephemeral=True)
            return

        num_lines = lines if lines else 15
        output_lines = selected_lines[-num_lines:]
        content = "".join(output_lines)
        if len(content) > 1900:
            content = content[-1900:]

        await interaction.response.send_message(f"📋 **Ostatnie {len(output_lines)} linijek (`{filter.name}`):**\n```log\n{content}\n```", ephemeral=True)

    @app_commands.command(name="help", description="Show guide and command list for SubWoofer")
    async def help_command(self, interaction: discord.Interaction):
        embed = get_help_embed()
        view = HelpView(embed)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @commands.command(name="help")
    async def prefix_help(self, ctx: commands.Context):
        embed = get_help_embed()
        view = HelpView(embed)
        await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Music(bot))


