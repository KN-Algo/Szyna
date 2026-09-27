# fuzzy_ryzyko_1_opad

- **Plik / klasa / metoda:** `Algorytmy/funkcja_fuzzy_ryzyko_1_opad.py` / `KontrolerFuzzyRyzyko1Opad` /
  `fuzzy_ryzyko_opad`
- **Typ:** Fuzzy logic (FL1, ciągły) · **Cel:** Funkcja ryzyka (Kalman) + prognoza opadu ·
  **Adaptacyjny:** tak · **Bezpiecznik:** tak

## Jak działa

Jak [fuzzy_ryzyko_1.md](fuzzy_ryzyko_1.md) (cel z kaskady funkcji ryzyka, wykonawczo silnik FL1,
autotest + cyfrowy bliźniak), plus furtka prognozy opadu w setpointcie
(`_evaluate_risk_setpoint_z_opadem` — patrz [risk_function_opad.md](risk_function_opad.md)). Silnik
rozmyty sam w sobie NIE korzysta z prognozy opadu bezpośrednio — dostaje tylko finalny
`target_temperature`/`need_heat` już uwzględniający furtkę.

## FLOPs

Szacunek: **505/krok** (kaskada 20 + silnik FL1 40 + amortyzowane skoki + rzadka prognoza opadu).
Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_ryzyka_wspolne.KontrolerRyzykaOpadBazowy` + silnik `silniki_fuzzy`. Wariant bez
opadu: [fuzzy_ryzyko_1.md](fuzzy_ryzyko_1.md).
