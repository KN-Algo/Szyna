# fuzzy_ryzyko_2v2

- **Plik / klasa / metoda:** `Algorytmy/funkcja_fuzzy_ryzyko_2v2.py` / `KontrolerFuzzyRyzyko2v2` / `fuzzy_ryzyko`
- **Typ:** Fuzzy logic (FL2v2, binarny, 7 reguł) · **Cel:** Funkcja ryzyka (Kalman) · **Adaptacyjny:** tak ·
  **Bezpiecznik:** tak

## Jak działa

Jak [fuzzy_ryzyko_2.md](fuzzy_ryzyko_2.md) (cel z kaskady funkcji ryzyka, autotest + bliźniak), ale
wykonawczo silnik `silniki_fuzzy.wnioskowanie_fl2v2` (7 reguł, dodatkowa reguła śnieg+chłodno, próg
"lodowato" zależny od intensywności opadu — patrz [fuzzy_logic_2v2.md](fuzzy_logic_2v2.md) po pełny
opis różnic silnika) zamiast podstawowego 6-regułowego. Próg wykrycia deszczu w tym wariancie:
`precip > 0.2` (nie `> 0.0` jak w reszcie rodziny) — spójnie z oryginalnym `fuzzy_logic_2v2.py`.

## FLOPs

Szacunek: **498/krok** (kaskada 20 + silnik FL2v2 48 — o 8 więcej niż silniki FL1/FL2 z powodu
dodatkowej reguły). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy` + silnik `wnioskowanie_fl2v2` (współdzielony
z `fuzzy_logic_2v2.py`). Wariant z prognozą opadu:
[fuzzy_ryzyko_2v2_opad.md](fuzzy_ryzyko_2v2_opad.md).
