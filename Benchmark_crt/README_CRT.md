# Benchmark_crt

Samodzielna, **pełna kopia** projektu `Benchmark/benchmark` (2026-09-26, na życzenie
użytkownika: "nowy folder do całości tylko na testy z tym CRT"), dedykowana wyłącznie
testom na obiekcie z transmitancjami zidentyfikowanymi z REALNYCH danych urządzenia
z Wrocławia Popowice (patrz `Identyfikacja/notatki_identyfikacja/wyniki.md`), zamiast
dotychczasowych stałych z `main_test.py`/`Identyfikacja_obiektu/`.

**Oryginalny `Benchmark/benchmark/` pozostaje w 100% nietknięty** — to dwa całkowicie
niezależne projekty, żaden nie odwołuje się do drugiego.

## Co się zmieniło względem oryginału

- `benchmark/symulacja_fizyczna.py` — obie transmitancje obiektu (AT→CRT, moc→ΔHRT)
  podmienione na wartości z realnych danych (patrz nagłówek pliku po szczegóły i R²).
- `benchmark/Algorytmy/` — dodane 4 warianty `fuzzy_ryzyko_2v2`/`fuzzy_ryzyko_2v2_opad`,
  w których wyznacznikiem decyzji jest CRT (szyna zimna) zamiast HRT:
  `funkcja_fuzzy_ryzyko_2v2_crt_progi.py`, `_crt_pelny.py`, `_opad_crt_progi.py`,
  `_opad_crt_pelny.py` (zarejestrowane w `rejestr_algorytmow.py` pod tymi samymi
  nazwami, bez podfolderu — leżą wprost w `Algorytmy/`, jak każdy inny algorytm).
- `benchmark/testy/test_wszystkie_rownolegle_crt.py` — dedykowany skrypt testowy:
  domyślnie 4 nowe algorytmy + `algorytm_z_normy`, na 10 najzimniejszych lokalizacjach.
  Excel wynikowy: `Podsumowanie_calkowite_zmienione_crt.xlsx`.
- `benchmark/testy/test_wszystkie_rownolegle.py` — **niezmieniony kod**, ale ponieważ
  importuje po prostu `symulacja_fizyczna`, w tym folderze automatycznie liczy
  WSZYSTKIE 49 algorytmów (45 oryginalnych + 4 nowe) na NOWYM obiekcie — zweryfikowane.

## Co NIE zostało skopiowane (celowo)

- `wyniki/` — puste, tworzone od nowa przy pierwszym uruchomieniu.
- `slurm/` — pominięte na razie (praca lokalna, nie na klastrze) — jeśli
  potrzebne, można dociągnąć z oryginału i podmienić `symulacja_fizyczna` w
  skryptach tak jak tutaj.
- `__pycache__/`.

## Status: w toku

Optymalizacja funkcji ryzyka (`Algorytmy/funkcja_ryzyka_wspolne.py`) i cyfrowych
bliźniaków (`Algorytmy/rdzen_kontrolera.py`) pod kątem CRT jako głównego
wyznacznika — **jeszcze nie zrobiona w tej kopii**, czeka na doprecyzowanie
zakresu (patrz rozmowa z 2026-09-26).
