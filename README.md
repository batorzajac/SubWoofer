# SubWoofer - Muzyczny Bot na Discorda 🐶🔊

Zaawansowany, ultralekki i w pełni asynchroniczny bot muzyczny dla platformy **Discord**, napisany w języku **Python 3.10+** z wykorzystaniem **discord.py**, **yt-dlp** oraz **ytmusicapi**. Obsługuje odtwarzanie dźwięku w wysokiej jakości, nowoczesne komendy ukośnikowe (Slash Commands), zaawansowane kolejkowanie per-serwer oraz omijanie restrykcji wiekowych bez konieczności logowania kontem YouTube.

---

> 🔗 **Szybkie dodanie bota na serwer Discord:**  
> **[Kliknij tutaj, aby zaprosić bota SubWoofer](https://discord.com/oauth2/authorize?client_id=1539396744234934355&permissions=8&scope=bot+applications.commands)**  
> *(Wymagane uprawnienia administratora lub zarządzania serwerem)*

---

## 🚀 Główne Możliwości i Funkcje

- **Wieloplatformowe źródła dźwięku i obsługa Playlist:** Odtwarzanie pojedynczych utworów oraz całych **playlist YouTube / YouTube Music** i **SoundCloud** (do 500 utworów w kolejce).
- **Inteligentne Leniwe Ładowanie (Lazy Loading):** Import playlist odbywa się błyskawicznie (w ~2 sekundy pobierane są metadane), a bezpośredni strumień audio generowany jest tuż przed startem każdego utworu. Dzięki temu linki nigdy nie wygasają, a YouTube nie nakłada blokad rate-limit.
- **Twardy limit kolejki (500 utworów):** Automatyczna ochrona przed przeciążeniem i spamem – bot powiadamia użytkownika w przypadku próby przekroczenia limitu.
- **Omijanie blokad wiekowych (Age-Restricted Bypass):** Zaawansowany *client spoofing* w `yt-dlp` (emulacja klientów Android/Web), pozwalający na odtwarzanie materiałów z restrykcją 18+ całkowicie bez logowania czy konieczności eksportu ciasteczek.
- **Wielopoziomowe Wyszukiwanie:** Błyskawiczne dopasowywanie utworów i metadanych przez `ytmusicapi` z automatycznym przełączaniem (fallback) na ogólną wyszukiwarkę `yt-dlp` w razie nietypowych tytułów.
- **Dynamiczny System Kolejkowania (Queue):** Niezależna kolejka odtwarzania w pamięci podręcznej dla każdego serwera Discord, automatyczne odtwarzanie kolejnych pozycji i powiadomienia na czacie.
- **Nowoczesne Komendy Ukośnikowe (Slash Commands):** Pełna integracja z API Discorda, automatyczne podpowiedzi parametrów i brak konieczności wpisywania prefiksów tekstowych.
- **Wsparcie dla nowego protokołu DAVE:** Pełna obsługa biblioteki `davey` wymaganej przez Discord do szyfrowania end-to-end połączeń głosowych.
- **Gotowość do wdrożenia (Production Ready):** Kompletna konfiguracja pod Dockera (`Dockerfile`, `docker-compose.yml`) oraz gotowy plik usługi systemowej `systemd` pod serwery VPS Linux.
- **Kompleksowe Logowanie:** Automatyczny zrzut zdarzeń, akcji użytkowników i ewentualnych wyjątków do pliku `bot.log` oraz na konsolę.

---

## 📋 Dostępne Komendy (Slash Commands)

| Komenda | Parametry | Opis |
| :--- | :--- | :--- |
| `/play` | `zapytanie` *(tekst lub URL)* | Wyszukuje utwór lub pobiera strumień z linku i rozpoczyna odtwarzanie bądź dodaje go do kolejki |
| `/pause` | *brak* | Wstrzymuje odtwarzanie aktualnego utworu |
| `/resume` | *brak* | Wznawia wstrzymane odtwarzanie |
| `/skip` | *brak* | Pomija bieżący utwór i natychmiast przechodzi do kolejnego z kolejki |
| `/skipto` | `pozycja` *(liczba od 1)* | Przeskakuje bezpośrednio do wybranego numeru w kolejce |
| `/playnext` | `pozycja` *(liczba od 1)* | Przenosi wybrany utwór z kolejki na pierwsze miejsce (zagra jako następny) |
| `/repeat` | *brak* | Włącza lub wyłącza powtarzanie (zapętlenie) całej kolejki utworów |
| `/shuffle` | *brak* | Przelosowuje kolejność wszystkich utworów w kolejce |
| `/stop` | *brak* | Zatrzymuje muzykę, czyści całą kolejkę serwera i odłącza bota od kanału głosowego |
| `/queue` | *brak* | Wyświetla listę oczekujących utworów oraz stan zapełnienia (do 500) w Discord Embed |
| `/nowplaying` | *brak* | Wyświetla szczegóły i link aktualnie odtwarzanego utworu |
| `/setchannel` | `kanal` *(opcjonalnie)* | Ogranicza komendy bota do wybranego kanału tekstowego (lub usuwa ograniczenie) |

---

## 🛠️ Stos Technologiczny (Tech Stack)

* **Język:** Python 3.10+
* **Framework bota:** `discord.py 2.7+` (obsługa Cogs, App Commands / Slash Commands)
* **Ekstrakcja i streaming audio:** `yt-dlp` (z zaawansowaną konfiguracją extractor_args)
* **Wyszukiwanie muzyczne:** `ytmusicapi` (nieoficjalne API YouTube Music)
* **Transkodowanie dźwięku:** `FFmpeg` (poprzez `discord.FFmpegPCMAudio`)
* **Szyfrowanie głosu:** `PyNaCl` + `davey` (protokół Discord DAVE)
* **Zarządzanie konfiguracją:** `python-dotenv`
* **Konteneryzacja:** Docker & Docker Compose

---

## 📂 Struktura Projektu

```text
bot muzyczny/
├── cogs/
│   ├── __init__.py             # Inicjalizacja pakietu modułów
│   └── music.py                # Moduł odtwarzacza, kolejki i komend muzycznych
├── deploy/
│   ├── bot-muzyczny.service    # Konfiguracja usługi systemd pod Linux VPS
│   └── deploy_readme.md        # Przewodnik wdrożeniowy krok po kroku
├── docs/
│   ├── dokumentacja.md         # Szczegółowa dokumentacja bibliotek i funkcji
│   ├── handoff.md              # Instrukcja wdrożeniowa dla dewelopera / agenta
│   └── testy_behawioralne.md   # Zestaw scenariuszy testowych (8 testów)
├── .env.example                # Wzorzec konfiguracji zmiennych środowiskowych
├── .gitignore                  # Pliki ignorowane przez repozytorium git
├── Dockerfile                  # Obraz kontenera z wbudowanym FFmpeg
├── docker-compose.yml          # Konfiguracja orkiestracji kontenera
├── LICENSE                     # Licencja GNU GPL v3
├── main.py                     # Główny punkt startowy bota i logger
├── README.md                   # Ten plik dokumentacji
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

### 2. Wymóg FFmpeg
* **Windows:** Zainstaluj przez `winget install Gyan.FFmpeg.Essentials` lub umieść `ffmpeg.exe` w folderze bota. *(Aplikacja automatycznie odświeża ścieżkę z rejestru systemowego)*.
* **Linux (Ubuntu/Debian):** `sudo apt update && sudo apt install -y ffmpeg`

### 3. Konfiguracja tokenu
Skopiuj plik `.env.example` do `.env`:
```bash
cp .env.example .env
```
Otwórz `.env` i wklej swój token z [Discord Developer Portal](https://discord.com/developers/applications).

### 4. Uruchomienie bota
```bash
python main.py
```

---

## 🐳 Wdrożenie i Hosting (Docker)

Najprostszą metodą hostingu produkcyjnego 24/7 jest Docker, który sam pobiera i konfiguruje odpowiednią wersję Pythona oraz FFmpeg:

```bash
docker-compose up -d --build
```

Podgląd logów w czasie rzeczywistym:
```bash
docker-compose logs -f
```

---

## 📄 Licencja

Projekt dystrybuowany na warunkach licencji **GNU General Public License v3.0 (GPL-3.0)**. Szczegóły w pliku [LICENSE](LICENSE).
