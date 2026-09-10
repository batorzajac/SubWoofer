import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import logging
from ytmusicapi import YTMusic

logger = logging.getLogger('musicbot.music_cog')

# Inicjalizacja ytmusicapi (do błyskawicznego odpytywania metadanych YTM)
ytmusic = YTMusic()

# Zaawansowana konfiguracja yt-dlp pomagająca ominąć blokady wiekowe YouTube bez logowania (spoofing jako TV/Android)
YTDL_OPTIONS = {
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
    # Krytyczne do ominięcia 18+ : Spoofing
    'extractor_args': {
        'youtube': {
            'client': ['android', 'web']
        }
    }
}

# Parametry optymalizujące przerywanie dźwięku w FFmpeg
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {} # struktura: {guild_id: [dict, dict, ...]}
        self.current_song = {} # struktura: {guild_id: dict}

    def get_queue(self, guild_id):
        """Pobiera (lub tworzy, jeśli brak) kolejkę dla danego serwera."""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    async def search_song(self, query):
        """Asynchroniczne wyszukiwanie z użyciem ytmusicapi (dla tekstu) oraz yt-dlp (dla odczytania samego linku)."""
        logger.info(f"Rozpoczynam proces wyszukiwania dla zapytania: {query}")
        try:
            loop = asyncio.get_event_loop()
            
            # Jeśli to jest link bezpośredni
            if query.startswith('http://') or query.startswith('https://'):
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
                if 'entries' in data and data['entries']:
                    data = data['entries'][0]
                stream_url = data.get('url')
                if not stream_url and 'formats' in data:
                    for f in reversed(data['formats']):
                        if f.get('acodec') != 'none' and f.get('url'):
                            stream_url = f['url']
                            break
                return {'url': stream_url, 'title': data.get('title', 'Nieznany tytuł z URL')}
            
            # Jeśli to tekst, próbujemy najpierw szybkiego API Youtube Music
            top_result = None
            try:
                search_results = ytmusic.search(query, filter="songs")
                if search_results:
                    top_result = search_results[0]
            except Exception as e:
                logger.warning(f"Błąd wyszukiwania w ytmusicapi: {e}")

            if top_result and 'videoId' in top_result:
                video_id = top_result['videoId']
                artist_name = top_result.get('artists', [{}])[0].get('name', '')
                title = f"{artist_name} - {top_result['title']}" if artist_name else top_result['title']
                yt_url = f"https://music.youtube.com/watch?v={video_id}"
                logger.info(f"Znaleziono utwór na YTM: {title}. Rozpoczynam ekstrakcję przez yt-dlp...")
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(yt_url, download=False))
            else:
                # Fallback do ogólnego wyszukiwania yt-dlp
                logger.info(f"Brak w YTM, używam wyszukiwania ogólnego yt-dlp dla: {query}")
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{query}", download=False))
                if 'entries' in data and data['entries']:
                    data = data['entries'][0]
                title = data.get('title', query)

            stream_url = data.get('url')
            if not stream_url and 'formats' in data:
                for f in reversed(data['formats']):
                    if f.get('acodec') != 'none' and f.get('url'):
                        stream_url = f['url']
                        break

            return {'url': stream_url, 'title': title}
            
        except Exception as e:
            logger.error(f"Błąd podczas wyszukiwania i parsowania utworu: {e}")
            return None

    def play_next(self, interaction: discord.Interaction):
        """Odtwarza następny utwór w kolejce."""
        guild_id = interaction.guild.id
        queue = self.get_queue(guild_id)
        voice_client = interaction.guild.voice_client

        if not voice_client:
            logger.warning(f"Zażądano play_next, ale brak VoiceClienta na serwerze {guild_id}")
            return

        if not queue:
            self.current_song.pop(guild_id, None)
            logger.info(f"Kolejka odtwarzania na serwerze {guild_id} dobiegła końca.")
            return

        # Zdejmij pierwszy element
        song = queue.pop(0)
        self.current_song[guild_id] = song
        
        try:
            logger.info(f"Rozpoczynam odtwarzanie utworu: {song['title']} (Serwer: {guild_id})")
            source = discord.FFmpegPCMAudio(song['url'], **FFMPEG_OPTIONS)
            
            def after_playing(error):
                if error:
                    logger.error(f"Błąd FFmpeg podczas odtwarzania utworu: {error}")
                self.play_next(interaction)

            voice_client.play(source, after=after_playing)
            
            # Powiadomienie na czacie - ponieważ to lambda (sync), trzeba to wywołać w wątku asynchronicznym pętli bota
            coro = interaction.channel.send(f"🎶 Teraz odtwarzam: **{song['title']}**")
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
            
        except Exception as e:
            logger.error(f"Wystąpił błąd w FFmpeg podczas odtwarzania na serwerze {guild_id}: {e}")
            # Przejdź do kolejnego w przypadku crasha tego pliku
            self.play_next(interaction)


    @app_commands.command(name="play", description="Wyszukaj i odtwórz utwór muzyczny (wspiera nazwy i linki)")
    async def play(self, interaction: discord.Interaction, zapytanie: str):
        logger.info(f"Użytkownik {interaction.user} (G:{interaction.guild.id}) rząda /play [{zapytanie}]")
        
        if not interaction.user.voice:
            await interaction.response.send_message("❌ Musisz dołączyć do kanału głosowego!", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if not voice_client:
            await voice_channel.connect()
            voice_client = interaction.guild.voice_client
            logger.info(f"Dołączono do kanału {voice_channel.name} (G:{interaction.guild.id})")

        # Utrzymuje interakcję przez dłuższy czas (wyszukiwanie yt-dlp bywa wolne, domyślnie Discord daje na to tylko 3s)
        await interaction.response.defer()

        song = await self.search_song(zapytanie)
        if not song:
            logger.error(f"Nie udało się odnaleźć muzyki dla zapytania '{zapytanie}' (G:{interaction.guild.id})")
            await interaction.followup.send("❌ Nie znaleziono utworu lub wystąpił błąd przy pobieraniu strumienia.")
            return

        queue = self.get_queue(interaction.guild.id)
        queue.append(song)
        logger.info(f"Pomyślnie dodano do kolejki utwór: {song['title']} na serwerze (G:{interaction.guild.id})")
        
        # Jeśli nic w tej chwili nie gra, po prostu zacznij odtwarzać to co przed chwilą dodaliśmy do kolejki
        if not voice_client.is_playing() and not voice_client.is_paused():
            await interaction.followup.send(f"🎵 Znaleziono i ładuję: **{song['title']}**...")
            self.play_next(interaction)
        else:
            await interaction.followup.send(f"➕ Dodano do kolejki: **{song['title']}**")

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
        
        if voice_client and voice_client.is_playing():
            # Zatrzymanie voice clienta automatycznie triggeruje callback `after=self.play_next`
            voice_client.stop()
            await interaction.response.send_message("⏭️ Pomyślnie pominięto utwór.")
        else:
            await interaction.response.send_message("Obecnie nie odtwarzam żadnego utworu.", ephemeral=True)

    @app_commands.command(name="queue", description="Pokazuje aktualną kolejkę nadchodzących utworów")
    async def queue(self, interaction: discord.Interaction):
        logger.info(f"Wywołano /queue przez {interaction.user} (G:{interaction.guild.id})")
        queue = self.get_queue(interaction.guild.id)
        
        if not queue:
            await interaction.response.send_message("📜 Kolejka jest w tej chwili całkowicie pusta.")
            return
        
        embed = discord.Embed(title="Kolejka Odtwarzania", color=discord.Color.dark_purple())
        
        # Wyświetlamy max. 10 elementów aby nie złamać limitów znakowych Discorda
        for i, song in enumerate(queue[:10]):
            embed.add_field(name=f"{i+1}. {song['title']}", value="⏳ Oczekuje w kolejce", inline=False)
            
        if len(queue) > 10:
            embed.set_footer(text=f"I {len(queue) - 10} innych piosenek na liście...")
            
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
            embed = discord.Embed(title="Aktualnie odtwarzany utwór", description=f"🎶 **{song['title']}**", color=discord.Color.green())
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("W tej chwili nic nie jest odtwarzane.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Music(bot))
