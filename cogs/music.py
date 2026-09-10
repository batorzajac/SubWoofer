import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import logging
import random
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


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}          # {guild_id: [{'title': str, 'webpage_url': str}, ...]}
        self.current_song = {}    # {guild_id: dict}
        self.repeat_mode = {}     # {guild_id: bool}
        self.music_channels = {}  # {guild_id: int (channel_id)}

    def get_queue(self, guild_id: int):
        """Pobiera (lub tworzy, jeśli brak) kolejkę dla danego serwera."""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    async def update_presence(self, song_title: Optional[str] = None):
        """Aktualizuje status profilu bota (Discord Presence) lub czyści go po zakończeniu grania."""
        try:
            if song_title:
                activity = discord.Activity(
                    type=discord.ActivityType.listening,
                    name=song_title[:128]
                )
                await self.bot.change_presence(activity=activity)
            else:
                await self.bot.change_presence(activity=None)
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
            return

        # Jeśli kolejka jest pusta
        if not queue:
            self.current_song.pop(guild_id, None)
            logger.info(f"Kolejka odtwarzania na serwerze {guild_id} dobiegła końca.")
            await self.update_presence(None)
            
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
            
            # Ciche odtwarzanie + Discord Presence (Słucha: Tytuł piosenki)
            await self.update_presence(song['title'])

        except Exception as e:
            logger.error(f"Wystąpił błąd w FFmpeg podczas startu odtwarzania na serwerze {guild_id}: {e}")
            if not queue and not self.repeat_mode.get(guild_id, False):
                if voice_client.is_connected():
                    await voice_client.disconnect()
                await self.update_presence(None)
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
            await interaction.followup.send("❌ Nie znaleziono utworu/playlisty lub wystąpił błąd przy pobieraniu.", ephemeral=True)
            return

        current_len = len(queue)
        available_slots = MAX_QUEUE_SIZE - current_len

        # Samoznikające wiadomości po 5 minutach (delete_after=300)
        if is_playlist:
            total_playlist_songs = len(songs)
            if total_playlist_songs > available_slots:
                songs_to_add = songs[:available_slots]
                queue.extend(songs_to_add)
                await interaction.followup.send(
                    f"⚠️ **Dodano {len(songs_to_add)} utworów z playlisty '{playlist_title}'!**\n"
                    f"Osiągnięto limit **{MAX_QUEUE_SIZE}** utworów w kolejce (pominięto {total_playlist_songs - available_slots} nadmiarowych utworów).",
                    delete_after=300
                )
            else:
                queue.extend(songs)
                await interaction.followup.send(
                    f"📑 **Dodano playlistę:** `{playlist_title}` ({len(songs)} utworów) do kolejki! 🎶 (Łącznie w kolejce: {len(queue)}/{MAX_QUEUE_SIZE})",
                    delete_after=300
                )
        else:
            song = songs[0]
            queue.append(song)
            if not voice_client.is_playing() and not voice_client.is_paused():
                await interaction.followup.send(f"🎵 Załadowano: **{song['title']}**...", delete_after=300)
            else:
                await interaction.followup.send(f"➕ Dodano do kolejki: **{song['title']}** (Pozycja: {len(queue)}/{MAX_QUEUE_SIZE})", delete_after=300)

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

    @app_commands.command(name="setchannel", description="Ogranicza komendy bota do wybranego kanału tekstowego (lub resetuje)")
    @app_commands.describe(kanal="Wybierz kanał tekstowy dla bota (pozostaw puste, aby usunąć ograniczenie)")
    @app_commands.default_permissions(manage_guild=True)
    async def setchannel(self, interaction: discord.Interaction, kanal: Optional[discord.TextChannel] = None):
        guild_id = interaction.guild.id
        if kanal:
            self.music_channels[guild_id] = kanal.id
            logger.info(f"Użytkownik {interaction.user} ograniczył bota do kanału #{kanal.name} (G:{guild_id})")
            await interaction.response.send_message(f"🔒 Komendy muzyczne zostały ograniczone do kanału {kanal.mention}.", ephemeral=True)
        else:
            self.music_channels.pop(guild_id, None)
            logger.info(f"Użytkownik {interaction.user} usunął ograniczenie kanału (G:{guild_id})")
            await interaction.response.send_message("🔓 Usunięto ograniczenie kanału. Komendy muzyczne działają teraz na wszystkich kanałach tekstowych.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Music(bot))
