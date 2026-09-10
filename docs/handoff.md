# Handoff: Instrukcja wdrożeniowa dla Agenta / Programisty

## Cel
Napisanie w pełni funkcjonalnego bota muzycznego na Discorda zgodnie z przygotowaną strukturą plików i założeniami opisanymi w dokumentacji.

## Zakres prac i kroki do zrealizowania (Auto-wykonywane)

1. **Konfiguracja Loggera (`main.py`)**:
   - Skonfiguruj standardowy moduł Pythona `logging`.
   - Zdefiniuj obsługę logowania równolegle na standardowe wyjście (konsola) oraz do pliku `bot.log`.
   - Podepnij logger pod start bota i ładowanie modułów. Wszystkie wyjątki i uruchomienia powinny być odnotowane.

2. **Implementacja Logiki Głosowej (`cogs/music.py`)**:
   - Zaimportuj `yt_dlp` oraz `ytmusicapi`.
   - Zbuduj zaawansowaną konfigurację dla `yt-dlp` (`YTDL_OPTIONS`), w tym włączenie "client spoofingu" (`extractor_args: {'youtube': {'client': ['android', 'web']}}`) – zapobiegnie to błędom 403 i zignoruje blokady wiekowe.
   - Zainicjalizuj instancję `YTMusic()` jako wsparcie przy wyszukiwaniu słownym.

3. **System Kolejki i Odtwarzania**:
   - Zdefiniuj strukturę na serwerowe kolejki, np. słownik `self.queues = {}` (klucz: `guild.id`, wartość: `list`).
   - Napisz asynchroniczną funkcję `search_song(query)`, która:
     - Rozpoznaje czy podano link, czy ciąg znaków.
     - Jeśli link: od razu korzysta z `yt-dlp` do pobrania URL strumienia audio.
     - Jeśli tekst: odpytuje `ytmusicapi` po pierwszy wynik, buduje sztuczny link do Youtube (lub przekazuje go do `yt-dlp`).
   - Zaimplementuj funkcję `play_next(interaction)` obsługiwaną przy callbacku końca odtwarzania przez `FFmpegPCMAudio`. Musi pobierać kolejny utwór z listy.

4. **Komendy**:
   - `/play` - dodanie logiki dołączania do kanału (jeśli bot na nim nie jest), pobranie metadanych utworu, dodanie do kolejki. Następnie uruchomienie `play_next` jeśli bot aktualnie nic nie odtwarza.
   - `/stop` - zatrzymanie utworu, wyczyszczenie pamięci `self.queues` dla tego serwera i wyjście (disconnect) z kanału.
   - `/skip` - przerwanie aktualnego obiektu `voice_client.stop()`, co automatycznie powinno wyzwolić `play_next`.
   - `/queue` - zwrócenie pierwszych kilkunastu elementów z kolejki używając ładnego widoku `discord.Embed`.
   - Każda komenda i jej wynik (sukces/błąd) ma wpisywać log używając zaimplementowanego na początku globalnego loggera (kto, gdzie i co zrobił).

## Instrukcje dla Agenta realizującego to zadanie
**WYKONAJ KROKI OD 1 DO 4 OD RAZU**. Możesz nadpisać istniejące szablony `main.py` oraz `cogs/music.py`.
Pomiń wpisywanie prawdziwych kluczy i tokenów do `.env` - zostaną one uzupełnione przez użytkownika pod koniec pracy. Użyj placeholdera dla tokenu podczas uruchamiania testowego, lub wywołuj kod bez sprawdzania API.
