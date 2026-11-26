# Bloodborne Trainer (bbport, gra 1.09)

Narzędzie do ćwiczenia w stylu SilkySouls. Start: skrót „Bloodborne Trainer” na pulpicie
albo `~/bb-trainer/trainer.py --play`.

**Grę trzeba uruchomić z trainera** (skrótem albo przyciskiem „Uruchom grę”). Do gry
odpalonej inaczej system nie da mu dostępu.

## Co jest
- Gracz: HP, leczenie, zawsze pełne HP / stamina, nieśmiertelność, one-shot, nieskończone
  kule i przedmioty, niewidzialność, cisza.
- Podróż: 5 slotów pozycji, przesuwanie góra/dół, warp do 45 lamp, bossowie (stan,
  wskrzeszenie, oznaczenie jako pokonany, warp przed wejście do walki, własne wejście pinezką).
  Gehrman i Moon Presence: trainer robi kopię zapisu, ustawia flagi fabuły, a po warpie
  gdzie indziej je przywraca. Prawdziwa wygrana kończy grę (NG+); tryb treningowy do tego
  nie dopuszcza.
- Wrogowie: wyłączanie AI i ataków, flagi obrażeń, lista pobliskich (zabij, 1 HP, zamroź).
- Itemy, staty, echa, wgląd, NG+, prędkość gry, wyjście do menu, kopia zapisów.

## Skróty
F5 zapisz pozycję, F6 wczytaj, F7 ulecz, F8 nieśmiertelność, F10 powtórz warp.
Pad: Select/View + krzyżak (góra zapisz, dół wczytaj, lewo ulecz, prawo warp).

## Uwagi
- Zmiany w statach, itemach i flagach bossów zostają w zapisie.
- Nie używać w co-opie online.
- Zamknięcie trainera wyłącza cheaty i oddaje grze oryginalny kod.

## Jak działa
`engine.py` czyta i pisze pamięć procesu `bb-probe`. Wstawka `stub.s` w głównej pętli gry
skaluje czas klatki i wykonuje funkcje gry na jej wątku. Lampy i nazwy przedmiotów
`gamedata.py` czyta z plików gry. Adresy dotyczą tylko wersji 1.09; przed ingerencją
trainer porównuje bajty i przy innej wersji nic nie rusza.

Źródła offsetów: kod BBSC w bbport, nazwy flag z menu debugowego samej gry,
układ statów zgodny z github.com/Noxde/Bloodborne-save-editor.
