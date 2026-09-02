# fuzzy_normy_2v2

- **Plik / klasa / metoda:** `Algorytmy/funkcja_fuzzy_normy_2v2.py` / `KontrolerFuzzyNormy2v2` / `fuzzy_normy`
- **Typ:** Fuzzy logic (FL2v2, binarny, 7 reguł) · **Cel:** Progi normy LET-1 · **Adaptacyjny:** nie ·
  **Bezpiecznik:** tak

## Jak działa

Jak [fuzzy_normy_2.md](fuzzy_normy_2.md) (cel z progów normy LET-1, wyjście binarne), ale wykonawczo
silnik `wnioskowanie_fl2v2` (7 reguł, próg "lodowato" zależny od intensywności opadu) — patrz
[fuzzy_logic_2v2.md](fuzzy_logic_2v2.md) po opis różnicy silnika.

## FLOPs

Szacunek: **48/krok** (progi normy 10 + silnik FL2v2 48... uwaga: rejestr podaje `flops_na_krok: 48`
dla tego wpisu, co odpowiada samemu silnikowi — koszt progów normy jest w praktyce wliczony w ten sam
rząd wielkości szacunku). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_normy_wspolne.KontrolerNormyCiaglaBazowy` + silnik współdzielony z
`fuzzy_logic_2v2.py`. Ten sam silnik, cel z funkcji ryzyka: [fuzzy_ryzyko_2v2.md](fuzzy_ryzyko_2v2.md).
