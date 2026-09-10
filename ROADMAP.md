# 🗺️ SubWoofer — Roadmap & Future Ideas

Ten plik gromadzi pomysły i plany rozwoju bota muzycznego **SubWoofer**.

---

## 💡 Pomysły i Eksperymenty (Research & Prototyping)

### 1. P2P & Torrent / Soulseek Audio Streaming (Fallback do YouTube)
- **Cel:** Zbadanie możliwości bezpośredniego streamingu lub szybkiego cache'owania bezstratnych/wysokiej jakości plików audio ze źródeł rozproszonych / sieci P2P zamiast wyłącznego polegania na YouTube i YouTube Music.
- **Koncepcja:**
  1. Użytkownik wpisuje zapytanie `/play <utwór>`.
  2. Bot w pierwszej kolejności przeszukuje źródła alternatywne (np. sieć Soulseek / P2P).
  3. Jeśli plik audio jest dostępny z dużą prędkością pobierania: buforowanie i bezpośredni streaming przez FFmpeg.
  4. Jeśli źródło jest niedostępne, powolne lub nie znaleziono pliku: automatyczny fallback do YouTube / YouTube Music przez proxy Cloudflare WARP.
- **Materiały i źródła referencyjne:**
  - **Soulseek Network:** [https://www.slsknet.org/](https://www.slsknet.org/) (protokół Soulseek, np. biblioteki Python `slskd` / `pysoulseek` / Soulseek API).
  - **WebTorrent / libtorrent:** buforowanie strumieniowe `piece-by-piece` w locie bezpośrednio do potoku `stdout -> FFmpeg`.
- **Status:** Do analizy wydajnościowej (opóźnienia buforowania vs jakość dźwięku vs przepustowość VPS).
