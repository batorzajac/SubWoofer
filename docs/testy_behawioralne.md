# Testy Behawioralne - Bot Muzyczny

Poniższa lista weryfikuje poprawność i odporność napisanego bota. Należy przejść przez wszystkie scenariusze po wprowadzeniu Tokena i uruchomieniu aplikacji.

### Scenariusz 1: Odmowa współpracy poza kanałem głosowym
1. Będąc na dowolnym kanale tekstowym, bez dołączania na kanał głosowy, wpisz `/play Eminem`.
2. **Oczekiwany rezultat:** Bot natychmiast odpowiada komunikatem błędu (z widocznością tylko dla Ciebie), z informacją, że musisz być połączony z kanałem głosowym. Nic nie trafia do logów błędów (to poprawne zachowanie użytkownika).

### Scenariusz 2: Podstawowe odtwarzanie utworu (wyszukiwanie po tytule)
1. Dołącz do kanału głosowego na serwerze testowym.
2. Wpisz komendę `/play Never Gonna Give You Up`.
3. **Oczekiwany rezultat:** Bot dołącza do Twojego kanału głosowego, wyświetla komunikat o wyszukiwaniu, a następnie o odtwarzaniu utworu Ricka Astleya. W pliku `bot.log` pojawia się precyzyjny wpis informujący o dodaniu do kolejki i odtwarzaniu przez `yt-dlp`. Muzyka gra poprawnie, bez zacinania.

### Scenariusz 3: Dodawanie do kolejki (Kolejkowanie)
1. Gdy gra utwór z poprzedniego scenariusza, wpisz drugą komendę: `/play Zwiastun Cyberpunk 2077`.
2. **Oczekiwany rezultat:** Aktualnie grająca muzyka nie zostaje przerwana. Bot zwraca wiadomość tekstową informującą o tym, że nowy materiał ("Zwiastun Cyberpunk...") został dodany do kolejki.

### Scenariusz 4: Wyświetlanie poprawnej kolejki
1. Wpisz komendę `/queue`.
2. **Oczekiwany rezultat:** Zwracana jest przejrzysta, ładna wiadomość (embed) pokazująca, że w oczekiwaniu jest tylko 1 utwór (ten wpisany w kroku 3).

### Scenariusz 5: Funkcja pomijania (Skip)
1. Wpisz komendę `/skip`.
2. **Oczekiwany rezultat:** Aktualnie odtwarzany utwór urywa się. Bot wysyła wiadomość o pominięciu utworu i automatycznie z automatu wczytuje zwiastun Cyberpunk, wysyłając komunikat "Teraz odtwarzam: ...".

### Scenariusz 6: Wymuszony Stop i wyrzucenie bota
1. Wpisz komendę `/stop`.
2. **Oczekiwany rezultat:** Zwiastun Cyberpunka przestaje grać. Kolejka zostaje bezpowrotnie usunięta w pamięci, a bot rozłącza się (wychodzi) z kanału głosowego.

### Scenariusz 7: Utwór Age-Restricted (Blokada 18+)
1. Będąc na kanale głosowym wpisz komendę z linkiem objętym restrykcjami wiekowymi (bez logowania w przeglądarce się go nie obejrzy). W razie braku, wpisz `/play https://www.youtube.com/watch?v=F3t21Xv01S4` (Przykład materiału, który bywał 18+).
2. **Oczekiwany rezultat:** Bot NIE rzuca błędem 403 (Sign In to confirm your age). Spoofing za pomocą Android-client na poziomie `yt-dlp` obchodzi blokadę. Bot normalnie odtwarza piosenkę na kanale głosowym.

### Scenariusz 8: Błędne odwołanie do kanału (Edge-case)
1. Wpisz komendę `/queue` na pustym serwerze (tuż po uruchomieniu bota).
2. **Oczekiwany rezultat:** Aplikacja się nie wywala, bot uprzejmie informuje, że "kolejka jest pusta". W konsoli aplikacji/pliku `.log` nie pojawiają się rzucone błędy Pythona typu `KeyError` lub `IndexError`.
