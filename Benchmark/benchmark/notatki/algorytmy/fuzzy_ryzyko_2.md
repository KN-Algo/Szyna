# fuzzy_ryzyko_2

- **Plik / klasa / metoda:** `Algorytmy/funkcja_fuzzy_ryzyko_2.py` / `KontrolerFuzzyRyzyko2` / `fuzzy_ryzyko`
- **Typ:** Fuzzy logic (FL2, binarny) · **Cel:** Funkcja ryzyka (Kalman) · **Adaptacyjny:** tak ·
  **Bezpiecznik:** tak

## Jak działa

Jak [fuzzy_ryzyko_1.md](fuzzy_ryzyko_1.md) (cel z kaskady 4 priorytetów funkcji ryzyka, autotest
startowy + cyfrowy bliźniak identyczne), ale wykonawczo silnik `wnioskowanie_fl_podstawowe` +
**`binaryzuj`** (twarde 0/100% przy progu 50%) zamiast miękkiego obcięcia krańców FL1 — zachowuje się
jak przełącznik sterowany rozmytą oceną błędu temperatury zamiast regulatora proporcjonalnego.

## FLOPs

Szacunek: **490/krok** (kaskada 20 + silnik 40 — identyczny koszt silnika co FL1, binaryzacja
pomijalna). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy` + silnik `silniki_fuzzy` (współdzielony z
`fuzzy_logic_2.py`). Wariant z prognozą opadu: [fuzzy_ryzyko_2_opad.md](fuzzy_ryzyko_2_opad.md).
