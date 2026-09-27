# fuzzy_ryzyko_2v2_opad

- **Plik / klasa / metoda:** `Algorytmy/funkcja_fuzzy_ryzyko_2v2_opad.py` / `KontrolerFuzzyRyzyko2v2Opad` /
  `fuzzy_ryzyko_opad`
- **Typ:** Fuzzy logic (FL2v2, binarny, 7 reguł) · **Cel:** Funkcja ryzyka (Kalman) + prognoza opadu ·
  **Adaptacyjny:** tak · **Bezpiecznik:** tak

## Jak działa

Jak [fuzzy_ryzyko_2v2.md](fuzzy_ryzyko_2v2.md) (cel z kaskady funkcji ryzyka, wykonawczo silnik FL2v2
7-regułowy), plus furtka prognozy opadu w setpointcie — patrz
[risk_function_opad.md](risk_function_opad.md) po opis furtki.

## FLOPs

Szacunek: **513/krok** (kaskada 20 + silnik FL2v2 48 + rzadka prognoza opadu — najwyższy koszt
spośród rodziny `fuzzy_ryzyko_*_opad` z powodu dodatkowej reguły silnika). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_ryzyka_wspolne.KontrolerRyzykaOpadBazowy` + silnik `wnioskowanie_fl2v2`. Wariant
bez opadu: [fuzzy_ryzyko_2v2.md](fuzzy_ryzyko_2v2.md).
