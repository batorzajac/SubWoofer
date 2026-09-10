# Wdrożenie Bota Muzycznego (Deploy)

Dla ułatwienia przygotowałem gotowe pliki wspierające dwie najpopularniejsze metody hostowania bota (np. na serwerach VPS z systemem Linux - Ubuntu/Debian).

## Opcja 1: Docker (Rekomendowana)
Najbezpieczniejsza i najmniej awaryjna opcja, nie śmieci w systemie operacyjnym i dba o to, by odpowiednia wersja Pythona i FFmpeg zawsze tam była.

1. Wgraj zawartość folderu bota na serwer.
2. Upewnij się, że masz uzupełniony Token w pliku `.env`.
3. W folderze z projektem wykonaj:
   ```bash
   docker-compose up -d --build
   ```
Twój bot jest już online i sam wznowi pracę po ewentualnym crashu lub ponownym uruchomieniu serwera.

## Opcja 2: Usługa Systemd (Klasycznie - bez Dockera)
Jeśli wolisz zainstalować pakiety klasycznie i stworzyć proces systemowy w systemie operacyjnym:

1. Przenieś folder z botem do np. `/opt/subwoofer` na serwerze.
2. Zainstaluj FFmpeg i Pythona:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-venv python3-pip ffmpeg
   ```
3. Utwórz wirtualne środowisko (venv) i zainstaluj zależności w folderze z botem:
   ```bash
   cd /opt/subwoofer
   python3 -m venv venv
   ./venv/bin/pip install -r requirements.txt
   ```
4. Przekopiuj przygotowany plik usługi do procesów systemowych:
   ```bash
   sudo cp deploy/subwoofer.service /etc/systemd/system/
   ```
5. Aktywuj i uruchom bota!
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable subwoofer
   sudo systemctl start subwoofer
   ```
