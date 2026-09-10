# Dokumentacja Bota Muzycznego (SubWoofer) 🐶🔊

> 🔗 **Link do zaproszenia bota na Twój serwer Discord:**  
> **[Kliknij tutaj, aby dodać bota SubWoofer](https://discord.com/oauth2/authorize?client_id=1539396744234934355&permissions=8&scope=bot+applications.commands)**  
> *(Wymaga uprawnień do zarządzania serwerem lub administratora)*

---

## Wykorzystane Biblioteki

### 1. discord.py
Główna biblioteka napisana w Pythonie, będąca interfejsem (wrapperem) dla oficjalnego API Discorda. Służy do łączenia bota z platformą, nasłuchiwania zdarzeń (np. wiadomości), obsługi komend slash (`/play`, `/stop`) oraz zarządzania interakcjami głosowymi.

### 2. yt-dlp
Najpotężniejsze i najszybciej aktualizowane narzędzie i biblioteka Pythona do wyciągania strumieni audio. W projekcie odpowiada za pozyskiwanie bezpośrednich linków do surowych plików dźwiękowych z serwerów YouTube oraz SoundCloud. Używamy jej ze specjalną konfiguracją tzw. _client spoofing_ (np. udając klienta Android lub iOS), co pozwala omijać zabezpieczenia wiekowe YouTube całkowicie bez logowania.

### 3. ytmusicapi
Nieoficjalne API do platformy YouTube Music. Umożliwia precyzyjne wyszukiwanie utworów, albumów i playlist z wykorzystaniem ekosystemu muzycznego. Pobrane stąd metadane są następnie rzucane do `yt-dlp`, co przyspiesza cały proces w stosunku do standardowego wyszukiwania.

### 4. PyNaCl
Biblioteka dostarczająca wiązania do narzędzi kryptograficznych. Jest to bezwzględny wymóg `discord.py` – wszystkie dane wysyłane na kanały głosowe Discorda muszą być szyfrowane używając protokołów Sodium/NaCl.

### 5. davey
Biblioteka wymagana przez najnowsze wersje `discord.py` (2.5+) do obsługi nowego protokołu szyfrowania transmisji głosowej Discorda (DAVE - Discord Audio/Video End-to-End Encryption). Bez niej bot nie może połączyć się z kanałami głosowymi.

### 6. python-dotenv
Mała biblioteka do bezpiecznego wczytywania zmiennych środowiskowych z pliku `.env`. Pozwala na ukrycie sekretnego Tokenu Bota, zapobiegając jego wyciekowi podczas dzielenia się kodem.

### 7. FFmpeg
Choć nie jest to biblioteka Pythona, lecz samodzielne narzędzie systemowe, jest kluczowe w procesie odtwarzania. W tle konwertuje strumień danych przechwytywany przez `yt-dlp` na format audio, który akceptuje Discord (Opus). Zainstalowany w systemie i automatycznie wykrywany.

## Dostępne Komendy (Slash Commands)
* `/play [zapytanie]` - Wyszukuje utwór na YouTube Music / YouTube, przyjmuje bezpośredni link lub link do całej playlisty (obsługa do 500 utworów w kolejce z mechanizmem Lazy Loading).
* `/pause` - Wstrzymuje aktualnie odtwarzany utwór.
* `/resume` - Wznawia wstrzymany utwór.
* `/skip` - Pomija bieżący utwór i natychmiast odtwarza kolejny z kolejki.
* `/skipto [pozycja]` - Przeskakuje bezpośrednio do wskazanego utworu w kolejce (od 1 do N).
* `/playnext [pozycja]` - Ustawia wybrany utwór z kolejki na pierwsze miejsce (zagra jako następny).
* `/repeat` - Włącza lub wyłącza powtarzanie (zapętlenie) całej kolejki utworów.
* `/shuffle` - Przelosowuje kolejność wszystkich utworów w kolejce.
* `/stop` - Zatrzymuje odtwarzanie, czyści całą kolejkę serwera i odłącza bota od kanału głosowego.
* `/queue` - Wyświetla listę oczekujących utworów oraz stan zapełnienia kolejki (np. 42/500) w estetycznym oknie Discord Embed.
* `/nowplaying` - Wyświetla tytuł i link obecnie granego utworu.
* `/setchannel [kanał]` - Ogranicza komendy bota do wybranego kanału tekstowego (lub usuwa ograniczenie).

## Główne Cechy
* **Obsługa całych Playlist i Lazy Loading:** Bot potrafi wczytać całe playlisty z YouTube/SoundCloud w 1-2 sekundy. Bezpośredni link strumieniowy wyciągany jest tuż przed startem utworu, dzięki czemu linki nigdy nie wygasają, a YouTube nie blokuje IP.
* **Limit 500 utworów:** Zabezpieczenie chroniące przed niekontrolowanym rozrostem kolejki z informowaniem użytkownika o przekroczeniu limitu.
* **Zarządzanie odtwarzaniem:** Pełen zestaw komend sterujących (`/play`, `/pause`, `/resume`, `/skip`, `/stop`, `/queue`, `/nowplaying`).
* **Dynamiczny System Kolejkowania (Queue):** Każdy serwer otrzymuje własną niezależną kolejkę utworów w pamięci podręcznej.
* **Integracja z kanałami głosowymi:** Mechanizm sprawdzania obecności użytkownika na kanale, automatyczne dołączanie i płynne przejścia.
* **Bypass limitów YouTube:** Wsparcie dla odtwarzania materiałów 18+ (Age-Restricted) z Youtube Music poprzez spoofing klientów (Android/Web) bez konieczności podawania ciasteczek czy logowania.
* **Wielopoziomowe Wyszukiwanie:** Szybkie zapytania przez `ytmusicapi` z automatycznym fallbackiem do ogólnego wyszukiwania `yt-dlp` w razie nietypowych tytułów.
