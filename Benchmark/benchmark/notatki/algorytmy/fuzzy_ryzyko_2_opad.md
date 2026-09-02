# fuzzy_ryzyko_2_opad

- **Plik / klasa / metoda:** `Algorytmy/funkcja_fuzzy_ryzyko_2_opad.py` / `KontrolerFuzzyRyzyko2Opad` /
  `fuzzy_ryzyko_opad`
- **Typ:** Fuzzy logic (FL2, binarny) · **Cel:** Funkcja ryzyka (Kalman) + prognoza opadu ·
  **Adaptacyjny:** tak · **Bezpiecznik:** tak

## Jak działa

Jak [fuzzy_ryzyko_2.md](fuzzy_ryzyko_2.md) (cel z kaskady funkcji ryzyka, wykonawczo silnik FL2
binarny), plus furtka prognozy opadu w setpointcie — patrz
[risk_function_opad.md](risk_function_opad.md) po opis furtki.

## FLOPs

Szacunek: **505/krok** (kaskada 20 + silnik 40 + rzadka prognoza opadu). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_ryzyka_wspolne.KontrolerRyzykaOpadBazowy` + silnik `silniki_fuzzy`. Wariant bez
opadu: [fuzzy_ryzyko_2.md](fuzzy_ryzyko_2.md).
