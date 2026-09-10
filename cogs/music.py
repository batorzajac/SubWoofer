import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import logging
import random
import os
import json
from typing import Optional
from ytmusicapi import YTMusic

logger = logging.getLogger('musicbot.music_cog')

# Maksymalny limit utworów w kolejce per-serwer
MAX_QUEUE_SIZE = 500

# Inicjalizacja ytmusicapi (do błyskawicznego wyszukiwania w ekosystemie YouTube Music)
ytmusic = YTMusic()

# 1. Konfiguracja do błyskawicznego pobierania metadanych i całych playlist (Lazy Loading)
YTDL_FLAT_OPTIONS = {
    'extract_flat': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'js_runtimes': {'node': {}}
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
    'source_address': '0.0.0.0',
    'js_runtimes': {'node': {}}
}

# Parametry optymalizujące przerywanie dźwięku w FFmpeg
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl_flat = yt_dlp.YoutubeDL(YTDL_FLAT_OPTIONS)
ytdl_stream = yt_dlp.YoutubeDL(YTDL_STREAM_OPTIONS)


STATE_FILE = "bot_state.json"


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
        random.shuffle(queue)
        await interaction.response.send_message(f"🔀 Przelosowano kolejność **{len(queue)}** utworów!", ephemeral=True)
        await cog.update_dashboard(guild_id)

    @discord.ui.button(emoji="🔁", label="Powtarzaj", style=discord.ButtonStyle.secondary, custom_id="sb_repeat")
    async def repeat_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog, guild_id = self._resolve(interaction)
        if not cog or not guild_id:
            return
        curr = cog.repeat_mode.get(guild_id, False)
        cog.repeat_mode[guild_id] = not curr
        st = "WŁĄCZONE 🔁" if cog.repeat_mode[guild_id] else "WYŁĄCZONE ⏹️"
        await interaction.response.send_message(f"🔁 Powtarzanie kolejki: **{st}**", ephemeral=True)
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
                cog.current_song.pop(guild_id, None)
            vc.stop()
            await vc.disconnect()
            await interaction.response.send_message("🛑 Zatrzymano muzykę i rozłączono bota.", ephemeral=True)
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
            await interaction.response.send_message("📜 Kolejka jest w tej chwili całkowicie pusta.", ephemeral=True)
            return
        embed = discord.Embed(title=f"Kolejka Odtwarzania ({len(queue)}/{MAX_QUEUE_SIZE})", color=discord.Color.dark_purple())
        for i, s in enumerate(queue[:10]):
            embed.add_field(name=f"{i+1}. {s['title']}", value="⏳ W kolejce", inline=False)
        if len(queue) > 10:
            embed.set_footer(text=f"I {len(queue) - 10} innych utworów...")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(emoji="🔄", label="Odśwież", style=discord.ButtonStyle.secondary, custom_id="sb_refresh", row=1)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog, guild_id = self._resolve(interaction)
        if cog and guild_id:
            await cog.update_dashboard(guild_id)
        await interaction.response.send_message("🔄 Odświeżono stan panelu.", ephemeral=True)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}             # {guild_id: [{'title': str, 'webpage_url': str}, ...]}
        self.current_song = {}       # {guild_id: dict}
        self.repeat_mode = {}        # {guild_id: bool}
        self.music_channels = {}     # {guild_id: int (channel_id)}
        self.dashboards = {}         # {guild_id: discord.Message}
        self.dashboard_metadata = {} # {guild_id: {'channel_id': int, 'message_id': int}}
        self.load_state()

    async def cog_load(self):
        # Trwałe przyciski panelu działające nawet po restartach bota
        self.bot.add_view(MusicDashboardView(self))

    def load_state(self):
        """Wczytuje zapisany stan kanałów i dashboardów z pliku."""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.music_channels = {int(k): v for k, v in data.get("music_channels", {}).items()}
                    self.dashboard_metadata = {int(k): v for k, v in data.get("dashboards", {}).items()}
                    logger.info("Wczytano zapisany stan dashboardów i ograniczeń kanałów.")
        except Exception as e:
            logger.warning(f"Nie udało się wczytać stanu z {STATE_FILE}: {e}")

    def save_state(self):
        """Zapisuje bieżący stan kanałów i dashboardów do pliku."""
        try:
            data = {
                "music_channels": {str(k): v for k, v in self.music_channels.items()},
                "dashboards": {str(k): v for k, v in self.dashboard_metadata.items()}
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

    def generate_dashboard_embed(self, guild_id: int) -> discord.Embed:
        """Tworzy estetyczny Embed reprezentujący aktualny stan bota dla dashboardu."""
        guild = self.bot.get_guild(guild_id)
        vc = guild.voice_client if guild else None
        song = self.current_song.get(guild_id)
        queue = self.get_queue(guild_id)
        repeat = self.repeat_mode.get(guild_id, False)

        embed = discord.Embed(
            title="🐶 SubWoofer — Interaktywny Panel Muzyczny",
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

        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="W kolejce", value=f"{len(queue)}/{MAX_QUEUE_SIZE}", inline=True)
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

    async def search_items(self, query: str):
        """
        Wyszukuje pojedynczy utwór lub playlistę w trybie leniwym (Lazy Loading).
        Zwraca: (is_playlist: bool, songs: list[dict], playlist_title: Optional[str])
        """
        loop = asyncio.get_event_loop()
        logger.info(f"Rozpoczynam wyszukiwanie/ekstrakcję dla: {query}")
        
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
        """Asynchroniczne pobranie świeżego linku audio i odtworzenie kolejnego utworu (Lazy Loading)."""
        guild_id = interaction.guild.id
        queue = self.get_queue(guild_id)
        voice_client = interaction.guild.voice_client

        if not voice_client or not voice_client.is_connected():
            logger.warning(f"Zażądano _play_next_async, ale brak VoiceClienta na serwerze {guild_id}")
            await self.update_presence(None)
            await self.update_dashboard(guild_id)
            return

        # Jeśli kolejka jest pusta
        if not queue:
            self.current_song.pop(guild_id, None)
            logger.info(f"Kolejka odtwarzania na serwerze {guild_id} dobiegła końca.")
            await self.update_presence(None)
            await self.update_dashboard(guild_id)
            
            # Jeśli repeat nie jest włączony -> automatyczne rozłączenie z kanału głosowego
            if not self.repeat_mode.get(guild_id, False):
                if voice_client.is_connected():
                    await voice_client.disconnect()
                    logger.info(f"SubWoofer opuścił kanał po zakończeniu odtwarzania kolejki (G:{guild_id}).")
            return

        # Pobieramy kolejny utwór z kolejki
        song = queue.pop(0)
        self.current_song[guild_id] = song

        # Jeśli włączony jest tryb repeat: wrzucamy utwór z powrotem na koniec kolejki
        if self.repeat_mode.get(guild_id, False):
            queue.append({'title': song['title'], 'webpage_url': song['webpage_url']})

        # LAZY LOADING: Pobieramy świeży link audio tuż przed startem
        stream_url = await self.get_stream_url(song['webpage_url'])
        if not stream_url:
            logger.warning(f"Nie udało się wyciągnąć strumienia dla '{song['title']}', pomijam...")
            if not queue and not self.repeat_mode.get(guild_id, False):
                if voice_client.is_connected():
                    await voice_client.disconnect()
                    logger.info(f"Rozłączono po błędzie odtwarzania ostatniego utworu (G:{guild_id}).")
                await self.update_presence(None)
                await self.update_dashboard(guild_id)
                return
            self.play_next(interaction)
            return

        try:
            logger.info(f"Rozpoczynam odtwarzanie utworu: {song['title']} (Serwer: {guild_id})")
            source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)

            def after_playing(error):
                if error:
                    logger.error(f"Błąd FFmpeg podczas odtwarzania utworu: {error}")
                self.play_next(interaction)

            voice_client.play(source, after=after_playing)
            
            # Ciche odtwarzanie + Discord Presence (Słucha: Tytuł piosenki) + Dashboard
            await self.update_presence(song['title'])
            await self.update_dashboard(guild_id)

        except Exception as e:
            logger.error(f"Wystąpił błąd w FFmpeg podczas startu odtwarzania na serwerze {guild_id}: {e}")
            if not queue and not self.repeat_mode.get(guild_id, False):
                if voice_client.is_connected():
                    await voice_client.disconnect()
                await self.update_presence(None)
                await self.update_dashboard(guild_id)
                return
            self.play_next(interaction)

    # ==========================================
    # KOMENDY DISCORDA (SLASH COMMANDS)
    # ==========================================

    @app_commands.command(name="play", description="Wyszukaj utwór lub dodaj playlistę (do 500 utworów w kolejce)")
    async def play(self, interaction: discord.Interaction, zapytanie: str):
        if not await self.check_channel(interaction):
            return

        logger.info(f"Użytkownik {interaction.user} (G:{interaction.guild.id}) żąda /play [{zapytanie}]")

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

        is_playlist, songs, playlist_title = await self.search_items(zapytanie)
        if not songs:
            logger.error(f"Nie udało się odnaleźć muzyki dla zapytania '{zapytanie}' (G:{interaction.guild.id})")
            err_msg = await interaction.followup.send("❌ Nie znaleziono utworu/playlisty lub wystąpił błąd przy pobieraniu.")
            if err_msg:
                try:
                    await err_msg.delete(delay=30)
                except Exception:
                    pass
            return

        current_len = len(queue)
        available_slots = MAX_QUEUE_SIZE - current_len

        # Samoznikające wiadomości po 5 minutach (delete(delay=300))
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
            logger.error(f"Błąd podczas wysyłania lub planowania usunięcia wiadomości w /play: {e}")

        await self.update_dashboard(interaction.guild.id)

        # Jeśli aktualnie nic nie gra, odpalamy pierwszy utwór z kolejki
        if not voice_client.is_playing() and not voice_client.is_paused():
            self.play_next(interaction)

    @app_commands.command(name="repeat", description="Włącza lub wyłącza powtarzanie (zapętlenie) całej kolejki")
    async def repeat(self, interaction: discord.Interaction):
        if not await self.check_channel(interaction):
            return

        guild_id = interaction.guild.id
        current = self.repeat_mode.get(guild_id, False)
        self.repeat_mode[guild_id] = not current
        status = "WŁĄCZONE 🔁" if self.repeat_mode[guild_id] else "WYŁĄCZONE ⏹️"
        logger.info(f"Użytkownik {interaction.user} zmienił repeat na: {status} (G:{guild_id})")
        await interaction.response.send_message(f"🔁 Powtarzanie całej kolejki: **{status}**", ephemeral=True)
        await self.update_dashboard(guild_id)

    @app_commands.command(name="shuffle", description="Przelosowuje kolejność utworów w kolejce")
    async def shuffle(self, interaction: discord.Interaction):
        if not await self.check_channel(interaction):
            return

        queue = self.get_queue(interaction.guild.id)
        if len(queue) < 2:
            await interaction.response.send_message("❌ Za mało utworów w kolejce, aby przelosować (minimum 2).", ephemeral=True)
            return

        random.shuffle(queue)
        logger.info(f"Użytkownik {interaction.user} przelosował kolejkę (G:{interaction.guild.id})")
        await interaction.response.send_message(f"🔀 Przelosowano kolejność **{len(queue)}** utworów w kolejce!", ephemeral=True)
        await self.update_dashboard(interaction.guild.id)

    @app_commands.command(name="skipto", description="Wymusza natychmiastowe odtworzenie utworu o wskazanym numerze w kolejce")
    @app_commands.describe(pozycja="Numer utworu w kolejce do natychmiastowego odtworzenia (od 1)")
    async def skipto(self, interaction: discord.Interaction, pozycja: int):
        if not await self.check_channel(interaction):
            return

        queue = self.get_queue(interaction.guild.id)
        if pozycja < 1 or pozycja > len(queue):
            await interaction.response.send_message(
                f"❌ Nieprawidłowy numer! Podaj pozycję od 1 do {len(queue)}.",
                ephemeral=True
            )
            return

        # Wyciągamy wskazany utwór i umieszczamy go na pozycji 0 (zagra od razu, reszta kolejki bez zmian)
        target_song = queue.pop(pozycja - 1)
        queue.insert(0, target_song)

        voice_client = interaction.guild.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            logger.info(f"Użytkownik {interaction.user} użył skipto {pozycja}: {target_song['title']} (G:{interaction.guild.id})")
            voice_client.stop()
            await interaction.response.send_message(
                f"⏭️ Wymuszono odtworzenie: **{target_song['title']}** (pozostałe utwory zachowane w pierwotnym porządku).",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("Bot nie odtwarza obecnie muzyki.", ephemeral=True)

        await self.update_dashboard(interaction.guild.id)

    @app_commands.command(name="playnext", description="Ustawia wybrany utwór z kolejki jako następny do zagrania")
    @app_commands.describe(pozycja="Numer utworu w kolejce, który ma zagrać jako następny (od 1)")
    async def playnext(self, interaction: discord.Interaction, pozycja: int):
        if not await self.check_channel(interaction):
            return

        queue = self.get_queue(interaction.guild.id)
        if pozycja < 1 or pozycja > len(queue):
            await interaction.response.send_message(
                f"❌ Nieprawidłowy numer! Podaj pozycję od 1 do {len(queue)}.",
                ephemeral=True
            )
            return

        # Wyciągamy wybrany utwór i wstawiamy go na sam początek kolejki (indeks 0)
        song = queue.pop(pozycja - 1)
        queue.insert(0, song)
        logger.info(f"Użytkownik {interaction.user} ustawił utwór jako następny: {song['title']} (G:{interaction.guild.id})")
        await interaction.response.send_message(f"⏩ Utwór **{song['title']}** zagra teraz jako następny w kolejce!", ephemeral=True)
        await self.update_dashboard(interaction.guild.id)

    @app_commands.command(name="stop", description="Zatrzymuje muzykę, czyści kolejkę i bot opuszcza kanał")
    async def stop(self, interaction: discord.Interaction):
        if not await self.check_channel(interaction):
            return

        logger.info(f"Wywołano /stop przez {interaction.user} (G:{interaction.guild.id})")
        voice_client = interaction.guild.voice_client
        
        await self.update_presence(None)

        if voice_client:
            self.get_queue(interaction.guild.id).clear()
            self.current_song.pop(interaction.guild.id, None)
            voice_client.stop()
            await voice_client.disconnect()
            logger.info(f"Oczyszczono kolejkę i rozłączono kanał na (G:{interaction.guild.id})")
            await interaction.response.send_message("🛑 Zatrzymano muzykę i wyczyszczono kolejkę. Bot opuścił kanał.", ephemeral=True)
        else:
            await interaction.response.send_message("Bot aktualnie nie odtwarza muzyki na żadnym kanale głosowym.", ephemeral=True)

        await self.update_dashboard(interaction.guild.id)

    @app_commands.command(name="skip", description="Pomija aktualnie odtwarzany utwór")
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

    @app_commands.command(name="queue", description="Pokazuje aktualną kolejkę nadchodzących utworów (do 500)")
    async def queue(self, interaction: discord.Interaction):
        if not await self.check_channel(interaction):
            return

        logger.info(f"Wywołano /queue przez {interaction.user} (G:{interaction.guild.id})")
        queue = self.get_queue(interaction.guild.id)
        
        if not queue:
            repeat_status = " (🔁 Repeat: WŁĄCZONE)" if self.repeat_mode.get(interaction.guild.id, False) else ""
            await interaction.response.send_message(f"📜 Kolejka jest w tej chwili całkowicie pusta.{repeat_status}", ephemeral=True)
            return
        
        total = len(queue)
        repeat_tag = " [🔁 Repeat]" if self.repeat_mode.get(interaction.guild.id, False) else ""
        embed = discord.Embed(
            title=f"Kolejka Odtwarzania ({total}/{MAX_QUEUE_SIZE}){repeat_tag}",
            color=discord.Color.dark_purple()
        )
        
        for i, song in enumerate(queue[:10]):
            embed.add_field(name=f"{i+1}. {song['title']}", value="⏳ Oczekuje w kolejce", inline=False)
            
        if total > 10:
            embed.set_footer(text=f"I {total - 10} innych utworów na liście...")
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="pause", description="Wstrzymuje odtwarzanie aktualnego utworu")
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

    @app_commands.command(name="resume", description="Wznawia wstrzymane odtwarzanie")
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

    @app_commands.command(name="nowplaying", description="Pokazuje informacje o aktualnie odtwarzanym utworze")
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

    @app_commands.command(name="dashboard", description="Włącza lub wyłącza interaktywny panel sterowania muzyką (Dashboard)")
    @app_commands.describe(akcja="Wybierz, czy chcesz utworzyć nowy panel, czy wyłączyć i usunąć istniejący")
    @app_commands.choices(akcja=[
        app_commands.Choice(name="Włącz panel na tym kanale", value="on"),
        app_commands.Choice(name="Wyłącz i usuń panel", value="off")
    ])
    async def dashboard(self, interaction: discord.Interaction, akcja: app_commands.Choice[str]):
        if not await self.check_channel(interaction):
            return

        guild_id = interaction.guild.id

        if akcja.value == "on":
            old_msg = await self.get_dashboard_message(guild_id)
            if old_msg:
                try:
                    await old_msg.delete()
                except Exception:
                    pass

            embed = self.generate_dashboard_embed(guild_id)
            view = MusicDashboardView(self, guild_id)
            # Panel wysyłamy jako stałą wiadomość na kanale
            msg = await interaction.channel.send(embed=embed, view=view)
            self.dashboards[guild_id] = msg
            self.dashboard_metadata[guild_id] = {
                "channel_id": interaction.channel.id,
                "message_id": msg.id
            }
            self.save_state()
            logger.info(f"Utworzono panel dashboardu na kanale #{interaction.channel.name} (G:{guild_id})")
            await interaction.response.send_message("✅ Pomyślnie utworzono interaktywny panel sterowania!", ephemeral=True)

        elif akcja.value == "off":
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

    @app_commands.command(name="setchannel", description="Ogranicza komendy bota do wybranego kanału tekstowego (lub resetuje)")
    @app_commands.describe(kanal="Wybierz kanał tekstowy dla bota (pozostaw puste, aby usunąć ograniczenie)")
    @app_commands.default_permissions(manage_guild=True)
    async def setchannel(self, interaction: discord.Interaction, kanal: Optional[discord.TextChannel] = None):
        guild_id = interaction.guild.id
        if kanal:
            self.music_channels[guild_id] = kanal.id
            self.save_state()
            logger.info(f"Użytkownik {interaction.user} ograniczył bota do kanału #{kanal.name} (G:{guild_id})")
            await interaction.response.send_message(f"🔒 Komendy muzyczne zostały ograniczone do kanału {kanal.mention}.", ephemeral=True)
        else:
            self.music_channels.pop(guild_id, None)
            self.save_state()
            logger.info(f"Użytkownik {interaction.user} usunął ograniczenie kanału (G:{guild_id})")
            await interaction.response.send_message("🔓 Usunięto ograniczenie kanału. Komendy muzyczne działają teraz na wszystkich kanałach tekstowych.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Music(bot))
