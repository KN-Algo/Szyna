# fuzzy_ryzyko_3_opad

- **Plik / klasa / metoda:** `Algorytmy/funkcja_fuzzy_ryzyko_3_opad.py` / `KontrolerFuzzyRyzyko3Opad` /
  `fuzzy_ryzyko_opad`
- **Typ:** Fuzzy logic (FL3, PWM) · **Cel:** Funkcja ryzyka (Kalman) + prognoza opadu ·
  **Adaptacyjny:** tak · **Bezpiecznik:** tak

## Jak działa

Jak [fuzzy_ryzyko_3.md](fuzzy_ryzyko_3.md) (cel z kaskady funkcji ryzyka, wykonawczo PWM), plus furtka
prognozy opadu w setpointcie — patrz [risk_function_opad.md](risk_function_opad.md) po opis furtki.

**Uwaga z testów odporności na awarie czujników** (`test_awarie_czujnikow.py` /
`Podsumowanie_awarii.xlsx`): ten konkretny wariant wykazał SILNE niedogrzewanie pod wpływem biasu na
czujniku HRT — kombinacja "cel z ryzyka + PWM + furtka opadowa" okazała się najbardziej wrażliwa ze
sprawdzanych na tę konkretną awarię. Warto to zweryfikować/monitorować przy każdej zmianie w tej
rodzinie.

## FLOPs

Szacunek: **507/krok** (kaskada 20 + silnik FL1 amortyzowany do cyklu PWM + krok PWM + rzadka
prognoza opadu). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_ryzyka_wspolne.KontrolerRyzykaOpadBazowy` + mechanizm PWM. Wariant bez opadu:
[fuzzy_ryzyko_3.md](fuzzy_ryzyko_3.md).
