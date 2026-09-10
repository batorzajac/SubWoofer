# SubWoofer - Muzyczny Bot na Discorda 🐶🔊

[🇵🇱 **Polska wersja**](README.md) | [🇬🇧 **English version**](README_EN.md)

---

Zaawansowany, ultralekki i w pełni asynchroniczny bot muzyczny dla platformy **Discord**, napisany w języku **Python 3.11+** z wykorzystaniem **discord.py**, **yt-dlp**, **ytmusicapi** oraz **aiohttp**. Obsługuje odtwarzanie dźwięku w wysokiej jakości, nowoczesne komendy ukośnikowe (Slash Commands), zaawansowane kolejkowanie per-serwer, interaktywny Dashboard, wsparcie dla linków Spotify, regulację głośności, auto-disconnect oraz omijanie restrykcji YouTube i datacenter bez konieczności logowania.

---

## 🚀 Główne Możliwości i Funkcje

- **Wieloplatformowe źródła dźwięku i obsługa Playlist:** Odtwarzanie pojedynczych utworów oraz całych playlist i albumów z **YouTube**, **YouTube Music**, **Spotify** (`open.spotify.com`) oraz **SoundCloud** (do 500 utworów w kolejce).
- **Inteligentne Leniwe Ładowanie (Lazy Loading):** Import playlist i albumów odbywa się błyskawicznie (w ~2 sekundy pobierane są metadane), a bezpośredni strumień audio generowany jest tuż przed startem każdego utworu. Dzięki temu linki nigdy nie wygasają, a bot nie jest blokowany przez limity zapytań.
- **Wsparcie dla Spotify:** Bezpośrednia obsługa linków do utworów, playlist i albumów ze Spotify bez wymogu rejestrowania aplikacji czy podawania kluczy API.
- **Interaktywne Wyszukiwanie (`/search`):** Wyszukiwanie na żywo zwracające 5 najlepiej dopasowanych filmów i utworów (z wykluczeniem kanałów i playlist) w postaci rozwijanego menu Discord Select Menu.
- **Automatyczne Rozłączanie (`/autoleave`):** Jeśli wszyscy użytkownicy opuszczą kanał głosowy, bot odczekuje określony czas (domyślnie 10 minut) i bezpiecznie się rozłącza, oszczędzając zasoby serwera. Czas i stan funkcji można konfigurować komendą.
- **Regulacja Głośności (`/volume`):** Płynna zmiana głośności odtwarzacza w czasie rzeczywistym w skali 0–100% z trwałym zapisem per-serwer.
- **Twardy limit kolejki (500 utworów):** Automatyczna ochrona przed przeciążeniem i spamem – bot powiadamia użytkownika w przypadku próby przekroczenia limitu.
- **Interaktywny Panel Dashboardu (`/dashboard`):** Trwały panel przycisków pod odtwarzaczem (Play/Pause, Skip, Shuffle, Repeat, Stop, Queue, Refresh, Help) działający nieprzerwanie nawet po restartach bota.
- **Stronicowana Kolejka (`/queue`):** Przejrzysta lista utworów podzielona na strony po 10 pozycji wraz z przyciskami nawigacji `◀️`, wskaźnikiem stron i przyciskiem losowania `🔀`.
- **Narzędzia Diagnostyczne:** Wbudowane komendy diagnostyczne (`/ping`, `/status` z pomiarem RAM i uptime, `/logs` z filtrem na błędy dla administratorów).
- **Bezpieczeństwo Logów:** Rotacja plików `bot.log` (`RotatingFileHandler`, max 10 MB, do 5 plików archiwalnych) zapobiegająca zapełnieniu dysku VPS.
- **Wsparcie dla protokołu DAVE:** Pełna obsługa biblioteki `davey` wymaganej przez Discord do szyfrowania end-to-end (E2EE) połączeń głosowych.
- **Omijanie blokad YouTube:** Wbudowany silnik Deno oraz obsługa tunelu proxy (np. Cloudflare WARP / Privoxy) w konfiguracji Docker do bezproblemowego streamingu z serwerów VPS.

---

## 📋 Dostępne Komendy (Slash Commands)

Wszystkie komendy i ich parametry są w języku angielskim:

| Komenda | Parametry | Opis |
| :--- | :--- | :--- |
| `/play` | `query` *(tekst lub URL)* | Odtwarza utwór lub dodaje playlistę/album do kolejki (YouTube, YouTube Music, Spotify) |
| `/search` | `query` *(fraza)* | Wyszukuje 5 najlepszych filmów/utworów na YouTube i wyświetla menu wyboru |
| `/nowplaying` | *brak* | Wyświetla szczegóły, czas i link aktualnie odtwarzanego utworu |
| `/pause` | *brak* | Wstrzymuje odtwarzanie aktualnego utworu |
| `/resume` | *brak* | Wznawia wstrzymane odtwarzanie |
| `/volume` | `level` *(0–100)* | Ustawia głośność odtwarzacza w procentach |
| `/skip` | *brak* | Pomija bieżący utwór i przechodzi do następnego w kolejce |
| `/skipto` | `position` *(numer od 1)* | Przeskakuje bezpośrednio do wskazanego numeru w kolejce |
| `/playnext` | `position` *(numer od 1)* | Przenosi wybrany utwór z kolejki na pierwsze miejsce (zagra jako następny) |
| `/shuffle` | *brak* | Losowo miesza kolejność wszystkich utworów w kolejce |
| `/repeat` | *brak* | Włącza lub wyłącza zapętlenie bieżącej kolejki |
| `/stop` | *brak* | Zatrzymuje muzykę, czyści całą kolejkę i odłącza bota od kanału głosowego |
| `/queue` | *brak* | Wyświetla interaktywną listę oczekujących utworów ze stronicowaniem |
| `/dashboard` | `action` *(on / off)* | Włącza lub wyłącza stały, interaktywny panel sterowania na kanale |
| `/setchannel` | `channel` *(opcjonalnie)* | Ogranicza komendy bota do wybranego kanału tekstowego (lub resetuje) |
| `/autoleave` | `action`, `minutes` | Konfiguruje auto-rozłączanie przy pustym kanale (`status`, `enable`, `disable`) |
| `/ping` | *brak* | Sprawdza opóźnienie Discord Gateway oraz Voice WebSocket w milisekundach |
| `/status` | *brak* | Wyświetla czas działania (uptime), zużycie pamięci RAM i wersje komponentów |
| `/logs` | `filter`, `lines` | Podgląd ostatnich logów lub błędów (tylko dla Administratorów) |
| `/help` | *brak* | Wyświetla interaktywne menu pomocy (działa również prefiks `!help`) |

---

## 🛠️ Stos Technologiczny (Tech Stack)

* **Język:** Python 3.11+
* **Framework bota:** `discord.py 2.7+` (obsługa Cogs, App Commands / Slash Commands, Persistent UI Views)
* **Ekstrakcja i streaming audio:** `yt-dlp` (z silnikiem JS Deno i wsparciem proxy)
* **Klient Spotify:** Asynchroniczny parser metadanych (`aiohttp`)
* **Wyszukiwanie muzyczne:** `ytmusicapi` (oficjalny ekosystem YouTube Music)
* **Transkodowanie dźwięku:** `FFmpeg` (poprzez `discord.FFmpegPCMAudio` i `PCMVolumeTransformer`)
* **Szyfrowanie głosu:** `PyNaCl` + `davey` (protokół Discord DAVE E2EE)
* **Konteneryzacja:** Docker & Docker Compose

---

## 📂 Struktura Projektu

```text
SubWoofer/
├── cogs/
│   ├── __init__.py             # Inicjalizacja pakietu modułów
│   └── music.py                # Główny moduł odtwarzacza, kolejki, dashboardu i komend
├── deploy/
│   ├── deploy_readme.md        # Przewodnik wdrożeniowy krok po kroku
│   └── subwoofer.service       # Konfiguracja usługi systemd pod Linux VPS
├── docs/
│   ├── dokumentacja.md         # Szczegółowa dokumentacja bibliotek i funkcji
│   ├── handoff.md              # Instrukcja wdrożeniowa dla dewelopera / agenta
│   └── testy_behawioralne.md   # Zestaw scenariuszy testowych
├── .env.example                # Wzorzec konfiguracji zmiennych środowiskowych
├── .gitignore                  # Pliki ignorowane przez repozytorium git
├── Dockerfile                  # Obraz kontenera (Python 3.11 + FFmpeg + Deno + Node.js)
├── docker-compose.yml          # Konfiguracja orkiestracji kontenera Docker
├── LICENSE                     # Licencja GNU General Public License v3.0
├── main.py                     # Główny punkt startowy bota, logger z rotacją i sync
├── README.md                   # Dokumentacja w języku polskim
├── README_EN.md                # Dokumentacja w języku angielskim
└── requirements.txt            # Zależności bibliotek Pythona
```

---

## ⚡ Szybki Start (Lokalnie na Windows / Linux)

### 1. Klonowanie i przygotowanie środowiska
```bash
git clone https://github.com/batorzajac/SubWoofer.git
cd SubWoofer
python -m venv venv
```

Aktywacja wirtualnego środowiska:
* **Windows (PowerShell):** `.\venv\Scripts\Activate.ps1`
* **Linux / macOS:** `source venv/bin/activate`

Instalacja zależności:
```bash
pip install -r requirements.txt
```

### 2. Wymagania systemowe (FFmpeg i Deno / Node.js)
* **FFmpeg** (wymagany do transkodowania dźwięku):
  * **Windows:** `winget install Gyan.FFmpeg.Essentials` lub umieść `ffmpeg.exe` w folderze bota.
  * **Linux (Ubuntu/Debian):** `sudo apt update && sudo apt install -y ffmpeg`
* **Deno / Node.js** (wymagane przez yt-dlp do rozwiązywania skryptów JavaScript YouTube):
  * **Windows:** `winget install DenoLand.Deno` lub [nodejs.org](https://nodejs.org/).
  * **Linux:** `curl -fsSL https://deno.land/install.sh | sh`

### 3. Konfiguracja tokenu
Skopiuj plik `.env.example` do `.env`:
```bash
cp .env.example .env
```
Wklej swój token bota z [Discord Developer Portal](https://discord.com/developers/applications):
```env
DISCORD_TOKEN=twoj_token_tutaj
```

### 4. Uruchomienie bota
```bash
python main.py
```

---

## 🐳 Wdrożenie i Hosting 24/7 (Docker)

Najprostszą i najbardziej niezawodną metodą hostingu 24/7 na VPS jest Docker:

```bash
docker compose up -d --build
```

Podgląd logów na żywo:
```bash
docker compose logs -f
```

Zatrzymanie bota:
```bash
docker compose down
```

---

## 📄 Licencja

Projekt dystrybuowany na warunkach licencji **GNU General Public License v3.0 (GPL-3.0)**. Szczegóły w pliku [LICENSE](LICENSE).
