# fuzzy_ryzyko_1

- **Plik / klasa / metoda:** `Algorytmy/funkcja_fuzzy_ryzyko_1.py` / `KontrolerFuzzyRyzyko1` / `fuzzy_ryzyko`
- **Typ:** Fuzzy logic (FL1, ciągły) · **Cel:** Funkcja ryzyka (Kalman) · **Adaptacyjny:** tak ·
  **Bezpiecznik:** tak

## Jak działa

**Hybryda**: cel (setpoint) wyznaczany przez tę samą kaskadę 4 priorytetów co `risk_function_pid`
(`_evaluate_risk_setpoint` — patrz [risk_function_pid.md](risk_function_pid.md)), ale WYKONAWCZO
obsłużony silnikiem rozmytym FL1 (`silniki_fuzzy.wnioskowanie_fl_podstawowe` + `klamra_fl1`) zamiast
histerezy/PID. Funkcja ryzyka dostarcza WYŁĄCZNIE `target_temperature` i `need_heat` — samą moc zawsze
wylicza silnik rozmyty na podstawie `blad_T = target - HRT`.

Wykonuje ten sam **jednorazowy autotest startowy** co `risk_function_pid` — dopóki trwa, grzeje pełną
mocą. Wynik identyfikacji zasila fizyczną prognozę HRT w `_evaluate_risk_setpoint` (cyfrowy bliźniak),
ale sam silnik rozmyty NIE jest przez to przestrajany (nie ma odpowiednika SIMC dla progów rozmytych)
— korzysta tylko z lepszego/dokładniejszego celu i prognozy `warmup_soon`.

## FLOPs

Szacunek: **490/krok** (kaskada 20 + silnik FL1 40, plus amortyzowane skoki Kalman/bliźniak — więcej
niż `risk_function_pid` mimo prostszego wykonawcy, bo brak zaoszczędzenia z formuły PI vs koszt
podobny). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy` (setpoint) + silnik `silniki_fuzzy`
(współdzielony z `fuzzy_logic_1.py`). Wariant z prognozą opadu:
[fuzzy_ryzyko_1_opad.md](fuzzy_ryzyko_1_opad.md). Rodzeństwo z innym silnikiem:
[fuzzy_ryzyko_2.md](fuzzy_ryzyko_2.md), [fuzzy_ryzyko_2v2.md](fuzzy_ryzyko_2v2.md),
[fuzzy_ryzyko_3.md](fuzzy_ryzyko_3.md).
