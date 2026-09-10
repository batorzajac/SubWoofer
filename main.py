import discord
from discord.ext import commands
import os
import logging
from dotenv import load_dotenv

# Wczytanie zmiennych środowiskowych
load_dotenv()

# Odświeżenie zmiennej PATH z rejestru Windows (aby natychmiast wykryć FFmpeg bez restartu systemu)
if os.name == 'nt':
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Environment') as key:
            user_path, _ = winreg.QueryValueEx(key, 'Path')
            for p in user_path.split(';'):
                if p and p not in os.environ.get('PATH', ''):
                    os.environ['PATH'] = p + ';' + os.environ.get('PATH', '')
    except Exception:
        pass

# ==========================================
# KONFIGURACJA SYSTEMU LOGOWANIA (DEBUG/INFO)
# ==========================================
logger = logging.getLogger('musicbot')
logger.setLevel(logging.INFO)

# Formater logów (data, nazwa loggera, poziom, wiadomość)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Zapis do pliku
file_handler = logging.FileHandler('bot.log', encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Wypisywanie na konsolę (terminal)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# Podpięcie biblioteki discordowej pod nasz globalny system (żeby zrzucić błędy Discord API)
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.WARNING)
discord_logger.addHandler(file_handler)
discord_logger.addHandler(stream_handler)


class MusicBot(commands.Bot):
    def __init__(self):
        # Definicja uprawnień bota (Intents)
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(command_prefix='!', intents=intents, help_command=None)

    async def setup_hook(self):
        logger.info("System startuje... Wczytywanie modułów.")
        try:
            await self.load_extension('cogs.music')
            logger.info("Moduł 'cogs.music' wczytany poprawnie.")
        except Exception as e:
            logger.error(f"Błąd przy ładowaniu modułu muzycznego: {e}")
            
        logger.info("Synchronizowanie Slash Commands z serwerami Discorda...")
        await self.tree.sync()
        logger.info("Synchronizacja zakończona.")

    async def on_ready(self):
        logger.info('===================================')
        logger.info(f'Zalogowano pomyslnie jako: {self.user}')
        logger.info(f'Bot ID: {self.user.id}')
        if self.guilds:
            logger.info('Podłączone serwery:')
            for g in self.guilds:
                logger.info(f' - {g.name} (ID: {g.id})')
        else:
            logger.info('Bot nie jest jeszcze dodany do żadnego serwera!')
        logger.info('Oczekuje na komendy od uzytkownikow!')
        logger.info('===================================')

        # Wyczyszczenie statusu obecności po restarcie (jeśli bot nic nie odtwarza)
        try:
            if not any(vc.is_playing() for vc in self.voice_clients):
                await self.change_presence(activity=None, status=discord.Status.online)
                logger.info("Zresetowano status profilu bota (brak aktywnego odtwarzania).")
        except Exception as e:
            logger.warning(f"Błąd resetowania obecności w on_ready: {e}")

        # Błyskawiczna synchronizacja komend bezpośrednio dla podłączonych serwerów (Guild Sync)
        # Dzięki temu komendy pojawiają się na serwerze od razu, bez czekania do 1h na globalny cache Discorda
        for g in self.guilds:
            try:
                self.tree.copy_global_to(guild=g)
                await self.tree.sync(guild=g)
                logger.info(f"Błyskawicznie zsynchronizowano Slash Commands dla serwera: {g.name} (ID: {g.id})")
            except Exception as e:
                logger.warning(f"Błąd synchronizacji komend dla serwera {g.name}: {e}")

if __name__ == '__main__':
    bot = MusicBot()
    token = os.getenv('DISCORD_TOKEN')
    
    if token and "podaj_tutaj" not in token:
        logger.info("Wykryto token w .env, trwa łączenie...")
        # log_handler=None zapobiega nadpisywaniu naszych ustawień logowania
        bot.run(token, log_handler=None)
    else:
        logger.critical("BŁĄD: Nie znaleziono poprawnego tokenu w pliku .env!")
        logger.critical("Uzupełnij plik .env poprawnym kluczem z Discord Developer Portal i uruchom ponownie.")
