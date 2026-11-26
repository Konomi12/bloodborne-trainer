# Bloodborne Trainer dla bbporta (Linux)

Narzędzie do ćwiczenia w stylu SilkySouls dla Bloodborne na
[bbporcie](https://github.com/deadinside28/bloodborne_pc). Pełna instrukcja po angielsku:
[README.md](README.md).

## Instalacja
### AppImage (najprościej)
Pobierz `bb-trainer-…-x86_64.AppImage` z
[Releases](https://github.com/Konomi12/bb-trainer/releases). Ma w środku własnego Pythona,
GTK 4 i libadwaita, więc nie trzeba ich instalować. Potem:

```bash
chmod +x bb-trainer-*-x86_64.AppImage
./bb-trainer-*-x86_64.AppImage --install
```

`--install` dodaje skrót do menu (`--install --desktop` także na pulpit, `--uninstall` usuwa).
Plik można też po prostu uruchomić.

### Ze źródeł
Potrzebne: 64-bitowy Linux, bbport (AppImage, folder albo źródła; najpierw uruchom grę raz z
jego launchera), własny zrzut gry w wersji **1.09** oraz Python, GTK 4 i libadwaita 1.5+
(komendy dla dystrybucji są w README.md).

W folderze trainera:

```bash
./install.py
```

Dodaje skrót do menu (`--desktop` także na pulpit, `--uninstall` usuwa).

## Użycie
Otwórz trainer, naciśnij **Uruchom grę** i wczytaj postać. **Grę trzeba uruchomić z trainera**,
inaczej system nie da mu do niej dostępu. Jeśli trainer nie znajdzie bbporta albo wybierze zły,
wskaż go w zakładce **Gra → Ustawienia**; tam też zmienisz język.

## Co jest
- Gracz: HP, leczenie, zawsze pełne HP / stamina, nieśmiertelność, one-shot, nieskończone
  kule i przedmioty, niewidzialność, cisza.
- Podróż: 5 slotów pozycji, przesuwanie góra/dół, warp do lamp, bossowie (stan, wskrzeszenie,
  oznaczenie jako pokonany, warp przed wejście do walki, własne wejście pinezką). Gehrman i
  Moon Presence: trainer robi kopię zapisu, ustawia flagi fabuły, a po warpie gdzie indziej je
  przywraca. Prawdziwa wygrana kończy grę (NG+); tryb treningowy do tego nie dopuszcza.
- Wrogowie: wyłączanie AI i ataków, flagi obrażeń, lista pobliskich (zabij, 1 HP, zamroź).
- Itemy w grupach, broń (z ulepszeniem i wariantem) i stroje, staty, echa, wgląd, NG+.
- Gra: prędkość, hitboxy ataków, wyjście do menu, kopia zapisów.

## Skróty
F5 zapisz pozycję, F6 wczytaj, F7 ulecz, F8 nieśmiertelność, F10 powtórz warp.
Pad: Select/View + krzyżak (góra zapisz, dół wczytaj, lewo ulecz, prawo warp).

## Uwagi
- Zmiany w statach, itemach i flagach bossów zostają w zapisie.
- Nie używać w grze online.
- Zamknięcie trainera wyłącza cheaty i oddaje grze oryginalny kod.

## Licencja
[GPL-2.0-or-later](LICENSE), taka jak bbporta. Bez gwarancji.
