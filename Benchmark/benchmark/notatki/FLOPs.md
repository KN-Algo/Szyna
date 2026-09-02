# Jak liczymy FLOPs dla każdego algorytmu

Są DWA, celowo różne sposoby liczenia FLOPs w tym projekcie — nie mylić ich ze sobą:

1. **Szacunek analityczny** (`flops_na_krok` w `Algorytmy/rejestr_algorytmow.py`) — jedna liczba na
   algorytm, wyliczona ręcznie przez przeczytanie kodu i policzenie operacji w typowej ścieżce. Stała,
   niezależna od konkretnego przebiegu.
2. **Licznik rzeczywisty** (`self._flops_licznik`, kolumna `flops_rzeczywiste` w
   `PRZEGLAD_ZBIORCZY.csv` / "FLOPs (zmierzone)" w Excelu) — RZECZYWIŚCIE wykonane operacje w
   KONKRETNYM przebiegu na KONKRETNEJ lokalizacji, sumowane krok po kroku przez sam kontroler podczas
   symulacji. To jest pomiar, nie szacunek.

Te dwie liczby różnią się i **to jest oczekiwane** — patrz sekcja "Dlaczego się różnią" niżej.

## 1. Licznik rzeczywisty — jak to działa w kodzie

Każdy kontroler dziedziczący `KontrolerBazowy` (`Algorytmy/rdzen_kontrolera.py`) ma atrybut
`self._flops_licznik = 0` ustawiany w `__init__` i metodę:

```python
def _dodaj_flopy(self, n):
    self._flops_licznik += n
```

Kontrolery, które NIE dziedziczą po `KontrolerBazowy` (bo nie potrzebują pamięci/prognozy —
`algorytm_z_normy.py`, `fuzzy_logic_1/2/2v2/3.py`) definiują `self._flops_licznik = 0` samodzielnie i
inkrementują go bezpośrednio (`self._flops_licznik += n`) — funkcjonalnie identyczne, po prostu bez
wspólnej klasy bazowej do dziedziczenia.

Po zakończeniu przebiegu `symulacja_fizyczna.uruchom_kontroler` odczytuje licznik:

```python
'flops_rzeczywiste': getattr(controller, '_flops_licznik', None),
```

i zapisuje go do statystyk przebiegu — trafia do `PRZEGLAD_ZBIORCZY.csv` i zakładki `Dane` w Excelu
(`generuj_excel_podsumowanie.py`), gdzie zakładka `Zlozonosc_obliczeniowa` zestawia go ze
`flops_na_krok` (patrz sekcja 3).

Każda metoda decyzyjna algorytmu wywołuje `_dodaj_flopy(n)` (albo `self._flops_licznik += n` w
klasach bez wspólnej bazy) z liczbą `n` dobraną ręcznie przez policzenie mnożeń/dodawań w danym bloku
kodu — to NIE jest automatyczny profiler instrukcji, tylko ręczna adnotacja przy każdym nietrywialnym
obliczeniu. Poniżej pełna lista miejsc, które coś liczą, z dokładnym wzorem na `n`.

### Wspólny rdzeń (`rdzen_kontrolera.py`) — używany przez KAŻDY kontroler z pamięcią/prognozą

| Miejsce | Wzór na `n` | Co się liczy |
|---|---|---|
| `_kalman_forecast_series` | `len(historia) * 20 + kroki_prognozy * 7` | Filtr Kalmana (poziom+trend): ~20 FLOPs/próbka historii (aktualizacja stanu + kowariancji 2×2), ~7 FLOPs/krok prognozy w przód |
| `_forecast_attribute` (bin averaging) | `len(bin_ids) * 3` | Grupowanie historii do siatki 15-min (`_bin_average_core`, JIT numba) — sumowanie w grupie + porównanie bin_id |
| `_forecast_attribute` (interpolacja) | `len(pelne_biny) * 2` | `np.interp` na ewentualne luki w siatce — wyszukanie przedziału + interpolacja liniowa |
| `_krok_modelu` (cyfrowy bliźniak, 1 krok) | `2*n² + 2*n` (n = wymiar stanu modelu) | Krok stanowy `A@x + B*u` — mnożenia macierzowe |
| `_prognoza_zanikania_ciepla` (cyfrowy bliźniak, symulacja w przód) | `liczba_krokow * (2*n² + 4*n + 1)` | Pętla `C@x + D*u` (odczyt wyjścia) + `A@x + B*u` (krok stanu) na każdy z `liczba_krokow` kroków prognozy |

**Estymator grubości śniegu** (`_estymuj_grubosc_sniegu_mm`, patrz `rdzen_kontrolera.py`) — dodaje `4`
FLOPs na wywołanie (2 mnożenia + odjęcie + `max`/clip). Wołany raz na krok przez `_evaluate_risk_setpoint`
(rodzina `risk_function*`) i `_evaluate_nauczony_setpoint` (rodzina `nauka_kary*`) — zastąpił darmowy
odczyt pola `row_data['SNIEG_GRUBOSC_MM']` (2026-09-02, patrz AGENTS.md), więc te dwie rodziny mają od
teraz o 4 FLOPy/krok więcej niż analityczne szacunki w rejestrze zakładały (pomijalne wobec setek
FLOPs/krok tych algorytmów, nie warto przeliczać `flops_na_krok` w rejestrze dla tak małej różnicy).

`temperature_prediction()`/`rail_temperature_prediction()` wołają `_forecast_attribute`, które
wewnętrznie woła `_kalman_forecast_series` — czyli jedno wywołanie prognozy Kalmana dopisuje FLOPy z
WSZYSTKICH TRZECH pierwszych wierszy naraz. Dzięki cache'owaniu (`TEMP_FORECAST_REFRESH_S = 300 s`)
realnie dzieje się to raz na 300 sekund symulowanego czasu, nie co krok — stąd "amortyzowane" w opisie
złożoności czasowej w rejestrze.

### Logika decyzyjna — osobno per algorytm

| Algorytm(y) | Miejsce | `n` | Co się liczy |
|---|---|---|---|
| `compute_control` (histereza LET-1) | `histereza_let1.py` | `45` | `calculate_risk_level` (10 progów) + histereza + limit przełączeń |
| `compute_control_gorski` | `histereza_let1_gorski.py` | `45` | Identyczne jak `compute_control` (dziedziczy bez zmiany logiki, tylko inna stała progowa) |
| `algorytm_z_normy` | `algorytm_z_normy.py` | `18` | Porównania progów + logika stanu (automat pogodowy czysty) |
| `risk_function` | `funkcja_ryzyka_wspolne.py` (`_evaluate_risk_setpoint`) + `funkcja_ryzyka_binarna.py` | `20` + `15` | Kaskada 4 priorytetów (20) + histereza/limit przełączeń (15) |
| `risk_function_pid` | jw. + `funkcja_ryzyka_pid.py` | `20` + `15` | Kaskada (20) + formuła PI(D) + anti-windup (15) |
| `norma_pid` | `funkcja_normy_wspolne.py` + `funkcja_pid_normy.py` | `10` + `15` | Progi normy (10) + PI(D) (15) |
| `fuzzy_logic_1/2` | `fuzzy_logic_1.py`/`_2.py` | `40` | Silnik FL1/FL2 (4 funkcje przynależności + 6 reguł Sugeno) |
| `fuzzy_logic_2v2` | `fuzzy_logic_2v2.py` | `48` | Silnik FL2v2 (4 f. przynależności + 7 reguł) |
| `fuzzy_logic_3` | `fuzzy_logic_3.py` | `40` (raz/60s cyklu PWM) + `2`/krok | Silnik FL1 liczony RAZ na cykl PWM + krok PWM (porównanie licznika) |
| `fuzzy_ryzyko_1` | `funkcja_fuzzy_ryzyko_1.py` | `20` + `40` | Kaskada ryzyka (20) + silnik FL1 (40) |
| `fuzzy_ryzyko_2` | `funkcja_fuzzy_ryzyko_2.py` | `20` + `40` | Kaskada (20) + silnik FL1/FL2 (40, FL2 to samo wnioskowanie + binaryzacja) |
| `fuzzy_ryzyko_2v2` | `funkcja_fuzzy_ryzyko_2v2.py` | `20` + `48` | Kaskada (20) + silnik FL2v2 (48) |
| `fuzzy_ryzyko_3` | `funkcja_fuzzy_ryzyko_3.py` | `20` + `40`/cykl + `2`/krok | Kaskada (20) + silnik FL1 raz/cykl PWM + krok PWM |
| `fuzzy_normy_1/2` | `funkcja_fuzzy_normy_1.py`/`_2.py` | `10` + `40` | Progi normy (10) + silnik FL1/FL2 (40) |
| `fuzzy_normy_2v2` | `funkcja_fuzzy_normy_2v2.py` | `10` + `48` | Progi normy (10) + silnik FL2v2 (48) |
| `fuzzy_normy_3` | `funkcja_fuzzy_normy_3.py` | `10` + `40`/cykl + `2`/krok | Progi normy (10) + silnik FL1 raz/cykl PWM + krok PWM |
| `risk_function_opad` | `funkcja_ryzyka_wspolne.py` (`_evaluate_risk_setpoint` + `_front_ustepuje`) + `funkcja_ryzyka_binarna_opad.py` | `20` + `160`* + `15` | Kaskada (20) + prognoza opadu (160, tylko gdy furtka śniegu w ogóle jest sprawdzana) + histereza (15) |
| `risk_function_pid_opad` | jw. + `funkcja_ryzyka_pid_opad.py` | `20` + `160`* + `15` | Kaskada + prognoza opadu + PI(D) |
| `fuzzy_ryzyko_1/2_opad` | odpowiednie `_opad.py` | `20` + `160`* + `40` | Kaskada + prognoza opadu + silnik FL1/FL2 |
| `fuzzy_ryzyko_2v2_opad` | jw. | `20` + `160`* + `48` | Kaskada + prognoza opadu + silnik FL2v2 |
| `fuzzy_ryzyko_3_opad` | jw. | `20` + `160`* + `40`/cykl + `2`/krok | Kaskada + prognoza opadu + FL1 PWM |
| `nauka_kary` | `funkcja_nauka_kary_wspolna.py` (`_evaluate_nauczony_setpoint`, wliczone w próg normy `10`) + `funkcja_nauka_kary_pid.py` | `10` + `15` | Progi normy + korekta uczenia (rejestracja kar to proste porównania, nie liczone osobno) + PI(D) |
| `nauka_kary_temp` | jw. + `funkcja_nauka_kary_pid_temp.py` | `10` + `2*8` + `15` | jw. + przejrzenie prognozy AT (8 kroków, min/any) |
| `nauka_kary_opad` | jw. + `funkcja_nauka_kary_pid_opad.py` | `10` + `160`* + `15` | jw. + prognoza opadu |
| `nauka_kary_blizniak` | jw. + `funkcja_nauka_kary_pid_blizniak.py` | `10` + `2*8` + `15` | jw. + przejrzenie prognozy HRT z cyfrowego bliźniaka (8 kroków) |
| `nauka_kary_ryzyko` | jw. + `funkcja_nauka_kary_pid_ryzyko.py` | `10` + `2*8` + `160`* + `2*8` + `15` | jw. + WSZYSTKIE trzy prognozy (AT, opad, bliźniak HRT) połączone w jeden wynik ryzyka |

`*160` = koszt `przewidywanie_opadow.predict_winter_precipitation` (~20 FLOPs/krok horyzontu × 8
kroków) — patrz `przewidywanie_opadow.py`. Doliczany TYLKO gdy dana ścieżka kodu faktycznie woła
prognozę opadu (np. w `risk_function_opad` tylko wtedy, gdy w ogóle jesteśmy w gałęzi śniegu i
podstawowa ucieczka `warmup_soon` jeszcze nie zwolniła z grzania — patrz
`KontrolerRyzykaOpadBazowy._front_ustepuje`), więc realny, uśredniony koszt na krok jest niższy niż
suma powyżej sugerowałaby dla stałej obecności warunku.

**Autotest startowy** (`_autotest_startowy`/`autotest`/`_identify_sopdt`) NIE jest liczony do
`_flops_licznik` w ogóle — to jednorazowy koszt (raz na cały przebieg, do 14400 kroków), analitycznie
opisany osobno w `zlozonosc_czasowa` w rejestrze, celowo pominięty w liczniku rzeczywistym, żeby nie
zniekształcał porównania "koszt na krok w stanie ustalonym" między algorytmami.

## 2. Szacunek analityczny — `flops_na_krok` w rejestrze

Pole `flops_na_krok` w `Algorytmy/rejestr_algorytmow.py` to RĘCZNIE wyliczona ŚREDNIA liczba FLOPs na
krok, uwzględniająca amortyzację skoków co `TEMP_FORECAST_REFRESH_S` (prognoza Kalmana, raz na 300
kroków) i co `HORIZON_STEPS*STEP_SECONDS=7200` kroków (symulacja cyfrowego bliźniaka w przód) — czyli
to NIE jest suma stałych z tabeli wyżej, tylko: koszt-stały-co-krok + (koszt-skoku / okres-skoku).
Wyliczona przez czytanie kodu, NIE profilerem. Traktuj jako rząd wielkości (dziesiątki-setki
FLOPs/krok), nie dokładną liczbę cykli procesora.

## 3. Dlaczego się różnią (i to jest w porządku)

Licznik rzeczywisty i szacunek analityczny mierzą to samo pojęciowo, ale z innych źródeł, więc się
rozjeżdżają:

- **Szacunek** zakłada "typową" długość historii przy amortyzacji skoków (np. że bufor Kalmana urósł
  do jakiegoś rozsądnego rozmiaru). **Licznik rzeczywisty** liczy DOKŁADNIE tyle, ile faktycznie się
  wydarzyło w TYM przebiegu — jeśli historia urosła większa niż szacunek zakładał (bo próg przycinania
  `SENSOR_HISTORY_MAX_SAMPLES=43200` jest wysoki), koszt `_kalman_forecast_series` (proporcjonalny do
  `len(historia)`) jest realnie wyższy.
- To odkrycie NIE jest hipotetyczne — dokładnie to się stało dla rodziny `risk_function*`: pomiar
  pokazał koszt ~3.3x wyższy niż analityczny szacunek, bo historia realnie rosła do ~86400 próbek
  zanim przycinanie zadziałało (próg przycinania to `SENSOR_HISTORY_MAX_SAMPLES*2`), nie do 43200 jak
  szacunek zakładał.
- Prognoza opadu/bliźniaka jest WARUNKOWA (wołana tylko w niektórych gałęziach kodu) — szacunek
  zakłada jakąś średnią częstość tych gałęzi, licznik rzeczywisty odzwierciedla DOKŁADNIE tyle, ile razy
  dana gałąź faktycznie wykonała się w danej pogodzie/lokalizacji (więcej opadu = więcej wywołań
  `_front_ustepuje` = więcej FLOPs).

**Wniosek praktyczny**: do porównania "który algorytm jest droższy obliczeniowo" ufaj kolumnie
`flops_rzeczywiste` (zakładka `Zlozonosc_obliczeniowa` w Excelu zestawia obie wartości obok siebie
właśnie po to, żeby to rozbieżność było widać na pierwszy rzut oka) — `flops_na_krok` w rejestrze
przydaje się tylko do orientacyjnego "z grubsza jakiego rzędu wielkości się spodziewać" PRZED
odpaleniem przebiegu.

## 4. Dlaczego w ogóle FLOPs, skoro to nie jest wąskie gardło wydajności

Warto pamiętać (patrz też komentarz w rejestrze): realny czas symulacji (minuty/godziny) wynika z
narzutu interpretera Pythona/pandas na krok, NIE z limitu przepustowości FLOPs procesora — te
dziesiątki/setki FLOPs na krok to nic dla współczesnego CPU. Liczymy je mimo to, bo:

1. Pozwalają **obiektywnie PORÓWNAĆ** złożoność logiki decyzyjnej między algorytmami (np. `norma_pid`
   ~18-25 FLOPs/krok vs `nauka_kary_ryzyko` ~640 FLOPs/krok szacunkowo) niezależnie od tego, jak szybko
   akurat działa Python na danym sprzęcie.
2. Pozwalają **zweryfikować założenia** analitycznego szacunku (patrz sekcja 3 wyżej) — rozbieżność
   3.3x dla `risk_function*` byłaby niewidoczna bez rzeczywistego pomiaru.
3. Docelowo (sterowniki rzeczywiste, nie symulacja) to jest realny budżet obliczeniowy na
   mikrokontrolerze, gdzie setki FLOPs na krok MOGĄ mieć znaczenie przy bardzo ograniczonych zasobach.
