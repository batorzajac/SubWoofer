import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import logging
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
        self.queues = {} # struktura: {guild_id: [{'title': str, 'webpage_url': str}, ...]}
        self.current_song = {} # struktura: {guild_id: dict}

    def get_queue(self, guild_id):
        """Pobiera (lub tworzy, jeśli brak) kolejkę dla danego serwera."""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    async def get_stream_url(self, webpage_url):
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

    async def search_items(self, query):
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
                
                # Jeśli to playlista (posiada _type == 'playlist' lub listę wpisów > 1)
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

                # Jeśli to pojedynczy utwór z linku
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

        # 2. Przypadek: Wyszukiwanie tekstowe (próbujemy najpierw YouTube Music)
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
            return

        if not queue:
            self.current_song.pop(guild_id, None)
            logger.info(f"Kolejka odtwarzania na serwerze {guild_id} dobiegła końca.")
            return

        # Pobieramy kolejny utwór z kolejki
        song = queue.pop(0)
        self.current_song[guild_id] = song

        # LAZY LOADING: Dopiero teraz pobieramy świeży bezpośredni link audio
        stream_url = await self.get_stream_url(song['webpage_url'])
        if not stream_url:
            logger.warning(f"Nie udało się wyciągnąć strumienia dla '{song['title']}', pomijam...")
            try:
                await interaction.channel.send(f"⚠️ Nie udało się pobrać strumienia dla: **{song['title']}**, pomijam...")
            except Exception:
                pass
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

            try:
                await interaction.channel.send(f"🎶 Teraz odtwarzam: **{song['title']}**")
            except Exception as e:
                logger.warning(f"Błąd wysyłania komunikatu 'Teraz odtwarzam': {e}")

        except Exception as e:
            logger.error(f"Wystąpił błąd w FFmpeg podczas startu odtwarzania na serwerze {guild_id}: {e}")
            self.play_next(interaction)

    @app_commands.command(name="play", description="Wyszukaj utwór lub dodaj playlistę (do 500 utworów w kolejce)")
    async def play(self, interaction: discord.Interaction, zapytanie: str):
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

        # 1. Weryfikacja twardego limitu 500 utworów
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
            await interaction.followup.send("❌ Nie znaleziono utworu/playlisty lub wystąpił błąd przy pobieraniu.")
            return

        # Sprawdzenie ile wolnych miejsc pozostało w kolejce
        current_len = len(queue)
        available_slots = MAX_QUEUE_SIZE - current_len

        if is_playlist:
            total_playlist_songs = len(songs)
            if total_playlist_songs > available_slots:
                songs_to_add = songs[:available_slots]
                queue.extend(songs_to_add)
                await interaction.followup.send(
                    f"⚠️ **Dodano {len(songs_to_add)} utworów z playlisty '{playlist_title}'!**\n"
                    f"Osiągnięto limit **{MAX_QUEUE_SIZE}** utworów w kolejce (pominięto {total_playlist_songs - available_slots} nadmiarowych utworów)."
                )
            else:
                queue.extend(songs)
                await interaction.followup.send(
                    f"📑 **Dodano playlistę:** `{playlist_title}` ({len(songs)} utworów) do kolejki! 🎶 (Łącznie w kolejce: {len(queue)}/{MAX_QUEUE_SIZE})"
                )
        else:
            song = songs[0]
            queue.append(song)
            if not voice_client.is_playing() and not voice_client.is_paused():
                await interaction.followup.send(f"🎵 Znaleziono i ładuję: **{song['title']}**...")
            else:
                await interaction.followup.send(f"➕ Dodano do kolejki: **{song['title']}** (Pozycja: {len(queue)}/{MAX_QUEUE_SIZE})")

        # Jeśli aktualnie nic nie gra, odpalamy pierwszy utwór z kolejki
        if not voice_client.is_playing() and not voice_client.is_paused():
            self.play_next(interaction)

    @app_commands.command(name="stop", description="Zatrzymuje muzykę, czyści kolejkę i bot opuszcza kanał")
    async def stop(self, interaction: discord.Interaction):
        logger.info(f"Wywołano /stop przez {interaction.user} (G:{interaction.guild.id})")
        voice_client = interaction.guild.voice_client
        
        if voice_client:
            self.get_queue(interaction.guild.id).clear()
            self.current_song.pop(interaction.guild.id, None)
            voice_client.stop()
            await voice_client.disconnect()
            logger.info(f"Oczyszczono kolejkę i rozłączono kanał na (G:{interaction.guild.id})")
            await interaction.response.send_message("🛑 Zatrzymano muzykę i wyczyszczono kolejkę. Bot opuścił kanał.")
        else:
            await interaction.response.send_message("Bot aktualnie nie odtwarza muzyki na żadnym kanale głosowym.", ephemeral=True)

    @app_commands.command(name="skip", description="Pomija aktualnie odtwarzany utwór")
    async def skip(self, interaction: discord.Interaction):
        logger.info(f"Wywołano /skip przez {interaction.user} (G:{interaction.guild.id})")
        voice_client = interaction.guild.voice_client
        
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await interaction.response.send_message("⏭️ Pomyślnie pominięto utwór.")
        else:
            await interaction.response.send_message("Obecnie nie odtwarzam żadnego utworu.", ephemeral=True)

    @app_commands.command(name="queue", description="Pokazuje aktualną kolejkę nadchodzących utworów (do 500)")
    async def queue(self, interaction: discord.Interaction):
        logger.info(f"Wywołano /queue przez {interaction.user} (G:{interaction.guild.id})")
        queue = self.get_queue(interaction.guild.id)
        
        if not queue:
            await interaction.response.send_message("📜 Kolejka jest w tej chwili całkowicie pusta.")
            return
        
        total = len(queue)
        embed = discord.Embed(
            title=f"Kolejka Odtwarzania ({total}/{MAX_QUEUE_SIZE})",
            color=discord.Color.dark_purple()
        )
        
        for i, song in enumerate(queue[:10]):
            embed.add_field(name=f"{i+1}. {song['title']}", value="⏳ Oczekuje w kolejce", inline=False)
            
        if total > 10:
            embed.set_footer(text=f"I {total - 10} innych utworów na liście...")
            
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="pause", description="Wstrzymuje odtwarzanie aktualnego utworu")
    async def pause(self, interaction: discord.Interaction):
        logger.info(f"Wywołano /pause przez {interaction.user} (G:{interaction.guild.id})")
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message("⏸️ Wstrzymano odtwarzanie.")
        else:
            await interaction.response.send_message("Obecnie żaden utwór nie jest odtwarzany.", ephemeral=True)

    @app_commands.command(name="resume", description="Wznawia wstrzymane odtwarzanie")
    async def resume(self, interaction: discord.Interaction):
        logger.info(f"Wywołano /resume przez {interaction.user} (G:{interaction.guild.id})")
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message("▶️ Wznowiono odtwarzanie.")
        else:
            await interaction.response.send_message("Odtwarzanie nie jest wstrzymane.", ephemeral=True)

    @app_commands.command(name="nowplaying", description="Pokazuje informacje o aktualnie odtwarzanym utworze")
    async def nowplaying(self, interaction: discord.Interaction):
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
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("W tej chwili nic nie jest odtwarzane.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Music(bot))
