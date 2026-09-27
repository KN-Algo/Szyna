# Propozycja: automatyczne strojenie progów jako osobny algorytm

Odpowiedź na pytanie: "jak to zrobić, żeby [strojenie parametrów] automatycznie się zmieniało w postaci
osobnego algorytmu". To jest propozycja projektowa (nie zaimplementowana) — do dyskusji przed budową.

## Mechanizm: "perturb-and-observe" (proste wspinanie po zboczu, bez gradientu)

Rozszerzenie wzorca JUŻ istniejącego w `nauka_kary*` (`_czynnik_nauczony` — jedna liczba adaptowana
raz/dobę na podstawie zliczonych kar) na **kilka progów naraz**, z kierunkiem zmiany zamiast tylko
wielkości:

1. Wybierz zestaw N progów do strojenia (np. dla `risk_function_pid`:
   `RISK_HYSTERESIS_C`, `RISK_SNOW_PENALTY_PER_MM_C`, `hrt_on_precip`).
2. Każdy próg ma własny, mały **krok zmiany** (`krok_i`, np. ±2% wartości bazowej) i **kierunek**
   (+1/-1), inicjalizowany losowo albo od +1.
3. Co `OKRES_STROJENIA_S` (np. 7 dni symulowanego czasu — dłużej niż `OKRES_UCZENIA_S=86400s` w
   `nauka_kary`, żeby zmiana progu zdążyła się wyraźnie objawić w zachowaniu):
   - policz **koszt złożony** minionego okresu: `koszt = energia_kwh + WAGA_KARA * (kara_snieg + kara_lod + kara_przegrzanie)`
     (te same liczniki kar co `funkcja_nauka_kary_wspolna._zarejestruj_kary`),
   - porównaj z kosztem z POPRZEDNIEGO okresu,
   - **jeśli koszt spadł** → zastosuj TEN SAM kierunek zmiany dla każdego progu w kolejnym okresie
     (idziemy dobrze, kontynuuj),
   - **jeśli koszt wzrósł** → **odwróć kierunek** dla każdego progu (przeszliśmy za daleko/w złą
     stronę, zawróć),
   - przesuń każdy próg: `próg_i += kierunek_i * krok_i`, z twardym zakresem (min/max) jak
     `CZYNNIK_NAUCZONY_MIN_C/MAX_C` w istniejącym mechanizmie.
4. Loguj każdą aktualizację (jak `historia_uczenia`) — wartości progów + koszt w czasie, do tej samej
   zakładki "Uczenie_adaptacyjne" w Excelu (już istnieje, obsługuje dowolną krzywą w czasie).

## Dlaczego to, a nie coś bardziej wyrafinowanego (RL, gradient descent)

- **Brak gradientu**: symulacja fizyczna + logika progowa nie jest różniczkowalna w prosty sposób
  (histereza, warunki `if`) — klasyczny gradient descent by tu nie zadziałał bez dodatkowej pracy
  (np. wygładzania/aproksymacji).
- **Spójne z filozofią projektu**: cała rodzina `nauka_kary*` już świadomie wybrała prosty,
  jednowymiarowy integrator kar zamiast formalnego RL ("zaakceptowany z użytkownikiem jako
  wystarczający" — patrz `funkcja_nauka_kary_wspolna.py`) — to rozszerza TEN SAM wzorzec na więcej
  wymiarów, nie wprowadza nowej filozofii.
- **Interpretowalne i bezpieczne**: w każdej chwili widać dokładnie, jakie są aktualne progi i dlaczego
  się zmieniły (log), można ograniczyć zakres (jak floor/ceiling na `_czynnik_nauczony`), można to
  wyłączyć i wrócić do stałych fabrycznych bez utraty reszty logiki.
- **Realistyczne na sterownik**: to jest coś, co dałoby się uruchomić na prawdziwym mikrokontrolerze
  (kilka porównań i dodawań raz na tydzień) — w przeciwieństwie do np. sieci neuronowej.

## Ograniczenia do świadomości

- Może utknąć w **lokalnym minimum** (brak losowej eksploracji poza kierunkiem +1/-1) — rozszerzenie:
  co jakiś czas (np. raz/miesiąc) spróbować losowego "restartu" jednego z progów.
- Potrzebuje **kilku okresów strojenia**, żeby się ustabilizować (podobnie jak `nauka_kary` w testach:
  1.0 → 6.0°C w 9 dni) — nie nadaje się do szybko zmieniających się warunków w obrębie JEDNEGO okresu.
- **Dobór WAGA_KARA jest kluczowy i ręczny** — za duża waga kary = strojenie ignoruje energię, za mała
  = ignoruje bezpieczeństwo (śnieg/lód/przegrzanie). Wymagałoby własnego małego eksperymentu
  kalibracyjnego, analogicznego do tego, co robimy teraz dla progów WPROST.

## Sugerowana nazwa i miejsce w rejestrze

`risk_function_pid_auto` albo `nauka_kary_auto` (zależnie od tego, na bazie którego algorytmu by
powstał — prawdopodobnie na bazie zwycięzcy z pełnego przeglądu, patrz strojenie grid-search w toku),
plik `Algorytmy/funkcja_..._auto_strojenie.py`, dziedziczący po tej samej klasie bazowej co algorytm
źródłowy, z dodatkową metodą `_strojenie_progow(timestamp)` wołaną raz/dobę obok istniejącego
`_aktualizuj_uczenie`.

**Status: ZAIMPLEMENTOWANA** (2026-09-02, na życzenie użytkownika) jako `risk_function_pid_auto` -
patrz [`Algorytmy/funkcja_ryzyka_pid_auto_strojenie.py`](../Algorytmy/funkcja_ryzyka_pid_auto_strojenie.py)
i [`notatki/algorytmy/risk_function_pid_auto.md`](algorytmy/risk_function_pid_auto.md). Zbudowana na
bazie `risk_function_pid` (nie fuzzy_ryzyko/nauka_kary, mimo że te wypadły lepiej w rankingu -
"konkretnie ta funkcja ryzyka" na wyraźne życzenie użytkownika). Zweryfikowana: progi realnie
oscylują zgodnie z logiką hill-climbingu (prześledzone ręcznie na 3 kolejnych aktualizacjach, 25-dniowe
okno). Ograniczenia z sekcji wyżej POTWIERDZONE w praktyce - koszt zaszumiony przez zmienność pogody
między okresami, nie tylko wybór progów.
