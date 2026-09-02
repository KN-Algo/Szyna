# risk_function_pid_auto

- **Plik / klasa / metoda:** `Algorytmy/funkcja_ryzyka_pid_auto_strojenie.py` /
  `KontrolerRyzykaPIDAutoStrojenie` / `risk_function_pid_auto`
- **Typ:** PID (PI, SIMC, auto-strojenie progów) · **Cel:** Funkcja ryzyka (Kalman) + progi
  strojone automatycznie · **Adaptacyjny:** tak · **Bezpiecznik:** tak

## Jak działa

Implementacja propozycji z [`notatki/propozycja_auto_strojenie.md`](../propozycja_auto_strojenie.md)
("perturb-and-observe", proste wspinanie po zboczu bez gradientu) — **realny, działający algorytm**,
nie tylko projekt na papierze. Dziedziczy CAŁĄ logikę [risk_function_pid](risk_function_pid.md)
(autotest, SIMC, kaskada 4 priorytetów, cyfrowy bliźniak) bez zmian — woła
`self.risk_function_pid(row_data)` i DOKŁADA na wierzchu automatyczne strojenie 4 progów setpointu:

- `hrt_on_precip` (cel bazowy przy opadzie), `at_low_freeze` (próg suchego mrozu),
  `hrt_on_dry` (cel przy suchym mrozie), `risk_snow_penalty_per_mm_c` (kara za mm zalegającego śniegu).

Co **7 dni symulowanego czasu** (`OKRES_STROJENIA_S`): liczy **koszt** minionego okresu = całka mocy
(%·h, proxy energii — celowo NIE prawdziwe kWh, żeby nie importować stałej grzałki z
`symulacja_fizyczna.py`) + `WAGA_KARA_H=50.0` × (godziny spędzone z przekroczonym progiem
śniegu/lodu/przegrzania — te same progi `KARA_*` co `nauka_kary_wspolna.py`, dla spójności).
Porównuje z kosztem POPRZEDNIEGO okresu: koszt spadł → kontynuuje ten sam kierunek zmiany dla
KAŻDEGO progu; koszt wzrósł → ODWRACA kierunek wszystkich naraz. Każdy próg ma własny mały krok
(np. `hrt_on_precip` ±0.2°C/okres) i twarde granice (`GRANICE_STROJENIA`).

Grubość śniegu do liczenia kar czytana **bezpośrednio z `self._snieg_estymowany_mm`** (już
zaktualizowanego przez `risk_function_pid`→`_evaluate_risk_setpoint`→`_estymuj_grubosc_sniegu_mm` w
TYM SAMYM kroku) — NIE wołana druga metoda, bo to podwójnie doliczyłoby przyrost/ubytek.

Historia każdej aktualizacji w `self.historia_strojenia` (aliasowana jako `self.historia_uczenia`,
żeby `test_wszystkie_rownolegle.py` automatycznie zapisał ją do `<lok>_risk_function_pid_auto_uczenie.csv`
bez zmian w skrypcie) → własna zakładka **"Strojenie_progow_ryzyka"** w Excelu (schemat inny niż
"Uczenie_adaptacyjne" rodziny `nauka_kary_*`, stąd osobna zakładka).

**Zweryfikowane działanie** (25-dniowe okno, Abisko+Ojmiakon): progi realnie oscylują między dwoma
stanami zgodnie z logiką (koszt spadł → kontynuuj; koszt wzrósł → odwróć) — prześledzone ręcznie na
3 kolejnych aktualizacjach, zgadza się co do liczby. **Zaobserwowane ograniczenie**: koszt bywa mocno
zmienny między okresami z powodu zmienności POGODY (śnieżny tydzień vs spokojny), nie tylko wyboru
progów — sygnał hill-climbingu jest więc zaszumiony przez czynnik, którego algorytm nie kontroluje
(zgodne z ograniczeniami opisanymi w propozycji: brak eksploracji losowej, wrażliwość na `WAGA_KARA_H`).

## FLOPs

Szacunek: **460/krok** — jak `risk_function_pid` (450) + mały narzut księgowania strojenia (rejestracja
kar, całka mocy) + amortyzowany skok co 7 dni (kilka porównań/przypisań, tani). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_ryzyka_pid.KontrolerRyzykaPID` bez nadpisywania jej logiki. Wymagał PROMOCJI
`RISK_SNOW_PENALTY_PER_MM_C` z modułowej stałej do atrybutu instancji `self.risk_snow_penalty_per_mm_c`
w `funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy.__init__` (domyślna wartość = stała modułowa, zero
zmiany zachowania dla WSZYSTKICH pozostałych 29 algorytmów — zmiana dotyczy jednej linii użycia w
`_evaluate_risk_setpoint`). Wariant bez strojenia: [risk_function_pid.md](risk_function_pid.md).
